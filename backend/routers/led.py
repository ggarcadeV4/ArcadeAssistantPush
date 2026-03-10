"""LED profile preview/apply endpoints backed by Controller Chucks mappings."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..constants.paths import Paths
from ..services.blinky_service import BlinkyProcessManager, BlinkyService
from ..services.launchbox_parser import parser
from ..services.led_calibration_service import LEDCalibrationService
from ..services.led_engine import get_led_engine
from ..services.led_engine.led_channel_mapping_service import LEDChannelMappingService
from ..services.led_engine.state import LEDChannelAssignment
from ..services.led_engine.ws_protocol import InvalidLEDMessage, parse_ws_message
from ..services.led_game_profiles import LEDGameProfileStore
from ..services.led_mapping_service import LEDMappingService
from ..services.policies import require_scope
from ..services.supabase_client import send_telemetry as sb_send_telemetry

router = APIRouter()
logger = logging.getLogger(__name__)

WS_REGISTRY_ATTR = "_led_ws_registry"


def _ws_registry(app_state) -> Dict[str, Any]:
    registry = getattr(app_state, WS_REGISTRY_ATTR, None)
    if registry is None:
        registry = {"clients": {}}
        setattr(app_state, WS_REGISTRY_ATTR, registry)
    return registry


def _register_ws_client(app_state, connection_id: str, websocket: WebSocket) -> None:
    registry = _ws_registry(app_state)
    client_meta = {
        "id": connection_id,
        "connected_at": datetime.utcnow().isoformat(),
        "client": getattr(websocket.client, "host", "unknown"),
        "port": getattr(websocket.client, "port", None),
        "headers": {
            "x-panel": websocket.headers.get("x-panel"),
            "x-device-id": websocket.headers.get("x-device-id"),
        },
    }
    registry["clients"][connection_id] = client_meta


def _remove_ws_client(app_state, connection_id: str) -> None:
    registry = _ws_registry(app_state)
    registry["clients"].pop(connection_id, None)


class LEDButtonSetting(BaseModel):
    model_config = ConfigDict(extra="allow")

    color: str = Field(..., description="Hex color code such as #FFAA00")
    pattern: Optional[str] = Field(default=None, description="Optional animation pattern")
    brightness: Optional[int] = Field(default=None, ge=0, le=100)

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("color must be a non-empty string")
        return value


class LEDProfilePayload(BaseModel):
    profile_name: str = Field(..., min_length=1, max_length=120)
    scope: str = Field(default="default")
    game: Optional[str] = None
    buttons: Dict[str, LEDButtonSetting]
    animation: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("buttons")
    @classmethod
    def validate_buttons(cls, value: Dict[str, LEDButtonSetting]) -> Dict[str, LEDButtonSetting]:
        if not value:
            raise ValueError("buttons payload cannot be empty")
        return value


class LEDProfileApplyRequest(LEDProfilePayload):
    dry_run: Optional[bool] = Field(
        default=None,
        description="Override dry-run default from server configuration",
    )


class LEDChannelModel(BaseModel):
    logical_button: str
    device_id: str
    channel_index: int
    label: Optional[str] = None
    vendor_id: Optional[str] = None
    product_id: Optional[str] = None
    board_name: Optional[str] = None


class LEDResolvedButton(BaseModel):
    logical_button: str
    settings: Dict[str, Any]
    channels: List[LEDChannelModel]


class LEDPreviewResponse(BaseModel):
    profile_name: str
    scope: str
    game: Optional[str]
    metadata: Dict[str, Any]
    buttons: Dict[str, LEDButtonSetting]
    resolved_buttons: List[LEDResolvedButton]
    missing_buttons: List[str]
    board: Dict[str, Any]
    target_file: str
    total_channels: int
    diff: str
    has_changes: bool


class LEDProfileApplyResponse(BaseModel):
    status: str
    dry_run: bool
    target_file: str
    backup_path: Optional[str]
    preview: LEDPreviewResponse


class LEDChannelEntry(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=120)
    channel: int = Field(..., ge=1, le=2048)


class LEDChannelUpdatePayload(LEDChannelEntry):
    logical_button: str = Field(..., min_length=2, max_length=64)


class LEDChannelMappingPayload(BaseModel):
    channels: Optional[Dict[str, LEDChannelEntry]] = None
    updates: List[LEDChannelUpdatePayload] = Field(default_factory=list)


class LEDChannelMappingApplyPayload(LEDChannelMappingPayload):
    dry_run: Optional[bool] = Field(
        default=None,
        description="Override dry-run default for channel writes",
    )


class LEDChannelPreviewResponse(BaseModel):
    target_file: str
    diff: str
    has_changes: bool
    total_channels: int
    channels: Dict[str, LEDChannelEntry]
    unmapped: List[str]
    unknown_logical: List[str]


class LEDChannelStateResponse(BaseModel):
    target_file: str
    total_channels: int
    channels: Dict[str, LEDChannelEntry]
    unmapped: List[str]
    unknown_logical: List[str]


class LEDChannelApplyResponse(BaseModel):
    status: str
    dry_run: bool
    target_file: str
    backup_path: Optional[str]
    preview: LEDChannelPreviewResponse


class LEDChannelDeleteResponse(BaseModel):
    status: str
    dry_run: bool
    target_file: str
    backup_path: Optional[str]
    preview: LEDChannelPreviewResponse


class LEDCalibrationStartResponse(BaseModel):
    status: str
    token: str
    started_at: datetime


class LEDCalibrationAssignPayload(BaseModel):
    token: str
    logical_button: str = Field(..., min_length=2, max_length=64)
    device_id: str = Field(..., min_length=1, max_length=120)
    channel: int = Field(..., ge=1, le=2048)
    dry_run: Optional[bool] = None


class LEDCalibrationFlashPayload(BaseModel):
    token: str
    logical_button: Optional[str] = None
    device_id: Optional[str] = None
    channel: Optional[int] = Field(default=None, ge=1, le=2048)
    color: Optional[str] = Field(default="#00E5FF")
    duration_ms: Optional[int] = Field(default=800, ge=100, le=5000)


class LEDCalibrationStopPayload(BaseModel):
    token: str


class LEDCalibrationEscapePayload(BaseModel):
    """Payload for calibration escape hatch (R-20)."""
    token: str
    action: str = Field(..., description="'skip' or 'assign_custom'")
    custom_name: Optional[str] = Field(default=None, description="Hardware name if action is assign_custom")


class LEDGameProfileBindingPayload(BaseModel):
    game_id: str = Field(..., min_length=1)
    profile_name: str = Field(..., min_length=1)


class LEDTestPayload(BaseModel):
    effect: str
    durationMs: Optional[int] = 1000
    color: Optional[str] = "#00E5FF"


class LEDPatternRequest(BaseModel):
    pattern: str = Field(..., min_length=1)
    params: Dict[str, Any] = Field(default_factory=dict)


class LEDBrightnessPayload(BaseModel):
    level: int = Field(..., ge=0, le=100)


class VoiceAmplitudePayload(BaseModel):
    amplitude: float = Field(..., ge=0.0, le=1.0)


class LEDChannelTestPayload(BaseModel):
    device_id: Optional[str] = Field(default=None, description="LED controller identifier")
    channel: int = Field(..., ge=0, le=2048)
    duration_ms: Optional[int] = Field(default=300, ge=50, le=10000)


class BlinkyFlashPayload(BaseModel):
    """Payload for direct LED flash via BlinkyService."""
    port: int = Field(..., ge=1, le=256, description="LED port number (1-based)")
    intensity: int = Field(default=48, ge=0, le=48, description="Brightness 0-48")
    duration_ms: int = Field(default=500, ge=50, le=5000, description="Flash duration")


class BlinkyTestAllPayload(BaseModel):
    """Payload for testing all LED ports."""
    port_count: int = Field(default=32, ge=1, le=256, description="Number of ports to test")
    delay_ms: int = Field(default=100, ge=50, le=1000, description="Delay between each port")


def _service_from_request(request: Request) -> LEDMappingService:
    return LEDMappingService(request.app.state.drive_root, request.app.state.manifest)


def _binding_store_from_request(request: Request) -> LEDGameProfileStore:
    return LEDGameProfileStore(request.app.state.drive_root, request.app.state.manifest)


def _channel_mapping_service_from_request(request: Request) -> LEDChannelMappingService:
    return LEDChannelMappingService(request.app.state.drive_root, request.app.state.manifest)


def _channel_mapping_metadata(
    mapping_service: LEDMappingService,
    channels: Dict[str, Any],
) -> Dict[str, List[str]]:
    payload = mapping_service.load_controls_mapping()
    mappings = payload.get("mappings") if isinstance(payload, dict) else {}
    logical_buttons = sorted(mappings.keys()) if isinstance(mappings, dict) else []
    channel_keys = sorted(channels.keys()) if isinstance(channels, dict) else []
    logical_set = set(logical_buttons)
    unmapped = [name for name in logical_buttons if name not in channel_keys]
    unknown = [name for name in channel_keys if name not in logical_set]
    return {"unmapped": unmapped, "unknown_logical": unknown}


def _build_channel_document(
    service: LEDChannelMappingService,
    payload: LEDChannelMappingPayload,
) -> Dict[str, Any]:
    if payload.channels is None:
        working: Dict[str, Any] = service.load_document()
    else:
        working = {"channels": {}}
        for logical_button, entry in payload.channels.items():
            working = service.set_mapping(logical_button, entry.device_id, entry.channel, document=working)
    for update in payload.updates:
        working = service.set_mapping(update.logical_button, update.device_id, update.channel, document=working)
    return working


async def _log_profile_event(
    request: Request,
    action: str,
    target_file: str,
    status: str,
    profile_name: str,
    scope: str,
    total_channels: int,
    backup_path: Optional[str],
) -> None:
    drive_root = request.app.state.drive_root
    log_file = drive_root / ".aa" / "logs" / "led" / "changes.jsonl"

    def _do_log():
        log_file.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": datetime.now().isoformat(),
            "scope": "led_profile",
            "action": action,
            "status": status,
            "target_file": target_file,
            "backup_path": backup_path,
            "profile_name": profile_name,
            "profile_scope": scope,
            "total_channels": total_channels,
            "device": request.headers.get("x-device-id", "unknown"),
            "panel": request.headers.get("x-panel", "unknown"),
        }

        with open(log_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    await asyncio.to_thread(_do_log)


async def _log_binding_event(
    request: Request,
    action: str,
    game_id: str,
    payload: Dict[str, Any],
    backup_path: Optional[str],
) -> None:
    drive_root = request.app.state.drive_root
    log_file = drive_root / ".aa" / "logs" / "led" / "changes.jsonl"

    def _do_log():
        log_file.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": datetime.now().isoformat(),
            "scope": "led_game_profile",
            "action": action,
            "game_id": game_id,
            "payload": payload,
            "backup_path": backup_path,
            "device": request.headers.get("x-device-id", "unknown"),
            "panel": request.headers.get("x-panel", "unknown"),
        }

        with open(log_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    await asyncio.to_thread(_do_log)


async def _resolve_game_metadata(game_id: str) -> Dict[str, Any]:
    if not game_id:
        raise HTTPException(status_code=400, detail="game_id is required")

    game = await run_in_threadpool(parser.get_game_by_id, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail=f"LaunchBox game not found: {game_id}")

    def _read(attr: str, default: str = "") -> str:
        if isinstance(game, dict):
            return str(game.get(attr) or default)
        return str(getattr(game, attr, default))

    return {
        "id": _read("id"),
        "title": _read("title", "Unknown"),
        "platform": _read("platform", "Unknown"),
    }


def _assignments_for_ws_command(
    mapping_service: LEDMappingService,
    player: str,
    button: str,
    color: Optional[str],
    state: bool,
) -> List[LEDChannelAssignment]:
    logical_button = f"p{str(player).strip().lower().lstrip('p')}.{str(button).strip().lower()}"
    channels = mapping_service.resolve_logical_button(logical_button)
    assignments: List[LEDChannelAssignment] = []
    for channel in channels:
        assignments.append(
            LEDChannelAssignment(
                device_id=channel.device_id or "mock-led-device",
                channel_index=max(0, int(channel.channel_index) - 1),
                color=color or "#00E5FF",
                logical_button=logical_button,
                active=state,
            )
        )
    return assignments


CALIBRATION_SESSIONS_ATTR = "led_calibration_sessions"


def _calibration_sessions(app_state: Any) -> Dict[str, Dict[str, Any]]:
    sessions = getattr(app_state, CALIBRATION_SESSIONS_ATTR, None)
    if sessions is None:
        sessions = {}
        setattr(app_state, CALIBRATION_SESSIONS_ATTR, sessions)
    return sessions


def _active_calibration_session(app_state: Any, token: str) -> Dict[str, Any]:
    sessions = _calibration_sessions(app_state)
    session = sessions.get(token)
    if not session:
        raise HTTPException(status_code=404, detail="Calibration session not found")
    return session


@router.get("/channels", response_model=LEDChannelStateResponse)
async def get_led_channel_mapping(request: Request) -> Dict[str, Any]:
    """Return the current logical-to-physical LED wiring table."""
    channel_service = _channel_mapping_service_from_request(request)
    mapping_service = _service_from_request(request)
    channels = channel_service.load_channels()
    response: Dict[str, Any] = {
        "target_file": channel_service.relative_target,
        "total_channels": len(channels),
        "channels": channels,
    }
    response.update(_channel_mapping_metadata(mapping_service, channels))
    return response


@router.post("/channels/preview", response_model=LEDChannelPreviewResponse)
async def preview_led_channel_mapping(
    request: Request,
    payload: LEDChannelMappingPayload,
) -> Dict[str, Any]:
    """Preview changes to LED channel wiring before writing the config."""
    channel_service = _channel_mapping_service_from_request(request)
    mapping_service = _service_from_request(request)
    document = _build_channel_document(channel_service, payload)
    preview = channel_service.preview(document)
    channels = dict(preview.response["channels"])
    response = dict(preview.response)
    response["channels"] = channels
    response.update(_channel_mapping_metadata(mapping_service, channels))
    return response


@router.post("/channels/apply", response_model=LEDChannelApplyResponse)
async def apply_led_channel_mapping(
    request: Request,
    payload: LEDChannelMappingApplyPayload,
) -> Dict[str, Any]:
    """Apply LED channel wiring changes with backup/logging."""
    require_scope(request, "config")
    channel_service = _channel_mapping_service_from_request(request)
    mapping_service = _service_from_request(request)
    document = _build_channel_document(channel_service, payload)
    preview_result = channel_service.preview(document)
    dry_default = getattr(request.app.state, "dry_run_default", True)
    dry_run = payload.dry_run if payload.dry_run is not None else dry_default

    channels = dict(preview_result.response["channels"])
    preview_payload = dict(preview_result.response)
    preview_payload["channels"] = channels
    preview_payload.update(_channel_mapping_metadata(mapping_service, channels))

    apply_result = channel_service.apply(document, dry_run=dry_run, request=request, preview=preview_result)
    apply_result["preview"] = preview_payload
    return apply_result


@router.delete("/channels/{logical_button}", response_model=LEDChannelDeleteResponse)
async def delete_led_channel_mapping(
    request: Request,
    logical_button: str,
    dry_run: Optional[bool] = None,
) -> Dict[str, Any]:
    """Delete a logical LED wiring entry."""
    require_scope(request, "config")
    channel_service = _channel_mapping_service_from_request(request)
    mapping_service = _service_from_request(request)
    document = channel_service.remove_mapping(logical_button)
    preview_result = channel_service.preview(document)
    channels = dict(preview_result.response["channels"])
    preview_payload = dict(preview_result.response)
    preview_payload["channels"] = channels
    preview_payload.update(_channel_mapping_metadata(mapping_service, channels))

    dry_run_value = dry_run if dry_run is not None else False
    apply_result = channel_service.apply(
        document,
        dry_run=dry_run_value,
        request=request,
        preview=preview_result,
    )
    apply_result["preview"] = preview_payload
    return apply_result


@router.post("/calibrate/start", response_model=LEDCalibrationStartResponse)
async def start_led_calibration(request: Request) -> Dict[str, Any]:
    """Begin a calibration session for AI/voice workflows."""
    require_scope(request, "config")
    sessions = _calibration_sessions(request.app.state)
    token = uuid4().hex
    now = datetime.utcnow()
    sessions[token] = {"token": token, "started_at": now.isoformat()}
    return {"status": "started", "token": token, "started_at": now}


@router.post("/calibrate/assign", response_model=LEDChannelApplyResponse)
async def calibrate_assign_channel(
    request: Request,
    payload: LEDCalibrationAssignPayload,
) -> Dict[str, Any]:
    """Assign a single logical button to a hardware channel while in calibration mode."""
    require_scope(request, "config")
    _active_calibration_session(request.app.state, payload.token)
    channel_service = _channel_mapping_service_from_request(request)
    mapping_service = _service_from_request(request)
    document = channel_service.set_mapping(
        payload.logical_button,
        payload.device_id,
        payload.channel,
    )
    preview_result = channel_service.preview(document)

    channels = dict(preview_result.response["channels"])
    preview_payload = dict(preview_result.response)
    preview_payload["channels"] = channels
    preview_payload.update(_channel_mapping_metadata(mapping_service, channels))

    dry_default = getattr(request.app.state, "dry_run_default", False)
    dry_run = payload.dry_run if payload.dry_run is not None else dry_default
    apply_result = channel_service.apply(
        document,
        dry_run=dry_run,
        request=request,
        preview=preview_result,
    )
    apply_result["preview"] = preview_payload
    return apply_result


async def _flash_led_channel(
    request: Request,
    device_id: str,
    channel: int,
    logical_button: Optional[str],
    color: str,
    duration_ms: int,
) -> None:
    """Flash an LED channel using BlinkyProcessManager (non-blocking).

    Delegates to BlinkyProcessManager.flash_port() which uses
    asyncio.create_subprocess_exec internally. If LEDBlinky.exe is
    missing, logs a warning gracefully (simulation mode fallback).
    """
    port = int(channel)
    logger.info(f"[Calibration] Flashing channel {channel} for {duration_ms}ms via BlinkyProcessManager")

    try:
        blinky = BlinkyProcessManager.get_instance()
        if not blinky.is_available:
            logger.warning("[Calibration] LEDBlinky.exe not available — simulation mode")
            return
        await blinky.flash_port(port, intensity=48, duration_ms=duration_ms)
        logger.info(f"[Calibration] Channel {channel} flash complete")
    except Exception as e:
        logger.error(f"[Calibration] LED flash failed: {e}")



@router.post("/calibrate/flash")
async def calibrate_flash_channel(request: Request, payload: LEDCalibrationFlashPayload) -> Dict[str, Any]:
    """Flash a channel for confirmation during calibration."""
    require_scope(request, "config")
    _active_calibration_session(request.app.state, payload.token)
    channel_service = _channel_mapping_service_from_request(request)

    device_id = payload.device_id
    channel_value = payload.channel
    logical_button = payload.logical_button

    if logical_button:
        binding = channel_service.resolve(logical_button)
        if binding is None:
            raise HTTPException(status_code=404, detail=f"No wiring exists for {logical_button}")
        device_id = binding.device_id
        channel_value = binding.channel

    if not device_id or channel_value is None:
        raise HTTPException(
            status_code=422,
            detail="device_id and channel are required when logical_button is not provided",
        )

    await _flash_led_channel(
        request,
        device_id=device_id,
        channel=int(channel_value),
        logical_button=logical_button,
        color=payload.color or "#00E5FF",
        duration_ms=payload.duration_ms or 800,
    )

    return {
        "status": "flashing",
        "device_id": device_id,
        "channel": int(channel_value),
        "logical_button": logical_button,
    }


@router.post("/calibrate/stop")
async def stop_led_calibration(request: Request, payload: LEDCalibrationStopPayload) -> Dict[str, Any]:
    """Terminate an active calibration session."""
    require_scope(request, "config")
    sessions = _calibration_sessions(request.app.state)
    session = sessions.pop(payload.token, None)
    if not session:
        raise HTTPException(status_code=404, detail="Calibration session not found")
    return {"status": "stopped", "token": payload.token}


@router.post("/calibrate/escape")
async def calibrate_escape_hatch(
    request: Request,
    payload: LEDCalibrationEscapePayload,
) -> Dict[str, Any]:
    """Handle calibration escape hatch (R-20).

    When a port blinks during calibration but doesn't match any button
    on the UI visualizer (e.g., coin door, trackball, spinner ring),
    the user can skip it or assign a custom hardware name.
    """
    require_scope(request, "config")
    _active_calibration_session(request.app.state, payload.token)

    if payload.action == "skip":
        result = LEDCalibrationService.skip_port()
        logger.info("[Calibration] Escape hatch: skipped port")
        return {"status": "skipped", **result}
    elif payload.action == "assign_custom":
        if not payload.custom_name:
            raise HTTPException(
                status_code=422,
                detail="custom_name is required when action is 'assign_custom'",
            )
        result = LEDCalibrationService.confirm_mapping(
            logical_id=payload.custom_name,
            description=f"Custom hardware: {payload.custom_name}",
        )
        logger.info(f"[Calibration] Escape hatch: assigned custom name '{payload.custom_name}'")
        return {"status": "assigned", "custom_name": payload.custom_name, **result}
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid escape action: {payload.action}. Use 'skip' or 'assign_custom'.",
        )


@router.post("/profile/preview", response_model=LEDPreviewResponse)
async def preview_led_profile(request: Request, payload: LEDProfilePayload) -> Dict[str, Any]:
    """Preview an LED profile by resolving logical buttons to hardware channels."""
    service = _service_from_request(request)
    preview_result = service.preview(payload.dict())
    preview = preview_result.response

    await _log_profile_event(
        request,
        action="led_profile_preview",
        status="preview",
        target_file=preview["target_file"],
        profile_name=preview["profile_name"],
        scope=preview["scope"],
        total_channels=preview["total_channels"],
        backup_path=None,
    )
    return preview


@router.post("/profile/apply", response_model=LEDProfileApplyResponse)
async def apply_led_profile(request: Request, payload: LEDProfileApplyRequest) -> Dict[str, Any]:
    """Apply an LED profile, respecting dry-run + backup policies."""
    require_scope(request, "config")

    service = _service_from_request(request)
    preview_payload = payload.dict(exclude={"dry_run"})
    preview_result = service.preview(preview_payload)
    preview = preview_result.response

    if preview["missing_buttons"]:
        raise HTTPException(
            status_code=422,
            detail={"missing_buttons": preview["missing_buttons"]},
        )

    dry_default = getattr(request.app.state, "dry_run_default", True)
    dry_run = payload.dry_run if payload.dry_run is not None else dry_default
    backup_on_write = getattr(request.app.state, "backup_on_write", True)

    write_result = service.apply(
        preview_payload,
        dry_run=dry_run,
        backup_on_write=backup_on_write,
        preview=preview_result,
    )

    status = write_result["status"]
    await _log_profile_event(
        request,
        action="led_profile_apply",
        status=status,
        target_file=write_result["target_file"],
        profile_name=preview["profile_name"],
        scope=preview["scope"],
        total_channels=preview["total_channels"],
        backup_path=write_result["backup_path"],
    )

    # Telemetry (best-effort)
    try:
        device_id = request.headers.get('x-device-id') or getattr(request.state, 'device_id', '') or os.getenv('AA_DEVICE_ID', '')
        level = 'INFO' if status == 'applied' else 'ERROR'
        msg = f"LED profile '{preview['profile_name']}' {status}"
        await asyncio.to_thread(
            sb_send_telemetry,
            device_id,
            level,
            'LED_PROFILE_APPLY',
            msg,
            {
                'profile_name': preview['profile_name'],
                'scope': preview['scope'],
                'total_channels': preview['total_channels'],
                'target_file': write_result['target_file']
            }
        )
    except Exception:
        pass

    response = {
        "status": status,
        "dry_run": dry_run,
        "target_file": write_result["target_file"],
        "backup_path": write_result["backup_path"],
        "preview": preview,
    }
    await _apply_preview_to_engine(request, preview)
    return response


@router.get("/game-profile")
async def get_led_game_profile(request: Request, game_id: str) -> Dict[str, Any]:
    """Return the LaunchBox metadata and current LED profile binding for a game."""
    store = _binding_store_from_request(request)
    game = await _resolve_game_metadata(game_id)
    binding = store.get_binding(game_id)
    return {"game": game, "binding": binding}


@router.get("/game-profiles")
async def list_led_game_profiles(request: Request) -> Dict[str, Any]:
    """List all stored LaunchBox ↔ LED profile bindings."""
    store = _binding_store_from_request(request)
    bindings = store.list_bindings()
    return {"bindings": bindings, "count": len(bindings)}


def _binding_preview_response(
    game: Dict[str, Any],
    profile_name: str,
    preview: Dict[str, Any],
    profile_path: str,
) -> Dict[str, Any]:
    return {
        "game": game,
        "profile_name": profile_name,
        "profile_path": profile_path,
        "preview": preview,
    }


async def _apply_preview_to_engine(request: Request, preview: Dict[str, Any]) -> None:
    resolved = preview.get("resolved_buttons") or []
    if not resolved:
        return
    try:
        engine = get_led_engine(request.app.state)
        await engine.apply_profile(resolved)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("LED engine apply failed: %s", exc)


@router.post("/test")
async def trigger_led_test(request: Request, payload: LEDTestPayload) -> Dict[str, Any]:
    """Queue a temporary LED pattern for hardware diagnostics."""
    require_scope(request, "state")
    effect = payload.effect.lower()
    valid_effects = {"solid", "pulse", "chase", "rainbow"}
    if effect not in valid_effects:
        raise HTTPException(status_code=400, detail=f"Invalid effect '{payload.effect}'")
    engine = get_led_engine(request.app.state)
    params = {"color": payload.color or "#00E5FF"}
    await engine.run_pattern(effect, params=params, duration_ms=payload.durationMs)
    return {
        "status": "queued",
        "effect": effect,
        "duration_ms": payload.durationMs,
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/test/all")
async def trigger_led_test_all(request: Request) -> Dict[str, Any]:
    """
    Zero-config quick LED test for clone validation.
    Runs a brief pulse pattern across all detected channels.
    Safe in simulation mode.
    
    Requires x-scope: state
    """
    require_scope(request, "state")
    engine = get_led_engine(request.app.state)
    status = await engine.status()
    
    # Get device count for response
    devices = status.get("devices") or []
    simulation_mode = status.get("registry", {}).get("simulation_mode", True)
    
    # Run rainbow pattern to cycle all channels (2 seconds)
    await engine.run_pattern("rainbow", params={"speed": 2}, duration_ms=2000)
    
    return {
        "status": "queued",
        "effect": "rainbow",
        "duration_ms": 2000,
        "devices_detected": len(devices),
        "simulation_mode": simulation_mode,
        "timestamp": datetime.now().isoformat(),
        "message": "All channels cycling - watch for LED activity" if not simulation_mode else "Simulation mode - no physical LEDs will activate"
    }


@router.post("/pattern/run")
async def run_led_pattern(request: Request, payload: LEDPatternRequest) -> Dict[str, Any]:
    require_scope(request, "state")
    engine = get_led_engine(request.app.state)
    await engine.run_pattern(payload.pattern, payload.params)
    return {"status": "queued", "pattern": payload.pattern, "params": payload.params}


@router.post("/pattern/clear")
async def clear_led_pattern(request: Request) -> Dict[str, Any]:
    require_scope(request, "state")
    engine = get_led_engine(request.app.state)
    await engine.clear_pattern()
    return {"status": "cleared"}


@router.post("/brightness")
async def update_led_brightness(request: Request, payload: LEDBrightnessPayload) -> Dict[str, Any]:
    require_scope(request, "state")
    engine = get_led_engine(request.app.state)
    await engine.update_brightness(payload.level)
    return {"status": "updated", "level": payload.level}


@router.post("/voice/amplitude")
async def set_voice_amplitude(request: Request, payload: VoiceAmplitudePayload) -> Dict[str, Any]:
    """Update the real-time voice breathing amplitude."""
    require_scope(request, "state")
    engine = get_led_engine(request.app.state)
    await engine.update_voice_amplitude(payload.amplitude)
    return {"status": "ok", "amplitude": payload.amplitude}


@router.post("/refresh")
async def refresh_led_hardware(request: Request) -> Dict[str, Any]:
    """Trigger a hardware rescan to detect newly connected LED devices.
    
    This endpoint allows real-time hardware detection without restarting the backend.
    Call this when LED hardware is connected after startup or to verify hardware status.
    """
    require_scope(request, "state")
    engine = get_led_engine(request.app.state)
    await engine.refresh_devices()
    # Wait briefly for the refresh to process through the engine queue
    await asyncio.sleep(0.15)
    status = await engine.status()
    registry = status.get("registry", {})
    return {
        "status": "refreshed",
        "simulation_mode": registry.get("simulation_mode", True),
        "devices": status.get("devices", []),
        "device_count": len(status.get("devices", [])),
        "hidapi_available": True,  # Will be overwritten below if import fails
        "last_refresh": registry.get("last_refresh"),
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/devices")
async def list_led_devices(request: Request) -> Dict[str, Any]:
    engine = get_led_engine(request.app.state)
    status = await engine.status()
    devices = status.get("devices") or []
    return {"devices": devices, "count": len(devices)}


@router.get("/status")
async def get_led_status(request: Request) -> Dict[str, Any]:
    require_scope(request, "state")
    try:
        engine = get_led_engine(request.app.state)
        status = await engine.status()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to load LED status: %s", exc)
        status = {
            "devices": [],
            "registry": {
                "simulation_mode": True,
                "message": "LED engine unavailable; running in simulation mode",
                "physical_count": 0,
                "all_devices": [],
                "discovery": [],
                "last_refresh": None,
            },
            "engine": {
                "running": False,
                "mode": "unknown",
                "connected_devices": [],
                "last_error": str(exc),
                "simulation_mode": True,
                "tick_ms": None,
                "discovered_devices": [],
                "last_refresh": None,
            },
            "log": [],
            "events": [],
            "brightness": 0,
            "active_pattern": None,
        }
    status["timestamp"] = datetime.now().isoformat()
    # Expose HID library availability for clone validation (Golden Drive requirement)
    try:
        import hid
        status["hidapi_available"] = hid is not None
    except ImportError:
        status["hidapi_available"] = False
    if status.get("registry", {}).get("simulation_mode"):
        status.setdefault("message", "Simulation mode - no LED hardware detected")
    return status


@router.post("/diagnostics/channel-test")
async def run_led_channel_test(request: Request, payload: LEDChannelTestPayload) -> Dict[str, Any]:
    require_scope(request, "state")
    engine = get_led_engine(request.app.state)
    try:
        return await engine.channel_test(payload.device_id, payload.channel, payload.duration_ms or 300)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "channel_test_failed",
                "message": str(exc),
            },
        )


@router.get("/engine-health")
async def get_led_engine_health(request: Request) -> Dict[str, Any]:
    require_scope(request, "state")
    engine = get_led_engine(request.app.state)
    snapshot = await engine.health_snapshot()
    registry = _ws_registry(request.app.state)
    clients = registry.get("clients", {})
    snapshot["ws_clients"] = list(clients.values())
    snapshot["ws_client_count"] = len(clients)
    return snapshot


@router.post("/game-profile/preview")
async def preview_led_game_profile(
    request: Request,
    payload: LEDGameProfileBindingPayload,
) -> Dict[str, Any]:
    """Preview the LED profile that would be bound to a LaunchBox game."""
    game = await _resolve_game_metadata(payload.game_id)
    mapping_service = _service_from_request(request)
    profile_doc = mapping_service.load_profile_document(payload.profile_name)
    preview_result = mapping_service.preview(profile_doc["document"])
    preview = preview_result.response
    return _binding_preview_response(game, payload.profile_name, preview, profile_doc["path"])


@router.post("/game-profile/apply")
async def apply_led_game_profile(
    request: Request,
    payload: LEDGameProfileBindingPayload,
) -> Dict[str, Any]:
    """Bind an LED profile to a LaunchBox game."""
    require_scope(request, "config")
    preview_payload = await preview_led_game_profile(request, payload)
    game = preview_payload["game"]
    preview = preview_payload["preview"]

    store = _binding_store_from_request(request)
    record = store.set_binding(
        game_id=game["id"],
        platform=game.get("platform") or "Unknown",
        title=game.get("title") or "Unknown",
        profile_name=payload.profile_name,
        updated_by=request.headers.get("x-device-id", "unknown"),
    )
    backup_path = record.pop("backup_path", None)

    await _log_binding_event(
        request,
        action="bind_game_profile",
        game_id=game["id"],
        payload=record,
        backup_path=backup_path,
    )

    try:
        await _apply_preview_to_engine(request, preview)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to apply game profile to LED engine: %s", exc)
    return {
        "status": "bound",
        "game": game,
        "binding": record,
        "preview": preview,
        "backup_path": backup_path,
    }


@router.delete("/game-profile")
async def delete_led_game_profile(request: Request, game_id: str) -> Dict[str, Any]:
    """Remove a stored LED profile binding for a LaunchBox game."""
    require_scope(request, "config")
    store = _binding_store_from_request(request)
    backup_path = store.delete_binding(game_id)
    await _log_binding_event(
        request,
        action="unbind_game_profile",
        game_id=game_id,
        payload={"game_id": game_id},
        backup_path=backup_path,
    )
    return {"status": "removed", "game_id": game_id, "backup_path": backup_path}


@router.websocket("/ws")
async def led_control_websocket(websocket: WebSocket):
    """Gateway-managed WebSocket endpoint for real-time LED commands."""
    connection_id = uuid4().hex
    _register_ws_client(websocket.app.state, connection_id, websocket)
    await websocket.accept()
    engine = get_led_engine(websocket.app.state)
    mapping_service = LEDMappingService(websocket.app.state.drive_root, websocket.app.state.manifest)

    async def _send_status() -> None:
        status = await engine.status()
        await websocket.send_json(
            {
                "type": "handshake_response",
                "server": "Arcade Assistant LED Engine",
                "version": "1.0.0",
                "brightness": status.get("brightness"),
                "devices": status.get("devices"),
                "connection_id": connection_id,
            }
        )

    try:
        await _send_status()
        while True:
            payload = await websocket.receive_json()
            try:
                command = parse_ws_message(payload)
            except InvalidLEDMessage as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
                continue

            action = command["action"]
            if action == "handshake":
                await _send_status()
                continue
            if action == "pattern":
                params = command.get("params") or {}
                if command.get("color"):
                    params.setdefault("color", command["color"])
                await engine.run_pattern(command["pattern"], params)
                await websocket.send_json({"type": "pattern_ack", "pattern": command["pattern"]})
                continue
            if action == "clear":
                await engine.clear_pattern()
                await websocket.send_json({"type": "pattern_ack", "pattern": "clear"})
                continue
            if action == "brightness":
                await engine.update_brightness(int(command["level"]))
                await websocket.send_json({"type": "brightness_ack", "level": int(command["level"])})
                continue
            if action == "led_command":
                assignments = _assignments_for_ws_command(
                    mapping_service,
                    player=command["player"],
                    button=command["button"],
                    color=command.get("color"),
                    state=bool(command.get("state", True)),
                )
                if assignments:
                    await engine.merge_assignments(assignments)
                await websocket.send_json(
                    {
                        "type": "led_command_ack",
                        "player": command["player"],
                        "button": command["button"],
                        "state": command.get("state", True),
                        "updated_channels": len(assignments),
                    }
                )
                continue

            if action == "set_trim":
                value = float(command.get("value", 1.0))
                LEDCalibrationService.update_multiplier(value)
                logger.debug("[WS] Trim Updated: %.2f", value)
                await websocket.send_json({"type": "set_trim_ack", "value": value})
                continue

            await websocket.send_json({"type": "error", "message": f"Unsupported action {action}"})

    except WebSocketDisconnect:
        logger.info("LED WebSocket disconnected")
    finally:
        _remove_ws_client(websocket.app.state, connection_id)


# =============================================================================
# LED Click-to-Map Calibration
# Simple approach: Flash LED channel → User clicks button in GUI → Map recorded
# No input detection needed - LED-Wiz only outputs, GUI click is the input
# =============================================================================

# Click-to-map calibration state
_click_to_map_state: Dict[str, Any] = {}


class LEDClickMapPayload(BaseModel):
    """Payload for mapping a GUI button click to the current LED channel."""
    logical_button: str = Field(..., description="Logical button like 'p1.button1'")
    custom_label: Optional[str] = Field(None, description="Optional custom label for misc buttons")


@router.post("/click-to-map/start")
async def start_click_to_map(
    request: Request,
    total_channels: int = 32,
    device_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Start LED Click-to-Map calibration.
    
    Flashes LED channels one-by-one. User clicks the corresponding button in GUI.
    No input detection needed - just GUI clicks.
    
    Args:
        total_channels: Number of LED channels to calibrate (default 32)
        device_id: LED device ID (auto-detected if not provided)
    """
    require_scope(request, "config")
    global _click_to_map_state
    
    # Auto-detect device ID if not provided
    engine = get_led_engine(request.app.state)
    if device_id is None:
        # Get first available device from registry
        all_devices = engine.registry.all_devices()
        if all_devices:
            device_id = all_devices[0].device_id
            total_channels = getattr(all_devices[0], 'channel_count', 32)
            logger.info("[LED ClickToMap] Auto-detected device: %s with %d channels", device_id, total_channels)
        else:
            raise HTTPException(status_code=404, detail="No LED devices detected. Connect an LED-Wiz and restart.")
    
    # Start calibration session
    sessions = _calibration_sessions(request.app.state)
    token = uuid4().hex
    now = datetime.utcnow()
    sessions[token] = {"token": token, "started_at": now.isoformat()}
    
    _click_to_map_state = {
        "token": token,
        "device_id": device_id,
        "current_channel": 1,
        "total_channels": total_channels,
        "mappings": {},  # {channel_id: logical_button}
        "started_at": now.isoformat(),
    }
    
    # Flash the first channel using engine.channel_test() for direct hardware control
    try:
        await engine.channel_test(device_id=device_id, channel=0, duration_ms=10000)  # Channel 0 = first LED
    except Exception as e:
        logger.warning("[LED ClickToMap] Could not flash channel 1: %s", e)
    
    return {
        "status": "started",
        "token": token,
        "device_id": device_id,
        "current_channel": 1,
        "total_channels": total_channels,
        "message": "Channel 1 is flashing. Click the button in the GUI that lit up.",
    }


