# LED Blinky Integration Implementation Plan

**Date**: 2025-10-30
**Branch**: `verify/p0-preflight`
**Status**: 🔄 Enhancement Phase - Add Streaming & Bus Integration
**Existing Coverage**: ~65% (needs boost to >85%)

---

## 📋 Executive Summary

LED Blinky service already has solid hardware detection and REST endpoints. This document outlines enhancements needed for WebSocket streaming, bus integration with Gunner/LaunchBox, and comprehensive testing per POR requirements.

---

## ✅ Existing Implementation (Already Complete)

### Backend Infrastructure
1. **`backend/services/led_hardware.py`** (7,755 bytes)
   - Singleton LED hardware service
   - HID device detection (LED-Wiz, Pac-LED64, GroovyGameGear, Ultimarc)
   - Hotplug monitoring with background thread
   - Mock mode for development
   - Event callback system

2. **`backend/services/led_config.py`** (8,092 bytes)
   - LED configuration management
   - Profile storage and retrieval

3. **`backend/services/led_animation.py`** (9,558 bytes)
   - Animation pattern definitions
   - Effect implementations (pulse, wave, solid, rainbow, etc.)

4. **`backend/routers/led_blinky.py`**
   - POST `/led/test` - Test LED effect
   - POST `/led/mapping/preview` - Preview LED mapping
   - POST `/led/mapping/apply` - Apply LED mapping
   - GET `/led/profiles` - List LED profiles
   - GET `/led/profiles/{name}` - Get specific profile

### Key Strengths
- ✅ Hardware detection with mock fallback
- ✅ Multiple LED controller support
- ✅ Hotplug monitoring
- ✅ Profile management
- ✅ Animation effects
- ✅ Pydantic validation
- ✅ Change logging to JSONL

---

## 🎯 Required Enhancements (POR Compliance)

### 1. WebSocket Real-Time Streaming

**Status**: ❌ Not Implemented
**Priority**: P0
**Estimated Time**: 2-3 hours

#### Purpose
Enable real-time LED control via WebSocket for responsive UI toggles and streaming pattern application.

#### Implementation

**Add to `backend/routers/led_blinky.py`**:
```python
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json
from typing import Dict, Set
import structlog

logger = structlog.get_logger(__name__)


class LEDWebSocketManager:
    """Manage WebSocket connections for LED streaming."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.led_state: Dict[int, Dict[str, str]] = {}  # {led_id: {color, status}}
        self.toggle_queue: asyncio.Queue = asyncio.Queue()
        self._debounce_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info("led_websocket_connected", total_connections=len(self.active_connections))

        # Send current LED state
        await websocket.send_json({
            "type": "state",
            "leds": self.led_state
        })

    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection."""
        self.active_connections.discard(websocket)
        logger.info("led_websocket_disconnected", remaining_connections=len(self.active_connections))

    async def broadcast(self, message: Dict):
        """Broadcast message to all connected clients."""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error("broadcast_failed", error=str(e))
                disconnected.add(connection)

        # Clean up disconnected clients
        self.active_connections -= disconnected

    async def handle_toggle(self, data: Dict):
        """Handle LED toggle request with debouncing."""
        await self.toggle_queue.put(data)

        # Start debounce task if not running
        if self._debounce_task is None or self._debounce_task.done():
            self._debounce_task = asyncio.create_task(self._process_toggle_queue())

    async def _process_toggle_queue(self):
        """Process toggle queue with 100ms debounce."""
        await asyncio.sleep(0.1)  # Debounce window

        batch = []
        while not self.toggle_queue.empty():
            try:
                item = self.toggle_queue.get_nowait()
                batch.append(item)
            except asyncio.QueueEmpty:
                break

        if batch:
            await self._apply_toggle_batch(batch)

    async def _apply_toggle_batch(self, batch: List[Dict]):
        """Apply batched LED toggles to hardware."""
        logger.info("applying_toggle_batch", count=len(batch))

        from ..services.led_hardware import LEDHardwareService
        hw_service = LEDHardwareService()

        for toggle in batch:
            led_id = toggle.get("led_id")
            color = toggle.get("color", "#000000")
            status = toggle.get("status", "on")

            # Update state
            self.led_state[led_id] = {"color": color, "status": status}

            # Apply to hardware (mock or real)
            try:
                if status == "on":
                    hw_service.set_led(led_id, self._hex_to_rgb(color))
                else:
                    hw_service.set_led(led_id, (0, 0, 0))
            except Exception as e:
                logger.error("hardware_apply_failed", led_id=led_id, error=str(e))

        # Broadcast state update
        await self.broadcast({
            "type": "update",
            "leds": {t["led_id"]: {"color": t["color"], "status": t.get("status", "on")} for t in batch}
        })

    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


# Global WebSocket manager
led_ws_manager = LEDWebSocketManager()


@router.websocket("/ws/led")
async def led_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time LED control.

    Client → Server Messages:
    - {"type": "toggle", "led_id": 5, "color": "#FF0000", "status": "on"}
    - {"type": "pattern", "pattern_id": "pulse", "leds": [1,2,3], "color": "#00FF00"}
    - {"type": "subscribe", "events": ["state", "update"]}

    Server → Client Messages:
    - {"type": "state", "leds": {1: {"color": "#FF0000", "status": "on"}}}
    - {"type": "update", "leds": {5: {"color": "#00FF00", "status": "on"}}}
    - {"type": "error", "message": "Invalid LED ID"}
    """
    await led_ws_manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "toggle":
                # Validate and queue toggle
                led_id = data.get("led_id")
                color = data.get("color", "#000000")

                if not isinstance(led_id, int) or led_id < 0:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Invalid LED ID: {led_id}"
                    })
                    continue

                # Validate hex color
                if not color.startswith("#") or len(color) != 7:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Invalid hex color: {color}"
                    })
                    continue

                await led_ws_manager.handle_toggle(data)

            elif msg_type == "pattern":
                # Apply pattern to multiple LEDs
                pattern_id = data.get("pattern_id")
                leds = data.get("leds", [])
                color = data.get("color", "#00FF00")

                for led_id in leds:
                    await led_ws_manager.handle_toggle({
                        "led_id": led_id,
                        "color": color,
                        "status": "on"
                    })

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}"
                })

    except WebSocketDisconnect:
        led_ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error("websocket_error", error=str(e))
        led_ws_manager.disconnect(websocket)
```

