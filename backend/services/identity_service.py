"""
Identity Service — MAC address and system identification for licensing prep.

Provides machine-level identity information:
- Primary NIC MAC address (formatted XX:XX:XX:XX:XX:XX)
- Drive root from AA_DRIVE_ROOT
- Machine hostname

Used by /api/system/identity endpoint and future licensing/provisioning.
"""

from __future__ import annotations

import platform
import uuid
from pathlib import Path
from typing import Any, Dict, Optional


def get_mac_address() -> str:
    """
    Retrieve the primary MAC address of the machine.
    
    Uses uuid.getnode() which returns the hardware address as a 48-bit
    positive integer. Falls back to a random MAC if no real NIC is found
    (bit 0 of the first octet will be set in that case).
    
    Returns:
        MAC address formatted as "XX:XX:XX:XX:XX:XX"
    """
    mac_int = uuid.getnode()
    
    # Check if this is a real MAC (bit 0 of first octet is 0 for real MACs)
    is_real = not (mac_int >> 40) & 1
    
    mac_hex = f"{mac_int:012X}"
    mac_formatted = ":".join(mac_hex[i:i+2] for i in range(0, 12, 2))
    
    return mac_formatted


def is_mac_real() -> bool:
    """
    Check if the MAC address from uuid.getnode() is a real hardware address.
    
    If Python can't determine the MAC, it generates a random one with
    the multicast bit set (bit 0 of the first octet = 1).
    
    Returns:
        True if the MAC is from a real NIC, False if randomly generated.
    """
    mac_int = uuid.getnode()
    return not (mac_int >> 40) & 1


def get_identity(drive_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Get full system identity payload.
    
    Args:
        drive_root: Optional explicit drive root. If None, resolves from env.
    
    Returns:
        Dict with mac_address, drive_root, hostname, and metadata.
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
    }
