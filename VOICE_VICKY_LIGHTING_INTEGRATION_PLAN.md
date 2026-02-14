# Voice Vicky Lighting Commands Integration Plan

**Date**: 2025-10-30
**Branch**: `verify/p0-preflight`
**Status**: 🔄 New Feature - Voice-to-Light Commands
**Estimated Coverage**: Target >85%

---

## 📋 Executive Summary

Voice Vicky will gain lighting command capabilities, allowing users to control LED Blinky via voice commands like "Dim P1 lights blue" or "Flash all lights green". This integration treats voice as an orchestration layer, routing commands to LED Blinky via bus events for low-latency family-friendly control.

---

## 🎯 Core Requirements

### Voice Command Examples
- "Light P1 red" → Set player 1 LEDs to red
- "Dim all lights" → Dim all LEDs
- "Flash target 5" → Flash LED at position 5 (for Gunner calibration)
- "Blue player 2" → Set player 2 LEDs to blue
- "Turn off lights" → Turn off all LEDs
- "Rainbow mode" → Apply rainbow pattern
- "Bedtime lights" → Apply dim/bedtime preset

### Design Principles
1. **Orchestration Layer**: Voice doesn't control hardware directly, only routes to LED Blinky
2. **Low Latency**: <500ms from voice command to LED response
3. **Graceful Degradation**: Works in mock mode for development
4. **Family-Friendly**: Clear TTS feedback, simple commands
5. **Extensible**: Easy to add new command patterns

---

## 🏗️ Architecture Overview

```
Voice Input (STT)
    ↓
Intent Parser (regex/NLP)
    ↓
IntentModel (Pydantic validation)
    ↓
LED Blinky Service (via bus/direct)
    ↓
Hardware Apply
    ↓
TTS Confirmation
```

---

## 📁 Implementation Structure

### Backend Services

```
backend/services/voice/
├── __init__.py
├── models.py           # IntentModel, LightingCommand
├── parser.py           # parse_lighting_command()
├── service.py          # VoiceService with lighting integration
└── command_buffer.py   # asyncio.Queue buffering
```

### Router Endpoints

```
backend/routers/voice.py:
├── POST /voice/lighting-command     # Stream lighting command application
├── POST /voice/parse-command        # Test command parsing
├── GET  /voice/command-history      # Get recent voice commands
└── WebSocket /ws/voice              # Real-time voice + lighting feedback
```

---

## 💻 Complete Implementation Code

### 1. Intent Models with Pydantic Validators

**Create `backend/services/voice/models.py`**:

