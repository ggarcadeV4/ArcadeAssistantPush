from fastapi import APIRouter, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from typing import Any, Dict, List
from datetime import datetime, timezone
from pathlib import Path
import time

from backend.startup_manager import initialize_app_state
from backend.constants.paths import Paths
from backend.services.cabinet_identity import load_cabinet_identity

try:
    import psutil  # type: ignore
    HAS_PSUTIL = True
except Exception:
    psutil = None
    HAS_PSUTIL = False

router = APIRouter(prefix="/api/system", tags=["system"])
local_router = APIRouter(prefix="/api/local/system", tags=["system"])


@router.post("/manifest/reload")
async def manifest_reload(request: Request) -> Dict[str, Any]:
    await initialize_app_state(request.app)
    m = getattr(request.app.state, "manifest", {}) or {}
    dr = str(getattr(request.app.state, "drive_root", ""))
    return {
        "success": True,
        "drive_root": dr,
        "sanctioned_paths": m.get("sanctioned_paths", []),
    }


def _disk_usage(path: Path) -> Dict[str, Any]:
    try:
        usage = psutil.disk_usage(str(path))
        return {
            "path": str(path),
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "percent_used": usage.percent,
        }
    except Exception as exc:
        return {
            "path": str(path),
            "error": str(exc),
        }


def _collect_system_metrics() -> Dict[str, Any]:
    if not HAS_PSUTIL:
        raise RuntimeError("psutil is not installed in this environment")

    cpu_percent = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory()
    uptime_seconds = max(0.0, time.time() - psutil.boot_time())

    drive_targets: List[Path] = []
    try:
        drive_targets.append(Paths.DRIVE_ROOT)
    except Exception:
        pass
    drive_targets.append(Path("C:/"))

    drives = []
    seen = set()
    for drive in drive_targets:
        key = str(drive)
        if key.lower() in seen:
            continue
        seen.add(key.lower())
        drives.append(_disk_usage(drive))

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cpu": {
            "percent": cpu_percent,
        },
        "memory": {
            "total_bytes": memory.total,
            "available_bytes": memory.available,
            "used_bytes": memory.used,
            "percent": memory.percent,
        },
        "uptime_seconds": uptime_seconds,
        "drives": drives,
        "psutil_available": True,
    }


@router.get("/metrics")
async def system_metrics() -> Dict[str, Any]:
    if not HAS_PSUTIL:
        raise HTTPException(
            status_code=503,
            detail="psutil not installed; install it to enable /api/system/metrics"
        )

    metrics = await run_in_threadpool(_collect_system_metrics)
    return metrics


@router.get("/identity")
async def system_identity(request: Request) -> Dict[str, Any]:
    """Return machine identity: MAC address, drive root, hostname."""
    from backend.services.identity_service import get_identity

    drive_root = getattr(request.app.state, "drive_root", None)
    return get_identity(drive_root=drive_root)


@local_router.get("/provisioning_status")
async def provisioning_status(request: Request) -> Dict[str, Any]:
    drive_root = getattr(request.app.state, "drive_root", None)
    identity = getattr(request.app.state, "cabinet_identity", None)
    if not identity:
        identity = load_cabinet_identity(drive_root).to_dict()

    return {
        "success": True,
        "drive_root": str(drive_root) if drive_root else "",
        "identity": identity,
        "manifest_present": bool(drive_root and (Path(drive_root) / ".aa" / "manifest.json").exists()),
    }
