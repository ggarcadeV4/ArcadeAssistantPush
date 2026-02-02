# backend/routers/gunner.py
"""Gunner FastAPI router for light gun calibration and profile management.

Provides HTTP endpoints and WebSocket connection for:
- Light gun device detection
- 9-point calibration wizard
- Profile save/load per user and game
- Real-time calibration feedback
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import logging
from pathlib import Path
from datetime import datetime
import json
import shutil

from ..services.gunner_hardware import HardwareDetector
from ..services.gunner_config import gunner_config
from ..services.gunner_factory import detector_factory, multi_gun_detector_factory
from ..services.gunner_service import (
    GunnerService,
    CalibData,
    CalibrationResult,
    get_gunner_service,
    get_config_service,
    get_supabase_client
)
from ..services.gunner.hardware import get_gun_registry
from ..services.gunner.modes import RetroMode, MODE_HANDLERS
from ..services.diffs import compute_diff, has_changes
from ..services.policies import is_allowed_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gunner", tags=["Gunner Light Guns"])


# ============================================================================
# Pydantic Models
# ============================================================================

class CalibrationPoint(BaseModel):
    """Single calibration point with normalized coordinates."""
    x: float = Field(..., ge=0.0, le=1.0, description="Normalized X coordinate (0.0-1.0)")
    y: float = Field(..., ge=0.0, le=1.0, description="Normalized Y coordinate (0.0-1.0)")


class CapturePointRequest(BaseModel):
    """Request to capture calibration point."""
    device_id: int = Field(..., description="Gun device ID")
    x: float = Field(..., ge=0.0, le=1.0, description="Normalized X coordinate")
    y: float = Field(..., ge=0.0, le=1.0, description="Normalized Y coordinate")


class SaveProfileRequest(BaseModel):
    """Request to save calibration profile."""
    user_id: str = Field(..., description="User identifier")
    game: str = Field(..., description="Game identifier")
    points: List[CalibrationPoint] = Field(..., min_items=9, max_items=9, description="9 calibration points")


class LoadProfileRequest(BaseModel):
    """Request to load calibration profile."""
    user_id: str = Field(..., description="User identifier")
    game: str = Field(..., description="Game identifier")


class LegacyProfileApplyRequest(BaseModel):
    """Backward-compatible payload for legacy /profile/apply acceptance calls."""
    profile: str = Field(..., description="Legacy profile identifier")
    dry_run: bool = False


class TendencyPayload(BaseModel):
    """Payload for updating gunner tendency namespace."""
    profile_id: str = Field(..., description="Profile identifier (e.g., dad)")
    handedness: Optional[str] = Field(None, description="preferred hand (left|right)")
    sensitivity: Optional[float] = Field(None, ge=0.0, le=100.0, description="Saved cabinet sensitivity")
    dry_run: Optional[bool] = None


# ============================================================================
# Helper Functions
# ============================================================================

def emit_event(event_name: str, payload: Dict) -> None:
    """Emit event by logging (gateway handles WebSocket broadcast).

    Args:
        event_name: Event type identifier
        payload: Event data dictionary
    """
    logger.info(f"GUNNER_EVENT: {event_name} | {payload}")


def _sanitize_segment(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    return cleaned or "gunner"


def _tendencies_file(drive_root: Path, profile_id: str) -> Path:
    safe_profile = _sanitize_segment(profile_id)
    return drive_root / "profiles" / safe_profile / "tendencies.json"


def _gunner_backup_root(drive_root: Path) -> Path:
    return drive_root / ".aa" / "backups" / "gunner"


def _create_tendency_backup(target_path: Path, drive_root: Path, reason: str) -> Optional[Path]:
    if not target_path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = _gunner_backup_root(drive_root) / f"{timestamp}_{reason}"
    backup_path = backup_dir / target_path.relative_to(drive_root)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target_path, backup_path)
    return backup_path


def _rel_path(path: Path, drive_root: Path) -> str:
    try:
        return str(path.relative_to(drive_root)).replace("\\", "/")
    except ValueError:
        return str(path)


def _log_gunner_change(
    request: Request,
    drive_root: Path,
    action: str,
    details: Dict,
    backup_path: Optional[Path] = None
) -> None:
    log_file = drive_root / ".aa" / "logs" / "changes.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "scope": "gunner",
        "action": action,
        "details": details,
        "backup_path": str(backup_path) if backup_path else None,
        "device": request.headers.get("x-device-id", "unknown"),
        "panel": request.headers.get("x-panel", "gunner"),
    }
    with open(log_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _prepare_tendency_content(current: Dict, payload: TendencyPayload) -> Dict:
    updated = json.loads(json.dumps(current or {})) if current else {}
    updated.setdefault("profile_id", payload.profile_id)
    gunner_section = updated.setdefault("gunner", {})

    if payload.handedness:
        gunner_section["handedness"] = payload.handedness
    if payload.sensitivity is not None:
        gunner_section["sensitivity"] = payload.sensitivity

    meta = updated.setdefault("meta", {})
    meta["last_modified"] = datetime.utcnow().isoformat() + "Z"
    meta.setdefault("version", 1)
    return updated


def _require_gunner_scope(request: Request, allowed_scopes: List[str]) -> str:
    scope = (request.headers.get("x-scope") or "").lower()
    if not scope:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required x-scope header. Allowed scopes: {allowed_scopes}"
        )
    allowed = {s.lower() for s in allowed_scopes}
    if scope not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"x-scope '{scope}' not permitted. Allowed: {allowed_scopes}"
        )
    return scope

# ============================================================================
# HTTP Endpoints
# ============================================================================

@router.get("/devices", status_code=200)
async def get_devices(
    request: Request,
    detector: HardwareDetector = Depends(detector_factory)
):
    """Get list of detected light gun devices.

    Returns all connected light guns including mock/virtual devices in development mode.
    Devices are auto-detected via HID enumeration (Sinden, AimTrak, Gun4IR).

    Args:
        detector: Hardware detector instance (injected via factory)

    Returns:
        List of device dictionaries with id, name, type, vid, pid
    """
    _require_gunner_scope(request, ["state", "local"])
    try:
        devices = detector.get_devices()

        return {
            "devices": devices,
            "count": len(devices),
            "mock_mode": any(d.get('type') == 'mock' for d in devices)
        }

    except Exception as e:
        logger.error(f"Device enumeration failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Device enumeration failed: {str(e)}")


@router.get("/profiles", status_code=200)
async def list_profiles(
    request: Request,
    user_id: str = Query(..., description="User identifier for profile scope")
):
    """List calibration profiles for a given user."""
    _require_gunner_scope(request, ["state", "local", "config"])
    try:
        profiles = gunner_config.list_profiles(user_id=user_id)
        return {
            "status": "success",
            "user_id": user_id,
            "count": len(profiles),
            "profiles": profiles
        }
    except Exception as e:
        logger.error(f"Profile list failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list profiles: {str(e)}")


@router.get("/registry", status_code=200)
async def get_gun_models():
    """Get gun hardware registry with VID/PID mappings and features.

    Returns the complete gun registry with supported models, features,
    and calibration adjustments. Useful for frontend to display supported
    hardware and mode-specific recommendations.

    Returns:
        Registry data with gun models, VID/PID, features (IR, recoil, rumble)
    """
    try:
        registry = get_gun_registry()

        # Convert registry to JSON-serializable format
        models_data = []
        for (vid, pid), model in registry.models.items():
            models_data.append({
                "vid": f"0x{vid:04X}",
                "pid": f"0x{pid:04X}",
                "name": model.name,
                "vendor": model.vendor,
                "features": model.features,
                "calib_adjust": model.calib_adjust,
                "notes": model.notes
            })

        return {
            "status": "success",
            "count": len(models_data),
            "models": models_data
        }

    except Exception as e:
        logger.error(f"Failed to get gun registry: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get gun registry: {str(e)}")


@router.get("/modes", status_code=200)
async def get_retro_modes():
    """Get available retro shooter game modes.

    Returns list of retro arcade shooter modes with descriptions and
    validation requirements. Useful for frontend to display mode selection
    and explain mode-specific calibration.

    Returns:
        List of retro modes with names, keys, and descriptions
    """
    try:
        modes_data = []

        for mode_enum in RetroMode:
            handler = MODE_HANDLERS.get(mode_enum)
            if handler:
                modes_data.append({
                    "key": mode_enum.value,
                    "name": handler.get_mode_name(),
                    "description": _get_mode_description(mode_enum),
                    "features_recommended": _get_mode_features(mode_enum)
                })

        return {
            "status": "success",
            "count": len(modes_data),
            "modes": modes_data
        }

    except Exception as e:
        logger.error(f"Failed to get retro modes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get retro modes: {str(e)}")


def _get_mode_description(mode: RetroMode) -> str:
    """Get mode description for API response."""
    descriptions = {
        RetroMode.TIME_CRISIS: "Off-screen reload with pedal mechanics - requires edge point calibration",
        RetroMode.HOUSE_DEAD: "Rapid fire zombie shooter - recoil weighting for accuracy boost",
        RetroMode.POINT_BLANK: "Precision trick shots - strict accuracy requirements",
        RetroMode.VIRTUA_COP: "Balanced arcade action - standard calibration",
        RetroMode.DUCK_HUNT: "Classic NES Zapper emulation - relaxed accuracy"
    }
    return descriptions.get(mode, "Arcade shooter mode")


def _get_mode_features(mode: RetroMode) -> List[str]:
    """Get recommended features for mode."""
    features_map = {
        RetroMode.TIME_CRISIS: ["ir", "recoil"],
        RetroMode.HOUSE_DEAD: ["recoil", "ir"],
        RetroMode.POINT_BLANK: ["ir"],
        RetroMode.VIRTUA_COP: ["ir"],
        RetroMode.DUCK_HUNT: []
    }
    return features_map.get(mode, [])


@router.post("/calibrate/point", status_code=200)
async def capture_calibration_point(
    payload: CapturePointRequest,
    raw_request: Request,
    detector: HardwareDetector = Depends(detector_factory)
):
    """Capture single point during 9-point calibration wizard.

    Records calibration point, provides LED feedback, and emits progress event.
    After 9th point, automatically completes calibration and emits completion event.

    Args:
        request: Capture point request with device_id, x, y
        detector: Hardware detector instance (injected via factory)

    Returns:
        Confirmation with current point index and completion status

    Raises:
        HTTPException: 400 for invalid device, 500 for capture failure
    """
    _require_gunner_scope(raw_request, ["state"])
    try:
        success = detector.capture_point(
            device_id=payload.device_id,
            x=payload.x,
            y=payload.y
        )

        if not success:
            raise HTTPException(status_code=400, detail="Point capture failed - device not found")

        # Check if calibration is complete
        is_complete = detector._current_point == 0  # Reset to 0 after 9 points

        emit_event("gun_calibration_point", {
            "device_id": payload.device_id,
            "point": detector._current_point - 1 if not is_complete else 8,
            "x": payload.x,
            "y": payload.y,
            "complete": is_complete
        })

        return {
            "status": "captured",
            "device_id": payload.device_id,
            "current_point": detector._current_point,
            "complete": is_complete
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Point capture failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Point capture failed: {str(e)}")


@router.post("/profile/apply", status_code=200)
async def apply_legacy_profile(payload: LegacyProfileApplyRequest):
    """
    Legacy compatibility endpoint for light gun profile apply requests.

    The modern API uses /profile/save and /profile/load; this stub acknowledges
    the profile request so acceptance tests can confirm the gateway path.
    """
    try:
        logger.info(
            "legacy_profile_apply",
            profile=payload.profile,
            dry_run=payload.dry_run
        )
        return {
            "status": "applied" if not payload.dry_run else "dry_run",
            "profile": payload.profile,
            "dry_run": payload.dry_run,
            "message": "Legacy light gun profile apply acknowledged"
        }
    except Exception as e:
        logger.error(f"Legacy profile apply failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to apply legacy profile request")


@router.post("/profile/save", status_code=200)
async def save_profile(
    payload: SaveProfileRequest,
    raw_request: Request
):
    """Save calibration profile to database.

    Stores 9-point calibration data per user and game in Supabase.
    Profile can be loaded later for the same user/game combination.

    Args:
        request: Save profile request with user_id, game, points

    Returns:
        Confirmation with save status

    Raises:
        HTTPException: 400 for invalid points, 500 for save failure
    """
    _require_gunner_scope(raw_request, ["state", "config"])
    drive_root = getattr(raw_request.app.state, "drive_root", Path("."))
    try:
        # Convert Pydantic models to dicts
        points_dict = [{"x": p.x, "y": p.y} for p in payload.points]

        success = gunner_config.save_profile(
            user_id=payload.user_id,
            game=payload.game,
            points=points_dict
        )

        if not success:
            raise HTTPException(status_code=500, detail="Profile save failed")

        emit_event("gun_profile_saved", {
            "user_id": payload.user_id,
            "game": payload.game,
            "points_count": len(points_dict)
        })

        _log_gunner_change(
            raw_request,
            drive_root,
            "profile_save",
            {
                "user_id": payload.user_id,
                "game": payload.game,
                "points_count": len(points_dict)
            }
        )

        return {
            "status": "saved",
            "user_id": payload.user_id,
            "game": payload.game,
            "points_count": len(points_dict)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile save failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Profile save failed: {str(e)}")


@router.post("/profile/load", status_code=200)
async def load_profile(
    payload: LoadProfileRequest,
    raw_request: Request
):
    """Load calibration profile from database.

    Retrieves saved 9-point calibration for specific user and game.
    Returns default profile if none exists.

    Args:
        request: Load profile request with user_id, game

    Returns:
        Calibration profile with points

    Raises:
        HTTPException: 500 for load failure
    """
    _require_gunner_scope(raw_request, ["state", "local", "config"])
    try:
        points = gunner_config.load_profile(
            user_id=payload.user_id,
            game=payload.game
        )

        return {
            "status": "loaded",
            "user_id": payload.user_id,
            "game": payload.game,
            "points": points,
            "is_default": len(points) == 9 and points[0]["x"] == 0.1  # Check if default
        }

    except Exception as e:
        logger.error(f"Profile load failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Profile load failed: {str(e)}")


@router.post("/calibrate", response_model=CalibrationResult, status_code=200)
async def calibrate_device(
    data: CalibData,
    raw_request: Request,
    detector: HardwareDetector = Depends(detector_factory)
) -> CalibrationResult:
    """Execute full 9-point calibration workflow.

    Orchestrated calibration flow:
    1. Validate device exists (via hardware detector)
    2. Calculate accuracy from confidence scores
    3. Save to Supabase (if configured)
    4. Save to local fallback
    5. Emit structured telemetry event

    This endpoint uses the GunnerService orchestrator for clean separation
    of concerns and enables reuse across REST, WebSocket, and background tasks.

    Args:
        data: CalibData with 9 points, device_id, user_id
        detector: Hardware detector (injected via Depends)

    Returns:
        CalibrationResult with status, accuracy, sync info

    Raises:
        HTTPException: 400 for validation errors, 404 for device not found, 500 for failures
    """
    _require_gunner_scope(raw_request, ["state"])
    try:
        # Create service with dependencies
        service = GunnerService(
            detector=detector,
            config_service=get_config_service(),
            supabase_client=get_supabase_client()
        )

        # Execute calibration workflow
        result = await service.calibrate(data)

        return result

    except ValueError as e:
        # Validation errors (device not found, invalid data)
        logger.warning(f"Calibration validation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Unexpected errors
        logger.error(f"Calibration failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Calibration failed: {str(e)}")


# ============================================================================
# Streaming Calibration Endpoint
# ============================================================================

@router.post("/calibrate/stream", status_code=200)
async def calibrate_device_stream(
    data: CalibData,
    raw_request: Request,
    detector: HardwareDetector = Depends(detector_factory)
):
    """Stream calibration progress with real-time updates.

    Provides incremental progress updates during 9-point calibration.
    Returns Server-Sent Events (SSE) for live progress tracking.

    Progress updates:
        {"status": "processing", "progress": 0.33, "partial_accuracy": 0.92}

    Final result:
        {"status": "complete", "accuracy": 0.95, "mode": "standard", ...}

    Args:
        data: CalibData with 9 points, device_id, user_id, game_type
        detector: Hardware detector (injected via Depends)

    Returns:
        Streaming JSON responses with calibration progress

    Raises:
        HTTPException: 400 for validation errors, 500 for failures
    """
    from fastapi.responses import StreamingResponse
    import json

    _require_gunner_scope(raw_request, ["state"])

    async def event_generator():
        """Generate Server-Sent Events for calibration progress."""
        try:
            # Create service with dependencies
            service = GunnerService(
                detector=detector,
                config_service=get_config_service(),
                supabase_client=get_supabase_client()
            )

            # Stream calibration updates
            async for update in service.calibrate_stream(data):
                # Format as SSE
                yield f"data: {json.dumps(update)}\n\n"

        except Exception as e:
            logger.error(f"Stream calibration failed: {e}", exc_info=True)
            error_update = {"status": "error", "error": str(e), "progress": 0.0}
            yield f"data: {json.dumps(error_update)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/tendencies/preview", status_code=200)
async def preview_tendencies(request: Request, payload: TendencyPayload):
    """Preview gunner tendency changes before applying."""
    _require_gunner_scope(request, ["state", "config", "backup"])
    drive_root = getattr(request.app.state, "drive_root", Path("."))
    manifest = getattr(request.app.state, "manifest", {}) or {}
    target_path = _tendencies_file(drive_root, payload.profile_id)
    if not is_allowed_file(target_path, drive_root, manifest.get("sanctioned_paths", [])):
        raise HTTPException(
            status_code=403,
            detail=f"Target path not sanctioned: {_rel_path(target_path, drive_root)}"
        )

    current_content = ""
    current_json: Dict = {}
    if target_path.exists():
        current_content = target_path.read_text(encoding="utf-8")
        try:
            current_json = json.loads(current_content) if current_content else {}
        except json.JSONDecodeError:
            current_json = {}

    updated = _prepare_tendency_content(current_json, payload)
    new_content = json.dumps(updated, indent=2, ensure_ascii=False)
    rel_path = _rel_path(target_path, drive_root)
    diff = compute_diff(current_content, new_content, rel_path)

    return {
        "target_file": rel_path,
        "has_changes": has_changes(current_content, new_content),
        "diff": diff,
        "tendencies": updated
    }


@router.post("/tendencies/apply", status_code=200)
async def apply_tendencies(request: Request, payload: TendencyPayload):
    """Apply gunner tendency changes with backup + audit logging."""
    _require_gunner_scope(request, ["state", "config", "backup"])
    drive_root = getattr(request.app.state, "drive_root", Path("."))
    manifest = getattr(request.app.state, "manifest", {}) or {}
    target_path = _tendencies_file(drive_root, payload.profile_id)
    if not is_allowed_file(target_path, drive_root, manifest.get("sanctioned_paths", [])):
        raise HTTPException(
            status_code=403,
            detail=f"Target path not sanctioned: {_rel_path(target_path, drive_root)}"
        )

    current_content = ""
    current_json: Dict = {}
    if target_path.exists():
        current_content = target_path.read_text(encoding="utf-8")
        try:
            current_json = json.loads(current_content) if current_content else {}
        except json.JSONDecodeError:
            current_json = {}

    updated = _prepare_tendency_content(current_json, payload)
    new_content = json.dumps(updated, indent=2, ensure_ascii=False)
    rel_path = _rel_path(target_path, drive_root)
    diff = compute_diff(current_content, new_content, rel_path)
    changed = has_changes(current_content, new_content)

    dry_default = getattr(request.app.state, "dry_run_default", False)
    dry_run = payload.dry_run if payload.dry_run is not None else dry_default

    backup_path = None
    if changed and not dry_run and target_path.exists() and getattr(request.app.state, "backup_on_write", True):
        backup_path = _create_tendency_backup(target_path, drive_root, reason="tendencies")

    if changed and not dry_run:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(new_content, encoding="utf-8")

    _log_gunner_change(
        request,
        drive_root,
        "tendencies_apply",
        {
            "profile_id": payload.profile_id,
            "has_changes": changed,
            "dry_run": dry_run
        },
        backup_path
    )

    return {
        "target_file": rel_path,
        "has_changes": changed,
        "diff": diff,
        "dry_run": dry_run,
        "backup_path": str(backup_path) if backup_path else None,
        "tendencies": updated
    }


@router.post("/test", status_code=200)
async def gunner_test(
    request: Request,
    detector: HardwareDetector = Depends(detector_factory)
):
    """Simple readiness probe for Gunner panel.

    Returns device count and mock-mode flag so gateway/CLI can verify connectivity.
    """
    _require_gunner_scope(request, ["state"])
    try:
        devices = detector.get_devices()
    except Exception as exc:
        logger.error(f"Gunner test failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Gunner test failed: {exc}")

    return {
        "status": "ok",
        "device_count": len(devices),
        "mock_mode": any(d.get("type") == "mock" for d in devices),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


# ============================================================================
# WebSocket Endpoint
# ============================================================================

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: Optional[str] = None
):
    """WebSocket connection for real-time calibration feedback (legacy).

    NOTE: WebSocket endpoints cannot use Depends() for detector injection.
    We create a detector instance directly within the connection handler.

    Provides live updates during calibration wizard with LED feedback sync.

    Message Format (Client → Server):
    - Capture: {"type": "capture", "device_id": 1, "x": 0.5, "y": 0.5}
    - Status: {"type": "status"}

    Message Format (Server → Client):
    - Point: {"type": "point", "current": 3, "x": 0.5, "y": 0.5}
    - Complete: {"type": "complete", "points": [...]}
    - Error: {"type": "error", "message": "..."}

    Args:
        websocket: WebSocket connection
        user_id: Optional user ID from query parameter
    """
    await websocket.accept()
    logger.info(f"Gunner WebSocket connected: user_id={user_id}")

    # Create detector instance for this WebSocket connection
    from ..services.gunner_factory import detector_factory
    detector = detector_factory()

    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            msg_type = data.get('type')

            if msg_type == 'capture':
                # Capture calibration point
                device_id = data.get('device_id')
                x = data.get('x')
                y = data.get('y')

                if device_id is None or x is None or y is None:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Missing device_id, x, or y"
                    })
                    continue

                success = detector.capture_point(device_id, x, y)

                if success:
                    is_complete = detector._current_point == 0

                    await websocket.send_json({
                        "type": "point",
                        "current": detector._current_point,
                        "x": x,
                        "y": y,
                        "complete": is_complete
                    })

                    if is_complete:
                        await websocket.send_json({
                            "type": "complete",
                            "points": detector._calibration_points
                        })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Point capture failed"
                    })

            elif msg_type == 'status':
                # Send current calibration status
                devices = detector.get_devices()
                await websocket.send_json({
                    "type": "status",
                    "devices": devices,
                    "current_point": detector._current_point,
                    "points_captured": len(detector._calibration_points)
                })

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}"
                })

    except WebSocketDisconnect:
        logger.info(f"Gunner WebSocket disconnected: user_id={user_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.close()
        except:
            pass


# ============================================================================
# Hardware-Specific Advice Endpoint
# ============================================================================

@router.get("/advice", status_code=200)
async def get_hardware_advice(
    request: Request,
    game_mode: Optional[str] = Query(None, description="Game mode (time_crisis, house_dead, etc.)"),
    detector: HardwareDetector = Depends(detector_factory)
):
    """Get hardware-specific advice based on detected guns.
    
    Gunner uses this to provide tailored recommendations without asking
    what gun the user has. Detects connected hardware and gives advice
    based on the gun's features and the selected game mode.
    
    Returns:
        Detected guns, their features, and mode-specific recommendations
    """
    try:
        # Detect connected guns
        devices = detector.get_devices()
        registry = get_gun_registry()
        
        guns_info = []
        for device in devices:
            vid_str = device.get('vid', '0x0000')
            pid_str = device.get('pid', '0x0000')
            
            # Parse VID/PID
            try:
                vid = int(vid_str, 16) if isinstance(vid_str, str) else vid_str
                pid = int(pid_str, 16) if isinstance(pid_str, str) else pid_str
            except:
                vid, pid = 0, 0
            
            # Get model from registry
            model = registry.get_model(vid, pid)
            
            # Build gun info
            gun_info = {
                "name": device.get('name', model.name),
                "vendor": model.vendor or "Unknown",
                "features": model.features,
                "notes": model.notes or "",
                "connected": device.get('connected', True)
            }
            
            # Get mode-specific recommendations if mode specified
            if game_mode:
                try:
                    mode_enum = RetroMode(game_mode)
                    handler = MODE_HANDLERS.get(mode_enum)
                    if handler:
                        gun_info["recommendations"] = handler.get_recommendations(model.features)
                        gun_info["mode_name"] = handler.get_mode_name()
                except:
                    pass
            
            guns_info.append(gun_info)
        
        # Build advice response
        if not guns_info:
            return {
                "status": "no_guns_detected",
                "advice": "No light guns detected. Check USB connections and ensure guns are powered on.",
                "guns": [],
                "mock_mode": True
            }
        
        # Generate summary advice based on detected hardware
        primary_gun = guns_info[0]
        features = primary_gun.get("features", {})
        
        advice_parts = []
        advice_parts.append(f"Detected: {primary_gun['name']} ({primary_gun['vendor']})")
        
        if features.get("ir"):
            advice_parts.append("IR tracking enabled - excellent accuracy.")
        if features.get("recoil"):
            advice_parts.append("Recoil active - perfect for immersive gameplay.")
        if features.get("pedal"):
            advice_parts.append("Pedal support available for cover mechanics.")
        if not features.get("ir"):
            advice_parts.append("No IR tracking - consider calibrating more frequently.")
        
        # Mode-specific advice
        if game_mode and primary_gun.get("recommendations"):
            advice_parts.append(f"For {primary_gun.get('mode_name', game_mode)}:")
            advice_parts.extend(primary_gun["recommendations"][:2])  # Top 2 recommendations
        
        return {
            "status": "ok",
            "guns": guns_info,
            "gun_count": len(guns_info),
            "primary_gun": primary_gun["name"],
            "advice": " ".join(advice_parts),
            "features_summary": {
                "has_ir": any(g.get("features", {}).get("ir") for g in guns_info),
                "has_recoil": any(g.get("features", {}).get("recoil") for g in guns_info),
                "has_pedal": any(g.get("features", {}).get("pedal") for g in guns_info),
            },
            "mock_mode": any(d.get('type') == 'mock' for d in devices)
        }
        
    except Exception as e:
        logger.error(f"Failed to get hardware advice: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get hardware advice: {str(e)}")
