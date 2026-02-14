"""Runtime USB/HID device scanner.

Attempts to enumerate every connected HID/XInput device so the UI can display
raw hardware inventory regardless of prior classification.
"""

from __future__ import annotations

import datetime as dt
import logging
import platform
import sys
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

try:  # hidapi-based enumeration (preferred for HID class devices)
    import hid  # type: ignore
except Exception:  # pragma: no cover
    hid = None  # type: ignore

try:
    import usb.core  # type: ignore
    import usb.util  # type: ignore
except Exception:  # pragma: no cover
    usb = None  # type: ignore

try:  # pygame for XInput/gamepad detection
    import pygame
    if not pygame.get_init():
        pygame.init()
    if not pygame.joystick.get_init():
        pygame.joystick.init()
except Exception:  # pragma: no cover
    pygame = None  # type: ignore


def _format_hex(value: int | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("0x"):
            return value.lower()
        try:
            value_int = int(value, 16)
        except ValueError:
            return None
        return f"0x{value_int:04x}"
    return f"0x{value:04x}"


def _hid_enumeration() -> List[Dict[str, Any]]:
    devices: List[Dict[str, Any]] = []
    if not hid:
        return devices

    try:
        for info in hid.enumerate():
            vid = _format_hex(info.get("vendor_id"))
            pid = _format_hex(info.get("product_id"))
            device_id = info.get("path") or f"HID::{vid}:{pid}"
            devices.append(
                {
                    "device_id": str(device_id),
                    "vid": vid,
                    "pid": pid,
                    "product": info.get("product_string"),
                    "manufacturer": info.get("manufacturer_string"),
                    "interface": "hid",
                    "usage_page": info.get("usage_page"),
                    "usage": info.get("usage"),
                    "xinput": False,
                    "timestamp": dt.datetime.utcnow().isoformat(),
                }
            )
    except Exception as exc:  # pragma: no cover - hardware dependent
        logger.debug("HID enumeration failed: %s", exc)
    return devices


def _usb_enumeration() -> List[Dict[str, Any]]:
    devices: List[Dict[str, Any]] = []
    if usb is None:  # pragma: no cover - optional dependency
        return devices
    try:
        for dev in usb.core.find(find_all=True):
            vid = _format_hex(dev.idVendor)
            pid = _format_hex(dev.idProduct)
            device_id = f"USB\\VID_{vid[2:].upper() if vid else '0000'}&PID_{pid[2:].upper() if pid else '0000'}"
            devices.append(
                {
                    "device_id": device_id,
                    "vid": vid,
                    "pid": pid,
                    "product": usb.util.get_string(dev, dev.iProduct) if dev.iProduct else None,
                    "manufacturer": usb.util.get_string(dev, dev.iManufacturer) if dev.iManufacturer else None,
                    "interface": "usb",
                    "usage_page": None,
                    "usage": None,
                    "xinput": False,
                    "timestamp": dt.datetime.utcnow().isoformat(),
                }
            )
    except Exception as exc:  # pragma: no cover
        logger.debug("USB enumeration failed: %s", exc)
    return devices


def _xinput_enumeration() -> List[Dict[str, Any]]:
    """Enumerate XInput/gamepad devices using pygame.
    
    XInput devices (like PactoTech-2000T in gamepad mode) don't show up
    in HID enumeration because Windows uses a different driver for them.
    """
    devices: List[Dict[str, Any]] = []
    if pygame is None:
        logger.debug("pygame not available for XInput enumeration")
        return devices

    try:
        # Refresh joystick detection
        pygame.joystick.quit()
        pygame.joystick.init()
        
        joystick_count = pygame.joystick.get_count()
        logger.info("XInput enumeration found %d joystick(s)", joystick_count)
        
        for i in range(joystick_count):
            try:
                js = pygame.joystick.Joystick(i)
                js.init()
                name = js.get_name()
                
                # Create a unique device ID for this joystick
                device_id = f"XINPUT\\JOYSTICK_{i}\\{name.replace(' ', '_').upper()}"
                
                # Detect if this is a PactoTech or other arcade encoder
                is_pactotech = "pactotech" in name.lower() or "pactec" in name.lower()
                is_xbox = "xbox" in name.lower() or "controller" in name.lower()
                
                # Try to determine VID/PID from name (not always available via pygame)
                vid = "0x045e" if is_xbox or is_pactotech else None  # Microsoft VID for XInput
                pid = "0x028e" if is_xbox or is_pactotech else None  # Standard Xbox controller PID
                
                devices.append({
                    "device_id": device_id,
                    "vid": vid,
                    "pid": pid,
                    "product": name,
                    "manufacturer": "XInput Device",
                    "interface": "xinput",
                    "usage_page": None,
                    "usage": None,
                    "xinput": True,
                    "joystick_index": i,
                    "num_buttons": js.get_numbuttons(),
                    "num_axes": js.get_numaxes(),
                    "num_hats": js.get_numhats(),
                    "suggested_role": "arcade_encoder" if is_pactotech else None,
                    "timestamp": dt.datetime.utcnow().isoformat(),
                })
                
                logger.info("XInput device %d: %s (%d buttons, %d axes, %d hats)",
                           i, name, js.get_numbuttons(), js.get_numaxes(), js.get_numhats())
                
            except Exception as e:
                logger.debug("Failed to enumerate joystick %d: %s", i, e)
                
    except Exception as exc:
        logger.debug("XInput enumeration failed: %s", exc)
    
    return devices


def scan_devices() -> List[Dict[str, Any]]:
    """Return best-effort snapshot of connected devices."""
    snapshot: Dict[str, Dict[str, Any]] = {}

    # HID devices first
    for device in _hid_enumeration():
        snapshot[device["device_id"]] = device

    # USB devices (fills in gaps)
    for device in _usb_enumeration():
        snapshot.setdefault(device["device_id"], device)
    
    # XInput/gamepad devices (includes PactoTech-2000T)
    for device in _xinput_enumeration():
        snapshot[device["device_id"]] = device

    # Add platform specific hints and suggested roles
    if platform.system().lower() == "windows":
        for device in snapshot.values():
            vid = device.get("vid", "")
            pid = device.get("pid", "")
            
            # XInput detection (Xbox controllers, PactoTech in XInput mode)
            if vid == "0x045e" and pid in {"0x028e", "0x02ea"}:
                device["xinput"] = True
                device["suggested_role"] = "arcade_encoder"
            
            # LED-Wiz detection (GGG vendor ID 0xfafa)
            # These are LED controllers, NOT arcade encoders
            if vid == "0xfafa":
                device["is_led_device"] = True
                device["suggested_role"] = "led_controller"
                logger.debug("LED-Wiz detected: %s (PID: %s)", device.get("device_id"), pid)
            
            # Ultimarc devices
            if vid == "0xd209":
                # U-Trak trackball
                if pid == "0x15a1":
                    device["suggested_role"] = "arcade_encoder"
                    device["device_subtype"] = "trackball"

    return list(snapshot.values())


__all__ = ["scan_devices"]

