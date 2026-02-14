"""Factory helpers for the LED engine runtime."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .engine import LEDEngine

ENGINE_ATTR = "_led_engine_instance"


def get_led_engine(app_state: Any) -> LEDEngine:
    """Return the singleton LEDEngine stored on FastAPI app state.
    
    No Path.cwd() fallback per Slice 2 contract.
    """
    engine: LEDEngine | None = getattr(app_state, ENGINE_ATTR, None)
    if engine is None:
        drive_root = getattr(app_state, "drive_root", None)
        if not drive_root:
            raise RuntimeError("drive_root not set in app state; LED engine cannot initialize")
        manifest = getattr(app_state, "manifest", {}) or {}
        engine = LEDEngine(drive_root=Path(drive_root), manifest=manifest)
        setattr(app_state, ENGINE_ATTR, engine)
    engine.ensure_started()
    return engine


__all__ = ["get_led_engine", "LEDEngine"]