---

### 2. Bus Event Integration for Gunner Calibration Flashes

**Status**: ❌ Not Implemented
**Priority**: P0
**Estimated Time**: 1-2 hours

#### Purpose
Subscribe to Gunner calibration events and flash LEDs at target coordinates.

#### Implementation

**Create `backend/services/led_bus_integration.py`**:
```python
"""LED Blinky bus event integration for cross-panel coordination."""

import asyncio
import structlog
from typing import Dict, Any
from .bus_events import subscribe_to_event, EventType
from .led_hardware import LEDHardwareService

logger = structlog.get_logger(__name__)


class LEDBusIntegration:
    """Handle LED responses to bus events from other panels."""

    def __init__(self):
        self.hw_service = LEDHardwareService()
        self._register_handlers()

    def _register_handlers(self):
        """Register event handlers for LED responses."""
        subscribe_to_event(EventType.LED_FLASH_TARGET, self._handle_flash_target)
        subscribe_to_event(EventType.LED_FLASH_SUCCESS, self._handle_flash_success)
        subscribe_to_event(EventType.LED_FLASH_ERROR, self._handle_flash_error)
        subscribe_to_event(EventType.CALIB_POINT_CAPTURED, self._handle_calib_point)

        logger.info("led_bus_handlers_registered")

    async def _handle_flash_target(self, event):
        """Flash LED at calibration target coordinates."""
        x = event.payload.get("x", 0.5)
        y = event.payload.get("y", 0.5)
        index = event.payload.get("index", 0)

        # Map coordinates to LED grid (assuming 4x4 grid, 16 LEDs)
        led_x = int(x * 3)  # 0-3
        led_y = int(y * 3)  # 0-3
        led_id = led_y * 4 + led_x

        logger.info("flashing_target_led",
                   x=x, y=y,
                   led_id=led_id,
                   point_index=index)

        # Flash LED white for 500ms
        await self._flash_led(led_id, (255, 255, 255), duration_ms=500)

    async def _handle_flash_success(self, event):
        """Flash all LEDs green for success."""
        logger.info("flashing_success_pattern")

        # Flash all LEDs green
        for led_id in range(16):  # Assuming 16 LEDs
            await self._flash_led(led_id, (0, 255, 0), duration_ms=200)

    async def _handle_flash_error(self, event):
        """Flash all LEDs red for error."""
        logger.info("flashing_error_pattern")

        # Flash all LEDs red
        for led_id in range(16):
            await self._flash_led(led_id, (255, 0, 0), duration_ms=200)

    async def _handle_calib_point(self, event):
        """Visual confirmation of calibration point captured."""
        index = event.payload.get("index", 0)
        confidence = event.payload.get("confidence", 0.0)

        # Flash LED based on confidence (green = high, yellow = medium, red = low)
        if confidence > 0.9:
            color = (0, 255, 0)  # Green
        elif confidence > 0.7:
            color = (255, 255, 0)  # Yellow
        else:
            color = (255, 128, 0)  # Orange

        # Flash LED at point index
        await self._flash_led(index % 16, color, duration_ms=300)

    async def _flash_led(self, led_id: int, rgb: tuple, duration_ms: int = 500):
        """Flash LED with specified color for duration."""
        try:
            # Turn on
            self.hw_service.set_led(led_id, rgb)

            # Wait
            await asyncio.sleep(duration_ms / 1000.0)

            # Turn off
            self.hw_service.set_led(led_id, (0, 0, 0))

        except Exception as e:
            logger.error("flash_led_failed", led_id=led_id, error=str(e))


# Initialize bus integration on module import
_led_bus = None

def get_led_bus_integration() -> LEDBusIntegration:
    """Get LED bus integration singleton."""
    global _led_bus
    if _led_bus is None:
        _led_bus = LEDBusIntegration()
    return _led_bus
```

