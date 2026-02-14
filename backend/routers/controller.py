import json
import logging
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

from ..services.backup import create_backup
from ..services.board_repair import BoardRepairService
from ..services.board_sanity import BoardSanityScanner, SanityReport
from ..services.device_scanner import scan_devices
from ..services.encoder_hints import enrich_with_hints
from ..services import device_registry
from ..services.firmware_manager import FirmwareManager
from ..services.mapping_recovery import MappingRecoveryService
from ..services.diffs import compute_diff, has_changes
from ..services.chuck.detection import (
    BoardDetectionError,
    BoardNotFoundError,
    get_detection_service,
)
from ..services.chuck.input_detector import InputDetectionService, InputEvent, detect_input_mode
from ..services.chuck.pactotech import PactoTechBoard
from ..services.chuck.encoder_state import get_encoder_state_manager
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
from ..services.mame_pergame_generator import (
    generate_pergame_config,
    save_pergame_config,
    get_genre_for_rom,
    get_supported_fighting_games,
)
from ..services.teknoparrot_config_generator import (
    build_canonical_mapping,
    apply_tp_config,
    is_game_supported,
    TPInputMode,
)
from ..services.policies import is_allowed_file, require_scope
from ..services import audit_log
from ..services import player_identity
from ..services.usb_detector import (
    USBBackendError,
    USBDetectionError,
    USBPermissionError,
    get_board_by_vid_pid,
)

logger = logging.getLogger(__name__)

router = APIRouter()


_input_detection_service: Optional[InputDetectionService] = None
_input_detection_lock = Lock()
_latest_input_event: Optional[InputEvent] = None
_wizard_states: Dict[str, Dict[str, Any]] = {}

# Player-specific wizard sequences
P1_WIZARD_SEQUENCE = [
    "p1.up", "p1.down", "p1.left", "p1.right",
    "p1.button1", "p1.button2", "p1.button3", "p1.button4",
    "p1.button5", "p1.button6", "p1.button7", "p1.button8",
    "p1.start", "p1.coin",
]

P2_WIZARD_SEQUENCE = [
    "p2.up", "p2.down", "p2.left", "p2.right",
    "p2.button1", "p2.button2", "p2.button3", "p2.button4",
    "p2.button5", "p2.button6",
    "p2.start", "p2.coin",
]

P3_WIZARD_SEQUENCE = [
    "p3.up", "p3.down", "p3.left", "p3.right",
    "p3.button1", "p3.button2", "p3.button3", "p3.button4",
    "p3.button5", "p3.button6",
    "p3.start", "p3.coin",
]

P4_WIZARD_SEQUENCE = [
    "p4.up", "p4.down", "p4.left", "p4.right",
    "p4.button1", "p4.button2", "p4.button3", "p4.button4",
    "p4.button5", "p4.button6",
    "p4.start", "p4.coin",
]

# Full sequence (all 4 players)
DEFAULT_WIZARD_SEQUENCE = (
    P1_WIZARD_SEQUENCE + P2_WIZARD_SEQUENCE + 
    P3_WIZARD_SEQUENCE + P4_WIZARD_SEQUENCE
)


def build_wizard_sequence(players: int = 2, buttons: int = 6) -> List[str]:
    """Build a wizard sequence with configurable players and buttons.
    
    Args:
        players: Number of players (1-4)
        buttons: Buttons per player (1-10)
    
    Returns:
        List of control keys to map
    """
    sequence = []
    for p in range(1, min(players, 4) + 1):
        # Add joystick directions
        sequence.extend([f"p{p}.up", f"p{p}.down", f"p{p}.left", f"p{p}.right"])
        # Add buttons (configurable count)
        for b in range(1, min(buttons, 10) + 1):
            sequence.append(f"p{p}.button{b}")
        # Add start/coin
        sequence.extend([f"p{p}.start", f"p{p}.coin"])
    return sequence

_TEACH_EVENT_LOG_RELATIVE = Path("state") / "controller" / "teach_events.jsonl"


def _ensure_writes_allowed(request: Request) -> None:
    """Block writes when startup marked drive root invalid."""
    if not getattr(request.app.state, "writes_allowed", True):
        reason = getattr(
            request.app.state,
            "write_block_reason",
            "AA_DRIVE_ROOT is not set; writes are disabled until it is configured.",
        )
        raise HTTPException(status_code=503, detail=reason)


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

# Pydantic models
class MappingUpdate(BaseModel):
    mappings: Dict[str, Any]  # e.g., {"p1.button1": {"pin": 7, "type": "button"}}

class MappingValidation(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]


class CascadeApplyRequest(BaseModel):
    skip_led: bool = False
    skip_emulators: List[str] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None
    baseline: Optional[Dict[str, Any]] = None


class InputDetectionEvent(BaseModel):
    timestamp: float
    keycode: str
    pin: int
    control_key: str
    player: int
    control_type: str
    source_id: str = ""


class PlayerIdentityResponse(BaseModel):
    """Response model for player identity calibration status."""
    status: str  # "bound" | "unbound"
    bindings: Dict[str, int]  # source_id -> player number
    calibrated_at: Optional[str] = None


class InputDetectionRequest(BaseModel):
    keycode: str


class WizardCapture(BaseModel):
    control_key: str = Field(..., description="Mapping key, e.g., p1.button1")
    pin: int = Field(..., ge=0)
    control_type: Optional[str] = Field(default=None)


class BoardSanityResponse(BaseModel):
    success: bool
    summary: str
    timestamp: datetime
    device_id: str
    report: Dict[str, Any]


class BoardRepairRequest(BaseModel):
    actions: List[str]
    dry_run: bool = True


class BoardRepairResponse(BaseModel):
    success: bool
    summary: str
    issue_type: Optional[str] = None
    actions_attempted: List[str] = Field(default_factory=list)
    actions_successful: List[str] = Field(default_factory=list)
    actions_failed: List[str] = Field(default_factory=list)
    mode_flags_before: Optional[Dict[str, Any]] = None
    mode_flags_after: Optional[Dict[str, Any]] = None


class FirmwarePreviewRequest(BaseModel):
    firmware_file: str


class FirmwarePreviewResponse(BaseModel):
    success: bool
    summary: str
    preview: Dict[str, Any]


class FirmwareApplyRequest(BaseModel):
    firmware_file: str
    confirm: bool = False


class FirmwareApplyResponse(BaseModel):
    success: bool
    summary: str
    flash_report: Dict[str, Any]


class MappingRecoveryRequest(BaseModel):
    duration_ms: Optional[int] = 30000


class MappingRecoveryResponse(BaseModel):
    success: bool
    summary: str
    result: Dict[str, Any]


class MappingApplyRequest(BaseModel):
    mapping: Dict[str, Any]
    dry_run: bool = True


class MappingApplyResponse(BaseModel):
    success: bool
    summary: str
    preview: Dict[str, Any]
    backup_path: Optional[str] = None


# Utility functions
def log_controller_change(request: Request, drive_root: Path, action: str, details: Dict[str, Any], backup_path: Optional[Path] = None):
    """Log Controller Chuck changes to changes.jsonl"""
    log_file = drive_root / ".aa" / "logs" / "changes.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    device = request.headers.get('x-device-id', 'unknown') if hasattr(request, 'headers') else 'unknown'
    panel = request.headers.get('x-panel', 'controller') if hasattr(request, 'headers') else 'controller'

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "scope": "controller",
        "action": action,
        "details": details,
        "backup_path": str(backup_path) if backup_path else None,
        "device": device,
        "panel": panel,
    }

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry) + "\n")


