"""
controller.py – Core Mapping CRUD, Cascade Orchestration & MAME Config
=========================================================================

Phase 2 (v1-persona-split): Slimmed monolith.

This router retains ONLY the "Shared Core" that both
ControllerChuckPanel and ConsoleWizardPanel depend on:

  • Mapping CRUD          – GET/POST /mapping, /mapping/preview, /mapping/apply, /mapping/reset
  • Cascade Orchestration – /cascade/status, /cascade/apply
  • Golden Drive Reset    – /admin/golden-reset
  • Baseline State        – /baseline
  • Effective Paths       – /effective-paths
  • MAME Config           – /mame-config/preview, /mame-config/apply, /mame-config/validate

Hardware endpoints (board sanity, firmware, USB, detection, refresh, health)
have moved to  →  routers/chuck_hardware.py

Wizard / mapping endpoints (learn wizard, click-to-map, wiring wizard,
encoder mode, player identity, genre profiles, MAME per-game fix)
have moved to  →  routers/wizard_mapping.py

Shared helpers live in  →  services/controller_shared.py
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

from ..services.policies import require_scope, is_allowed_file
from ..services.backup import create_backup
from ..services.diffs import compute_diff, has_changes
from ..services.controller_baseline import (
    ControllerBaselineError,
    build_encoder_snapshot,
    discover_and_expand_emulators,
    get_baseline_path,
    get_cascade_preference,
    load_controller_baseline,
    update_controller_baseline,
)
from ..services.controller_cascade import (
    enqueue_cascade_job,
    run_cascade_job,
    _default_config_hint_for_emulator,
    _resolve_config_path,
)
from ..services.mame_config_generator import (
    MAMEConfigError,
    generate_mame_config,
    get_mame_config_summary,
    validate_mame_config,
)
from ..services.mame_hot_swap import (
    write_ephemeral_config,
    clear_ephemeral_config,
    get_ephemeral_status,
)
from ..services.controller_shared import log_controller_change
from ..services.controller_bridge import (
    ControllerBridge,
    ControllerBridgeError,
    ConflictError,
)

# Board detection – used by GET /mapping for real-time status
try:
    from ..services.board_detection import (
        BoardDetectionError,
        BoardNotFoundError,
        PactoTechBoard,
        get_detection_service,
    )
except ImportError:
    BoardDetectionError = Exception
    BoardNotFoundError = Exception
    PactoTechBoard = None  # type: ignore[assignment, misc]

    def get_detection_service():  # type: ignore[misc]
        raise ImportError("Board detection not available")


logger = logging.getLogger(__name__)

router = APIRouter()

# Audit log (in-memory, capped)
audit_log: List[Dict[str, Any]] = []


# ============================================================================
# Utility Helpers (core-only)
# ============================================================================

def _ensure_writes_allowed(request: Request) -> None:
    """Block writes when startup marked drive root invalid."""
    if not getattr(request.app.state, "writes_allowed", True):
        reason = getattr(
            request.app.state,
            "write_block_reason",
            "AA_DRIVE_ROOT is not set; writes are disabled until it is configured.",
        )
        raise HTTPException(status_code=503, detail=reason)


def _mapping_paths(drive_root: Path) -> tuple[Path, Path]:
    mapping_file = drive_root / "config" / "mappings" / "controls.json"
    factory_file = drive_root / "config" / "mappings" / "factory-default.json"
    return mapping_file, factory_file


def _default_mapping_payload() -> Dict[str, Any]:
    return {
        "version": "1.0",
        "board": {
            "vid": "unknown",
            "pid": "unknown",
            "name": "Unassigned controller board",
            "detected": False,
            "status": "missing",
        },
        "mappings": {},
    }


def _load_mapping_seed(drive_root: Path) -> tuple[Dict[str, Any], bool, Optional[str]]:
    mapping_file, factory_file = _mapping_paths(drive_root)

    if mapping_file.exists():
        with open(mapping_file, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data, True, "config/mappings/controls.json"

    if factory_file.exists():
        try:
            with open(factory_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data, False, "config/mappings/factory-default.json"
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Factory default mapping unreadable at %s: %s", factory_file, exc)

    return _default_mapping_payload(), False, None


def _regenerate_mame_default_config(drive_root: Path, mapping_data: Dict[str, Any]) -> Dict[str, Any]:
    """Regenerate MAME default.cfg from mapping data.

    Called after controls.json is saved or reset to keep MAME in sync.

    Args:
        drive_root: AA drive root path
        mapping_data: The controls.json data (with 'mappings' key)

    Returns:
        Dict with 'success', 'path', and optional 'error' keys
    """
    mame_cfg_path = drive_root / "Emulators" / "MAME" / "cfg" / "default.cfg"

    try:
        # Generate clean XInput-only MAME config
        xml_config = generate_mame_config(mapping_data)

        # Ensure directory exists
        mame_cfg_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the config
        mame_cfg_path.write_text(xml_config, encoding="utf-8")

        logger.info("Regenerated MAME default.cfg with %d ports", xml_config.count("<port "))

        return {
            "success": True,
            "path": str(mame_cfg_path),
            "ports_count": xml_config.count("<port "),
        }
    except MAMEConfigError as exc:
        logger.error("Failed to generate MAME config: %s", exc)
        return {
            "success": False,
            "path": str(mame_cfg_path),
            "error": str(exc),
        }
    except Exception as exc:
        logger.error("Failed to write MAME config: %s", exc)
        return {
            "success": False,
            "path": str(mame_cfg_path),
            "error": str(exc),
        }


# ============================================================================
# Pydantic Models (core-only)
# ============================================================================

class MappingUpdate(BaseModel):
    mappings: Dict[str, Any]

class MappingValidation(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]

class CascadeApplyRequest(BaseModel):
    skip_led: bool = False
    skip_emulators: List[str] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None
    baseline: Optional[Dict[str, Any]] = None

class GoldenResetRequest(BaseModel):
    """Request model for Golden Drive Reset."""
    confirm: bool = Field(
        ...,
        description="Must be True to confirm the wipe operation"
    )
    clear_high_scores: bool = Field(
        default=False,
        description="Also clear MAME high scores (optional)"
    )


class MappingOverrideRequest(BaseModel):
    """AI-driven single-input override (Diagnosis Mode / remediate_controller_config tool).

    Q8 decision: optimistic per-input + confirm-before-commit.
    The frontend MUST show the proposal diff to the user before setting confirmed_by='user'.
    """
    control_key  : str            = Field(...,       description="e.g. 'p1.button3'")
    pin          : int            = Field(...,       description="GPIO pin number to assign")
    label        : Optional[str] = Field(None,      description="Human-readable label")
    source       : str            = Field("ai_tool", description="Origin: 'ai_tool' | 'user' | 'hardware'")
    force        : bool           = Field(False,     description="Bypass error-severity conflicts (requires reasoning)")
    confirmed_by : str            = Field("user",   description="Who confirmed: 'user' | 'ai_tool' | 'auto'")
    reasoning    : Optional[str] = Field(None,      description="AI reasoning for this override")


# ============================================================================
# Validation Helpers
# ============================================================================

def validate_mapping_structure(mapping_data: Dict[str, Any]) -> MappingValidation:
    """Validate mapping structure and detect conflicts

    Returns:
        MappingValidation with errors and warnings
    """
    errors = []
    warnings = []

    # Check required top-level keys
    required_keys = ["version", "board", "mappings"]
    for key in required_keys:
        if key not in mapping_data:
            errors.append(f"Missing required key: {key}")

    # If critical errors, return early
    if errors:
        return MappingValidation(valid=False, errors=errors, warnings=warnings)

    # Validate board structure
    board = mapping_data.get("board", {})
    board_required = ["vid", "pid", "name"]
    for key in board_required:
        if key not in board:
            errors.append(f"Missing board key: {key}")

    # Validate mappings and check for pin conflicts
    mappings = mapping_data.get("mappings", {})
    pin_usage = {}  # Track which pins are used by which controls

    for control_key, control_data in mappings.items():
        # Validate control structure
        if not isinstance(control_data, dict):
            errors.append(f"Invalid mapping for {control_key}: must be object")
            continue

        if "pin" not in control_data:
            errors.append(f"Missing pin for {control_key}")
            continue

        if "type" not in control_data:
            warnings.append(f"Missing type for {control_key}")

        # Check for pin conflicts
        pin = control_data["pin"]
        if pin in pin_usage:
            errors.append(f"Pin conflict: pin {pin} used by both {pin_usage[pin]} and {control_key}")
        else:
            pin_usage[pin] = control_key

    return MappingValidation(valid=len(errors) == 0, errors=errors, warnings=warnings)


# ============================================================================
# Internal Helpers (used by apply_controller_mapping)
# ============================================================================

def _mapping_entry_from_event(event, existing: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Create a mapping entry dict from an InputEvent."""
    label = (existing or {}).get("label") or event.control_key.replace(".", " ").title()
    mapping_type = "joystick" if event.control_type == "joystick" else "button"
    return {
        "pin": event.pin,
        "type": mapping_type,
        "label": label,
    }