---

### 3. Async Streaming Pattern Application

**Status**: ⚠️ Partial (has animation support, needs async streaming)
**Priority**: P1
**Estimated Time**: 2 hours

#### Implementation

**Create `backend/services/blinky/streaming.py`**:
```python
"""Async streaming pattern application with progress yields."""

import asyncio
import structlog
from typing import AsyncGenerator, Dict, Any, List
from pydantic import BaseModel, Field, validator
from enum import Enum

logger = structlog.get_logger(__name__)


class PatternMode(str, Enum):
    """LED pattern modes."""
    SOLID = "solid"
    WAVE = "wave"
    PULSE = "pulse"
    CHASE = "chase"
    RAINBOW = "rainbow"
    BREATHE = "breathe"


class PatternData(BaseModel):
    """LED pattern configuration with validation."""
    leds: Dict[int, str] = Field(..., description="LED ID to hex color mapping")
    mode: PatternMode = Field(default=PatternMode.SOLID)
    duration_ms: int = Field(default=1000, ge=100, le=10000)
    repeat: bool = Field(default=False)

    @validator('leds')
    def validate_led_colors(cls, v):
        """Validate LED color hex codes."""
        for led_id, color in v.items():
            if not isinstance(led_id, int) or led_id < 0:
                raise ValueError(f"Invalid LED ID: {led_id}")

            if not color.startswith('#') or len(color) != 7:
                raise ValueError(f"Invalid hex color: {color}. Must be #RRGGBB format.")

            # Validate hex digits
            try:
                int(color[1:], 16)
            except ValueError:
                raise ValueError(f"Invalid hex color: {color}")

        return v


class LEDPatternStreamer:
    """Stream LED pattern application with progress updates."""

    def __init__(self, hardware_service):
        self.hw_service = hardware_service

    async def apply_pattern_stream(self, pattern: PatternData) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Apply LED pattern with streaming progress updates.

        Yields progress updates for each LED as it's applied.

        Args:
            pattern: PatternData with LED configuration

        Yields:
            {"led_id": 5, "color": "#FF0000", "status": "applied", "progress": 0.33}
        """
        total_leds = len(pattern.leds)
        applied_count = 0

        logger.info("pattern_stream_started",
                   mode=pattern.mode,
                   led_count=total_leds)

        try:
            if pattern.mode == PatternMode.SOLID:
                # Apply all LEDs immediately
                for led_id, color in pattern.leds.items():
                    await self._apply_led(led_id, color)
                    applied_count += 1

                    yield {
                        "led_id": led_id,
                        "color": color,
                        "status": "applied",
                        "progress": applied_count / total_leds
                    }

                    # Small delay for visual feedback
                    await asyncio.sleep(0.05)

            elif pattern.mode == PatternMode.WAVE:
                # Apply LEDs in sequence with wave effect
                sorted_leds = sorted(pattern.leds.items())

                for led_id, color in sorted_leds:
                    await self._apply_led(led_id, color)
                    applied_count += 1

                    yield {
                        "led_id": led_id,
                        "color": color,
                        "status": "applied",
                        "progress": applied_count / total_leds,
                        "effect": "wave"
                    }

                    await asyncio.sleep(0.1)  # Wave delay

            elif pattern.mode == PatternMode.PULSE:
                # Pulse all LEDs together
                for cycle in range(3):  # 3 pulse cycles
                    # Fade in
                    for brightness in range(0, 101, 10):
                        for led_id, color in pattern.leds.items():
                            await self._apply_led_with_brightness(led_id, color, brightness / 100.0)

                        yield {
                            "status": "pulsing",
                            "cycle": cycle + 1,
                            "brightness": brightness,
                            "progress": (cycle * 100 + brightness) / 300
                        }

                        await asyncio.sleep(0.05)

                    # Fade out
                    for brightness in range(100, -1, -10):
                        for led_id, color in pattern.leds.items():
                            await self._apply_led_with_brightness(led_id, color, brightness / 100.0)

                        await asyncio.sleep(0.05)

            # Final status
            yield {
                "status": "complete",
                "mode": pattern.mode.value,
                "leds_applied": total_leds,
                "progress": 1.0
            }

        except Exception as e:
            logger.error("pattern_stream_failed", error=str(e))
            yield {
                "status": "error",
                "error": str(e),
                "progress": applied_count / total_leds
            }

    async def _apply_led(self, led_id: int, hex_color: str):
        """Apply color to LED."""
        rgb = self._hex_to_rgb(hex_color)
        self.hw_service.set_led(led_id, rgb)

    async def _apply_led_with_brightness(self, led_id: int, hex_color: str, brightness: float):
        """Apply color to LED with brightness modifier."""
        rgb = self._hex_to_rgb(hex_color)
        dimmed_rgb = tuple(int(c * brightness) for c in rgb)
        self.hw_service.set_led(led_id, dimmed_rgb)

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
```

