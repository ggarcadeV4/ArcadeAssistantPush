"""Chuck Hardware Router — low-level hardware probing.

Extracted from the monolithic controller.py during Phase 2 (Persona Split).
Contains board sanity, firmware flashing, USB device scanning, input detection,
and all other endpoints that directly touch physical hardware.

Mounted at: /api/local/controller  (same prefix — no frontend URL changes)
"""

import json
import logging
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ..services.board_repair import BoardRepairService
from ..services.board_sanity import BoardSanityScanner, SanityReport
from ..services.controller_baseline import (
    ControllerBaselineError,
    load_controller_baseline,
)
from ..services.device_scanner import scan_devices
from ..services.encoder_hints import enrich_with_hints
from ..services import device_registry
from ..services.firmware_manager import FirmwareManager
from ..services.mapping_recovery import MappingRecoveryService
from ..services.chuck.ai import get_controller_ai_service
from ..services.chuck.detection import (
    BoardDetectionError,
    BoardNotFoundError,
    get_detection_service,
)
from ..services.chuck.input_detector import InputDetectionService, InputEvent
from ..services.chuck.pactotech import PactoTechBoard
from ..services.pacto_identity import (
    is_pacto_xinput_board_type,
    is_spoofed_xinput_pacto,
    is_spoofed_xinput_vid_pid,
    looks_like_pacto,
    normalize_vid_pid,
)
from ..services.policies import require_scope
from ..services.usb_detector import (
    USBBackendError,
    USBDetectionError,
    USBPermissionError,
    detect_arcade_boards,
    get_board_by_vid_pid,
)
from ..services.controller_shared import (
    ensure_writes_allowed,
    require_device_id,
    ensure_controller_panel,
    log_controller_change,
    record_teach_event,
    serialize_input_event,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Module-level state (hardware detection)
# ---------------------------------------------------------------------------

_input_detection_service: Optional[InputDetectionService] = None
_input_detection_lock = Lock()
_latest_input_event: Optional[InputEvent] = None

# Wave 1 #3: dedup demotion log entries so /input/start polling does not spam
# the operator log. Keys are stable strings derived from the demotion reason.
_demotion_logged_keys: set = set()


def _log_board_type_demotion(reason: str, key: str, detail: str) -> None:
    """Operator-visible signal for silent board-type fallbacks.

    Logs once per (reason, key) tuple at INFO level so debugging a "why isn't
    pacto-mode capture engaging?" question is a single grep away. Subsequent
    calls for the same demotion are silent.
    """
    dedup_key = f"{reason}::{key}"
    if dedup_key in _demotion_logged_keys:
        return
    _demotion_logged_keys.add(dedup_key)
    logger.info(
        "[Chuck] board-type demoted to generic — reason=%s key=%s detail=%s",
        reason, key, detail,
    )


def get_latest_event() -> Optional[InputEvent]:
    """Get the most recent input event captured by the service."""
    return _latest_input_event


def _looks_like_pacto_board(board: Dict[str, Any]) -> bool:
    """Compatibility wrapper — Pacto identity now lives in pacto_identity.

    Kept as a thin wrapper so any existing reference inside this module reads
    naturally; new code should call :func:`looks_like_pacto` directly.
    """
    return looks_like_pacto(board)


def _canonical_controller_entry(board: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Expose one logical encoder-board entry without hiding raw child endpoints."""
    board_key = board.get("board_type") or board.get("vid_pid") or f"board_{index}"
    return {
        "device_id": f"CANONICAL_BOARD\\{board_key}",
        "vid": board.get("vid"),
        "pid": board.get("pid"),
        "name": board.get("name") or board.get("board_name") or "Arcade Encoder",
        "manufacturer": board.get("vendor") or board.get("manufacturer"),
        "type": "arcade_board",
        "detected": bool(board.get("detected", True)),
        "interface": board.get("source") or "canonical",
        "status": "connected" if board.get("detected", True) else "configured (not connected)",
        "is_classified": False,
    }


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

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
    dry_run: bool = True


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
    backup_path: Optional[str] = None
    rollback_rationale: Optional[str] = None


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


class InputDetectionEvent(BaseModel):
    timestamp: float
    keycode: str
    pin: int
    control_key: str
    player: int
    control_type: str
    source_id: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _normalize_vid_pid_pair(
    vid: Optional[str],
    pid: Optional[str],
) -> Optional[str]:
    """Compatibility wrapper — delegates to shared ``normalize_vid_pid``."""
    return normalize_vid_pid(vid, pid)


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
        normalized = board_type.lower()
        if is_pacto_xinput_board_type(normalized):
            _log_board_type_demotion(
                "spoofed_pacto_board_type",
                normalized,
                "Saved board_type is XInput-spoofed Pacto; using generic capture path.",
            )
            return "generic"
        return normalized

    vid = board_info.get("vid")
    pid = board_info.get("pid")
    name = board_info.get("name")
    detected_mode = str(board_info.get("detected_mode") or "").lower()
    if detected_mode == "xinput":
        _log_board_type_demotion(
            "saved_detected_mode_xinput",
            normalize_vid_pid(vid, pid) or "no_vid_pid",
            "Saved detected_mode=xinput; using generic capture path.",
        )
        return "generic"

    if is_spoofed_xinput_vid_pid(vid, pid):
        _log_board_type_demotion(
            "spoofed_xinput_vid_pid",
            normalize_vid_pid(vid, pid) or "no_vid_pid",
            "Saved board carries Microsoft XInput VID/PID; using generic capture path.",
        )
        return "generic"

    if PactoTechBoard.matches(vid, pid, name):
        return PactoTechBoard.BOARD_TYPE

    return None


def get_input_detection_service(
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
            record_teach_event(service.drive_root, event)
        except Exception:  # pragma: no cover - logging failures must not break detection
            logger.debug("Teach event logging failed during capture.", exc_info=True)

    service.register_handler(_capture)
    setattr(service, "_controller_handler_registered", True)


# ---------------------------------------------------------------------------
# Board Sanity / Repair / Firmware endpoints
# ---------------------------------------------------------------------------

@router.get("/board/sanity")
async def controller_board_sanity(request: Request) -> BoardSanityResponse:
    """Perform a PactoTech board sanity scan."""
    require_scope(request, "state")
    device_id = require_device_id(request)
    ensure_controller_panel(request.headers.get("x-panel"))

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
    ensure_writes_allowed(request)
    device_id = require_device_id(request)
    ensure_controller_panel(request.headers.get("x-panel"))

    try:
        service = BoardRepairService(device_id=device_id)
        report = service.repair(actions=payload.actions, dry_run=payload.dry_run)
    except Exception as exc:  # pragma: no cover - hardware/service failure
        logger.exception("Board repair failed")
        raise HTTPException(status_code=502, detail="board_repair_failed") from exc

    success = report.final_state_verified or (report.issue_detected is False)

    await log_controller_change(
        request,
        request.app.state.drive_root,
        "board_repair_preview" if payload.dry_run else "board_repair_apply",
        {
            "device_id": device_id,
            "dry_run": payload.dry_run,
            "issue_type": report.issue_type,
            "success": success,
            "actions_attempted": report.actions_attempted,
            "actions_successful": report.actions_successful,
            "actions_failed": report.actions_failed,
        },
    )

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
        dry_run=payload.dry_run,
    )


@router.post("/board/firmware/preview", response_model=FirmwarePreviewResponse)
async def controller_firmware_preview(
    request: Request, payload: FirmwarePreviewRequest
) -> FirmwarePreviewResponse:
    """Preview firmware changes without flashing."""
    require_scope(request, "config")
    device_id = require_device_id(request)
    ensure_controller_panel(request.headers.get("x-panel"))

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
    ensure_writes_allowed(request)
    device_id = require_device_id(request)
    ensure_controller_panel(request.headers.get("x-panel"))

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
    rollback_rationale = (
        "No firmware backup artifact is available in the current hardware stub; "
        "use /board/firmware/preview before apply and rely on vendor recovery tooling for rollback."
    )

    await log_controller_change(
        request,
        request.app.state.drive_root,
        "firmware_apply",
        {
            "device_id": device_id,
            "firmware_file": payload.firmware_file,
            "confirm": payload.confirm,
            "success": success,
            "preview_route": "/api/local/controller/board/firmware/preview",
            "rollback_rationale": rollback_rationale,
            "flash_report": flash_payload,
        },
    )

    return FirmwareApplyResponse(
        success=success,
        summary=summary,
        flash_report=flash_payload,
        backup_path=None,
        rollback_rationale=rollback_rationale,
    )


# ---------------------------------------------------------------------------
# Board Mapping Recovery endpoints
# ---------------------------------------------------------------------------

@router.post("/board/mapping/preview", response_model=MappingRecoveryResponse)
async def controller_mapping_preview(
    request: Request, payload: MappingRecoveryRequest
) -> MappingRecoveryResponse:
    """Run a mapping recovery preview (no writes)."""
    require_scope(request, "state")
    device_id = require_device_id(request)
    ensure_controller_panel(request.headers.get("x-panel"))

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
    device_id = require_device_id(request)
    ensure_controller_panel(request.headers.get("x-panel"))

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
    device_id = require_device_id(request)
    ensure_controller_panel(request.headers.get("x-panel"))

    from ..services.controller_shared import log_controller_change

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
        await log_controller_change(
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


# ---------------------------------------------------------------------------
# Device scanning / detection
# ---------------------------------------------------------------------------

@router.get("/devices")
async def get_controller_devices(request: Request) -> Dict[str, Any]:
    """Scan for connected controller/encoder devices.

    Shows all detected USB/HID devices and marks any that have been
    classified as 'arcade_encoder' in the device registry.
    Users can classify devices via /devices/classify endpoint.
    """
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

        try:
            canonical_pacto_boards = [
                board for board in detect_arcade_boards()
                if board.get("detected", True) and _looks_like_pacto_board(board)
            ]
        except Exception as e:
            logger.debug("Could not load canonical Pacto board identities: %s", e)
            canonical_pacto_boards = []

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
        classified_arcade_present = False
        for device in raw_devices:
            device = enrich_with_hints(device)
            device_id = device.get("device_id", "unknown")

            # Check if user has classified this device
            classification = classifications.get(device_id)
            is_encoder = classification and classification.get("role") == "arcade_encoder"
            if is_encoder:
                classified_arcade_present = True

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

        if canonical_pacto_boards and not classified_arcade_present:
            canonical_entries = [
                _canonical_controller_entry(board, idx)
                for idx, board in enumerate(canonical_pacto_boards, start=1)
            ]
            controllers = canonical_entries + controllers

        # Determine overall status
        arcade_boards = [c for c in controllers if c["type"] == "arcade_board"]
        if arcade_boards:
            status = "ok"
            for board in arcade_boards:
                hints.append(f"\u2713 {board['name']} ({board['vid']}:{board['pid']})")
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
async def start_input_detection(
    request: Request,
    board_type: Optional[str] = None,
    learn_mode: bool = False
):
    """Begin listening for encoder inputs."""
    require_scope(request, "state")
    service = get_input_detection_service(request, board_type_override=board_type)
    if learn_mode:
        service.set_learn_mode(True)
    service.start_listening()
    return {
        "status": "listening",
        "board_type": service.board_type,
        "learn_mode": service._learn_mode,
        "message": f"Input detection started{' in learn mode' if learn_mode else ''}.",
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
        "event": serialize_input_event(_latest_input_event),
    }


# ---------------------------------------------------------------------------
# Cabinet Control Status — unified Chuck truth surface
# ---------------------------------------------------------------------------

def _build_usb_descriptor(details: Dict[str, Any], name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Wave 1 #11: when a Pacto-class board has been promoted from a spoofed
    XInput descriptor, expose the underlying USB identity as supporting detail
    so the panel can subordinate it to the friendly board name.

    Wave 2: identity check delegates to ``pacto_identity.is_spoofed_xinput_pacto``.
    """
    if not is_spoofed_xinput_pacto(name, details.get("vid"), details.get("pid")):
        return None
    vid_pid = normalize_vid_pid(details.get("vid"), details.get("pid"))
    return {
        "vid": details.get("vid"),
        "pid": details.get("pid"),
        "vid_pid": vid_pid,
        "product_string": details.get("product_string"),
        "manufacturer_string": details.get("manufacturer_string"),
        "label": "XInput-spoofed USB descriptor",
        "explanation": (
            "Windows sees this board with a Microsoft Xbox VID/PID, but the canonical "
            "hardware lane has promoted it to its real Pacto identity."
        ),
    }


def _probe_live_detection_failure() -> Optional[Dict[str, str]]:
    """Wave 1 #6: classify why live detection returned no boards.

    Called only when ``ControllerAIService.build_context()`` has reported no
    live board. ``detect_arcade_boards()`` is cached, so this re-probe is cheap
    in the common case. Returns ``None`` when detection succeeded but simply
    found no boards (the legitimate "nothing plugged in" path).
    """
    try:
        boards = detect_arcade_boards()
    except USBPermissionError as exc:
        return {
            "code": "usb_permission_denied",
            "title": "USB permission denied",
            "detail": (
                "The OS refused USB access while scanning for encoder boards. "
                f"Run the backend as Administrator (Windows) or fix plugdev membership "
                f"(Linux). Underlying error: {exc}"
            ),
        }
    except USBBackendError as exc:
        return {
            "code": "usb_backend_unavailable",
            "title": "USB backend unavailable",
            "detail": (
                "Chuck cannot talk to a USB backend at all. On Windows, start the backend "
                "via start-gui.bat. On WSL, attach the device with usbipd and install "
                f"libusb. Underlying error: {exc}"
            ),
        }
    except USBDetectionError as exc:
        return {
            "code": "usb_detection_error",
            "title": "USB detection error",
            "detail": f"Detector raised an error during scan: {exc}",
        }
    except Exception as exc:  # pragma: no cover - last-resort visibility
        return {
            "code": "detector_unexpected_exception",
            "title": "Detector failed unexpectedly",
            "detail": f"{type(exc).__name__}: {exc}",
        }

    if not boards:
        return {
            "code": "no_board_present",
            "title": "No encoder board present",
            "detail": (
                "USB scan succeeded but no arcade encoder board is currently visible. "
                "Plug in or repower the board, then click SCAN."
            ),
        }
    return None


def _build_connected_board(
    board_status: Dict[str, Any],
    saved_mapping: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    details = board_status.get("details") or {}
    source = board_status.get("source") or "none"
    detected = bool(board_status.get("detected"))

    configured_board = board_status.get("configured_board") or {}
    override_name = _resolve_user_override_name(configured_board, saved_mapping)

    if source == "canonical_board_lane" and detected:
        name = override_name or details.get("name") or "Encoder board"
        board_source = "user_override" if override_name else "canonical_board_lane"
        payload = {
            "status": "connected",
            "name": name,
            "vid": details.get("vid"),
            "pid": details.get("pid"),
            "manufacturer": details.get("manufacturer"),
            "board_type": details.get("board_type"),
            "source": board_source,
            "summary": (
                f"User-defined hardware profile override: {name}."
                if override_name
                else "Cabinet is reporting a live encoder board on the canonical hardware lane."
            ),
        }
        descriptor = _build_usb_descriptor(details, name)
        if descriptor is not None:
            payload["usb_descriptor"] = descriptor
        return payload
    if source == "configured_mapping" and detected:
        name = override_name or details.get("name") or "Encoder board"
        board_source = "user_override" if override_name else "configured_mapping"
        payload = {
            "status": "connected",
            "name": name,
            "vid": details.get("vid"),
            "pid": details.get("pid"),
            "manufacturer": details.get("manufacturer"),
            "source": board_source,
            "summary": (
                f"User-defined hardware profile override: {name}."
                if override_name
                else "Detected via the saved mapping VID/PID, not the canonical board lane."
            ),
        }
        descriptor = _build_usb_descriptor(details, name)
        if descriptor is not None:
            payload["usb_descriptor"] = descriptor
        return payload

    if override_name:
        return {
            "status": "connected",
            "name": override_name,
            "vid": configured_board.get("vid"),
            "pid": configured_board.get("pid"),
            "source": "user_override",
            "summary": f"User-defined hardware profile override: {override_name}. No live USB confirmation.",
        }

    failure = _probe_live_detection_failure()
    summary = (
        failure["detail"]
        if failure
        else "No live encoder board is reporting on the canonical hardware lane right now."
    )
    return {
        "status": "not_detected",
        "name": None,
        "vid": None,
        "pid": None,
        "source": source,
        "summary": summary,
        "detection_failure": failure,
    }


def _resolve_user_override_name(
    configured_board: Dict[str, Any],
    saved_mapping: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Return the user-defined board name if controls.json has a manual override.

    A manual override is identified by ``detected: false`` plus a non-empty
    ``name`` — the user told us what board this is even though USB didn't
    confirm it.  This is the highest-priority truth in the system.
    """
    if configured_board.get("detected") is False and configured_board.get("name"):
        return configured_board["name"]
    sm_board = (saved_mapping or {}).get("name") if saved_mapping else None
    sm_status = (saved_mapping or {}).get("status")
    if sm_status == "saved" and sm_board and configured_board.get("detected") is False:
        return sm_board
    return None


def _build_saved_mapping(
    board_status: Dict[str, Any],
    mapping_summary: Dict[str, Any],
) -> Dict[str, Any]:
    configured = (
        board_status.get("configured_board")
        or mapping_summary.get("configured_board")
        or mapping_summary.get("board")
        or {}
    )
    has_saved = bool(configured.get("vid") or configured.get("pid") or configured.get("name"))
    metadata = mapping_summary.get("metadata") or {}
    return {
        "status": "saved" if has_saved else "missing",
        "name": configured.get("name"),
        "vid": configured.get("vid"),
        "pid": configured.get("pid"),
        "file_path": "config/mappings/controls.json",
        "last_modified": mapping_summary.get("last_modified"),
        "modified_by": metadata.get("modified_by"),
        "summary": (
            "controls.json identifies this cabinet board."
            if has_saved
            else "No saved controls.json yet — Chuck is running from defaults."
        ),
    }


def _build_runtime_endpoints(
    board_status: Dict[str, Any],
    connected_board: Dict[str, Any],
) -> Dict[str, Any]:
    raw_endpoints = board_status.get("runtime_endpoints") or []
    endpoints = [
        {
            "name": ep.get("name") or ep.get("product") or "Unknown endpoint",
            "vid": ep.get("vid"),
            "pid": ep.get("pid"),
            "profile_id": ep.get("profile_id"),
        }
        for ep in raw_endpoints
        if isinstance(ep, dict)
    ]
    name_blob = " ".join(
        str(connected_board.get(key) or "")
        for key in ("name", "manufacturer", "board_type")
    ).lower()
    is_pacto_live = "pacto" in name_blob

    if endpoints and is_pacto_live:
        explanation = (
            "Windows reports these as generic Xbox 360 controllers, but they are child "
            "endpoints exposed by the Pacto encoder board, not separate gamepads. This is "
            "expected and does not change the cabinet board identity."
        )
    elif endpoints:
        explanation = "Child controller endpoints currently visible to Windows."
    else:
        explanation = "No runtime child controllers are visible right now."

    return {"endpoints": endpoints, "explanation": explanation}


def _build_cascade_payload(drive_root: Path) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "status": "unknown",
        "summary": "Cascade state unavailable.",
    }
    try:
        baseline = load_controller_baseline(drive_root)
    except ControllerBaselineError as exc:
        logger.warning("Cascade baseline unavailable for status endpoint: %s", exc)
        payload["summary"] = f"Baseline unreadable: {exc}"
        return payload
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Unexpected baseline error for status endpoint: %s", exc)
        payload["summary"] = "Baseline aggregation failed."
        return payload

    cascade_state = baseline.get("cascade") or {}
    emulators = baseline.get("emulators") or {}
    led = baseline.get("led") or {}
    emulator_summaries = [
        {
            "name": name,
            "status": (state or {}).get("status", "unknown"),
            "last_synced": (state or {}).get("last_synced"),
        }
        for name, state in sorted(emulators.items())
    ]
    return {
        "status": cascade_state.get("status") or "idle",
        "preference": cascade_state.get("preference"),
        "current_job": cascade_state.get("current_job"),
        "history_count": len(cascade_state.get("history") or []),
        "led": {
            "status": led.get("status") or "unknown",
            "last_synced": led.get("last_synced"),
        },
        "emulators": emulator_summaries,
        "updated_at": baseline.get("updated_at"),
        "summary": (
            f"{len(emulator_summaries)} emulator target(s) tracked. "
            f"LED baseline: {led.get('status') or 'unknown'}."
        ),
    }


def _build_status_warnings(
    connected_board: Dict[str, Any],
    saved_mapping: Dict[str, Any],
    cascade_payload: Dict[str, Any],
    hints: List[str],
) -> List[Dict[str, str]]:
    warnings: List[Dict[str, str]] = []
    has_saved = saved_mapping.get("status") == "saved"

    live_key = normalize_vid_pid(connected_board.get("vid"), connected_board.get("pid"))
    saved_key = normalize_vid_pid(saved_mapping.get("vid"), saved_mapping.get("pid"))

    if connected_board.get("status") == "connected" and has_saved and live_key and saved_key:
        if live_key != saved_key:
            warnings.append({
                "severity": "warning",
                "code": "saved_board_mismatch",
                "title": "Saved mapping board differs from the live board",
                "detail": (
                    f"controls.json identifies '{saved_mapping.get('name') or 'unknown'}' "
                    f"({saved_key}), but the cabinet is reporting "
                    f"'{connected_board.get('name')}' ({live_key}). Save a new mapping or "
                    f"reconnect the expected board."
                ),
            })
        elif (
            saved_mapping.get("name")
            and connected_board.get("name")
            and saved_mapping["name"] != connected_board["name"]
        ):
            warnings.append({
                "severity": "info",
                "code": "saved_board_renamed",
                "title": "Saved board name differs from live board name",
                "detail": (
                    f"Saved as '{saved_mapping['name']}' but cabinet reports "
                    f"'{connected_board['name']}'. VID/PID still match."
                ),
            })

    if connected_board.get("status") != "connected":
        failure = connected_board.get("detection_failure") or {}
        failure_code = failure.get("code") or "no_live_board"
        failure_title = failure.get("title") or "No live encoder board detected"
        failure_detail = failure.get("detail")
        if not failure_detail:
            failure_detail = (
                "Chuck is falling back to the saved mapping. Reconnect or repower the "
                "encoder board, then click SCAN."
                if has_saved
                else "Chuck cannot find a live board and there is no saved mapping yet."
            )
        warnings.append({
            "severity": "warning" if (has_saved or failure_code != "no_board_present") else "info",
            "code": failure_code,
            "title": failure_title,
            "detail": failure_detail,
        })

    cascade_status = str(cascade_payload.get("status") or "").lower()
    if cascade_status in {"failed", "error", "stale"}:
        warnings.append({
            "severity": "warning",
            "code": "cascade_attention",
            "title": f"Cascade status: {cascade_status}",
            "detail": cascade_payload.get("summary")
            or "Re-run cascade to sync downstream targets.",
        })

    seen_details = {w["detail"] for w in warnings}
    for hint in (hints or [])[:5]:
        if hint and hint not in seen_details:
            warnings.append({
                "severity": "info",
                "code": "hint",
                "title": "Detail",
                "detail": hint,
            })

    return warnings


@router.get("/status")
async def cabinet_control_status(request: Request) -> Dict[str, Any]:
    """Cabinet Control Status — unified Chuck truth surface.

    Reconciles four competing truths into one user-facing payload:
      1. live encoder board (canonical lane)
      2. saved mapping board (controls.json)
      3. runtime child endpoints (HID/XInput)
      4. cascade/sync state
    Plus explicit drift warnings.

    Read-only. Reuses ``ControllerAIService.build_context()`` so no new
    detection logic exists here.
    """
    require_scope(request, "state")
    drive_root: Path = request.app.state.drive_root

    try:
        ai_service = get_controller_ai_service()
        ctx = ai_service.build_context(drive_root)
    except Exception as exc:
        logger.exception("Failed to build Chuck status context")
        raise HTTPException(status_code=500, detail=f"status_failed: {exc}") from exc

    board_status = ctx.board_status or {}
    mapping_summary = ctx.mapping_summary or {}

    saved_mapping = _build_saved_mapping(board_status, mapping_summary)
    connected_board = _build_connected_board(board_status, saved_mapping)
    runtime = _build_runtime_endpoints(board_status, connected_board)
    cascade_payload = _build_cascade_payload(drive_root)
    warnings = _build_status_warnings(
        connected_board=connected_board,
        saved_mapping=saved_mapping,
        cascade_payload=cascade_payload,
        hints=ctx.hints or [],
    )

    return {
        "timestamp": ctx.timestamp,
        "connected_board": connected_board,
        "saved_mapping": saved_mapping,
        "runtime": runtime,
        "cascade": cascade_payload,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Refresh / Health
# ---------------------------------------------------------------------------

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


@router.post("/api/local/hardware/apply-config")
async def apply_config(request: Request):
    """
    Safety Pipeline: Backup -> Write -> Log.
    Never overwrites a config file silently.
    Accepts a JSON body with:
      - target_path: absolute path to the config file to write
      - content: the new file content as a string
    """
    try:
        body = await request.json()
        target_path = body.get("target_path")
        content = body.get("content")

        if not target_path or content is None:
            raise HTTPException(
                status_code=400,
                detail="target_path and content are required."
            )

        target = Path(target_path)

        if not await run_in_threadpool(target.parent.exists):
            raise HTTPException(
                status_code=400,
                detail=f"Target directory does not exist: {target.parent}"
            )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = target.parent / "backups" / timestamp
        await run_in_threadpool(backup_dir.mkdir, parents=True, exist_ok=True)

        target_exists = await run_in_threadpool(target.exists)
        backup_path = backup_dir / target.name

        if target_exists:
            await run_in_threadpool(shutil.copy2, str(target), str(backup_path))

        await run_in_threadpool(target.write_text, content, encoding="utf-8")

        log_path = target.parent / "tool_executor.log"
        log_entry = (
            f"[{timestamp}] APPLY-CONFIG | "
            f"file={target.name} | "
            f"backup={backup_path if target_exists else 'none'} | "
            f"chars={len(content)}\n"
        )

        def _append_log() -> None:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(log_entry)

        await run_in_threadpool(_append_log)

        return {
            "success": True,
            "target": str(target),
            "backup": str(backup_path) if target_exists else None,
            "timestamp": timestamp,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Safety pipeline failed: {str(e)}"
        )