def _apply_detected_event_to_mapping(request: Request, event) -> Dict[str, Any]:
    """Apply a single detected input event to the controls.json mapping file."""
    drive_root: Path = request.app.state.drive_root
    manifest = request.app.state.manifest
    mapping_path = drive_root / "config" / "mappings" / "controls.json"

    if not is_allowed_file(mapping_path, drive_root, manifest["sanctioned_paths"]):
        raise HTTPException(
            status_code=403,
            detail=f"Mapping file not in sanctioned areas: {mapping_path}",
        )

    mapping_data: Dict[str, Any] = {}
    if mapping_path.exists():
        with open(mapping_path, "r", encoding="utf-8") as handle:
            try:
                mapping_data = json.load(handle)
            except json.JSONDecodeError as exc:
                logger.warning("Invalid mappings JSON; recreating file: %s", exc)
                mapping_data = {}

    mappings = mapping_data.setdefault("mappings", {})
    existing_entry = mappings.get(event.control_key)
    updated_entry = _mapping_entry_from_event(event, existing_entry)

    pin_conflicts = [
        key
        for key, data in mappings.items()
        if key != event.control_key and isinstance(data, dict) and data.get("pin") == event.pin
    ]
    if pin_conflicts:
        logger.warning(
            "Detected pin %s already assigned to %s; overwriting with %s",
            event.pin,
            pin_conflicts,
            event.control_key,
        )

    changed = existing_entry != updated_entry or bool(pin_conflicts)

    if not changed:
        return {
            "changed": False,
            "backup_path": None,
            "mapping_path": str(mapping_path),
            "conflicts": pin_conflicts,
        }

    backup_path = None
    backup_on_write = getattr(request.app.state, "backup_on_write", False)
    if backup_on_write and mapping_path.exists():
        backup_path = create_backup(mapping_path, drive_root)

    mappings[event.control_key] = updated_entry
    mapping_data.setdefault("version", "1.0")
    mapping_data["last_modified"] = datetime.now().isoformat()
    mapping_data["modified_by"] = request.headers.get("x-device-id", "unknown")

    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    with open(mapping_path, "w", encoding="utf-8") as handle:
        json.dump(mapping_data, handle, indent=2)

    log_controller_change(
        request,
        drive_root,
        action="input_detection_update",
        details={
            "control_key": event.control_key,
            "pin": event.pin,
            "control_type": event.control_type,
            "mapping_path": str(mapping_path.relative_to(drive_root)),
        },
        backup_path=Path(backup_path) if backup_path else None,
    )

    return {
        "changed": True,
        "backup_path": str(backup_path) if backup_path else None,
        "mapping_path": str(mapping_path),
        "conflicts": pin_conflicts,
    }