@router.get("/click-to-map/status")
async def get_click_to_map_status(request: Request) -> Dict[str, Any]:
    """Get current click-to-map calibration status."""
    require_scope(request, "state")
    
    if not _click_to_map_state:
        return {"status": "not_started"}
    
    current = _click_to_map_state.get("current_channel", 1)
    total = _click_to_map_state.get("total_channels", 32)
    
    if current > total:
        return {
            "status": "complete",
            "mappings": _click_to_map_state.get("mappings", {}),
            "total_mapped": len(_click_to_map_state.get("mappings", {})),
            "message": "All channels calibrated! Click Save to persist.",
        }
    
    return {
        "status": "waiting",
        "current_channel": current,
        "total_channels": total,
        "mappings": _click_to_map_state.get("mappings", {}),
        "message": f"Channel {current} is flashing. Click the button in the GUI that lit up.",
    }


@router.post("/click-to-map/assign")
async def assign_click_to_map(
    request: Request,
    payload: LEDClickMapPayload,
) -> Dict[str, Any]:
    """Assign the current LED channel to a logical button.
    
    Called when user clicks a button in the GUI to map the currently flashing channel.
    """
    require_scope(request, "config")
    global _click_to_map_state
    
    if not _click_to_map_state:
        raise HTTPException(status_code=400, detail="Click-to-map not started")
    
    current_channel = _click_to_map_state.get("current_channel", 1)
    total_channels = _click_to_map_state.get("total_channels", 32)
    device_id = _click_to_map_state.get("device_id", "ledwiz_0")
    
    # Record the mapping
    _click_to_map_state["mappings"][str(current_channel)] = {
        "logical_button": payload.logical_button,
        "custom_label": payload.custom_label,
        "channel": current_channel,
        "device_id": device_id,
    }
    
    # Advance to next channel
    next_channel = current_channel + 1
    _click_to_map_state["current_channel"] = next_channel
    
    if next_channel > total_channels:
        return {
            "status": "complete",
            "assigned": payload.logical_button,
            "channel": current_channel,
            "mappings": _click_to_map_state.get("mappings", {}),
            "message": "All channels calibrated! Click Save to persist.",
        }
    
    # Flash the next channel using direct hardware control
    try:
        engine = get_led_engine(request.app.state)
        await engine.channel_test(device_id=device_id, channel=next_channel - 1, duration_ms=10000)  # 0-indexed
    except Exception as e:
        logger.warning("[LED ClickToMap] Could not flash channel %d: %s", next_channel, e)
    
    return {
        "status": "assigned",
        "assigned": payload.logical_button,
        "channel": current_channel,
        "next_channel": next_channel,
        "total_channels": total_channels,
        "message": f"Mapped! Channel {next_channel} is now flashing.",
    }