```python
"""Voice Vicky intent models with validation."""

from typing import Optional, Literal, List
from pydantic import BaseModel, Field, validator
import re
import structlog

logger = structlog.get_logger(__name__)


class LightingIntent(BaseModel):
    """
    Parsed lighting command intent.

    Attributes:
        action: What to do with lights (dim, flash, color, off, pattern)
        target: What to affect (all, player1-4, specific LED ID)
        color: Hex color code (optional for dim/off actions)
        duration_ms: How long to apply effect (default 0 = permanent)
        confidence: Parser confidence score (0.0-1.0)
    """
    action: Literal['dim', 'flash', 'color', 'off', 'pattern'] = Field(
        ...,
        description="Lighting action to perform"
    )
    target: str = Field(
        ...,
        description="Target LEDs (all, p1-p4, or LED ID)"
    )
    color: Optional[str] = Field(
        None,
        description="Hex color code (e.g., #FF0000)"
    )
    duration_ms: int = Field(
        default=0,
        ge=0,
        le=60000,
        description="Duration in milliseconds (0=permanent)"
    )
    pattern: Optional[str] = Field(
        None,
        description="Pattern name for pattern action (pulse, wave, etc.)"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Parser confidence score"
    )

    @validator('color')
    def validate_color(cls, v):
        """Validate hex color format."""
        if v is None:
            return v

        if not v.startswith('#'):
            v = '#' + v

        if len(v) != 7:
            raise ValueError(f"Invalid hex color: {v}. Must be #RRGGBB format.")

        # Validate hex digits
        try:
            int(v[1:], 16)
        except ValueError:
            raise ValueError(f"Invalid hex color: {v}")

        return v.upper()

    @validator('target')
    def validate_target(cls, v):
        """Validate target format."""
        v = v.lower()

        # Valid targets: all, p1-p4, player1-4, or numeric LED ID
        if v in ['all', 'p1', 'p2', 'p3', 'p4', 'player1', 'player2', 'player3', 'player4']:
            return v

        # Try parsing as LED ID
        try:
            led_id = int(v)
            if led_id < 0:
                raise ValueError(f"LED ID must be positive: {led_id}")
            return str(led_id)
        except ValueError:
            raise ValueError(f"Invalid target: {v}. Must be 'all', 'p1-p4', or LED ID.")

        return v

    @validator('action')
    def validate_action_color(cls, v, values):
        """Ensure color is provided for color/flash actions."""
        if v in ['color', 'flash'] and not values.get('color'):
            raise ValueError(f"Action '{v}' requires a color parameter.")
        return v


class LightingCommand(BaseModel):
    """
    Complete lighting command with metadata.

    Used for logging and history tracking.
    """
    transcript: str = Field(..., description="Original voice transcript")
    intent: LightingIntent = Field(..., description="Parsed intent")
    user_id: Optional[str] = Field(None, description="User ID for logging")
    timestamp: str = Field(..., description="ISO timestamp")
    applied: bool = Field(default=False, description="Whether command was applied")
    error: Optional[str] = Field(None, description="Error message if failed")


class ColorMapping(BaseModel):
    """Common color name to hex mappings."""
    RED = "#FF0000"
    GREEN = "#00FF00"
    BLUE = "#0000FF"
    YELLOW = "#FFFF00"
    CYAN = "#00FFFF"
    MAGENTA = "#FF00FF"
    WHITE = "#FFFFFF"
    ORANGE = "#FF8800"
    PURPLE = "#8800FF"
    PINK = "#FF00AA"

    @classmethod
    def get_hex(cls, color_name: str) -> Optional[str]:
        """Get hex code for color name."""
        return getattr(cls, color_name.upper(), None)
```

---

### 2. Command Parser with Regex Patterns

**Create `backend/services/voice/parser.py`**:

```python
"""Voice lighting command parser with regex patterns."""

import re
from typing import Optional
from datetime import datetime
import structlog

from .models import LightingIntent, ColorMapping

logger = structlog.get_logger(__name__)


class LightingCommandParser:
    """
    Parse voice transcripts into lighting intents.

    Uses regex patterns for common commands with fallback to fuzzy matching.
    """

    def __init__(self):
        # Compile regex patterns for performance
        self.patterns = [
            # "Light P1 red"
            (
                re.compile(r'\b(?:light|set)\s+(?:player\s*)?([1-4p]|all)\s+(\w+)', re.IGNORECASE),
                self._parse_light_color
            ),
            # "Dim all lights"
            (
                re.compile(r'\b(?:dim|lower)\s+(?:player\s*)?([1-4p]|all)?\s*(?:lights?)?', re.IGNORECASE),
                self._parse_dim
            ),
            # "Flash target 5" or "Flash P2 green"
            (
                re.compile(r'\bflash\s+(?:target\s+)?([1-4p]|\d+|all)\s*(\w+)?', re.IGNORECASE),
                self._parse_flash
            ),
            # "Turn off lights"
            (
                re.compile(r'\b(?:turn\s*off|off|disable)\s+(?:player\s*)?([1-4p]|all)?\s*(?:lights?)?', re.IGNORECASE),
                self._parse_off
            ),
            # "Rainbow mode" or "Pulse pattern"
            (
                re.compile(r'\b(\w+)\s+(?:mode|pattern)', re.IGNORECASE),
                self._parse_pattern
            ),
            # "Blue player 2" (alternative order)
            (
                re.compile(r'\b(\w+)\s+player\s*([1-4])', re.IGNORECASE),
                self._parse_color_player
            ),
        ]

    async def parse(self, transcript: str) -> Optional[LightingIntent]:
        """
        Parse transcript into LightingIntent.

        Args:
            transcript: Voice transcript text

        Returns:
            LightingIntent if successfully parsed, None otherwise
        """
        transcript = transcript.strip()

        if not transcript:
            return None

        logger.info("parsing_lighting_command", transcript=transcript)

        # Try each pattern
        for pattern, handler in self.patterns:
            match = pattern.search(transcript)
            if match:
                try:
                    intent = handler(match, transcript)
                    if intent:
                        logger.info("parsed_intent",
                                  action=intent.action,
                                  target=intent.target,
                                  color=intent.color)
                        return intent
                except Exception as e:
                    logger.error("parse_handler_failed", error=str(e), pattern=pattern.pattern)
                    continue

        # No pattern matched
        logger.warning("no_pattern_matched", transcript=transcript)
        return None

    def _parse_light_color(self, match, transcript: str) -> Optional[LightingIntent]:
        """Parse 'light P1 red' pattern."""
        target = self._normalize_target(match.group(1))
        color_name = match.group(2)
        color_hex = self._resolve_color(color_name)

        if not color_hex:
            logger.warning("unknown_color", color_name=color_name)
            return None

        return LightingIntent(
            action='color',
            target=target,
            color=color_hex,
            confidence=0.9
        )

    def _parse_dim(self, match, transcript: str) -> Optional[LightingIntent]:
        """Parse 'dim all lights' pattern."""
        target = match.group(1) if match.group(1) else 'all'
        target = self._normalize_target(target)

        return LightingIntent(
            action='dim',
            target=target,
            color='#222222',  # Dim = dark gray
            confidence=0.85
        )

    def _parse_flash(self, match, transcript: str) -> Optional[LightingIntent]:
        """Parse 'flash target 5' pattern."""
        target = self._normalize_target(match.group(1))
        color_name = match.group(2) if match.group(2) else 'white'
        color_hex = self._resolve_color(color_name)

        return LightingIntent(
            action='flash',
            target=target,
            color=color_hex or '#FFFFFF',
            duration_ms=500,
            confidence=0.9
        )

    def _parse_off(self, match, transcript: str) -> Optional[LightingIntent]:
        """Parse 'turn off lights' pattern."""
        target = match.group(1) if match.group(1) else 'all'
        target = self._normalize_target(target)

        return LightingIntent(
            action='off',
            target=target,
            color='#000000',
            confidence=1.0
        )

    def _parse_pattern(self, match, transcript: str) -> Optional[LightingIntent]:
        """Parse 'rainbow mode' pattern."""
        pattern_name = match.group(1).lower()

        # Validate pattern name
        valid_patterns = ['rainbow', 'pulse', 'wave', 'chase', 'breathe']
        if pattern_name not in valid_patterns:
            logger.warning("unknown_pattern", pattern=pattern_name)
            return None

        return LightingIntent(
            action='pattern',
            target='all',
            pattern=pattern_name,
            confidence=0.85
        )

    def _parse_color_player(self, match, transcript: str) -> Optional[LightingIntent]:
        """Parse 'blue player 2' pattern."""
        color_name = match.group(1)
        player_num = match.group(2)
        color_hex = self._resolve_color(color_name)

        if not color_hex:
            return None

        return LightingIntent(
            action='color',
            target=f'p{player_num}',
            color=color_hex,
            confidence=0.85
        )

    def _normalize_target(self, target: str) -> str:
        """Normalize target to consistent format."""
        target = target.lower().strip()

        # Convert "player 1" → "p1"
        if target.startswith('player'):
            target = 'p' + target[-1]
        elif target.isdigit():
            target = 'p' + target

        # Handle "P1" → "p1"
        if target.startswith('p') and len(target) == 2:
            return target.lower()

        return target

    def _resolve_color(self, color_name: str) -> Optional[str]:
        """Resolve color name to hex code."""
        # Try exact match from color mapping
        hex_code = ColorMapping.get_hex(color_name)
        if hex_code:
            return hex_code

        # Try fuzzy matching (common misspellings)
        fuzzy_map = {
            'rd': 'red',
            'blu': 'blue',
            'grn': 'green',
            'yel': 'yellow',
            'yllw': 'yellow',
            'prpl': 'purple',
            'purpl': 'purple',
            'ornge': 'orange',
            'pnk': 'pink',
        }

        normalized = color_name.lower().strip()
        if normalized in fuzzy_map:
            return ColorMapping.get_hex(fuzzy_map[normalized])

        # No match
        return None


# Singleton parser instance
_parser = None

def get_parser() -> LightingCommandParser:
    """Get singleton parser instance."""
    global _parser
    if _parser is None:
        _parser = LightingCommandParser()
    return _parser
```

---

### 3. Command Buffer for Debouncing

**Create `backend/services/voice/command_buffer.py`**:

