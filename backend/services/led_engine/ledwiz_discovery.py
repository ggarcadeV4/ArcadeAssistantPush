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


async def register_devices(registry) -> Dict[str, "LEDWizShimDriver"]:
    """Populate the LED registry with detected LED-Wiz drivers.
    
    Uses the C++ Shim-based driver for high-performance, reliable LED control.
    """
    from .ledwiz_shim_driver import LEDWizShimDriver
    
    devices_map: Dict[str, LEDWizShimDriver] = {}
    try:
        # Prioritize the C++ Shim driver as per the 'Day 5' mission briefing
        logger.info("Initializing C++ Shim-based LED-Wiz drivers")
        shim_drivers = await LEDWizShimDriver.discover()

        # We also still perform HID discovery for UI reporting/discovery status
        discovered = await discover_devices()
        if hasattr(registry, "update_discovery"):
            registry.update_discovery(discovered)

        # Register all potential shim drivers
        for driver in shim_drivers:
            devices_map[driver.device_id] = driver
            
        logger.info("Registered %d potential LED-Wiz units via C++ Shim", len(shim_drivers))

    except Exception as exc:  # pragma: no cover - defensive
        logger.error("LED-Wiz registration failed: %s", exc)
        devices_map = {}
        if hasattr(registry, "update_discovery"):
            registry.update_discovery([])

    if hasattr(registry, "replace_devices"):
        registry.replace_devices(devices_map)
    return devices_map


__all__ = ["DeviceInfo", "discover_devices", "register_devices"]
