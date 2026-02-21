# Gunner AI Integration Implementation Plan

**Date**: 2025-10-30
**Branch**: `verify/p0-preflight`
**Status**: 🔄 In Progress - Enhancement Phase
**Existing Coverage**: ~60% (needs boost to >85%)

---

## 📋 Executive Summary

Gunner light gun calibration service already has substantial infrastructure in place. This document outlines the enhancements needed to achieve full POR compliance with bus integration, adaptive modes, and comprehensive testing.

---

## ✅ Existing Implementation (Already Complete)

### Backend Infrastructure
1. **`backend/services/gunner/hardware.py`** (19,002 bytes)
   - Multi-gun registry with pluggable VID/PID detection
   - USB/pyusb async detection with fallback mocks
   - LRU cache for 90% performance improvement
   - Support for Sinden, Gun4IR, AIMTRAK, Ultimarc, Wiimote

2. **`backend/services/gunner/modes.py`** (17,261 bytes)
   - Retro shooter mode handlers
   - TimeCrisisHandler, HouseOfTheDeadHandler, PointBlankHandler
   - Feature-based adaptive calibration

3. **`backend/services/gunner_service.py`**
   - GunnerService orchestrator
   - CalibrationMode strategy pattern (Standard, Precision, Arcade, Kids)
   - Async streaming calibration (`calibrate_stream`)
   - Supabase integration
   - Structured logging with telemetry

4. **`backend/routers/gunner.py`**
   - GET `/gunner/devices` - List detected guns
   - GET `/gunner/gun-models` - Get gun registry
   - GET `/gunner/retro-modes` - List retro shooter modes
   - POST `/gunner/capture-point` - Capture calibration point
   - POST `/gunner/save-profile` - Save calibration profile
   - POST `/gunner/load-profile` - Load calibration profile
   - POST `/gunner/calibrate/stream` - **Streaming calibration (SSE)**
   - WebSocket `/gunner/ws` - Real-time calibration feedback

### Key Strengths
- ✅ Async-first architecture
- ✅ Pydantic validation
- ✅ Dependency injection via FastAPI Depends()
- ✅ Multiple calibration modes (Standard, Precision, Arcade, Kids)
- ✅ Hardware detection with mock fallback
- ✅ Supabase cloud sync
- ✅ Structured logging

---

## 🎯 Required Enhancements (POR Compliance)

### 1. Bus Event System for Cross-Panel Integration

**Status**: ❌ Not Implemented
**Priority**: P0
**Estimated Time**: 2-3 hours

#### Purpose
Enable gunner to communicate with other panels (LaunchBox, LED Blinky, ScoreKeeper) via event bus for coordinated actions.

#### Implementation

**Create `backend/services/bus_events.py`**:
```python
"""
Bus Event System for Cross-Panel Communication

Provides pub/sub event bus for coordinated actions across services:
- LaunchBox ROM validation on calibration complete
- LED Blinky target flashes during calibration
- ScoreKeeper accuracy multipliers
- Dewey AI explanations
"""

import asyncio
import structlog
from typing import Dict, List, Callable, Any, Optional
from datetime import datetime
from enum import Enum

logger = structlog.get_logger(__name__)


class EventType(Enum):
    """System-wide event types."""
    # Gunner events
    CALIB_STARTED = "gunner.calib_started"
    CALIB_POINT_CAPTURED = "gunner.calib_point_captured"
    CALIB_COMPLETED = "gunner.calib_completed"
    CALIB_FAILED = "gunner.calib_failed"
    GUN_DETECTED = "gunner.gun_detected"
    GUN_DISCONNECTED = "gunner.gun_disconnected"

    # LaunchBox events
    LAUNCHBOX_ROM_VALIDATE = "launchbox.rom_validate"
    LAUNCHBOX_LAUNCH = "launchbox.launch"

    # LED Blinky events
    LED_FLASH_TARGET = "led.flash_target"
    LED_FLASH_SUCCESS = "led.flash_success"
    LED_FLASH_ERROR = "led.flash_error"

    # ScoreKeeper events
    SCOREKEEPER_APPLY_MULTIPLIER = "scorekeeper.apply_multiplier"


class BusEvent:
    """Event payload with metadata."""
    def __init__(
        self,
        event_type: EventType,
        payload: Dict[str, Any],
        source: str,
        timestamp: Optional[datetime] = None
    ):
        self.event_type = event_type
        self.payload = payload
        self.source = source
        self.timestamp = timestamp or datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "payload": self.payload,
            "source": self.source,
            "timestamp": self.timestamp.isoformat()
        }


class EventBus:
    """Async event bus with pub/sub pattern."""

    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._event_log: List[BusEvent] = []
        self._max_log_size = 1000  # Rolling log

    def subscribe(self, event_type: EventType, handler: Callable):
        """Subscribe to event type with async handler."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        logger.info("event_bus_subscription", event_type=event_type.value, handler=handler.__name__)

    async def publish(self, event: BusEvent):
        """Publish event to all subscribers."""
        # Log event
        self._event_log.append(event)
        if len(self._event_log) > self._max_log_size:
            self._event_log.pop(0)

        logger.info("event_bus_publish",
                   event_type=event.event_type.value,
                   source=event.source,
                   payload=event.payload)

        # Notify subscribers
        handlers = self._subscribers.get(event.event_type, [])
        if handlers:
            # Run handlers concurrently
            tasks = [handler(event) for handler in handlers]
            await asyncio.gather(*tasks, return_exceptions=True)

    def get_recent_events(self, event_type: Optional[EventType] = None, limit: int = 50) -> List[BusEvent]:
        """Get recent events from log."""
        events = self._event_log[-limit:]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events


# Global event bus singleton
_event_bus = None

def get_event_bus() -> EventBus:
    """Get global event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


# Convenience functions
async def publish_event(event_type: EventType, payload: Dict[str, Any], source: str):
    """Publish event to bus."""
    event = BusEvent(event_type, payload, source)
    bus = get_event_bus()
    await bus.publish(event)


def subscribe_to_event(event_type: EventType, handler: Callable):
    """Subscribe to event type."""
    bus = get_event_bus()
    bus.subscribe(event_type, handler)
```

