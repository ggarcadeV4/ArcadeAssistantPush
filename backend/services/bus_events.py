"""Event bus for inter-service communication across the Arcade Assistant ecosystem.

This module provides a pub/sub event bus that enables decoupled communication between
services like LED Blinky, Gunner, ScoreKeeper, Voice Vicky, and others.

Architecture:
- Singleton pattern: Single event bus instance across the application
- Async callbacks: Non-blocking event processing
- Type-safe events: Pydantic models for event payloads
- Weak references: Prevents memory leaks from callback registration

Usage:
    # Subscribe to events
    bus = get_event_bus()

    def on_led_pattern_applied(event: LEDPatternAppliedEvent):
        print(f"Pattern applied for {event.rom}")

    bus.subscribe("led_pattern_applied", on_led_pattern_applied)

    # Publish events
    await bus.publish("led_pattern_applied", LEDPatternAppliedEvent(rom="sf2"))

    # Unsubscribe
    bus.unsubscribe("led_pattern_applied", on_led_pattern_applied)
"""
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, TypedDict
from collections import deque
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================================
# Event Types (Extensible)
# ============================================================================

class EventType(str, Enum):
    """Standard event types across the Arcade Assistant ecosystem."""
    # LED Blinky events
    LED_PATTERN_APPLIED = "led_pattern_applied"
    LED_PATTERN_PREVIEW = "led_pattern_preview"
    LED_TUTOR_STEP = "led_tutor_step"
    LED_DEVICE_CONNECTED = "led_device_connected"
    LED_DEVICE_DISCONNECTED = "led_device_disconnected"

    # Gunner events
    GUNNER_CALIBRATION_START = "gunner_calibration_start"
    GUNNER_CALIBRATION_POINT = "gunner_calibration_point"
    GUNNER_CALIBRATION_COMPLETE = "gunner_calibration_complete"
    GUNNER_TARGET_HIT = "gunner_target_hit"
    GUNNER_TARGET_MISS = "gunner_target_miss"

    # LaunchBox events
    GAME_LAUNCHED = "game_launched"
    GAME_EXITED = "game_exited"
    GAME_SELECTED = "game_selected"

    # Controller events
    CONTROLLER_CONNECTED = "controller_connected"
    CONTROLLER_DISCONNECTED = "controller_disconnected"
    CONTROLLER_REMAPPED = "controller_remapped"

    # ScoreKeeper events
    SCORE_SUBMITTED = "score_submitted"
    TOURNAMENT_STARTED = "tournament_started"
    TOURNAMENT_COMPLETED = "tournament_completed"

    # Voice Vicky events
    VOICE_COMMAND = "voice_command"
    TTS_SPEAK = "tts_speak"
    WAKE_WORD_DETECTED = "wake_word_detected"

    # System events
    SYSTEM_ERROR = "system_error"
    SYSTEM_WARNING = "system_warning"
    STATE_UPDATED = "state_updated"


# ============================================================================
# Event Models (Pydantic for type safety)
# ============================================================================

class BaseEvent(BaseModel):
    """Base event model with common fields."""
    timestamp: datetime = Field(default_factory=datetime.now)
    source: Optional[str] = Field(None, description="Service that emitted the event")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context")


class LEDPatternAppliedEvent(BaseEvent):
    """Event emitted when an LED pattern is applied to hardware."""
    rom: str
    game_name: Optional[str] = None
    platform: Optional[str] = None
    active_count: int = 0
    inactive_count: int = 0


class LEDTutorStepEvent(BaseEvent):
    """Event emitted for each step in a tutor sequence."""
    rom: str
    step_index: int
    total_steps: int
    led_id: int
    action: str
    color: str
    hint: Optional[str] = None
    status: str  # "executing", "completed", "retry", "skipped"


class GunnerCalibrationPointEvent(BaseEvent):
    """Event emitted when a calibration point is hit."""
    point_index: int
    total_points: int
    x: float
    y: float
    accuracy: Optional[float] = None
    gun_id: int = 0


class GameLaunchedEvent(BaseEvent):
    """Event emitted when a game is launched."""
    rom: str
    game_name: str
    platform: str
    emulator: Optional[str] = None


class TTSSpeakEvent(BaseEvent):
    """Event requesting text-to-speech output."""
    text: str
    voice_id: Optional[str] = None
    priority: int = 0  # 0=normal, 1=high (interrupts)


