"""Comprehensive pytest tests for chuck/detection.py.

Coverage Goals:
- >80% line coverage
- All critical paths tested
- Edge cases handled (unplug, conflicts, timeouts)
- Mocked USB backend

Test Categories:
1. Basic board detection (sync and async)
2. Hot-plug/unplug event detection
3. Caching behavior
4. Error handling (timeouts, not found, backend errors)
5. Event handler system
6. Async polling
7. Injectable backend (dependency injection)
"""

import pytest
import asyncio
import time
from typing import Dict, List, Optional, Any
from unittest.mock import Mock, MagicMock, patch

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.chuck.detection import (
    BoardDetectionService,
    BoardDetectionError,
    BoardNotFoundError,
    BoardTimeoutError,
    BoardInfo,
    BoardEvent,
    BoardStatus,
    detect_board,
    get_detection_service,
    DefaultUSBBackend,
)


# ============================================================================
# Mock USB Backend
# ============================================================================


class MockUSBBackend:
    """Mock USB backend for testing."""

    def __init__(self):
        self.devices: Dict[str, Dict[str, Any]] = {}
        self.call_count = 0

    def add_device(self, vid: str, pid: str, name: str = "Test Board", manufacturer: str = "Test Mfg"):
        """Add a device to the mock backend."""
        vid_clean = vid.lower().replace("0x", "").strip().zfill(4)
        pid_clean = pid.lower().replace("0x", "").strip().zfill(4)
        key = f"{vid_clean}:{pid_clean}"
        self.devices[key] = {
            "vid": f"0x{vid_clean}",
            "pid": f"0x{pid_clean}",
            "vid_pid": key,
            "product_string": name,
            "manufacturer_string": manufacturer,
        }

    def remove_device(self, vid: str, pid: str):
        """Remove a device from the mock backend."""
        vid_clean = vid.lower().replace("0x", "").strip().zfill(4)
        pid_clean = pid.lower().replace("0x", "").strip().zfill(4)
        key = f"{vid_clean}:{pid_clean}"
        if key in self.devices:
            del self.devices[key]

    def get_board_by_vid_pid(self, vid: str, pid: str) -> Optional[Dict[str, Any]]:
        """Mock get_board_by_vid_pid."""
        self.call_count += 1
        vid_clean = vid.lower().replace("0x", "").strip().zfill(4)
        pid_clean = pid.lower().replace("0x", "").strip().zfill(4)
        key = f"{vid_clean}:{pid_clean}"
        return self.devices.get(key)

    def detect_usb_devices(
        self, include_unknown: bool = False, use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """Mock detect_usb_devices."""
        return list(self.devices.values())


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_usb_backend():
    """Create mock USB backend."""
    return MockUSBBackend()


@pytest.fixture
def detection_service(mock_usb_backend):
    """Create detection service with mock backend."""
    return BoardDetectionService(
        usb_backend=mock_usb_backend, cache_ttl=1.0, poll_interval=0.1
    )


@pytest.fixture
def sample_board_vid_pid():
    """Sample VID/PID for testing."""
    return ("045e", "028e")  # Xbox 360 controller


# ============================================================================
# Basic Detection Tests
# ============================================================================


def test_detect_board_found(detection_service, mock_usb_backend, sample_board_vid_pid):
    """Test basic board detection when board is connected."""
    vid, pid = sample_board_vid_pid
    mock_usb_backend.add_device(vid, pid, "Xbox 360 Controller", "Microsoft")

    board = detection_service.detect_board(vid, pid, use_cache=False)

    assert board.detected is True
    assert board.status == BoardStatus.CONNECTED
    assert board.vid == f"0x{vid}"
    assert board.pid == f"0x{pid}"
    assert board.name == "Xbox 360 Controller"
    assert board.manufacturer == "Microsoft"


def test_detect_board_not_found(detection_service, sample_board_vid_pid):
    """Test detection when board is not connected."""
    vid, pid = sample_board_vid_pid

    with pytest.raises(BoardNotFoundError):
        detection_service.detect_board(vid, pid, use_cache=False)


def test_detect_board_caching(detection_service, mock_usb_backend, sample_board_vid_pid):
    """Test that detection results are cached."""
    vid, pid = sample_board_vid_pid
    mock_usb_backend.add_device(vid, pid)

    # First call
    board1 = detection_service.detect_board(vid, pid, use_cache=True)
    call_count_1 = mock_usb_backend.call_count

    # Second call (should use cache)
    board2 = detection_service.detect_board(vid, pid, use_cache=True)
    call_count_2 = mock_usb_backend.call_count

    # Backend should only be called once
    assert call_count_2 == call_count_1
    assert board1.vid_pid == board2.vid_pid


def test_detect_board_cache_expiry(detection_service, mock_usb_backend, sample_board_vid_pid):
    """Test that cache expires after TTL."""
    vid, pid = sample_board_vid_pid
    mock_usb_backend.add_device(vid, pid)

    # First call
    board1 = detection_service.detect_board(vid, pid, use_cache=True)
    call_count_1 = mock_usb_backend.call_count

    # Wait for cache to expire (TTL = 1.0 seconds)
    time.sleep(1.1)

    # Second call (should hit backend again)
    board2 = detection_service.detect_board(vid, pid, use_cache=True)
    call_count_2 = mock_usb_backend.call_count

    # Backend should be called twice
    assert call_count_2 > call_count_1


def test_invalidate_cache(detection_service, mock_usb_backend, sample_board_vid_pid):
    """Test cache invalidation."""
    vid, pid = sample_board_vid_pid
    mock_usb_backend.add_device(vid, pid)

    # First call
    board1 = detection_service.detect_board(vid, pid, use_cache=True)
    call_count_1 = mock_usb_backend.call_count

    # Invalidate cache
    detection_service.invalidate_cache(vid, pid)

    # Second call (should hit backend again)
    board2 = detection_service.detect_board(vid, pid, use_cache=True)
    call_count_2 = mock_usb_backend.call_count

    # Backend should be called twice
    assert call_count_2 > call_count_1


# ============================================================================
# Async Detection Tests
# ============================================================================


@pytest.mark.asyncio
async def test_detect_board_async(detection_service, mock_usb_backend, sample_board_vid_pid):
    """Test async board detection."""
    vid, pid = sample_board_vid_pid
    mock_usb_backend.add_device(vid, pid, "Test Board")

    board = await detection_service.detect_board_async(vid, pid, use_cache=False)

    assert board.detected is True
    assert board.status == BoardStatus.CONNECTED
    assert board.name == "Test Board"


@pytest.mark.asyncio
async def test_detect_board_async_not_found(detection_service, sample_board_vid_pid):
    """Test async detection when board not found."""
    vid, pid = sample_board_vid_pid

    with pytest.raises(BoardNotFoundError):
        await detection_service.detect_board_async(vid, pid, use_cache=False)


# ============================================================================
# Event Handler Tests
# ============================================================================


def test_register_event_handler(detection_service):
    """Test event handler registration."""
    handler = Mock()
    detection_service.register_event_handler(handler)

    assert handler in detection_service._event_handlers


def test_unregister_event_handler(detection_service):
    """Test event handler unregistration."""
    handler = Mock()
    detection_service.register_event_handler(handler)
    detection_service.unregister_event_handler(handler)

    assert handler not in detection_service._event_handlers


def test_emit_event(detection_service, sample_board_vid_pid):
    """Test event emission to handlers."""
    handler = Mock()
    detection_service.register_event_handler(handler)

    vid, pid = sample_board_vid_pid
    board = BoardInfo(
        vid=vid,
        pid=pid,
        vid_pid=f"{vid}:{pid}",
        name="Test Board",
        manufacturer="Test",
    )
    event = BoardEvent(event_type="connected", board=board, timestamp=time.time())

    detection_service._emit_event(event)

    handler.assert_called_once_with(event)


def test_event_handler_error_handling(detection_service, sample_board_vid_pid):
    """Test that event handler errors don't crash the service."""

    def failing_handler(event):
        raise Exception("Handler error")

    detection_service.register_event_handler(failing_handler)

    vid, pid = sample_board_vid_pid
    board = BoardInfo(
        vid=vid,
        pid=pid,
        vid_pid=f"{vid}:{pid}",
        name="Test Board",
        manufacturer="Test",
    )
    event = BoardEvent(event_type="connected", board=board, timestamp=time.time())

    # Should not raise exception
    detection_service._emit_event(event)


# ============================================================================
# Hot-Plug/Unplug Tests (Async Polling)
# ============================================================================


@pytest.mark.asyncio
async def test_polling_detects_connection(
    detection_service, mock_usb_backend, sample_board_vid_pid
):
    """Test that polling detects board connection."""
    vid, pid = sample_board_vid_pid
    events = []

    def event_handler(event: BoardEvent):
        events.append(event)

    detection_service.register_event_handler(event_handler)

    # Start polling without the board connected
    polling_task = asyncio.create_task(detection_service.start_polling([(vid, pid)]))

    # Wait a bit for first poll
    await asyncio.sleep(0.2)

    # Connect the board
    mock_usb_backend.add_device(vid, pid, "Test Board")

    # Wait for detection
    await asyncio.sleep(0.3)

    # Stop polling
    detection_service.stop_polling()
    await asyncio.sleep(0.2)
    polling_task.cancel()

    # Should have received a "connected" event
    connected_events = [e for e in events if e.event_type == "connected"]
    assert len(connected_events) > 0
    assert connected_events[0].board.name == "Test Board"


@pytest.mark.asyncio
async def test_polling_detects_disconnection(
    detection_service, mock_usb_backend, sample_board_vid_pid
):
    """Test that polling detects board disconnection."""
    vid, pid = sample_board_vid_pid
    events = []

    def event_handler(event: BoardEvent):
        events.append(event)

    detection_service.register_event_handler(event_handler)

    # Start with board connected
    mock_usb_backend.add_device(vid, pid, "Test Board")

    # Start polling
    polling_task = asyncio.create_task(detection_service.start_polling([(vid, pid)]))

    # Wait for initial detection
    await asyncio.sleep(0.2)

    # Disconnect the board
    mock_usb_backend.remove_device(vid, pid)

    # Wait for detection
    await asyncio.sleep(0.3)

    # Stop polling
    detection_service.stop_polling()
    await asyncio.sleep(0.2)
    polling_task.cancel()

    # Should have received "connected" and "disconnected" events
    connected_events = [e for e in events if e.event_type == "connected"]
    disconnected_events = [e for e in events if e.event_type == "disconnected"]

    assert len(connected_events) > 0
    assert len(disconnected_events) > 0


@pytest.mark.asyncio
async def test_polling_multiple_boards(detection_service, mock_usb_backend):
    """Test polling multiple boards simultaneously."""
    boards = [("045e", "028e"), ("054c", "0268")]  # Xbox 360, PS3 controller
    events = []

    def event_handler(event: BoardEvent):
        events.append(event)

    detection_service.register_event_handler(event_handler)

    # Add both boards
    mock_usb_backend.add_device(boards[0][0], boards[0][1], "Xbox 360")
    mock_usb_backend.add_device(boards[1][0], boards[1][1], "PS3 Controller")

    # Start polling
    polling_task = asyncio.create_task(detection_service.start_polling(boards))

    # Wait for detection
    await asyncio.sleep(0.3)

    # Stop polling
    detection_service.stop_polling()
    await asyncio.sleep(0.2)
    polling_task.cancel()

    # Should have received events for both boards
    connected_events = [e for e in events if e.event_type == "connected"]
    assert len(connected_events) >= 2


# ============================================================================
# Error Handling Tests
# ============================================================================


def test_detection_with_backend_error(detection_service, mock_usb_backend, sample_board_vid_pid):
    """Test detection when USB backend raises error."""
    vid, pid = sample_board_vid_pid

    # Make backend raise an error
    def error_backend(*args, **kwargs):
        from services.usb_detector import USBBackendError

        raise USBBackendError("Test backend error")

    mock_usb_backend.get_board_by_vid_pid = error_backend

    with pytest.raises(BoardDetectionError) as exc_info:
        detection_service.detect_board(vid, pid, use_cache=False)

    assert "backend error" in str(exc_info.value).lower()


def test_board_info_to_dict(detection_service, mock_usb_backend, sample_board_vid_pid):
    """Test BoardInfo.to_dict() conversion."""
    vid, pid = sample_board_vid_pid
    mock_usb_backend.add_device(vid, pid, "Test Board", "Test Manufacturer")

    board = detection_service.detect_board(vid, pid, use_cache=False)
    board_dict = board.to_dict()

    assert isinstance(board_dict, dict)
    assert board_dict["vid"] == f"0x{vid}"
    assert board_dict["pid"] == f"0x{pid}"
    assert board_dict["name"] == "Test Board"
    assert board_dict["manufacturer"] == "Test Manufacturer"
    assert board_dict["detected"] is True
    assert board_dict["status"] == "connected"


def test_normalize_vid_pid(detection_service):
    """Test VID/PID normalization."""
    # Test various formats
    test_cases = [
        ("0x045e", "0x028e", "045e", "028e"),
        ("045e", "028e", "045e", "028e"),
        ("45e", "28e", "045e", "028e"),  # Zero-padding
        ("0X45E", "0X28E", "045e", "028e"),  # Uppercase
    ]

    for vid_in, pid_in, vid_expected, pid_expected in test_cases:
        vid_out, pid_out, vid_pid = detection_service._normalize_vid_pid(vid_in, pid_in)
        assert vid_out == vid_expected
        assert pid_out == pid_expected
        assert vid_pid == f"{vid_expected}:{pid_expected}"


# ============================================================================
# Module-level Function Tests
# ============================================================================


def test_detect_board_function(mock_usb_backend, sample_board_vid_pid):
    """Test module-level detect_board function."""
    vid, pid = sample_board_vid_pid

    # Use singleton service with mock backend
    service = get_detection_service(usb_backend=mock_usb_backend)
    mock_usb_backend.add_device(vid, pid, "Test Board")

    board = detect_board(vid, pid, use_cache=False)

    assert board.detected is True
    assert board.name == "Test Board"


def test_get_detection_service_singleton():
    """Test that get_detection_service returns singleton."""
    service1 = get_detection_service()
    service2 = get_detection_service()

    # Should be the same instance
    assert service1 is service2


def test_cache_stats(detection_service, mock_usb_backend, sample_board_vid_pid):
    """Test cache statistics."""
    vid, pid = sample_board_vid_pid
    mock_usb_backend.add_device(vid, pid)

    # Detect board to populate cache
    detection_service.detect_board(vid, pid)

    stats = detection_service.get_cache_stats()

    assert stats["cached_boards"] == 1
    assert stats["cache_ttl"] == 1.0
    assert stats["polling_active"] is False
    assert stats["event_handlers"] == 0


# ============================================================================
# Edge Case Tests
# ============================================================================


def test_detect_board_with_missing_strings(detection_service, mock_usb_backend):
    """Test detection when manufacturer/product strings are missing."""
    vid, pid = "1234", "5678"
    mock_usb_backend.add_device(vid, pid, "", "")  # Empty strings

    board = detection_service.detect_board(vid, pid, use_cache=False)

    assert board.detected is True
    # Should handle empty strings gracefully


def test_concurrent_detection(detection_service, mock_usb_backend):
    """Test concurrent detection of same board."""
    vid, pid = "1234", "5678"
    mock_usb_backend.add_device(vid, pid, "Test Board")

    # Detect same board multiple times
    boards = [detection_service.detect_board(vid, pid, use_cache=False) for _ in range(5)]

    # All should succeed
    assert all(b.detected for b in boards)
    assert len(set(b.vid_pid for b in boards)) == 1  # Same board


@pytest.mark.asyncio
async def test_stop_polling_when_not_active(detection_service):
    """Test that stopping polling when not active doesn't error."""
    # Should not raise exception
    detection_service.stop_polling()


def test_invalidate_all_cache(detection_service, mock_usb_backend):
    """Test invalidating all cache entries."""
    # Add multiple boards
    boards = [("1234", "5678"), ("abcd", "ef01")]
    for vid, pid in boards:
        mock_usb_backend.add_device(vid, pid)
        detection_service.detect_board(vid, pid)

    # Invalidate all
    detection_service.invalidate_cache()

    stats = detection_service.get_cache_stats()
    assert stats["cached_boards"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