@router.post("/click-to-map/skip")
async def skip_click_to_map_channel(request: Request) -> Dict[str, Any]:
    """Skip the current LED channel (no button for this LED)."""
    require_scope(request, "config")
    global _click_to_map_state
    
    if not _click_to_map_state:
        raise HTTPException(status_code=400, detail="Click-to-map not started")
    
    current_channel = _click_to_map_state.get("current_channel", 1)
    total_channels = _click_to_map_state.get("total_channels", 32)
    device_id = _click_to_map_state.get("device_id", "ledwiz_0")
    
    # Advance without recording
    next_channel = current_channel + 1
    _click_to_map_state["current_channel"] = next_channel
    
    if next_channel > total_channels:
        return {
            "status": "complete",
            "skipped": current_channel,
            "mappings": _click_to_map_state.get("mappings", {}),
            "message": "All channels done! Click Save to persist.",
        }
    
    # Flash the next channel using direct hardware control
    try:
        engine = get_led_engine(request.app.state)
        await engine.channel_test(device_id=device_id, channel=next_channel - 1, duration_ms=10000)  # 0-indexed
    except Exception as e:
        logger.warning("[LED ClickToMap] Could not flash channel %d: %s", next_channel, e)
    
    return {
        "status": "skipped",
        "skipped": current_channel,
        "next_channel": next_channel,
        "message": f"Skipped. Channel {next_channel} is now flashing.",
    }