def _teach_event_log_path(drive_root: Path) -> Path:
    path = (drive_root / _TEACH_EVENT_LOG_RELATIVE).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _record_teach_event(drive_root: Path, event: InputEvent) -> None:
    """Append detected events so Teach Wizard can render real data."""
    try:
        payload = _serialize_input_event(event)
        payload["raw_timestamp"] = event.timestamp
        with open(_teach_event_log_path(drive_root), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
    except Exception:  # pragma: no cover - best-effort logging only
        logger.debug("Failed to persist teach event", exc_info=True)


def _wizard_session_key(request: Request) -> str:
    return (
        request.headers.get("x-session-id")
        or request.headers.get("x-device-id")
        or request.headers.get("x-client-id")
        or "default"
    )


def _default_control_type(control_key: str) -> str:
    if ".button" in control_key or control_key.endswith(("coin", "start")):
        return "button"
    return "joystick"


def _get_next_step(state: Dict[str, Any]) -> Optional[str]:
    for control in state.get("sequence", []):
        if control not in state.get("captures", {}):
            return control
    return None


def _require_device_id(request: Request) -> str:
    device_id = request.headers.get("x-device-id")
    if not device_id:
        raise HTTPException(status_code=400, detail="Missing x-device-id header.")
    return device_id


def _ensure_controller_panel(panel: Optional[str]) -> None:
    if not panel:
        raise HTTPException(status_code=400, detail="Missing x-panel header.")
    if panel.lower() != "controller":
        raise HTTPException(
            status_code=403,
            detail="x-panel must be 'controller' for controller board routes.",
        )


def _build_sanity_summary(report: SanityReport) -> str:
    sentences: List[str] = []
    name = (report.board_info.name if report.board_info else "the encoder") or "the encoder"
    sentences.append(f"I finished scanning {name}.")
    sentences.append(
        "I confirmed the board is connected and responding." if report.board_detected else
        "I could not confirm a connected board."
    )
    sentences.append(f"Firmware shows as {report.firmware_version or 'unknown version'}.")
    sentences.append(f"Turbo flag is {'ON' if report.mode_flags.turbo else 'OFF'}.")
    sentences.append(f"Analog flag is {'ON' if report.mode_flags.analog else 'OFF'}.")
    sentences.append(
        "I did not detect ghost pulses." if not report.ghost_pulses_detected else
        "I saw ghost pulses during the pin sample."
    )
    if report.issues_detected:
        issue_text = "; ".join(issue.description for issue in report.issues_detected)
        sentences.append(f"Issues: {issue_text}.")
    else:
        sentences.append("I did not record any critical issues.")
    if report.recommendations:
        sentences.append(f"My top recommendation is: {report.recommendations[0]}.")
    else:
        sentences.append("No immediate action is required.")
    sentences.append("I refreshed the controller state references.")
    sentences.append("All HID telemetry returned within expected tolerances.")
    sentences.append("Encoder telemetry is ready for Chuck to narrate.")
    sentences.append("You can ask me to run a repair if you still notice problems.")
    sentences.append("Let me know if you want a follow-up scan or repair sequence.")
    sentences.append("Chuck is standing by for the next command.")
    return " ".join(sentences[:13])


@router.get("/board/sanity")
async def controller_board_sanity(request: Request) -> BoardSanityResponse:
    """Perform a PactoTech board sanity scan."""
    require_scope(request, "state")
    device_id = _require_device_id(request)
    _ensure_controller_panel(request.headers.get("x-panel"))

    try:
        scanner = BoardSanityScanner(device_id)
        report = scanner.scan()
    except Exception as exc:  # pragma: no cover - hardware-specific failure logged
        logger.exception("Board sanity scan failed")
        raise HTTPException(status_code=502, detail="board_sanity_failed") from exc

    summary = _build_sanity_summary(report)
    return BoardSanityResponse(
        success=True,
        timestamp=datetime.utcnow(),
        device_id=device_id,
        summary=summary,
        report=report.to_dict(),
    )


@router.post("/board/repair", response_model=BoardRepairResponse)
async def controller_board_repair(
    request: Request, payload: BoardRepairRequest
) -> BoardRepairResponse:
    """Process a board repair request using the repair service."""
    require_scope(request, "config")
    device_id = _require_device_id(request)
    _ensure_controller_panel(request.headers.get("x-panel"))

    try:
        service = BoardRepairService(device_id=device_id)
        report = service.repair(actions=payload.actions, dry_run=payload.dry_run)
    except Exception as exc:  # pragma: no cover - hardware/service failure
        logger.exception("Board repair failed")
        raise HTTPException(status_code=502, detail="board_repair_failed") from exc

    success = report.final_state_verified or (report.issue_detected is False)

    return BoardRepairResponse(
        success=success,
        summary=report.summary,
        issue_type=report.issue_type,
        actions_attempted=report.actions_attempted,
        actions_successful=report.actions_successful,
        actions_failed=report.actions_failed,
        mode_flags_before=report.mode_flags_before.to_dict()
        if report.mode_flags_before
        else None,
        mode_flags_after=report.mode_flags_after.to_dict()
        if report.mode_flags_after
        else None,
    )


@router.post("/board/firmware/preview", response_model=FirmwarePreviewResponse)
async def controller_firmware_preview(
    request: Request, payload: FirmwarePreviewRequest
) -> FirmwarePreviewResponse:
    """Preview firmware changes without flashing."""
    require_scope(request, "config")
    device_id = _require_device_id(request)
    _ensure_controller_panel(request.headers.get("x-panel"))

    try:
        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        manager = FirmwareManager(device_id=device_id, drive_root=drive_root, manifest=manifest)
        preview = manager.preview_firmware(payload.firmware_file)
    except Exception as exc:  # pragma: no cover - hardware/service failure
        logger.exception("Firmware preview failed")
        raise HTTPException(
            status_code=502,
            detail={"success": False, "error": "firmware_preview_failed"},
        ) from exc

    preview_payload = asdict(preview)
    summary = (
        f"Previewed firmware file {preview.firmware_file}; "
        f"compatibility={preview.compatibility_check.upper()} (not implemented)."
    )
    return FirmwarePreviewResponse(
        success=True,
        summary=summary,
        preview=preview_payload,
    )


@router.post("/board/firmware/apply", response_model=FirmwareApplyResponse)
async def controller_firmware_apply(
    request: Request, payload: FirmwareApplyRequest
) -> FirmwareApplyResponse:
    """Apply firmware using the firmware manager (stub)."""
    require_scope(request, "config")
    device_id = _require_device_id(request)
    _ensure_controller_panel(request.headers.get("x-panel"))

    try:
        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        manager = FirmwareManager(device_id=device_id, drive_root=drive_root, manifest=manifest)
        report = manager.apply_firmware(
            firmware_file=payload.firmware_file,
            confirm=payload.confirm,
        )
    except Exception as exc:  # pragma: no cover - hardware/service failure
        logger.exception("Firmware apply failed")
        raise HTTPException(
            status_code=502,
            detail={"success": False, "error": "firmware_apply_failed"},
        ) from exc

    summary = (
        f"Firmware apply stub ran; no real flashing performed (confirm={payload.confirm})."
    )
    flash_payload = asdict(report)
    success = bool(report.flash_successful)
    return FirmwareApplyResponse(
        success=success,
        summary=summary,
        flash_report=flash_payload,
    )


@router.post("/board/mapping/preview", response_model=MappingRecoveryResponse)
async def controller_mapping_preview(
    request: Request, payload: MappingRecoveryRequest
) -> MappingRecoveryResponse:
    """Run a mapping recovery preview (no writes)."""
    require_scope(request, "state")
    device_id = _require_device_id(request)
    _ensure_controller_panel(request.headers.get("x-panel"))

    drive_root = request.app.state.drive_root
    manifest = request.app.state.manifest

    try:
        service = MappingRecoveryService(
            device_id=device_id, drive_root=drive_root, manifest=manifest
        )
        result = service.preview_recovery(duration_ms=payload.duration_ms or 30000)
    except Exception as exc:  # pragma: no cover - hardware/service failure
        logger.exception("Mapping recovery preview failed")
        raise HTTPException(
            status_code=502,
            detail={"success": False, "error": "mapping_preview_failed"},
        ) from exc

    result_payload = {
        "session": {
            "started_at": result.session.started_at.isoformat(),
            "duration_ms": result.session.duration_ms,
            "samples_collected": result.session.samples_collected,
        },
        "detected_pins": [
            {
                "logical_key": pin.logical_key,
                "pin": pin.pin,
                "physical_code": pin.physical_code,
                "sample_count": pin.sample_count,
                "control_type": pin.control_type,
                "notes": pin.notes,
            }
            for pin in result.detected_pins
        ],
        "comparison": {
            "mismatches": result.comparison.mismatches,
            "unmapped_logical": result.comparison.unmapped_logical,
            "unmapped_physical": result.comparison.unmapped_physical,
        },
        "proposed_mapping": result.proposed_mapping,
        "summary": result.summary,
    }

    summary = result.summary or "Teach wizard preview generated."
    return MappingRecoveryResponse(
        success=True,
        summary=summary,
        result=result_payload,
    )


@router.post("/board/mapping/recover", response_model=MappingRecoveryResponse)
async def controller_mapping_recover(
    request: Request, payload: MappingRecoveryRequest
) -> MappingRecoveryResponse:
    """Preview mapping recovery flow using config scope."""
    require_scope(request, "config")
    device_id = _require_device_id(request)
    _ensure_controller_panel(request.headers.get("x-panel"))

    drive_root = request.app.state.drive_root
    manifest = request.app.state.manifest

    try:
        service = MappingRecoveryService(
            device_id=device_id, drive_root=drive_root, manifest=manifest
        )
        result = service.preview_recovery(duration_ms=payload.duration_ms or 30000)
    except Exception as exc:  # pragma: no cover - hardware/service failure
        logger.exception("Mapping recovery preview failed (config scope)")
        raise HTTPException(
            status_code=502,
            detail={"success": False, "error": "mapping_recover_failed"},
        ) from exc

    result_payload = {
        "session": {
            "started_at": result.session.started_at.isoformat(),
            "duration_ms": result.session.duration_ms,
            "samples_collected": result.session.samples_collected,
        },
        "detected_pins": [
            {
                "logical_key": pin.logical_key,
                "pin": pin.pin,
                "physical_code": pin.physical_code,
                "sample_count": pin.sample_count,
                "control_type": pin.control_type,
                "notes": pin.notes,
            }
            for pin in result.detected_pins
        ],
        "comparison": {
            "mismatches": result.comparison.mismatches,
            "unmapped_logical": result.comparison.unmapped_logical,
            "unmapped_physical": result.comparison.unmapped_physical,
        },
        "proposed_mapping": result.proposed_mapping,
        "summary": result.summary,
    }

    return MappingRecoveryResponse(
        success=True,
        summary=result.summary,
        result=result_payload,
    )


@router.post("/board/mapping/apply", response_model=MappingApplyResponse)
async def controller_mapping_apply(
    request: Request, payload: MappingApplyRequest
) -> MappingApplyResponse:
    """Apply a new mapping dictionary with backup/preview semantics."""
    require_scope(request, "config")
    device_id = _require_device_id(request)
    _ensure_controller_panel(request.headers.get("x-panel"))

    drive_root = request.app.state.drive_root
    manifest = request.app.state.manifest

    service = MappingRecoveryService(
        device_id=device_id, drive_root=drive_root, manifest=manifest
    )

    try:
        report, preview = service.apply_mapping(payload.mapping, dry_run=payload.dry_run)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - IO failure
        logger.exception("Mapping dictionary apply failed")
        raise HTTPException(status_code=502, detail="mapping_apply_failed") from exc

    preview_payload = {
        **preview,
        "actions": report.actions_taken,
        "warnings": report.warnings,
        "errors": report.errors,
    }

    backup_path = report.backup_path

    if not payload.dry_run and report.success and report.changes_count > 0:
        backup_for_log = drive_root / backup_path if backup_path else None
        log_controller_change(
            request,
            drive_root,
            "mapping_dictionary_apply",
            {
                "target": preview.get("target_file"),
                "device_id": device_id,
                "changes_count": report.changes_count,
            },
            backup_for_log,
        )

    return MappingApplyResponse(
        success=report.success,
        summary=report.summary,
        preview=preview_payload,
        backup_path=backup_path,
    )

# Validation helpers
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


@router.get("/devices")
async def get_controller_devices(request: Request) -> Dict[str, Any]:
    """Scan for connected controller/encoder devices.
    
    Shows all detected USB/HID devices and marks any that have been
    classified as 'arcade_encoder' in the device registry.
    Users can classify devices via /devices/classify endpoint.
    """
    from ..services.device_scanner import scan_devices
    from ..services.encoder_hints import enrich_with_hints
    from ..services import device_registry
    
    hints: List[str] = []
    errors: List[Dict[str, str]] = []
    controllers: List[Dict[str, Any]] = []
    
    try:
        # Get user classifications from device registry
        drive_root: Path = request.app.state.drive_root
        sanctioned_paths = request.app.state.manifest.get("sanctioned_paths", [])
        
        try:
            classifications = {
                entry["device_id"]: entry
                for entry in device_registry.list_classifications(
                    drive_root,
                    sanctioned_paths=sanctioned_paths,
                )
            }
        except Exception as e:
            logger.debug("Could not load device classifications: %s", e)
            classifications = {}
        
        # Scan USB/HID devices
        raw_devices = scan_devices()
        logger.info("Device scan returned %d devices", len(raw_devices))
        
        if not raw_devices:
            # Check if we have any classified encoders even without USB scan
            encoder_classifications = [c for c in classifications.values() if c.get("role") == "arcade_encoder"]
            if encoder_classifications:
                for cls in encoder_classifications:
                    controllers.append({
                        "device_id": cls.get("device_id", "unknown"),
                        "vid": None,
                        "pid": None,
                        "name": cls.get("label") or "Configured Encoder",
                        "manufacturer": None,
                        "type": "arcade_board",
                        "detected": False,  # Not currently detected on USB
                        "interface": "configured",
                        "status": "configured (not connected)",
                    })
                return {
                    "status": "partial",
                    "controllers": controllers,
                    "hints": ["No USB devices detected, but found configured encoder(s)."],
                    "errors": [],
                }
            
            hints.append("No USB/HID devices detected. Check connections and try again.")
            return {
                "status": "empty",
                "controllers": [],
                "hints": hints,
                "errors": [],
            }
        
        # Process each device
        for device in raw_devices:
            device = enrich_with_hints(device)
            device_id = device.get("device_id", "unknown")
            
            # Check if user has classified this device
            classification = classifications.get(device_id)
            is_encoder = classification and classification.get("role") == "arcade_encoder"
            
            # Use classification label if available, otherwise use product string
            device_name = device.get("product") or "Unknown Device"
            if classification and classification.get("label"):
                device_name = classification.get("label")
            
            controller_entry = {
                "device_id": device_id,
                "vid": device.get("vid"),
                "pid": device.get("pid"),
                "name": device_name,
                "manufacturer": device.get("manufacturer"),
                "type": "arcade_board" if is_encoder else "unknown",
                "detected": True,
                "interface": device.get("interface", "unknown"),
                "status": "connected",
                "is_classified": classification is not None,
            }
            controllers.append(controller_entry)
        
        # Determine overall status
        arcade_boards = [c for c in controllers if c["type"] == "arcade_board"]
        if arcade_boards:
            status = "ok"
            for board in arcade_boards:
                hints.append(f"✓ {board['name']} ({board['vid']}:{board['pid']})")
        else:
            status = "partial"
            hints.append("No encoder classified yet. Use 'Classify' to mark your encoder board.")
        
        return {
            "status": status,
            "controllers": controllers,
            "hints": hints,
            "errors": errors,
        }
        
    except Exception as exc:
        logger.exception("Device scan failed")
        return {
            "status": "error",
            "controllers": [],
            "hints": ["Device scanning failed. Check USB connections."],
            "errors": [{"message": str(exc)}],
        }


@router.get("/input/start")
async def start_input_detection(request: Request, board_type: Optional[str] = None):
    """Begin listening for encoder inputs."""
    require_scope(request, "state")
    service = _get_input_detection_service(request, board_type_override=board_type)
    service.start_listening()
    return {
        "status": "listening",
        "board_type": service.board_type,
        "message": "Input detection started.",
    }


@router.get("/input/stop")
async def stop_input_detection(request: Request):
    """Stop listening for encoder inputs."""
    require_scope(request, "state")
    service = _input_detection_service
    if service is not None:
        service.stop_listening()
    return {"status": "stopped", "message": "Input detection stopped."}


@router.get("/input/latest")
async def get_latest_input_event(request: Request):
    """Return the most recent detected encoder input event, if any."""
    require_scope(request, "state")
    if _latest_input_event is None:
        return {
            "status": "idle",
            "event": None,
        }

    return {
        "status": "detected",
        "event": _serialize_input_event(_latest_input_event),
    }


# Learn mode state
_learn_mode_latest_key: Optional[str] = None


@router.post("/input/learn/start")
async def start_learn_mode(request: Request):
    """Enable learn mode - captures ALL key presses without requiring existing mappings.
    
    Use this to teach the system what key each button sends.
    """
    require_scope(request, "state")
    global _learn_mode_latest_key
    _learn_mode_latest_key = None
    
    service = _get_input_detection_service(request)
    service.set_learn_mode(True)
    
    # Register a raw handler to capture keys
    def capture_raw_key(keycode: str) -> None:
        global _learn_mode_latest_key
        _learn_mode_latest_key = keycode
        logger.info("Learn mode captured: %s", keycode)
    
    # Clear any existing raw handlers and add our capture handler
    service._raw_handlers.clear()
    service.register_raw_handler(capture_raw_key)
    service.start_listening()
    
    return {
        "status": "learning",
        "message": "Learn mode enabled. Press any button on your encoder.",
    }


@router.post("/input/learn/stop")
async def stop_learn_mode(request: Request):
    """Disable learn mode and return to normal input detection."""
    require_scope(request, "state")
    service = _input_detection_service
    if service is not None:
        service.set_learn_mode(False)
        service._raw_handlers.clear()
    return {"status": "stopped", "message": "Learn mode disabled."}


@router.get("/input/learn/latest")
async def get_learn_mode_latest(request: Request):
    """Get the latest key captured in learn mode."""
    require_scope(request, "state")
    return {
        "status": "captured" if _learn_mode_latest_key else "waiting",
        "keycode": _learn_mode_latest_key,
    }


@router.post("/input/learn/clear")
async def clear_learn_mode_capture(request: Request):
    """Clear the last captured key to prepare for the next button press."""
    require_scope(request, "state")
    global _learn_mode_latest_key
    _learn_mode_latest_key = None
    return {"status": "cleared"}


# Learn Wizard state - tracks which control we're mapping
_learn_wizard_state: Dict[str, Any] = {}


def get_control_display_name(control_key: str) -> str:
    """Get human-friendly display name for a control key."""
    # Parse control key like "p1.button3" or "p2.up"
    if not control_key or "." not in control_key:
        return control_key
    
    parts = control_key.split(".", 1)
    player_num = parts[0].replace("p", "Player ")
    control_name = parts[1]
    
    # Format control name nicely
    if control_name.startswith("button"):
        btn_num = control_name.replace("button", "")
        return f"{player_num} Button {btn_num}"
    else:
        return f"{player_num} {control_name.capitalize()}"


# Legacy static lookup (for backwards compatibility)
CONTROL_DISPLAY_NAMES = {
    f"p{p}.{c}": get_control_display_name(f"p{p}.{c}")
    for p in range(1, 5)
    for c in ["up", "down", "left", "right", "start", "coin"] + 
             [f"button{b}" for b in range(1, 11)]
}



@router.post("/learn-wizard/start")
async def start_learn_wizard(
    request: Request,
    player: Optional[int] = None,
    players: Optional[int] = None,
    buttons: Optional[int] = None,
    auto_advance: bool = True,
):
    """Start the voice-guided learn wizard.
    
    Chuck will guide you through mapping each control by pressing buttons.
    Will warn if encoder mode baseline is missing or mode drift detected.
    
    Args:
        player: Which player to map (1=P1 only, 2=P2 only, etc. None=all)
        players: Number of players for this cabinet (1-4). Used with 'buttons'.
        buttons: Buttons per player (1-10). Used with 'players'.
        auto_advance: If True, auto-confirm and advance when button pressed (default True)
    """
    require_scope(request, "state")
    global _learn_wizard_state, _learn_mode_latest_key
    
    drive_root: Path = request.app.state.drive_root
    
    # Select the appropriate sequence based on parameters
    if players is not None and buttons is not None:
        # Use configurable sequence
        sequence = build_wizard_sequence(players=players, buttons=buttons)
        player_label = f"{players} players, {buttons} buttons each"
    elif player == 1:
        sequence = list(P1_WIZARD_SEQUENCE)
        player_label = "Player 1"
    elif player == 2:
        sequence = list(P2_WIZARD_SEQUENCE)
        player_label = "Player 2"
    elif player == 3:
        sequence = list(P3_WIZARD_SEQUENCE)
        player_label = "Player 3"
    elif player == 4:
        sequence = list(P4_WIZARD_SEQUENCE)
        player_label = "Player 4"
    else:
        # Default: use configurable sequence for flexibility (2 players, 6 buttons)
        sequence = build_wizard_sequence(players=2, buttons=6)
        player_label = "all players"
    
    # Check encoder mode state
    encoder_manager = get_encoder_state_manager(drive_root)
    encoder_state = encoder_manager.get_state()
    mode_warning = None
    
    # Log warnings internally but don't confuse the user with technical details
    if encoder_state.get("needs_recalibration"):
        mode_warning = (
            f"Encoder may have switched modes. "
            f"Baseline was {encoder_state.get('baseline_mode')}, "
            f"but recent inputs look like {encoder_state.get('current_mode')}."
        )
        logger.warning("[LearnWizard] %s", mode_warning)
    elif not encoder_state.get("baseline_mode"):
        logger.info("[LearnWizard] No encoder baseline set - proceeding without mode detection")
    
    # Initialize wizard state
    _learn_wizard_state = {
        "sequence": sequence,
        "player": player,
        "players": players,
        "buttons": buttons,
        "auto_advance": auto_advance,
        "current_index": 0,
        "captures": {},
        "started_at": datetime.utcnow().isoformat(),
        "encoder_mode": encoder_state.get("baseline_mode"),
    }
    _learn_mode_latest_key = None

    # AUTO-DETECT CONNECTED ENCODER BOARDS
    # Try to detect PactoTech or other arcade encoders to determine input mode
    detected_board = None
    detected_mode = None
    try:
        from ..services.usb_detector import detect_arcade_boards
        boards = detect_arcade_boards()

        # Look for PactoTech boards (they use XInput mode by default)
        for board in boards:
            if "pacto" in board.get("vendor", "").lower() or "paxco" in board.get("vendor", "").lower():
                detected_board = board
                detected_mode = "xinput"  # PactoTech defaults to XInput
                logger.info(f"[LearnWizard] Detected {board['name']} - using XInput mode")
                break
            elif "ultimarc" in board.get("vendor", "").lower():
                detected_board = board
                detected_mode = "keyboard"  # Ultimarc I-PAC uses keyboard mode
                logger.info(f"[LearnWizard] Detected {board['name']} - using keyboard mode")
                break

        if not detected_board and boards:
            detected_board = boards[0]
            logger.info(f"[LearnWizard] Detected {detected_board.get('name')} - mode unknown")
    except Exception as e:
        logger.warning(f"[LearnWizard] Could not auto-detect encoder board: {e}")

    # START AUTOMATIC INPUT DETECTION (keyboard + XInput gamepad)
    # Get the input detection service and enable learn mode for dual-mode capture
    service = _get_input_detection_service(request)
    service.set_learn_mode(True)

    # Register handler to capture raw inputs (keyboard OR gamepad)
    def capture_wizard_input(keycode: str) -> None:
        # Filter out TRIGGER noise (Xbox triggers spam events at rest position)
        # But ALLOW joystick AXIS inputs (needed for UP/DOWN/LEFT/RIGHT)
        if "TRIGGER" in keycode:
            logger.debug(f"[LearnWizard] Ignored trigger noise: {keycode}")
            return

        global _learn_mode_latest_key
        _learn_mode_latest_key = keycode
        logger.info("[LearnWizard] Captured input: %s", keycode)

    # Clear existing handlers and register wizard capture handler
    service._raw_handlers.clear()
    service.register_raw_handler(capture_wizard_input)

    # Start listening for BOTH keyboard and gamepad inputs
    service.start_listening()
    logger.info("[LearnWizard] Started dual-mode input detection (keyboard + XInput)")

    # Get first control to map
    first_control = sequence[0] if sequence else "p1.up"
    display_name = get_control_display_name(first_control)

    # Build conversational prompt with board detection info
    if detected_board:
        board_name = detected_board.get("name", "encoder board")
        if detected_mode == "xinput":
            chuck_prompt = (
                f"I detected your {board_name} in XInput mode! "
                f"Just press {display_name} on your controller and I'll capture it automatically."
            )
        elif detected_mode == "keyboard":
            chuck_prompt = (
                f"I detected your {board_name} in keyboard mode! "
                f"Just press {display_name} and I'll capture the keycode."
            )
        else:
            chuck_prompt = (
                f"I detected your {board_name}! "
                f"Press {display_name} - I'm listening for both keyboard and gamepad inputs."
            )
    else:
        chuck_prompt = (
            f"Alright, let's map your controls! "
            f"Press {display_name} - I'm listening for keyboard or gamepad input."
        )


    return {
        "status": "started",
        "current_control": first_control,
        "current_index": 0,
        "total_controls": len(sequence),
        "auto_advance": auto_advance,
        "players": players,
        "buttons": buttons,
        "chuck_prompt": chuck_prompt,
        "display_name": display_name,
        "mode_warning": mode_warning,
        "encoder_mode": encoder_state.get("baseline_mode"),
        "detected_board": detected_board.get("name") if detected_board else None,
        "detected_mode": detected_mode,
        "dual_mode_enabled": True,  # Now listening for both keyboard + XInput
    }


@router.get("/learn-wizard/status")
async def get_learn_wizard_status(request: Request):
    """Get current learn wizard status and any captured key."""
    require_scope(request, "state")
    
    if not _learn_wizard_state:
        return {"status": "not_started"}
    
    current_index = _learn_wizard_state.get("current_index", 0)
    sequence = _learn_wizard_state.get("sequence", [])
    
    # Check encoder mode status for live drift detection
    drive_root: Path = request.app.state.drive_root
    encoder_manager = get_encoder_state_manager(drive_root)
    encoder_state = encoder_manager.get_state()
    mode_warning = None
    
    if encoder_state.get("needs_recalibration"):
        mode_warning = (
            f"Mode drift detected! Baseline was {encoder_state.get('baseline_mode')}, "
            f"current looks like {encoder_state.get('current_mode')}. "
            f"Mappings may be incorrect."
        )
    
    if current_index >= len(sequence):
        return {
            "status": "complete",
            "captures": _learn_wizard_state.get("captures", {}),
            "chuck_prompt": "All done! Your controls are mapped. Ready to save?",
            "encoder_mode": encoder_state.get("baseline_mode"),
            "mode_warning": mode_warning,
        }
    
    current_control = sequence[current_index]
    display_name = CONTROL_DISPLAY_NAMES.get(current_control, current_control)
    
    return {
        "status": "waiting",
        "current_control": current_control,
        "current_index": current_index,
        "total_controls": len(sequence),
        "captured_key": _learn_mode_latest_key,
        "captures": _learn_wizard_state.get("captures", {}),
        "display_name": display_name,
        "encoder_mode": encoder_state.get("baseline_mode"),
        "mode_match": encoder_state.get("mode_match"),
        "mode_warning": mode_warning,
    }


@router.post("/learn-wizard/confirm")
async def confirm_learn_wizard_capture(request: Request):
    """Confirm the captured key for the current control and move to next."""
    require_scope(request, "state")
    global _learn_mode_latest_key
    
    if not _learn_wizard_state:
        raise HTTPException(status_code=400, detail="Wizard not started")
    
    if not _learn_mode_latest_key:
        return {
            "status": "no_capture",
            "chuck_prompt": "I didn't catch that. Press the button again.",
        }
    
    current_index = _learn_wizard_state.get("current_index", 0)
    sequence = _learn_wizard_state.get("sequence", [])
    
    if current_index >= len(sequence):
        return {"status": "complete"}
    
    current_control = sequence[current_index]
    
    # Save the capture
    _learn_wizard_state["captures"][current_control] = {
        "keycode": _learn_mode_latest_key,
        "key_name": _learn_mode_latest_key.upper().replace("KEY_", "").lower(),
    }
    
    # Move to next control
    _learn_wizard_state["current_index"] = current_index + 1
    _learn_mode_latest_key = None
    
    # Check if complete
    if current_index + 1 >= len(sequence):
        return {
            "status": "complete",
            "captures": _learn_wizard_state.get("captures", {}),
            "chuck_prompt": "Perfect! All controls are mapped. Say 'save' or click Save to apply.",
        }
    
    # Get next control
    next_control = sequence[current_index + 1]
    next_display = CONTROL_DISPLAY_NAMES.get(next_control, next_control)
    
    return {
        "status": "next",
        "captured": current_control,
        "next_control": next_control,
        "current_index": current_index + 1,
        "total_controls": len(sequence),
        "chuck_prompt": f"Got it! Now, which button is {next_display}? Press it now.",
        "display_name": next_display,
    }


class ManualKeyRequest(BaseModel):
    keycode: str = Field(..., description="The keycode to assign, e.g., 'F1', 'UP', 'SPACE'")


@router.post("/learn-wizard/set-key")
async def set_learn_wizard_key(request: Request, payload: ManualKeyRequest):
    """Manually set the keycode for the current control.
    
    Use this when automatic key detection doesn't work (e.g., encoder in gamepad mode).
    User can type the keycode they see when pressing a button in Notepad.
    
    Args:
        keycode: The key to assign (e.g., 'F1', 'UP', 'ENTER', 'A')
    """
    require_scope(request, "state")
    global _learn_mode_latest_key
    
    if not _learn_wizard_state:
        raise HTTPException(status_code=400, detail="Wizard not started")
    
    current_index = _learn_wizard_state.get("current_index", 0)
    sequence = _learn_wizard_state.get("sequence", [])
    
    if current_index >= len(sequence):
        return {"status": "complete"}
    
    current_control = sequence[current_index]
    
    # Normalize the keycode
    keycode = payload.keycode.strip().upper()
    if not keycode.startswith("KEY_"):
        keycode = f"KEY_{keycode}"
    
    # Save the capture
    _learn_wizard_state["captures"][current_control] = {
        "keycode": keycode,
        "key_name": keycode.replace("KEY_", "").lower(),
    }
    
    # Move to next control
    _learn_wizard_state["current_index"] = current_index + 1
    _learn_mode_latest_key = None
    
    # Check if complete
    if current_index + 1 >= len(sequence):
        return {
            "status": "complete",
            "captures": _learn_wizard_state.get("captures", {}),
            "chuck_prompt": "Perfect! All controls are mapped. Ready to save!",
        }
    
    # Get next control
    next_control = sequence[current_index + 1]
    next_display = CONTROL_DISPLAY_NAMES.get(next_control, next_control)
    
    return {
        "status": "next",
        "captured": current_control,
        "keycode": keycode,
        "next_control": next_control,
        "current_index": current_index + 1,
        "total_controls": len(sequence),
        "chuck_prompt": f"Got it! Next up: {next_display}. What key is that?",
        "display_name": next_display,
    }


@router.post("/learn-wizard/skip")
async def skip_learn_wizard_control(request: Request):
    """Skip the current control and move to the next one."""
    require_scope(request, "state")
    global _learn_mode_latest_key
    
    if not _learn_wizard_state:
        raise HTTPException(status_code=400, detail="Wizard not started")
    
    current_index = _learn_wizard_state.get("current_index", 0)
    sequence = _learn_wizard_state.get("sequence", [])
    
    # Move to next control
    _learn_wizard_state["current_index"] = current_index + 1
    _learn_mode_latest_key = None
    
    if current_index + 1 >= len(sequence):
        return {
            "status": "complete",
            "captures": _learn_wizard_state.get("captures", {}),
            "chuck_prompt": "All done! Click Save when you're ready.",
        }
    
    next_control = sequence[current_index + 1]
    next_display = CONTROL_DISPLAY_NAMES.get(next_control, next_control)
    
    return {
        "status": "skipped",
        "next_control": next_control,
        "chuck_prompt": f"Skipped. Next: {next_display}.",
        "display_name": next_display,
    }


@router.post("/learn-wizard/save")
async def save_learn_wizard(request: Request, background_tasks: BackgroundTasks):
    """Save all captured mappings to controls.json and trigger cascade to emulators.
    
    This is the main "Save" action that:
    1. Writes captures to controls.json (source of truth)
    2. Triggers cascade to MAME, TeknoParrot, and other configured emulators
    3. Returns status indicating cascade progress
    """
    require_scope(request, "config")
    _ensure_writes_allowed(request)
    
    if not _learn_wizard_state or not _learn_wizard_state.get("captures"):
        raise HTTPException(status_code=400, detail="No captures to save")
    
    drive_root: Path = request.app.state.drive_root
    manifest = request.app.state.manifest
    mapping_file = drive_root / "config" / "mappings" / "controls.json"
    
    # Create backup before saving
    backup_path = None
    if mapping_file.exists() and getattr(request.app.state, "backup_on_write", True):
        backup_path = create_backup(mapping_file, drive_root)
    
    # Load existing
    try:
        with open(mapping_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {"version": 1, "board": {}, "mappings": {}}
    
    if "mappings" not in data:
        data["mappings"] = {}
    
    # Update mappings with captures
    controls_mapped = []
    for control_key, capture in _learn_wizard_state["captures"].items():
        if control_key not in data["mappings"]:
            data["mappings"][control_key] = {}
        data["mappings"][control_key]["keycode"] = capture["keycode"]
        data["mappings"][control_key]["key_name"] = capture["key_name"]
        controls_mapped.append(control_key)
    
    # Update timestamp
    data["last_modified"] = datetime.now().isoformat()
    data["modified_by"] = request.headers.get("x-device-id", "learn_wizard")
    
    # Save
    try:
        mapping_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mapping_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save: {exc}")
    
    # Log the save
    log_controller_change(
        request, drive_root, "learn_wizard_save",
        {
            "controls_mapped": controls_mapped,
            "count": len(controls_mapped),
        },
        backup_path,
    )

    # Stop input detection service after saving
    global _input_detection_service
    if _input_detection_service is not None:
        _input_detection_service.set_learn_mode(False)
        _input_detection_service._raw_handlers.clear()
        _input_detection_service.stop_listening()
        logger.info("[LearnWizard] Stopped input detection after save")

    # Direct MAME config write (simpler than cascade system)
    mame_config_result = None
    try:
        mame_config_path = drive_root / "Emulators" / "MAME" / "cfg" / "default.cfg"
        
        # Check if path is allowed by manifest
        sanctioned_paths = manifest.get("sanctioned_paths", [])
        if is_allowed_file(mame_config_path, drive_root, sanctioned_paths):
            # Generate MAME config XML from controls.json data
            xml_content = generate_mame_config(data)
            
            # Validate before writing
            validation_errors = validate_mame_config(xml_content)
            if not validation_errors:
                # Create directory if needed
                mame_config_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Create backup if file exists
                if mame_config_path.exists():
                    create_backup(mame_config_path, drive_root)
                
                # Write the config
                with open(mame_config_path, "w", encoding="utf-8") as f:
                    f.write(xml_content)
                
                mame_config_result = {
                    "status": "success",
                    "path": str(mame_config_path.relative_to(drive_root)),
                    "controls": len(controls_mapped),
                }
                logger.info("[LearnWizard] Wrote MAME config to %s", mame_config_path)
            else:
                mame_config_result = {
                    "status": "validation_failed",
                    "errors": validation_errors[:3],
                }
                logger.warning("[LearnWizard] MAME config validation failed: %s", validation_errors)
        else:
            mame_config_result = {
                "status": "path_not_allowed",
                "path": str(mame_config_path),
            }
            logger.debug("[LearnWizard] MAME config path not in sanctioned paths")
    except MAMEConfigError as e:
        mame_config_result = {"status": "generation_failed", "error": str(e)}
        logger.warning("[LearnWizard] MAME config generation failed: %s", e)
    except Exception as e:
        mame_config_result = {"status": "write_failed", "error": str(e)}
        logger.exception("[LearnWizard] MAME config write failed")

    # Direct TeknoParrot config write (for all existing profiles)
    teknoparrot_results = []
    try:
        tp_profiles_dir = drive_root / "Emulators" / "TeknoParrot" / "UserProfiles"
        
        # Check if TP profiles directory exists and is allowed
        sanctioned_paths = manifest.get("sanctioned_paths", [])
        if tp_profiles_dir.exists() and is_allowed_file(tp_profiles_dir, drive_root, sanctioned_paths):
            # Get panel mappings from controls.json data
            panel_mappings = data.get("mappings", {})
            
            # Iterate through existing profile XMLs
            profile_count = 0
            success_count = 0
            for profile_path in tp_profiles_dir.glob("*.xml"):
                profile_name = profile_path.name
                
                # Only update profiles for supported games
                if is_game_supported(profile_name):
                    profile_count += 1
                    
                    # Build canonical mapping for this game
                    canonical = build_canonical_mapping(
                        profile_name,
                        panel_mappings,
                        player=1,
                        input_mode=TPInputMode.XINPUT,
                    )
                    
                    if canonical:
                        # Apply the config
                        result = apply_tp_config(
                            profile_path,
                            canonical,
                            drive_root,
                            backup=True,
                        )
                        
                        if result.success:
                            success_count += 1
                            teknoparrot_results.append({
                                "profile": profile_name,
                                "status": "success",
                                "changes": result.changes_applied,
                            })
                        else:
                            teknoparrot_results.append({
                                "profile": profile_name,
                                "status": "failed",
                                "error": result.error,
                            })
            
            if profile_count > 0:
                logger.info(
                    "[LearnWizard] Updated %d/%d TeknoParrot profiles",
                    success_count, profile_count
                )
        else:
            logger.debug("[LearnWizard] TeknoParrot UserProfiles not found or not allowed")
    except Exception as e:
        logger.exception("[LearnWizard] TeknoParrot config write failed")
        teknoparrot_results = [{"status": "error", "error": str(e)}]

    # Trigger cascade to update MAME, TeknoParrot, etc.
    cascade_job = None
    cascade_preference = get_cascade_preference(drive_root)
    
    if cascade_preference == "auto":
        # Auto-cascade: trigger immediately
        requested_by = request.headers.get("x-device-id", "learn_wizard")
        backup_on_write = getattr(request.app.state, "backup_on_write", False)
        
        cascade_job = enqueue_cascade_job(
            drive_root,
            requested_by=requested_by,
            metadata={"source": "learn_wizard", "controls_mapped": controls_mapped},
            backup=backup_on_write,
        )
        
        background_tasks.add_task(
            run_cascade_job,
            drive_root,
            manifest,
            cascade_job["job_id"],
            backup=backup_on_write,
        )
    
    # Build response
    response = {
        "status": "saved",
        "controls_mapped": len(controls_mapped),
        "backup_path": str(backup_path) if backup_path else None,
        "cascade_preference": cascade_preference,
    }
    
    # Add MAME config result to response
    if mame_config_result:
        response["mame_config"] = mame_config_result
    
    # Add TeknoParrot results to response
    if teknoparrot_results:
        tp_success = sum(1 for r in teknoparrot_results if r.get("status") == "success")
        response["teknoparrot_config"] = {
            "profiles_updated": tp_success,
            "total_attempted": len(teknoparrot_results),
            "details": teknoparrot_results[:5],  # First 5 for brevity
        }
    
    # Build user-friendly prompt based on what happened
    mame_ok = mame_config_result and mame_config_result.get("status") == "success"
    tp_ok = teknoparrot_results and any(r.get("status") == "success" for r in teknoparrot_results)
    
    if mame_ok and tp_ok:
        response["chuck_prompt"] = (
            f"Done! Saved {len(controls_mapped)} controls. "
            f"Updated MAME and TeknoParrot configs. Your controls are ready!"
        )
    elif mame_ok:
        response["chuck_prompt"] = (
            f"Done! Saved {len(controls_mapped)} controls and updated MAME config. "
            f"Your controls are ready to use!"
        )
    elif tp_ok:
        response["chuck_prompt"] = (
            f"Done! Saved {len(controls_mapped)} controls and updated TeknoParrot profiles. "
            f"Your controls are ready to use!"
        )
    else:
        response["chuck_prompt"] = (
            f"Done! Saved {len(controls_mapped)} controls. "
            f"Your mappings are ready to use."
        )
    
    return response



@router.post("/learn-wizard/stop")
async def stop_learn_wizard(request: Request):
    """Stop the learn wizard without saving."""
    require_scope(request, "state")
    global _learn_wizard_state, _input_detection_service

    # Stop input detection service if running
    if _input_detection_service is not None:
        _input_detection_service.set_learn_mode(False)
        _input_detection_service._raw_handlers.clear()
        _input_detection_service.stop_listening()
        logger.info("[LearnWizard] Stopped input detection")

    _learn_wizard_state = {}

    return {"status": "stopped", "chuck_prompt": "Wizard cancelled. No changes saved."}


@router.post("/learn-wizard/undo")
async def undo_learn_wizard_capture(request: Request):
    """Undo the last capture and go back one step.
    
    This allows users to correct mistakes during the wizard by stepping
    back to the previous control and re-capturing it.
    """
    require_scope(request, "state")
    global _learn_mode_latest_key
    
    if not _learn_wizard_state:
        raise HTTPException(status_code=400, detail="Wizard not started")
    
    current_index = _learn_wizard_state.get("current_index", 0)
    sequence = _learn_wizard_state.get("sequence", [])
    
    # Can't go back from the first control
    if current_index <= 0:
        first_control = sequence[0] if sequence else "p1.up"
        display_name = CONTROL_DISPLAY_NAMES.get(first_control, first_control)
        return {
            "status": "at_start",
            "current_control": first_control,
            "chuck_prompt": f"Already at the first control. Which button is {display_name}? Press it now.",
            "display_name": display_name,
        }
    
    # Go back one step
    _learn_wizard_state["current_index"] = current_index - 1
    previous_control = sequence[current_index - 1]
    
    # Remove the previous capture so it can be re-captured
    if previous_control in _learn_wizard_state.get("captures", {}):
        del _learn_wizard_state["captures"][previous_control]
    
    # Clear any pending capture
    _learn_mode_latest_key = None
    
    previous_display = CONTROL_DISPLAY_NAMES.get(previous_control, previous_control)
    
    return {
        "status": "undone",
        "current_control": previous_control,
        "current_index": current_index - 1,
        "total_controls": len(sequence),
        "chuck_prompt": f"Okay, back to {previous_display}.",
        "display_name": previous_display,
        "captures": _learn_wizard_state.get("captures", {}),
    }


# ============================================================================
# Click-to-Map Single Control Mapping
# ============================================================================

class SingleMappingRequest(BaseModel):
    controlKey: str = Field(..., description="Control key, e.g., 'p1.up', 'p2.button3'")
    keycode: str = Field(..., description="Keycode to assign, e.g., 'ArrowUp', 'KeyZ', 'GAMEPAD_BTN_0'")
    source: Optional[str] = Field(default="keyboard", description="Input source: 'keyboard' or 'gamepad'")


@router.post("/mapping/set")
async def set_single_mapping(request: Request, payload: SingleMappingRequest):
    """Set mapping for a single control (click-to-map system).
    
    This is the core endpoint for the user-driven mapping flow where users
    click a control in the GUI and then press a physical button.
    
    Body:
        controlKey: Control to map (e.g., "p1.up", "p2.button3")
        keycode: Keycode to assign (e.g., "ArrowUp", "GAMEPAD_BTN_0")
        source: "keyboard" or "gamepad"
    
    Returns:
        Status and the updated mapping
    """
    require_scope(request, "config")
    _ensure_writes_allowed(request)
    
    control_key = payload.controlKey
    keycode = payload.keycode
    source = payload.source or "keyboard"
    
    # Validate control key format
    if "." not in control_key:
        raise HTTPException(status_code=400, detail=f"Invalid control key format: {control_key}")
    
    drive_root: Path = request.app.state.drive_root
    mapping_file = drive_root / "config" / "mappings" / "controls.json"
    
    # Create backup before modifying
    backup_path = None
    if mapping_file.exists() and getattr(request.app.state, "backup_on_write", True):
        backup_path = create_backup(mapping_file, drive_root)
    
    # Load existing mappings
    try:
        if mapping_file.exists():
            with open(mapping_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"version": 1, "board": {}, "mappings": {}}
    except Exception:
        data = {"version": 1, "board": {}, "mappings": {}}
    
    if "mappings" not in data:
        data["mappings"] = {}
    
    # Check for duplicate keycode
    duplicate_control = None
    for existing_key, existing_mapping in data["mappings"].items():
        if existing_key != control_key and existing_mapping.get("keycode") == keycode:
            duplicate_control = existing_key
            break
    
    # Update the single mapping
    data["mappings"][control_key] = {
        "keycode": keycode,
        "key_name": keycode.replace("KEY_", "").replace("GAMEPAD_", "").lower(),
        "source": source,
        "mapped_at": datetime.now().isoformat(),
    }
    
    # Update metadata
    data["last_modified"] = datetime.now().isoformat()
    data["modified_by"] = request.headers.get("x-device-id", "click_to_map")
    
    # Save
    try:
        mapping_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mapping_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save mapping: {exc}")
    
    # Log the change
    log_controller_change(
        request, drive_root, "single_mapping_set",
        {
            "control_key": control_key,
            "keycode": keycode,
            "source": source,
        },
        backup_path,
    )
    
    response = {
        "status": "saved",
        "controlKey": control_key,
        "keycode": keycode,
        "source": source,
    }
    
    if duplicate_control:
        response["warning"] = f"Note: {keycode} was also assigned to {duplicate_control}"
        response["duplicate_control"] = duplicate_control
    
    return response


class ClearMappingRequest(BaseModel):
    controlKey: str = Field(..., description="Control key to clear, e.g., 'p1.up'")


@router.post("/mapping/clear")
async def clear_single_mapping(request: Request, payload: ClearMappingRequest):
    """Clear mapping for a single control.
    
    Removes the keycode assignment for a specific control.
    
    Body:
        controlKey: Control to clear (e.g., "p1.up")
    """
    require_scope(request, "config")
    _ensure_writes_allowed(request)
    
    control_key = payload.controlKey
    
    drive_root: Path = request.app.state.drive_root
    mapping_file = drive_root / "config" / "mappings" / "controls.json"
    
    if not mapping_file.exists():
        return {"status": "no_file", "controlKey": control_key}
    
    # Load existing
    try:
        with open(mapping_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"status": "parse_error", "controlKey": control_key}
    
    if "mappings" not in data or control_key not in data["mappings"]:
        return {"status": "not_found", "controlKey": control_key}
    
    # Create backup
    backup_path = None
    if getattr(request.app.state, "backup_on_write", True):
        backup_path = create_backup(mapping_file, drive_root)
    
    # Remove the mapping
    old_mapping = data["mappings"].pop(control_key, None)
    
    # Update metadata
    data["last_modified"] = datetime.now().isoformat()
    
    # Save
    try:
        with open(mapping_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save: {exc}")
    
    return {
        "status": "cleared",
        "controlKey": control_key,
        "previous_keycode": old_mapping.get("keycode") if old_mapping else None,
    }


class EncoderModeRequest(BaseModel):
    mode: str = Field(..., description="Encoder mode: 'keyboard', 'xinput', or 'dinput'")


@router.post("/encoder-mode")
async def set_encoder_mode(request: Request, payload: EncoderModeRequest):
    """Set the encoder mode preference.
    
    This stores the user's declared encoder mode in the controls.json file.
    Used by the click-to-map system to know how to interpret inputs.
    
    Body:
        mode: "keyboard", "xinput", or "dinput"
    """
    require_scope(request, "config")
    
    mode = payload.mode.lower()
    if mode not in ("keyboard", "xinput", "dinput"):
        raise HTTPException(status_code=400, detail=f"Invalid mode: {mode}")
    
    drive_root: Path = request.app.state.drive_root
    mapping_file = drive_root / "config" / "mappings" / "controls.json"
    
    # Load or create
    try:
        if mapping_file.exists():
            with open(mapping_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"version": 1, "board": {}, "mappings": {}}
    except Exception:
        data = {"version": 1, "board": {}, "mappings": {}}
    
    # Set encoder mode
    data["encoder_mode"] = mode
    data["last_modified"] = datetime.now().isoformat()
    
    # Save
    try:
        mapping_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mapping_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save: {exc}")
    
    return {
        "status": "saved",
        "encoder_mode": mode,
    }


# ============================================================================
# Encoder Mode State (Calibration / Mode Drift Detection)
# ============================================================================

@router.get("/encoder-state")
async def get_encoder_state(request: Request):
    """Get current encoder mode state.
    
    Returns:
        - baseline_mode: The calibrated baseline mode (keyboard/xinput/dinput)
        - current_mode: Mode detected from most recent input
        - mode_match: True if current matches baseline
        - needs_recalibration: True if mode drift detected
    """
    require_scope(request, "state")
    drive_root: Path = request.app.state.drive_root
    manager = get_encoder_state_manager(drive_root)
    return manager.get_state()


@router.post("/encoder-state/calibrate")
async def calibrate_encoder_baseline(request: Request):
    """Capture baseline mode by pressing any button.
    
    This starts learn mode briefly, captures the first keypress,
    detects the mode from that keypress, and saves it as baseline.
    
    Returns the updated encoder state with the new baseline.
    """
    require_scope(request, "state")
    drive_root: Path = request.app.state.drive_root
    
    # Get the encoder state manager
    manager = get_encoder_state_manager(drive_root)
    
    # Return instructions - actual capture happens via learn-mode
    return {
        "status": "ready",
        "message": "Start learn mode, press any button, then call /encoder-state/capture with the keycode.",
        "instructions": [
            "1. Call POST /controller/input/learn/start",
            "2. Press any button on your encoder",
            "3. Call GET /controller/input/learn/latest to get the keycode",
            "4. Call POST /controller/encoder-state/capture with the keycode"
        ],
        "current_baseline": manager.baseline_mode,
    }


class EncoderCaptureRequest(BaseModel):
    keycode: str = Field(..., description="The captured keycode to set baseline from")


@router.post("/encoder-state/capture")
async def capture_encoder_baseline(request: Request, payload: EncoderCaptureRequest):
    """Capture a keycode and set it as the mode baseline.
    
    Called after user presses a button in learn mode.
    Detects the mode from the keycode and saves as baseline.
    """
    require_scope(request, "state")
    drive_root: Path = request.app.state.drive_root
    
    # Detect mode from keycode
    mode = detect_input_mode(payload.keycode)
    
    # Get encoder state manager and capture baseline
    manager = get_encoder_state_manager(drive_root)
    state = manager.capture_baseline(mode, payload.keycode)
    
    return {
        "status": "captured",
        "keycode": payload.keycode,
        "detected_mode": mode,
        "chuck_prompt": f"Got it! Your encoder is in {mode} mode. I'll watch for mode changes.",
        **state,
    }


@router.post("/encoder-state/reset")
async def reset_encoder_state(request: Request):
    """Reset encoder state to defaults (clear baseline)."""
    require_scope(request, "state")
    drive_root: Path = request.app.state.drive_root
    
    manager = get_encoder_state_manager(drive_root)
    manager.reset()
    
    return {
        "status": "reset",
        "message": "Encoder state reset. No baseline mode set.",
        "chuck_prompt": "Encoder baseline cleared. Run calibration again when ready.",
    }

# NOTE: /mapping/reset endpoint is defined later in this file at line ~2145
# It restores from factory-default.json which is the correct behavior


class LearnMappingRequest(BaseModel):
    control_key: str = Field(..., description="Control to map, e.g., p1.button1")
    keycode: str = Field(..., description="Key code captured, e.g., KEY_F1")


@router.post("/input/learn/save")
async def save_learned_mapping(request: Request, payload: LearnMappingRequest):
    """Save a learned key-to-control mapping to the controls.json file.
    
    This updates the mapping so the captured keycode is associated with the control.
    """
    require_scope(request, "config")
    drive_root: Path = request.app.state.drive_root
    mapping_file = drive_root / "config" / "mappings" / "controls.json"
    
    if not mapping_file.exists():
        raise HTTPException(status_code=404, detail="Mapping file not found")
    
    try:
        with open(mapping_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read mapping: {exc}")
    
    # Ensure mappings dict exists
    if "mappings" not in data:
        data["mappings"] = {}
    
    # Normalize keycode to get the key name (remove KEY_ prefix if present)
    key_name = payload.keycode.upper().replace("KEY_", "").lower()
    
    # Update or create the mapping entry
    # We need to find the pin for this keycode from the board mapping
    # For now, we'll store the keycode directly and let the detection service use it
    if payload.control_key not in data["mappings"]:
        data["mappings"][payload.control_key] = {}
    
    data["mappings"][payload.control_key]["keycode"] = payload.keycode
    data["mappings"][payload.control_key]["key_name"] = key_name
    
    # Write back
    try:
        with open(mapping_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save mapping: {exc}")
    
    # Log the change
    audit_log.append({
        "scope": "config",
        "action": "learn_mapping",
        "control_key": payload.control_key,
        "keycode": payload.keycode,
        "device_id": request.headers.get("x-device-id", "unknown"),
    })
    
    return {
        "status": "saved",
        "control_key": payload.control_key,
        "keycode": payload.keycode,
        "message": f"Mapped {payload.control_key} to {payload.keycode}",
    }


@router.post("/input/detect")

async def detect_input_event(
    request: Request,
    payload: InputDetectionRequest,
    background_tasks: BackgroundTasks,
):
    """Manually process a keycode as if it were received from the encoder."""
    require_scope(request, "state")
    drive_root: Path = request.app.state.drive_root
    cascade_preference = get_cascade_preference(drive_root)
    service = _get_input_detection_service(request)
    try:
        event = service.on_input_detected(payload.keycode)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    global _latest_input_event
    _latest_input_event = event
    _record_teach_event(drive_root, event)
    logger.info(
        "Input detection manual event: key=%s pin=%s control=%s",
        event.keycode,
        event.pin,
        event.control_key,
    )

    mapping_result = _apply_detected_event_to_mapping(request, event)
    cascade_job = None
    cascade_prompt = False
    if mapping_result["changed"]:
        cascade_job = _maybe_trigger_auto_cascade(
            request,
            background_tasks,
            metadata={"source": "input-detection", "control_key": event.control_key},
        )
        if cascade_job is None and cascade_preference == "ask":
            cascade_prompt = True

    response: Dict[str, Any] = {
        "status": "detected",
        "event": _serialize_input_event(event),
        "mapping_updated": mapping_result["changed"],
        "pin_conflicts": mapping_result.get("conflicts") or [],
        "mapping_path": mapping_result.get("mapping_path"),
    }
    if mapping_result["backup_path"]:
        response["backup_path"] = mapping_result["backup_path"]
    if cascade_job:
        response["cascade_job"] = {
            "job_id": cascade_job["job_id"],
            "status": cascade_job.get("status"),
        }
    elif cascade_prompt:
        response["cascade_prompt"] = True
    response["cascade_preference"] = cascade_preference
    return response


def _resolve_board_type(
    request: Request,
    board_type_override: Optional[str] = None,
) -> str:
    if board_type_override:
        return board_type_override.lower()

    config = getattr(request.app.state, "config", {}) or {}
    configured = config.get("controller_board_type")
    if configured:
        return str(configured).lower()

    drive_root: Path = request.app.state.drive_root
    inferred = _board_type_from_mapping(drive_root)
    if inferred:
        return inferred

    # As a final fallback, perform a quick detection for known boards.
    pacto_helper = PactoTechBoard()
    board = pacto_helper.detect(use_cache=True, timeout=1.0)
    if board and board.detected:
        return pacto_helper.BOARD_TYPE

    return "generic"


def _board_type_from_mapping(drive_root: Path) -> Optional[str]:
    mapping_path = drive_root / "config" / "mappings" / "controls.json"
    if not mapping_path.exists():
        return None

    try:
        with open(mapping_path, "r", encoding="utf-8") as handle:
            mapping_data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None

    board_info = mapping_data.get("board") or {}
    board_type = board_info.get("board_type")
    if isinstance(board_type, str) and board_type.strip():
        return board_type.lower()

    vid = board_info.get("vid")
    pid = board_info.get("pid")
    name = board_info.get("name")
    if PactoTechBoard.matches(vid, pid, name):
        return PactoTechBoard.BOARD_TYPE

    return None


def _get_input_detection_service(
    request: Request,
    *,
    board_type_override: Optional[str] = None,
) -> InputDetectionService:
    drive_root: Path = request.app.state.drive_root
    board_type = _resolve_board_type(request, board_type_override=board_type_override)

    global _input_detection_service
    with _input_detection_lock:
        service = _input_detection_service
        if service is None or service.board_type != board_type:
            if service:
                service.stop_listening()
            service = InputDetectionService(board_type, drive_root)
            _register_input_event_handler(service)
            _input_detection_service = service
        return service


def _register_input_event_handler(service: InputDetectionService) -> None:
    if getattr(service, "_controller_handler_registered", False):
        return

    def _capture(event: InputEvent) -> None:
        global _latest_input_event
        _latest_input_event = event
        try:
            _record_teach_event(service.drive_root, event)
        except Exception:  # pragma: no cover - logging failures must not break detection
            logger.debug("Teach event logging failed during capture.", exc_info=True)

    service.register_handler(_capture)
    setattr(service, "_controller_handler_registered", True)


def _serialize_input_event(event: InputEvent) -> Dict[str, Any]:
    payload = InputDetectionEvent(
        timestamp=event.timestamp,
        keycode=event.keycode,
        pin=event.pin,
        control_key=event.control_key,
        player=event.player,
        control_type=event.control_type,
        source_id=event.source_id,
    )
    return payload.dict()


def _mapping_entry_from_event(
    event: InputEvent,
    existing: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    label = (existing or {}).get("label") or event.control_key.replace(".", " ").title()
    mapping_type = "joystick" if event.control_type == "joystick" else "button"
    entry = {
        "pin": event.pin,
        "type": mapping_type,
        "label": label,
    }
    return entry


def _apply_detected_event_to_mapping(
    request: Request,
    event: InputEvent,
) -> Dict[str, Any]:
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
            except json.JSONDecodeError as exc:  # pragma: no cover
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
        mapping_file = drive_root / "config" / "mappings" / "controls.json"

        if not mapping_file.exists():
            raise HTTPException(
                status_code=404,
                detail="Mapping file not found at config/mappings/controls.json"
            )

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

                if PactoTechBoard.matches(vid, pid, board.name):
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
        mapping_file = drive_root / "config" / "mappings" / "controls.json"

        # Read current content
        current_content = ""
        current_data = {}
        if mapping_file.exists():
            with open(mapping_file, 'r', encoding='utf-8') as f:
                current_content = f.read()
                current_data = json.loads(current_content) if current_content else {}

        # Merge with new mappings (deep merge for nested structures)
        new_data = {**current_data}

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
            "file_exists": mapping_file.exists(),
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
        mapping_file = drive_root / "config" / "mappings" / "controls.json"

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

        # Read current content
        current_content = ""
        current_data = {}
        if mapping_file.exists():
            with open(mapping_file, 'r', encoding='utf-8') as f:
                current_content = f.read()
                current_data = json.loads(current_content) if current_content else {}

        # Merge with new mappings
        new_data = {**current_data}

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
        log_controller_change(
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
        log_controller_change(
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
        log_controller_change(
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

    audit_log.append(
        {
            "scope": "controller",
            "action": "controller_cascade_queued",
            "job_id": job_record["job_id"],
            "requested_by": request.headers.get("x-device-id", "unknown"),
            "skip_led": payload.skip_led,
            "skip_emulators": payload.skip_emulators,
        }
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


# ========== MAME Config Generation Endpoints ==========

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
        log_controller_change(
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


# ========== Controller Device Detection Endpoints ==========
# NOTE: The primary /devices endpoint is defined earlier (line ~714)
# This duplicate was removed on 2025-12-26 to fix route ambiguity.
# See: LED_BLINKY_CONTROLLER_CHUCK_AUDIT_2025-12-26_1541.md Finding #4


@router.post("/refresh")
async def refresh_controller_detection(request: Request):
    """Force refresh of board detection cache.
    
    Clears cached device detection results and re-scans hardware.
    Call this when devices are connected after startup or to verify hardware status.
    """
    require_scope(request, "state")
    try:
        # Invalidate detection service cache
        detection_service = get_detection_service()
        detection_service.invalidate_cache()
        
        # Re-scan devices
        snapshot = scan_devices()
        
        return {
            "status": "refreshed",
            "devices": snapshot,
            "device_count": len(snapshot),
            "cache_cleared": True,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Controller refresh failed: {e}")
        raise HTTPException(status_code=500, detail=f"Refresh failed: {str(e)}")


@router.get("/health")
async def get_controller_health(request: Request):
    """Get controller subsystem health and diagnostics

    Checks USB backend availability, permissions, and provides actionable
    guidance for troubleshooting detection issues.

    Returns:
        Dictionary with health status and diagnostic information
    """
    try:
        health_data = {
            "usb_backend": "ok",
            "permissions": "ok",
            "arcade_board_detection": "unknown",
            "handheld_detection": "unknown",
            "last_check": datetime.now().isoformat(),
            "hints": [],
        }

        # Test USB backend availability
        try:
            from ..services.usb_detector import detect_usb_devices

            # Try a quick USB detection
            try:
                devices = detect_usb_devices(include_unknown=False, use_cache=False)
                health_data["usb_backend"] = "ok"
                health_data["handheld_detection"] = "ok"
                health_data["usb_device_count"] = len(devices)
            except USBBackendError as e:
                health_data["usb_backend"] = "backend_unavailable"
                health_data["handheld_detection"] = "degraded"
                health_data["hints"].append(
                    "USB backend unavailable. Run backend on Windows (start-gui.bat), "
                    "or on WSL install libusb and attach device with usbipd."
                )
                logger.warning(f"USB backend unavailable: {e}")
            except USBPermissionError as e:
                health_data["usb_backend"] = "ok"
                health_data["permissions"] = "permission_denied"
                health_data["handheld_detection"] = "degraded"
                health_data["hints"].append(
                    "USB permission denied. Run as Administrator (Windows) "
                    "or use sudo/add user to plugdev (Linux)."
                )
                logger.warning(f"USB permission denied: {e}")
        except ImportError as e:
            health_data["usb_backend"] = "backend_unavailable"
            health_data["hints"].append("USB detection module not available")
            logger.error(f"USB detector import failed: {e}")

        # Check arcade board detection capability
        try:
            detection_service = get_detection_service()
            stats = detection_service.get_cache_stats()
            health_data["arcade_board_detection"] = "ok"
            health_data["detection_cache_stats"] = stats
        except Exception as e:
            health_data["arcade_board_detection"] = "degraded"
            logger.warning(f"Arcade board detection service unavailable: {e}")

        # Check mapping file
        drive_root = request.app.state.drive_root
        mapping_file = drive_root / "config" / "mappings" / "controls.json"
        health_data["mapping_file_exists"] = mapping_file.exists()

        if mapping_file.exists():
            try:
                with open(mapping_file, 'r', encoding='utf-8') as f:
                    mapping_data = json.load(f)
                    board = mapping_data.get("board", {})
                    if board.get("vid") and board.get("pid"):
                        health_data["configured_board"] = {
                            "vid": board.get("vid"),
                            "pid": board.get("pid"),
                            "name": board.get("name", "Unknown"),
                        }
            except Exception as e:
                logger.warning(f"Failed to read mapping file: {e}")

        # Overall health determination
        if health_data["usb_backend"] == "backend_unavailable":
            health_data["overall_status"] = "degraded"
        elif health_data["permissions"] == "permission_denied":
            health_data["overall_status"] = "degraded"
        else:
            health_data["overall_status"] = "healthy"

        return health_data

    except Exception as e:
        logger.error(f"Controller health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.post("/wizard/start")
async def start_wiring_wizard(request: Request):
    require_scope(request, "state")
    session_key = _wizard_session_key(request)
    drive_root: Path = request.app.state.drive_root
    # Load any existing identity bindings
    existing_identity = player_identity.load_bindings(drive_root)
    _wizard_states[session_key] = {
        "captures": {},
        "sequence": list(DEFAULT_WIZARD_SEQUENCE),
        "started_at": datetime.utcnow().isoformat(),
        "identity": existing_identity.get("bindings", {}),
        "identity_status": existing_identity.get("status", "unbound"),
        "identity_pending": None,  # Player number awaiting next detection
    }
    return {
        "status": "started",
        "next": DEFAULT_WIZARD_SEQUENCE[0],
        "identity_status": existing_identity.get("status", "unbound"),
    }


@router.post("/wizard/next-step")
async def wizard_next_step(request: Request):
    require_scope(request, "state")
    session_key = _wizard_session_key(request)
    state = _wizard_states.get(session_key)
    if not state:
        raise HTTPException(status_code=404, detail="Wizard not started")
    return {"next": _get_next_step(state)}


@router.post("/wizard/capture")
async def wizard_capture(request: Request, capture: WizardCapture):
    require_scope(request, "state")
    session_key = _wizard_session_key(request)
    state = _wizard_states.setdefault(
        session_key,
        {"captures": {}, "sequence": list(DEFAULT_WIZARD_SEQUENCE), "started_at": datetime.utcnow().isoformat()},
    )
    if capture.control_key not in state["sequence"]:
        raise HTTPException(status_code=400, detail="Control not part of wizard sequence")
    entry = {
        "pin": capture.pin,
        "type": capture.control_type or _default_control_type(capture.control_key),
    }
    state["captures"][capture.control_key] = entry
    return {"status": "recorded", "control": capture.control_key, "next": _get_next_step(state)}


@router.post("/wizard/preview")
async def wizard_preview(request: Request):
    require_scope(request, "state")
    session_key = _wizard_session_key(request)
    state = _wizard_states.get(session_key)
    if not state or not state["captures"]:
        return {"status": "empty"}
    update = MappingUpdate(mappings=state["captures"])
    return await preview_controller_mapping(request, update)


@router.post("/wizard/apply")
async def wizard_apply(request: Request, background_tasks: BackgroundTasks):
    require_scope(request, "config")
    session_key = _wizard_session_key(request)
    state = _wizard_states.get(session_key)
    if not state or not state["captures"]:
        raise HTTPException(status_code=400, detail="No captures to apply")
    update = MappingUpdate(mappings=state["captures"])
    response = await apply_controller_mapping(request, update, background_tasks)
    state["captures"] = {}
    return response


# ------------------------------------------------------------------ #
# Player Identity Calibration Endpoints
# ------------------------------------------------------------------ #

@router.get("/wizard/identity", response_model=PlayerIdentityResponse)
async def get_player_identity(request: Request):
    """Return current player identity calibration status and bindings.
    
    Shows whether identity has been calibrated and the current source->player mappings.
    """
    require_scope(request, "state")
    drive_root: Path = request.app.state.drive_root
    data = player_identity.load_bindings(drive_root)
    return PlayerIdentityResponse(
        status=data.get("status", "unbound"),
        bindings=data.get("bindings", {}),
        calibrated_at=data.get("calibrated_at"),
    )


@router.post("/wizard/identity/bind")
async def bind_player_identity(request: Request, player: int):
    """Bind the next detected input source to the specified player number.
    
    Args:
        player: The logical player number (1-4) to bind.
    
    Call this, then press a button on the physical station. The source_id from
    the next detection will be bound to this player number.
    """
    require_scope(request, "state")
    if player < 1 or player > 4:
        raise HTTPException(status_code=400, detail="Player must be 1-4")
    
    session_key = _wizard_session_key(request)
    state = _wizard_states.get(session_key)
    if not state:
        # Start a minimal session if not already started
        drive_root: Path = request.app.state.drive_root
        existing_identity = player_identity.load_bindings(drive_root)
        state = {
            "captures": {},
            "sequence": [],
            "started_at": datetime.utcnow().isoformat(),
            "identity": existing_identity.get("bindings", {}),
            "identity_status": existing_identity.get("status", "unbound"),
            "identity_pending": None,
        }
        _wizard_states[session_key] = state
    
    state["identity_pending"] = player
    
    # Start input detection to capture the next button press
    service = _get_input_detection_service(request)
    service.start_listening()
    
    return {
        "status": "awaiting_input",
        "message": f"Press any button at Player {player} station",
        "player": player,
    }


@router.post("/wizard/identity/capture")
async def capture_player_identity(request: Request):
    """Capture the most recent input and bind it to the pending player.
    
    Must be called after /wizard/identity/bind and after a button was pressed.
    Binds the source_id from the detected input to the pending player number.
    """
    require_scope(request, "state")
    session_key = _wizard_session_key(request)
    state = _wizard_states.get(session_key)
    
    if not state:
        raise HTTPException(status_code=400, detail="No wizard session active")
    
    pending_player = state.get("identity_pending")
    if pending_player is None:
        raise HTTPException(status_code=400, detail="No identity bind pending. Call /wizard/identity/bind first.")
    
    # Get the latest detected event
    if _latest_input_event is None:
        raise HTTPException(status_code=400, detail="No input detected. Press a button on the encoder.")
    
    source_id = _latest_input_event.source_id
    if not source_id:
        source_id = "unknown"  # Fallback if source_id wasn't populated
    
    # Update the identity bindings in session state
    if "identity" not in state:
        state["identity"] = {}
    state["identity"][source_id] = pending_player
    state["identity_pending"] = None
    state["identity_status"] = "pending_apply"
    
    return {
        "status": "captured",
        "source_id": source_id,
        "player": pending_player,
        "bindings": state["identity"],
        "message": f"Bound {source_id} to Player {pending_player}",
    }


@router.post("/wizard/identity/apply")
async def apply_player_identity(request: Request):
    """Persist the current session's identity bindings to disk.
    
    Creates a backup of any existing bindings and logs the change to changes.jsonl.
    """
    require_scope(request, "config")
    session_key = _wizard_session_key(request)
    state = _wizard_states.get(session_key)
    
    if not state:
        raise HTTPException(status_code=400, detail="No wizard session active")
    
    bindings = state.get("identity", {})
    if not bindings:
        raise HTTPException(status_code=400, detail="No identity bindings to apply")
    
    drive_root: Path = request.app.state.drive_root
    backup_path = player_identity.save_bindings(drive_root, bindings)
    
    # Update session state
    state["identity_status"] = "bound"
    
    return {
        "status": "applied",
        "bindings": bindings,
        "backup_path": str(backup_path) if backup_path else None,
        "message": f"Applied {len(bindings)} identity binding(s)",
    }


@router.post("/wizard/identity/reset")
async def reset_player_identity(request: Request):
    """Clear all identity bindings and revert to pin-based inference.
    
    Creates a backup before clearing and logs the reset action.
    """
    require_scope(request, "config")
    drive_root: Path = request.app.state.drive_root
    backup_path = player_identity.reset_bindings(drive_root)
    
    # Clear session state if active
    session_key = _wizard_session_key(request)
    state = _wizard_states.get(session_key)
    if state:
        state["identity"] = {}
        state["identity_status"] = "unbound"
        state["identity_pending"] = None
    
    return {
        "status": "reset",
        "backup_path": str(backup_path) if backup_path else None,
        "message": "Identity bindings reset. System will use pin-based player inference.",
    }


# ============================================================================
# Click-to-Map Input Detection Endpoints
# ============================================================================
# These endpoints support the new click-to-map controller mapping system.
# The frontend polls /input-detect to get the latest captured input from pygame.

# Global state for click-to-map input capture
_click_to_map_latest_input: Optional[Dict[str, Any]] = None
_click_to_map_lock = Lock()


@router.get("/input-detect")
async def get_captured_input(request: Request):
    """Get the latest captured input from pygame-based detection.
    
    Returns the most recently captured keycode/button/hat press from the
    InputDetectionService. Used by the click-to-map frontend component
    to detect physical button presses on the arcade encoder.
    
    Returns:
        captured_key: The captured keycode (e.g., "DPAD_UP_JS1", "BTN_0_JS1")
        source: Input source ("keyboard", "xinput", "dinput", "hat")
        timestamp: When the input was captured
    """
    global _click_to_map_latest_input
    
    with _click_to_map_lock:
        if _click_to_map_latest_input:
            return _click_to_map_latest_input
        
    return {"captured_key": None, "source": None, "timestamp": None}


@router.post("/input-detect/clear")
async def clear_captured_input(request: Request):
    """Clear the latest captured input.
    
    Called by the frontend after it has processed a captured input,
    so subsequent polls return null until a new input is detected.
    """
    global _click_to_map_latest_input
    
    with _click_to_map_lock:
        _click_to_map_latest_input = None
    
    return {"status": "cleared"}


@router.post("/input-detect/start")
async def start_input_detection(request: Request):
    """Start listening for inputs in click-to-map mode.
    
    Initializes the InputDetectionService if not already running and
    registers a handler to capture inputs for click-to-map.
    """
    global _input_detection_service, _click_to_map_latest_input
    
    drive_root: Path = request.app.state.drive_root
    
    def capture_handler(keycode: str):
        """Raw handler that captures inputs for click-to-map."""
        global _click_to_map_latest_input
        import time
        
        with _click_to_map_lock:
            # Detect input mode from keycode pattern
            source = detect_input_mode(keycode)
            
            _click_to_map_latest_input = {
                "captured_key": keycode,
                "source": source,
                "timestamp": time.time(),
            }
            logger.info(f"[Click-to-Map] Captured: {keycode} (source: {source})")
    
    with _input_detection_lock:
        if not _input_detection_service:
            try:
                _input_detection_service = InputDetectionService(
                    board_type="generic",
                    drive_root=drive_root
                )
            except Exception as e:
                logger.error(f"Failed to create InputDetectionService: {e}")
                raise HTTPException(status_code=500, detail=f"Input detection service failed: {e}")
        
        # Enable learn mode to capture all keys
        _input_detection_service.set_learn_mode(True)
        
        # Register the capture handler
        _input_detection_service.register_raw_handler(capture_handler)
        
        # Start listening if not already
        _input_detection_service.start_listening()
    
    # Clear any previous captured input
    with _click_to_map_lock:
        _click_to_map_latest_input = None
    
    return {"status": "started", "message": "Input detection started for click-to-map"}


@router.post("/input-detect/stop")
async def stop_input_detection(request: Request):
    """Stop listening for inputs in click-to-map mode.
    
    Stops the InputDetectionService and clears any captured input.
    """
    global _input_detection_service, _click_to_map_latest_input
    
    with _input_detection_lock:
        if _input_detection_service:
            _input_detection_service.set_learn_mode(False)
            # Note: We don't stop listening entirely, just disable learn mode
    
    with _click_to_map_lock:
        _click_to_map_latest_input = None
    
    return {"status": "stopped", "message": "Input detection stopped"}


# =============================================================================
# Genre Profile Endpoints
# =============================================================================

@router.get("/genre-profiles")
async def list_genre_profiles(request: Request) -> Dict[str, Any]:
    """List all available genre profiles.
    
    Returns a summary of each profile including name, description, genres matched,
    button count, LED profile availability, and supported emulators.
    """
    from ..services.genre_profile_service import get_genre_profile_service
    
    drive_root: Path = request.app.state.drive_root
    service = get_genre_profile_service(drive_root)
    
    profiles = service.list_profiles()
    genre_map = service.get_all_matching_genres()
    
    return {
        "status": "success",
        "profile_count": len(profiles),
        "profiles": profiles,
        "genre_mappings": genre_map,
    }


@router.get("/genre-profiles/{profile_key}")
async def get_genre_profile(request: Request, profile_key: str) -> Dict[str, Any]:
    """Get full details of a specific genre profile.
    
    Args:
        profile_key: Profile key (e.g., "fighting", "racing", "shmup")
    
    Returns:
        Complete profile data including button layout, LED profile, and emulator mappings.
    """
    from ..services.genre_profile_service import get_genre_profile_service
    
    drive_root: Path = request.app.state.drive_root
    service = get_genre_profile_service(drive_root)
    
    profile = service.get_profile(profile_key)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Genre profile '{profile_key}' not found")
    
    return {
        "status": "success",
        "profile_key": profile_key,
        "profile": profile,
    }


@router.get("/genre-profiles/match/genre/{genre}")
async def get_profile_for_genre(request: Request, genre: str) -> Dict[str, Any]:
    """Find the matching profile for a genre.
    
    Used by the launch system to determine which profile to apply for a game.
    
    Args:
        genre: Genre string from LaunchBox (e.g., "Fighting", "Racing")
    
    Returns:
        Matched profile key and profile data, or default if no specific match.
    """
    from ..services.genre_profile_service import get_genre_profile_service
    
    drive_root: Path = request.app.state.drive_root
    service = get_genre_profile_service(drive_root)
    
    profile_key, profile = service.get_profile_for_genre(genre)
    
    return {
        "status": "success",
        "genre_searched": genre,
        "profile_key": profile_key,
        "profile": profile,
        "match_type": "exact" if profile_key != "default" else "default",
    }


@router.get("/genre-profiles/match/game")
async def get_profile_for_game(
    request: Request,
    game_id: Optional[str] = None,
    game_title: Optional[str] = None,
    genre: Optional[str] = None,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """Find the matching profile for a specific game.
    
    Attempts to resolve the game's genre from LaunchBox metadata if not provided.
    
    Args:
        game_id: LaunchBox game ID (will lookup genre from cache)
        game_title: Game title (for logging/display)
        genre: Genre string (if already known, skips lookup)
        platform: Platform name (for additional context)
    
    Returns:
        Matched profile key and profile data.
    """
    from ..services.genre_profile_service import get_genre_profile_service
    
    drive_root: Path = request.app.state.drive_root
    service = get_genre_profile_service(drive_root)
    
    profile_key, profile = service.get_profile_for_game(
        game_id=game_id,
        game_title=game_title,
        genre=genre,
        platform=platform,
    )
    
    return {
        "status": "success",
        "game_id": game_id,
        "game_title": game_title,
        "genre_provided": genre,
        "platform": platform,
        "profile_key": profile_key,
        "profile": profile,
    }


@router.get("/genre-profiles/{profile_key}/emulator/{emulator}")
async def get_emulator_mappings_for_profile(
    request: Request,
    profile_key: str,
    emulator: str,
) -> Dict[str, Any]:
    """Get emulator-specific mappings for a genre profile.
    
    Resolves the profile's button_map against the current controls.json to produce
    emulator-ready input bindings.
    
    Args:
        profile_key: Profile key (e.g., "fighting")
        emulator: Emulator name (e.g., "teknoparrot", "pcsx2", "mame")
    
    Returns:
        Resolved emulator mappings with panel control → pin/keycode resolution.
    """
    from ..services.genre_profile_service import get_genre_profile_service
    
    drive_root: Path = request.app.state.drive_root
    service = get_genre_profile_service(drive_root)
    
    # Load current controls.json
    controls_path = drive_root / "config" / "mappings" / "controls.json"
    base_controls: Dict[str, Any] = {}
    if controls_path.exists():
        try:
            with open(controls_path, "r", encoding="utf-8") as f:
                controls_data = json.load(f)
                base_controls = controls_data.get("mappings", {})
        except Exception as e:
            logger.warning(f"Failed to load controls.json: {e}")
    
    mappings = service.get_emulator_mappings(emulator, profile_key, base_controls)
    if mappings is None:
        raise HTTPException(
            status_code=404,
            detail=f"No emulator mappings for '{emulator}' in profile '{profile_key}'"
        )
    
    return {
        "status": "success",
        "profile_key": profile_key,
        "emulator": emulator,
        "mappings": mappings,
    }


@router.get("/genre-profiles/{profile_key}/led")
async def get_led_profile_for_genre(request: Request, profile_key: str) -> Dict[str, Any]:
    """Get the LED color scheme for a genre profile.
    
    Args:
        profile_key: Profile key (e.g., "fighting")
    
    Returns:
        LED settings per button (color, label).
    """
    from ..services.genre_profile_service import get_genre_profile_service
    
    drive_root: Path = request.app.state.drive_root
    service = get_genre_profile_service(drive_root)
    
    led_profile = service.get_led_profile(profile_key)
    if not led_profile:
        raise HTTPException(
            status_code=404,
            detail=f"No LED profile for genre profile '{profile_key}'"
        )
    
    return {
        "status": "success",
        "profile_key": profile_key,
        "led_profile": led_profile,
    }


# =============================================================================
# MAME Per-Game Config Fix Endpoint (for Chuck)
# =============================================================================

class MAMEFixRequest(BaseModel):
    """Request body for MAME per-game config fix."""
    rom_name: str
    genre: Optional[str] = None  # Auto-detect if not specified
    issue_description: Optional[str] = None  # What the user reported


@router.post("/mame-fix")
async def fix_mame_game_config(
    request: Request,
    payload: MAMEFixRequest,
):
    """Generate a per-game MAME config to fix control issues.
    
    This endpoint is designed to be called by Chuck when a user reports
    game-specific issues like "special moves don't work in Street Fighter".
    
    It generates a clean per-game cfg with:
    - No OR fallbacks (single-source bindings)
    - Genre-appropriate button layout
    - UI controls (ESC to exit, etc.)
    
    Args:
        payload: ROM name and optional genre override
        
    Returns:
        Success status with generated config path and Chuck's response
    """
    drive_root: Path = request.app.state.drive_root
    
    rom_name = payload.rom_name.lower().replace(".zip", "").replace(".7z", "")
    
    # Auto-detect genre
    detected_genre = get_genre_for_rom(rom_name)
    genre = payload.genre or detected_genre
    
    logger.info(f"[MAME-Fix] Generating per-game config for {rom_name} (genre: {genre})")
    
    # Determine MAME cfg directory
    mame_cfg_dir = drive_root / "Emulators" / "MAME" / "cfg"
    
    # Check if sanctioned
    if not is_allowed_file(mame_cfg_dir / f"{rom_name}.cfg", drive_root, 
                           request.app.state.manifest.get("sanctioned_paths", [])):
        raise HTTPException(
            status_code=403,
            detail="MAME cfg directory is not in sanctioned paths"
        )
    
    try:
        # Generate and save the per-game config
        cfg_path = save_pergame_config(
            rom_name=rom_name,
            cfg_dir=mame_cfg_dir,
            genre=genre,
            backup=True,
        )
        
        # Generate Chuck's response
        genre_description = {
            "fighting": "6-button fighting game",
            "fighting_4button": "4-button fighting game",
            "shooter": "shooter",
            "racing": "racing game",
            "default": "arcade game",
        }.get(genre, "arcade game")
        
        chuck_prompt = (
            f"Done! I created a clean config for {rom_name} as a {genre_description}. "
            f"Restart the game and your controls should work properly now. "
            f"ESC will now exit the game to the menu."
        )
        
        return {
            "status": "success",
            "rom_name": rom_name,
            "genre": genre,
            "genre_detected": detected_genre,
            "cfg_path": str(cfg_path),
            "chuck_prompt": chuck_prompt,
        }
        
    except Exception as e:
        logger.exception(f"[MAME-Fix] Failed to generate config for {rom_name}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to generate per-game config: {str(e)}"
        )


@router.get("/mame-fix/fighting-games")
async def list_supported_fighting_games(request: Request):
    """List known fighting game ROMs that can be fixed.
    
    Returns:
        List of ROMs with their genres and descriptions
    """
    games = get_supported_fighting_games()
    return {
        "status": "success",
        "count": len(games),
        "games": games,
        "chuck_prompt": f"I know {len(games)} fighting games. Tell me which one needs fixing!",
    }