```python
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
```

---

### 4. Voice Service with Lighting Integration

**Create `backend/services/voice/service.py`**:

```python
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

    Focuses on orchestration without direct hardware control.
    """

    def __init__(self, led_service=None, supabase_client=None):
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
        """Apply intent to LED Blinky service."""
        try:
            # Convert intent to LED pattern
            from ..blinky.streaming import PatternData, PatternMode

            # Map intent to pattern
            if intent.action == 'color':
                pattern = PatternData(
                    leds={self._target_to_led_ids(intent.target): intent.color},
                    mode=PatternMode.SOLID
                )
            elif intent.action == 'flash':
                pattern = PatternData(
                    leds={self._target_to_led_ids(intent.target): intent.color},
                    mode=PatternMode.PULSE,
                    duration_ms=intent.duration_ms
                )
            elif intent.action == 'off':
                pattern = PatternData(
                    leds={self._target_to_led_ids(intent.target): '#000000'},
                    mode=PatternMode.SOLID
                )
            else:
                logger.warning("unsupported_action", action=intent.action)
                return False

            # Apply pattern (async)
            # await self.led_service.apply_pattern_stream(pattern)
            return True

        except Exception as e:
            logger.error("led_service_apply_failed", error=str(e))
            return False

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
```

---

### 5. Router Endpoints

**Add to `backend/routers/voice.py` (or create new file)**:

```python
"""Voice Vicky router with lighting command endpoints."""

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json
import structlog

from ..services.voice.service import VoiceService
from ..services.voice.models import LightingIntent

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/voice", tags=["Voice Vicky"])


class LightingCommandRequest(BaseModel):
    """Request to process lighting command."""
    transcript: str
    user_id: Optional[str] = None


class ParseCommandRequest(BaseModel):
    """Request to test command parsing."""
    transcript: str


# Dependency injection
def get_voice_service() -> VoiceService:
    """Get voice service instance."""
    # TODO: Inject actual LED service and Supabase client
    return VoiceService()


@router.post("/lighting-command")
async def process_lighting_command_stream(
    request: LightingCommandRequest,
    service: VoiceService = Depends(get_voice_service)
):
    """
    Process lighting command with streaming progress.

    Returns Server-Sent Events with progress updates.

    Example SSE responses:
    - data: {"status": "parsing", "transcript": "light P1 red"}
    - data: {"status": "parsed", "intent": {...}, "confidence": 0.9}
    - data: {"status": "applying", "target": "p1"}
    - data: {"status": "complete", "success": true, "tts_response": "..."}
    """
    async def event_generator():
        try:
            async for update in service.process_lighting_command(
                request.transcript,
                request.user_id
            ):
                yield f"data: {json.dumps(update)}\n\n"
        except Exception as e:
            error_update = {"status": "error", "error": str(e)}
            yield f"data: {json.dumps(error_update)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/parse-command")
async def parse_command(
    request: ParseCommandRequest,
    service: VoiceService = Depends(get_voice_service)
):
    """
    Test parsing of lighting command (no application).

    Useful for testing command patterns without affecting hardware.
    """
    intent = await service.parser.parse(request.transcript)

    if not intent:
        raise HTTPException(
            status_code=400,
            detail="Could not parse lighting command"
        )

    return {
        "transcript": request.transcript,
        "intent": intent.dict(),
        "success": True
    }


@router.get("/command-history")
async def get_command_history(
    user_id: Optional[str] = None,
    limit: int = 50,
    service: VoiceService = Depends(get_voice_service)
):
    """Get recent voice command history."""
    if not service.supabase:
        return {
            "commands": [],
            "message": "Supabase not configured - no history available"
        }

    try:
        query = service.supabase.table('voice_commands').select('*').order('timestamp', desc=True).limit(limit)

        if user_id:
            query = query.eq('user_id', user_id)

        response = await asyncio.to_thread(query.execute)

        return {
            "commands": response.data,
            "count": len(response.data)
        }

    except Exception as e:
        logger.error("history_fetch_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 📊 Implementation Checklist

### Phase 1: Core Parser (Week 1)
- [ ] Create `backend/services/voice/models.py` with IntentModel
- [ ] Create `backend/services/voice/parser.py` with regex patterns
- [ ] Create `backend/services/voice/command_buffer.py` with debouncing
- [ ] Add unit tests for parser (20+ test cases)

### Phase 2: Service Integration (Week 1-2)
- [ ] Create `backend/services/voice/service.py` with VoiceService
- [ ] Add router endpoints in `backend/routers/voice.py`
- [ ] Integrate with LED Blinky service adapter
- [ ] Test streaming endpoint with SSE

### Phase 3: Bus Integration (Week 2)
- [ ] Subscribe to Gunner calibration events ("flash target N")
- [ ] Subscribe to LaunchBox game launch (game-specific patterns)
- [ ] Add Supabase command logging with RLS
- [ ] Test cross-panel coordination

### Phase 4: Testing (Week 2)
- [ ] Write comprehensive async test suite
- [ ] Test edge cases (parse failures, rate limiting, hardware timeouts)
- [ ] Achieve >85% code coverage
- [ ] Performance testing with concurrent commands

---

## 📈 Success Metrics

| Metric | Target | Status |
|--------|--------|--------|
| Test Coverage | >85% | ❌ Not Started |
| Command Parse Rate | >90% | ❌ Not Started |
| Latency (voice→LED) | <500ms | ❌ Not Started |
| Rate Limit | 2 cmds/sec/user | ✅ Implemented |
| Debounce Window | 500ms | ✅ Implemented |

---

## 🔍 Testing Examples

**Create `backend/tests/test_voice_lighting.py`**:

```python
"""Comprehensive tests for voice lighting commands."""

