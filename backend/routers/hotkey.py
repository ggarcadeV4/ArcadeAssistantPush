"""
Hotkey Router
WebSocket endpoint for broadcasting F9/A key events to frontend
"""

import os
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.services.hotkey_manager import get_hotkey_manager
from backend.services.activity_guard import overlay_allowed_now
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hotkey", tags=["hotkey"])

# Active WebSocket connections
active_connections: List[WebSocket] = []
_last_overlay_boot_ms = 0
_hotkey_event_count = 0
_last_hotkey_event_at = ""
_last_overlay_boot_note = ""
_last_overlay_boot_at = ""
_last_overlay_boot_success = False
_last_block_reason = ""


def _guard_enabled() -> bool:
    """Whether to enforce activity guard before broadcasting hotkey events."""
    return os.getenv("HOTKEY_ENFORCE_ACTIVITY_GUARD", "false").lower() in {"1", "true", "yes"}


def _ensure_dewey_overlay_sidecar() -> tuple[bool, str]:
    """Best-effort overlay bootstrap for F9 when Electron HUD is not running."""
    global _last_overlay_boot_ms

    enabled = os.getenv("AA_HOTKEY_BOOT_DEWEY_OVERLAY", "true").lower() in {"1", "true", "yes"}
    if not enabled:
        return False, "disabled by AA_HOTKEY_BOOT_DEWEY_OVERLAY"

    if os.name != "nt":
        return False, "unsupported on non-Windows host"

    now = int(time.time() * 1000)
    if now - _last_overlay_boot_ms < 3000:
        return False, "boot throttled"
    _last_overlay_boot_ms = now

    repo_root = Path(__file__).resolve().parents[2]
    overlay_entry = repo_root / "frontend" / "electron" / "main.cjs"
    if not overlay_entry.exists():
        return False, f"overlay entry missing: {overlay_entry}"

    candidates = [
        [str(repo_root / "frontend" / "node_modules" / ".bin" / "electron.cmd"), str(overlay_entry)],
        ["electron", str(overlay_entry)],
    ]

    create_new_process_group = 0x00000200
    detached_process = 0x00000008
    last_error = None

    for cmd in candidates:
        exe = cmd[0]
        if exe.lower().endswith("electron.cmd") and not Path(exe).exists():
            continue
        try:
            subprocess.Popen(
                cmd,
                cwd=str(repo_root),
                creationflags=create_new_process_group | detached_process,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True, f"started via: {exe}"
        except Exception as e:
            last_error = e

    return False, f"failed to start overlay: {last_error}"


@router.websocket("/ws")
async def hotkey_websocket(websocket: WebSocket):
    """Stream hotkey events to connected clients"""
    await websocket.accept()
    active_connections.append(websocket)
    logger.info(f"[Hotkey WS] Client connected (total: {len(active_connections)})")

    try:
        # Keep connection alive
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        logger.info(f"[Hotkey WS] Client disconnected (total: {len(active_connections)})")


async def _emit_hotkey_event(apply_activity_guard: bool) -> bool:
    """Emit a hotkey event to all WS clients. Returns True if broadcast occurred."""
    global _hotkey_event_count, _last_hotkey_event_at
    global _last_overlay_boot_note, _last_overlay_boot_at, _last_overlay_boot_success
    global _last_block_reason

    manager = get_hotkey_manager()

    if apply_activity_guard:
        try:
            if not overlay_allowed_now():
                _last_block_reason = "overlay_suppressed_by_activity_guard"
                logger.info("[Hotkey WS] Overlay suppressed (activity guard)")
                return False
        except Exception as e:
            _last_block_reason = f"activity_guard_error:{e}"
            logger.warning(f"[Hotkey WS] activity guard check failed: {e}")
            return False

    _last_block_reason = ""

    should_boot_overlay = len(active_connections) == 0
    if should_boot_overlay:
        booted, boot_note = _ensure_dewey_overlay_sidecar()
    else:
        booted, boot_note = False, "overlay already connected"
    _last_overlay_boot_success = bool(booted)
    _last_overlay_boot_note = boot_note
    _last_overlay_boot_at = datetime.utcnow().isoformat()
    if booted:
        logger.info(f"[Hotkey WS] Dewey overlay bootstrap: {boot_note}")

    _hotkey_event_count += 1
    _last_hotkey_event_at = datetime.utcnow().isoformat()

    event = json.dumps({
        "type": "hotkey_pressed",
        "key": manager.hotkey.upper(),
        "timestamp": datetime.utcnow().isoformat()
    })

    logger.info(f"[Hotkey WS] Broadcasting event to {len(active_connections)} client(s)")

    for connection in active_connections:
        try:
            await connection.send_text(event)
        except Exception as e:
            logger.error(f"[Hotkey WS] Failed to send to client: {e}")

    return True


async def broadcast_hotkey_event():
    """Send hotkey event to all WebSocket clients."""
    await _emit_hotkey_event(apply_activity_guard=_guard_enabled())


@router.get("/health")
async def hotkey_health():
    """Health check endpoint with normalized keys."""
    manager = get_hotkey_manager()
    is_enabled = manager.is_active
    return {
        "enabled": is_enabled,
        "key": (manager.hotkey or "").upper(),
        "ws_clients": len(active_connections),
        "event_count": _hotkey_event_count,
        "last_event_at": _last_hotkey_event_at,
        "last_overlay_boot_success": _last_overlay_boot_success,
        "last_overlay_boot_note": _last_overlay_boot_note,
        "last_overlay_boot_at": _last_overlay_boot_at,
        "activity_guard_enabled": _guard_enabled(),
        "last_block_reason": _last_block_reason,
        # Back-compat fields
        "service": "hotkey",
        "status": "active" if manager.is_active else "inactive",
        "feature_enabled": is_enabled,
    }


@router.post("/trigger")
async def trigger_hotkey_event():
    """Manual diagnostic trigger for the hotkey chain (no keyboard press required)."""
    broadcasted = await _emit_hotkey_event(apply_activity_guard=False)
    health = await hotkey_health()
    health["trigger_broadcasted"] = broadcasted
    return health


@router.post("/bootstrap-overlay")
async def bootstrap_overlay():
    """Manual diagnostic overlay bootstrap."""
    booted, note = _ensure_dewey_overlay_sidecar()
    return {
        "ok": True,
        "booted": booted,
        "note": note,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.on_event("startup")
async def startup_event():
    """Start hotkey detection on backend startup"""
    if os.getenv("V2_HOTKEY_LAUNCHER", "false").lower() == "true":
        try:
            manager = get_hotkey_manager()
            manager.register_callback(broadcast_hotkey_event)
            await manager.start()
            logger.info("[Hotkey] Service started successfully")
        except Exception as e:
            logger.error(f"[Hotkey] Failed to start service: {e}")
            logger.error("[Hotkey] Make sure backend is running as Administrator")
    else:
        logger.info("[Hotkey] Service disabled (V2_HOTKEY_LAUNCHER=false)")


@router.on_event("shutdown")
async def shutdown_event():
    """Stop hotkey detection on backend shutdown"""
    if os.getenv("V2_HOTKEY_LAUNCHER", "false").lower() == "true":
        manager = get_hotkey_manager()
        manager.stop()
        logger.info("[Hotkey] Service stopped")