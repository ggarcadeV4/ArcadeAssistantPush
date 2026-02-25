"""Doc Diagnostics Router — Cabinet vitals endpoint.

Exposes ``GET /vitals`` returning drive latency, CPU/RAM load, and the
hardware bio from the Identity Service.  All paths resolve through
``request.app.state.drive_root`` — zero hardcoded drive letters.

Part of Phase 4: Agentic Repair & Self-Healing Launch.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request

from backend.services.identity_service import scan_hardware_bio

logger = logging.getLogger(__name__)

router = APIRouter()


def _measure_drive_latency(drive_root: Path) -> Optional[float]:
    """Write 1 KB then read it back; return elapsed ms or None on failure."""
    probe_dir = drive_root / ".aa" / "tmp"
    probe_file = probe_dir / "latency_probe.bin"
    try:
        probe_dir.mkdir(parents=True, exist_ok=True)
        payload = os.urandom(1024)
        t0 = time.perf_counter()
        probe_file.write_bytes(payload)
        _ = probe_file.read_bytes()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return round(elapsed_ms, 2)
    except Exception as exc:
        logger.warning("Drive latency test failed: %s", exc)
        return None
    finally:
        try:
            probe_file.unlink(missing_ok=True)
        except Exception:
            pass


def _get_system_load() -> Dict[str, Optional[float]]:
    """Return CPU and memory stats via psutil, or nulls if unavailable."""
    try:
        import psutil
    except ImportError:
        return {
            "cpu_percent": None,
            "memory_percent": None,
            "memory_used_gb": None,
            "memory_total_gb": None,
            "error": "psutil is not installed",
        }

    try:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        return {
            "cpu_percent": cpu,
            "memory_percent": mem.percent,
            "memory_used_gb": round(mem.used / (1024 ** 3), 2),
            "memory_total_gb": round(mem.total / (1024 ** 3), 2),
            "error": None,
        }
    except Exception as exc:
        logger.warning("psutil collection failed: %s", exc)
        return {
            "cpu_percent": None,
            "memory_percent": None,
            "memory_used_gb": None,
            "memory_total_gb": None,
            "error": f"psutil error: {exc}",
        }


@router.get("/vitals")
async def get_vitals(request: Request) -> Dict[str, Any]:
    """Return cabinet health telemetry.

    Response shape::

        {
            "drive_latency_ms": float | null,
            "cpu_percent": float | null,
            "memory_percent": float | null,
            "memory_used_gb": float | null,
            "memory_total_gb": float | null,
            "hardware_bio": { ... },
            "timestamp": str,
            "errors": [str]
        }
    """
    errors: List[str] = []
    drive_root: Optional[Path] = getattr(request.app.state, "drive_root", None)

    # Drive latency
    drive_latency_ms: Optional[float] = None
    if drive_root:
        drive_latency_ms = _measure_drive_latency(drive_root)
        if drive_latency_ms is None:
            errors.append("Drive latency test failed — drive root may be inaccessible")
    else:
        errors.append("drive_root not configured on app.state")

    # CPU / RAM
    sys_load = _get_system_load()
    if sys_load.get("error"):
        errors.append(sys_load["error"])

    # Hardware bio
    hardware_bio = scan_hardware_bio(drive_root=drive_root)
    if hardware_bio.get("error"):
        errors.append(hardware_bio["error"])

    return {
        "drive_latency_ms": drive_latency_ms,
        "cpu_percent": sys_load.get("cpu_percent"),
        "memory_percent": sys_load.get("memory_percent"),
        "memory_used_gb": sys_load.get("memory_used_gb"),
        "memory_total_gb": sys_load.get("memory_total_gb"),
        "hardware_bio": hardware_bio,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "errors": errors,
    }
