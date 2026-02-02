"""LED-Wiz DLL-based driver - wraps ledwiz64.dll for LED output.

This driver uses the official LEDWiz DLL instead of raw HID,
which is more reliable and compatible with the LWCloneU2 replacement DLL.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Sequence

from .ledwiz_dll_wrapper import LEDWizDLL, get_ledwiz_dll

logger = logging.getLogger("led_engine.ledwiz_dll_driver")


class LEDWizDLLDriver:
    """LED-Wiz driver using the official DLL (via ctypes).
    
    This driver conforms to the LEDDevice protocol and can be used
    as a drop-in replacement for the raw HID LEDWizDriver.
    """
    
    CHANNEL_COUNT = 32
    
    def __init__(
        self,
        device_id: str = "fafa:00f0",
        ledwiz_id: int = 1,
    ):
        """Initialize the DLL-based driver.
        
        Args:
            device_id: Device identifier for compatibility with existing code.
            ledwiz_id: LED-Wiz device number (1-16). Most setups use 1.
        """
        self.device_id = device_id
        self.channel_count = self.CHANNEL_COUNT
        self.ledwiz_id = ledwiz_id
        self._dll: LEDWizDLL | None = None
        self._lock = asyncio.Lock()
        self._last_frame: list[int] = [0] * self.CHANNEL_COUNT
        self._last_write_ts: float | None = None
        
        # Additional properties for compatibility with status reporting
        self.vendor_id = 0xFAFA
        self.product_id = 0x00F0
        self.serial = "unknown"
        self.manufacturer = "GGG"
        self.product_name = "LED-Wiz (DLL)"
    
    def _ensure_loaded(self) -> bool:
        """Ensure the DLL is loaded, loading it if necessary."""
        if self._dll is None:
            self._dll = LEDWizDLL(device_id=self.ledwiz_id)
            if not self._dll.load():
                logger.error("Failed to load LEDWiz DLL")
                self._dll = None
                return False
            logger.info("LEDWiz DLL driver initialized for device %s", self.device_id)
        return self._dll.is_loaded()
    
    async def set_channels(self, frame: Sequence[int]) -> None:
        """Write a full brightness frame to the device.
        
        Args:
            frame: Sequence of 32 brightness values (0-48)
        """
        async with self._lock:
            if not self._ensure_loaded():
                logger.warning("Cannot set channels - DLL not loaded")
                return
            
            # Run DLL call in thread to avoid blocking the event loop
            await asyncio.to_thread(self._dll.set_channels, frame)
            self._last_frame = list(frame[:self.CHANNEL_COUNT])
            self._last_write_ts = time.time()
    
    async def close(self) -> None:
        """Close the driver (DLL is shared, so this is a no-op)."""
        pass
    
    @property
    def last_hid_write(self) -> float | None:
        """Return timestamp of last write for compatibility."""
        return self._last_write_ts
    
    @classmethod
    async def discover(cls) -> list["LEDWizDLLDriver"]:
        """Discover LED-Wiz devices using HID enumeration + DLL control.

        The DLL's LWZ_REGISTER doesn't reliably return device count on all systems,
        so we use HID enumeration to find devices, then create DLL drivers for control.
        """
        from .ledwiz_discovery import discover_devices as hid_discover

        # First verify DLL can load (needed for control)
        dll = LEDWizDLL(device_id=1)
        if not dll.load():
            logger.error("LED-Wiz DLL failed to load")
            return []

        # Use HID enumeration to find all LED-Wiz devices
        hid_devices = await hid_discover()

        if not hid_devices:
            logger.info("No LED-Wiz devices found via HID enumeration")
            return []

        logger.info("LED-Wiz detected via HID: %d device(s)", len(hid_devices))

        # Create a DLL driver for each HID device found
        drivers = []
        for i, hid_dev in enumerate(hid_devices, start=1):
            device_id = f"{hid_dev.vendor_id:04x}:{hid_dev.product_id:04x}"
            driver = cls(device_id=device_id, ledwiz_id=i)
            drivers.append(driver)
            logger.info("Created driver for LED-Wiz device %d (%s - %s)", i, device_id, hid_dev.product)

        return drivers


# Singleton driver instance for the LED engine
_driver_instance: LEDWizDLLDriver | None = None


def get_dll_driver() -> LEDWizDLLDriver:
    """Get the singleton DLL-based LED-Wiz driver."""
    global _driver_instance
    if _driver_instance is None:
        _driver_instance = LEDWizDLLDriver()
    return _driver_instance