class ScoreSubmittedEvent(BaseEvent):
    """Event emitted when a score is submitted."""
    game_name: str
    player_name: str
    score: int
    rank: Optional[int] = None


class StateEvent(TypedDict, total=False):
    """Typed payload for cross-panel state sync."""
    user_id: str
    profile: Dict[str, Any]
    source: str
    priority: str
    timestamp: str


# ============================================================================
# Event Bus Implementation
# ============================================================================

class EventBus:
    """Central event bus for pub/sub messaging across services.

    Singleton service that manages event subscriptions and dispatching.
    Uses regular sets for subscribers (weak refs not compatible with functions).
    """

    _instance: Optional['EventBus'] = None

    def __new__(cls) -> 'EventBus':
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._subscribers: Dict[str, set] = {}
            cls._instance._initialized = False
            # Use deque for O(1) operations on event history
            cls._instance._event_history: deque = deque(maxlen=100)
        return cls._instance

    def __init__(self):
        """Initialize event bus (called once due to singleton)."""
        if self._initialized:
            return
        self._initialized = True
        logger.info("Event bus initialized")

    def subscribe(self, event_type: str, callback: Callable) -> None:
        """Subscribe to an event type.

        Args:
            event_type: Event type to subscribe to (e.g., "led_pattern_applied")
            callback: Callable to invoke when event is published.
                     Can be sync or async function.

        Example:
            def on_pattern_applied(event: LEDPatternAppliedEvent):
                print(f"Pattern applied: {event.rom}")

            bus.subscribe("led_pattern_applied", on_pattern_applied)
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = set()

        self._subscribers[event_type].add(callback)
        logger.debug(f"Subscribed to {event_type}: {callback.__name__}")

    def unsubscribe(self, event_type: str, callback: Callable) -> bool:
        """Unsubscribe from an event type.

        Args:
            event_type: Event type to unsubscribe from
            callback: Callback function to remove

        Returns:
            True if callback was removed, False if not found
        """
        if event_type not in self._subscribers:
            return False

        if callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)
            logger.debug(f"Unsubscribed from {event_type}: {callback.__name__}")
            return True
        return False

    async def publish(
        self,
        event_type: str,
        event_data: Optional[BaseEvent] = None,
        **kwargs
    ) -> int:
        """Publish an event to all subscribers.

        Args:
            event_type: Event type identifier
            event_data: Optional Pydantic event model
            **kwargs: If event_data not provided, construct from kwargs

        Returns:
            Number of callbacks invoked

        Note:
            Callbacks are invoked concurrently using asyncio.gather.
            Exceptions in callbacks are logged but don't block other callbacks.

        Example:
            # With Pydantic model
            event = LEDPatternAppliedEvent(rom="sf2", game_name="Street Fighter 2")
            await bus.publish("led_pattern_applied", event)

            # With kwargs
            await bus.publish("led_pattern_applied", rom="sf2", game_name="Street Fighter 2")
        """
        if event_type not in self._subscribers or not self._subscribers[event_type]:
            logger.debug(f"No subscribers for {event_type}")
            return 0

        # Build event data
        if event_data is None and kwargs:
            event_data = kwargs
        elif event_data:
            # Convert Pydantic model to dict for callback simplicity
            event_data = event_data.model_dump() if hasattr(event_data, 'model_dump') else event_data

        # Record in history
        self._add_to_history(event_type, event_data)

        # Invoke callbacks concurrently
        callbacks = list(self._subscribers[event_type])
        tasks = []

        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    tasks.append(self._invoke_async_callback(callback, event_type, event_data))
                else:
                    tasks.append(self._invoke_sync_callback(callback, event_type, event_data))
            except Exception as e:
                logger.error(f"Error preparing callback {callback.__name__} for {event_type}: {e}")

        # Wait for all callbacks
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.debug(f"Published {event_type} to {len(callbacks)} subscribers")
        return len(callbacks)

    async def _invoke_async_callback(self, callback: Callable, event_type: str, event_data: Any) -> None:
        """Invoke async callback with error handling."""
        try:
            await callback(event_data)
        except Exception as e:
            logger.error(f"Error in async callback {callback.__name__} for {event_type}: {e}", exc_info=True)

    async def _invoke_sync_callback(self, callback: Callable, event_type: str, event_data: Any) -> None:
        """Invoke sync callback in executor with error handling."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, callback, event_data)
        except Exception as e:
            logger.error(f"Error in sync callback {callback.__name__} for {event_type}: {e}", exc_info=True)

    def _add_to_history(self, event_type: str, event_data: Any) -> None:
        """Add event to ring buffer history (O(1) operation with deque)."""
        self._event_history.append((datetime.now(), event_type, event_data))
        # deque with maxlen automatically evicts oldest entries

    def get_recent_events(self, limit: int = 10, event_type: Optional[str] = None) -> List[tuple]:
        """Get recent event history.

        Args:
            limit: Maximum number of events to return
            event_type: Optional filter by event type

        Returns:
            List of (timestamp, event_type, event_data) tuples
        """
        history = list(self._event_history)  # Convert deque to list for slicing

        if event_type:
            history = [e for e in history if e[1] == event_type]

        return history[-limit:]

    def get_subscriber_count(self, event_type: Optional[str] = None) -> int:
        """Get count of subscribers.

        Args:
            event_type: Optional specific event type, or None for total

        Returns:
            Number of subscribers
        """
        if event_type:
            return len(self._subscribers.get(event_type, set()))
        return sum(len(subs) for subs in self._subscribers.values())

    def clear_all_subscribers(self) -> None:
        """Clear all subscriptions (useful for testing)."""
        self._subscribers.clear()
        logger.info("All event subscriptions cleared")


