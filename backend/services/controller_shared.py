"""Shared helpers for controller routers.

Extracted from the monolithic controller.py during Phase 2 (Persona Split)
to be imported by chuck_hardware.py, wizard_mapping.py, and the slim controller.py.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request

from .chuck.input_detector import InputEvent

logger = logging.getLogger(__name__)

_TEACH_EVENT_LOG_RELATIVE = Path("state") / "controller" / "teach_events.jsonl"


# ---------------------------------------------------------------------------
# Request-header helpers
# ---------------------------------------------------------------------------

def ensure_writes_allowed(request: Request) -> None:
    """Block writes when startup marked drive root invalid."""
    if not getattr(request.app.state, "writes_allowed", True):
        reason = getattr(
            request.app.state,
            "write_block_reason",
            "AA_DRIVE_ROOT is not set; writes are disabled until it is configured.",
        )
        raise HTTPException(status_code=503, detail=reason)


def require_device_id(request: Request) -> str:
    device_id = request.headers.get("x-device-id")
    if not device_id:
        raise HTTPException(status_code=400, detail="Missing x-device-id header.")
    return device_id


def ensure_controller_panel(panel: Optional[str]) -> None:
    if not panel:
        raise HTTPException(status_code=400, detail="Missing x-panel header.")
    if panel.lower() != "controller":
        raise HTTPException(
            status_code=403,
            detail="x-panel must be 'controller' for controller board routes.",
        )


def wizard_session_key(request: Request) -> str:
    return (
        request.headers.get("x-session-id")
        or request.headers.get("x-device-id")
        or request.headers.get("x-client-id")
        or "default"
    )


# ---------------------------------------------------------------------------
# Control-type helpers
# ---------------------------------------------------------------------------

def default_control_type(control_key: str) -> str:
    if ".button" in control_key or control_key.endswith(("coin", "start")):
        return "button"
    return "joystick"


def get_next_step(state: Dict[str, Any]) -> Optional[str]:
    for control in state.get("sequence", []):
        if control not in state.get("captures", {}):
            return control
    return None


# ---------------------------------------------------------------------------
# Logging / Audit
# ---------------------------------------------------------------------------

async def log_controller_change(
    request: Request,
    drive_root: Path,
    action: str,
    details: Dict[str, Any],
    backup_path: Optional[Path] = None,
) -> None:
    """Log Controller Chuck changes to changes.jsonl"""
    log_file = drive_root / ".aa" / "logs" / "changes.jsonl"

    def _do_log():
        log_file.parent.mkdir(parents=True, exist_ok=True)

        device = request.headers.get('x-device-id', 'unknown') if hasattr(request, 'headers') else 'unknown'
        panel = request.headers.get('x-panel', 'controller') if hasattr(request, 'headers') else 'controller'

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "scope": "controller",
            "action": action,
            "details": details,
            "backup_path": str(backup_path) if backup_path else None,
            "device": device,
            "panel": panel,
        }

        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + "\n")

    await asyncio.to_thread(_do_log)


def teach_event_log_path(drive_root: Path) -> Path:
    path = (drive_root / _TEACH_EVENT_LOG_RELATIVE).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


async def record_teach_event(drive_root: Path, event: InputEvent) -> None:
    """Append detected events so Teach Wizard can render real data."""
    try:
        payload = serialize_input_event(event)
        payload["raw_timestamp"] = event.timestamp

        def _do_record():
            with open(teach_event_log_path(drive_root), "a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload) + "\n")

        await asyncio.to_thread(_do_record)
    except Exception:  # pragma: no cover - best-effort logging only
        logger.debug("Failed to persist teach event", exc_info=True)


# ---------------------------------------------------------------------------
# Event serialization
# ---------------------------------------------------------------------------

def serialize_input_event(event: InputEvent) -> Dict[str, Any]:
    """Serialize an InputEvent to a dictionary."""
    from pydantic import BaseModel

    class InputDetectionEvent(BaseModel):
        timestamp: float
        keycode: str
        pin: int
        control_key: str
        player: int
        control_type: str
        source_id: str = ""

    payload = InputDetectionEvent(
        timestamp=event.timestamp,
        keycode=event.keycode,
        pin=event.pin,
        control_key=event.control_key,
        player=event.player,
        control_type=event.control_type,
        source_id=event.source_id,
    )
    return payload.dict()


def mapping_entry_from_event(
    event: InputEvent,
    existing: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    label = (existing or {}).get("label") or event.control_key.replace(".", " ").title()
    mapping_type = "joystick" if event.control_type == "joystick" else "button"
    entry = {
        "pin": event.pin,
        "type": mapping_type,
        "label": label,
    }
    return entry
