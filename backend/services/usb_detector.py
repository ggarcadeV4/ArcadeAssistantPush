"""USB Device Detection Service

Detects arcade controller boards and other USB devices.
Supports PacDrive, I-PAC, Ultimarc, and other common arcade hardware.

Performance optimized with caching and efficient USB enumeration.
"""

from __future__ import annotations

import logging
import platform
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, cast

import usb.core
import usb.util
from usb.backend import libusb0, libusb1

logger = logging.getLogger(__name__)

# Cache TTL in seconds for device detection results
DEVICE_CACHE_TTL = 5.0


class DeviceType(Enum):
    """USB device type enumeration for type safety."""
    KEYBOARD_ENCODER = "keyboard_encoder"
    LED_CONTROLLER = "led_controller"
    GAMEPAD = "gamepad"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class BoardConfig:
    """Immutable configuration for known arcade boards."""
    name: str
    vendor: str
    device_type: DeviceType
    modes: Dict[str, bool] = field(default_factory=dict)


# Known arcade controller board configurations using frozen dataclass
KNOWN_BOARDS: Dict[str, BoardConfig] = {
    # Ultimarc I-PAC series
    "d209:0501": BoardConfig(
        name="Ultimarc I-PAC2",
        vendor="Ultimarc",
        device_type=DeviceType.KEYBOARD_ENCODER,
        modes={"turbo": True, "shift": True}
    ),
    "d209:0502": BoardConfig(
        name="Ultimarc I-PAC4",
        vendor="Ultimarc",
        device_type=DeviceType.KEYBOARD_ENCODER,
        modes={"turbo": True, "shift": True, "four_player": True}
    ),

    # Ultimarc PacDrive
    "d209:1500": BoardConfig(
        name="Ultimarc PacDrive",
        vendor="Ultimarc",
        device_type=DeviceType.LED_CONTROLLER,
        modes={"led_output": True}
    ),

    # Ultimarc PAC-LED64
    "d209:1401": BoardConfig(
        name="Ultimarc PAC-LED64",
        vendor="Ultimarc",
        device_type=DeviceType.LED_CONTROLLER,
        modes={"led_output": True, "high_density": True}
    ),

    # J-PAC (Keyboard/Mouse encoder with VGA passthrough)
    "d209:0511": BoardConfig(
        name="Ultimarc J-PAC",
        vendor="Ultimarc",
        device_type=DeviceType.KEYBOARD_ENCODER,
        modes={"vga_passthrough": True}
    ),

    # Paxco Tech Arcade Encoder Boards
    "0d62:0001": BoardConfig(
        name="Paxco Tech 4000T",
        vendor="Paxco Tech",
        device_type=DeviceType.KEYBOARD_ENCODER,
        modes={"dpad": True, "analog": True, "turbo": True}
    ),
    "0d62:0002": BoardConfig(
        name="Paxco Tech 5000",
        vendor="Paxco Tech",
        device_type=DeviceType.KEYBOARD_ENCODER,
        modes={"dpad": True, "analog": True, "turbo": True, "led": True}
    ),
    "0d62:0003": BoardConfig(
        name="Paxco Tech Ultratik",
        vendor="Paxco Tech",
        device_type=DeviceType.KEYBOARD_ENCODER,
        modes={"six_button": True, "turbo": True}
    ),

    # Pacto Tech encoder series
    "1234:5678": BoardConfig(
        name="Pacto Tech NinePanel",
        vendor="Pacto Tech",
        device_type=DeviceType.KEYBOARD_ENCODER,
        modes={"nine_panel": True, "macro": True, "shift": True}
    ),

    # Generic HID gamepad (common VID/PIDs for testing)
    "046d:c21d": BoardConfig(
        name="Logitech F310 Gamepad",
        vendor="Logitech",
        device_type=DeviceType.GAMEPAD,
        modes={"xinput": True}
    ),
    # Microsoft Xbox 360 VID/PID — also used by spoofed XInput arcade encoders
    # (e.g. Pacto 2000T/4000T, Standalone XInput boards). Chuck's input_detector
    # and device_scanner already classify this VID/PID as an arcade-relevant
    # encoder, so the canonical board lane must surface it too.
    "045e:028e": BoardConfig(
        name="Xbox 360 / XInput-Spoofed Arcade Encoder",
        vendor="Microsoft / Pacto",
        device_type=DeviceType.KEYBOARD_ENCODER,
        modes={"xinput": True, "arcade_encoder": True, "spoofed": True}
    ),
    # Xbox One XInput VID/PID — same arcade-encoder spoofing pattern recognised
    # by services/device_scanner.py (`0x028e`/`0x02ea` → arcade_encoder role).
    "045e:02ea": BoardConfig(
        name="Xbox One / XInput-Spoofed Arcade Encoder",
        vendor="Microsoft / Pacto",
        device_type=DeviceType.KEYBOARD_ENCODER,
        modes={"xinput": True, "arcade_encoder": True, "spoofed": True}
    ),
    "054c:05c4": BoardConfig(
        name="Sony DualShock 4",
        vendor="Sony",
        device_type=DeviceType.GAMEPAD,
        modes={"touchpad": True, "motion": True}
    ),
    "057e:2009": BoardConfig(
        name="Nintendo Switch Pro Controller",
        vendor="Nintendo",
        device_type=DeviceType.GAMEPAD,
        modes={"gyro": True, "nfc": True}
    ),
    "0c12:0ef8": BoardConfig(
        name="Brook Universal Fighting Board",
        vendor="Brook",
        device_type=DeviceType.KEYBOARD_ENCODER,
        modes={"xinput": True, "arcade_encoder": True}
    ),
}


