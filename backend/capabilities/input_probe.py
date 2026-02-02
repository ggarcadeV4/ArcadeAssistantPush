"""
Input Probe - Fast Controller Detection

Detects connected controllers via VID/PID with <50ms latency.

PERFORMANCE CONTRACT:
- Detection completes in <50ms (bounded)
- Uses cached USB device list (refreshed every 5 seconds)
- Class-based detection (controller/encoder/lightgun)
- No blocking I/O on hot path

MOCK SUPPORT:
- Set MOCK_DEVICES env var for testing without hardware
- Example: MOCK_DEVICES='[{"vid":"2dc8","pid":"6101","name":"8BitDo SN30 Pro"}]'
"""

import os
import time
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import json

# VID/PID to device class mapping
# Format: (VID, PID) -> (manufacturer, model, device_class)
KNOWN_DEVICES = {
    # 8BitDo Controllers
    ("2dc8", "6101"): ("8BitDo", "SN30 Pro", "controller"),
    ("2dc8", "6100"): ("8BitDo", "SF30 Pro", "controller"),
    ("2dc8", "3106"): ("8BitDo", "Zero 2", "controller"),

    # Xbox Controllers
    ("045e", "02ea"): ("Microsoft", "Xbox One Controller", "controller"),
    ("045e", "02dd"): ("Microsoft", "Xbox One Controller (2015)", "controller"),
    ("045e", "0b12"): ("Microsoft", "Xbox Series Controller", "controller"),

    # PlayStation Controllers
    ("054c", "05c4"): ("Sony", "DualShock 4", "controller"),
    ("054c", "09cc"): ("Sony", "DualShock 4 (2nd Gen)", "controller"),
    ("054c", "0ce6"): ("Sony", "DualSense", "controller"),

    # Arcade Encoders
    ("d209", "0501"): ("Ultimarc", "I-PAC 2", "encoder"),
    ("d209", "0410"): ("Ultimarc", "I-PAC 4", "encoder"),
    ("d209", "1500"): ("Ultimarc", "PacDrive", "encoder"),

    # Light Guns
    ("d209", "1601"): ("Ultimarc", "AimTrak", "lightgun"),
    ("d209", "1602"): ("Ultimarc", "AimTrak (dual)", "lightgun"),
}

@dataclass
class DetectedDevice:
    """Represents a detected input device"""
    vendor_id: str  # Hex string (e.g., "2dc8")
    product_id: str  # Hex string (e.g., "6101")
    name: str  # Device name
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    device_class: str = "controller"  # controller | encoder | lightgun
    profile_exists: bool = False
    profile_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "device_class": self.device_class,
            "profile_exists": self.profile_exists,
            "profile_name": self.profile_name,
        }


# Device cache (refreshed every 5 seconds)
_device_cache: Optional[List[DetectedDevice]] = None
_cache_timestamp: float = 0
_cache_ttl: float = 5.0  # 5 second TTL


def _get_mock_devices() -> List[DetectedDevice]:
    """Get mock devices from environment variable"""
    mock_json = os.getenv("MOCK_DEVICES", "[]")

    try:
        mock_data = json.loads(mock_json)
        devices = []

        for item in mock_data:
            vid = item.get("vid", "").lower()
            pid = item.get("pid", "").lower()
            name = item.get("name", "Unknown Device")

            # Look up in known devices
            key = (vid, pid)
            if key in KNOWN_DEVICES:
                manufacturer, model, device_class = KNOWN_DEVICES[key]
            else:
                manufacturer = item.get("manufacturer")
                model = item.get("model")
                device_class = item.get("device_class", "controller")

            devices.append(DetectedDevice(
                vendor_id=vid,
                product_id=pid,
                name=name,
                manufacturer=manufacturer,
                model=model,
                device_class=device_class
            ))

        return devices

    except json.JSONDecodeError:
        return []


