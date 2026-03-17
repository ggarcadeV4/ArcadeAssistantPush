"""
Doc diagnostics router for the Doc system health persona.

Required endpoints:
    GET /api/doc/bio
    GET /api/doc/vitals
    GET /api/doc/alerts
    GET /api/doc/processes
    WS  /api/doc/ws/events
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from backend.services.identity_service import parse_vid_pid, scan_hardware_bio
from backend.services.system_health import health_service

try:
    import hid  # type: ignore

    HAS_HID = True
except Exception:  # pragma: no cover - environment dependent
    hid = None  # type: ignore
    HAS_HID = False

try:
    import psutil  # type: ignore

    HAS_PSUTIL = True
except Exception:  # pragma: no cover - environment dependent
    psutil = None  # type: ignore
    HAS_PSUTIL = False

try:
    import serial  # type: ignore
    import serial.tools.list_ports  # type: ignore

    HAS_SERIAL = True
except Exception:  # pragma: no cover - environment dependent
    serial = None  # type: ignore
    HAS_SERIAL = False


logger = logging.getLogger(__name__)

# Keep the router prefix empty so the existing app mount at /api/doc produces the
# user-facing contract path /api/doc/* and the standalone test app works as-is.
router = APIRouter(tags=["Doc Diagnostics"])

_ws_clients: Dict[str, WebSocket] = {}

__all__ = ["router", "broadcast_health_event"]

_DEVICE_LATENCY_BUDGET_SECONDS = 2.0
_DEVICE_PROBE_TIMEOUT_MS = 50
_DEFAULT_HID_REPORT_SIZE = 64


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_hardware_bio(scan_timestamp: Optional[str] = None) -> Dict[str, Any]:
    return {
        "devices": [],
        "device_count": 0,
        "scan_timestamp": scan_timestamp or _iso_now(),
    }


def _register_client(client_id: str, websocket: WebSocket) -> None:
    _ws_clients[client_id] = websocket
    logger.info("Doc WS client connected: %s (total=%d)", client_id, len(_ws_clients))


def _remove_client(client_id: str) -> None:
    if _ws_clients.pop(client_id, None) is not None:
        logger.info("Doc WS client disconnected: %s (total=%d)", client_id, len(_ws_clients))


async def broadcast_health_event(event: dict) -> int:
    """Broadcast a health event to connected Doc clients."""
    if not _ws_clients:
        return 0

    delivered = 0
    dead_clients: List[str] = []

    for client_id, websocket in list(_ws_clients.items()):
        try:
            await websocket.send_json(event)
            delivered += 1
        except Exception as exc:
            logger.warning("Doc WS send failed for %s: %s", client_id, exc)
            dead_clients.append(client_id)

    for client_id in dead_clients:
        _remove_client(client_id)

    return delivered


def _resolve_drive_root(request: Request, errors: List[str]) -> Optional[Path]:
    app_state = getattr(request.app, "state", None)
    state_store = getattr(app_state, "_state", {})
    configured_root = state_store.get("drive_root") if isinstance(state_store, dict) else None

    if configured_root is not None:
        try:
            return Path(configured_root)
        except Exception as exc:
            errors.append(f"drive_root on app.state is invalid: {exc}")
            return None

    env_drive_root = os.getenv("AA_DRIVE_ROOT", "A:/")
    errors.append(f"drive_root missing on app.state; fallback candidate is {env_drive_root}")
    return None


def _measure_drive_latency(drive_root: Path, errors: Optional[List[str]] = None) -> Optional[float]:
    probe_dir = drive_root / ".aa" / "state" / "system-health"
    probe_path = probe_dir / f".doc-latency-{uuid.uuid4().hex}.bin"
    payload = os.urandom(1024)

    try:
        probe_dir.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        probe_path.write_bytes(payload)
        readback = probe_path.read_bytes()
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)

        if readback != payload:
            raise IOError("drive latency probe readback mismatch")

        return elapsed_ms
    except Exception as exc:
        if errors is not None:
            errors.append(f"drive latency unavailable for {drive_root}: {exc}")
        logger.warning("Doc drive latency probe failed for %s: %s", drive_root, exc)
        return None
    finally:
        try:
            if probe_path.exists():
                probe_path.unlink()
        except Exception:
            pass


def _normalize_hex_id(value: Any) -> Optional[str]:
    if value is None:
        return None

    raw = str(value).strip().lower()
    if not raw:
        return None
    if raw.startswith("0x"):
        raw = raw[2:]

    try:
        parsed = int(raw, 16)
    except ValueError:
        return None

    return f"{parsed:04x}"


def _extract_device_vid_pid(device: Dict[str, Any]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    vid_pid = device.get("vid_pid")
    if isinstance(vid_pid, str) and ":" in vid_pid:
        vid, pid = vid_pid.split(":", 1)
        vid = _normalize_hex_id(vid)
        pid = _normalize_hex_id(pid)
        if vid and pid:
            return vid, pid, f"{vid}:{pid}"

    vid = _normalize_hex_id(device.get("vid"))
    pid = _normalize_hex_id(device.get("pid"))
    if vid and pid:
        return vid, pid, f"{vid}:{pid}"

    device_id = device.get("device_id")
    if isinstance(device_id, str):
        parsed = parse_vid_pid(device_id)
        if parsed and ":" in parsed:
            vid, pid = parsed.split(":", 1)
            vid = _normalize_hex_id(vid)
            pid = _normalize_hex_id(pid)
            if vid and pid:
                return vid, pid, f"{vid}:{pid}"

    return None, None, None


def _existing_device_latency_ms(device: Dict[str, Any]) -> Optional[float]:
    direct_latency = device.get("latency_ms")
    if isinstance(direct_latency, (int, float)):
        return round(float(direct_latency), 3)

    metrics = device.get("metrics")
    if isinstance(metrics, dict):
        metrics_latency = metrics.get("latency_ms")
        if isinstance(metrics_latency, (int, float)):
            return round(float(metrics_latency), 3)

    return None


def _enumerate_hid_probe_sources() -> Dict[str, List[Dict[str, Any]]]:
    probe_sources: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    if not HAS_HID or hid is None:
        return {}

    try:
        for info in hid.enumerate():
            vid = _normalize_hex_id(info.get("vendor_id"))
            pid = _normalize_hex_id(info.get("product_id"))
            path = info.get("path")
            if not vid or not pid or not path:
                continue

            probe_sources[f"{vid}:{pid}"].append(info)
    except Exception as exc:  # pragma: no cover - hardware dependent
        logger.debug("Doc HID enumeration failed: %s", exc)
        return {}

    return dict(probe_sources)


def _enumerate_serial_probe_sources() -> Dict[str, List[Any]]:
    probe_sources: Dict[str, List[Any]] = defaultdict(list)
    if not HAS_SERIAL or serial is None:
        return {}

    try:
        for port in serial.tools.list_ports.comports():  # type: ignore[attr-defined]
            vid = _normalize_hex_id(getattr(port, "vid", None))
            pid = _normalize_hex_id(getattr(port, "pid", None))
            if not vid or not pid:
                continue
            probe_sources[f"{vid}:{pid}"].append(port)
    except Exception as exc:  # pragma: no cover - hardware dependent
        logger.debug("Doc serial enumeration failed: %s", exc)
        return {}

    return dict(probe_sources)


def _probe_hid_latency(probe_info: Dict[str, Any], timeout_ms: int) -> Optional[float]:
    if not HAS_HID or hid is None or timeout_ms <= 0:
        return None

    path = probe_info.get("path")
    if not path:
        return None

    device = hid.device()
    try:
        device.open_path(path)
        started = time.perf_counter()
        data = device.read(_DEFAULT_HID_REPORT_SIZE, timeout_ms)
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        if not data:
            return None
        return elapsed_ms
    except Exception as exc:  # pragma: no cover - hardware dependent
        logger.debug("Doc HID latency probe failed: %s", exc)
        return None
    finally:
        try:
            device.close()
        except Exception:
            pass


def _probe_serial_latency(port_info: Any, timeout_ms: int) -> Optional[float]:
    if not HAS_SERIAL or serial is None or timeout_ms <= 0:
        return None

    device_name = getattr(port_info, "device", None)
    if not device_name:
        return None

    try:
        started = time.perf_counter()
        with serial.Serial(device_name, timeout=timeout_ms / 1000.0, write_timeout=timeout_ms / 1000.0) as connection:  # type: ignore[attr-defined]
            line = connection.readline()
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        if not line:
            return None
        return elapsed_ms
    except Exception as exc:  # pragma: no cover - hardware dependent
        logger.debug("Doc serial latency probe failed for %s: %s", device_name, exc)
        return None


def _measure_device_latency(
    device: Dict[str, Any],
    hid_sources: Dict[str, List[Dict[str, Any]]],
    serial_sources: Dict[str, List[Any]],
    deadline: float,
) -> Optional[float]:
    existing_latency = _existing_device_latency_ms(device)
    if existing_latency is not None:
        return existing_latency

    if time.perf_counter() >= deadline:
        return None

    _, _, vid_pid = _extract_device_vid_pid(device)
    if not vid_pid:
        return None

    while hid_sources.get(vid_pid):
        remaining_ms = int((deadline - time.perf_counter()) * 1000.0)
        if remaining_ms <= 0:
            return None

        probe_info = hid_sources[vid_pid].pop(0)
        latency_ms = _probe_hid_latency(probe_info, min(_DEVICE_PROBE_TIMEOUT_MS, remaining_ms))
        if latency_ms is not None:
            return latency_ms

    while serial_sources.get(vid_pid):
        remaining_ms = int((deadline - time.perf_counter()) * 1000.0)
        if remaining_ms <= 0:
            return None

        port_info = serial_sources[vid_pid].pop(0)
        latency_ms = _probe_serial_latency(port_info, min(_DEVICE_PROBE_TIMEOUT_MS, remaining_ms))
        if latency_ms is not None:
            return latency_ms

    return None


def _normalize_hardware_device(
    device: Dict[str, Any],
    latency_ms: Optional[float],
) -> Dict[str, Any]:
    normalized = dict(device)
    vid, pid, vid_pid = _extract_device_vid_pid(device)

    if vid_pid:
        normalized["vid_pid"] = vid_pid
    normalized["vid"] = vid
    normalized["pid"] = pid
    normalized.setdefault("status", "connected")
    normalized["latency_ms"] = latency_ms
    return normalized


def _attach_device_latency(devices: List[Dict[str, Any]], include_latency: bool) -> List[Dict[str, Any]]:
    if not devices:
        return []

    hid_sources = _enumerate_hid_probe_sources() if include_latency else {}
    serial_sources = _enumerate_serial_probe_sources() if include_latency else {}
    deadline = time.perf_counter() + _DEVICE_LATENCY_BUDGET_SECONDS

    normalized_devices: List[Dict[str, Any]] = []
    for device in devices:
        latency_ms = _existing_device_latency_ms(device)
        if latency_ms is None and include_latency and time.perf_counter() < deadline:
            latency_ms = _measure_device_latency(device, hid_sources, serial_sources, deadline)
        normalized_devices.append(_normalize_hardware_device(device, latency_ms))

    return normalized_devices


def _collect_psutil_metrics(errors: List[str]) -> Dict[str, Any]:
    metrics = {
        "cpu_percent": None,
        "memory_percent": None,
        "memory_used_gb": 0.0,
        "memory_total_gb": 0.0,
        "temperature_c": None,
    }

    if not HAS_PSUTIL or psutil is None:
        errors.append("psutil unavailable")
        return metrics

    try:
        cpu_percent = psutil.cpu_percent(interval=None)  # type: ignore[attr-defined]
        if isinstance(cpu_percent, (int, float)):
            metrics["cpu_percent"] = round(float(cpu_percent), 2)
    except Exception as exc:
        errors.append(f"cpu metric unavailable: {exc}")

    try:
        memory = psutil.virtual_memory()  # type: ignore[attr-defined]
        total_bytes = float(getattr(memory, "total", 0.0) or 0.0)
        used_bytes = float(getattr(memory, "used", 0.0) or 0.0)
        percent = getattr(memory, "percent", None)

        metrics["memory_used_gb"] = round(used_bytes / (1024**3), 2)
        metrics["memory_total_gb"] = round(total_bytes / (1024**3), 2)
        if isinstance(percent, (int, float)):
            metrics["memory_percent"] = round(float(percent), 2)
    except Exception as exc:
        errors.append(f"memory metric unavailable: {exc}")

    try:
        sensors_temperatures = getattr(psutil, "sensors_temperatures", None)
        if callable(sensors_temperatures):
            readings = sensors_temperatures() or {}
            preferred: List[float] = []
            fallback: List[float] = []

            for sensor_name, entries in readings.items():
                for entry in entries or []:
                    current = getattr(entry, "current", None)
                    if not isinstance(current, (int, float)):
                        continue

                    label = f"{sensor_name} {getattr(entry, 'label', '')}".lower()
                    if any(token in label for token in ("package", "cpu", "core", "tdie", "tctl", "temp")):
                        preferred.append(float(current))
                    else:
                        fallback.append(float(current))

            if preferred:
                metrics["temperature_c"] = round(preferred[0], 2)
            elif fallback:
                metrics["temperature_c"] = round(fallback[0], 2)
        else:
            errors.append("temperature metrics unavailable: psutil lacks sensors_temperatures")
    except Exception as exc:
        errors.append(f"temperature metric unavailable: {exc}")

    return metrics


def _collect_hardware_bio(errors: List[str], include_latency: bool = False) -> Dict[str, Any]:
    fallback = _empty_hardware_bio()

    try:
        bio = scan_hardware_bio()
    except Exception as exc:
        errors.append(f"hardware bio scan failed: {exc}")
        logger.warning("Hardware bio scan failed: %s", exc)
        return fallback

    if not isinstance(bio, dict):
        errors.append("hardware bio scan returned an invalid payload")
        return fallback

    raw_devices = bio.get("devices")
    if not isinstance(raw_devices, list):
        raw_devices = []

    devices = _attach_device_latency(raw_devices, include_latency)

    device_count = bio.get("device_count")
    if not isinstance(device_count, int):
        device_count = len(devices)

    scan_timestamp = bio.get("scan_timestamp")
    if not isinstance(scan_timestamp, str) or not scan_timestamp:
        scan_timestamp = _iso_now()

    scan_error = bio.get("error")
    if scan_error:
        errors.append(f"hardware bio scan error: {scan_error}")

    return {
        "devices": devices,
        "device_count": device_count,
        "scan_timestamp": scan_timestamp,
    }


def _build_alert_hardware_context(errors: List[str]) -> Dict[str, Any]:
    hardware_errors: List[str] = []
    hardware_bio = _collect_hardware_bio(hardware_errors)
    errors.extend(hardware_errors)

    devices = []
    for device in hardware_bio["devices"]:
        vid_pid = device.get("vid_pid")
        device_id = device.get("device_id")
        devices.append(
            {
                "id": vid_pid or device_id or uuid.uuid4().hex,
                "name": device.get("name") or "USB Device",
                "status": "connected",
                "metadata": device,
            }
        )

    return {
        "timestamp": hardware_bio["scan_timestamp"],
        "status": "degraded" if hardware_errors else "healthy",
        "categories": [
            {
                "id": "usb",
                "title": "USB Devices",
                "devices": devices,
            }
        ],
        "error": "; ".join(hardware_errors) if hardware_errors else None,
    }


@router.get("/bio")
async def get_bio() -> Dict[str, Any]:
    errors: List[str] = []
    hardware_bio = await asyncio.to_thread(_collect_hardware_bio, errors, True)
    response: Dict[str, Any] = dict(hardware_bio)
    if errors:
        response["errors"] = errors
    return response


@router.get("/vitals")
async def get_vitals(request: Request) -> Dict[str, Any]:
    errors: List[str] = []
    timestamp = _iso_now()
    hardware_bio = _empty_hardware_bio(timestamp)
    drive_latency_ms: Optional[float] = None
    metrics = {
        "cpu_percent": None,
        "memory_percent": None,
        "memory_used_gb": 0.0,
        "memory_total_gb": 0.0,
    }

    try:
        hardware_bio = await asyncio.to_thread(_collect_hardware_bio, errors, True)
        metrics = _collect_psutil_metrics(errors)

        drive_root = _resolve_drive_root(request, errors)
        if drive_root is None:
            errors.append("drive_root unavailable for drive latency probe")
        else:
            error_count_before_probe = len(errors)
            drive_latency_ms = _measure_drive_latency(drive_root, errors)
            if drive_latency_ms is None and len(errors) == error_count_before_probe:
                errors.append(f"drive latency unavailable for {drive_root}")
    except Exception as exc:
        logger.exception("Unexpected Doc vitals failure")
        errors.append(f"unexpected vitals failure: {exc}")

    return {
        "drive_latency_ms": drive_latency_ms,
        "cpu_percent": metrics["cpu_percent"],
        "memory_percent": metrics["memory_percent"],
        "memory_used_gb": float(metrics["memory_used_gb"]),
        "memory_total_gb": float(metrics["memory_total_gb"]),
        "temperature_c": metrics["temperature_c"],
        "hardware_bio": hardware_bio,
        "timestamp": timestamp,
        "errors": errors,
    }


@router.get("/alerts")
async def get_alerts(request: Request) -> Dict[str, Any]:
    errors: List[str] = []
    alerts: List[Dict[str, Any]] = []

    try:
        performance = health_service.collect_performance_snapshot(request.app.state)
    except Exception as exc:
        performance = {
            "timestamp": _iso_now(),
            "cpu": {"percent": None},
            "memory": {"percent": None},
        }
        errors.append(f"performance snapshot unavailable: {exc}")

    hardware = _build_alert_hardware_context(errors)

    drive_root = _resolve_drive_root(request, errors)
    if drive_root is not None:
        try:
            alerts = health_service.get_active_alerts(drive_root, performance, hardware)
        except Exception as exc:
            errors.append(f"alert evaluation failed: {exc}")
    else:
        try:
            alerts = health_service.evaluate_dynamic_alerts(performance, hardware)
        except Exception as exc:
            errors.append(f"dynamic alert evaluation failed: {exc}")

    return {
        "alerts": alerts,
        "timestamp": _iso_now(),
        "errors": errors,
    }


@router.get("/processes")
async def get_processes() -> Dict[str, Any]:
    return health_service.collect_processes()


@router.websocket("/ws/events")
async def doc_event_stream(websocket: WebSocket) -> None:
    client_id = uuid.uuid4().hex[:8]
    await websocket.accept()
    _register_client(client_id, websocket)

    try:
        await websocket.send_json(
            {
                "type": "connected",
                "client_id": client_id,
                "timestamp": _iso_now(),
            }
        )

        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                if message == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": _iso_now()})
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat", "timestamp": _iso_now()})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("Doc WS client %s error: %s", client_id, exc)
    finally:
        _remove_client(client_id)