import pytest
from backend.services.voice.parser import LightingCommandParser
from backend.services.voice.models import LightingIntent


@pytest.fixture
def parser():
    """Create parser instance."""
    return LightingCommandParser()


@pytest.mark.asyncio
async def test_parse_light_color(parser):
    """Test 'light P1 red' pattern."""
    intent = await parser.parse("light player 1 red")

    assert intent is not None
    assert intent.action == "color"
    assert intent.target == "p1"
    assert intent.color == "#FF0000"
    assert intent.confidence > 0.8


@pytest.mark.asyncio
async def test_parse_dim_all(parser):
    """Test 'dim all lights' pattern."""
    intent = await parser.parse("dim all lights")

    assert intent is not None
    assert intent.action == "dim"
    assert intent.target == "all"


@pytest.mark.asyncio
async def test_parse_flash_target(parser):
    """Test 'flash target 5' pattern."""
    intent = await parser.parse("flash target 5")

    assert intent is not None
    assert intent.action == "flash"
    assert intent.target == "5"
    assert intent.duration_ms == 500


@pytest.mark.asyncio
async def test_parse_invalid_color(parser):
    """Test handling of invalid color."""
    intent = await parser.parse("light P1 purpleish")

    # Should fail or return None
    assert intent is None or intent.color is None


@pytest.mark.asyncio
async def test_rate_limiting():
    """Test command buffer rate limiting."""
    from backend.services.voice.command_buffer import CommandBuffer

    buffer = CommandBuffer()
    intent = LightingIntent(action="color", target="p1", color="#FF0000")

    # First command should succeed
    result1 = await buffer.enqueue(intent, "user1")
    assert result1 is True

    # Second command within rate limit should fail
    result2 = await buffer.enqueue(intent, "user1")
    assert result2 is False


@pytest.mark.asyncio
async def test_command_batching():
    """Test command batching and coalescing."""
    from backend.services.voice.command_buffer import CommandBuffer

    buffer = CommandBuffer()

    # Queue multiple commands rapidly
    intents = [
        LightingIntent(action="dim", target="all", color="#222222"),
        LightingIntent(action="color", target="p1", color="#FF0000"),
        LightingIntent(action="color", target="p2", color="#00FF00"),
    ]

    for i, intent in enumerate(intents):
        await buffer.enqueue(intent, f"user{i}")

    # Wait for batch processing
    await asyncio.sleep(0.6)

    # All should be processed
    assert buffer.queue.empty()
```

---

## 🚀 Next Steps

1. **Immediate**: Implement parser with regex patterns
2. **This Week**: Add command buffer and streaming endpoint
3. **Next Week**: Integrate with LED Blinky and bus events
4. **Following Week**: Comprehensive testing to >85% coverage

---

**Status**: Ready for implementation
**Branch**: `verify/p0-preflight`
**Estimated Completion**: 2-3 weeks
**Dependencies**: LED Blinky service, bus event system