**Add streaming endpoint to `routers/led_blinky.py`**:
```python
from fastapi.responses import StreamingResponse
from ..services.blinky.streaming import LEDPatternStreamer, PatternData

@router.post("/pattern/stream")
async def stream_led_pattern(pattern: PatternData):
    """
    Stream LED pattern application with real-time progress.

    Returns Server-Sent Events with progress updates as each LED is applied.

    Example SSE responses:
    - data: {"led_id": 5, "color": "#FF0000", "status": "applied", "progress": 0.2}
    - data: {"led_id": 6, "color": "#00FF00", "status": "applied", "progress": 0.4}
    - data: {"status": "complete", "mode": "solid", "leds_applied": 10, "progress": 1.0}
    """
    from ..services.led_hardware import LEDHardwareService
    import json

    hw_service = LEDHardwareService()
    streamer = LEDPatternStreamer(hw_service)

    async def event_generator():
        try:
            async for update in streamer.apply_pattern_stream(pattern):
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
```

---

### 4. Supabase Pattern Persistence

**Status**: ❌ Not Implemented
**Priority**: P2
**Estimated Time**: 2 hours

#### Implementation

**Create `backend/services/blinky/persistence.py`**:
```python
"""LED pattern persistence with Supabase + local fallback."""

import json
import asyncio
import aiofiles
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


class LEDPatternPersistence:
    """Persist LED patterns to Supabase with local JSON fallback."""

    def __init__(self, supabase_client=None, storage_path: Path = None):
        self.supabase = supabase_client
        self.storage_path = storage_path or Path("/mnt/a/state/led/patterns")
        self.storage_path.mkdir(parents=True, exist_ok=True)

    async def save_pattern(self, pattern_id: str, pattern_data: Dict[str, Any], user_id: str):
        """Save LED pattern to Supabase and local storage."""
        pattern_record = {
            "pattern_id": pattern_id,
            "user_id": user_id,
            "data": pattern_data,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        # Try Supabase first
        if self.supabase:
            try:
                response = await asyncio.to_thread(
                    self.supabase.table('led_patterns')
                    .upsert(pattern_record, on_conflict='pattern_id')
                    .execute
                )

                logger.info("pattern_saved_supabase", pattern_id=pattern_id)
                # Also save local copy
                await self._save_local(pattern_id, pattern_record)
                return response.data[0] if response.data else pattern_record

            except Exception as e:
                logger.error("supabase_save_failed", error=str(e), pattern_id=pattern_id)
                # Fall through to local save

        # Local fallback
        await self._save_local(pattern_id, pattern_record)
        logger.info("pattern_saved_local", pattern_id=pattern_id)
        return pattern_record

    async def load_pattern(self, pattern_id: str) -> Optional[Dict[str, Any]]:
        """Load LED pattern from Supabase or local storage."""
        # Try Supabase first
        if self.supabase:
            try:
                response = await asyncio.to_thread(
                    self.supabase.table('led_patterns')
                    .select('*')
                    .eq('pattern_id', pattern_id)
                    .execute
                )

                if response.data:
                    logger.info("pattern_loaded_supabase", pattern_id=pattern_id)
                    return response.data[0]

            except Exception as e:
                logger.error("supabase_load_failed", error=str(e), pattern_id=pattern_id)

        # Local fallback
        return await self._load_local(pattern_id)

    async def list_patterns(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all patterns, optionally filtered by user."""
        # Try Supabase first
        if self.supabase:
            try:
                query = self.supabase.table('led_patterns').select('*')
                if user_id:
                    query = query.eq('user_id', user_id)

                response = await asyncio.to_thread(query.execute)
                if response.data:
                    logger.info("patterns_listed_supabase", count=len(response.data))
                    return response.data

            except Exception as e:
                logger.error("supabase_list_failed", error=str(e))

        # Local fallback
        return await self._list_local()

    async def _save_local(self, pattern_id: str, data: Dict[str, Any]):
        """Save pattern to local JSON."""
        pattern_file = self.storage_path / f"{pattern_id}.json"

        async with aiofiles.open(pattern_file, 'w') as f:
            await f.write(json.dumps(data, indent=2))

    async def _load_local(self, pattern_id: str) -> Optional[Dict[str, Any]]:
        """Load pattern from local JSON."""
        pattern_file = self.storage_path / f"{pattern_id}.json"

        if not pattern_file.exists():
            return None

        try:
            async with aiofiles.open(pattern_file, 'r') as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logger.error("local_load_failed", pattern_id=pattern_id, error=str(e))
            return None

    async def _list_local(self) -> List[Dict[str, Any]]:
        """List all local patterns."""
        patterns = []

        for pattern_file in self.storage_path.glob("*.json"):
            try:
                async with aiofiles.open(pattern_file, 'r') as f:
                    content = await f.read()
                    patterns.append(json.loads(content))
            except Exception as e:
                logger.error("local_list_error", file=pattern_file.name, error=str(e))

        return patterns
```

