"""Shared state models used by the LED engine."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LEDChannelAssignment:
    """Logical instruction describing a physical LED channel update."""

    device_id: str
    channel_index: int
    color: str
    logical_button: Optional[str] = None
    active: bool = True


@dataclass
class PatternState:
    """Metadata for a running pattern animation."""

    name: str
    params: Dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=lambda: time.monotonic())
    duration_ms: Optional[int] = None


@dataclass
class EngineFrame:
    """Represents a finalized brightness frame per device."""

    device_id: str
    channels: List[int]


@dataclass
class EngineStatus:
    """Snapshot returned by /led/status."""

    brightness: int
    active_pattern: Optional[str]
    devices: List[Dict[str, Any]]
    event_log: List[Dict[str, Any]]
