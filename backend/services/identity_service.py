"""Identity Service — WMI-based USB hardware bio scanner.

Provides `scan_hardware_bio()` which enumerates connected USB devices via
Windows WMI (Win32_PnPEntity) and returns a canonical HardwareBio dictionary
with VID:PID pairs in lowercase hex format.

Gracefully degrades on non-Windows platforms or when the `wmi` package is
unavailable, returning an empty device list with an error description.

Part of Phase 4: Agentic Repair & Self-Healing Launch.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

logger = logging.getLogger(__name__)

# Regex to extract VID and PID from a WMI DeviceID string
# Example: USB\VID_D209&PID_0501\...
_VID_PID_RE = re.compile(
    r"USB\\VID_([0-9A-Fa-f]{4})&PID_([0-9A-Fa-f]{4})", re.IGNORECASE
)


class USBDevice(TypedDict):
    vid_pid: str      # e.g. "d209:0501"
    name: str         # Device description from WMI
    device_id: str    # Full PnP device ID


class HardwareBio(TypedDict):
    devices: List[USBDevice]
    device_count: int
    scan_timestamp: str   # ISO 8601
    error: Optional[str]  # None on success, message on failure


def parse_vid_pid(device_id: str) -> Optional[str]:
    """Extract VID:PID from a WMI DeviceID string.

    Args:
        device_id: Full PnP device ID (e.g. ``USB\\VID_D209&PID_0501\\...``)

    Returns:
        Lowercase hex ``"d209:0501"`` or ``None`` if unparseable.
    """
    m = _VID_PID_RE.search(device_id)
    if not m:
        return None
    vid = m.group(1).lower()
    pid = m.group(2).lower()
    return f"{vid}:{pid}"


def scan_hardware_bio(drive_root: Optional[Path] = None) -> HardwareBio:
    """Query Win32_PnPEntity via WMI to enumerate USB devices.

    Returns a ``HardwareBio`` dict with VID:PID pairs for all USB devices.
    Falls back gracefully if WMI is unavailable (e.g. non-Windows or missing
    ``wmi`` package).

    Args:
        drive_root: Optional drive root for future file operations.

    Returns:
        HardwareBio with ``devices``, ``device_count``, ``scan_timestamp``,
        and ``error`` (None on success).
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        import wmi  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("wmi library unavailable — returning empty hardware bio")
        return HardwareBio(
            devices=[],
            device_count=0,
            scan_timestamp=timestamp,
            error="wmi library is not installed",
        )

    try:
        c = wmi.WMI()
        pnp_entities = c.Win32_PnPEntity()
    except Exception as exc:
        logger.error("WMI query failed: %s", exc)
        return HardwareBio(
            devices=[],
            device_count=0,
            scan_timestamp=timestamp,
            error=f"WMI query failed: {exc}",
        )

    devices: List[USBDevice] = []
    for entity in pnp_entities:
        raw_id = getattr(entity, "DeviceID", "") or ""
        vid_pid = parse_vid_pid(raw_id)
        if vid_pid is None:
            continue
        name = getattr(entity, "Description", None) or getattr(entity, "Name", "") or "Unknown USB Device"
        devices.append(
            USBDevice(vid_pid=vid_pid, name=str(name), device_id=str(raw_id))
        )

    logger.info("Hardware bio scan complete: %d USB devices found", len(devices))
    return HardwareBio(
        devices=devices,
        device_count=len(devices),
        scan_timestamp=timestamp,
        error=None,
    )
