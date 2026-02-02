"""Console Gamepad Detection Service

Detects console controllers (Xbox, PlayStation, Switch) and matches them to profiles.
Uses USB VID/PID detection with profile-based configuration.

Performance optimized with caching and profile loading.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
import platform
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .usb_detector import (
    USBBackendError,
    USBDetectionError,
    USBPermissionError,
    detect_usb_devices,
    format_vid_pid,
    invalidate_cache as invalidate_usb_cache
)

logger = logging.getLogger(__name__)

# Cache TTL in seconds for controller detection results
CONTROLLER_CACHE_TTL = 5.0

# Profile directory path
PROFILE_DIR = Path(__file__).parent.parent / "data" / "controller_profiles"


class ControllerType(Enum):
    """Controller type enumeration for type safety."""
    XBOX_360 = "xbox_360"
    XBOX_ONE = "xbox_one"
    PS4_DUALSHOCK = "ps4_dualshock"
    PS5_DUALSENSE = "ps5_dualsense"
    SWITCH_PRO = "switch_pro"
    SWITCH_JOYCON = "switch_joycon"
    GENERIC = "generic"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ControllerProfile:
    """Immutable controller profile loaded from JSON."""
    profile_id: str
    name: str
    manufacturer: str
    type: str
    usb_identifiers: List[Dict[str, str]]
    buttons: Dict[str, Any]
    dpad: Dict[str, Any]
    axes: Dict[str, Any]
    retroarch_defaults: Dict[str, str] = field(default_factory=dict)
    features: Dict[str, bool] = field(default_factory=dict)
    notes: str = ""
    version: str = "1.0"


class GamepadDetectionError(Exception):
    """Raised when gamepad detection encounters an error."""
    pass


class ProfileLoadError(GamepadDetectionError):
    """Raised when profile loading fails."""
    pass


# Cache for loaded profiles
_profile_cache: Optional[Dict[str, ControllerProfile]] = None

# Cache for controller detection results
_controller_cache: Optional[Tuple[float, List[Dict[str, Any]]]] = None


def _load_profile_from_file(profile_path: Path) -> Optional[ControllerProfile]:
    """Load a controller profile from JSON file.

    Args:
        profile_path: Path to profile JSON file

    Returns:
        ControllerProfile instance or None if loading fails
    """
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Validate required fields
        required_fields = ['profile_id', 'name', 'manufacturer', 'type', 'usb_identifiers',
                          'buttons', 'dpad', 'axes']
        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            logger.warning(f"Profile {profile_path.name} missing required fields: {missing_fields}")
            return None

        # Create frozen dataclass
        profile = ControllerProfile(
            profile_id=data['profile_id'],
            name=data['name'],
            manufacturer=data['manufacturer'],
            type=data['type'],
            usb_identifiers=data['usb_identifiers'],
            buttons=data['buttons'],
            dpad=data['dpad'],
            axes=data['axes'],
            retroarch_defaults=data.get('retroarch_defaults', {}),
            features=data.get('features', {}),
            notes=data.get('notes', ''),
            version=data.get('version', '1.0')
        )

        logger.debug(f"Loaded profile: {profile.name} ({profile.profile_id})")
        return profile

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in profile {profile_path.name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to load profile {profile_path.name}: {e}")
        return None


@lru_cache(maxsize=1)
def load_controller_profiles() -> Dict[str, ControllerProfile]:
    """Load all controller profiles from the profiles directory.

    Returns:
        Dictionary mapping profile_id to ControllerProfile

    Raises:
        ProfileLoadError: If profile directory doesn't exist or no profiles found

    Note:
        Result is cached since profiles are static
    """
    global _profile_cache

    if _profile_cache is not None:
        return _profile_cache

    if not PROFILE_DIR.exists():
        error_msg = f"Profile directory not found: {PROFILE_DIR}"
        logger.error(error_msg)
        raise ProfileLoadError(error_msg)

    profiles = {}

    # Load all JSON files in the profiles directory
    for profile_file in PROFILE_DIR.glob("*.json"):
        profile = _load_profile_from_file(profile_file)
        if profile:
            profiles[profile.profile_id] = profile

    if not profiles:
        error_msg = f"No valid profiles found in {PROFILE_DIR}"
        logger.warning(error_msg)
        # Don't raise here, just return empty dict
        return {}

    logger.info(f"Loaded {len(profiles)} controller profiles")
    _profile_cache = profiles
    return profiles


def _match_controller_to_profile(vid: str, pid: str) -> Optional[ControllerProfile]:
    """Match a VID/PID to a controller profile.

    Args:
        vid: Vendor ID (hex string like 'd209' or '0xd209')
        pid: Product ID (hex string like '0501' or '0x0501')

    Returns:
        Matching ControllerProfile or None
    """
    # Normalize VID/PID format
    vid_clean = vid.lower().replace('0x', '').strip()
    pid_clean = pid.lower().replace('0x', '').strip()

    try:
        profiles = load_controller_profiles()
    except ProfileLoadError:
        return None

    # Check each profile's USB identifiers
    for profile in profiles.values():
        for usb_id in profile.usb_identifiers:
            profile_vid = usb_id['vid'].lower().replace('0x', '').strip()
            profile_pid = usb_id['pid'].lower().replace('0x', '').strip()

            if vid_clean == profile_vid and pid_clean == profile_pid:
                return profile

    return None


def _match_profile_by_strings(manufacturer: Optional[str], product: Optional[str]) -> Optional[ControllerProfile]:
    """Best-effort fallback match using product/manufacturer strings.

    If VID/PID matching fails but USB descriptors are available, try to match
    against known profile names (e.g., 'Xbox 360 Controller', 'DualShock', 'Switch Pro').
    """
    try:
        profiles = load_controller_profiles()
    except ProfileLoadError:
        return None

    prod = (product or "").lower()
    manu = (manufacturer or "").lower()

    # Brand heuristics (helps when VID/PID are aliased, e.g., 8BitDo in XInput mode)
    if "8bitdo" in prod or "8bitdo" in manu:
        for profile in profiles.values():
            if "8bitdo" in profile.manufacturer.lower():
                return profile

    for profile in profiles.values():
        name = profile.name.lower()
        # Simple substring checks to avoid introducing regex/extra schema fields
        if name and (name in prod or name in manu):
            return profile
        # Heuristics for common variations
        if profile.profile_id == ControllerType.XBOX_360.value and ("xbox" in prod or "xinput" in prod):
            return profile
        if profile.profile_id == ControllerType.PS4_DUALSHOCK.value and ("dualshock" in prod or "ds4" in prod or "ps4" in prod):
            return profile
        if profile.profile_id == ControllerType.SWITCH_PRO.value and ("switch pro" in prod or "nintendo" in manu):
            return profile

    return None


def _build_controller_info(
    vid: str,
    pid: str,
    profile: Optional[ControllerProfile] = None,
    manufacturer: Optional[str] = None,
    product: Optional[str] = None,
    detected: bool = True
) -> Dict[str, Any]:
    """Build standardized controller information dictionary.

    Args:
        vid: Vendor ID
        pid: Product ID
        profile: Matched controller profile if found
        manufacturer: Manufacturer string from USB
        product: Product string from USB
        detected: Whether controller is currently connected

    Returns:
        Standardized controller info dictionary
    """
    vid_clean = vid.lower().replace('0x', '').strip()
    pid_clean = pid.lower().replace('0x', '').strip()
    vid_pid_key = f"{vid_clean}:{pid_clean}"

    if profile:
        controller_data = {
            "vid": f"0x{vid_clean}",
            "pid": f"0x{pid_clean}",
            "vid_pid": vid_pid_key,
            "profile_id": profile.profile_id,
            "name": profile.name,
            "manufacturer": profile.manufacturer,
            "type": profile.type,
            "detected": detected,
            "has_profile": True,
            "button_count": len(profile.buttons),
            "dpad_buttons": len(profile.dpad),
            "axis_count": len(profile.axes),
            "features": dict(profile.features),
        }

        # Add full profile data for detailed view
        controller_data["profile"] = {
            "buttons": profile.buttons,
            "dpad": profile.dpad,
            "axes": profile.axes,
            "retroarch_defaults": profile.retroarch_defaults,
            "notes": profile.notes,
            "version": profile.version
        }
    else:
        controller_data = {
            "vid": f"0x{vid_clean}",
            "pid": f"0x{pid_clean}",
            "vid_pid": vid_pid_key,
            "name": product or "Unknown Controller",
            "manufacturer": manufacturer or "Unknown",
            "type": "generic",
            "detected": detected,
            "has_profile": False
        }

    # Add USB string descriptors if available
    if manufacturer:
        controller_data["manufacturer_string"] = manufacturer
    if product:
        controller_data["product_string"] = product

    return controller_data


def detect_controllers(use_cache: bool = True) -> List[Dict[str, Any]]:
    """Detect connected console controllers.

    Args:
        use_cache: If True, use cached results if available and fresh

    Returns:
        List of controller info dictionaries

    Raises:
        GamepadDetectionError: If detection fails
        USBBackendError: If USB backend is not available
        USBPermissionError: If insufficient permissions
    """
    global _controller_cache

    # Check cache if enabled
    if use_cache and _controller_cache is not None:
        cache_time, cached_controllers = _controller_cache
        if time.time() - cache_time < CONTROLLER_CACHE_TTL:
            logger.debug(f"Using cached controller list ({len(cached_controllers)} controllers)")
            return cached_controllers

    controllers = []

    try:
        # Load profiles first
        profiles = load_controller_profiles()

        if not profiles:
            logger.warning("No controller profiles loaded, detection may be limited")

        # Detect all USB devices
        try:
            usb_devices = detect_usb_devices(include_unknown=True, use_cache=use_cache)
        except USBBackendError:
            # On Windows, fall back to XInput if libusb backend is unavailable
            if platform.system() == "Windows":
                logger.info("USB backend unavailable; attempting Windows XInput fallback")
                usb_devices = []  # continue with empty list; XInput handled below
            else:
                raise
        except USBPermissionError:
            # Bubble up permission error (tells UI to run as admin / fix udev)
            raise
        except USBDetectionError as e:
            raise GamepadDetectionError(f"USB detection failed: {str(e)}")

        # Filter to only devices that match controller profiles
        for device in usb_devices:
            vid_pid = device.get('vid_pid', '')
            if not vid_pid:
                continue

            # Try to match to a profile by VID/PID first
            vid, pid = vid_pid.split(':')
            profile = _match_controller_to_profile(vid, pid)

            # Fallback: try product/manufacturer strings
            if profile is None:
                profile = _match_profile_by_strings(
                    manufacturer=device.get('manufacturer_string'),
                    product=device.get('product_string'),
                )

            if profile:
                # Build controller info with profile
                controller_info = _build_controller_info(
                    vid=vid,
                    pid=pid,
                    profile=profile,
                    manufacturer=device.get('manufacturer_string'),
                    product=device.get('product_string'),
                    detected=True
                )
                controllers.append(controller_info)

        # Windows-only: If no controllers found via USB, try XInput fallback
        if platform.system() == "Windows" and not controllers:
            try:
                for pad in _detect_xinput_controllers():
                    controllers.append(pad)
            except Exception as xe:
                logger.debug(f"XInput fallback failed: {xe}")

        # Update cache
        _controller_cache = (time.time(), controllers)

        logger.info(f"Detected {len(controllers)} console controllers")
        return controllers

    except ProfileLoadError as e:
        logger.error(f"Profile loading failed: {e}")
        # Continue with empty profiles
        return []
    except Exception as e:
        logger.error(f"Controller detection failed: {e}")
        raise GamepadDetectionError(f"Controller detection failed: {str(e)}")


def _detect_xinput_controllers() -> List[Dict[str, Any]]:
    """Detect connected Xbox-class controllers via XInput on Windows.

    Returns a list of controller info dicts mapped to the xbox_360 profile.
    Only used as a Windows fallback when libusb is unavailable.
    """
    logger.info("[XInput] Starting XInput controller detection")
    if platform.system() != "Windows":
        logger.info("[XInput] Not on Windows, skipping")
        return []

    try:
        import ctypes
        from ctypes import wintypes
    except Exception as e:
        logger.warning(f"[XInput] ctypes unavailable for XInput: {e}")
        return []

    # Try common XInput DLLs
    xinput = None
    for dll in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
        try:
            xinput = ctypes.WinDLL(dll)
            logger.info(f"[XInput] Successfully loaded {dll}")
            break
        except Exception as e:
            logger.debug(f"[XInput] Failed to load {dll}: {e}")
            continue
    if xinput is None:
        logger.warning("[XInput] No XInput DLL found")
        return []

    class XINPUT_GAMEPAD(ctypes.Structure):
        _fields_ = [
            ("wButtons", wintypes.WORD),
            ("bLeftTrigger", ctypes.c_ubyte),
            ("bRightTrigger", ctypes.c_ubyte),
            ("sThumbLX", ctypes.c_short),
            ("sThumbLY", ctypes.c_short),
            ("sThumbRX", ctypes.c_short),
            ("sThumbRY", ctypes.c_short),
        ]

    class XINPUT_STATE(ctypes.Structure):
        _fields_ = [
            ("dwPacketNumber", wintypes.DWORD),
            ("Gamepad", XINPUT_GAMEPAD),
        ]

    # Prototype
    XInputGetState = xinput.XInputGetState
    XInputGetState.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
    XInputGetState.restype = wintypes.DWORD

    controllers: List[Dict[str, Any]] = []

    # Attempt users 0..3
    for i in range(4):
        state = XINPUT_STATE()
        res = XInputGetState(wintypes.DWORD(i), ctypes.byref(state))
        logger.debug(f"[XInput] Slot {i}: result code = {res}")
        if res == 0:  # ERROR_SUCCESS
            logger.info(f"[XInput] Controller detected in slot {i}")
            # Map to xbox_360 profile if available
            profiles = {}
            try:
                profiles = load_controller_profiles()
            except Exception:
                pass
            profile = profiles.get(ControllerType.XBOX_360.value)
            # Use common Xbox 360 VID/PID for compatibility in downstream logic
            ctrl = _build_controller_info(
                vid="045e",
                pid="028e",
                profile=profile,
                manufacturer="Microsoft",
                product="XInput Controller",
                detected=True,
            )
            controllers.append(ctrl)

    logger.info(f"[XInput] Found {len(controllers)} XInput controllers")
    return controllers


def get_controller_by_profile_id(profile_id: str) -> Optional[Dict[str, Any]]:
    """Get controller info by profile ID if connected.

    Args:
        profile_id: Profile identifier (e.g., 'xbox_360', 'ps4_dualshock')

    Returns:
        Controller info dict if found and connected, None otherwise
    """
    try:
        controllers = detect_controllers(use_cache=True)
        for controller in controllers:
            if controller.get('profile_id') == profile_id:
                return controller
    except GamepadDetectionError:
        pass

    return None


@lru_cache(maxsize=1)
def get_available_profiles() -> List[Dict[str, Any]]:
    """Get list of all available controller profiles.

    Returns:
        List of profile info dictionaries

    Note:
        Result is cached since profiles are static
    """
    try:
        profiles = load_controller_profiles()
    except ProfileLoadError:
        return []

    profile_list = []

    for profile in profiles.values():
        # Build minimal profile info (without full button/axis details)
        profile_info = {
            "profile_id": profile.profile_id,
            "name": profile.name,
            "manufacturer": profile.manufacturer,
            "type": profile.type,
            "button_count": len(profile.buttons),
            "dpad_buttons": len(profile.dpad),
            "axis_count": len(profile.axes),
            "features": dict(profile.features),
            "notes": profile.notes,
            "version": profile.version,
            "usb_identifiers": profile.usb_identifiers
        }
        profile_list.append(profile_info)

    return sorted(profile_list, key=lambda x: (x["manufacturer"], x["name"]))


def get_profile_details(profile_id: str) -> Optional[Dict[str, Any]]:
    """Get full details for a specific profile.

    Args:
        profile_id: Profile identifier

    Returns:
        Full profile dictionary with buttons, axes, etc., or None if not found
    """
    try:
        profiles = load_controller_profiles()
        profile = profiles.get(profile_id)

        if not profile:
            return None

        return {
            "profile_id": profile.profile_id,
            "name": profile.name,
            "manufacturer": profile.manufacturer,
            "type": profile.type,
            "usb_identifiers": profile.usb_identifiers,
            "buttons": profile.buttons,
            "dpad": profile.dpad,
            "axes": profile.axes,
            "retroarch_defaults": profile.retroarch_defaults,
            "features": profile.features,
            "notes": profile.notes,
            "version": profile.version
        }
    except ProfileLoadError:
        return None


def invalidate_cache() -> None:
    """Invalidate both controller and USB device caches.

    Use this when you know the USB configuration has changed.
    """
    global _controller_cache
    _controller_cache = None
    invalidate_usb_cache()  # Also invalidate USB cache
    logger.debug("Controller detection cache invalidated")


# Module-level test function
def main() -> None:
    """Run gamepad detection tests and display results."""
    print("Console Controller Detection Test")
    print("=" * 60)

    try:
        print("\nLoading controller profiles...")
        profiles = load_controller_profiles()
        print(f"Loaded {len(profiles)} profiles:")
        for profile_id, profile in profiles.items():
            print(f"  - {profile.name} ({profile_id})")
            print(f"    Manufacturer: {profile.manufacturer}")
            print(f"    Buttons: {len(profile.buttons)}, Axes: {len(profile.axes)}")

        print("\n" + "=" * 60)
        print("\nDetecting connected controllers...")
        controllers = detect_controllers(use_cache=False)

        if controllers:
            print(f"Found {len(controllers)} connected controllers:")
            for ctrl in controllers:
                print(f"\n  {ctrl['name']}")
                print(f"    VID:PID = {ctrl['vid_pid']}")
                print(f"    Profile: {ctrl.get('profile_id', 'None')}")
                if ctrl.get('has_profile'):
                    print(f"    Buttons: {ctrl['button_count']}, Axes: {ctrl['axis_count']}")
                    if ctrl.get('features'):
                        print(f"    Features: {', '.join(ctrl['features'].keys())}")
        else:
            print("No controllers detected")
            print("\nNote: Connect an Xbox, PlayStation, or Switch controller and try again")

        print("\n" + "=" * 60)
        print("\nAvailable profiles:")
        available = get_available_profiles()
        for prof in available:
            detected_status = "✓ CONNECTED" if any(
                c.get('profile_id') == prof['profile_id'] for c in controllers
            ) else "  Not connected"
            print(f"  {detected_status} - {prof['name']}")

    except USBBackendError as e:
        print(f"\nERROR: {e}")
        print("\nInstall USB backend to enable controller detection")
    except USBPermissionError as e:
        print(f"\nERROR: {e}")
        print("\nRun with elevated permissions or add user to USB group")
    except ProfileLoadError as e:
        print(f"\nERROR: {e}")
        print("\nEnsure controller profile JSON files exist in:")
        print(f"  {PROFILE_DIR}")
    except GamepadDetectionError as e:
        print(f"\nERROR: {e}")


if __name__ == "__main__":
    main()
