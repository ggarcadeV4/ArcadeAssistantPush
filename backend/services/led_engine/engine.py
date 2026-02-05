"""Asynchronous LED runtime engine."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .devices import DeviceRegistry, LEDDevice
from .patterns import PatternRenderer, color_to_brightness
from .state import LEDChannelAssignment, PatternState

logger = logging.getLogger("led_engine.engine")


class LEDEngine:
    """Runtime daemon that merges LED commands into real hardware frames."""

    def __init__(self, drive_root: Path, manifest: Dict[str, object]):
        self.drive_root = Path(drive_root)
        self.manifest = manifest or {}
        self.registry = DeviceRegistry()
        self._renderer = PatternRenderer()
        self._queue: asyncio.Queue[Dict[str, object]] = asyncio.Queue()
        self._profile_frames: Dict[str, List[int]] = {}
        self._active_pattern: Optional[PatternState] = None
        self._global_brightness = 85
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._event_log = deque(maxlen=200)
        self._loop_interval = 0.05
        self._last_tick_ms = 0.0
        self._last_hid_write: Optional[float] = None
        self._last_error: Optional[str] = None
        self._voice_amplitude: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    def ensure_started(self) -> None:
        if self._task is None or self._task.done():
            loop = asyncio.get_event_loop()
            self._running = True
            self._task = loop.create_task(self._engine_loop())

    async def shutdown(self) -> None:
        self._running = False
        if self._task:
            await self._task

    # ------------------------------------------------------------------
    # Public command APIs
    # ------------------------------------------------------------------

    async def apply_profile(self, resolved_buttons: Iterable[Dict[str, object]]) -> None:
        assignments = list(self._convert_resolved_buttons(resolved_buttons))
        await self._queue.put({"type": "channels", "assignments": assignments, "replace": True})

    async def merge_assignments(self, assignments: Iterable[LEDChannelAssignment]) -> None:
        await self._queue.put({"type": "channels", "assignments": list(assignments), "replace": False})

    async def run_pattern(self, pattern: str, params: Optional[Dict[str, object]] = None, duration_ms: Optional[int] = None) -> None:
        await self._queue.put(
            {"type": "pattern", "pattern": pattern, "params": params or {}, "duration_ms": duration_ms}
        )

    async def clear_pattern(self) -> None:
        await self._queue.put({"type": "clear_pattern"})

    async def update_brightness(self, level: int) -> None:
        level = max(0, min(100, int(level)))
        await self._queue.put({"type": "brightness", "level": level})

    async def update_voice_amplitude(self, amplitude: float) -> None:
        """Update the real-time voice breathing amplitude."""
        amplitude = max(0.0, min(1.0, float(amplitude)))
        # We use a direct set to avoid queue latency for 10Hz updates
        self._voice_amplitude = amplitude

    async def refresh_devices(self) -> None:
        await self._queue.put({"type": "refresh_devices"})

    async def status(self) -> Dict[str, object]:
        all_devices: List[Dict[str, object]] = []
        hardware_devices: List[Dict[str, object]] = []
        for device in self.registry.all_devices():
            summary = self._device_summary(device)
            all_devices.append(summary)
            if not summary.get("simulation"):
                hardware_devices.append(summary)

        discovery = [
            info.as_dict() if hasattr(info, "as_dict") else info  # type: ignore[union-attr]
            for info in self.registry.discovery_snapshot()
        ]
        events = list(self._event_log)
        last_refresh = self.registry.last_refresh()
        simulation_mode = self.registry.simulation_mode()
        diagnostics = {
            "tick_ms": round(self._last_tick_ms, 4) if self._last_tick_ms else self._loop_interval * 1000.0,
            "running": self._running,
            "mode": "simulation" if simulation_mode else "hardware",
            "connected_devices": [device["device_id"] for device in hardware_devices],
            "last_hid_write": self._last_hid_write,
            "last_error": self._last_error,
            "simulation_mode": simulation_mode,
            "last_refresh": datetime.fromtimestamp(last_refresh).isoformat() if last_refresh else None,
            "discovered_devices": discovery,
        }
        registry_summary = {
            "simulation_mode": simulation_mode,
            "message": "Simulation mode - no LED hardware detected" if simulation_mode else "Hardware devices detected",
            "physical_count": len(hardware_devices),
            "all_devices": all_devices,
            "discovery": discovery,
            "last_refresh": diagnostics["last_refresh"],
        }
        return {
            "brightness": self._global_brightness,
            "active_pattern": self._active_pattern.name if self._active_pattern else None,
            "devices": hardware_devices,
            "registry": registry_summary,
            "log": events,
            "events": events,
            "engine": diagnostics,
        }

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _engine_loop(self) -> None:
        await self.registry.refresh()
        logger.info("LED engine loop started")
        try:
            while self._running:
                loop_started = time.perf_counter()
                await self._drain_queue()
                frames = await self._compose_frames()
                await self._flush_frames(frames)
                await asyncio.sleep(self._loop_interval)
                self._last_tick_ms = (time.perf_counter() - loop_started) * 1000.0
        except asyncio.CancelledError:  # pragma: no cover - defensive
            logger.info("LED engine loop cancelled")
        except Exception as exc:
            logger.error("LED engine crashed: %s", exc, exc_info=True)
        finally:
            self._running = False

    async def _drain_queue(self) -> None:
        while True:
            try:
                command = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            await self._handle_command(command)

    async def _handle_command(self, command: Dict[str, object]) -> None:
        ctype = command.get("type")
        if ctype == "channels":
            assignments: List[LEDChannelAssignment] = command.get("assignments", [])
            replace = command.get("replace", False)
            self._apply_assignments(assignments, replace=bool(replace))
        elif ctype == "pattern":
            self._active_pattern = PatternState(
                name=str(command.get("pattern")),
                params=command.get("params", {}) or {},
                duration_ms=command.get("duration_ms"),
            )
            self._event_log.append(
                {"timestamp": time.time(), "action": "pattern", "pattern": self._active_pattern.name}
            )
        elif ctype == "clear_pattern":
            self._active_pattern = None
            self._event_log.append({"timestamp": time.time(), "action": "pattern_clear"})
        elif ctype == "brightness":
            self._global_brightness = int(command.get("level", self._global_brightness))
            self._event_log.append({"timestamp": time.time(), "action": "brightness", "value": self._global_brightness})
        elif ctype == "refresh_devices":
            await self.registry.refresh()
        else:  # pragma: no cover - defensive
            logger.debug("Unknown LED engine command: %s", command)

    async def _compose_frames(self) -> Dict[str, List[int]]:
        devices = list(self.registry.all_devices())
        if not devices:
            await self.registry.refresh()
            devices = list(self.registry.all_devices())

        frames: Dict[str, List[int]] = {}
        for device in devices:
            base = self._profile_frames.get(device.device_id)
            if base is None:
                base = [0] * device.channel_count
            frames[device.device_id] = list(base[: device.channel_count])

            # Apply Voice Breathing to P1/P2 Start buttons (Ports 1 & 2)
            if self._voice_amplitude > 0 and len(frames[device.device_id]) >= 2:
                v_bright = int(48 * self._voice_amplitude)
                frames[device.device_id][0] = max(frames[device.device_id][0], v_bright)
                frames[device.device_id][1] = max(frames[device.device_id][1], v_bright)

        if self._active_pattern:
            elapsed_ms = (time.monotonic() - self._active_pattern.started_at) * 1000.0
            for device in devices:
                frames[device.device_id] = self._pattern_frame(device, elapsed_ms)
            if self._active_pattern.duration_ms and elapsed_ms >= self._active_pattern.duration_ms:
                self._active_pattern = None

        # Apply global brightness scaling
        scale = self._global_brightness / 100.0
        for device_id, frame in frames.items():
            frames[device_id] = [max(0, min(48, int(value * scale))) for value in frame]
        return frames

    async def _flush_frames(self, frames: Dict[str, List[int]]) -> None:
        had_error = False
        for device in self.registry.all_devices():
            frame = frames.get(device.device_id)
            if frame is None:
                continue
            try:
                await device.set_channels(frame)
                device_last = getattr(device, "last_hid_write", None)
                if device_last:
                    self._last_hid_write = device_last
            except Exception as exc:  # pragma: no cover - defensive
                message = f"{device.device_id}: {exc}"
                self._last_error = message
                self._event_log.append({"timestamp": time.time(), "action": "error", "message": message})
                logger.error("Failed to write LED frame to %s: %s", device.device_id, exc)
                had_error = True
        if not had_error:
            self._last_error = None

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def _apply_assignments(self, assignments: List[LEDChannelAssignment], replace: bool) -> None:
        if not assignments:
            return
        if replace:
            self._profile_frames.clear()
        for assignment in assignments:
            device_id = assignment.device_id or "mock-led-device"
            channel_count = self.registry.channel_count(device_id)
            frame = self._profile_frames.setdefault(device_id, [0] * channel_count)
            index = assignment.channel_index
            if index < 0:
                continue
            if index >= len(frame):
                # Resize frame for controllers with more ports than default
                frame.extend([0] * (index + 1 - len(frame)))
            value = color_to_brightness(assignment.color) if assignment.active else 0
            frame[index] = value
        self._event_log.append(
            {
                "timestamp": time.time(),
                "action": "assignments",
                "count": len(assignments),
                "replace": replace,
            }
        )

    def _pattern_frame(self, device: LEDDevice, time_ms: float) -> List[int]:
        pattern = self._active_pattern
        renderer = PatternRenderer(channel_count=device.channel_count)
        params = pattern.params if pattern else {}
        color = str(params.get("color", "#00E5FF"))
        name = (pattern.name or "solid") if pattern else "solid"
        if name == "pulse":
            return renderer.pulse(color, time_ms)
        if name == "chase":
            return renderer.chase(color, time_ms)
        if name == "rainbow":
            return renderer.rainbow(time_ms)
        if name == "solid":
            return renderer.solid(color)
        logger.debug("Unknown pattern '%s', falling back to solid", name)
        return renderer.solid(color)

    def _convert_resolved_buttons(self, resolved_buttons: Iterable[Dict[str, object]]) -> Iterable[LEDChannelAssignment]:
        assignments: List[LEDChannelAssignment] = []
        for entry in resolved_buttons or []:
            settings = entry.get("settings") or {}
            color = settings.get("color") or entry.get("color")
            if not color:
                continue
            channels = entry.get("channels") or []
            for channel in channels:
                try:
                    port = int(channel.get("channel_index", 0))
                except (TypeError, ValueError):
                    continue
                # LED-Wiz channels are 1-based; convert to zero-based index
                channel_index = max(0, port - 1)
                assignments.append(
                    LEDChannelAssignment(
                        device_id=str(channel.get("device_id") or "mock-led-device"),
                        channel_index=channel_index,
                        color=str(color),
                        logical_button=entry.get("logical_button") or entry.get("key"),
                        active=True,
                    )
                )
        return assignments

    def _device_summary(self, device: LEDDevice) -> Dict[str, object]:
        summary: Dict[str, object] = {
            "device_id": device.device_id,
            "channels": device.channel_count,
            "driver": device.__class__.__name__,
        }
        if hasattr(device, "vendor_id"):
            summary["vendor_id"] = getattr(device, "vendor_id")
            summary["product_id"] = getattr(device, "product_id")
        if hasattr(device, "serial"):
            summary["serial"] = getattr(device, "serial")
        if hasattr(device, "manufacturer"):
            summary["manufacturer"] = getattr(device, "manufacturer")
        if hasattr(device, "product_name"):
            summary["product"] = getattr(device, "product_name")
        summary["simulation"] = bool(getattr(device, "device_id", "") == "mock-led-device")
        return summary

    # ------------------------------------------------------------------
    # Diagnostics helpers
    # ------------------------------------------------------------------

    async def channel_test(self, device_id: Optional[str], channel: int, duration_ms: int = 300) -> Dict[str, object]:
        """Flash a single LED channel for diagnostics."""
        duration_ms = max(50, min(int(duration_ms), 10000))
        if channel < 0:
            raise RuntimeError("channel must be non-negative")
        channel_index = channel

        device = None
        if device_id:
            device = await self.registry.get(device_id)
        if device is None:
            device = await self.registry.get_default()
            device_id = device.device_id

        channel_count = getattr(device, "channel_count", 32)
        if channel_index >= channel_count:
            channel_index = min(channel_count - 1, channel_index)

        frame_on = [0] * channel_count
        frame_on[channel_index] = 48
        frame_off = [0] * channel_count
        simulated = bool(getattr(device, "device_id", "") == "mock-led-device" or self.registry.simulation_mode())
        try:
            await device.set_channels(frame_on)
            await asyncio.sleep(duration_ms / 1000.0)
            await device.set_channels(frame_off)
        except Exception as exc:  # pragma: no cover - defensive
            message = f"{device_id}: {exc}"
            self._last_error = message
            self._event_log.append({"timestamp": time.time(), "action": "channel_test", "status": "error", "message": message})
            logger.error("Channel test failed for %s: %s", device_id, exc)
            raise RuntimeError(message)

        self._event_log.append(
            {
                "timestamp": time.time(),
                "action": "channel_test",
                "device_id": device_id,
                "channel": channel_index,
                "duration_ms": duration_ms,
                "mode": "simulation" if simulated else "hardware",
            }
        )
        return {
            "status": "ok",
            "device_id": device_id,
            "channel": channel_index,
            "duration_ms": duration_ms,
            "mode": "simulation" if simulated else "hardware",
            "simulated": simulated,
        }

    async def health_snapshot(self) -> Dict[str, object]:
        """Return a safe snapshot of engine health."""
        status = await self.status()
        queue_depth = self._queue.qsize()
        diagnostics = status.get("engine", {}).copy()
        diagnostics.update(
            {
                "running": self._running,
                "tick_ms": diagnostics.get("tick_ms"),
                "queue_depth": queue_depth,
                "pending_commands": queue_depth,
                "stuck_commands": queue_depth > 0,
                "active_pattern": status.get("active_pattern"),
                "events": status.get("events", []),
                "simulation_mode": diagnostics.get("simulation_mode"),
            }
        )
        return diagnostics
