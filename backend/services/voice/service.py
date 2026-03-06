"""Voice service with lighting command processing."""

import asyncio
from typing import AsyncGenerator, Dict, Any, Optional
from datetime import datetime
import structlog

from .models import LightingIntent, LightingCommand
from .parser import get_parser
from .command_buffer import get_command_buffer

logger = structlog.get_logger(__name__)


class VoiceService:
    """
    Voice service orchestrating STT, TTS, and lighting commands.

    Accepts an LEDHardwareService instance and optional Supabase client
    for real hardware control and command logging.
    """

    def __init__(self, led_service=None, supabase_client=None):
        """Initialize VoiceService.

        Args:
            led_service: LEDHardwareService singleton for HID LED control.
                         If None, voice lighting commands run in mock mode.
            supabase_client: Supabase client for command logging.
                             If None, commands are not logged remotely.
        """
        self.led_service = led_service
        self.supabase = supabase_client
        self.parser = get_parser()
        self.buffer = get_command_buffer()

    async def process_lighting_command(
        self,
        transcript: str,
        user_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process lighting command from voice transcript.

        Yields progress updates as command is parsed and applied.

        Args:
            transcript: Voice transcript text
            user_id: Optional user ID for logging

        Yields:
            {"status": "parsing", "transcript": "..."}
            {"status": "parsed", "intent": {...}}
            {"status": "applying", "target": "p1"}
            {"status": "complete", "success": true}
        """
        logger.info("processing_lighting_command",
                   transcript=transcript,
                   user_id=user_id)

        yield {"status": "parsing", "transcript": transcript}

        try:
            # Parse transcript
            intent = await self.parser.parse(transcript)

            if not intent:
                yield {
                    "status": "error",
                    "error": "Could not understand lighting command",
                    "suggestion": "Try 'light P1 red' or 'dim all lights'"
                }
                return

            yield {
                "status": "parsed",
                "intent": intent.dict(),
                "confidence": intent.confidence
            }

            # Check confidence
            if intent.confidence < 0.7:
                yield {
                    "status": "low_confidence",
                    "intent": intent.dict(),
                    "message": "Did you mean this?",
                    "requires_confirmation": True
                }
                # In production, wait for user confirmation here
                await asyncio.sleep(0.5)  # Simulated confirmation wait

            # Enqueue command
            if user_id:
                enqueued = await self.buffer.enqueue(intent, user_id)
                if not enqueued:
                    yield {
                        "status": "error",
                        "error": "Too many commands. Slow down!",
                        "rate_limit": True
                    }
                    return

            yield {"status": "applying", "target": intent.target}

            # Apply via LED service
            if self.led_service:
                success = await self._apply_to_led_service(intent)
            else:
                # Mock mode
                logger.info("mock_mode_apply", intent=intent.dict())
                success = True
                await asyncio.sleep(0.2)  # Simulate apply time

            # Log to Supabase
            if self.supabase:
                await self._log_command(transcript, intent, user_id, success)

            yield {
                "status": "complete",
                "success": success,
                "intent": intent.dict(),
                "tts_response": self._generate_tts_response(intent, success)
            }

        except Exception as e:
            logger.error("lighting_command_failed", error=str(e), transcript=transcript)
            yield {
                "status": "error",
                "error": str(e),
                "transcript": transcript
            }

    async def _apply_to_led_service(self, intent: LightingIntent) -> bool:
        """Apply intent to LED hardware via injected LEDHardwareService."""
        try:
            hw = self.led_service
            port = self._target_to_led_ids(intent.target)

            if intent.action == 'color':
                color_rgb = self._hex_to_rgb(intent.color)
                logger.info("applying_color", target=intent.target, rgb=color_rgb)
                hw.write_port(0, port, color_rgb)
                await self._sync_led_state(port, color_rgb, "vicky_voice")
                return True

            elif intent.action == 'flash':
                color_rgb = self._hex_to_rgb(intent.color)
                logger.info("applying_flash", target=intent.target, color=intent.color)
                hw.write_port(0, port, color_rgb)
                await asyncio.sleep(0.3)
                hw.write_port(0, port, (0, 0, 0))
                return True

            elif intent.action == 'off':
                logger.info("turning_off", target=intent.target)
                hw.write_port(0, port, (0, 0, 0))
                await self._sync_led_state(port, (0, 0, 0), "vicky_voice")
                return True

            elif intent.action == 'dim':
                logger.info("dimming", target=intent.target)
                # Dim = 20% brightness (scale current color)
                hw.write_port(0, port, (12, 12, 12))
                await self._sync_led_state(port, (12, 12, 12), "vicky_voice")
                return True

            elif intent.action == 'pattern':
                logger.info("applying_pattern", pattern=intent.pattern)
                # Patterns delegated to BlinkyService CLI when available
                try:
                    from ..blinky_service import BlinkyProcessManager
                    manager = BlinkyProcessManager.get_instance()
                    await manager.play_animation(intent.pattern)
                except Exception as pat_err:
                    logger.warning("pattern_fallback", error=str(pat_err))
                return True

            logger.warning("unsupported_action", action=intent.action)
            return False

        except Exception as e:
            logger.error("led_service_apply_failed", error=str(e))
            return False

    async def _sync_led_state(
        self, port: int, rgb: tuple, triggered_by: str
    ) -> None:
        """Mirror LED state to Supabase for fleet visibility (Pillar 4)."""
        if not self.supabase:
            return
        try:
            import os
            await asyncio.to_thread(
                self.supabase.table("led_states").insert({
                    "device_id": os.getenv("AA_DEVICE_ID", "unknown"),
                    "port": port,
                    "hex": f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}",
                    "triggered_by": triggered_by,
                }).execute
            )
        except Exception as e:
            logger.debug("led_state_sync_failed", error=str(e))

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def _target_to_led_ids(self, target: str) -> int:
        """Convert target to LED IDs."""
        # Simplified mapping (in production, query hardware)
        mapping = {
            'p1': 0,
            'p2': 4,
            'p3': 8,
            'p4': 12,
            'all': list(range(16))
        }

        return mapping.get(target, 0)

    async def _log_command(
        self,
        transcript: str,
        intent: LightingIntent,
        user_id: Optional[str],
        success: bool
    ):
        """Log command to Supabase."""
        try:
            command = LightingCommand(
                transcript=transcript,
                intent=intent,
                user_id=user_id,
                timestamp=datetime.utcnow().isoformat(),
                applied=success
            )

            # Supabase logging with RLS
            await asyncio.to_thread(
                self.supabase.table('voice_commands')
                .insert(command.dict())
                .execute
            )

            logger.info("command_logged", transcript=transcript, success=success)

        except Exception as e:
            logger.error("command_log_failed", error=str(e))

    def _generate_tts_response(self, intent: LightingIntent, success: bool) -> str:
        """Generate TTS confirmation message."""
        if not success:
            return "Sorry, I couldn't apply that lighting command."

        # Generate friendly confirmation
        responses = {
            'color': f"Lights set to {intent.color} for {intent.target}",
            'dim': f"Dimmed lights for {intent.target}",
            'flash': f"Flashing {intent.target}",
            'off': f"Turned off lights for {intent.target}",
            'pattern': f"Applied {intent.pattern} pattern"
        }

        return responses.get(intent.action, "Lighting command applied")