---

## 📊 Implementation Checklist

### Phase 1: Core Streaming (Week 1)
- [ ] Add WebSocket endpoint `/ws/led` with LEDWebSocketManager
- [ ] Implement debounce queue for rapid toggles (100ms window)
- [ ] Add async pattern streaming with progress yields
- [ ] Test WebSocket with multiple concurrent clients

### Phase 2: Bus Integration (Week 1)
- [ ] Create `led_bus_integration.py` with event handlers
- [ ] Subscribe to Gunner calibration events
- [ ] Subscribe to LaunchBox game launch events
- [ ] Test flash patterns on Gunner calibration

### Phase 3: Persistence (Week 2)
- [ ] Implement Supabase pattern persistence
- [ ] Add local JSON fallback
- [ ] Create pattern save/load/list endpoints
- [ ] Test offline mode with fallback

### Phase 4: Testing (Week 2)
- [ ] Write comprehensive async test suite
- [ ] Test edge cases (rapid toggles, disconnects, invalid patterns)
- [ ] Achieve >85% code coverage
- [ ] Performance testing with 100+ LED patterns

---

## 📈 Success Metrics

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Test Coverage | >85% | ~65% | 🟡 In Progress |
| WebSocket Latency | <50ms | N/A | ❌ Not Implemented |
| Toggle Debounce | 100ms | N/A | ❌ Not Implemented |
| Pattern Sync | <200ms | N/A | ❌ Not Implemented |
| Bus Event Response | <50ms | N/A | ❌ Not Implemented |

---

## 🚀 Next Steps

1. **Immediate**: Add WebSocket endpoint with debounce queue
2. **This Week**: Implement bus event integration for Gunner
3. **Next Week**: Add Supabase persistence with fallback
4. **Following Week**: Comprehensive testing to >85% coverage

---

**Status**: Ready for implementation
**Branch**: `verify/p0-preflight`
**Estimated Completion**: 2-3 weeks