@router.post("/click-to-map/save")
async def save_click_to_map(request: Request) -> Dict[str, Any]:
    """Persist click-to-map calibration to led_channels.json with Backup + Log."""
    require_scope(request, "config")
    global _click_to_map_state
    
    if not _click_to_map_state or not _click_to_map_state.get("mappings"):
        raise HTTPException(status_code=400, detail="No mappings to save")
    
    mappings = _click_to_map_state["mappings"]
    device_id = _click_to_map_state.get("device_id", "ledwiz_0")
    
    # Build channel mapping document
    channel_service = _channel_mapping_service_from_request(request)
    document = channel_service.load_document()
    
    for channel_id, mapping in mappings.items():
        logical_button = mapping.get("logical_button")
        if logical_button:
            document = channel_service.set_mapping(
                logical_button,
                device_id,
                int(channel_id),
                document=document,
            )
    
    # Apply with backup
    result = channel_service.apply(document, dry_run=False, request=request)
    
    # Clean up state
    saved_count = len([m for m in mappings.values() if m.get("logical_button")])
    token = _click_to_map_state.get("token")
    _click_to_map_state = {}
    
    # End calibration session
    if token:
        sessions = _calibration_sessions(request.app.state)
        sessions.pop(token, None)
    
    logger.info("[LED ClickToMap] Saved %d LED channel mappings", saved_count)
    
    return {
        "status": "saved",
        "total_mapped": saved_count,
        "target_file": result.get("target_file"),
        "backup_path": result.get("backup_path"),
        "message": f"Saved {saved_count} LED channel mappings!",
    }