# VID:PID allowlist for arcade-relevant XInput-spoofed encoder boards.
#
# These boards (Pacto 2000T/4000T, Standalone XInput arcade encoders, etc.)
# present as Microsoft Xbox 360/One controllers because Windows binds them
# to the XUSB driver. libusb on Windows CANNOT enumerate XUSB-owned devices,
# so the canonical KNOWN_BOARDS-via-libusb path will silently miss them even
# though they are physically connected and visible to other Chuck subsystems
# (services/device_scanner._xinput_enumeration and
# services/chuck/input_detector.detect_pacto_topology).
#
# Wave 2: this set lives in services/pacto_identity.py now. Re-exported
# here as ``ARCADE_XINPUT_VID_PIDS`` only for any legacy import path; do
# NOT add new entries here — extend ``SPOOFED_XINPUT_VID_PIDS`` instead.
from .pacto_identity import SPOOFED_XINPUT_VID_PIDS as ARCADE_XINPUT_VID_PIDS


class USBDetectionError(Exception):
    """Raised when USB detection encounters an error."""
    pass


class USBBackendError(USBDetectionError):
    """Raised when USB backend is not available."""
    pass


class USBPermissionError(USBDetectionError):
    """Raised when insufficient permissions to access USB devices."""
    pass


# Cache for device detection results
_device_cache: Optional[Tuple[float, List[Dict[str, Any]]]] = None


def format_vid_pid(vid: int, pid: int) -> str:
    """Format VID/PID as hex string (e.g., 'd209:0501').

    Args:
        vid: Vendor ID as integer
        pid: Product ID as integer

    Returns:
        Formatted VID:PID string in lowercase hex
    """
    return f"{vid:04x}:{pid:04x}"


def _get_usb_backend() -> Optional[Any]:
    """Get the first available USB backend.

    Returns:
        USB backend instance or None if no backend available
    """
    # Try libusb1 first (preferred), then libusb0
    for backend_module in [libusb1, libusb0]:
        try:
            backend = backend_module.get_backend()
            if backend is not None:
                logger.debug(f"Using USB backend: {backend_module.__name__}")
                return backend
        except Exception as e:
            logger.debug(f"Backend {backend_module.__name__} not available: {e}")

    return None


def _enumerate_windows_registry_devices(include_unknown: bool = False) -> List[Dict[str, Any]]:
    """Enumerate USB devices via Windows registry as a fallback.

    Reads HKLM\\SYSTEM\\CurrentControlSet\\Enum\\USB and builds device info from
    VID/PID present in key names, using FriendlyName/DeviceDesc/Mfg when available.

    Returns:
        List of device dictionaries similar to libusb path.
    """
    devices: List[Dict[str, Any]] = []
    if platform.system() != "Windows":
        return devices

    try:
        import winreg  # type: ignore
    except Exception:
        # winreg not available in non-Windows or limited envs
        return devices

    try:
        root = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
        base_path = r"SYSTEM\CurrentControlSet\Enum\USB"
        with winreg.OpenKey(root, base_path) as usb_key:
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(usb_key, i)
                except OSError:
                    break
                i += 1

                # Expect names like 'VID_045E&PID_028E' (case-insensitive)
                name_lower = subkey_name.lower()
                if "vid_" not in name_lower or "pid_" not in name_lower:
                    continue
                try:
                    vid_hex = name_lower.split("vid_")[1].split("&")[0]
                    pid_hex = name_lower.split("pid_")[1].split("&")[0]
                except Exception:
                    continue

                # Enumerate instance subkeys
                try:
                    with winreg.OpenKey(usb_key, subkey_name) as dev_key:
                        j = 0
                        while True:
                            try:
                                inst_name = winreg.EnumKey(dev_key, j)
                            except OSError:
                                break
                            j += 1
                            mfg = None
                            friendly = None
                            desc = None
                            is_connected = False
                            try:
                                with winreg.OpenKey(dev_key, inst_name) as inst_key:
                                    # Try common value names; ignore errors per value
                                    for val_name in ("FriendlyName", "DeviceDesc", "Mfg", "StatusFlags"):
                                        try:
                                            val, _ = winreg.QueryValueEx(inst_key, val_name)
                                            if val_name == "FriendlyName":
                                                friendly = str(val)
                                            elif val_name == "DeviceDesc":
                                                desc = str(val)
                                            elif val_name == "Mfg":
                                                mfg = str(val)
                                            elif val_name == "StatusFlags":
                                                # StatusFlags bit 0 = device is connected (DN_DEVICE_DISCONNECTED)
                                                status_flags = int(val)
                                                is_connected = (status_flags & 0x00000001) == 0
                                        except Exception:
                                            pass
                            except Exception:
                                # Skip unreadable instance
                                continue

                            # Only include devices that are actually connected
                            if not is_connected:
                                logger.debug(f"Skipping disconnected device {subkey_name}\\{inst_name}")
                                continue

                            # Build device info; prefer FriendlyName, then DeviceDesc
                            product = friendly or (desc.split(";")[-1].strip() if desc else None)
                            manufacturer = mfg

                            vid_int = int(vid_hex, 16)
                            pid_int = int(pid_hex, 16)
                            vid_pid_key = format_vid_pid(vid_int, pid_int)
                            board_config = KNOWN_BOARDS.get(vid_pid_key)

                            if board_config or include_unknown:
                                devices.append(
                                    _build_device_info(
                                        vid_int,
                                        pid_int,
                                        board_config,
                                        manufacturer,
                                        product,
                                    )
                                )
                except Exception:
                    continue

    except Exception:
        # Any registry errors -> return best-effort discovered list (possibly empty)
        return devices

    return devices