**Integrate into `gunner_service.py`**:
```python
from .bus_events import publish_event, EventType, subscribe_to_event

class GunnerService:
    async def calibrate_stream(self, data: CalibData) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream calibration progress with bus events."""
        # Publish calibration started
        await publish_event(
            EventType.CALIB_STARTED,
            {"device_id": data.device_id, "user_id": data.user_id, "points": len(data.points)},
            source="gunner_service"
        )

        try:
            for i, point in enumerate(data.points):
                # Flash LED target
                await publish_event(
                    EventType.LED_FLASH_TARGET,
                    {"x": point.x, "y": point.y, "index": i},
                    source="gunner_service"
                )

                # Process point...
                yield {"step": i + 1, "total": len(data.points), "progress": (i + 1) / len(data.points)}

                # Publish point captured
                await publish_event(
                    EventType.CALIB_POINT_CAPTURED,
                    {"index": i, "x": point.x, "y": point.y, "confidence": point.confidence},
                    source="gunner_service"
                )

            # Calibration complete
            result = await self._finalize_calibration(data)

            await publish_event(
                EventType.CALIB_COMPLETED,
                {"device_id": data.device_id, "accuracy": result["accuracy"], "mode": result["mode"]},
                source="gunner_service"
            )

            # Trigger LaunchBox ROM validation
            if data.game_type:
                await publish_event(
                    EventType.LAUNCHBOX_ROM_VALIDATE,
                    {"game_type": data.game_type, "calibration_id": data.device_id},
                    source="gunner_service"
                )

            yield {"status": "complete", **result}

        except Exception as e:
            await publish_event(
                EventType.CALIB_FAILED,
                {"device_id": data.device_id, "error": str(e)},
                source="gunner_service"
            )
            raise
```

---

### 2. Adaptive Calibration Modes (Kid/Pro)

**Status**: ⚠️ Partially Implemented (has Kids mode, needs enhancement)
**Priority**: P1
**Estimated Time**: 1-2 hours

#### Current State
- KidsMode exists in `gunner_service.py`
- Uses simplified 9-point calibration
- No dynamic point count adjustment

#### Enhancement Needed

