"""Helpers for translating WebSocket payloads into engine commands."""
from __future__ import annotations

from typing import Any, Dict, Optional


class InvalidLEDMessage(ValueError):
    """Raised when a WebSocket message is malformed."""


def parse_ws_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize legacy (type=...) and new (op=...) message formats."""
    if not isinstance(payload, dict):
        raise InvalidLEDMessage("Payload must be a JSON object")

    op = str(payload.get("op") or payload.get("type") or "").strip().lower()
    if not op:
        raise InvalidLEDMessage("Missing 'op' or 'type' field")

    if op in {"handshake", "hello"}:
        return {"action": "handshake"}

    if op in {"pattern", "run_pattern"}:
        name = payload.get("pattern") or payload.get("name")
        if not name:
            raise InvalidLEDMessage("pattern message missing 'pattern' field")
        return {"action": "pattern", "pattern": str(name), "color": payload.get("color"), "params": payload.get("params")}

    if op in {"clear", "reset"}:
        return {"action": "clear"}

    if op in {"brightness"}:
        level = payload.get("level")
        if level is None:
            raise InvalidLEDMessage("brightness message missing 'level'")
        return {"action": "brightness", "level": level}

    if op in {"led_command", "command"}:
        player = payload.get("player")
        button = payload.get("button")
        if player is None or button is None:
            raise InvalidLEDMessage("led_command requires 'player' and 'button'")
        return {
            "action": "led_command",
            "player": str(player),
            "button": str(button),
            "state": bool(payload.get("state", True)),
            "color": payload.get("color"),
        }

    raise InvalidLEDMessage(f"Unsupported LED command: {op}")