def _maybe_trigger_auto_cascade(
    request: Request,
    background_tasks: BackgroundTasks,
    *,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    drive_root: Path = request.app.state.drive_root
    manifest = request.app.state.manifest
    cascade_preference = get_cascade_preference(drive_root)

    if cascade_preference != "auto":
        return None

    requested_by = request.headers.get("x-device-id", "unknown")
    backup_on_write = getattr(request.app.state, "backup_on_write", False)
    job_record = enqueue_cascade_job(
        drive_root,
        requested_by=requested_by,
        metadata=metadata,
        backup=backup_on_write,
    )
    background_tasks.add_task(
        run_cascade_job,
        drive_root,
        manifest,
        job_record["job_id"],
        backup=backup_on_write,
    )
    return job_record



# ============================================================================
# Diagnosis Mode — AI-Driven Mapping Override (Q8)
# ============================================================================

@router.post("/profiles/mapping-override")
async def mapping_override(request: Request, payload: MappingOverrideRequest):
    """AI-driven single-input mapping override via ControllerBridge.

    Decision refs (diagnosis_mode_plan.md):
      Q4  — ControllerBridge is sole merge authority
      Q7  — Hardware truth wins; 4 conflict types returned on proposal
      Q8  — 5-step atomic flow: validate → backup → write → meta → return

    Two-phase flow:
      Phase 1 (proposal):  POST with confirmed_by='pending'
                           Returns proposal + conflicts for UI diff display.
                           Does NOT write to disk.
      Phase 2 (commit):    POST with confirmed_by='user' (or 'ai_tool' / 'auto')
                           Commits atomically with backup.

    The frontend ChuckSidebar MUST show the proposal diff before confirming.
    """
    require_scope(request, "config")
    _ensure_writes_allowed(request)

    drive_root: Path = request.app.state.drive_root
    bridge = ControllerBridge(drive_root)

    # ── Phase 1: Proposal only (no write) ─────────────────────────────────────
    if payload.confirmed_by == "pending":
        try:
            proposal = bridge.propose_override(
                control_key = payload.control_key,
                pin         = payload.pin,
                label       = payload.label,
                source      = payload.source,
            )
        except ControllerBridgeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return {
            "phase"           : "proposal",
            "control_key"     : proposal["control_key"],
            "pin"             : proposal["pin"],
            "conflicts"       : proposal["conflicts"],
            "can_auto_commit" : proposal["can_auto_commit"],
            "mapping_before"  : proposal["mapping_before"],
            "mapping_after"   : proposal["mapping_after"],
            "reasoning"       : payload.reasoning,
        }

    # ── Phase 2: Commit ────────────────────────────────────────────────────────
    try:
        proposal = bridge.propose_override(
            control_key = payload.control_key,
            pin         = payload.pin,
            label       = payload.label,
            source      = payload.source,
        )
        result = bridge.commit_override(
            proposal,
            confirmed_by = payload.confirmed_by,
            force        = payload.force,
        )
    except ConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message"  : "Conflict(s) blocked the override. Use force=true to override, or resolve first.",
                "conflicts": exc.conflicts,
            },
        )
    except ControllerBridgeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Log to controller audit trail
    await log_controller_change(
        request, drive_root,
        action  = "mapping_override",
        details = {
            "control_key"  : payload.control_key,
            "pin"          : payload.pin,
            "source"       : payload.source,
            "confirmed_by" : payload.confirmed_by,
            "reasoning"    : payload.reasoning,
            "warnings"     : result.get("warnings", []),
        },
        backup_path = Path(result["backup_path"]) if result.get("backup_path") else None,
    )

    return {
        "phase"        : "committed",
        "status"       : result["status"],
        "control_key"  : result["control_key"],
        "pin"          : result["pin"],
        "confirmed_by" : result["confirmed_by"],
        "backup_path"  : result["backup_path"],
        "warnings"     : result.get("warnings", []),
        "reasoning"    : payload.reasoning,
    }


# ============================================================================
# Mapping CRUD Endpoints
# ============================================================================

