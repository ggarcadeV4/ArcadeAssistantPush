from __future__ import annotations
import logging
from typing import Sequence
from .ledwiz_shim_client import get_shim_client

logger = logging.getLogger("led_engine.shim_driver")

# =============================================================================
# CINEMA CALIBRATION LOGIC (Gamma 2.5)
# =============================================================================
GAMMA = 2.5
MAX_BRIGHTNESS_MODE = False

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

    def _apply_cinema_calibration(self, frame: Sequence[int]) -> list[int]:
        """Apply Gamma 2.5 and Color Scaling logic (Cinema Calibration)."""
        if MAX_BRIGHTNESS_MODE:
            # If MAX_BRIGHTNESS_MODE is True, everything > 0 is full bright (48)
            return [48 if v > 0 else 0 for v in frame]

        # Gamma 2.5 scaling for the 0-48 range
        calibrated = []
        for v in frame:
            if v <= 0:
                calibrated.append(0)
            else:
                # Normalize 0-48 to 0.0-1.0, apply gamma, then scale back to 0-48
                normalized = min(1.0, v / 48.0)
                gamma_val = normalized ** GAMMA
                calibrated.append(max(0, min(48, int(gamma_val * 48.0))))
        return calibrated

    async def set_channels(self, frame: Sequence[int]) -> None:
        """Write a full brightness frame via the shim."""
        # Apply cinema calibration before sending to the transport layer
        calibrated_frame = self._apply_cinema_calibration(frame)
        self._client.set_channels(self.ledwiz_id, calibrated_frame)

    async def close(self) -> None:
        pass
