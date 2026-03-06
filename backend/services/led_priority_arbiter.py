"""
LED Priority Arbiter — Circuit Breaker for LED State Conflicts.

Solves the real-world problem where multiple subsystems compete for LED control:
  - Game lifecycle wants genre-specific animations (Fighting strobe, Racing chase)
  - Vicky Voice wants her signature Magenta pulse when speaking
  - Attract mode wants slow random cycling when idle

The arbiter enforces a strict priority hierarchy:
  VOICE > GAME > ATTRACT > IDLE

When a higher-priority consumer claims the LEDs, lower-priority animations
are paused. When the higher-priority consumer releases, the previous
animation resumes automatically.

Also includes a scroll throttle to prevent HID buffer overflow when
rapidly browsing games in LaunchBox.

@service: led_priority_arbiter
@owner: Arcade Assistant / LED Blinky
@status: active
"""

from __future__ import annotations

import asyncio
import time
import structlog
from enum import IntEnum
from typing import Optional, Callable, Awaitable

logger = structlog.get_logger(__name__)


class LEDPriority(IntEnum):
    """Priority levels for LED access. Higher value = higher priority."""
    IDLE = 0         # No activity — default front-end animation
    ATTRACT = 10     # Attract mode — slow random cycle
    GAME = 20        # Active game — genre-specific animation
    VOICE = 30       # Vicky speaking — always wins


