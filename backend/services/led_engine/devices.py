"""Device abstraction layer for runtime LED output."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Iterable, List, Optional, Protocol, Sequence

from .ledwiz_discovery import DeviceInfo, register_devices

logger = logging.getLogger("led_engine.devices")


class LEDDevice(Protocol):
    """Common protocol implemented by LED hardware drivers."""

    device_id: str
    channel_count: int

    async def set_channels(self, frame: Sequence[int]) -> None:
        ...

    async def close(self) -> None:
        ...


class MockLEDDevice:
    """Fallback device used when no physical controllers are available."""

    def __init__(self, channel_count: int = 32):
        self.device_id = "mock-led-device"
        self.channel_count = channel_count
        self.last_frame: Sequence[int] | None = None

    async def set_channels(self, frame: Sequence[int]) -> None:  # pragma: no cover - trivial
        self.last_frame = list(frame)

    async def close(self) -> None:  # pragma: no cover - trivial
        return


class DeviceRegistry:
    """Tracks available LED hardware drivers."""

    def __init__(self):
        self._devices: Dict[str, LEDDevice] = {}
        self._lock = asyncio.Lock()
        self._simulation = False
        self._last_refresh: float | None = None
        self._discovery: List[DeviceInfo] = []

    async def refresh(self) -> None:
        """Re-scan hardware and rebuild the registry."""
        async with self._lock:
            try:
                await register_devices(self)
                devices = dict(self._devices)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("LED device refresh failed: %s", exc)
                devices = {}
                self._discovery = []

            if not devices:
                logger.info("No LED hardware detected; entering simulation mode")
                mock = MockLEDDevice()
                devices = {mock.device_id: mock}
                self._simulation = True
            else:
                self._simulation = False
            self._devices = devices
            self._last_refresh = time.time()

    async def get(self, device_id: str) -> Optional[LEDDevice]:
        async with self._lock:
            if not self._devices:
                await self.refresh()
            return self._devices.get(device_id)

    async def get_default(self) -> LEDDevice:
        async with self._lock:
            if not self._devices:
                await self.refresh()
            # Return first device
            return next(iter(self._devices.values()))

    def all_devices(self) -> Iterable[LEDDevice]:
        return list(self._devices.values())

    def channel_count(self, device_id: Optional[str]) -> int:
        if not device_id:
            return 32
        device = self._devices.get(device_id)
        return device.channel_count if device else 32

    # ------------------------------------------------------------------
    # Discovery helpers
    # ------------------------------------------------------------------

    def replace_devices(self, devices: Dict[str, LEDDevice]) -> None:
        self._devices = devices

    def update_discovery(self, entries: Iterable[DeviceInfo]) -> None:
        self._discovery = list(entries)

    def discovery_snapshot(self) -> List[DeviceInfo]:
        return list(self._discovery)

    def simulation_mode(self) -> bool:
        return self._simulation

    def last_refresh(self) -> float | None:
        return self._last_refresh
