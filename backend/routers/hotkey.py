"""
Hotkey Router
WebSocket endpoint for broadcasting F9/A key events to frontend
"""

import os
import json
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


async def broadcast_hotkey_event():
    """Send hotkey event to all WebSocket clients"""
    manager = get_hotkey_manager()
    try:
        if not overlay_allowed_now():
            logger.info("[Hotkey WS] Overlay suppressed (no active emulator)")
            return
    except Exception as e:
        logger.warning(f"[Hotkey WS] overlay_allowed check failed: {e}")
    event = json.dumps({
        "type": "hotkey_pressed",
        "key": manager.hotkey.upper(),  # Use actual configured key (not hardcoded)
        "timestamp": datetime.utcnow().isoformat()
    })

    logger.info(f"[Hotkey WS] Broadcasting event to {len(active_connections)} client(s)")

    for connection in active_connections:
        try:
            await connection.send_text(event)
        except Exception as e:
            logger.error(f"[Hotkey WS] Failed to send to client: {e}")


@router.get("/health")
async def hotkey_health():
    """Health check endpoint with normalized keys."""
    manager = get_hotkey_manager()
    # Use manager's actual state, not env var (which may be cached differently)
    is_enabled = manager.is_active
    return {
        "enabled": is_enabled,
        "key": (manager.hotkey or "").upper(),
        "ws_clients": len(active_connections),
        # Back-compat fields (do not rely on these in new clients)
        "service": "hotkey",
        "status": "active" if manager.is_active else "inactive",
        "feature_enabled": is_enabled,
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