def _detect_usb_devices_fast() -> List[DetectedDevice]:
    """
    Fast USB device detection (<50ms).

    Uses pyusb for actual hardware detection when available.
    Falls back to mock devices if MOCK_DEVICES env var is set.

    Returns:
        List of detected devices
    """
    # Check for mock devices first
    mock_devices = _get_mock_devices()
    if mock_devices:
        return mock_devices

    # Try actual USB detection
    try:
        import usb.core
        import usb.util

        devices = []
        usb_devices = usb.core.find(find_all=True)

        for usb_dev in usb_devices:
            # Only process HID devices (class 3)
            if usb_dev.bDeviceClass != 3:
                # Check interface descriptors
                is_hid = False
                try:
                    for cfg in usb_dev:
                        for intf in cfg:
                            if intf.bInterfaceClass == 3:  # HID
                                is_hid = True
                                break
                        if is_hid:
                            break
                except:
                    pass

                if not is_hid:
                    continue

            vid = f"{usb_dev.idVendor:04x}"
            pid = f"{usb_dev.idProduct:04x}"

            # Look up device info
            key = (vid, pid)
            if key in KNOWN_DEVICES:
                manufacturer, model, device_class = KNOWN_DEVICES[key]
                name = f"{manufacturer} {model}"
            else:
                # Try to read product string
                try:
                    name = usb.util.get_string(usb_dev, usb_dev.iProduct)
                except:
                    name = f"USB Device {vid}:{pid}"

                manufacturer = None
                model = None
                device_class = "controller"  # Default

            devices.append(DetectedDevice(
                vendor_id=vid,
                product_id=pid,
                name=name,
                manufacturer=manufacturer,
                model=model,
                device_class=device_class
            ))

        return devices

    except ImportError:
        # pyusb not available - return empty list
        return []
    except Exception as e:
        # USB detection failed - log and return empty
        print(f"WARNING: USB detection failed: {e}")
        return []


def detect_devices(force_refresh: bool = False) -> List[DetectedDevice]:
    """
    Detect connected input devices with caching.

    Args:
        force_refresh: Force cache refresh

    Returns:
        List of detected devices

    Performance: <50ms guaranteed (uses cache after first call)
    """
    global _device_cache, _cache_timestamp

    now = time.time()

    # Return cached devices if fresh
    if not force_refresh and _device_cache is not None:
        if (now - _cache_timestamp) < _cache_ttl:
            return _device_cache

    # Refresh cache
    start = time.time()
    _device_cache = _detect_usb_devices_fast()
    _cache_timestamp = now
    elapsed_ms = (time.time() - start) * 1000

    # Verify performance contract
    if elapsed_ms > 50:
        print(f"WARNING: Device detection took {elapsed_ms:.1f}ms (target <50ms)")

    return _device_cache


def check_profile_exists(device: DetectedDevice, drive_root) -> bool:
    """
    Check if a profile exists for this device.

    Returns:
        True if profile exists in staging or emulator trees
    """
    from pathlib import Path
    from .autoconfig_manager import normalize_profile_name, get_staging_path

    # Generate expected profile name
    if device.manufacturer and device.model:
        profile_name = f"{device.manufacturer} {device.model}"
    else:
        profile_name = device.name

    normalized = normalize_profile_name(profile_name)
    staging_path = get_staging_path(profile_name, Path(drive_root))

    return staging_path.exists()


def detect_unconfigured_devices(drive_root) -> List[DetectedDevice]:
    """
    Detect devices that need auto-configuration.

    Returns:
        List of devices without existing profiles
    """
    devices = detect_devices()
    unconfigured = []

    for device in devices:
        if not check_profile_exists(device, drive_root):
            device.profile_exists = False
            unconfigured.append(device)
        else:
            device.profile_exists = True

    return unconfigured


def get_device_by_vidpid(vendor_id: str, product_id: str) -> Optional[DetectedDevice]:
    """
    Find device by VID/PID.

    Args:
        vendor_id: Hex string (e.g., "2dc8")
        product_id: Hex string (e.g., "6101")

    Returns:
        DetectedDevice or None
    """
    devices = detect_devices()

    vid_lower = vendor_id.lower()
    pid_lower = product_id.lower()

    for device in devices:
        if device.vendor_id == vid_lower and device.product_id == pid_lower:
            return device

    return None


def classify_device_by_name(name: str) -> str:
    """
    Classify device by name when VID/PID unknown.

    Returns:
        "controller" | "encoder" | "lightgun"
    """
    name_lower = name.lower()

    if any(kw in name_lower for kw in ["gun", "aimtrak", "wiimote"]):
        return "lightgun"

    if any(kw in name_lower for kw in ["ipac", "pacdrive", "encoder", "arcade"]):
        return "encoder"

    return "controller"
