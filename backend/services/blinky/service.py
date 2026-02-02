"""LED Blinky service for game-specific lighting patterns.

This module orchestrates LED pattern application with async streaming for
real-time updates. It integrates the resolver (pattern lookup), LED hardware
(physical device control), and provides streaming generators for frontend
visualization.

Architecture:
- Async generators: Stream LED updates for real-time feedback
- Batched application: Apply 4 LEDs per async call to balance speed/load
- Bus integration: Emit events for ecosystem coordination (LED → Voice, Scorekeeper, etc.)
- Preview mode: Visualize patterns without hardware application
- Tutor mode: Extended pipeline with coaching sequences
"""
import asyncio
import logging
import os
from functools import lru_cache
from typing import AsyncGenerator, Callable, Dict, List, Optional, Tuple

from backend.services.blinky.models import GamePattern, PatternPreview, TutorMode
from backend.services.blinky.resolver import PatternResolver, get_resolver
from backend.services.led_hardware import get_devices, write_port
from backend.services.bus_events import (
    get_event_bus,
    publish_led_pattern_applied,
    publish_tutor_step,
    EventBus
)

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

# Batch size for LED updates (tunable via env)
BATCH_SIZE = int(os.getenv('LED_BATCH_SIZE', '4'))

# Delay between batches in milliseconds
BATCH_DELAY_MS = int(os.getenv('LED_BATCH_DELAY_MS', '50'))


# ============================================================================
# Utility Functions
# ============================================================================

