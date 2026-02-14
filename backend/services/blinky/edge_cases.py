"""Edge case handlers for LED Blinky service.

This module provides robust error handling and recovery for common edge cases:
- Unknown ROM patterns (intelligent fallback)
- Mismatched button counts (hardware vs config)
- Hardware disconnection mid-apply
- Spam protection (rate limiting, debounce)
- Offline Supabase fallback
- Concurrent request handling

Design Philosophy:
- Fail gracefully with sensible defaults
- Log all edge cases for debugging
- Provide user-friendly error messages
- Never crash the service
"""
import asyncio
import logging
import time
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple
from functools import wraps

from backend.services.blinky.models import GamePattern

logger = logging.getLogger(__name__)


# ============================================================================
# Rate Limiting & Spam Protection
# ============================================================================

class RateLimiter:
    """Token bucket rate limiter for spam protection.

    Prevents excessive LED pattern changes that could:
    - Overwhelm USB bus
    - Cause flickering/epilepsy risk
    - Degrade user experience
    """

    def __init__(self, max_requests: int = 10, window_seconds: float = 1.0):
        """Initialize rate limiter.

        Args:
            max_requests: Max requests allowed in window
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window = window_seconds
        self._timestamps: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_requests))

    def check_rate_limit(self, identifier: str) -> Tuple[bool, Optional[float]]:
        """Check if request is within rate limit.

        Args:
            identifier: Unique identifier (e.g., ROM name, device ID)

        Returns:
            (allowed, retry_after_seconds) tuple
        """
        now = time.time()
        timestamps = self._timestamps[identifier]

        # Remove timestamps outside the window
        while timestamps and now - timestamps[0] > self.window:
            timestamps.popleft()

        # Check if limit exceeded
        if len(timestamps) >= self.max_requests:
            oldest = timestamps[0]
            retry_after = self.window - (now - oldest)
            logger.warning(
                f"Rate limit exceeded for {identifier}: "
                f"{len(timestamps)}/{self.max_requests} requests in {self.window}s"
            )
            return False, retry_after

        # Add current timestamp
        timestamps.append(now)
        return True, None

    def reset(self, identifier: Optional[str] = None):
        """Reset rate limit for identifier or all.

        Args:
            identifier: Optional specific identifier, or None for all
        """
        if identifier:
            if identifier in self._timestamps:
                del self._timestamps[identifier]
        else:
            self._timestamps.clear()


# Global rate limiter (10 pattern changes per second max)
_rate_limiter = RateLimiter(max_requests=10, window_seconds=1.0)


def rate_limit(identifier_func=lambda *args, **kwargs: "global"):
    """Decorator for rate-limiting async functions.

    Args:
        identifier_func: Function to extract identifier from args/kwargs

    Example:
        @rate_limit(identifier_func=lambda rom, *args, **kwargs: rom)
        async def apply_pattern(rom: str):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            identifier = identifier_func(*args, **kwargs)
            allowed, retry_after = _rate_limiter.check_rate_limit(identifier)

            if not allowed:
                raise ValueError(
                    f"Rate limit exceeded for {identifier}. "
                    f"Retry after {retry_after:.1f} seconds"
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================================
# Unknown ROM Fallback
# ============================================================================

def get_fallback_pattern(rom: str, hardware_button_count: int = 8) -> GamePattern:
    """Get intelligent fallback pattern for unknown ROMs.

    Uses heuristics based on ROM name and hardware configuration.

    Args:
        rom: ROM identifier
        hardware_button_count: Number of physical buttons available

    Returns:
        Fallback GamePattern with sensible defaults
    """
    rom_lower = rom.lower()

    # Heuristic: fighting game keywords -> 6 buttons
    if any(kw in rom_lower for kw in ['vs', 'fight', 'combat', 'battle', 'punch', 'kick']):
        return GamePattern(
            rom=rom,
            game_name=f"Unknown Fighting Game ({rom})",
            platform="Unknown",
            active_leds={
                1: "#FF0000", 2: "#00FF00", 3: "#0000FF",
                4: "#FFFF00", 5: "#FF00FF", 6: "#00FFFF"
            },
            inactive_leds=[7, 8] if hardware_button_count >= 8 else [],
            control_count=6
        )

    # Heuristic: platformer keywords -> 2 buttons (jump + action)
    elif any(kw in rom_lower for kw in ['jump', 'run', 'platform', 'climb']):
        return GamePattern(
            rom=rom,
            game_name=f"Unknown Platformer ({rom})",
            platform="Unknown",
            active_leds={1: "#FF0000", 2: "#00FF00"},  # Red jump, green action
            inactive_leds=list(range(3, hardware_button_count + 1)),
            control_count=2
        )

    # Heuristic: shooter keywords -> 2 buttons (fire + bomb)
    elif any(kw in rom_lower for kw in ['shoot', 'gun', 'space', 'invader', 'galaga']):
        return GamePattern(
            rom=rom,
            game_name=f"Unknown Shooter ({rom})",
            platform="Unknown",
            active_leds={1: "#FF0000", 2: "#FFFF00"},  # Red fire, yellow bomb
            inactive_leds=list(range(3, hardware_button_count + 1)),
            control_count=2
        )

    # Default: single white button (safe universal fallback)
    logger.info(f"No heuristic match for ROM '{rom}' - using single button fallback")
    return GamePattern(
        rom=rom,
        game_name=f"Unknown Game ({rom})",
        platform="Unknown",
        active_leds={1: "#FFFFFF"},  # White
        inactive_leds=list(range(2, hardware_button_count + 1)),
        control_count=1
    )


# ============================================================================
# Button Count Mismatch Handler
# ============================================================================

def adapt_pattern_to_hardware(
    pattern: GamePattern,
    hardware_button_count: int
) -> GamePattern:
    """Adapt pattern to match available hardware buttons.

    Handles cases where game requires more buttons than hardware has, or
    where hardware has more buttons than game uses.

    Args:
        pattern: Original pattern
        hardware_button_count: Actual hardware button count

    Returns:
        Adapted GamePattern

    Strategy:
        - Too many active buttons: Prorate to fit (keep most important)
        - Too few active buttons: Fill remaining with inactive (dark)
    """
    active_count = len(pattern.active_leds)

    if active_count > hardware_button_count:
        # Prorate: Keep first N buttons (most important controls usually mapped first)
        logger.warning(
            f"Pattern {pattern.rom} requires {active_count} buttons but hardware has "
            f"{hardware_button_count}. Prorating to fit."
        )

        # Sort by LED ID and keep first N
        sorted_active = sorted(pattern.active_leds.items())
        kept_active = dict(sorted_active[:hardware_button_count])

        return GamePattern(
            rom=pattern.rom,
            game_name=pattern.game_name,
            platform=pattern.platform,
            active_leds=kept_active,
            inactive_leds=[],  # All others implicitly dark
            control_count=hardware_button_count,
            brightness=pattern.brightness
        )

    elif active_count < hardware_button_count:
        # Extend: Mark remaining buttons as inactive
        all_leds = set(range(1, hardware_button_count + 1))
        used_leds = set(pattern.active_leds.keys()) | set(pattern.inactive_leds)
        unused_leds = list(all_leds - used_leds)

        return GamePattern(
            rom=pattern.rom,
            game_name=pattern.game_name,
            platform=pattern.platform,
            active_leds=pattern.active_leds,
            inactive_leds=pattern.inactive_leds + unused_leds,
            control_count=pattern.control_count,
            brightness=pattern.brightness
        )

    # Perfect match
    return pattern


# ============================================================================
# Hardware Disconnection Handler
# ============================================================================

class DeviceHealthChecker:
    """Monitors LED device health and handles disconnections."""

    def __init__(self, check_interval: float = 1.0):
        """Initialize health checker.

        Args:
            check_interval: How often to check device health (seconds)
        """
        self.check_interval = check_interval
        self._last_check = 0.0
        self._device_healthy = True

    async def check_device(self, device_id: int) -> bool:
        """Check if LED device is healthy and responsive.

        Args:
            device_id: Device ID to check

        Returns:
            True if healthy, False if disconnected/unresponsive
        """
        now = time.time()

        # Throttle checks to avoid overhead
        if now - self._last_check < self.check_interval:
            return self._device_healthy

        self._last_check = now

        try:
            # Import here to avoid circular dependency
            from backend.services.led_hardware import get_devices

            devices = get_devices()
            device_healthy = any(d['id'] == device_id for d in devices)

            if not device_healthy and self._device_healthy:
                logger.error(f"LED device {device_id} disconnected!")
            elif device_healthy and not self._device_healthy:
                logger.info(f"LED device {device_id} reconnected")

            self._device_healthy = device_healthy
            return device_healthy

        except Exception as e:
            logger.error(f"Error checking device health: {e}")
            self._device_healthy = False
            return False


_health_checker = DeviceHealthChecker()


async def safe_hardware_write(device_id: int, port: int, rgb: Tuple[int, int, int]) -> bool:
    """Write to LED hardware with disconnection handling.

    Args:
        device_id: LED device ID
        port: Port number
        rgb: RGB color tuple

    Returns:
        True if write succeeded, False if device unavailable
    """
    # Check device health
    healthy = await _health_checker.check_device(device_id)
    if not healthy:
        logger.warning(f"Skipping write to disconnected device {device_id}")
        return False

    try:
        from backend.services.led_hardware import write_port
        write_port(device_id, port, rgb)
        return True
    except Exception as e:
        logger.error(f"Hardware write error: {e}")
        return False


# ============================================================================
# Concurrent Request Protection
# ============================================================================

class DeviceLock:
    """Semaphore-based lock for LED device access.

    Prevents multiple concurrent pattern applications that could cause:
    - Conflicting LED states
    - USB bus saturation
    - Flickering
    """

    def __init__(self, max_concurrent: int = 1):
        """Initialize device lock.

        Args:
            max_concurrent: Max concurrent operations per device (usually 1)
        """
        self._locks: Dict[int, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(max_concurrent)
        )

    async def __aenter__(self):
        """Context manager entry - not used directly."""
        pass

    async def __aexit__(self, *args):
        """Context manager exit - not used directly."""
        pass

    def acquire(self, device_id: int):
        """Get semaphore for device.

        Args:
            device_id: Device ID

        Returns:
            Async context manager

        Usage:
            async with device_lock.acquire(0):
                # Apply pattern
                await apply_pattern(...)
        """
        return self._locks[device_id]


_device_lock = DeviceLock(max_concurrent=1)


def get_device_lock() -> DeviceLock:
    """Get global device lock for concurrent protection.

    Returns:
        Singleton DeviceLock instance
    """
    return _device_lock


# ============================================================================
# Error Recovery Utilities
# ============================================================================

async def with_retry(
    func,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    backoff: float = 2.0
):
    """Execute async function with exponential backoff retry.

    Args:
        func: Async function to execute
        max_retries: Maximum retry attempts
        retry_delay: Initial delay between retries (seconds)
        backoff: Backoff multiplier for each retry

    Returns:
        Function result

    Raises:
        Last exception if all retries exhausted
    """
    last_exception = None
    delay = retry_delay

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
                delay *= backoff
            else:
                logger.error(f"All {max_retries + 1} attempts failed")

    raise last_exception
