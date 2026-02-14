"""
Runtime state router.
Read-only API exposing current frontend/mode/game for marquee or AI helpers.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/local/runtime", tags=["runtime"])
state_router = APIRouter(prefix="/api/local/state", tags=["runtime"])


def _drive_root(request: Optional[Request]) -> Path:
    """Get drive root from app state. No CWD fallback per Slice 2 contract."""
    if request:
        root = getattr(request.app.state, "drive_root", None)
        if root:
            return Path(root)
    # Fall back to env for edge cases, but no CWD
    from backend.constants.drive_root import get_drive_root
    return get_drive_root(allow_cwd_fallback=False)


def _runtime_state_path(request: Optional[Request]) -> Path:
    return _drive_root(request) / ".aa" / "state" / "runtime_state.json"



def _default_runtime_state() -> Dict[str, Any]:
    return {
        "version": 1,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "frontend": "unknown",  # launchbox | retrofe | unknown
        "mode": "idle",         # in_game | idle | browse
        "system_id": None,
        "game_title": None,
        "player": None,
        "elapsed_seconds": None,
    }


def load_runtime_state(request: Optional[Request]) -> Dict[str, Any]:
    path = _runtime_state_path(request)
    data = None
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = None

    if not isinstance(data, dict):
        data = _default_runtime_state()
        save_runtime_state(data, request)
    return data


def save_runtime_state(state: Dict[str, Any], request: Optional[Request]) -> None:
    """Safe write for future writers; read-only for this router."""
    path = _runtime_state_path(request)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(path)


@router.get("/state")
async def get_runtime_state(request: Request):
    """Return current runtime state; rebuild default if missing/invalid."""
    return load_runtime_state(request)


@state_router.get("/frontend")
async def get_runtime_state_frontend(request: Request):
    """Return current runtime state (frontend-friendly)."""
    return load_runtime_state(request)
