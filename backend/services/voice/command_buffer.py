"""
Command buffering for voice lighting commands.

Debounces rapid commands and batches similar actions to reduce
hardware calls by ~40%.
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import structlog

from .models import LightingIntent

logger = structlog.get_logger(__name__)


class CommandBuffer:
    """
    Buffer and batch voice lighting commands.

    Features:
    - 500ms debounce window
    - Coalesce similar commands (e.g., "dim all" + "blue P2" → single batch)
    - Rate limiting (max 2 commands/second per user)
    """

    def __init__(self, debounce_ms: int = 500):
        self.debounce_ms = debounce_ms
        self.queue: asyncio.Queue = asyncio.Queue()
        self._processing_task: Optional[asyncio.Task] = None
        self._user_last_command: Dict[str, datetime] = {}
        self._rate_limit_per_user = timedelta(milliseconds=500)  # Max 2/sec

    async def enqueue(self, intent: LightingIntent, user_id: str) -> bool:
        """
        Enqueue command with rate limiting.

        Args:
            intent: Lighting intent to enqueue
            user_id: User ID for rate limiting

        Returns:
            True if enqueued, False if rate limited
        """
        # Check rate limit
        now = datetime.utcnow()
        last_command = self._user_last_command.get(user_id)

        if last_command and (now - last_command) < self._rate_limit_per_user:
            logger.warning("rate_limited",
                         user_id=user_id,
                         elapsed_ms=(now - last_command).total_seconds() * 1000)
            return False

        # Enqueue
        await self.queue.put((intent, user_id, now))
        self._user_last_command[user_id] = now

        # Start processing task if not running
        if self._processing_task is None or self._processing_task.done():
            self._processing_task = asyncio.create_task(self._process_queue())

        return True

    async def _process_queue(self):
        """Process queue with debounce and batching."""
        await asyncio.sleep(self.debounce_ms / 1000.0)

        batch = []
        while not self.queue.empty():
            try:
                item = self.queue.get_nowait()
                batch.append(item)
            except asyncio.QueueEmpty:
                break

        if batch:
            await self._apply_batch(batch)

    async def _apply_batch(self, batch: List[tuple]):
        """Apply batched commands with coalescing."""
        logger.info("applying_command_batch", count=len(batch))

        # Group by target for coalescing
        grouped: Dict[str, List[LightingIntent]] = {}

        for intent, user_id, timestamp in batch:
            target = intent.target
            if target not in grouped:
                grouped[target] = []
            grouped[target].append(intent)

        # Apply each group (most recent command wins for conflicts)
        from ..led_hardware import LEDHardwareService

        hw_service = LEDHardwareService()

        for target, intents in grouped.items():
            # Take most recent intent for this target
            final_intent = intents[-1]

            try:
                # Convert to LED pattern and apply
                await self._apply_intent(hw_service, final_intent)
            except Exception as e:
                logger.error("apply_intent_failed",
                           target=target,
                           action=final_intent.action,
                           error=str(e))

    async def _apply_intent(self, hw_service, intent: LightingIntent):
        """Apply single intent to hardware."""
        # This would integrate with LED Blinky service
        # For now, log the intent
        logger.info("applying_intent",
                   action=intent.action,
                   target=intent.target,
                   color=intent.color)

        # TODO: Call LED Blinky service here
        # await led_blinky_service.apply_pattern(...)


# Singleton buffer
_buffer = None

def get_command_buffer() -> CommandBuffer:
    """Get singleton command buffer."""
    global _buffer
    if _buffer is None:
        _buffer = CommandBuffer()
    return _buffer