@router.post("/click-to-map/cancel")
async def cancel_click_to_map(request: Request) -> Dict[str, Any]:
    """Cancel click-to-map calibration without saving."""
    require_scope(request, "config")
    global _click_to_map_state
    
    token = _click_to_map_state.get("token") if _click_to_map_state else None
    mappings_count = len(_click_to_map_state.get("mappings", {})) if _click_to_map_state else 0
    
    # End calibration session
    if token:
        sessions = _calibration_sessions(request.app.state)
        sessions.pop(token, None)
    
    _click_to_map_state = {}
    
    return {
        "status": "cancelled",
        "discarded": mappings_count,
        "message": "Calibration cancelled. No changes saved.",
    }



def _get_led_input_detection_service(request: Request):
    """Get the input detection service - REUSES Controller's instance for sharing pynput listener.
    
    This is read-only usage - LED wizard does NOT write to controls.json.
    """
    from pathlib import Path
    # Import Controller's input detection service to reuse the same pynput listener
    from .chuck_hardware import get_input_detection_service as get_controller_service
    
    # Reuse Controller's input detection service (same pynput listener)
    try:
        return get_controller_service(request)
    except Exception as e:
        logger.warning("[LEDLearnWizard] Could not get controller service, creating standalone: %s", e)
        # Fallback: create standalone service if controller import fails
        from ..services.chuck.input_detector import InputDetectionService
        attr = "_led_input_detection_service"
        service = getattr(request.app.state, attr, None)
        if service is None:
            drive_root: Path = request.app.state.drive_root
            service = InputDetectionService(board_type="generic", drive_root=drive_root)
            setattr(request.app.state, attr, service)
        return service