class LEDPriorityArbiter:
    """
    Singleton arbiter that manages LED ownership across subsystems.

    Usage:
        arbiter = get_led_arbiter()

        # Game starts — claim LEDs at GAME priority
        await arbiter.claim(LEDPriority.GAME, animation_code="3", label="Fighting")

        # Vicky starts speaking — claim LEDs at VOICE priority (overrides GAME)
        await arbiter.claim(LEDPriority.VOICE, animation_code="9", label="Vicky Active")

        # Vicky stops — release VOICE priority (GAME animation resumes)
        await arbiter.release(LEDPriority.VOICE)

        # Game exits — release GAME priority
        await arbiter.release(LEDPriority.GAME)
    """

    # ── Scroll throttle settings ───────────────────────────────────────────
    SCROLL_THROTTLE_MS = 300  # Minimum ms between LED updates during scrolling
    
    def __init__(self):
        self._current_priority: LEDPriority = LEDPriority.IDLE
        self._current_label: str = "idle"
        self._current_animation: Optional[str] = None
        
        # Stacked state — when voice overrides game, game's state is preserved here
        self._stacked: dict[LEDPriority, dict] = {}
        
        # Scroll throttle
        self._last_scroll_fire: float = 0.0
        self._scroll_pending: Optional[asyncio.Task] = None
        
        # Callback to actually fire LEDBlinky — injected to avoid circular imports
        self._fire_callback: Optional[Callable[..., Awaitable]] = None
        
        self._lock = asyncio.Lock()
        
        logger.info("[LEDArbiter] Initialized — priority hierarchy: VOICE > GAME > ATTRACT > IDLE")

    def set_fire_callback(self, callback: Callable[..., Awaitable]):
        """
        Inject the actual LED firing function.

        This avoids circular imports — game_lifecycle.py sets this during init.
        Expected signature: async def callback(animation_code: str, label: str)
        """
        self._fire_callback = callback
        logger.info("[LEDArbiter] Fire callback registered")

    async def claim(
        self,
        priority: LEDPriority,
        animation_code: str,
        label: str = "",
        rom_name: Optional[str] = None,
    ) -> bool:
        """
        Claim LED control at the given priority level.

        If a higher-priority consumer already owns the LEDs, this claim
        is stacked but won't fire. When the higher-priority consumer
        releases, this animation will resume.

        Returns True if the animation was immediately fired.
        """
        async with self._lock:
            # Always store the state for this priority level
            self._stacked[priority] = {
                "animation_code": animation_code,
                "label": label,
                "rom_name": rom_name,
            }

            if priority >= self._current_priority:
                # We win — fire the animation
                self._current_priority = priority
                self._current_label = label
                self._current_animation = animation_code
                
                logger.info(
                    "[LEDArbiter] Claimed",
                    priority=priority.name,
                    animation=animation_code,
                    label=label,
                )
                
                await self._fire(animation_code, rom_name)
                return True
            else:
                # Higher priority active — stash for later
                logger.info(
                    "[LEDArbiter] Stacked (higher priority active)",
                    requested=priority.name,
                    current=self._current_priority.name,
                    label=label,
                )
                return False

    async def release(self, priority: LEDPriority):
        """
        Release LED control at the given priority level.

        If this was the active priority, the next-highest stacked
        animation resumes automatically.
        """
        async with self._lock:
            # Remove from stack
            self._stacked.pop(priority, None)

            if priority != self._current_priority:
                # Not the active owner — just clean up
                logger.info("[LEDArbiter] Released (was not active)", priority=priority.name)
                return

            # Find the next-highest priority in the stack
            if self._stacked:
                next_priority = max(self._stacked.keys())
                next_state = self._stacked[next_priority]
                
                self._current_priority = next_priority
                self._current_label = next_state["label"]
                self._current_animation = next_state["animation_code"]
                
                logger.info(
                    "[LEDArbiter] Released -> resuming",
                    released=priority.name,
                    resuming=next_priority.name,
                    animation=next_state["animation_code"],
                    label=next_state["label"],
                )
                
                await self._fire(next_state["animation_code"], next_state.get("rom_name"))
            else:
                # Nothing in stack — go idle
                self._current_priority = LEDPriority.IDLE
                self._current_label = "idle"
                self._current_animation = None
                logger.info("[LEDArbiter] Released -> idle", released=priority.name)

    async def throttled_claim(
        self,
        priority: LEDPriority,
        animation_code: str,
        label: str = "",
        rom_name: Optional[str] = None,
    ) -> bool:
        """
        Throttled version of claim() for rapid-fire scenarios like LaunchBox scrolling.

        Prevents HID buffer overflow by enforcing a minimum interval between
        LED updates. If called again within the throttle window, the previous
        pending update is cancelled and replaced.
        """
        now = time.monotonic() * 1000  # ms
        elapsed = now - self._last_scroll_fire

        # Cancel any pending throttled fire
        if self._scroll_pending and not self._scroll_pending.done():
            self._scroll_pending.cancel()

        if elapsed >= self.SCROLL_THROTTLE_MS:
            # Enough time passed — fire immediately
            self._last_scroll_fire = now
            return await self.claim(priority, animation_code, label, rom_name)
        else:
            # Too soon — schedule a delayed fire
            delay_s = (self.SCROLL_THROTTLE_MS - elapsed) / 1000.0
            self._scroll_pending = asyncio.create_task(
                self._delayed_claim(delay_s, priority, animation_code, label, rom_name)
            )
            return False

    async def _delayed_claim(
        self,
        delay: float,
        priority: LEDPriority,
        animation_code: str,
        label: str,
        rom_name: Optional[str],
    ):
        """Internal: wait then fire a throttled claim."""
        try:
            await asyncio.sleep(delay)
            self._last_scroll_fire = time.monotonic() * 1000
            await self.claim(priority, animation_code, label, rom_name)
        except asyncio.CancelledError:
            pass  # Replaced by a newer scroll event — expected

    async def _fire(self, animation_code: str, rom_name: Optional[str] = None):
        """Fire the actual LED command via the registered callback."""
        if self._fire_callback:
            try:
                await self._fire_callback(animation_code, rom_name)
            except Exception as e:
                logger.error("[LEDArbiter] Fire callback failed", error=str(e))
        else:
            logger.warning("[LEDArbiter] No fire callback registered — LED command silently dropped")

    @property
    def current_state(self) -> dict:
        """Return current arbiter state for diagnostics."""
        return {
            "priority": self._current_priority.name,
            "animation": self._current_animation,
            "label": self._current_label,
            "stacked": {
                p.name: s["label"] for p, s in self._stacked.items()
            },
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_arbiter: Optional[LEDPriorityArbiter] = None


def get_led_arbiter() -> LEDPriorityArbiter:
    """Get or create the global LED Priority Arbiter singleton."""
    global _arbiter
    if _arbiter is None:
        _arbiter = LEDPriorityArbiter()
    return _arbiter