@router.get("/mapping")
async def get_controller_mapping(request: Request):
    """Get current Mapping Dictionary with real-time USB detection

    Returns the current arcade controller mapping configuration
    including board info and pin assignments for all players.
    Also performs real-time USB detection to update board.detected status.
    """
    # Note: This is a read-only endpoint, no scope required
    try:
        drive_root = request.app.state.drive_root
        mapping_file, factory_file = _mapping_paths(drive_root)

        if not mapping_file.exists():
            logger.info("Controller mapping missing at %s; returning empty mapping payload", mapping_file)
            return {
                "mapping": {
                    "version": "1.0",
                    "board": {
                        "name": "No saved controller mapping",
                        "detected": False,
                        "status": "missing",
                    },
                    "mappings": {},
                },
                "file_path": "config/mappings/controls.json",
                "status": "missing",
                "message": (
                    "No saved controller mapping found yet. "
                    + (
                        "Chuck can preview and save from factory-default.json until controls.json exists."
                        if factory_file.exists()
                        else "Run Controller Chuck to create controls.json."
                    )
                ),
                "factory_defaults_available": factory_file.exists(),
                "seed_source": "config/mappings/factory-default.json" if factory_file.exists() else None,
            }

        with open(mapping_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Perform real-time USB detection for the configured board using detection service
        board_info = data.get("board", {})
        vid = board_info.get("vid")
        pid = board_info.get("pid")

        if vid and pid:
            try:
                # Use detection service for board detection
                detection_service = get_detection_service()
                board = detection_service.detect_board(vid, pid, use_cache=True)

                # Board is connected - update status with detection service data
                data["board"]["detected"] = board.detected
                data["board"]["status"] = board.status.value
                data["board"]["vendor"] = board.manufacturer
                if board.manufacturer:
                    data["board"]["manufacturer"] = board.manufacturer

                # Merge in detected strings if available
                if board.manufacturer_string:
                    data["board"]["manufacturer_string"] = board.manufacturer_string
                if board.product_string:
                    data["board"]["product_string"] = board.product_string

                if PactoTechBoard and PactoTechBoard.matches(vid, pid, board.name):
                    data["board"]["board_type"] = PactoTechBoard.BOARD_TYPE
                    modes = data["board"].setdefault("modes", {})
                    modes.setdefault("nine_panel", True)
                    modes.setdefault("macro", True)

                logger.info(f"Board {vid}:{pid} detected via detection service: {board.name}")

            except BoardNotFoundError:
                # Board not connected
                data["board"]["detected"] = False
                data["board"]["status"] = "disconnected"
                logger.debug(f"Board {vid}:{pid} not connected")

            except BoardDetectionError as e:
                # Detection failed (no backend, permissions, timeout, etc.)
                # Set detected to False but don't fail the request
                data["board"]["detected"] = False
                data["board"]["status"] = "error"
                data["board"]["detection_error"] = str(e)
                logger.warning(f"Board detection failed for {vid}:{pid}: {e}")
        else:
            # No VID/PID configured
            data["board"]["detected"] = False
            data["board"]["status"] = "disconnected"
            logger.debug("No VID/PID configured in board info")

        return {
            "mapping": data,
            "file_path": "config/mappings/controls.json",
            "status": "success"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read mapping: {str(e)}")

@router.post("/mapping/preview")
async def preview_controller_mapping(request: Request, update: MappingUpdate):
    """Preview controller mapping changes without writing

    Returns diff and validation results for proposed changes.
    """
    try:
        drive_root = request.app.state.drive_root
        mapping_file, _factory_file = _mapping_paths(drive_root)
        current_data, file_exists, seed_source = _load_mapping_seed(drive_root)
        current_content = (
            mapping_file.read_text(encoding="utf-8")
            if file_exists
            else json.dumps(current_data, indent=2)
        )

        # Merge with new mappings (deep merge for nested structures)
        new_data = json.loads(json.dumps(current_data))

        # Update specific mappings if provided
        if "mappings" in update.mappings:
            new_data["mappings"] = {**new_data.get("mappings", {}), **update.mappings["mappings"]}
        else:
            # Assume direct mapping updates
            new_data["mappings"] = {**new_data.get("mappings", {}), **update.mappings}

        # Update board info if provided
        if "board" in update.mappings:
            new_data["board"] = {**new_data.get("board", {}), **update.mappings["board"]}

        # Update metadata
        new_data["last_modified"] = datetime.now().isoformat()
        new_data["modified_by"] = request.headers.get('x-device-id', 'unknown')

        # Validate the new mapping
        validation = validate_mapping_structure(new_data)

        # Generate diff
        new_content = json.dumps(new_data, indent=2)
        diff = compute_diff(current_content, new_content, "controls.json")

        cascade_preview = None
        try:
            baseline_snapshot = load_controller_baseline(drive_root)
            current_mappings = current_data.get("mappings", {})
            new_mappings = new_data.get("mappings", {})
            changed_controls = []
            for control_key, control_value in new_mappings.items():
                if current_mappings.get(control_key) != control_value:
                    changed_controls.append(control_key)

            cascade_preview = {
                "needs_cascade": bool(changed_controls),
                "changed_controls": changed_controls,
                "baseline": {
                    "updated_at": baseline_snapshot.get("updated_at"),
                    "led": baseline_snapshot.get("led"),
                    "emulators": baseline_snapshot.get("emulators"),
                    "current_job": (baseline_snapshot.get("cascade") or {}).get("current_job"),
                },
            }
        except ControllerBaselineError as exc:
            logger.debug("Baseline unavailable during preview: %s", exc)

        return {
            "target_file": "config/mappings/controls.json",
            "has_changes": has_changes(current_content, new_content),
            "diff": diff,
            "validation": {
                "valid": validation.valid,
                "errors": validation.errors,
                "warnings": validation.warnings
            },
            "preview_mapping": new_data,
            "file_exists": file_exists,
            "seed_source": seed_source,
            "cascade_preview": cascade_preview,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")

@router.post("/mapping/apply")
async def apply_controller_mapping(
    request: Request,
    update: MappingUpdate,
    background_tasks: BackgroundTasks,
):
    """Apply controller mapping changes with backup

    Creates backup, validates, writes changes, and logs to changes.jsonl
    """
    try:
        # Validate scope header
        require_scope(request, "config")
        _ensure_writes_allowed(request)

        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        mapping_file, _factory_file = _mapping_paths(drive_root)

        # Validate path is in sanctioned areas
        if not is_allowed_file(mapping_file, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(
                status_code=403,
                detail=f"File not in sanctioned areas: {mapping_file}"
            )

        baseline_path = get_baseline_path(drive_root)
        if not is_allowed_file(baseline_path, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(
                status_code=403,
                detail=f"Baseline path not in sanctioned areas: {baseline_path}"
            )

        # Ensure directory exists
        mapping_file.parent.mkdir(parents=True, exist_ok=True)

        current_data, file_exists, seed_source = _load_mapping_seed(drive_root)
        current_content = (
            mapping_file.read_text(encoding="utf-8")
            if file_exists
            else json.dumps(current_data, indent=2)
        )

        # Merge with new mappings
        new_data = json.loads(json.dumps(current_data))

        if "mappings" in update.mappings:
            new_data["mappings"] = {**new_data.get("mappings", {}), **update.mappings["mappings"]}
        else:
            new_data["mappings"] = {**new_data.get("mappings", {}), **update.mappings}

        if "board" in update.mappings:
            new_data["board"] = {**new_data.get("board", {}), **update.mappings["board"]}

        current_mappings = current_data.get("mappings", {})
        new_mappings = new_data.get("mappings", {})
        changed_controls = [
            key for key, value in new_mappings.items() if current_mappings.get(key) != value
        ]

        # Update metadata
        new_data["last_modified"] = datetime.now().isoformat()
        new_data["modified_by"] = request.headers.get('x-device-id', 'unknown')

        # Validate before writing
        validation = validate_mapping_structure(new_data)
        if not validation.valid:
            raise HTTPException(
                status_code=400,
                detail=f"Validation failed: {', '.join(validation.errors)}"
            )

        new_content = json.dumps(new_data, indent=2)

        # Check if changes exist
        if not has_changes(current_content, new_content):
            return {
                "status": "no_changes",
                "target_file": "config/mappings/controls.json",
                "backup_path": None
            }

        # Create backup if file exists
        backup_path = None
        if mapping_file.exists() and request.app.state.backup_on_write:
            backup_path = create_backup(mapping_file, drive_root)

        # Write new content
        with open(mapping_file, 'w', encoding='utf-8') as f:
            f.write(new_content)

        # === MAME AUTO-REGENERATION ===
        # Keep MAME default.cfg in sync with controls.json
        mame_regen_result = _regenerate_mame_default_config(drive_root, new_data)

        # Log change
        await log_controller_change(
            request, drive_root, "mapping_apply",
            {
                "keys_updated": list(update.mappings.keys()),
                "validation": {"errors": validation.errors, "warnings": validation.warnings},
                "mame_regenerated": mame_regen_result.get("success", False),
            },
            backup_path
        )

        encoder_snapshot = build_encoder_snapshot(
            new_data,
            modified_by=request.headers.get('x-device-id', 'unknown')
        )

        try:
            baseline_after = update_controller_baseline(
                drive_root,
                {"encoder": encoder_snapshot},
                backup=request.app.state.backup_on_write,
            )
        except ControllerBaselineError as exc:
            logger.error("Failed to update controller baseline: %s", exc)
            raise HTTPException(
                status_code=500,
                detail=f"Baseline update failed: {exc}"
            )

        cascade_job = None
        cascade_preference = get_cascade_preference(drive_root)
        affected_emulators = sorted((baseline_after.get("emulators") or {}).keys())
        cascade_preview = {
            "needs_cascade": bool(changed_controls),
            "changed_controls": changed_controls,
            "affected_emulators": affected_emulators,
            "baseline": {
                "led": baseline_after.get("led"),
                "emulators": baseline_after.get("emulators"),
            },
            "preference": cascade_preference,
        }
        cascade_callout = None

        if changed_controls:
            metadata = {
                "source": "mapping_apply",
                "changed_controls": changed_controls,
            }
            if cascade_preference == "auto":
                cascade_job = _maybe_trigger_auto_cascade(
                    request,
                    background_tasks,
                    metadata=metadata,
                )
                if cascade_job:
                    cascade_preview["auto_triggered"] = True
                    cascade_preview["job_id"] = cascade_job["job_id"]
            elif cascade_preference == "ask":
                cascade_preview["prompt"] = True
                cascade_callout = "Cascade not applied — click Apply Cascade to push changes to emulators."
        elif cascade_preference == "ask":
            cascade_callout = "Cascade not applied — click Apply Cascade to push changes to emulators."

        response: Dict[str, Any] = {
            "status": "applied",
            "target_file": "config/mappings/controls.json",
            "backup_path": str(backup_path) if backup_path else None,
            "mapping": new_data,
            "changes_count": len(update.mappings),
            "file_exists_before_apply": file_exists,
            "seed_source": seed_source,
            "validation": {
                "warnings": validation.warnings
            },
            "baseline": {
                "encoder": baseline_after.get("encoder"),
                "updated_at": baseline_after.get("updated_at"),
            },
            "mame_config": mame_regen_result,
        }
        response["cascade_preview"] = cascade_preview
        if cascade_preview.get("prompt"):
            response["cascade_prompt"] = True
        if cascade_job:
            response["cascade_job"] = {
                "job_id": cascade_job["job_id"],
                "status": cascade_job.get("status"),
            }
        response["cascade_preference"] = cascade_preference
        if cascade_callout:
            response["cascade_callout"] = cascade_callout

        # Slice 3 C: Make autoconfig behavior explicit
        autoconfig_enabled = os.getenv("CONTROLLER_AUTOCONFIG_ENABLED", "false").lower() == "true"
        if not autoconfig_enabled:
            response["autoconfig_callout"] = (
                "Controller autoconfig mirroring is disabled. "
                "Set CONTROLLER_AUTOCONFIG_ENABLED=true to auto-mirror to emulators."
            )

        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Apply failed: {str(e)}")

@router.post("/mapping/reset")
async def reset_controller_mapping(request: Request):
    """Reset controller mapping to factory defaults

    Restores controls.json from factory-default.json (Greg's golden config)
    Creates backup of current config before reset.
    """
    try:
        # Validate scope header
        require_scope(request, "config")
        _ensure_writes_allowed(request)

        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        mapping_file = drive_root / "config" / "mappings" / "controls.json"
        factory_file = drive_root / "config" / "mappings" / "factory-default.json"

        # Validate factory file exists
        if not factory_file.exists():
            raise HTTPException(
                status_code=404,
                detail="Factory default file not found at config/mappings/factory-default.json"
            )

        # Validate paths are in sanctioned areas
        if not is_allowed_file(mapping_file, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(status_code=403, detail="Mapping file not in sanctioned areas")

        # Create backup of current config before reset
        backup_path = None
        if mapping_file.exists() and request.app.state.backup_on_write:
            backup_path = create_backup(mapping_file, drive_root)

        # Read factory defaults
        with open(factory_file, 'r', encoding='utf-8') as f:
            factory_data = json.load(f)

        # Update metadata
        factory_data["last_modified"] = datetime.now().isoformat()
        factory_data["modified_by"] = request.headers.get('x-device-id', 'unknown')

        # Write factory defaults to controls.json
        with open(mapping_file, 'w', encoding='utf-8') as f:
            json.dump(factory_data, f, indent=2)

        # === MAME AUTO-REGENERATION ===
        # Keep MAME default.cfg in sync with factory reset
        mame_regen_result = _regenerate_mame_default_config(drive_root, factory_data)

        # Log reset action
        await log_controller_change(
            request, drive_root, "mapping_reset",
            {
                "action": "factory_reset",
                "restored_from": "factory-default.json",
                "mame_regenerated": mame_regen_result.get("success", False),
            },
            backup_path
        )

        return {
            "status": "reset_complete",
            "target_file": "config/mappings/controls.json",
            "backup_path": str(backup_path) if backup_path else None,
            "restored_from": "config/mappings/factory-default.json",
            "mapping": factory_data,
            "mame_config": mame_regen_result,
            "chuck_prompt": "All mappings have been reset to factory defaults. MAME config regenerated. Ready to learn new controls!",
            "message": "Mappings reset to factory default. MAME config synced.",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")


# ============================================================================
# Golden Drive Reset
# ============================================================================

@router.post("/admin/golden-reset")
async def golden_drive_reset(request: Request, payload: GoldenResetRequest):
    """Master wipe for Golden Drive cloning preparation.

    Clears ALL cabinet and player state to prepare for drive cloning:
    - controls.json → Factory defaults
    - MAME default.cfg → Regenerated from factory
    - player_identity.json → Deleted
    - Player profiles/tendencies → Deleted
    - (Optional) MAME high scores → Deleted

    CAUTION: This is a destructive operation. Requires confirm=True.
    """
    try:
        # Validate scope header - require config access
        require_scope(request, "config")
        _ensure_writes_allowed(request)

        # Require explicit confirmation
        if not payload.confirm:
            raise HTTPException(
                status_code=400,
                detail="Golden Reset requires confirm=True. This will wipe ALL cabinet and player data."
            )

        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        results: Dict[str, Any] = {
            "status": "golden_reset_complete",
            "cleared": [],
            "errors": [],
        }

        # === 1. Reset controls.json to factory ===
        mapping_file = drive_root / "config" / "mappings" / "controls.json"
        factory_file = drive_root / "config" / "mappings" / "factory-default.json"

        try:
            if factory_file.exists():
                with open(factory_file, 'r', encoding='utf-8') as f:
                    factory_data = json.load(f)
                factory_data["last_modified"] = datetime.now().isoformat()
                factory_data["modified_by"] = "golden-reset"
                with open(mapping_file, 'w', encoding='utf-8') as f:
                    json.dump(factory_data, f, indent=2)
                results["cleared"].append("controls.json")

                # Regenerate MAME config from factory
                mame_result = _regenerate_mame_default_config(drive_root, factory_data)
                results["mame_config"] = mame_result
                if mame_result.get("success"):
                    results["cleared"].append("MAME default.cfg")
            else:
                results["errors"].append("factory-default.json not found")
        except Exception as exc:
            results["errors"].append(f"controls.json reset failed: {exc}")

        # === 2. Delete player_identity.json ===
        player_identity_file = drive_root / "state" / "controller" / "player_identity.json"
        try:
            if player_identity_file.exists():
                player_identity_file.unlink()
                results["cleared"].append("player_identity.json")
        except Exception as exc:
            results["errors"].append(f"player_identity.json delete failed: {exc}")

        # === 3. Delete all player profiles/tendencies ===
        profiles_dir = drive_root / ".aa" / "state" / "voice" / "profiles"
        profiles_cleared = 0
        try:
            if profiles_dir.exists():
                import shutil
                for profile_dir in profiles_dir.iterdir():
                    if profile_dir.is_dir():
                        shutil.rmtree(profile_dir)
                        profiles_cleared += 1
                results["cleared"].append(f"player_profiles ({profiles_cleared} profiles)")
        except Exception as exc:
            results["errors"].append(f"player_profiles delete failed: {exc}")

        # === 4. Optional: Clear MAME high scores ===
        if payload.clear_high_scores:
            hiscore_dir = drive_root / "Emulators" / "MAME" / "hi"
            hiscores_cleared = 0
            try:
                if hiscore_dir.exists():
                    for hi_file in hiscore_dir.glob("*.hi"):
                        hi_file.unlink()
                        hiscores_cleared += 1
                    results["cleared"].append(f"MAME high scores ({hiscores_cleared} files)")
            except Exception as exc:
                results["errors"].append(f"high scores delete failed: {exc}")

        # Log the action
        await log_controller_change(
            request, drive_root, "golden_reset",
            {
                "action": "golden_drive_reset",
                "cleared": results["cleared"],
                "errors": results["errors"],
                "clear_high_scores": payload.clear_high_scores,
            },
            None
        )

        logger.info("Golden Drive Reset completed: cleared=%s, errors=%s",
                   results["cleared"], results["errors"])

        results["chuck_prompt"] = (
            "Golden Drive Reset complete! Cabinet is now in factory state, "
            "ready for cloning. Run the Learn Wizard to configure new controls."
        )

        return results

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Golden reset failed: {str(e)}")


# ============================================================================
# Baseline & Cascade Endpoints
# ============================================================================

@router.get("/baseline")
async def get_controller_baseline_state(request: Request):
    """Return the persisted controller baseline state."""
    try:
        drive_root = request.app.state.drive_root
        baseline = load_controller_baseline(drive_root)
        return baseline
    except ControllerBaselineError as exc:
        logger.error("Failed to load controller baseline: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load controller baseline: {exc}"
        )


@router.get("/cascade/status")
async def get_controller_cascade_status(request: Request):
    """Return the current cascade job status with history."""
    try:
        drive_root = request.app.state.drive_root
        baseline = load_controller_baseline(drive_root)
        cascade_state = baseline.get("cascade", {})
        return {
            "status": cascade_state.get("status", "unknown"),
            "job": cascade_state.get("current_job"),
            "history": cascade_state.get("history", []),
            "updated_at": baseline.get("updated_at"),
        }
    except ControllerBaselineError as exc:
        logger.error("Failed to load cascade status: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load cascade status: {exc}"
        )


def _effective_paths_payload(drive_root: Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve effective emulator config targets and allow/deny status with reasons."""
    sanctioned = manifest.get("sanctioned_paths", [])
    emulators = ["retroarch", "mame", "dolphin", "ppsspp", "pcsx2"]
    payload: Dict[str, Any] = {}
    for emulator in emulators:
        hint = _default_config_hint_for_emulator(emulator)
        path = _resolve_config_path(drive_root, hint) if hint else None
        allowed = is_allowed_file(path, drive_root, sanctioned) if path else False

        entry = {
            "hint": str(hint) if hint else None,
            "resolved_path": str(path) if path else None,
            "allowed": allowed,
        }

        # Add reason when disallowed (Slice 3: make decisions legible)
        if not allowed:
            if not path:
                entry["reason"] = "No config path configured for this emulator"
            elif not sanctioned:
                entry["reason"] = "sanctioned_paths is empty in manifest"
            else:
                try:
                    path.relative_to(drive_root)
                    entry["reason"] = "Path not in sanctioned_paths"
                except ValueError:
                    entry["reason"] = "Path outside AA_DRIVE_ROOT"

        payload[emulator] = entry
    return payload


@router.get("/effective-paths")
async def effective_paths(request: Request):
    """Diagnostic: show resolved emulator config targets and access allowance."""
    drive_root = request.app.state.drive_root
    manifest = request.app.state.manifest
    autoconfig_enabled = os.getenv("CONTROLLER_AUTOCONFIG_ENABLED", "false").lower() == "true"
    writes_allowed = getattr(request.app.state, "writes_allowed", True)
    # If sanctioned_paths is empty, treat writes as disallowed even if other checks passed
    if not manifest.get("sanctioned_paths"):
        writes_allowed = False

    # LED baseline status (Slice 3 D: expose LED state for operators)
    led_status = None
    try:
        baseline = load_controller_baseline(drive_root)
        led_state = baseline.get("led") or {}
        led_status = {
            "status": led_state.get("status"),
            "message": led_state.get("message"),
            "last_synced": led_state.get("last_synced"),
        }
    except Exception:
        led_status = {"status": "unknown", "message": "Failed to load baseline"}

    return {
        "drive_root": str(drive_root),
        "sanctioned_paths": manifest.get("sanctioned_paths", []),
        "paths": _effective_paths_payload(drive_root, manifest),
        "autoconfig_enabled": autoconfig_enabled,
        "writes_allowed": writes_allowed,
        "write_block_reason": getattr(request.app.state, "write_block_reason", None),
        "led": led_status,
    }


@router.post("/cascade/preview")
async def preview_controller_cascade(
    request: Request,
    payload: CascadeApplyRequest,
):
    """Preview cascade queue inputs without mutating baseline or enqueuing jobs."""
    require_scope(request, "config")
    _ensure_writes_allowed(request)

    drive_root = request.app.state.drive_root
    baseline_snapshot = load_controller_baseline(drive_root)
    available_emulators = sorted((baseline_snapshot.get("emulators") or {}).keys())
    available_set = set(available_emulators)
    invalid_emulators = [
        emulator for emulator in payload.skip_emulators if emulator not in available_set
    ]
    if invalid_emulators:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown emulators in skip_emulators: {invalid_emulators}"
        )

    baseline_preview = baseline_snapshot
    if payload.baseline:
        baseline_preview = json.loads(json.dumps(baseline_snapshot))
        for key, value in payload.baseline.items():
            if isinstance(value, dict) and isinstance(baseline_preview.get(key), dict):
                baseline_preview[key].update(value)
            else:
                baseline_preview[key] = value

    return {
        "status": "preview",
        "dry_run": True,
        "skip_led": payload.skip_led,
        "skip_emulators": payload.skip_emulators,
        "metadata": payload.metadata,
        "available_emulators": available_emulators,
        "baseline": {
            "updated_at": baseline_preview.get("updated_at"),
            "cascade": baseline_preview.get("cascade"),
        },
    }


@router.post("/cascade/apply")
async def apply_controller_cascade(
    request: Request,
    payload: CascadeApplyRequest,
    background_tasks: BackgroundTasks,
):
    """Trigger the controller cascade orchestration (async)."""
    require_scope(request, "config")
    _ensure_writes_allowed(request)

    drive_root = request.app.state.drive_root
    manifest = request.app.state.manifest
    baseline_path = get_baseline_path(drive_root)
    backup_on_write = request.app.state.backup_on_write

    if not is_allowed_file(baseline_path, drive_root, manifest["sanctioned_paths"]):
        raise HTTPException(
            status_code=403,
            detail=f"Baseline path not in sanctioned areas: {baseline_path}"
        )

    try:
        baseline_snapshot = discover_and_expand_emulators(
            drive_root,
            manifest,
            backup=backup_on_write,
        )
    except ControllerBaselineError as exc:
        logger.error("Failed to expand emulator list: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to expand emulator list: {exc}",
        )

    available_emulators = sorted((baseline_snapshot.get("emulators") or {}).keys())
    available_set = set(available_emulators)
    invalid_emulators = [
        emulator for emulator in payload.skip_emulators if emulator not in available_set
    ]
    if invalid_emulators:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown emulators in skip_emulators: {invalid_emulators}"
        )

    if payload.baseline:
        try:
            update_controller_baseline(
                drive_root,
                payload.baseline,
                backup=backup_on_write,
            )
        except ControllerBaselineError as exc:
            logger.error("Failed to merge baseline update: %s", exc)
            raise HTTPException(
                status_code=400,
                detail=f"Failed to merge baseline update: {exc}"
            )

    try:
        job_record = enqueue_cascade_job(
            drive_root,
            requested_by=request.headers.get("x-device-id", "unknown"),
            metadata=payload.metadata,
            skip_led=payload.skip_led,
            skip_emulators=payload.skip_emulators,
            backup=backup_on_write,
            emulator_names=available_emulators,
        )
    except ControllerBaselineError as exc:
        logger.error("Failed to enqueue cascade job: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to enqueue cascade job: {exc}"
        )

    background_tasks.add_task(
        run_cascade_job,
        drive_root,
        manifest,
        job_record["job_id"],
        backup=backup_on_write,
    )

    audit_entry = {
        "job_id": job_record["job_id"],
        "requested_by": request.headers.get("x-device-id", "unknown"),
        "panel": request.headers.get("x-panel", "unknown"),
        "skip_led": payload.skip_led,
        "skip_emulators": payload.skip_emulators,
        "metadata": payload.metadata,
        "baseline_updated": bool(payload.baseline),
        "available_emulators": available_emulators,
    }

    audit_log.append(
        {
            "scope": "controller",
            "action": "controller_cascade_queued",
            **audit_entry,
        }
    )

    await log_controller_change(
        request,
        drive_root,
        "controller_cascade_queued",
        audit_entry,
    )

    try:
        baseline_after = load_controller_baseline(drive_root)
    except ControllerBaselineError as exc:
        logger.warning("Cascade job queued but baseline reload failed: %s", exc)
        baseline_payload = None
    else:
        baseline_payload = {
            "updated_at": baseline_after.get("updated_at"),
            "cascade": baseline_after.get("cascade"),
        }

    response: Dict[str, Any] = {
        "status": "queued",
        "job": job_record,
        "message": "Cascade job queued; status will update asynchronously.",
    }

    if baseline_payload is not None:
        response["baseline"] = baseline_payload

    return response


# ============================================================================
# MAME Config Generation Endpoints
# ============================================================================

@router.get("/mame-config/preview")
async def preview_mame_config(request: Request):
    """Preview MAME config generated from current Mapping Dictionary

    Generates MAME default.cfg XML from current control mappings
    without writing to disk. Returns XML content, validation results,
    and summary statistics.

    Returns:
        Preview with XML content, validation, and summary
    """
    try:
        drive_root = request.app.state.drive_root
        mapping_file = drive_root / "config" / "mappings" / "controls.json"

        if not mapping_file.exists():
            raise HTTPException(
                status_code=404,
                detail="Mapping file not found at config/mappings/controls.json"
            )

        # Read current mapping
        with open(mapping_file, 'r', encoding='utf-8') as f:
            mapping_data = json.load(f)

        # DEBUG: Log P2 mappings
        logger.info(f"🔍 P2.up mapping: {mapping_data['mappings'].get('p2.up', 'MISSING')}")
        logger.info(f"🔍 P2.button1 mapping: {mapping_data['mappings'].get('p2.button1', 'MISSING')}")

        # Generate MAME config XML
        xml_content = generate_mame_config(mapping_data)

        # Validate generated XML
        validation_errors = validate_mame_config(xml_content)

        # Get summary statistics
        summary = get_mame_config_summary(xml_content)

        return {
            "xml_content": xml_content,
            "validation": {
                "valid": len(validation_errors) == 0,
                "errors": validation_errors
            },
            "summary": summary,
            "source_mapping": "config/mappings/controls.json",
            "target_file": "config/mame/cfg/default.cfg"
        }

    except MAMEConfigError as e:
        raise HTTPException(
            status_code=400,
            detail=f"MAME config generation failed: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MAME config preview error: {e}")
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")


@router.post("/mame-config/apply")
async def apply_mame_config(request: Request):
    """Generate and write MAME config from current Mapping Dictionary

    Creates MAME default.cfg XML from current control mappings,
    validates it, and writes to config/mame/cfg/default.cfg with backup.

    Returns:
        Apply status with backup path and summary
    """
    try:
        # Validate scope header
        require_scope(request, "config")

        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        mapping_file = drive_root / "config" / "mappings" / "controls.json"
        # MAME config goes to the actual MAME installation folder
        mame_config_file = drive_root / "Emulators" / "MAME" / "cfg" / "default.cfg"

        # Validate paths are in sanctioned areas
        if not is_allowed_file(mame_config_file, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(
                status_code=403,
                detail=f"MAME config path not in sanctioned areas: {mame_config_file}"
            )

        # Read current mapping
        if not mapping_file.exists():
            raise HTTPException(
                status_code=404,
                detail="Mapping file not found at config/mappings/controls.json"
            )

        with open(mapping_file, 'r', encoding='utf-8') as f:
            mapping_data = json.load(f)

        # Generate MAME config XML
        xml_content = generate_mame_config(mapping_data)

        # Validate generated XML
        validation_errors = validate_mame_config(xml_content)
        if validation_errors:
            raise HTTPException(
                status_code=400,
                detail=f"Generated MAME config failed validation: {', '.join(validation_errors)}"
            )

        # Ensure directory exists
        mame_config_file.parent.mkdir(parents=True, exist_ok=True)

        # Create backup if file exists
        backup_path = None
        if mame_config_file.exists() and request.app.state.backup_on_write:
            backup_path = create_backup(mame_config_file, drive_root)

        # Write MAME config
        with open(mame_config_file, 'w', encoding='utf-8') as f:
            f.write(xml_content)

        # Get summary for response
        summary = get_mame_config_summary(xml_content)

        # Log the change
        await log_controller_change(
            request, drive_root, "mame_config_apply",
            {
                "action": "generate_mame_config",
                "port_count": summary["port_count"],
                "player_count": summary["player_count"],
                "source": "config/mappings/controls.json"
            },
            backup_path
        )

        return {
            "status": "applied",
            "target_file": "config/mame/cfg/default.cfg",
            "backup_path": str(backup_path) if backup_path else None,
            "summary": summary,
            "validation": {
                "valid": True,
                "errors": []
            }
        }

    except MAMEConfigError as e:
        raise HTTPException(
            status_code=400,
            detail=f"MAME config generation failed: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MAME config apply error: {e}")
        raise HTTPException(status_code=500, detail=f"Apply failed: {str(e)}")


@router.get("/mame-config/validate")
async def validate_existing_mame_config(request: Request):
    """Validate existing MAME config file

    Reads the existing config/mame/cfg/default.cfg file (if it exists)
    and validates it for well-formed XML and correctness.

    Returns:
        Validation results and summary
    """
    try:
        drive_root = request.app.state.drive_root
        mame_config_file = drive_root / "config" / "mame" / "cfg" / "default.cfg"

        if not mame_config_file.exists():
            return {
                "exists": False,
                "file_path": "config/mame/cfg/default.cfg",
                "validation": {
                    "valid": False,
                    "errors": ["File does not exist"]
                },
                "summary": None
            }

        # Read existing MAME config
        with open(mame_config_file, 'r', encoding='utf-8') as f:
            xml_content = f.read()

        # Validate
        validation_errors = validate_mame_config(xml_content)

        # Get summary
        summary = get_mame_config_summary(xml_content)

        return {
            "exists": True,
            "file_path": "config/mame/cfg/default.cfg",
            "validation": {
                "valid": len(validation_errors) == 0,
                "errors": validation_errors
            },
            "summary": summary
        }

    except Exception as e:
        logger.error(f"MAME config validation error: {e}")
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


# =============================================================================
# MAME Hot-Swap — Ephemeral Controller Config (Phase 3)
# =============================================================================


@router.post("/mame-config/hot-swap")
async def hot_swap_mame_config(request: Request):
    """Write ephemeral MAME controller config for live session.

    Generates live_session.cfg in MAME's ctrlr/ directory instead of
    overwriting default.cfg.  MAME reads it via -ctrlr live_session.

    Returns:
        Ephemeral config status with summary and MAME flag.
    """
    try:
        require_scope(request, "config")

        drive_root = request.app.state.drive_root
        mapping_file = drive_root / "config" / "mappings" / "controls.json"

        if not mapping_file.exists():
            raise HTTPException(
                status_code=404,
                detail="Mapping file not found at config/mappings/controls.json",
            )

        with open(mapping_file, "r", encoding="utf-8") as f:
            mapping_data = json.load(f)

        result = write_ephemeral_config(mapping_data, drive_root)

        # Log the change
        await log_controller_change(
            request, drive_root, "mame_hot_swap_write",
            {
                "action": "write_ephemeral_config",
                "profile": result["profile_name"],
                "port_count": result["summary"].get("port_count", 0),
                "player_count": result["summary"].get("player_count", 0),
                "source": "config/mappings/controls.json",
            },
        )

        return result

    except (MAMEConfigError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Hot-swap write error: {e}")
        raise HTTPException(status_code=500, detail=f"Hot-swap failed: {str(e)}")


@router.delete("/mame-config/hot-swap")
async def clear_hot_swap_config(request: Request):
    """Remove the ephemeral MAME controller config.

    Safe to call even if no ephemeral config exists.
    """
    try:
        require_scope(request, "config")
        drive_root = request.app.state.drive_root

        result = clear_ephemeral_config(drive_root)

        if result["was_active"]:
            await log_controller_change(
                request, drive_root, "mame_hot_swap_clear",
                {"action": "clear_ephemeral_config"},
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Hot-swap clear error: {e}")
        raise HTTPException(status_code=500, detail=f"Clear failed: {str(e)}")


@router.get("/mame-config/hot-swap/status")
async def hot_swap_status(request: Request):
    """Check if an ephemeral MAME config is active.

    Returns:
        Status with active flag, summary, and MAME launch flag.
    """
    try:
        drive_root = request.app.state.drive_root
        return get_ephemeral_status(drive_root)
    except Exception as e:
        logger.error(f"Hot-swap status error: {e}")
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")