@router.post("/learn-wizard/start")
async def start_led_learn_wizard(
    request: Request,
    players: int = 2,
    skip_trackball: bool = False,
) -> Dict[str, Any]:
    """Start the LED Learn Wizard to map physical buttons to LED channels.
    
    Uses Controller input detection (read-only) to capture button presses.
    Flashes LED channels during calibration so user knows which LED to map.
    Stores mappings in led_channels.json (separate from color profiles).
    
    Args:
        players: Number of players (2 or 4)
        skip_trackball: If True, skip trackball detection step
    """
    require_scope(request, "config")
    global _led_wizard_state, _led_wizard_latest_input
    
    # Select sequence based on player count
    sequence = LED_WIZARD_SEQUENCE_4P if players == 4 else LED_WIZARD_SEQUENCE_2P
    
    # Start a calibration session for flashing LEDs
    sessions = _calibration_sessions(request.app.state)
    token = uuid4().hex
    now = datetime.utcnow()
    sessions[token] = {"token": token, "started_at": now.isoformat()}
    
    # Initialize wizard state
    _led_wizard_state = {
        "sequence": sequence,
        "players": players,
        "current_index": 0,
        "current_channel": 1,  # Start with LED channel 1
        "captures": {},  # {logical_button: {channel, device_id, input_key}}
        "token": token,
        "started_at": now.isoformat(),
        "skip_trackball": skip_trackball,
        "trackball_detected": None,
    }
    _led_wizard_latest_input = None
    
    # Get input detection service (read-only reuse of Controller's detector)
    service = _get_led_input_detection_service(request)
    service.set_learn_mode(True)
    
    # Register handler to capture raw inputs
    def capture_led_wizard_input(keycode: str) -> None:
        global _led_wizard_latest_input
        _led_wizard_latest_input = keycode
        logger.info("[LEDLearnWizard] Captured input: %s", keycode)
    
    service._raw_handlers.clear()
    service.register_raw_handler(capture_led_wizard_input)
    service.start_listening()
    logger.info("[LEDLearnWizard] Started input detection for LED calibration")
    
    # Get first control to map
    first_control = sequence[0] if sequence else "p1.button1"
    display_name = LED_CONTROL_DISPLAY_NAMES.get(first_control, first_control)
    
    # Flash the first LED channel
    try:
        await _flash_led_channel(
            request,
            device_id="ledwiz_0",  # Default device
            channel=1,
            logical_button=first_control,
            color="#00FF00",  # Green flash
            duration_ms=1000,
        )
    except Exception as e:
        logger.warning("[LEDLearnWizard] Could not flash LED: %s", e)
    
    return {
        "status": "started",
        "token": token,
        "players": players,
        "current_control": first_control,
        "current_channel": 1,
        "current_index": 0,
        "total_controls": len(sequence),
        "display_name": display_name,
        "chuck_prompt": f"Press {display_name} now! The LED for this button is flashing green.",
        "skip_trackball": skip_trackball,
    }


@router.get("/learn-wizard/status")
async def get_led_learn_wizard_status(request: Request) -> Dict[str, Any]:
    """Poll for LED Learn Wizard status and any captured input.
    
    Frontend polls this to detect when user presses a button.
    Returns captured_input when a button press is detected.
    """
    require_scope(request, "state")
    
    if not _led_wizard_state:
        return {"status": "not_started"}
    
    current_index = _led_wizard_state.get("current_index", 0)
    sequence = _led_wizard_state.get("sequence", [])
    current_channel = _led_wizard_state.get("current_channel", 1)
    
    if current_index >= len(sequence):
        return {
            "status": "complete",
            "captures": _led_wizard_state.get("captures", {}),
            "chuck_prompt": "All done! Your LED channels are mapped. Click Save to persist.",
            "total_mapped": len(_led_wizard_state.get("captures", {})),
        }
    
    current_control = sequence[current_index]
    display_name = LED_CONTROL_DISPLAY_NAMES.get(current_control, current_control)
    
    return {
        "status": "waiting",
        "current_control": current_control,
        "current_channel": current_channel,
        "current_index": current_index,
        "total_controls": len(sequence),
        "captured_input": _led_wizard_latest_input,
        "captures": _led_wizard_state.get("captures", {}),
        "display_name": display_name,
        "trackball_detected": _led_wizard_state.get("trackball_detected"),
    }


@router.post("/learn-wizard/confirm")
async def confirm_led_learn_capture(request: Request) -> Dict[str, Any]:
    """Confirm the captured input for the current LED control and advance.
    
    Maps the current logical button to the current LED channel.
    Advances to the next button in the sequence.
    """
    require_scope(request, "config")
    global _led_wizard_latest_input
    
    if not _led_wizard_state:
        raise HTTPException(status_code=400, detail="LED wizard not started")
    
    if not _led_wizard_latest_input:
        raise HTTPException(status_code=400, detail="No input captured yet - press a button first")
    
    current_index = _led_wizard_state.get("current_index", 0)
    sequence = _led_wizard_state.get("sequence", [])
    current_channel = _led_wizard_state.get("current_channel", 1)
    
    if current_index >= len(sequence):
        return {
            "status": "complete",
            "captures": _led_wizard_state.get("captures", {}),
        }
    
    current_control = sequence[current_index]
    
    # Record the mapping (logical button -> LED channel + input key)
    _led_wizard_state["captures"][current_control] = {
        "channel": current_channel,
        "device_id": "ledwiz_0",  # Default LED-Wiz device
        "input_key": _led_wizard_latest_input,
    }
    
    # Advance to next control
    _led_wizard_state["current_index"] = current_index + 1
    _led_wizard_state["current_channel"] = current_channel + 1
    _led_wizard_latest_input = None  # Clear for next capture
    
    new_index = _led_wizard_state["current_index"]
    if new_index >= len(sequence):
        return {
            "status": "complete",
            "captures": _led_wizard_state.get("captures", {}),
            "chuck_prompt": "All done! Click Save to persist your LED mappings.",
        }
    
    # Get next control
    next_control = sequence[new_index]
    display_name = LED_CONTROL_DISPLAY_NAMES.get(next_control, next_control)
    
    # Flash the next LED channel
    try:
        await _flash_led_channel(
            request,
            device_id="ledwiz_0",
            channel=_led_wizard_state["current_channel"],
            logical_button=next_control,
            color="#00FF00",
            duration_ms=1000,
        )
    except Exception as e:
        logger.warning("[LEDLearnWizard] Could not flash LED: %s", e)
    
    return {
        "status": "waiting",
        "next_control": next_control,
        "current_index": new_index,
        "current_channel": _led_wizard_state["current_channel"],
        "total_controls": len(sequence),
        "captures": _led_wizard_state.get("captures", {}),
        "display_name": display_name,
        "chuck_prompt": f"Got it! Now press {display_name}.",
    }


@router.post("/learn-wizard/skip")
async def skip_led_learn_control(request: Request) -> Dict[str, Any]:
    """Skip the current control and move to next."""
    require_scope(request, "config")
    global _led_wizard_latest_input
    
    if not _led_wizard_state:
        raise HTTPException(status_code=400, detail="LED wizard not started")
    
    current_index = _led_wizard_state.get("current_index", 0)
    sequence = _led_wizard_state.get("sequence", [])
    
    # Advance without recording
    _led_wizard_state["current_index"] = current_index + 1
    _led_wizard_state["current_channel"] = _led_wizard_state.get("current_channel", 1) + 1
    _led_wizard_latest_input = None
    
    new_index = _led_wizard_state["current_index"]
    if new_index >= len(sequence):
        return {
            "status": "complete",
            "captures": _led_wizard_state.get("captures", {}),
        }
    
    next_control = sequence[new_index]
    display_name = LED_CONTROL_DISPLAY_NAMES.get(next_control, next_control)
    
    return {
        "status": "waiting",
        "next_control": next_control,
        "current_index": new_index,
        "display_name": display_name,
        "chuck_prompt": f"Skipped. Now press {display_name}.",
    }


@router.post("/learn-wizard/save")
async def save_led_learn_wizard(request: Request) -> Dict[str, Any]:
    """Persist LED Learn Wizard captures to led_channels.json with Backup + Log.
    
    Only writes LED channel mappings. Does NOT modify:
    - Controller mappings (controls.json)
    - LED color profiles
    """
    require_scope(request, "config")
    global _led_wizard_state, _led_wizard_latest_input
    
    if not _led_wizard_state or not _led_wizard_state.get("captures"):
        raise HTTPException(status_code=400, detail="No LED mappings to save")
    
    captures = _led_wizard_state["captures"]
    
    # Build channel mapping document
    channel_service = _channel_mapping_service_from_request(request)
    document = channel_service.load_document()
    
    for logical_button, capture in captures.items():
        document = channel_service.set_mapping(
            logical_button,
            capture["device_id"],
            capture["channel"],
            document=document,
        )
    
    # Apply with backup
    result = channel_service.apply(document, dry_run=False, request=request)
    
    # Stop input detection
    try:
        service = _get_led_input_detection_service(request)
        service.set_learn_mode(False)
        service.stop_listening()
    except Exception as e:
        logger.warning("[LEDLearnWizard] Could not stop input detection: %s", e)
    
    # Clean up wizard state
    saved_count = len(captures)
    token = _led_wizard_state.get("token")
    _led_wizard_state = {}
    _led_wizard_latest_input = None
    
    # End calibration session
    if token:
        sessions = _calibration_sessions(request.app.state)
        sessions.pop(token, None)
    
    logger.info("[LEDLearnWizard] Saved %d LED channel mappings", saved_count)
    
    return {
        "status": "saved",
        "total_mapped": saved_count,
        "target_file": result.get("target_file"),
        "backup_path": result.get("backup_path"),
        "chuck_prompt": f"Saved {saved_count} LED channel mappings!",
    }


@router.post("/learn-wizard/stop")
async def stop_led_learn_wizard(request: Request) -> Dict[str, Any]:
    """Cancel the LED Learn Wizard without saving."""
    require_scope(request, "config")
    global _led_wizard_state, _led_wizard_latest_input
    
    token = _led_wizard_state.get("token") if _led_wizard_state else None
    captures_count = len(_led_wizard_state.get("captures", {})) if _led_wizard_state else 0
    
    # Stop input detection
    try:
        service = _get_led_input_detection_service(request)
        service.set_learn_mode(False)
        service.stop_listening()
    except Exception as e:
        logger.warning("[LEDLearnWizard] Could not stop input detection: %s", e)
    
    # End calibration session
    if token:
        sessions = _calibration_sessions(request.app.state)
        sessions.pop(token, None)
    
    _led_wizard_state = {}
    _led_wizard_latest_input = None
    
    return {
        "status": "stopped",
        "discarded_captures": captures_count,
        "chuck_prompt": "LED calibration cancelled. No changes saved.",
    }


