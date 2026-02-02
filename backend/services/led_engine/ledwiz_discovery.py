"""LED-Wiz hardware discovery helpers."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List

try:  # pragma: no cover - optional dependency
    import hid  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    hid = None

from .ledwiz_driver import LEDWizDriver

logger = logging.getLogger("led_engine.ledwiz_discovery")


@dataclass
class DeviceInfo:
    """Snapshot of a detected LED-Wiz device."""

    path: bytes
    vendor_id: int
    product_id: int
    serial_number: str | None = None
    manufacturer: str | None = None
    product: str | None = None

    def as_dict(self) -> Dict[str, object]:
        """Return a JSON-safe payload for status endpoints."""
        path_value: str
        if isinstance(self.path, (bytes, bytearray)):
            path_value = self.path.decode(errors="ignore")
        else:
            path_value = str(self.path)
        return {
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "serial_number": self.serial_number,
            "manufacturer": self.manufacturer,
            "product": self.product,
            "path": path_value,
        }


async def discover_devices() -> List[DeviceInfo]:
    """Return all LED-Wiz HID descriptors without opening the devices."""
    if hid is None:
        logger.info("hid module not available; LED-Wiz discovery disabled")
        return []

    def _scan() -> List[DeviceInfo]:
        devices: List[DeviceInfo] = []
        for info in hid.enumerate():
            vendor_id = info.get("vendor_id")
            product_id = info.get("product_id")
            if (vendor_id, product_id) not in LEDWizDriver.SUPPORTED_IDS:
                continue
            devices.append(
                DeviceInfo(
                    path=info.get("path", b""),
                    vendor_id=vendor_id,
                    product_id=product_id,
                    serial_number=info.get("serial_number") or info.get("serial"),
                    manufacturer=info.get("manufacturer_string"),
                    product=info.get("product_string"),
                )
            )
        return devices

    return await asyncio.to_thread(_scan)


async def register_devices(registry) -> Dict[str, "LEDWizDLLDriver"]:
    """Populate the LED registry with detected LED-Wiz drivers.
    
    Uses the DLL-based driver for reliable LED control.
    """
    from .ledwiz_dll_driver import LEDWizDLLDriver
    
    devices_map: Dict[str, LEDWizDLLDriver] = {}
    try:
        # First, try to discover via DLL (more reliable)
        dll_drivers = await LEDWizDLLDriver.discover()
        if dll_drivers:
            logger.info("Using DLL-based LED-Wiz driver")
            for driver in dll_drivers:
                devices_map[driver.device_id] = driver
        else:
            # Fall back to HID discovery for device info only
            discovered = await discover_devices()
            if hasattr(registry, "update_discovery"):
                registry.update_discovery(discovered)
            
            if discovered:
                # Create DLL driver for first discovered device
                logger.info("Creating DLL driver for discovered LED-Wiz")
                driver = LEDWizDLLDriver(
                    device_id=f"{discovered[0].vendor_id:04x}:{discovered[0].product_id:04x}",
                    ledwiz_id=1,
                )
                devices_map[driver.device_id] = driver
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("LED-Wiz registration failed: %s", exc)
        devices_map = {}
        if hasattr(registry, "update_discovery"):
            registry.update_discovery([])

    if hasattr(registry, "replace_devices"):
        registry.replace_devices(devices_map)
    return devices_map


__all__ = ["DeviceInfo", "discover_devices", "register_devices"]