**Update `CalibData` model**:
```python
class CalibData(BaseModel):
    """Calibration data with adaptive mode support."""
    device_id: int
    user_id: str
    game_type: Optional[str] = None
    points: List[CalibPoint]
    metadata: Optional[Dict[str, Any]] = None

    # Adaptive mode selection
    calib_mode: str = Field(default="auto", description="auto|kid|standard|pro")
    min_points: int = Field(default=5, ge=5, le=13, description="Minimum points for adaptive mode")

    @validator('calib_mode')
    def validate_mode(cls, v):
        """Validate calibration mode."""
        valid_modes = ["auto", "kid", "standard", "pro"]
        if v not in valid_modes:
            raise ValueError(f"Invalid mode: {v}. Must be one of {valid_modes}")
        return v

    @validator('points')
    def validate_points_count(cls, v, values):
        """Validate point count matches mode."""
        mode = values.get('calib_mode', 'standard')
        required_points = {
            "kid": 5,      # Corners + center
            "standard": 9, # 3x3 grid
            "pro": 13      # 3x3 + 4 mid-edges
        }

        if mode in required_points and len(v) < required_points[mode]:
            raise ValueError(f"{mode} mode requires at least {required_points[mode]} points")

        return v
```

**Add Adaptive Mode Handler**:
```python
class AdaptiveMode(CalibrationMode):
    """Auto-selects best mode based on user age, gun features, and game type."""

    async def process_calib(self, data: CalibData) -> Dict[str, Any]:
        """Auto-select mode and process calibration."""
        # Analyze user profile from Supabase
        user_age = await self._get_user_age(data.user_id)

        # Select mode
        if user_age and user_age < 13:
            selected_mode = "kid"
        elif data.game_type and "sniper" in data.game_type.lower():
            selected_mode = "pro"
        else:
            selected_mode = "standard"

        logger.info("adaptive_mode_selected",
                   user_age=user_age,
                   game_type=data.game_type,
                   selected_mode=selected_mode)

        # Delegate to appropriate mode
        mode_handlers = {
            "kid": KidsMode(),
            "standard": StandardMode(),
            "pro": PrecisionMode()
        }

        handler = mode_handlers[selected_mode]
        result = await handler.process_calib(data)
        result["auto_selected_mode"] = selected_mode
        return result

    async def _get_user_age(self, user_id: str) -> Optional[int]:
        """Fetch user age from Supabase profile."""
        # TODO: Implement Supabase query
        return None

    def get_mode_name(self) -> str:
        return "Adaptive"
```

---

### 3. Draft Persistence for Resume on Interrupt

**Status**: ❌ Not Implemented
**Priority**: P1
**Estimated Time**: 2 hours

#### Purpose
Save partial calibration progress to allow resume after interruption (disconnect, UI close, etc.).

#### Implementation

**Create `backend/services/gunner/drafts.py`**:
```python
"""Draft calibration persistence for resume functionality."""

import json
import asyncio
import aiofiles
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger(__name__)


class CalibrationDraft:
    """Persist partial calibration for resume."""

    def __init__(self, storage_path: Path = None):
        self.storage_path = storage_path or Path("/mnt/a/state/gunner/drafts")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=24)  # Drafts expire after 24 hours

    async def save_draft(self, user_id: str, device_id: int, data: Dict[str, Any]):
        """Save calibration draft."""
        draft_id = f"{user_id}_{device_id}"
        draft_file = self.storage_path / f"{draft_id}.json"

        draft_data = {
            "user_id": user_id,
            "device_id": device_id,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data
        }

        async with aiofiles.open(draft_file, 'w') as f:
            await f.write(json.dumps(draft_data, indent=2))

        logger.info("draft_saved", draft_id=draft_id, points_captured=len(data.get("points", [])))

    async def load_draft(self, user_id: str, device_id: int) -> Optional[Dict[str, Any]]:
        """Load calibration draft if exists and not expired."""
        draft_id = f"{user_id}_{device_id}"
        draft_file = self.storage_path / f"{draft_id}.json"

        if not draft_file.exists():
            return None

        try:
            async with aiofiles.open(draft_file, 'r') as f:
                content = await f.read()
                draft_data = json.loads(content)

            # Check TTL
            timestamp = datetime.fromisoformat(draft_data["timestamp"])
            if datetime.utcnow() - timestamp > self.ttl:
                await self.delete_draft(user_id, device_id)
                logger.info("draft_expired", draft_id=draft_id)
                return None

            logger.info("draft_loaded", draft_id=draft_id, age_minutes=(datetime.utcnow() - timestamp).seconds / 60)
            return draft_data["data"]

        except Exception as e:
            logger.error("draft_load_failed", draft_id=draft_id, error=str(e))
            return None

    async def delete_draft(self, user_id: str, device_id: int):
        """Delete calibration draft."""
        draft_id = f"{user_id}_{device_id}"
        draft_file = self.storage_path / f"{draft_id}.json"

        if draft_file.exists():
            draft_file.unlink()
            logger.info("draft_deleted", draft_id=draft_id)

    async def cleanup_expired(self):
        """Clean up expired drafts."""
        for draft_file in self.storage_path.glob("*.json"):
            try:
                async with aiofiles.open(draft_file, 'r') as f:
                    content = await f.read()
                    draft_data = json.loads(content)

                timestamp = datetime.fromisoformat(draft_data["timestamp"])
                if datetime.utcnow() - timestamp > self.ttl:
                    draft_file.unlink()
                    logger.info("draft_cleaned_up", file=draft_file.name)
            except Exception as e:
                logger.error("draft_cleanup_error", file=draft_file.name, error=str(e))
```