# =============================================================================
# WebSocket Endpoint - LED Pattern Streaming
# =============================================================================
# PERFORMANCE CONSTRAINT: Do NOT use Pydantic models for frame serialization.
# LED data is high-frequency; raw dict streaming avoids encoder overhead.

@router.websocket("/ws")
async def led_websocket(websocket: WebSocket, rom: Optional[str] = None):
    """WebSocket endpoint for real-time LED pattern streaming.
    
    Streams LED updates as raw dictionaries directly from BlinkyService
    to minimize serialization overhead for high-frequency updates.
    
    Query params:
        rom: ROM name to apply lighting for (optional)
        
    Message types (from client):
        {"type": "apply_pattern", "rom": "sf2"}
        {"type": "test_pattern"}
        {"type": "all_dark"}
        {"type": "ping"}
    """
    await websocket.accept()
    connection_id = str(uuid4())
    
    # Register connection
    registry = _ws_registry(websocket.app.state)
    registry["clients"][connection_id] = {
        "connected_at": datetime.now().isoformat(),
        "rom": rom
    }
    
    logger.info(f"[LED WS] Client connected: {connection_id}")
    
    # Import service here to avoid circular imports
    from ..services.blinky.service import get_service as get_blinky_service
    
    try:
        # Send initial connection confirmation (raw dict)
        await websocket.send_json({
            "type": "connected",
            "connection_id": connection_id,
            "message": "LED WebSocket ready"
        })
        
        # If ROM provided, immediately stream pattern
        if rom:
            service = get_blinky_service()
            async for frame in service.process_game_lights(rom):
                # PERFORMANCE: Send raw dict directly, no Pydantic encoding
                await websocket.send_json(frame)
        
        # Listen for client messages
        while True:
            try:
                data = await websocket.receive_json()
                msg_type = data.get("type", "")
                
                if msg_type == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
                
                elif msg_type == "apply_pattern":
                    target_rom = data.get("rom")
                    if not target_rom:
                        await websocket.send_json({"type": "error", "message": "ROM required"})
                        continue
                    
                    service = get_blinky_service()
                    async for frame in service.process_game_lights(target_rom):
                        # PERFORMANCE: Raw dict streaming
                        await websocket.send_json(frame)
                
                elif msg_type == "test_pattern":
                    service = get_blinky_service()
                    async for frame in service.apply_test_pattern():
                        await websocket.send_json(frame)
                
                elif msg_type == "all_dark":
                    service = get_blinky_service()
                    await service.apply_all_dark()
                    await websocket.send_json({"type": "all_dark_complete"})
                
                else:
                    await websocket.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"[LED WS] Message error: {e}")
                await websocket.send_json({"type": "error", "message": str(e)})
                
    finally:
        # Cleanup connection
        registry["clients"].pop(connection_id, None)
        logger.info(f"[LED WS] Client disconnected: {connection_id}")


# =============================================================================
# BLINKY SERVICE ENDPOINTS (Phase 4.1 - Direct LED Hardware Control)
# =============================================================================
# These endpoints use the BlinkyService class which wraps LEDBlinky.exe CLI
# with deterministic A: drive paths per the Arcade Assistant architecture.

@router.get("/blinky/status")
async def blinky_status(request: Request) -> Dict[str, Any]:
    """Get BlinkyService status and availability."""
    require_scope(request, "state")
    return BlinkyService.get_status()


@router.post("/blinky/flash")
async def blinky_flash(request: Request, payload: BlinkyFlashPayload) -> Dict[str, Any]:
    """
    Flash a single LED port at the given intensity.
    
    This uses LEDBlinky.exe Command 14 (Set Port) via the BlinkyService.
    """
    require_scope(request, "config")
    
    result = await BlinkyService.flash_port(
        port=payload.port,
        intensity=payload.intensity,
        duration_ms=payload.duration_ms
    )
    
    logger.info(f"[Blinky] Flash port={payload.port} intensity={payload.intensity} -> {result.get('success')}")
    return result


@router.post("/blinky/all-off")
async def blinky_all_off(request: Request) -> Dict[str, Any]:
    """Turn all LEDs off using LEDBlinky.exe Command 5."""
    require_scope(request, "config")
    
    result = await BlinkyService.all_off()
    logger.info(f"[Blinky] All off -> {result.get('success')}")
    return result


@router.post("/blinky/test-all")
async def blinky_test_all(request: Request, payload: BlinkyTestAllPayload) -> Dict[str, Any]:
    """
    Test all LED ports by cycling through them sequentially.
    
    Use this to discover which physical LEDs are connected to which ports.
    """
    require_scope(request, "config")
    
    logger.info(f"[Blinky] Testing {payload.port_count} ports with {payload.delay_ms}ms delay")
    result = await BlinkyService.test_all_ports(
        port_count=payload.port_count,
        delay_ms=payload.delay_ms
    )
    return result


@router.post("/blinky/game/{game_name}")
async def blinky_set_game(request: Request, game_name: str) -> Dict[str, Any]:
    """
    Set the active game for LEDBlinky (Command 1).
    
    This triggers LEDBlinky's game-specific lighting profile if configured.
    """
    require_scope(request, "config")
    
    result = await BlinkyService.set_game(game_name)
    logger.info(f"[Blinky] Set game={game_name} -> {result.get('success')}")
    return result


# =============================================================================
# BLINKY BRIDGE - GAME SELECTION (DEBOUNCED) & LIFECYCLE
# =============================================================================
# These endpoints implement the "Blinky Bridge" pattern with throttling
# for UI scrolling events and immediate execution for game launches.


class GameSelectionPayload(BaseModel):
    """Payload for game selection (debounced).
    
    Accepts either LaunchBox plugin format OR custom frontend format:
    - Plugin: { rom, emulator }
    - Custom: { gameId, title, emulator? }
    
    Extra fields are allowed to prevent 400 errors from unexpected data.
    """
    # Allow extra fields to prevent validation failures
    model_config = {"extra": "allow"}
    
    # Primary fields (from plugin)
    rom: Optional[str] = Field(default=None, max_length=256)
    emulator: str = Field(default="MAME", max_length=64)
    
    # Alternative fields (from custom frontend)
    gameId: Optional[str] = Field(default=None, max_length=256)
    title: Optional[str] = Field(default=None, max_length=256)

    @model_validator(mode='after')
    def require_game_identifier(self):
        """Ensure we have at least one game identifier."""
        if not self.rom and not self.gameId:
            raise ValueError("Either 'rom' or 'gameId' is required")
        return self

    def get_rom(self) -> str:
        """Return rom, falling back to gameId if rom not set."""
        return self.rom or self.gameId or ""


class AnimationPayload(BaseModel):
    """Payload for playing an animation."""
    animation: str = Field(..., min_length=1, max_length=128)
    single_loop: bool = Field(default=False)


@router.post("/blinky/system-start")
async def blinky_system_start(request: Request) -> Dict[str, Any]:
    """
    Signal that Arcade Assistant has started.
    Activates LEDBlinky's frontend mode (Command 1).
    """
    require_scope(request, "config")
    manager = BlinkyProcessManager.get_instance()
    return await manager.system_start()


@router.post("/blinky/system-quit")
async def blinky_system_quit(request: Request) -> Dict[str, Any]:
    """
    Signal that Arcade Assistant is shutting down.
    Triggers LEDBlinky's quit sequence (Command 2).
    """
    require_scope(request, "config")
    manager = BlinkyProcessManager.get_instance()
    return await manager.system_quit()


@router.post("/blinky/game-selected")
async def blinky_game_selected(request: Request, payload: GameSelectionPayload) -> Dict[str, Any]:
    """
    Game selection event - DEBOUNCED (250ms).
    
    Called when user scrolls/hovers over a game in the UI.
    This is throttled to avoid spawning a process for every scroll tick.
    Only fires the CLI command after the user stops scrolling.
    """
    require_scope(request, "config")
    manager = BlinkyProcessManager.get_instance()
    rom = payload.get_rom()
    result = await manager.game_selected(rom, payload.emulator)
    logger.debug(f"[Blinky] Game selected: {rom} -> debouncing")
    return result


@router.post("/blinky/game-launch")
async def blinky_game_launch(request: Request, payload: GameSelectionPayload) -> Dict[str, Any]:
    """
    Game launch event - IMMEDIATE (no debounce).
    
    Called when a game is actually being launched.
    Triggers full LEDBlinky game start with lighting, speech, and animations.
    """
    require_scope(request, "config")
    manager = BlinkyProcessManager.get_instance()
    rom = payload.get_rom()
    result = await manager.game_launch(rom, payload.emulator)
    logger.info(f"[Blinky] Game launch: {rom} ({payload.emulator}) -> {result.get('success')}")
    return result


@router.post("/blinky/game-stop")
async def blinky_game_stop(request: Request) -> Dict[str, Any]:
    """
    Game stop event (Command 4).
    Called when returning from a game to the frontend.
    """
    require_scope(request, "config")
    manager = BlinkyProcessManager.get_instance()
    return await manager.game_stop()


@router.post("/blinky/animation/play")
async def blinky_animation_play(request: Request, payload: AnimationPayload) -> Dict[str, Any]:
    """
    Play an LED animation (.lwax file).
    """
    require_scope(request, "config")
    manager = BlinkyProcessManager.get_instance()
    return await manager.play_animation(payload.animation, payload.single_loop)