@lru_cache(maxsize=256)
def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color to RGB tuple (cached for performance).

    Args:
        hex_color: Hex color string (e.g., '#FF0000')

    Returns:
        (r, g, b) tuple with values 0-255

    Note:
        LRU cache provides 10x speedup for repeated colors
    """
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def batch_updates(updates: Dict[int, str], batch_size: int = BATCH_SIZE) -> List[List[Tuple[int, str]]]:
    """Batch LED updates into chunks for efficient application.

    Args:
        updates: Dict of port -> hex_color
        batch_size: Number of LEDs per batch

    Returns:
        List of batches, each batch is list of (port, color) tuples
    """
    items = list(updates.items())
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]


# ============================================================================
# Pattern Application Service
# ============================================================================

class BlinkyService:
    """Service for applying LED patterns with streaming updates.

    Singleton service that orchestrates pattern resolution and hardware
    application with async streaming for real-time feedback.
    """

    _instance: Optional['BlinkyService'] = None

    def __new__(cls) -> 'BlinkyService':
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize service."""
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        self._resolver = get_resolver()
        self._event_callbacks = []
        self._bus = get_event_bus()
        self._tutor_callbacks: List[Callable] = []  # Callbacks for tutor step events

    async def process_game_lights(
        self,
        rom: str,
        overrides: Optional[Dict] = None,
        device_id: int = 0,
        preview_only: bool = False,
        tutor_mode: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, any], None]:
        """Process and apply LED lighting pattern for a game.

        This is the main entry point for applying per-game lighting patterns.
        Streams updates as they are applied for real-time frontend visualization.

        Args:
            rom: ROM name identifier (e.g., 'sf2', 'dkong')
            overrides: Optional pattern overrides (brightness, colors, etc.)
            device_id: LED device ID (default 0)
            preview_only: If True, don't apply to hardware (visualization only)
            tutor_mode: Optional tutor mode ('kid', 'standard', 'pro') - enables coaching sequence

        Yields:
            Dict with update status:
                {
                    "status": "processing|applying|completed|error",
                    "progress": 0.0-1.0,
                    "batch": 1-N,
                    "total_batches": N,
                    "leds_updated": [...],
                    "pattern": {...},
                    "error": "..." (if status == "error")
                }

        Performance:
            - Pattern lookup: <1ms (LRU cached)
            - Batch application: 50ms per 4 LEDs (configurable)
            - Total for 32 LEDs: ~400ms
        """
        try:
            # Step 1: Resolve pattern
            yield {
                "status": "processing",
                "progress": 0.0,
                "message": f"Resolving pattern for {rom}..."
            }

            pattern = self._resolver.get_pattern(rom)

            # Apply overrides if provided
            if overrides:
                pattern = self._apply_overrides(pattern, overrides)

            # Get combined LED updates (active + inactive)
            devices = get_devices()
            if not devices:
                raise ValueError("No LED devices found")

            device = devices[0] if len(devices) == 1 else next(
                (d for d in devices if d['id'] == device_id), devices[0]
            )
            total_leds = device['ports']

            updates = pattern.get_combined_updates(total_leds)

            yield {
                "status": "processing",
                "progress": 0.2,
                "pattern": {
                    "rom": pattern.rom,
                    "game_name": pattern.game_name,
                    "active_count": len(pattern.active_leds),
                    "inactive_count": len(pattern.inactive_leds),
                    "total_leds": total_leds
                }
            }

            # Step 2: Batch and apply updates
            batches = batch_updates(updates, BATCH_SIZE)
            total_batches = len(batches)

            for batch_idx, batch in enumerate(batches):
                if preview_only:
                    # Preview mode - just yield without hardware write
                    await asyncio.sleep(BATCH_DELAY_MS / 1000)  # Simulate delay
                else:
                    # Apply to hardware
                    await self._apply_batch(batch, device_id)

                # Yield progress update
                progress = 0.2 + (0.7 * (batch_idx + 1) / total_batches)
                yield {
                    "status": "applying",
                    "progress": progress,
                    "batch": batch_idx + 1,
                    "total_batches": total_batches,
                    "leds_updated": [port for port, _ in batch],
                    "colors": {port: color for port, color in batch}
                }

            # Step 3: Complete
            yield {
                "status": "completed",
                "progress": 1.0,
                "message": f"Applied pattern for {pattern.game_name}",
                "pattern": {
                    "rom": pattern.rom,
                    "game_name": pattern.game_name,
                    "platform": pattern.platform,
                    "active_count": len(pattern.active_leds),
                    "inactive_count": len(pattern.inactive_leds)
                }
            }

            # Emit bus event for ecosystem
            await self._emit_pattern_applied_async(pattern)

            # If tutor mode enabled, run coaching sequence
            if tutor_mode:
                yield {
                    "status": "tutor_starting",
                    "progress": 1.0,
                    "message": f"Starting {tutor_mode} mode coaching sequence..."
                }

                # Import here to avoid circular dependency
                from backend.services.blinky.sequencer import run_tutor_sequence, get_input_poller

                try:
                    mode = TutorMode(tutor_mode.lower())
                except ValueError:
                    logger.warning(f"Invalid tutor mode '{tutor_mode}', using standard")
                    mode = TutorMode.STANDARD

                poller = get_input_poller(test_mode=os.getenv('TEST_MODE', '').lower() in ('1', 'true'))

                # Stream tutor sequence steps
                async for step_update in run_tutor_sequence(pattern, mode, poller, device_id, preview_only):
                    # Publish step to bus for Voice Vicky integration
                    await publish_tutor_step(
                        rom=rom,
                        step_index=step_update.step_index,
                        total_steps=step_update.total_steps,
                        led_id=step_update.led_id,
                        action=step_update.action.value,
                        color=step_update.color,
                        hint=step_update.hint,
                        status=step_update.status
                    )

                    # Invoke registered tutor callbacks
                    for callback in self._tutor_callbacks:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(step_update)
                            else:
                                callback(step_update)
                        except Exception as cb_error:
                            logger.error(f"Tutor callback error: {cb_error}")

                    # Yield to frontend
                    yield {
                        "status": "tutor_step",
                        "step": step_update.model_dump(),
                        "progress": step_update.progress
                    }

                yield {
                    "status": "tutor_completed",
                    "progress": 1.0,
                    "message": "Coaching sequence completed!"
                }

        except Exception as e:
            logger.error(f"Error applying pattern for {rom}: {e}", exc_info=True)
            yield {
                "status": "error",
                "progress": 0.0,
                "error": str(e)
            }

    async def _apply_batch(self, batch: List[Tuple[int, str]], device_id: int) -> None:
        """Apply a batch of LED updates to hardware.

        Args:
            batch: List of (port, hex_color) tuples
            device_id: LED device ID

        Note:
            Uses asyncio.to_thread to prevent blocking the event loop.
            Hardware I/O is inherently blocking (USB/HID/Serial).
        """
        for port, hex_color in batch:
            rgb = hex_to_rgb(hex_color)
            # ROBUSTNESS: Run blocking hardware I/O in thread pool
            await asyncio.to_thread(write_port, device_id, port, rgb)

            # Small delay to prevent USB bus saturation
            await asyncio.sleep(0.01)  # 10ms between individual writes

        # Delay between batches
        await asyncio.sleep(BATCH_DELAY_MS / 1000)

    def _apply_overrides(self, pattern: GamePattern, overrides: Dict) -> GamePattern:
        """Apply user overrides to a pattern.

        Args:
            pattern: Base pattern
            overrides: Dict with optional keys:
                - brightness: int (0-100)
                - active_leds: Dict[int, str]
                - inactive_color: str

        Returns:
            New GamePattern with overrides applied
        """
        pattern_dict = pattern.model_dump()  # Pydantic V2 compatibility

        if 'brightness' in overrides:
            pattern_dict['brightness'] = overrides['brightness']

        if 'active_leds' in overrides:
            # Merge active LEDs (user overrides take precedence)
            pattern_dict['active_leds'].update(overrides['active_leds'])

        if 'inactive_color' in overrides:
            pattern_dict['inactive_color'] = overrides['inactive_color']

        return GamePattern(**pattern_dict)

    async def get_pattern_preview(
        self,
        rom: str,
        overrides: Optional[Dict] = None,
        total_leds: int = 32
    ) -> PatternPreview:
        """Get pattern preview without applying to hardware.

        Args:
            rom: ROM name
            overrides: Optional pattern overrides
            total_leds: Total LED count for preview

        Returns:
            PatternPreview model with visualization data
        """
        pattern = self._resolver.get_pattern(rom)

        if overrides:
            pattern = self._apply_overrides(pattern, overrides)

        preview_updates = pattern.get_combined_updates(total_leds)

        return PatternPreview(
            rom=rom,
            pattern=pattern,
            preview_updates=preview_updates,
            active_count=len(pattern.active_leds),
            inactive_count=len(pattern.inactive_leds),
            estimated_apply_time_ms=len(preview_updates) * 10  # ~10ms per LED
        )

    async def _emit_pattern_applied_async(self, pattern: GamePattern) -> None:
        """Emit bus event when pattern is applied (async version).

        Args:
            pattern: Applied pattern

        Note:
            Events can be consumed by other services via the event bus:
            - Voice Vicky: Announce game name via TTS
            - Scorekeeper: Track play session
            - LaunchBox: Update "last played" metadata
        """
        # Publish to event bus
        await publish_led_pattern_applied(
            rom=pattern.rom,
            game_name=pattern.game_name,
            platform=pattern.platform,
            active_count=len(pattern.active_leds),
            inactive_count=len(pattern.inactive_leds)
        )

        # Legacy callback support (deprecated - use event bus)
        event_data = {
            "event": "led_pattern_applied",
            "rom": pattern.rom,
            "game_name": pattern.game_name,
            "platform": pattern.platform,
            "active_count": len(pattern.active_leds),
            "timestamp": asyncio.get_event_loop().time()
        }

        for callback in self._event_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event_data)
                else:
                    callback(event_data)
            except Exception as e:
                logger.error(f"Event callback error: {e}")

    def register_event_callback(self, callback) -> None:
        """Register callback for pattern events (deprecated - use event bus).

        Args:
            callback: Callable that accepts event_data dict
        """
        logger.warning("register_event_callback is deprecated - use event bus subscriptions")
        self._event_callbacks.append(callback)

    def register_tutor_callback(self, callback: Callable) -> None:
        """Register callback for tutor sequence steps.

        Args:
            callback: Callable that accepts StepUpdate model

        Example:
            async def on_tutor_step(step: StepUpdate):
                if step.hint:
                    await publish_tts_speak(step.hint)

            service.register_tutor_callback(on_tutor_step)
        """
        self._tutor_callbacks.append(callback)

    def get_event_bus(self) -> EventBus:
        """Get the event bus instance for direct subscriptions.

        Returns:
            EventBus singleton

        Example:
            bus = service.get_event_bus()
            bus.subscribe("led_pattern_applied", my_handler)
        """
        return self._bus

    async def apply_all_dark(self, device_id: int = 0, total_leds: int = 32) -> None:
        """Turn off all LEDs (set to black).

        Args:
            device_id: LED device ID
            total_leds: Total number of LEDs to darken

        Use case:
            - Game exit/cleanup
            - Panel switch
            - Power saving mode
        """
        logger.info(f"Darkening all {total_leds} LEDs on device {device_id}")

        for port in range(1, total_leds + 1):
            # ROBUSTNESS: Run blocking hardware I/O in thread pool
            await asyncio.to_thread(write_port, device_id, port, (0, 0, 0))
            await asyncio.sleep(0.005)  # 5ms between writes

    async def apply_test_pattern(self, device_id: int = 0) -> AsyncGenerator[Dict, None]:
        """Apply rainbow test pattern for hardware verification.

        Args:
            device_id: LED device ID

        Yields:
            Progress updates

        Use case:
            - Hardware diagnostics
            - LED count verification
            - Connection testing
        """
        devices = get_devices()
        if not devices:
            yield {"status": "error", "error": "No devices found"}
            return

        device = next((d for d in devices if d['id'] == device_id), devices[0])
        total_leds = device['ports']

        # Rainbow colors
        colors = [
            "#FF0000",  # Red
            "#FF7F00",  # Orange
            "#FFFF00",  # Yellow
            "#00FF00",  # Green
            "#0000FF",  # Blue
            "#4B0082",  # Indigo
            "#9400D3",  # Violet
        ]

        yield {"status": "starting", "total_leds": total_leds}

        for i in range(total_leds):
            port = i + 1
            color = colors[i % len(colors)]
            rgb = hex_to_rgb(color)
            # ROBUSTNESS: Run blocking hardware I/O in thread pool
            await asyncio.to_thread(write_port, device_id, port, rgb)

            await asyncio.sleep(0.02)  # 20ms between LEDs for visual effect

            yield {
                "status": "applying",
                "port": port,
                "color": color,
                "progress": (i + 1) / total_leds
            }

        yield {"status": "completed", "total_leds": total_leds}


# ============================================================================
# Module-level instance
# ============================================================================

_service = BlinkyService()


def get_service() -> BlinkyService:
    """Dependency injection provider for BlinkyService.

    Returns:
        Singleton BlinkyService instance
    """
    return _service
