"""Hardware Detection Router

REST endpoints for USB device and arcade board detection.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Request, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..services.usb_detector import (
    detect_usb_devices,
    detect_arcade_boards,
    get_board_by_vid_pid,
    get_supported_boards,
    get_connection_troubleshooting_hints,
    invalidate_cache,
    USBDetectionError,
    USBBackendError,
    USBPermissionError
)

logger = logging.getLogger(__name__)
router = APIRouter()
ENCODER_EVENTS_WS_PATH = "/ws/encoder-events"
ENCODER_POLL_INTERVAL_SECONDS = 2.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_board_entry(board: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": board.get("name") or board.get("board_name") or "Unknown Board",
        "vid": board.get("vid"),
        "pid": board.get("pid"),
        "detected": bool(board.get("detected", False)),
        "status": board.get("status") or ("connected" if board.get("detected") else "offline"),
        "manufacturer": board.get("manufacturer"),
        "board_type": board.get("board_type") or board.get("type"),
        "device_id": board.get("device_id"),
        "interface": board.get("interface"),
        # Additive topology pass-through (populated when encoder_detector's
        # canonical topology helper inferred a Pacto_2000T / Pacto_4000T /
        # Standalone_XInput identity). All None for non-topology entries —
        # frontend consumers that don't read them ignore them.
        "players": board.get("players"),
        "parent_hub": board.get("parent_hub"),
        "xinput_nodes": board.get("xinput_nodes"),
    }


def _build_encoder_snapshot() -> Dict[str, Any]:
    boards = detect_arcade_boards()
    normalized_boards = [_normalize_board_entry(board) for board in boards]
    detected_boards = [board for board in normalized_boards if board.get("detected")]
    primary_board = detected_boards[0] if detected_boards else (normalized_boards[0] if normalized_boards else None)

    return {
        "timestamp": _utc_now(),
        "source": "usb_poll",
        "boards": normalized_boards,
        "count": len(normalized_boards),
        "detected_count": len(detected_boards),
        "primary_board": primary_board,
    }


def _snapshot_signature(snapshot: Dict[str, Any]) -> str:
    stable_payload = {
        "boards": snapshot.get("boards", []),
        "count": snapshot.get("count", 0),
        "detected_count": snapshot.get("detected_count", 0),
        "primary_board": snapshot.get("primary_board"),
    }
    return json.dumps(stable_payload, sort_keys=True)


class USBDeviceResponse(BaseModel):
    """Response model for USB device information"""
    devices: List[Dict[str, Any]]
    count: int
    cache_used: bool = False


class BoardDetectionResponse(BaseModel):
    """Response model for arcade board detection"""
    boards: List[Dict[str, Any]]
    count: int
    detected_count: int


class TroubleshootingResponse(BaseModel):
    """Response model for troubleshooting hints"""
    hints: List[str]
    board_type: str
    os_type: str


@router.websocket(ENCODER_EVENTS_WS_PATH)
async def encoder_events_stream(websocket: WebSocket):
    """Small, real websocket termination for encoder/USB board state.

    There is no push-native hardware event bus in the current USB detection layer,
    so this endpoint truthfully polls the existing detector and emits:
    - `HARDWARE_STATE_UPDATE` on connect and whenever the snapshot changes
    - `HARDWARE_HEARTBEAT` while the connection is idle
    - `HARDWARE_ERROR` if polling fails
    """
    await websocket.accept()
    await websocket.send_json({
        "event": "HARDWARE_CONNECTED",
        "data": {
            "timestamp": _utc_now(),
            "path": ENCODER_EVENTS_WS_PATH,
            "source": "usb_poll",
        },
    })

    last_signature = None
    last_error = None

    try:
        while True:
            try:
                snapshot = await run_in_threadpool(_build_encoder_snapshot)
                signature = _snapshot_signature(snapshot)
                if signature != last_signature:
                    await websocket.send_json({
                        "event": "HARDWARE_STATE_UPDATE",
                        "data": snapshot,
                    })
                    last_signature = signature
                    last_error = None
                else:
                    await websocket.send_json({
                        "event": "HARDWARE_HEARTBEAT",
                        "data": {
                            "timestamp": snapshot["timestamp"],
                            "source": snapshot["source"],
                            "count": snapshot["count"],
                            "detected_count": snapshot["detected_count"],
                        },
                    })
            except USBDetectionError as exc:
                error_message = str(exc)
                logger.warning("Encoder websocket poll failed: %s", error_message)
                if error_message != last_error:
                    await websocket.send_json({
                        "event": "HARDWARE_ERROR",
                        "message": error_message,
                        "data": {
                            "timestamp": _utc_now(),
                            "source": "usb_poll",
                        },
                    })
                    last_error = error_message

            try:
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=ENCODER_POLL_INTERVAL_SECONDS,
                )
                if message == "ping":
                    await websocket.send_json({
                        "event": "HARDWARE_HEARTBEAT",
                        "data": {
                            "timestamp": _utc_now(),
                            "source": "ping",
                        },
                    })
            except asyncio.TimeoutError:
                continue
    except WebSocketDisconnect:
        logger.info("Encoder events websocket disconnected")


@router.get("/usb/devices", response_model=USBDeviceResponse)
async def get_usb_devices(
    include_unknown: bool = Query(default=False, description="Include unrecognized USB devices"),
    use_cache: bool = Query(default=True, description="Use cached results if available")
):
    """Get all connected USB devices

    Returns detected USB devices with VID/PID, vendor, and device type information.
    Known arcade boards are automatically identified.

    Query Parameters:
        - include_unknown: Include devices not in the known boards database
        - use_cache: Use cached results (5-second TTL) for performance

    Returns:
        List of USB devices with metadata
    """
    try:
        devices = detect_usb_devices(include_unknown=include_unknown, use_cache=use_cache)

        return USBDeviceResponse(
            devices=devices,
            count=len(devices),
            cache_used=use_cache
        )

    except USBBackendError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "usb_backend_unavailable",
                "message": str(e),
                "hints": get_connection_troubleshooting_hints()[:3]
            }
        )
    except USBPermissionError as e:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "usb_permission_denied",
                "message": str(e),
                "hints": ["Run as administrator/root", "Add user to plugdev group (Linux)"]
            }
        )
    except USBDetectionError as e:
        logger.error(f"USB detection failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "usb_detection_failed",
                "message": str(e)
            }
        )


@router.get("/arcade/boards", response_model=BoardDetectionResponse)
async def get_arcade_boards():
    """Get all connected arcade controller boards

    Returns only known arcade hardware (I-PAC, PacDrive, etc.).
    This is a filtered view of the USB devices endpoint.

    Returns:
        List of detected arcade boards with connection status
    """
    try:
        boards = detect_arcade_boards()
        detected_count = sum(1 for b in boards if b.get("detected", False))

        return BoardDetectionResponse(
            boards=boards,
            count=len(boards),
            detected_count=detected_count
        )

    except USBDetectionError as e:
        # Return empty list on detection failure (non-critical for this endpoint)
        logger.warning(f"Arcade board detection failed: {e}")
        return BoardDetectionResponse(
            boards=[],
            count=0,
            detected_count=0
        )


@router.get("/arcade/boards/supported")
async def get_supported_arcade_boards():
    """Get list of all supported arcade boards

    Returns complete database of known arcade controller boards,
    regardless of connection status. Useful for manual board selection.

    Returns:
        List of all supported boards with VID/PID and capabilities
    """
    try:
        boards = get_supported_boards()
        return {
            "boards": boards,
            "count": len(boards),
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Failed to get supported boards: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve supported boards: {str(e)}"
        )


@router.get("/arcade/board/{vid}/{pid}")
async def get_board_status(vid: str, pid: str):
    """Get connection status for a specific board by VID/PID

    Args:
        vid: Vendor ID (hex format like 'd209' or '0xd209')
        pid: Product ID (hex format like '0501' or '0x0501')

    Returns:
        Board information if connected, 404 if not found or not connected
    """
    try:
        board = get_board_by_vid_pid(vid, pid)

        if board is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "board_not_found",
                    "message": f"Board {vid}:{pid} not connected or not supported",
                    "vid": vid,
                    "pid": pid
                }
            )

        return {
            "board": board,
            "status": "connected"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check board status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Board status check failed: {str(e)}"
        )


@router.post("/usb/invalidate-cache")
async def invalidate_usb_cache():
    """Invalidate the USB device detection cache

    Forces the next USB detection call to re-enumerate devices.
    Use this when you know the USB configuration has changed
    (device plugged/unplugged).

    Returns:
        Success confirmation
    """
    try:
        invalidate_cache()
        return {
            "status": "cache_invalidated",
            "message": "USB device cache cleared. Next detection will re-enumerate."
        }
    except Exception as e:
        logger.error(f"Failed to invalidate cache: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Cache invalidation failed: {str(e)}"
        )


@router.get("/troubleshooting", response_model=TroubleshootingResponse)
async def get_troubleshooting(
    board_type: str = Query(default="keyboard_encoder", description="Board type for specific hints"),
    os_type: Optional[str] = Query(default=None, description="OS type (auto-detected if not provided)")
):
    """Get troubleshooting hints for board connection issues

    Returns platform-specific and board-type-specific troubleshooting advice
    for resolving USB connection problems.

    Query Parameters:
        - board_type: Type of board (keyboard_encoder, led_controller, gamepad, unknown)
        - os_type: Operating system (Windows, Linux, Darwin) - auto-detected if not provided

    Returns:
        List of troubleshooting hints
    """
    try:
        import platform as plat

        hints = get_connection_troubleshooting_hints(
            board_type=board_type,
            os_type=os_type
        )

        return TroubleshootingResponse(
            hints=hints,
            board_type=board_type,
            os_type=os_type or plat.system()
        )

    except Exception as e:
        logger.error(f"Failed to get troubleshooting hints: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve troubleshooting hints: {str(e)}"
        )


# Health check endpoint for hardware router
@router.get("/health")
async def hardware_health_check():
    """Health check for hardware detection subsystem

    Returns:
        System status and USB backend availability
    """
    import platform as plat

    try:
        # Try to detect devices to verify backend is working
        detect_usb_devices(include_unknown=False, use_cache=False)
        backend_status = "available"
        error_message = None

    except USBBackendError as e:
        backend_status = "backend_unavailable"
        error_message = str(e)

    except USBPermissionError as e:
        backend_status = "permission_denied"
        error_message = str(e)

    except USBDetectionError as e:
        backend_status = "detection_error"
        error_message = str(e)

    return {
        "status": "healthy" if backend_status == "available" else "degraded",
        "usb_backend": backend_status,
        "platform": plat.system(),
        "error": error_message
    }