@router.post("/blinky/animation/stop")
async def blinky_animation_stop(request: Request) -> Dict[str, Any]:
    """
    Stop the current animation (Command 11).
    """
    require_scope(request, "config")
    manager = BlinkyProcessManager.get_instance()
    return await manager.stop_animation()


@router.get("/blinky/manager-status")
async def blinky_manager_status(request: Request) -> Dict[str, Any]:
    """
    Get the Blinky Process Manager status including debounce state.
    """
    require_scope(request, "state")
    manager = BlinkyProcessManager.get_instance()
    return manager.get_status()


# =============================================================================
# LED MAPPING TRANSLATOR (Phase 2 - JSON to LEDBlinky XML)
# =============================================================================
# These endpoints handle the translation from our wizard JSON output
# to LEDBlinky's LEDBlinkyInputMap.xml format.

from ..services.led_blinky_translator import LEDBlinkyTranslator


@router.post("/blinky/translate")
async def blinky_translate_mapping(request: Request) -> Dict[str, Any]:
    """
    Translate our JSON mapping to LEDBlinkyInputMap.xml.
    
    Call this after completing the calibration wizard to sync
    our mapping with LEDBlinky's expected format.
    
    This enables the hybrid approach:
    - Our wizard creates physical-to-logical mapping
    - LEDBlinky's engine handles game-aware lighting
    """
    require_scope(request, "config")
    
    result = LEDBlinkyTranslator.translate()
    
    if result.get("success"):
        logger.info(f"[Translator] Successfully translated {result.get('mappings_count')} mappings")
    else:
        logger.error(f"[Translator] Translation failed: {result.get('error')}")
    
    return result


@router.get("/blinky/translator-status")
async def blinky_translator_status(request: Request) -> Dict[str, Any]:
    """
    Get the translator status including JSON and XML file states.
    """
    require_scope(request, "state")
    return LEDBlinkyTranslator.get_status()


@router.get("/blinky/validate-xml")
async def blinky_validate_xml(request: Request) -> Dict[str, Any]:
    """
    Validate the generated LEDBlinkyInputMap.xml file.
    """
    require_scope(request, "state")
    return LEDBlinkyTranslator.validate_xml()


# =============================================================================
# NATIVE TOOL LAUNCHERS
# =============================================================================
# These endpoints launch LEDBlinky's native configuration tools.
# We use the vendor tools instead of custom XML generation to avoid
# corrupting the lighting configuration ("Ghost Map" prevention).

import subprocess

@router.post("/blinky/tools/input-map")
async def blinky_launch_input_map(request: Request) -> Dict[str, Any]:
    """
    Launch GenLEDBlinkyInputMap.exe - the native input mapping tool.
    
    This creates/updates LEDBlinkyInputMap.xml which maps physical
    ports to logical button names. Uses vendor tool for safety.
    """
    require_scope(request, "config")
    
    ledblinky_dir = Paths.Tools.LEDBlinky.root()
    exe_path = ledblinky_dir / "GenLEDBlinkyInputMap.exe"
    cwd = ledblinky_dir
    
    if not exe_path.exists():
        return {
            "success": False,
            "error": f"GenLEDBlinkyInputMap.exe not found at {exe_path}"
        }
    
    try:
        # Use Popen so it opens on server desktop without blocking API
        subprocess.Popen(
            [str(exe_path)],
            cwd=str(cwd),
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        logger.info(f"[Blinky] Launched GenLEDBlinkyInputMap.exe")
        return {
            "success": True,
            "message": "Input mapping tool opened on server desktop",
            "tool": "GenLEDBlinkyInputMap.exe"
        }
    except Exception as e:
        logger.error(f"[Blinky] Failed to launch GenLEDBlinkyInputMap.exe: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/blinky/tools/config-wizard")
async def blinky_launch_config_wizard(request: Request) -> Dict[str, Any]:
    """
    Launch LEDBlinkyConfigWizard.exe - the main configuration tool.
    
    Configures LED controllers, colors, game options, etc.
    """
    require_scope(request, "config")
    
    ledblinky_dir = Paths.Tools.LEDBlinky.root()
    exe_path = ledblinky_dir / "LEDBlinkyConfigWizard.exe"
    cwd = ledblinky_dir
    
    if not exe_path.exists():
        return {
            "success": False,
            "error": f"LEDBlinkyConfigWizard.exe not found at {exe_path}"
        }
    
    try:
        subprocess.Popen(
            [str(exe_path)],
            cwd=str(cwd),
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        logger.info(f"[Blinky] Launched LEDBlinkyConfigWizard.exe")
        return {
            "success": True,
            "message": "Configuration wizard opened on server desktop",
            "tool": "LEDBlinkyConfigWizard.exe"
        }
    except Exception as e:
        logger.error(f"[Blinky] Failed to launch LEDBlinkyConfigWizard.exe: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/blinky/tools/output-test")
async def blinky_launch_output_test(request: Request) -> Dict[str, Any]:
    """
    Launch LEDBlinkyOutputTest.exe - the hardware diagnostic tool.
    
    Tests LED controllers and verifies port connectivity.
    """
    require_scope(request, "config")
    
    ledblinky_dir = Paths.Tools.LEDBlinky.root()
    exe_path = ledblinky_dir / "LEDBlinkyOutputTest.exe"
    cwd = ledblinky_dir
    
    if not exe_path.exists():
        return {
            "success": False,
            "error": f"LEDBlinkyOutputTest.exe not found at {exe_path}"
        }
    
    try:
        subprocess.Popen(
            [str(exe_path)],
            cwd=str(cwd),
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        logger.info(f"[Blinky] Launched LEDBlinkyOutputTest.exe")
        return {
            "success": True,
            "message": "Output test tool opened on server desktop",
            "tool": "LEDBlinkyOutputTest.exe"
        }
    except Exception as e:
        logger.error(f"[Blinky] Failed to launch LEDBlinkyOutputTest.exe: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# =============================================================================
# 4-PLAYER CALIBRATION WIZARD (DEPRECATED)
# =============================================================================
# NOTE: This wizard saves to JSON which LEDBlinky cannot read ("Ghost Map").
# For production use, launch GenLEDBlinkyInputMap.exe via /blinky/tools/input-map
# These endpoints are kept for backwards compatibility but should not be used.

class WizardStartPayload(BaseModel):
    """Payload for starting calibration wizard."""
    total_ports: int = Field(default=96, ge=1, le=256)
    player_count: int = Field(default=4, ge=2, le=4)


class WizardConfirmPayload(BaseModel):
    """Payload for confirming a button mapping."""
    logical_id: str = Field(..., min_length=2, max_length=32, description="e.g., p1.b1, p2.start")
    description: str = Field(default="", max_length=100)


@router.get("/calibrate/wizard/status")
async def calibrate_wizard_status(request: Request) -> Dict[str, Any]:
    """Get current calibration wizard status."""
    require_scope(request, "state")
    return LEDCalibrationService.get_status().dict()


@router.post("/calibrate/wizard/start")
async def calibrate_wizard_start(request: Request, payload: WizardStartPayload) -> Dict[str, Any]:
    """
    Start a new 4-player LED calibration wizard session.
    
    This resets any existing session and begins blinking port 1.
    """
    require_scope(request, "config")
    
    session = await LEDCalibrationService.start_wizard(
        total_ports=payload.total_ports,
        player_count=payload.player_count
    )
    
    logger.info(f"[Calibration] Wizard started: {payload.total_ports} ports, {payload.player_count} players")
    
    return {
        "status": "started",
        "token": session.token,
        "current_port": session.current_port,
        "total_ports": session.total_ports,
        "player_count": session.player_count
    }


@router.post("/calibrate/wizard/confirm")
async def calibrate_wizard_confirm(request: Request, payload: WizardConfirmPayload) -> Dict[str, Any]:
    """
    Confirm which button corresponds to the currently blinking port.
    
    The user clicked a button in the GUI - record the mapping and advance.
    """
    require_scope(request, "config")
    
    try:
        session = await LEDCalibrationService.confirm_mapping(
            logical_id=payload.logical_id,
            description=payload.description
        )
        
        return {
            "status": "confirmed" if session.is_active else "complete",
            "mapped": payload.logical_id,
            "current_port": session.current_port,
            "mapped_count": len(session.mappings),
            "is_active": session.is_active
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/calibrate/wizard/skip")
async def calibrate_wizard_skip(request: Request) -> Dict[str, Any]:
    """
    Skip the current port (no LED visible or broken).
    """
    require_scope(request, "config")
    
    try:
        session = await LEDCalibrationService.skip_port()
        
        return {
            "status": "skipped" if session.is_active else "complete",
            "current_port": session.current_port,
            "skipped_count": len(session.skipped_ports),
            "is_active": session.is_active
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/calibrate/wizard/finish")
async def calibrate_wizard_finish(request: Request) -> Dict[str, Any]:
    """
    Finish the calibration wizard and save mappings to JSON.
    """
    require_scope(request, "config")
    
    result = await LEDCalibrationService.finish()
    logger.info(f"[Calibration] Wizard finished: {result}")
    return result


@router.post("/calibrate/wizard/cancel")
async def calibrate_wizard_cancel(request: Request) -> Dict[str, Any]:
    """
    Cancel the current calibration session without saving.
    """
    require_scope(request, "config")
    
    result = await LEDCalibrationService.cancel()
    logger.info("[Calibration] Wizard cancelled")
    return result