# ============================================================================
# Dependency Injection
# ============================================================================

_bus = EventBus()


def get_event_bus() -> EventBus:
    """Get the singleton event bus instance.

    Returns:
        Singleton EventBus instance

    Usage in FastAPI:
        from fastapi import Depends

        @router.post("/apply-pattern")
        async def apply_pattern(bus: EventBus = Depends(get_event_bus)):
            await bus.publish("led_pattern_applied", rom="sf2")
    """
    return _bus


# ============================================================================
# Helper Functions
# ============================================================================

async def publish_led_pattern_applied(
    rom: str,
    game_name: Optional[str] = None,
    platform: Optional[str] = None,
    active_count: int = 0,
    inactive_count: int = 0
) -> None:
    """Convenience function to publish LED pattern applied event.

    Args:
        rom: ROM identifier
        game_name: Game name
        platform: Platform name
        active_count: Number of active LEDs
        inactive_count: Number of inactive LEDs
    """
    bus = get_event_bus()
    event = LEDPatternAppliedEvent(
        rom=rom,
        game_name=game_name,
        platform=platform,
        active_count=active_count,
        inactive_count=inactive_count,
        source="led_blinky"
    )
    await bus.publish(EventType.LED_PATTERN_APPLIED, event)


async def publish_tts_speak(text: str, voice_id: Optional[str] = None, priority: int = 0) -> None:
    """Convenience function to request TTS output.

    Args:
        text: Text to speak
        voice_id: Optional voice ID
        priority: 0=normal, 1=high (interrupts current speech)
    """
    bus = get_event_bus()
    event = TTSSpeakEvent(
        text=text,
        voice_id=voice_id,
        priority=priority,
        source="system"
    )
    await bus.publish(EventType.TTS_SPEAK, event)


def log_state_event(user_id: str, action: str) -> None:
    logger.info("state_event", extra={"user_id": user_id, "action": action})


async def publish_state_update(event: StateEvent) -> None:
    """Emit typed state update events consumed by Dewey liaison."""
    bus = get_event_bus()
    event.setdefault("timestamp", datetime.utcnow().isoformat())
    event.setdefault("source", "unknown")
    event.setdefault("priority", "medium")
    log_state_event(event["user_id"], "publish_state_update")
    await bus.publish(EventType.STATE_UPDATED, event)


async def publish_tutor_step(
    rom: str,
    step_index: int,
    total_steps: int,
    led_id: int,
    action: str,
    color: str,
    hint: Optional[str] = None,
    status: str = "executing"
) -> None:
    """Convenience function to publish tutor step event.

    Args:
        rom: ROM identifier
        step_index: Current step index
        total_steps: Total steps in sequence
        led_id: LED port being highlighted
        action: Action type (pulse, hold, fade)
        color: Hex color
        hint: Optional hint text
        status: Step status
    """
    bus = get_event_bus()
    event = LEDTutorStepEvent(
        rom=rom,
        step_index=step_index,
        total_steps=total_steps,
        led_id=led_id,
        action=action,
        color=color,
        hint=hint,
        status=status,
        source="led_blinky_tutor"
    )
    await bus.publish(EventType.LED_TUTOR_STEP, event)
