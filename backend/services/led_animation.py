"""LED animation engine with async execution and audio reactivity."""
import asyncio
import math
import uuid
import logging
from pathlib import Path
from typing import Dict, List, Optional, Callable
from backend.services.led_config import config_service
from backend.services.led_hardware import led_service

try:
    from pydub import AudioSegment
except ImportError:
    AudioSegment = None

logger = logging.getLogger(__name__)


class LEDAnimationEngine:
    """Singleton animation engine with async task management."""

    _instance = None

    def __new__(cls):
        """Enforce singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize animation engine."""
        if self._initialized:
            return
        self._initialized = True
        self.tasks: Dict[str, asyncio.Task] = {}
        self._event_callbacks: Dict[str, List[Callable]] = {
            "led_animation_started": [],
            "led_animation_stopped": []
        }

    async def pulse(self, config: Dict, duration: float = 2.0) -> None:
        """Smooth brightness pulse animation using sine wave.

        Args:
            config: LED configuration dict with colors and brightness
            duration: Time for one complete pulse cycle
        """
        device_id = config.get('device_id', 0)
        base_color = self._parse_color(config.get('colors', {}).get('primary', '#00FF00'))
        brightness = config.get('brightness', 100) / 100.0
        steps = 60  # 60 FPS smooth animation

        try:
            while True:
                for i in range(steps):
                    factor = (1 + math.sin(2 * math.pi * i / steps)) / 2
                    rgb = tuple(int(c * factor * brightness) for c in base_color)
                    for port in range(1, 33):
                        led_service.write_port(device_id, port, rgb)
                    await asyncio.sleep(duration / steps)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Pulse animation error: {e}")

    async def fade_in_out(self, config: Dict, duration: float = 3.0) -> None:
        """Single fade in and out cycle.

        Args:
            config: LED configuration dict
            duration: Total time for fade in + fade out
        """
        device_id = config.get('device_id', 0)
        base_color = self._parse_color(config.get('colors', {}).get('primary', '#00FF00'))
        brightness = config.get('brightness', 100) / 100.0
        steps = 30

        try:
            # Fade in
            for i in range(steps):
                factor = i / steps * brightness
                rgb = tuple(int(c * factor) for c in base_color)
                for port in range(1, 33):
                    led_service.write_port(device_id, port, rgb)
                await asyncio.sleep(duration / (2 * steps))

            # Fade out
            for i in range(steps, 0, -1):
                factor = i / steps * brightness
                rgb = tuple(int(c * factor) for c in base_color)
                for port in range(1, 33):
                    led_service.write_port(device_id, port, rgb)
                await asyncio.sleep(duration / (2 * steps))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Fade animation error: {e}")

    async def chase(self, config: Dict, speed: float = 0.1) -> None:
        """Light one port at a time in sequence.

        Args:
            config: LED configuration dict
            speed: Delay between port changes
        """
        device_id = config.get('device_id', 0)
        color = self._parse_color(config.get('colors', {}).get('primary', '#00FF00'))
        brightness = config.get('brightness', 100) / 100.0
        rgb = tuple(int(c * brightness) for c in color)
        off = (0, 0, 0)

        try:
            while True:
                for port in range(1, 33):
                    # Turn off previous, turn on current
                    if port > 1:
                        led_service.write_port(device_id, port - 1, off)
                    elif port == 1:
                        led_service.write_port(device_id, 32, off)
                    led_service.write_port(device_id, port, rgb)
                    await asyncio.sleep(speed)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Chase animation error: {e}")

    async def solid(self, config: Dict) -> None:
        """Set all ports to solid color and hold.

        Args:
            config: LED configuration dict
        """
        device_id = config.get('device_id', 0)
        color = self._parse_color(config.get('colors', {}).get('primary', '#00FF00'))
        brightness = config.get('brightness', 100) / 100.0
        rgb = tuple(int(c * brightness) for c in color)

        try:
            for port in range(1, 33):
                led_service.write_port(device_id, port, rgb)
            # Keep running until cancelled
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Solid animation error: {e}")

    async def audio_reactive(self, audio_path: str, config: Dict) -> None:
        """React to audio intensity with brightness changes.

        Args:
            audio_path: Path to audio file
            config: LED configuration dict
        """
        if not AudioSegment:
            logger.error("pydub not installed - audio reactive mode unavailable")
            return

        device_id = config.get('device_id', 0)
        color = self._parse_color(config.get('colors', {}).get('primary', '#00FF00'))

        try:
            audio = AudioSegment.from_file(audio_path)
            chunk_size = 100  # 100ms chunks

            for i in range(0, len(audio), chunk_size):
                chunk = audio[i:i + chunk_size]
                rms = chunk.rms if hasattr(chunk, 'rms') else 5000
                brightness = min(255, int((rms / 10000) * 255))
                rgb = tuple(int(c * brightness / 255) for c in color)

                for port in range(1, 33):
                    led_service.write_port(device_id, port, rgb)

                await asyncio.sleep(chunk_size / 1000)
        except FileNotFoundError:
            logger.error(f"Audio file not found: {audio_path}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Audio reactive error: {e}")

    def start_animation(self, name: str, game: str, device_id: str, user_id: Optional[str] = None) -> str:
        """Start an animation task.

        Args:
            name: Animation name (pulse, chase, solid, fade_in_out, audio_reactive)
            game: Game identifier for config lookup
            device_id: LED device ID
            user_id: Optional user ID for personalized config

        Returns:
            Task ID string
        """
        # Cancel existing animation for same game
        for tid, task in list(self.tasks.items()):
            if hasattr(task, 'game') and task.game == game:
                task.cancel()
                del self.tasks[tid]

        # Get configuration
        config = config_service.get_config(device_id, game, user_id)
        config['device_id'] = int(device_id)

        # Create animation coroutine
        if name == 'pulse':
            coro = self.pulse(config)
        elif name == 'fade_in_out':
            coro = self.fade_in_out(config)
        elif name == 'chase':
            coro = self.chase(config)
        elif name == 'solid':
            coro = self.solid(config)
        elif name.startswith('audio:'):
            audio_path = name.split(':', 1)[1]
            coro = self.audio_reactive(audio_path, config)
        else:
            logger.error(f"Unknown animation: {name}")
            return ""

        # Create and store task
        task_id = str(uuid.uuid4())
        task = asyncio.create_task(coro)
        task.game = game  # Attach metadata
        self.tasks[task_id] = task

        # Emit event
        self._emit("led_animation_started", {"name": name, "game": game, "task_id": task_id})
        return task_id

    def stop_animation(self, task_id: str) -> bool:
        """Stop a specific animation task."""
        if task_id in self.tasks:
            self.tasks[task_id].cancel()
            del self.tasks[task_id]
            self._emit("led_animation_stopped", {"task_id": task_id})
            return True
        return False

    def stop_all(self) -> int:
        """Stop all running animations."""
        count = len(self.tasks)
        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()
        return count

    def _parse_color(self, hex_color: str) -> tuple:
        """Parse hex color to RGB tuple."""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def _emit(self, event: str, data: Dict) -> None:
        """Emit event to registered callbacks."""
        for callback in self._event_callbacks.get(event, []):
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Callback error: {e}")


# Module-level singleton
animation_engine = LEDAnimationEngine()