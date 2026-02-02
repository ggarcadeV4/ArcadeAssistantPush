from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Deque, Dict, List, Optional

try:
    import psutil  # type: ignore

    HAS_PSUTIL = True
except Exception:  # pragma: no cover
    psutil = None  # type: ignore
    HAS_PSUTIL = False

try:
    from backend.services.usb_detector import (
        detect_arcade_boards,
        detect_usb_devices,
        USBBackendError,
        USBDetectionError,
        USBPermissionError,
    )

    HAS_USB_DETECTOR = True
except Exception:  # pragma: no cover
    detect_arcade_boards = detect_usb_devices = None  # type: ignore
    USBBackendError = USBDetectionError = USBPermissionError = Exception  # type: ignore
    HAS_USB_DETECTOR = False


FIVE_MINUTES_SECONDS = 300
SAMPLE_INTERVAL_SECONDS = 5
MAX_SAMPLES = FIVE_MINUTES_SECONDS // SAMPLE_INTERVAL_SECONDS


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_gb(value_bytes: float) -> float:
    return round(value_bytes / (1024**3), 2)


class SystemHealthService:
    def __init__(self) -> None:
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Performance / Timeseries
    # ------------------------------------------------------------------
    def _get_timeseries_store(self, app_state: Any) -> Deque[Dict[str, Any]]:
        container = app_state or self
        if not hasattr(container, "health_performance_samples"):
            setattr(container, "health_performance_samples", deque(maxlen=MAX_SAMPLES))
        store = getattr(container, "health_performance_samples")
        if store.maxlen != MAX_SAMPLES:
            new_store: Deque[Dict[str, Any]] = deque(store, maxlen=MAX_SAMPLES)
            setattr(container, "health_performance_samples", new_store)
            store = new_store
        return store

    def collect_performance_snapshot(self, app_state: Any) -> Dict[str, Any]:
        state = app_state or self
        timestamp = _iso_now()
        fps = 59.7
        latency_ms = 2.5
        frame_consistency = 98.1
        gpu_temp_c = None

        if not HAS_PSUTIL:
            snapshot = {
                "timestamp": timestamp,
                "psutil_available": False,
                "cpu": {"percent": None},
                "memory": {
                    "percent": None,
                    "total_bytes": None,
                    "used_bytes": None,
                    "used_gb": None,
                    "total_gb": None,
                },
                "fps": fps,
                "latency_ms": latency_ms,
                "frame_consistency": frame_consistency,
                "gpu_temp_c": gpu_temp_c,
            }
            self._append_sample(state, snapshot, fps, latency_ms)
            return snapshot

        cpu_percent = psutil.cpu_percent(interval=None)  # type: ignore[attr-defined]
        memory = psutil.virtual_memory()  # type: ignore[attr-defined]
        try:
            throughput = psutil.sensors_temperatures()  # type: ignore[attr-defined]
            for entries in throughput.values():
                for entry in entries:
                    if "gpu" in entry.label.lower() or "gpu" in entry.device.lower():
                        gpu_temp_c = float(entry.current)
                        break
        except Exception:
            gpu_temp_c = None

        snapshot = {
            "timestamp": timestamp,
            "psutil_available": True,
            "cpu": {"percent": cpu_percent},
            "memory": {
                "percent": memory.percent,
                "total_bytes": memory.total,
                "used_bytes": memory.used,
                "used_gb": _to_gb(memory.used),
                "total_gb": _to_gb(memory.total),
            },
            "uptime_seconds": max(0.0, datetime.now().timestamp() - psutil.boot_time()),  # type: ignore[attr-defined]
            "fps": fps,
            "latency_ms": latency_ms,
            "frame_consistency": frame_consistency,
            "gpu_temp_c": gpu_temp_c,
        }

        self._append_sample(state, snapshot, fps, latency_ms)
        return snapshot

    def _append_sample(self, app_state: Any, snapshot: Dict[str, Any], fps: float, latency_ms: float) -> None:
        sample = {
            "timestamp": snapshot["timestamp"],
            "cpu_percent": snapshot["cpu"]["percent"],
            "memory_percent": snapshot["memory"]["percent"],
            "fps": fps,
            "latency_ms": latency_ms,
        }
        store = self._get_timeseries_store(app_state)
        with self._lock:
            if store and self._seconds_between(store[-1]["timestamp"], sample["timestamp"]) < SAMPLE_INTERVAL_SECONDS:
                store[-1] = sample
            else:
                store.append(sample)

    def _seconds_between(self, iso_a: str, iso_b: str) -> float:
        try:
            dt_a = datetime.fromisoformat(iso_a)
            dt_b = datetime.fromisoformat(iso_b)
            return abs((dt_b - dt_a).total_seconds())
        except Exception:  # pragma: no cover
            return SAMPLE_INTERVAL_SECONDS

    def get_performance_timeseries(self, app_state: Any) -> List[Dict[str, Any]]:
        store = self._get_timeseries_store(app_state or self)
        with self._lock:
            return list(store)

    # ------------------------------------------------------------------
    # Processes
    # ------------------------------------------------------------------
    def collect_processes(self) -> Dict[str, Any]:
        timestamp = _iso_now()
        if not HAS_PSUTIL:
            return {"timestamp": timestamp, "psutil_available": False, "groups": []}

        groups: Dict[str, Dict[str, Any]] = {
            "gaming": {"id": "gaming", "title": "Gaming Processes", "processes": []},
            "assistant": {"id": "assistant", "title": "Assistant Services", "processes": []},
            "system": {"id": "system", "title": "System", "processes": []},
        }
        gaming_keywords = ("mame", "retroarch", "dolphin", "pcsx2", "cemu", "yuzu")
        assistant_keywords = ("launchbox", "ledblinky", "arcadeassistant", "fastapi", "node", "gateway", "gunner")

        for proc in psutil.process_iter(  # type: ignore[attr-defined]
            attrs=["pid", "name", "exe", "cpu_percent", "memory_info", "status", "cmdline"]
        ):
            name = (proc.info.get("name") or "").lower()
            exe = proc.info.get("exe") or (proc.info.get("cmdline") or [""])[0]
            group = "system"
            if any(keyword in name for keyword in gaming_keywords):
                group = "gaming"
            elif any(keyword in name for keyword in assistant_keywords):
                group = "assistant"

            cpu_percent = proc.info.get("cpu_percent") or 0.0
            mem_info = proc.info.get("memory_info")
            mem_bytes = getattr(mem_info, "rss", None)
            health_score = max(0.0, min(1.0, 1.0 - (cpu_percent / 100.0)))
            groups[group]["processes"].append(
                {
                    "pid": proc.info.get("pid"),
                    "name": proc.info.get("name"),
                    "path": exe,
                    "cpu_percent": cpu_percent,
                    "memory_bytes": mem_bytes,
                    "status": proc.info.get("status"),
                    "health": health_score,
                }
            )

        return {"timestamp": timestamp, "psutil_available": True, "groups": list(groups.values())}

    # ------------------------------------------------------------------
    # Hardware
    # ------------------------------------------------------------------
    def collect_hardware(self) -> Dict[str, Any]:
        timestamp = _iso_now()
        usb_backend = "unknown"
        error: Optional[str] = None
        controller_devices: List[Dict[str, Any]] = []
        usb_devices: List[Dict[str, Any]] = []

        if HAS_USB_DETECTOR:
            try:
                boards = detect_arcade_boards() or []  # type: ignore[operator]
                for board in boards:
                    controller_devices.append(
                        {
                            "id": f"{board.get('vendor_id')}:{board.get('product_id')}",
                            "name": board.get("name") or board.get("board_type") or "Arcade Board",
                            "status": "connected" if board.get("detected") else "disconnected",
                            "health": board.get("health"),
                            "metadata": board,
                        }
                    )
            except Exception as exc:  # pragma: no cover
                error = f"Arcade board detection failed: {exc}"

            try:
                devices = detect_usb_devices(include_unknown=False, use_cache=True) or []  # type: ignore[operator]
                for device in devices:
                    usb_devices.append(
                        {
                            "id": f"{device.get('vendor_id')}:{device.get('product_id')}",
                            "name": device.get("name") or f"{device.get('vendor')} device",
                            "status": "connected",
                            "health": 1.0,
                            "metadata": device,
                        }
                    )
                usb_backend = "available"
            except USBBackendError as exc:
                error = f"USB backend unavailable: {exc}"
                usb_backend = "backend_unavailable"
            except USBPermissionError as exc:
                error = f"USB permission denied: {exc}"
                usb_backend = "permission_denied"
            except USBDetectionError as exc:
                error = f"USB detection error: {exc}"
        else:
            error = "USB detector unavailable on this platform"
            usb_backend = "unavailable"

        controllers_placeholder = [
            {
                "id": "joystick-p1",
                "name": "Sanwa JLF Joystick P1",
                "status": "connected",
                "health": 0.94,
                "metrics": {"latency_ms": 0.8, "actuations": 2_847_563},
            },
            {
                "id": "trackball",
                "name": "Arcade Trackball",
                "status": "warning",
                "health": 0.78,
                "metrics": {"accuracy": 0.96, "friction": "medium"},
            },
        ]
        display_placeholder = [
            {
                "id": "crt-display",
                "name": '19" CRT Monitor',
                "status": "connected",
                "health": 0.89,
                "metrics": {"resolution": "640x480", "refresh_hz": 60, "hours": 12847},
            }
        ]

        categories = [
            {
                "id": "controllers",
                "title": "Controllers & Inputs",
                "devices": controller_devices or controllers_placeholder,
            },
            {
                "id": "usb",
                "title": "USB Devices",
                "devices": usb_devices,
            },
            {
                "id": "display",
                "title": "Display & Visual",
                "devices": display_placeholder,
            },
        ]

        status = "healthy" if error is None else "degraded"
        return {
            "timestamp": timestamp,
            "status": status,
            "usb_backend": usb_backend,
            "categories": categories,
            "error": error,
        }

    # ------------------------------------------------------------------
    # Alerts / Persistence
    # ------------------------------------------------------------------
    def _alert_file(self, drive_root: Path) -> Path:
        alerts_dir = drive_root / ".aa" / "state" / "system-health"
        alerts_dir.mkdir(parents=True, exist_ok=True)
        return alerts_dir / "alerts.json"

    def _load_alert_state(self, drive_root: Path) -> Dict[str, Any]:
        path = self._alert_file(drive_root)
        if not path.exists():
            return {"active": [], "history": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data.setdefault("active", [])
            data.setdefault("history", [])
            return data
        except Exception:
            return {"active": [], "history": []}

    def _save_alert_state(self, drive_root: Path, data: Dict[str, Any]) -> None:
        path = self._alert_file(drive_root)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def evaluate_dynamic_alerts(
        self, performance: Dict[str, Any], hardware: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        timestamp = performance.get("timestamp", _iso_now())

        cpu_percent = performance.get("cpu", {}).get("percent")
        if isinstance(cpu_percent, (int, float)) and cpu_percent >= 85:
            alerts.append(
                {
                    "id": "cpu-high",
                    "title": "High CPU Usage",
                    "message": f"CPU utilization at {cpu_percent:.1f}%",
                    "severity": "warning",
                    "detected_at": timestamp,
                    "source": "performance",
                }
            )

        memory_percent = performance.get("memory", {}).get("percent")
        if isinstance(memory_percent, (int, float)) and memory_percent >= 90:
            alerts.append(
                {
                    "id": "memory-high",
                    "title": "High Memory Usage",
                    "message": f"Memory usage at {memory_percent:.1f}%",
                    "severity": "warning",
                    "detected_at": timestamp,
                    "source": "performance",
                }
            )

        if hardware.get("status") == "degraded":
            alerts.append(
                {
                    "id": "hardware-degraded",
                    "title": "Hardware Detection Issues",
                    "message": hardware.get("error") or "Hardware subsystem degraded",
                    "severity": "warning",
                    "detected_at": hardware.get("timestamp", timestamp),
                    "source": "hardware",
                }
            )

        for category in hardware.get("categories", []):
            for device in category.get("devices", []):
                status = (device.get("status") or "").lower()
                if status in {"warning", "disconnected"}:
                    alerts.append(
                        {
                            "id": f"device-{device.get('id')}",
                            "title": f"{device.get('name') or 'Device'} Issue",
                            "message": f"{device.get('name') or 'Device'} status: {device.get('status')}",
                            "severity": "warning",
                            "detected_at": hardware.get("timestamp", timestamp),
                            "source": "hardware",
                        }
                    )
        return alerts

    def get_active_alerts(
        self, drive_root: Path, performance: Dict[str, Any], hardware: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        state = self._load_alert_state(drive_root)
        dismissed_ids = {
            entry.get("id")
            for entry in state.get("history", [])
            if entry.get("status") == "dismissed"
        }
        dynamic_alerts = [
            alert for alert in self.evaluate_dynamic_alerts(performance, hardware) if alert["id"] not in dismissed_ids
        ]
        state["active"] = dynamic_alerts
        self._save_alert_state(drive_root, state)
        return dynamic_alerts

    def get_alert_history(self, drive_root: Path) -> List[Dict[str, Any]]:
        state = self._load_alert_state(drive_root)
        return state.get("history", [])

    def dismiss_alert(self, drive_root: Path, alert_id: str, reason: Optional[str]) -> Dict[str, Any]:
        state = self._load_alert_state(drive_root)
        timestamp = _iso_now()
        active = state.get("active", [])
        remaining = [alert for alert in active if alert.get("id") != alert_id]
        dismissed_entry = next((alert for alert in active if alert.get("id") == alert_id), None)
        if not dismissed_entry:
            dismissed_entry = {"id": alert_id, "title": "Alert", "message": reason or "", "severity": "info"}
        dismissed_entry.update({"status": "dismissed", "dismissed_at": timestamp, "reason": reason})
        history = state.get("history", [])
        history.append(dismissed_entry)
        state["active"] = remaining
        state["history"] = history
        self._save_alert_state(drive_root, state)
        return dismissed_entry


health_service = SystemHealthService()
