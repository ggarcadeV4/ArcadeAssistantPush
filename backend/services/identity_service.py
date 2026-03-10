"""Identity Service — Hardware bio scanning and system identity.

Provides two hardware scanning approaches:
  - `scan_hardware_bio()` — WMI-based USB PnP enumeration (HardwareBio typed dict)
  - `get_hardware_bio()` — pyserial/board_detection approach with fingerprinting

Also provides `get_identity()` for full system identity payload
(MAC, hostname, drive root, platform info, hardware bio).

Part of Phase 4: Agentic Repair & Self-Healing Launch.
"""

from __future__ import annotations

import hashlib
import logging
import platform
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


# ─────────────────────────────────────────────────────────
# WMI-based scanning (used by doc_diagnostics.py)
# ─────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────
# pyserial-based scanning (used by get_identity)
# ─────────────────────────────────────────────────────────

def get_hardware_bio() -> Dict[str, Any]:
    """Gather high-precision hardware bio descriptors using pyserial/win32.
    
    Mission: Phase 4.1 - Nervous System
    Scanning for HID/COM devices to extract VID:PID and generating machine fingerprint.
    """
    encoders: list = []
    raw_descriptors: list = []
    scan_error: Optional[str] = None
    
    try:
        # Use pyserial for COM-based encoders and general descriptor listing
        import serial.tools.list_ports
        for port in serial.tools.list_ports.comports():
            # port.vid/pid can be None for some generic ports
            vid = f"{port.vid:04x}" if port.vid is not None else "0000"
            pid = f"{port.pid:04x}" if port.pid is not None else "0000"
            sig = f"{vid}:{pid}".lower()
            raw_descriptors.append(sig)
            
            encoders.append({
                "vid": vid,
                "pid": pid,
                "name": port.description or port.device,
                "port": port.device,
                "hwid": port.hwid,
                "manufacturer": port.manufacturer or "Unknown"
            })
            
        # Fallback to existing board detection if available (for pure HID)
        try:
            from backend.services.board_detection import detect_arcade_boards
            boards = detect_arcade_boards() or []
            for board in boards:
                vid = board.get("vendor_id", "0000")
                pid = board.get("product_id", "0000")
                sig = f"{vid}:{pid}".lower()
                if sig not in raw_descriptors:
                    raw_descriptors.append(sig)
                    encoders.append({
                        "vid": vid,
                        "pid": pid,
                        "name": board.get("name") or "Unknown HID Board",
                        "board_type": board.get("board_type"),
                        "detected": True
                    })
        except (ImportError, Exception):
            pass

    except Exception as e:
        scan_error = str(e)
        logger.error("hardware_bio_scan_failed: %s", scan_error)

    # Generate deterministic hardware fingerprint (SHA-256 of sorted signatures)
    signatures = sorted(list(set(raw_descriptors)))
    fingerprint = hashlib.sha256("|".join(signatures).encode()).hexdigest()[:16] if signatures else None

    return {
        "encoders": encoders,
        "signatures": signatures,
        "fingerprint": fingerprint,
        "encoder_count": len(encoders),
        "scan_error": scan_error,
        "timestamp": datetime.now().isoformat()
    }


# ─────────────────────────────────────────────────────────
# System identity (MAC, hostname, drive, hardware)
# ─────────────────────────────────────────────────────────

def get_mac_address() -> Optional[str]:
    """Get the primary MAC address of this machine."""
    try:
        import uuid
        mac_int = uuid.getnode()
        mac_str = ':'.join(f'{(mac_int >> i) & 0xff:02x}' for i in range(40, -1, -8))
        return mac_str
    except Exception:
        return None


def is_mac_real() -> bool:
    """Check if the MAC address is a real hardware address (not random)."""
    try:
        import uuid
        mac_int = uuid.getnode()
        # Bit 0 of first octet = multicast flag — real NICs have it unset
        return not bool((mac_int >> 40) & 0x01)
    except Exception:
        return False


def get_identity(drive_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Get full system identity payload.
    
    Returns:
        Dict with mac_address, drive_root, hostname, hardware_bio, and metadata.
    """
    mac = get_mac_address()
    hostname = platform.node()
    
    if drive_root is None:
        try:
            from backend.constants.drive_root import get_drive_root_or_none
            drive_root = get_drive_root_or_none()
        except Exception:
            drive_root = None
    
    drive_letter = None
    if drive_root and drive_root.drive:
        drive_letter = drive_root.drive  # e.g. "A:"
    
    return {
        "mac_address": mac,
        "mac_is_real": is_mac_real(),
        "hostname": hostname,
        "drive_root": str(drive_root) if drive_root else None,
        "drive_letter": drive_letter,
        "platform": platform.system(),
        "platform_version": platform.version(),
        "hardware_bio": get_hardware_bio(),
    }