**Integrate into `gunner_service.py`**:
```python
from .gunner.drafts import CalibrationDraft

class GunnerService:
    def __init__(self, ...):
        self.draft_manager = CalibrationDraft()

    async def calibrate_stream(self, data: CalibData) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream calibration with draft persistence."""
        try:
            for i, point in enumerate(data.points):
                # Save draft after each point
                await self.draft_manager.save_draft(
                    data.user_id,
                    data.device_id,
                    {"points": data.points[:i+1], "mode": data.metadata.get("mode")}
                )

                yield {"step": i + 1, "draft_saved": True}

            # Delete draft on completion
            await self.draft_manager.delete_draft(data.user_id, data.device_id)

        except Exception as e:
            # Draft persists on error for resume
            logger.warning("calib_interrupted", error=str(e))
            raise


# Add resume endpoint in routers/gunner.py
@router.get("/resume/{user_id}/{device_id}")
async def resume_calibration(
    user_id: str,
    device_id: int,
    service: GunnerService = Depends(get_gunner_service)
):
    """Resume interrupted calibration from draft."""
    draft_data = await service.draft_manager.load_draft(user_id, device_id)

    if not draft_data:
        raise HTTPException(status_code=404, detail="No draft found")

    return {
        "status": "draft_found",
        "points_captured": len(draft_data.get("points", [])),
        "data": draft_data
    }
```

---

### 4. Self-Auditing Calibration Loop

**Status**: ❌ Not Implemented
**Priority**: P2
**Estimated Time**: 2 hours

#### Purpose
Re-test calibration points after save to detect hardware drift and prompt recalibration.

#### Implementation

```python
class GunnerService:
    async def audit_calibration(self, calib_id: str, tolerance: float = 0.05) -> Dict[str, Any]:
        """
        Re-test calibration points to detect drift.

        Args:
            calib_id: Calibration profile ID
            tolerance: Maximum allowed drift (0.05 = 5%)

        Returns:
            {"drift_detected": bool, "drift_percentage": float, "affected_points": List[int]}
        """
        # Load original calibration
        original_calib = await self.config_service.load_profile(calib_id)

        # Re-test points
        audit_results = []
        for i, point in enumerate(original_calib["points"]):
            # Capture point again
            captured = await self._capture_point(point["x"], point["y"])

            # Calculate drift
            drift_x = abs(captured["x"] - point["x"])
            drift_y = abs(captured["y"] - point["y"])
            drift = max(drift_x, drift_y)

            audit_results.append({
                "index": i,
                "original": point,
                "captured": captured,
                "drift": drift,
                "within_tolerance": drift <= tolerance
            })

        # Analyze results
        drifted_points = [r for r in audit_results if not r["within_tolerance"]]
        max_drift = max(r["drift"] for r in audit_results)

        drift_detected = len(drifted_points) > 0

        if drift_detected:
            logger.warning("calibration_drift_detected",
                          affected_points=len(drifted_points),
                          max_drift=max_drift)

        return {
            "drift_detected": drift_detected,
            "drift_percentage": max_drift * 100,
            "affected_points": [r["index"] for r in drifted_points],
            "audit_results": audit_results
        }


# Add audit endpoint
@router.post("/audit/{calib_id}")
async def audit_calibration(
    calib_id: str,
    tolerance: float = Query(0.05, ge=0.01, le=0.2),
    service: GunnerService = Depends(get_gunner_service)
):
    """Audit calibration for drift."""
    return await service.audit_calibration(calib_id, tolerance)
```

---

### 5. Multi-Gun Semaphore Limits

**Status**: ❌ Not Implemented
**Priority**: P1
**Estimated Time**: 1 hour

#### Purpose
Prevent hardware overload when calibrating multiple guns concurrently in family setups.

#### Implementation

