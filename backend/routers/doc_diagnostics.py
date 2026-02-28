"""
Doc Diagnostics Router — Hardware Bio & Vital Signs for Doc persona.

Endpoints:
    GET  /api/doc/bio     — Hardware Bio (USB/HID inventory, encoder signatures)
    GET  /api/doc/vitals  — Vital Signs (CPU, memory, thermal, drive I/O)
    GET  /api/doc/alerts  — Active health alerts
    WS   /api/doc/ws/events — Real-time health event broadcast

@persona: Doc (The Physician)
@owner: Arcade Assistant / Agentic Repair Ecosystem
@status: active
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from backend.services.identity_service import scan_hardware_bio
from backend.services.system_health import health_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/doc", tags=["Doc Diagnostics"])

# ─────────────────────────────────────────────────────────
# WebSocket client registry for health event broadcasting
# ─────────────────────────────────────────────────────────
_ws_clients: Dict[str, WebSocket] = {}


def _register_client(client_id: str, ws: WebSocket) -> None:
    _ws_clients[client_id] = ws
    logger.info(f"Doc WS client connected: {client_id} (total: {len(_ws_clients)})")


def _remove_client(client_id: str) -> None:
    _ws_clients.pop(client_id, None)
    logger.info(f"Doc WS client disconnected: {client_id} (total: {len(_ws_clients)})")


async def broadcast_health_event(event: Dict[str, Any]) -> int:
    """
    Broadcast a health event to all connected Doc WebSocket clients.
    
    Used by other services (LoRa remediation, identity changes) to push
    real-time alerts to the frontend.
    
    Returns:
        Number of clients that received the event.
    """
    if not _ws_clients:
        return 0

    payload = json.dumps(event)
    dead: List[str] = []
    sent = 0

    for client_id, ws in _ws_clients.items():
        try:
            await ws.send_text(payload)
            sent += 1
        except Exception:
            dead.append(client_id)

    for cid in dead:
        _remove_client(cid)

    return sent


# ─────────────────────────────────────────────────────────
# REST Endpoints
# ─────────────────────────────────────────────────────────

@router.get("/bio")
async def get_bio():
    """
    Hardware Bio — USB/HID inventory with encoder signatures.

    Returns VID/PID for all detected arcade boards and USB devices,
    plus a deterministic hardware fingerprint.
    """
    try:
        bio = scan_hardware_bio()
        return {
            "status": "ok",
            "hardware_bio": bio,
        }
    except Exception as e:
        logger.error(f"Hardware Bio scan failed: {e}")
        raise HTTPException(status_code=500, detail=f"Hardware Bio scan failed: {e}")


@router.get("/vitals")
async def get_vitals(request: Request):
    """
    Vital Signs — CPU, memory, thermal, drive I/O health.
    
    Phase 4.1 Directive:
    - Drive Latency: Ping Golden Drive (AA_DRIVE_ROOT)
    - Thermal State: Capture CPU/GPU temps
    - Encoder Match: Match against Pacto Tech signatures
    - Broadcast Hook: Push to ScoreKeeper WebSocket
    """
    import httpx
    import time
    from datetime import datetime
    import psutil

    drive_root: Optional[Path] = getattr(request.app.state, "drive_root", None)
    if not drive_root:
        # Fallback to env if app state not hydrated
        drive_root = Path(os.getenv("AA_DRIVE_ROOT", "C:/AI-Hub"))

    # 1. Drive Latency Probe (High-res IO ping)
    latency_ms = -1.0
    try:
        test_file = drive_root / ".aa" / "logs" / "diagnostics" / ".doc_ping"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        start = time.perf_counter()
        test_file.write_bytes(os.urandom(1024))
        _ = test_file.read_bytes()
        test_file.unlink()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
    except Exception as e:
        logger.error(f"Doc drive latency probe failed: {e}")

    # 2. Thermal State Sensing
    thermals = {}
    try:
        # psutil thermal scan
        if hasattr(psutil, "sensors_temperatures"):
            st = psutil.sensors_temperatures()
            for name, entries in st.items():
                if entries:
                    thermals[name] = entries[0].current
    except Exception:
        pass

    # 3. Encoder Match (Pacto Tech)
    bio = scan_hardware_bio()
    sigs = [s.lower() for s in bio.get("signatures", [])]
    # KNOWN Pacto Tech IDs (04D8:EF7F, 1234:5678, atc.)
    PACTO_IDS = ["04d8:ef7f", "1234:5678", "0d62:0001", "0d62:0002", "0d62:0003"]
    pacto_matches = [s for s in sigs if s in PACTO_IDS or s.startswith("04d8:")]
    
    vitals = {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "drive_latency_ms": latency_ms,
        "thermal": thermals or {"status": "unsupported"},
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "pacto_match": {
            "found": len(pacto_matches) > 0,
            "count": len(pacto_matches),
            "signatures": pacto_matches
        },
        "drive_path": str(drive_root)
    }

    # 4. Broadcast Hook (ScoreKeeper WebSocket)
    # Gateway localhost:8787 expects JSON broadcasts
    GATEWAY_BROADCAST_URL = "http://localhost:8787/api/scorekeeper/broadcast"
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                GATEWAY_BROADCAST_URL,
                json={
                    "type": "diagnostic_pulse",
                    "source": "doc",
                    "data": vitals
                },
                timeout=1.0
            )
    except Exception as e:
        logger.warning(f"ScoreKeeper broadcast failed: {e}")

    return vitals


@router.get("/alerts")
async def get_alerts(request: Request):
    """
    Active health alerts — CPU spikes, thermal warnings, drive issues.

    Uses SystemHealthService dynamic alert evaluation.
    """
    try:
        drive_root: Optional[Path] = getattr(request.app.state, "drive_root", None)
        if not drive_root:
            raise HTTPException(status_code=503, detail="Drive root not configured")

        performance = health_service.collect_performance_snapshot(request.app.state)
        hardware = health_service.collect_hardware()

        alerts = health_service.get_active_alerts(drive_root, performance, hardware)

        return {
            "status": "ok",
            "alerts": alerts,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Alert evaluation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Alert evaluation failed: {e}")


# ─────────────────────────────────────────────────────────
# WebSocket — Real-time health event stream
# ─────────────────────────────────────────────────────────

@router.websocket("/ws/events")
async def doc_event_stream(websocket: WebSocket):
    """
    Real-time health event broadcast.

    Frontend connects here to receive:
    - Hardware detection events (new board plugged in)
    - Vital sign alerts (CPU spike, thermal warning)
    - Remediation events from LoRa (launch fix applied)
    """
    import uuid

    client_id = str(uuid.uuid4())[:8]
    await websocket.accept()
    _register_client(client_id, websocket)

    try:
        # Send initial handshake
        await websocket.send_json({
            "type": "connected",
            "client_id": client_id,
            "message": "Doc event stream active",
        })

        # Keep connection alive — events are pushed via broadcast_health_event()
        while True:
            try:
                # Listen for client messages (ping/pong, unsubscribe, etc.)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_json({"type": "heartbeat"})

    except WebSocketDisconnect:
        logger.info(f"Doc WS client {client_id} disconnected")
    except Exception as e:
        logger.error(f"Doc WS error for {client_id}: {e}")
    finally:
        _remove_client(client_id)