def _apply_chuck_intelligence_supplements(devices: List[Dict[str, Any]]) -> None:
    """Merge richer Chuck-detection evidence into the canonical device list.

    Both ``detect_usb_devices`` exit paths (libusb success and the no-libusb
    Windows registry fallback) need to benefit from:

    1. The WMI XInput-spoofed arcade-encoder supplement
       (``_enumerate_arcade_xinput_via_wmi``) — recovers boards owned by the
       XUSB driver that libusb cannot see.
    2. The ``device_scanner`` promotion step
       (``_promote_arcade_relevant_from_device_scanner``) — surfaces
       arcade-relevant evidence (HID via hidapi, XInput via pygame) that
       Chuck's other subsystems already classify but currently leave
       stranded outside the canonical board lane.

    Mutates ``devices`` in place. Both supplements are wrapped in their own
    try/except so a failure in one does not break the other or the libusb
    path that already populated ``devices``.
    """
    # Dedupe by composite (vid_pid, parent_hub) so that multiple distinct
    # physical encoder boards that share the same XInput-spoofed VID/PID
    # but live on different USB hubs (e.g. a Pacto_2000T and a Pacto_4000T
    # plugged into the same cabinet) are NOT collapsed into one entry.
    # For non-topology entries (libusb, device_scanner) parent_hub is None,
    # which is a stable composite key in its own right.
    def _dedupe_key(d: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        return (d.get("vid_pid"), d.get("parent_hub"))

    existing_keys = {_dedupe_key(d) for d in devices}

    if platform.system() == "Windows":
        try:
            for supp in _enumerate_arcade_xinput_via_wmi():
                key = _dedupe_key(supp)
                if key[0] and key not in existing_keys:
                    devices.append(supp)
                    existing_keys.add(key)
        except Exception as exc:
            logger.debug("XInput arcade encoder supplement skipped: %s", exc)

    try:
        for promoted in _promote_arcade_relevant_from_device_scanner():
            key = _dedupe_key(promoted)
            if key[0] and key not in existing_keys:
                devices.append(promoted)
                existing_keys.add(key)
    except Exception as exc:
        logger.debug(
            "Arcade-relevant promotion from device_scanner skipped: %s", exc
        )


def _promote_arcade_relevant_from_device_scanner() -> List[Dict[str, Any]]:
    """Promote arcade-relevant evidence from ``device_scanner.scan_devices()``
    into the canonical board-lane shape.

    The ``services.device_scanner`` module already does richer enumeration
    than the libusb-only path: HID-class devices via ``hidapi``, XInput
    gamepads via ``pygame.joystick``, and Ultimarc/LED-Wiz/PactoTech name
    classification. Anything it considers arcade-relevant is tagged with
    ``suggested_role == "arcade_encoder"`` (see
    ``device_scanner._xinput_enumeration`` and the platform-specific
    classification block at the bottom of ``device_scanner.scan_devices``).

    That signal currently lives only on the ``/api/local/devices`` lane, so
    Chuck's canonical board lane (``/api/local/hardware/arcade/boards``)
    cannot see it. This helper bridges them: it consumes the existing
    ``scan_devices`` output and re-shapes the arcade-relevant entries into
    the same dict format ``detect_usb_devices`` already returns, so
    ``detect_arcade_boards`` will pick them up automatically.

    Narrow contract:
    - Only entries already classified as ``arcade_encoder`` are promoted.
    - Entries with no resolvable VID/PID are dropped (we cannot key them
      against ``KNOWN_BOARDS`` or dedupe them against the libusb pass).
    - This helper never broadens detection to "all gamepads"; it relies
      entirely on ``device_scanner``'s pre-existing classification.

    Returns:
        List of canonical board-lane dicts (KEYBOARD_ENCODER type) ready
        to be merged into ``detect_usb_devices``' return value.
    """
    promoted: List[Dict[str, Any]] = []

    # Lazy import: device_scanner pulls in pygame at module load, which has
    # its own init side effects. Keep the import inside the helper so a
    # failure to import never breaks the libusb-only path.
    try:
        from .device_scanner import scan_devices  # type: ignore
    except Exception as exc:
        logger.debug(
            "device_scanner unavailable for canonical board-lane promotion: %s",
            exc,
        )
        return promoted

    try:
        scanned = scan_devices()
    except Exception as exc:
        logger.debug("device_scanner.scan_devices() failed: %s", exc)
        return promoted

    for entry in scanned:
        if entry.get("suggested_role") != "arcade_encoder":
            continue

        vid_str = entry.get("vid")  # e.g. "0x045e"
        pid_str = entry.get("pid")  # e.g. "0x028e"
        if not vid_str or not pid_str:
            continue
        try:
            vid_int = int(str(vid_str).lower().replace("0x", ""), 16)
            pid_int = int(str(pid_str).lower().replace("0x", ""), 16)
        except (ValueError, AttributeError):
            continue

        vid_pid_key = format_vid_pid(vid_int, pid_int)
        board_config = KNOWN_BOARDS.get(vid_pid_key)
        manufacturer = entry.get("manufacturer")
        product = entry.get("product")

        device_data = _build_device_info(
            vid_int, pid_int, board_config, manufacturer, product
        )

        # If device_scanner tagged something as arcade_encoder but it's not
        # in KNOWN_BOARDS, synthesize a KEYBOARD_ENCODER-typed entry so
        # detect_arcade_boards still surfaces it. This stays narrow: we only
        # ever do this for entries device_scanner *already* classified.
        if board_config is None:
            device_data["type"] = DeviceType.KEYBOARD_ENCODER.value
            device_data["known"] = True
            if not device_data.get("name") or device_data["name"] == "Unknown USB Device":
                device_data["name"] = product or f"Arcade Encoder ({vid_pid_key})"

        # Carry forward the richer device_scanner metadata so the hardware
        # router's _normalize_board_entry has device_id / interface /
        # manufacturer fields to surface in the GUI board pill.
        if entry.get("device_id"):
            device_data["device_id"] = entry["device_id"]
        if entry.get("interface"):
            device_data["interface"] = entry["interface"]
        if manufacturer:
            device_data["manufacturer"] = manufacturer
        device_data["source"] = "device_scanner"

        promoted.append(device_data)
        logger.info(
            "Promoted arcade-relevant device %s (%s) from device_scanner "
            "into canonical board lane",
            vid_pid_key,
            device_data.get("name"),
        )

    return promoted


def _enumerate_arcade_xinput_via_wmi() -> List[Dict[str, Any]]:
    """Windows-only canonical-topology probe for arcade encoder boards.

    Delegates entirely to the side-effect-free topology helper
    ``services.encoder_detector.detect_encoder_boards``. That helper
    groups present XInput nodes by USB hub parent and emits real logical
    board identities — ``Pacto Tech 2000T`` (2 nodes), ``Pacto Tech 4000T``
    (4+ nodes), or ``Standalone XInput Controller`` (any other count) —
    instead of a generic VID/PID match. This is the single canonical
    Chuck topology helper; this wrapper exists only so the existing
    ``_apply_chuck_intelligence_supplements`` call site does not need
    to know which module owns the implementation.

    libusb on Windows cannot enumerate devices owned by the XUSB driver
    (Xbox/XInput controllers and the arcade-encoder boards that spoof
    them), so this WMI-based supplement is the only way the canonical
    board lane can see them at all.

    Returns:
        List of canonical board dictionaries with topology-enriched
        identity fields (``board_type``, ``players``, ``parent_hub``,
        ``xinput_nodes``). Returns ``[]`` on non-Windows platforms, when
        ``wmi`` is unavailable, or if the WMI query fails — in any of
        those cases the canonical lane falls back to the libusb pass and
        the device_scanner promotion supplement.
    """
    if platform.system() != "Windows":
        return []

    try:
        from .encoder_detector import detect_encoder_boards
    except Exception as exc:
        logger.debug(
            "encoder_detector unavailable for canonical topology probe: %s", exc
        )
        return []

    try:
        return detect_encoder_boards()
    except Exception as exc:
        logger.debug("encoder_detector.detect_encoder_boards() failed: %s", exc)
        return []


def _enumerate_lsusb(include_unknown: bool = False) -> List[Dict[str, Any]]:
    """Enumerate USB devices by parsing `lsusb` output (Linux fallback).

    Requires `lsusb` to be available (usbutils). Extracts VID:PID pairs and
    best-effort vendor/product strings.
    """
    devices: List[Dict[str, Any]] = []
    if platform.system() == "Windows":
        return devices

    import shutil
    import subprocess

    if shutil.which("lsusb") is None:
        return devices

    try:
        out = subprocess.check_output(["lsusb"], text=True, timeout=2.0)
        for line in out.splitlines():
            # Typical: Bus 001 Device 004: ID 045e:028e Microsoft Corp. Xbox 360 Controller
            parts = line.strip().split()
            if "ID" not in parts:
                continue
            try:
                idx = parts.index("ID")
                vid_pid = parts[idx + 1]
                if ":" not in vid_pid:
                    continue
                vid_hex, pid_hex = vid_pid.split(":", 1)
                vid_int = int(vid_hex, 16)
                pid_int = int(pid_hex, 16)

                # Vendor/product strings are the rest of the line
                remainder = " ".join(parts[idx + 2:]).strip()
                manufacturer = None
                product = None
                if remainder:
                    # Heuristic: split once at first period to get vendor then product
                    if "." in remainder:
                        vendor_str, product_str = remainder.split(".", 1)
                        manufacturer = vendor_str.strip()
                        product = product_str.strip()
                    else:
                        product = remainder

                board_config = KNOWN_BOARDS.get(format_vid_pid(vid_int, pid_int))
                if board_config or include_unknown:
                    devices.append(
                        _build_device_info(
                            vid_int, pid_int, board_config, manufacturer, product
                        )
                    )
            except Exception:
                continue
    except Exception:
        return devices

    return devices


def _extract_device_strings(dev: usb.core.Device) -> Tuple[Optional[str], Optional[str]]:
    """Safely extract manufacturer and product strings from USB device.

    Args:
        dev: USB device object

    Returns:
        Tuple of (manufacturer_string, product_string), either may be None
    """
    manufacturer = None
    product = None

    try:
        # Attempt to read strings with timeout
        if dev.manufacturer is not None:
            manufacturer = str(dev.manufacturer)
    except (ValueError, usb.core.USBError, AttributeError) as e:
        # pyusb stubs don't expose idVendor/idProduct at type-check time, but they exist at runtime
        logger.debug(f"Cannot read manufacturer string for {dev.idVendor:04x}:{dev.idProduct:04x}: {e}")  # type: ignore[attr-defined]

    try:
        if dev.product is not None:
            product = str(dev.product)
    except (ValueError, usb.core.USBError, AttributeError) as e:
        # pyusb stubs don't expose idVendor/idProduct at type-check time, but they exist at runtime
        logger.debug(f"Cannot read product string for {dev.idVendor:04x}:{dev.idProduct:04x}: {e}")  # type: ignore[attr-defined]

    return manufacturer, product


def _build_device_info(
    vid: int,
    pid: int,
    board_config: Optional[BoardConfig] = None,
    manufacturer: Optional[str] = None,
    product: Optional[str] = None
) -> Dict[str, Any]:
    """Build a standardized device information dictionary.

    Args:
        vid: Vendor ID
        pid: Product ID
        board_config: Known board configuration if applicable
        manufacturer: Manufacturer string from device
        product: Product string from device

    Returns:
        Standardized device information dictionary
    """
    vid_pid_key = format_vid_pid(vid, pid)

    if board_config:
        device_data = {
            "vid": f"0x{vid:04x}",
            "pid": f"0x{pid:04x}",
            "vid_pid": vid_pid_key,
            "name": board_config.name,
            "vendor": board_config.vendor,
            "type": board_config.device_type.value,
            "modes": dict(board_config.modes),  # Create a copy
            "detected": True,
            "known": True
        }
    else:
        device_data = {
            "vid": f"0x{vid:04x}",
            "pid": f"0x{pid:04x}",
            "vid_pid": vid_pid_key,
            "name": product or "Unknown USB Device",
            "vendor": manufacturer or "Unknown",
            "type": DeviceType.UNKNOWN.value,
            "detected": True,
            "known": False
        }

    # Add optional string descriptors if available
    if manufacturer:
        device_data["manufacturer_string"] = manufacturer
    if product:
        device_data["product_string"] = product

    _apply_arcade_identity_hints(device_data)

    return device_data


def _apply_arcade_identity_hints(device_data: Dict[str, Any]) -> None:
    """Promote richer board identity from descriptors when topology is unavailable.

    On systems where the WMI topology probe is unavailable, spoofed XInput
    encoder boards still surface through ``device_scanner`` with useful product
    strings such as ``Controller (PactoTech-2000T-FW 20250112)``. Without this
    pass the canonical board lane only exposes the generic
    ``Xbox 360 / XInput-Spoofed Arcade Encoder`` name, which makes the wizard
    look like it found a handheld gamepad instead of the cabinet encoder.

    Wave 2: model identification delegates to the shared
    ``services/pacto_identity`` module so all Pacto rules live in one place.
    """
    from .pacto_identity import detect_pacto_model

    promoted = detect_pacto_model(device_data)
    if not promoted:
        return

    device_data["name"] = promoted["name"]
    device_data["vendor"] = promoted["vendor"]
    if "board_type" in promoted:
        # Standalone XInput uses setdefault to preserve any prior board_type.
        if promoted["board_type"] == "Standalone_XInput":
            device_data.setdefault("board_type", promoted["board_type"])
        else:
            device_data["board_type"] = promoted["board_type"]
    if "players" in promoted:
        device_data["players"] = promoted["players"]


def detect_usb_devices(include_unknown: bool = False, use_cache: bool = True) -> List[Dict[str, Any]]:
    """Detect all USB devices, with special handling for arcade boards.

    Args:
        include_unknown: If True, include unrecognized USB devices
        use_cache: If True, use cached results if available and fresh

    Returns:
        List of device dictionaries with vid, pid, name, vendor, type, etc.

    Raises:
        USBBackendError: If USB backend is not available
        USBPermissionError: If insufficient permissions to access USB
        USBDetectionError: If USB enumeration fails critically
    """
    global _device_cache

    # Check cache if enabled
    if use_cache and _device_cache is not None:
        cache_time, cached_devices = _device_cache
        if time.time() - cache_time < DEVICE_CACHE_TTL:
            logger.debug(f"Using cached device list ({len(cached_devices)} devices)")
            # Filter based on include_unknown flag
            if not include_unknown:
                return [d for d in cached_devices if d.get("known", False)]
            return cached_devices

    devices: List[Dict[str, Any]] = []
    detected_devices: List[usb.core.Device] = []

    # Get USB backend explicitly
    backend = _get_usb_backend()
    if backend is None:
        # On Windows, try a safe registry-based fallback before failing
        if platform.system() == "Windows":
            logger.info("libusb backend not found; attempting Windows registry fallback for USB enumeration")
            devices = _enumerate_windows_registry_devices(include_unknown=include_unknown)
        else:
            # On Linux/WSL, try lsusb if available
            logger.info("libusb backend not found; attempting lsusb fallback enumeration")
            devices = _enumerate_lsusb(include_unknown=include_unknown)

        # Even if the registry/lsusb fallback found nothing, still apply the
        # Chuck-intelligence supplements (WMI XInput probe + device_scanner
        # promotion) so the canonical board lane benefits from the richer
        # detection that lives in neighbouring subsystems.
        _apply_chuck_intelligence_supplements(devices)

        if devices:
            _device_cache = (time.time(), devices)
            if not include_unknown:
                return [d for d in devices if d.get("known", False)]
            return devices

        error_msg = (
            "USB backend not available. "
            f"On {platform.system()}: "
        )
        if platform.system() == "Windows":
            error_msg += "Install libusb (e.g., Zadig WinUSB) or run Windows registry fallback by starting backend on Windows"
        elif platform.system() == "Linux":
            error_msg += "Install libusb-1.0-0 package (apt-get install libusb-1.0-0)"
        else:
            error_msg += "Install libusb via homebrew (brew install libusb)"

        logger.warning(error_msg)
        # Graceful fallback: return empty list instead of raising so panels can continue
        _device_cache = (time.time(), [])
        return []

    try:
        # Find all USB devices with explicit backend
        usb_devices = usb.core.find(find_all=True, backend=backend)

        # Convert generator to list to avoid multiple iterations
        # pyusb.find() returns Generator[Device] | Device | None, but we've passed find_all=True so it's always Generator
        detected_devices = list(usb_devices) if usb_devices is not None else []  # type: ignore[arg-type]

        if not detected_devices:
            # Don't early-return here: we still want the Windows WMI XInput
            # supplement below to run, since libusb cannot enumerate XUSB-owned
            # arcade encoder boards even when libusb itself succeeds.
            logger.info("No USB devices detected via libusb")
        else:
            logger.debug(f"Found {len(detected_devices)} USB devices")

        # Process each device
        for dev in detected_devices:
            try:
                # pyusb stubs don't expose idVendor/idProduct at type-check time, but they exist at runtime
                vid = dev.idVendor  # type: ignore[attr-defined]
                pid = dev.idProduct  # type: ignore[attr-defined]
                vid_pid_key = format_vid_pid(vid, pid)

                # Check if this is a known arcade board
                board_config = KNOWN_BOARDS.get(vid_pid_key)

                if board_config or include_unknown:
                    # Extract device strings once
                    manufacturer, product = _extract_device_strings(dev)

                    # Build device info
                    device_data = _build_device_info(
                        vid, pid, board_config, manufacturer, product
                    )

                    devices.append(device_data)

            except usb.core.USBError as e:
                # Check for permission errors
                if "access" in str(e).lower() or "permission" in str(e).lower():
                    # pyusb stubs don't expose idVendor/idProduct at type-check time, but they exist at runtime
                    logger.warning(f"Permission denied for device {dev.idVendor:04x}:{dev.idProduct:04x}")  # type: ignore[attr-defined]
                    if not devices:  # Only raise if we have no devices at all
                        raise USBPermissionError(
                            "Insufficient permissions to access USB devices. "
                            f"On {platform.system()}: run as administrator/root or add user to appropriate group"
                        )
                else:
                    logger.debug(f"Could not access USB device: {e}")
                continue
            except Exception as e:
                logger.debug(f"Unexpected error processing device: {e}")
                continue

    except usb.core.NoBackendError:
        # This shouldn't happen since we check backend explicitly, but handle it
        raise USBBackendError("USB backend became unavailable during enumeration")

    except usb.core.USBError as e:
        if "permission" in str(e).lower():
            raise USBPermissionError(f"USB permission error: {str(e)}")
        logger.error(f"USB detection failed: {e}")
        raise USBDetectionError(f"USB detection failed: {str(e)}")

    finally:
        # Clean up device references to free resources
        for dev in detected_devices:
            try:
                usb.util.dispose_resources(dev)
            except Exception:
                pass  # Best effort cleanup

    # Apply Chuck-intelligence supplements (WMI XInput probe + device_scanner
    # promotion) so the canonical board lane benefits from richer detection
    # that already exists in neighbouring Chuck subsystems.
    _apply_chuck_intelligence_supplements(devices)

    # Update cache
    _device_cache = (time.time(), devices)

    return devices


def detect_arcade_boards() -> List[Dict[str, Any]]:
    """Detect only known arcade controller boards.

    Returns:
        List of detected arcade boards (I-PAC, PacDrive, etc.)
    """
    try:
        all_devices = detect_usb_devices(include_unknown=False)
        # Filter to only keyboard_encoder and led_controller types
        arcade_boards = [
            dev for dev in all_devices
            if dev.get("type") in [
                DeviceType.KEYBOARD_ENCODER.value,
                DeviceType.LED_CONTROLLER.value
            ]
        ]
        return _coalesce_arcade_boards(arcade_boards)
    except USBDetectionError as e:
        logger.warning(f"Failed to detect arcade boards: {e}")
        return []


def _coalesce_arcade_boards(boards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse raw XInput child endpoints when a topology board is available.

    The canonical USB/device lanes can legitimately see both:
    1. raw spoofed XInput endpoints (one entry per child controller), and
    2. a topology-enriched logical board entry from ``encoder_detector``.

    For controller setup flows we want the logical board to be the source of
    truth, not the child endpoints. When topology entries are present for the
    known arcade XInput VID/PIDs, suppress the raw child nodes and return the
    logical board list instead.
    """
    if not boards:
        return []

    has_topology_xinput_board = any(
        board.get("vid_pid") in ARCADE_XINPUT_VID_PIDS
        and board.get("parent_hub")
        and board.get("board_type")
        for board in boards
    )

    coalesced: List[Dict[str, Any]] = []
    seen_keys = set()

    for board in boards:
        vid_pid = board.get("vid_pid")
        parent_hub = board.get("parent_hub")
        is_raw_xinput_child = vid_pid in ARCADE_XINPUT_VID_PIDS and not parent_hub

        if has_topology_xinput_board and is_raw_xinput_child:
            continue

        dedupe_key = (
            vid_pid,
            parent_hub or board.get("device_id") or board.get("name"),
        )
        if dedupe_key in seen_keys:
            continue

        seen_keys.add(dedupe_key)
        coalesced.append(board)

    return coalesced


def get_board_by_vid_pid(vid: str, pid: str) -> Optional[Dict[str, Any]]:
    """Get board info by VID/PID if connected.

    Args:
        vid: Vendor ID (hex string like '0xd209' or 'd209')
        pid: Product ID (hex string like '0x0501' or '0501')

    Returns:
        Board info dict if found and connected, None otherwise
    """
    # Normalize VID/PID format
    vid_clean = vid.lower().replace('0x', '').strip()
    pid_clean = pid.lower().replace('0x', '').strip()

    # Validate hex format
    try:
        int(vid_clean, 16)
        int(pid_clean, 16)
    except ValueError:
        logger.error(f"Invalid VID/PID format: {vid}/{pid}")
        return None

    vid_pid_key = f"{vid_clean}:{pid_clean}"

    # Check if it's a known board first
    if vid_pid_key not in KNOWN_BOARDS:
        return None

    # Check if it's actually connected
    try:
        devices = detect_usb_devices(include_unknown=False, use_cache=True)
        for dev in devices:
            if dev.get("vid_pid") == vid_pid_key:
                return dev
    except USBDetectionError:
        pass

    return None


@lru_cache(maxsize=1)
def get_supported_boards() -> List[Dict[str, Any]]:
    """Get list of all supported arcade boards (for manual selection).

    Returns:
        List of board info dicts for all known boards

    Note:
        Result is cached since the supported boards list is static
    """
    boards = []
    for vid_pid, config in KNOWN_BOARDS.items():
        vid, pid = vid_pid.split(":")
        board = {
            "vid": f"0x{vid}",
            "pid": f"0x{pid}",
            "vid_pid": vid_pid,
            "name": config.name,
            "vendor": config.vendor,
            "type": config.device_type.value,
            "modes": dict(config.modes),
            "detected": False,  # Will be updated by detection
            "known": True
        }
        boards.append(board)

    return sorted(boards, key=lambda x: (x["vendor"], x["name"]))


def invalidate_cache() -> None:
    """Invalidate the device detection cache.

    Use this when you know the USB configuration has changed.
    """
    global _device_cache
    _device_cache = None
    logger.debug("USB device cache invalidated")


def get_connection_troubleshooting_hints(
    board_type: str = "keyboard_encoder",
    os_type: Optional[str] = None
) -> List[str]:
    """Get troubleshooting hints for board connection issues.

    Args:
        board_type: Type of board (keyboard_encoder, led_controller, etc.)
        os_type: Operating system type (Windows, Linux, Darwin) or None to auto-detect

    Returns:
        List of troubleshooting hint strings
    """
    if os_type is None:
        os_type = platform.system()

    hints = []

    # Common hints for all platforms
    hints.extend([
        "Ensure the USB cable is securely connected to both the board and the PC",
        "Try a different USB port (USB 2.0 ports work best for arcade hardware)",
        "Check if the board's LED indicators are lit (if applicable)",
        "Verify the board has power (some boards require external power)",
    ])

    # OS-specific hints
    if os_type == "Windows":
        hints.extend([
            "Check Device Manager to see if the board appears with a yellow exclamation mark",
            "Try installing the manufacturer's drivers from their website",
            "Some boards require running the configuration utility before they're recognized",
            "Run this application as Administrator for full USB access",
        ])
    elif os_type == "Linux":
        hints.extend([
            "Check if you have permission to access USB devices: sudo usermod -a -G plugdev $USER",
            "Install libusb-1.0: sudo apt-get install libusb-1.0-0-dev",
            "Check dmesg for USB-related errors: dmesg | grep -i usb",
            "You may need to add a udev rule for your specific device",
        ])
    elif os_type == "Darwin":  # macOS
        hints.extend([
            "Grant USB access permissions in System Preferences > Security & Privacy",
            "Install libusb via Homebrew: brew install libusb",
            "Some devices require kernel extension approval in System Preferences",
        ])

    # Board type specific hints
    if board_type == DeviceType.KEYBOARD_ENCODER.value:
        hints.append("I-PAC and similar boards appear as standard keyboards - check if keyboard input works")
    elif board_type == DeviceType.LED_CONTROLLER.value:
        hints.append("LED controllers usually require configuration software to be installed first")

    return hints


# Module-level test function
def main() -> None:
    """Run USB detection tests and display results."""
    print("USB Device Detection Test")
    print("=" * 50)

    try:
        print(f"\nPlatform: {platform.system()}")
        print(f"Python: {platform.python_version()}")

        print("\nDetecting all USB devices (including unknown)...")
        devices = detect_usb_devices(include_unknown=True, use_cache=False)
        print(f"Found {len(devices)} USB devices")

        for dev in devices:
            print(f"\n  {dev['name']}")
            print(f"    VID:PID = {dev['vid_pid']}")
            print(f"    Vendor: {dev['vendor']}")
            print(f"    Type: {dev['type']}")
            if dev.get("modes"):
                print(f"    Modes: {', '.join(dev['modes'].keys())}")

        print("\n" + "=" * 50)
        print("\nDetecting arcade boards only...")
        arcade = detect_arcade_boards()
        print(f"Found {len(arcade)} arcade boards")

        for board in arcade:
            print(f"\n  {board['name']} - {'CONNECTED' if board['detected'] else 'NOT DETECTED'}")

        print("\n" + "=" * 50)
        print("\nSupported boards:")
        supported = get_supported_boards()
        for board in supported:
            print(f"  - {board['name']} ({board['vid_pid']})")

        # Test cache
        print("\n" + "=" * 50)
        print("\nTesting cache performance...")
        import timeit

        # First call (no cache)
        t1 = timeit.timeit(lambda: detect_usb_devices(use_cache=False), number=1)
        print(f"Without cache: {t1*1000:.2f}ms")

        # Second call (with cache)
        t2 = timeit.timeit(lambda: detect_usb_devices(use_cache=True), number=1)
        print(f"With cache: {t2*1000:.2f}ms")
        print(f"Cache speedup: {t1/t2:.1f}x")

    except USBBackendError as e:
        print(f"\nERROR: {e}")
        print("\nBackend Installation Instructions:")
        hints = get_connection_troubleshooting_hints()
        for hint in hints[:3]:  # Show first 3 hints
            print(f"  - {hint}")

    except USBPermissionError as e:
        print(f"\nERROR: {e}")
        print("\nPermission Resolution:")
        if platform.system() == "Windows":
            print("  Run this application as Administrator")
        else:
            print("  Run with sudo or add your user to the appropriate group")

    except USBDetectionError as e:
        print(f"\nERROR: {e}")
        print("\nTroubleshooting hints:")
        for hint in get_connection_troubleshooting_hints():
            print(f"  - {hint}")
