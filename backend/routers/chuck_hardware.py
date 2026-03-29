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
from ..services.device_scanner import scan_devices
from ..services.encoder_hints import enrich_with_hints
from ..services import device_registry
from ..services.firmware_manager import FirmwareManager
from ..services.mapping_recovery import MappingRecoveryService
from ..services.chuck.detection import (
    BoardDetectionError,
    BoardNotFoundError,
    get_detection_service,
)
from ..services.chuck.input_detector import InputDetectionService, InputEvent
from ..services.chuck.pactotech import PactoTechBoard
from ..services.policies import require_scope
from ..services.usb_detector import (
    USBBackendError,
    USBDetectionError,
    USBPermissionError,
    get_board_by_vid_pid,
)
from ..services.controller_shared import (
    ensure_writes_allowed,
    require_device_id,
    ensure_controller_panel,
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


def get_latest_event() -> Optional[InputEvent]:
    """Get the most recent input event captured by the service."""
    return _latest_input_event


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
    device_id = require_device_id(request)
    ensure_controller_panel(request.headers.get("x-panel"))

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
    return FirmwareApplyResponse(
        success=success,
        summary=summary,
        flash_report=flash_payload,
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
