from __future__ import annotations
import logging
from typing import Sequence
from .ledwiz_shim_client import get_shim_client

logger = logging.getLogger("led_engine.shim_driver")

class LEDWizShimDriver:
    """Driver that communicates via the C++ Shim Daemon."""

    def __init__(self, device_id: str, ledwiz_id: int):
        self.device_id = device_id
        self.ledwiz_id = ledwiz_id # 1-based
        self.channel_count = 32
        self._client = get_shim_client()

    @classmethod
    async def discover(cls) -> list["LEDWizShimDriver"]:
        """
        In the shim model, discovery is handled by the daemon.
        We return 16 potential drivers (the maximum supported units).
        The daemon will only send data to units it actually finds.
        """
        drivers = []
        for i in range(1, 17):
            pid = 0x00EF + i
            device_id = f"fafa:{pid:04x}"
            drivers.append(cls(device_id=device_id, ledwiz_id=i))

        # Tell the shim to rediscover hardware
        client = get_shim_client()
        client.discover()

        return drivers

    async def set_channels(self, frame: Sequence[int]) -> None:
        """Write a full brightness frame via the shim."""
        # Use a thread pool or just direct call since it's a pipe write
        self._client.set_channels(self.ledwiz_id, frame)

    async def close(self) -> None:
        pass