```python
import asyncio

class GunnerService:
    def __init__(self, ...):
        self.calib_semaphore = asyncio.Semaphore(2)  # Max 2 concurrent calibrations

    async def calibrate_stream(self, data: CalibData) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream calibration with semaphore limit."""
        async with self.calib_semaphore:
            logger.info("calibration_started",
                       device_id=data.device_id,
                       active_calibrations=2 - self.calib_semaphore._value)

            # Existing calibration logic...
            async for update in self._run_calibration(data):
                yield update
```

---

### 6. Comprehensive Test Suite

**Status**: ⚠️ Partial (~60%, needs >85%)
**Priority**: P0
**Estimated Time**: 3-4 hours

#### Test Coverage Targets

**Create `backend/tests/test_gunner_integration.py`**:
```python
"""
Comprehensive async tests for Gunner calibration service.

Test Coverage:
- Hardware detection (USB, mocks, timeouts)
- Calibration streaming (progress, completion, errors)
- Adaptive modes (kid/standard/pro auto-selection)
- Draft persistence (save, load, resume, TTL)
- Self-auditing (drift detection, tolerance)
- Multi-gun semaphore (concurrent limits)
- Bus events (LaunchBox, LED Blinky integration)
- Edge cases (unplug, timeout, invalid data)

Target: >85% code coverage
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from backend.services.gunner_service import GunnerService, CalibData, CalibPoint
from backend.services.gunner.drafts import CalibrationDraft
from backend.services.bus_events import EventBus, EventType, publish_event


@pytest.fixture
def mock_detector():
    """Mock hardware detector."""
    detector = Mock()
    detector.get_devices = Mock(return_value=[
        {"id": 1, "name": "Sinden Light Gun", "vid": "0x16C0", "pid": "0x0F3B"}
    ])
    return detector


@pytest.fixture
async def gunner_service(mock_detector):
    """Create gunner service with mocks."""
    service = GunnerService(
        detector=mock_detector,
        config_service=Mock(),
        supabase_client=None
    )
    return service


@pytest.mark.asyncio
async def test_calibration_stream_success(gunner_service):
    """Test successful calibration stream."""
    calib_data = CalibData(
        device_id=1,
        user_id="test_user",
        points=[CalibPoint(x=i*0.1, y=i*0.1, confidence=0.95) for i in range(9)],
        calib_mode="standard"
    )

    updates = []
    async for update in gunner_service.calibrate_stream(calib_data):
        updates.append(update)

    assert len(updates) > 0
    assert updates[-1]["status"] == "complete"
    assert "accuracy" in updates[-1]


@pytest.mark.asyncio
async def test_calibration_unplug_mid_stream(gunner_service):
    """Test calibration handles mid-stream disconnect."""
    calib_data = CalibData(
        device_id=1,
        user_id="test_user",
        points=[CalibPoint(x=0.5, y=0.5, confidence=0.95) for _ in range(9)]
    )

    # Simulate unplug after 3 points
    with patch.object(gunner_service.detector, 'get_devices', side_effect=[
        [{"id": 1}],  # First 3 calls succeed
        [{"id": 1}],
        [{"id": 1}],
        []  # 4th call - device unplugged
    ]):
        with pytest.raises(Exception, match="device.*disconnect"):
            async for _ in gunner_service.calibrate_stream(calib_data):
                pass


@pytest.mark.asyncio
async def test_draft_persistence_resume(gunner_service):
    """Test draft save and resume."""
    user_id = "test_user"
    device_id = 1

    # Save draft
    await gunner_service.draft_manager.save_draft(
        user_id, device_id,
        {"points": [{"x": 0.5, "y": 0.5}], "mode": "standard"}
    )

    # Load draft
    draft = await gunner_service.draft_manager.load_draft(user_id, device_id)
    assert draft is not None
    assert len(draft["points"]) == 1


@pytest.mark.asyncio
async def test_multi_gun_semaphore_limit(gunner_service):
    """Test concurrent calibration respects semaphore limit."""
    async def calibrate_gun(gun_id):
        calib_data = CalibData(
            device_id=gun_id,
            user_id="test_user",
            points=[CalibPoint(x=0.5, y=0.5, confidence=0.95) for _ in range(9)]
        )
        async for _ in gunner_service.calibrate_stream(calib_data):
            await asyncio.sleep(0.1)  # Simulate work

    # Try to calibrate 4 guns concurrently (semaphore allows max 2)
    start = asyncio.get_event_loop().time()
    await asyncio.gather(*[calibrate_gun(i) for i in range(4)])
    duration = asyncio.get_event_loop().time() - start

    # Should take longer due to semaphore queuing
    assert duration > 0.2  # At least 2 batches


@pytest.mark.asyncio
async def test_bus_event_publish_on_complete(gunner_service):
    """Test bus events published on calibration complete."""
    event_bus = EventBus()
    events_received = []

    async def capture_event(event):
        events_received.append(event)

    event_bus.subscribe(EventType.CALIB_COMPLETED, capture_event)

    # Run calibration
    calib_data = CalibData(
        device_id=1,
        user_id="test_user",
        points=[CalibPoint(x=0.5, y=0.5, confidence=0.95) for _ in range(9)]
    )

    async for _ in gunner_service.calibrate_stream(calib_data):
        pass

    assert len(events_received) > 0
    assert events_received[0].event_type == EventType.CALIB_COMPLETED


@pytest.mark.asyncio
async def test_adaptive_mode_kid_selection(gunner_service):
    """Test adaptive mode selects kid mode for age < 13."""
    # Mock user age
    with patch.object(gunner_service, '_get_user_age', return_value=10):
        calib_data = CalibData(
            device_id=1,
            user_id="kid_user",
            points=[CalibPoint(x=0.5, y=0.5, confidence=0.95) for _ in range(5)],
            calib_mode="auto"
        )

        result = await gunner_service._select_mode(calib_data)
        assert result == "kid"


@pytest.mark.asyncio
async def test_self_audit_drift_detection(gunner_service):
    """Test self-auditing detects calibration drift."""
    calib_id = "test_calib"

    # Mock original calibration
    gunner_service.config_service.load_profile = AsyncMock(return_value={
        "points": [{"x": 0.5, "y": 0.5, "confidence": 0.95}] * 9
    })

    # Mock capture with drift
    gunner_service._capture_point = AsyncMock(return_value={
        "x": 0.55, "y": 0.55  # 5% drift
    })

    result = await gunner_service.audit_calibration(calib_id, tolerance=0.03)
    assert result["drift_detected"] is True
    assert len(result["affected_points"]) > 0
```

