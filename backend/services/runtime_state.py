"""
Runtime state helpers.

Tracks current frontend/mode/game for marquee and AI helpers.
Read-only callers should use load_runtime_state; writers should use update_runtime_state.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

DEFAULT_STATE = {
    "version": 1,
    "frontend": "unknown",   # launchbox | retrofe | unknown
    "mode": "idle",          # in_game | idle | browse
    "system_id": None,
    "game_title": None,
    "game_id": None,
    "player": None,
    "elapsed_seconds": None,
    "last_updated": None,
}


def _drive_root() -> Path:
    from backend.constants.drive_root import get_drive_root
    return get_drive_root(allow_cwd_fallback=True) / "Arcade Assistant"


def _state_path(drive_root: Path) -> Path:
    return drive_root / ".aa" / "state" / "runtime_state.json"


def load_runtime_state(drive_root: Path | None = None) -> Dict[str, Any]:
    drive_root = drive_root or _drive_root()
    path = _state_path(drive_root)
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        # Fall through to default on parse errors
        pass
    return dict(DEFAULT_STATE, last_updated=datetime.now(timezone.utc).isoformat())


def save_runtime_state(state: Dict[str, Any], drive_root: Path | None = None) -> None:
    drive_root = drive_root or _drive_root()
    path = _state_path(drive_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    state = dict(state)
    state["last_updated"] = datetime.now(timezone.utc).isoformat()

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(path)


def update_runtime_state(partial: Dict[str, Any], drive_root: Path | None = None) -> Dict[str, Any]:
    drive_root = drive_root or _drive_root()
    current = load_runtime_state(drive_root)
    current.update({k: v for k, v in partial.items()})
    save_runtime_state(current, drive_root)
    return current
