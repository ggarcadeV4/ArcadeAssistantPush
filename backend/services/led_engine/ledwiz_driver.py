"""LED-Wiz HID driver implementation."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Sequence

try:
    import hid  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    hid = None

logger = logging.getLogger("led_engine.ledwiz")


class LEDWizDriver:
    """Concrete LEDDevice implementation for LED-Wiz controllers."""

    SUPPORTED_IDS = {
        (0xFAFA, 0x00F0),  # LED-Wiz Device 1
        (0xFAFA, 0x00F1),  # LED-Wiz Device 2
        (0xFAFA, 0x00F2),  # LED-Wiz Device 3
        (0xFAFA, 0x00F3),  # LED-Wiz Device 4
        (0xFAFA, 0x00F4),  # LED-Wiz Device 5
        (0xFAFA, 0x00F5),  # LED-Wiz Device 6
        (0xFAFA, 0x00F6),  # LED-Wiz Device 7
        (0xFAFA, 0x00F7),  # LED-Wiz Device 8
    }
    CHANNEL_COUNT = 32
    PACKET_LENGTH = 9  # HID report length including report ID byte

    def __init__(
        self,
        path: bytes,
        vendor_id: int,
        product_id: int,
        serial: str | None = None,
        product: str | None = None,
        manufacturer: str | None = None,
    ):
        self._path = path
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.serial = serial or "unknown"
        self.product_name = product or "LED-Wiz"
        self.manufacturer = manufacturer or "Groovy Game Gear"
        self.device_id = f"{vendor_id:04x}:{product_id:04x}"
        self.channel_count = self.CHANNEL_COUNT
        self._lock = asyncio.Lock()
        self._last_write_monotonic = 0.0
        self._last_write_ts: float | None = None
        self._last_frame: List[int] = [0] * self.channel_count

    @classmethod
    async def discover(cls) -> List["LEDWizDriver"]:
        """Detect all connected LED-Wiz devices."""
        if hid is None:
            logger.info("hid module not available; LED-Wiz detection disabled")
            return []

        def _enumerate() -> List["LEDWizDriver"]:
            devices: List[LEDWizDriver] = []
            for info in hid.enumerate():
                vid = info.get("vendor_id")
                pid = info.get("product_id")
                if (vid, pid) in cls.SUPPORTED_IDS:
                    devices.append(
                        cls(
                            path=info["path"],
                            vendor_id=vid,
                            product_id=pid,
                            serial=info.get("serial_number"),
                        )
                    )
            return devices

        return await asyncio.to_thread(_enumerate)

    async def set_channels(self, frame: Sequence[int]) -> None:
        """Write a full brightness frame to the device."""
        frame_copy = list(frame[: self.channel_count])
        if len(frame_copy) < self.channel_count:
            frame_copy.extend([0] * (self.channel_count - len(frame_copy)))

        async with self._lock:
            if hid is None:
                self._last_frame = frame_copy
                self._last_write_ts = time.time()
                return
            await asyncio.to_thread(self._write_frame, frame_copy)

    async def close(self) -> None:
        """Placeholder close hook (LED-Wiz has no persistent connection)."""
        return

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _write_frame(self, frame: List[int]) -> None:
        """Write LED-Wiz frame using proper SBA + PBA protocol.
        
        LED-Wiz protocol requires two command types:
        - SBA (Set Bank Address): 8-byte command to turn outputs ON/OFF
          Format: [Report ID, bank0, bank1, bank2, bank3, pulseSpeed, 0, 0, 0]
          bank0-3 are bitmasks for outputs 1-8, 9-16, 17-24, 25-32
        
        - PBA (Profile Brightness Address): 32 brightness values in 4 chunks
          Format: [Report ID, b1, b2, b3, b4, b5, b6, b7, b8] (values 0-48)
          First byte marker: 0x40 (64) for PBA command
        """
        now = time.monotonic()
        delta = now - self._last_write_monotonic
        if delta < 0.01:
            time.sleep(0.01 - delta)

        logger.info("[LEDWiz] _write_frame called for device %s", self.device_id)
        logger.info("[LEDWiz] Frame: %s", frame[:8])

        try:
            device = hid.device()
            device.open_path(self._path)
            device.set_nonblocking(0)
            logger.info("[LEDWiz] Device opened at path: %s", self._path)

            # Build bank bitmasks for SBA command (which outputs are ON)
            bank0 = bank1 = bank2 = bank3 = 0
            for i, val in enumerate(frame[:32]):
                if val > 0:  # Output is ON if brightness > 0
                    if i < 8:
                        bank0 |= (1 << i)
                    elif i < 16:
                        bank1 |= (1 << (i - 8))
                    elif i < 24:
                        bank2 |= (1 << (i - 16))
                    else:
                        bank3 |= (1 << (i - 24))

            # Send SBA command: turn outputs ON/OFF + set pulse speed (2)
            sba_packet = [0x00, bank0, bank1, bank2, bank3, 2, 0, 0, 0]
            logger.info("[LEDWiz] SBA packet: %s", sba_packet)
            bytes_written = device.write(sba_packet[:self.PACKET_LENGTH])
            logger.info("[LEDWiz] SBA bytes written: %s", bytes_written)

            # Send PBA commands: set brightness for each output (4 chunks of 8)
            # PBA uses marker 0x40-0x43 for chunks 0-3
            for chunk_idx in range(4):
                start = chunk_idx * 8
                chunk = frame[start:start + 8]
                # Downsample 0-255 to LED-Wiz brightness range (1-48, 0 = off)
                # Note: 0 means "off/default", 1-48 is PWM brightness
                clamped = [max(0, min(48, int(v * 48.0 / 255.0))) for v in chunk]
                # PBA packet: marker + 8 brightness values
                marker = 0x40 + chunk_idx  # 0x40, 0x41, 0x42, 0x43
                pba_packet = [0x00, marker] + clamped
                while len(pba_packet) < self.PACKET_LENGTH:
                    pba_packet.append(0x00)
                logger.info("[LEDWiz] PBA packet %d: %s", chunk_idx, pba_packet)
                bytes_written = device.write(pba_packet[:self.PACKET_LENGTH])
                logger.info("[LEDWiz] PBA bytes written: %s", bytes_written)

            device.close()
            self._last_frame = frame
            self._last_write_monotonic = time.monotonic()
            self._last_write_ts = time.time()
            logger.info("[LEDWiz] Write complete for %s", self.device_id)
        except OSError as exc:
            logger.error("[LEDWiz] Write failed (OSError): %s", exc)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("[LEDWiz] Unexpected error: %s", exc)

    def _clamp_values(self, values: Sequence[int], target_len: int) -> List[int]:
        clamped = [max(0, min(48, int(value))) for value in values]
        if len(clamped) < target_len:
            clamped.extend([0] * (target_len - len(clamped)))
        return clamped

    @property
    def last_hid_write(self) -> float | None:
        """Return the wall-clock timestamp of the most recent HID write."""
        return self._last_write_ts