---

## 📊 Implementation Checklist

### Phase 1: Core Enhancements (Week 1)
- [ ] Create `backend/services/bus_events.py` with EventBus
- [ ] Integrate bus events into `gunner_service.py`
- [ ] Add adaptive mode selection (kid/standard/pro)
- [ ] Implement `CalibrationDraft` for resume functionality
- [ ] Add semaphore limits for multi-gun calibration

### Phase 2: Integration (Week 1-2)
- [ ] Subscribe LaunchBox to `LAUNCHBOX_ROM_VALIDATE` events
- [ ] Subscribe LED Blinky to `LED_FLASH_TARGET` events
- [ ] Subscribe ScoreKeeper to `CALIB_COMPLETED` events for multipliers
- [ ] Add resume endpoint `/gunner/resume/{user_id}/{device_id}`
- [ ] Add audit endpoint `/gunner/audit/{calib_id}`

### Phase 3: Testing (Week 2)
- [ ] Write `test_gunner_integration.py` with async tests
- [ ] Test edge cases (unplug, timeout, multi-gun)
- [ ] Achieve >85% code coverage
- [ ] Performance testing with 4+ concurrent guns
- [ ] Integration testing with LaunchBox + LED Blinky

### Phase 4: Documentation & Polish (Week 2)
- [ ] Update API documentation
- [ ] Add usage examples
- [ ] Create troubleshooting guide
- [ ] Performance benchmarks

---

## 📈 Success Metrics

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Test Coverage | >85% | ~60% | 🟡 In Progress |
| API Response Time | <100ms | ~80ms | ✅ Met |
| Concurrent Guns | 4+ | 2 | 🟡 Needs Semaphore |
| Draft Resume Success | >95% | N/A | ❌ Not Implemented |
| Bus Event Latency | <50ms | N/A | ❌ Not Implemented |

---

## 🔄 Next Steps

1. **Immediate**: Implement `bus_events.py` and integrate into gunner service
2. **This Week**: Add adaptive modes, draft persistence, semaphore limits
3. **Next Week**: Comprehensive testing to >85% coverage
4. **Following Week**: Integration testing with LaunchBox and LED Blinky

---

**Status**: Ready for implementation
**Branch**: `verify/p0-preflight`
**Assignee**: Development Team
**Estimated Completion**: 2-3 weeks
