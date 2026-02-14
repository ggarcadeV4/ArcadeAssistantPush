"""Arcade Controller Board Detection Service

Async detection service for arcade controller boards with hot-plug/unplug support.
Provides injectable backend for testing and event-driven architecture.

Features:
- Async polling with configurable intervals
- Hot-plug/unplug event detection
- Injectable backend for testing (dependency injection)
- Caching with TTL
- Multiple board support with conflict detection
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol
from functools import lru_cache

from ..usb_detector import (
    USBBackendError,
    USBDetectionError,
    USBPermissionError,
    get_board_by_vid_pid,
    detect_usb_devices,
    invalidate_cache as invalidate_usb_cache
)

logger = logging.getLogger(__name__)

# Detection configuration
DETECTION_CACHE_TTL = 3.0  # seconds
POLL_INTERVAL = 1.0  # seconds for async polling
DETECTION_TIMEOUT = 5.0  # seconds


class BoardStatus(Enum):
    """Board connection status."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    TIMEOUT = "timeout"
    ERROR = "error"


class BoardDetectionError(Exception):
    """Base exception for board detection errors."""
    pass


class BoardNotFoundError(BoardDetectionError):
    """Board not found or not connected."""
    pass


class BoardTimeoutError(BoardDetectionError):
    """Detection timeout exceeded."""
    pass


@dataclass
class BoardInfo:
    """Detected board information."""
    vid: str
    pid: str
    vid_pid: str
    name: str
    manufacturer: str
    product_string: Optional[str] = None
    manufacturer_string: Optional[str] = None
    detected: bool = True
    status: BoardStatus = BoardStatus.CONNECTED
    detection_time: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "vid": self.vid,
            "pid": self.pid,
            "vid_pid": self.vid_pid,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "product_string": self.product_string,
            "manufacturer_string": self.manufacturer_string,
            "detected": self.detected,
            "status": self.status.value,
            "detection_time": self.detection_time,
            "error": self.error,
        }


@dataclass
class BoardEvent:
    """Board connection event."""
    event_type: str  # "connected", "disconnected", "error"
    board: BoardInfo
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event for streaming endpoints."""
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "board": self.board.to_dict(),
        }


# Protocol for injectable USB backend
class USBBackendProtocol(Protocol):
    """Protocol for USB backend dependency injection."""

    def get_board_by_vid_pid(self, vid: str, pid: str) -> Optional[Dict[str, Any]]:
        """Get board by VID/PID."""
        ...

    def detect_usb_devices(
        self, include_unknown: bool = False, use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """Detect all USB devices."""
        ...


class DefaultUSBBackend:
    """Default USB backend using usb_detector module."""

    def get_board_by_vid_pid(self, vid: str, pid: str) -> Optional[Dict[str, Any]]:
        """Get board by VID/PID."""
        return get_board_by_vid_pid(vid, pid)

    def detect_usb_devices(
        self, include_unknown: bool = False, use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """Detect all USB devices."""
        return detect_usb_devices(include_unknown=include_unknown, use_cache=use_cache)


class BoardDetectionService:
    """Async board detection service with event support.

    Provides injectable backend for testing and hot-plug/unplug detection.
    """

    def __init__(
        self,
        usb_backend: Optional[USBBackendProtocol] = None,
        cache_ttl: float = DETECTION_CACHE_TTL,
        poll_interval: float = POLL_INTERVAL,
    ):
        """Initialize detection service.

        Args:
            usb_backend: Injectable USB backend (defaults to DefaultUSBBackend)
            cache_ttl: Cache time-to-live in seconds
            poll_interval: Polling interval for async detection
        """
        self.usb_backend = usb_backend or DefaultUSBBackend()
        self.cache_ttl = cache_ttl
        self.poll_interval = poll_interval

        # Cache
        self._cache: Dict[str, tuple[float, BoardInfo]] = {}

        # Event handlers
        self._event_handlers: List[Callable[[BoardEvent], None]] = []

        # Polling state
        self._polling_task: Optional[asyncio.Task] = None
        self._polling_active = False
        self._last_detected_boards: Dict[str, BoardInfo] = {}

    def register_event_handler(self, handler: Callable[[BoardEvent], None]) -> None:
        """Register event handler for board connect/disconnect events.

        Args:
            handler: Callback function that receives BoardEvent
        """
        self._event_handlers.append(handler)
        handler_name = getattr(handler, "__name__", repr(handler))
        logger.debug(f"Registered event handler: {handler_name}")

    def unregister_event_handler(self, handler: Callable[[BoardEvent], None]) -> None:
        """Unregister event handler.

        Args:
            handler: Callback function to remove
        """
        if handler in self._event_handlers:
            self._event_handlers.remove(handler)
            handler_name = getattr(handler, "__name__", repr(handler))
            logger.debug(f"Unregistered event handler: {handler_name}")

    def _emit_event(self, event: BoardEvent) -> None:
        """Emit event to all registered handlers.

        Args:
            event: BoardEvent to emit
        """
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as e:
                handler_name = getattr(handler, "__name__", repr(handler))
                logger.error(f"Event handler {handler_name} failed: {e}")

    def _normalize_vid_pid(self, vid: str, pid: str) -> tuple[str, str, str]:
        """Normalize VID/PID format.

        Args:
            vid: Vendor ID (hex string)
            pid: Product ID (hex string)

        Returns:
            Tuple of (normalized_vid, normalized_pid, vid_pid_key)
        """
        vid_clean = vid.lower().replace("0x", "").strip().zfill(4)
        pid_clean = pid.lower().replace("0x", "").strip().zfill(4)
        vid_pid_key = f"{vid_clean}:{pid_clean}"
        return vid_clean, pid_clean, vid_pid_key

    def _build_board_info(
        self,
        vid: str,
        pid: str,
        device_data: Optional[Dict[str, Any]] = None,
        detected: bool = True,
        status: BoardStatus = BoardStatus.CONNECTED,
        error: Optional[str] = None,
    ) -> BoardInfo:
        """Build BoardInfo from device data.

        Args:
            vid: Vendor ID
            pid: Product ID
            device_data: Device data from USB detection
            detected: Whether board is detected
            status: Board status
            error: Error message if any

        Returns:
            BoardInfo instance
        """
        vid_clean, pid_clean, vid_pid_key = self._normalize_vid_pid(vid, pid)

        if device_data:
            return BoardInfo(
                vid=f"0x{vid_clean}",
                pid=f"0x{pid_clean}",
                vid_pid=vid_pid_key,
                name=device_data.get("product_string", "Unknown Board"),
                manufacturer=device_data.get("manufacturer_string", "Unknown"),
                product_string=device_data.get("product_string"),
                manufacturer_string=device_data.get("manufacturer_string"),
                detected=detected,
                status=status,
                detection_time=time.time(),
                error=error,
            )
        else:
            return BoardInfo(
                vid=f"0x{vid_clean}",
                pid=f"0x{pid_clean}",
                vid_pid=vid_pid_key,
                name="Unknown Board",
                manufacturer="Unknown",
                detected=detected,
                status=status,
                detection_time=time.time(),
                error=error,
            )

    def detect_board(
        self,
        vid: str,
        pid: str,
        use_cache: bool = True,
        timeout: float = DETECTION_TIMEOUT,
    ) -> BoardInfo:
        """Detect board by VID/PID synchronously.

        Args:
            vid: Vendor ID (hex string)
            pid: Product ID (hex string)
            use_cache: Use cached result if available
            timeout: Detection timeout in seconds

        Returns:
            BoardInfo instance

        Raises:
            BoardNotFoundError: If board not found
            BoardTimeoutError: If detection times out
            BoardDetectionError: For other detection errors
        """
        vid_clean, pid_clean, vid_pid_key = self._normalize_vid_pid(vid, pid)

        # Check cache
        if use_cache and vid_pid_key in self._cache:
            cache_time, cached_board = self._cache[vid_pid_key]
            if time.time() - cache_time < self.cache_ttl:
                logger.debug(f"Using cached board info for {vid_pid_key}")
                return cached_board

        start_time = time.time()

        try:
            # Attempt detection
            device_data = self.usb_backend.get_board_by_vid_pid(vid_clean, pid_clean)

            if device_data:
                board = self._build_board_info(
                    vid_clean, pid_clean, device_data, detected=True
                )
                self._cache[vid_pid_key] = (time.time(), board)
                logger.info(f"Board detected: {vid_pid_key} - {board.name}")
                return board
            else:
                # Board not found
                board = self._build_board_info(
                    vid_clean,
                    pid_clean,
                    None,
                    detected=False,
                    status=BoardStatus.DISCONNECTED,
                    error="Board not connected",
                )
                self._cache[vid_pid_key] = (time.time(), board)
                raise BoardNotFoundError(f"Board {vid_pid_key} not found")

        except BoardNotFoundError:
            # Re-raise BoardNotFoundError without wrapping
            raise

        except USBBackendError as e:
            error_msg = f"USB backend error: {str(e)}"
            board = self._build_board_info(
                vid_clean,
                pid_clean,
                None,
                detected=False,
                status=BoardStatus.ERROR,
                error=error_msg,
            )
            self._cache[vid_pid_key] = (time.time(), board)
            raise BoardDetectionError(error_msg) from e

        except USBPermissionError as e:
            error_msg = f"USB permission error: {str(e)}"
            board = self._build_board_info(
                vid_clean,
                pid_clean,
                None,
                detected=False,
                status=BoardStatus.ERROR,
                error=error_msg,
            )
            self._cache[vid_pid_key] = (time.time(), board)
            raise BoardDetectionError(error_msg) from e

        except Exception as e:
            if time.time() - start_time > timeout:
                error_msg = f"Detection timeout after {timeout}s"
                board = self._build_board_info(
                    vid_clean,
                    pid_clean,
                    None,
                    detected=False,
                    status=BoardStatus.TIMEOUT,
                    error=error_msg,
                )
                raise BoardTimeoutError(error_msg) from e
            else:
                error_msg = f"Detection failed: {str(e)}"
                board = self._build_board_info(
                    vid_clean,
                    pid_clean,
                    None,
                    detected=False,
                    status=BoardStatus.ERROR,
                    error=error_msg,
                )
                raise BoardDetectionError(error_msg) from e

    async def detect_board_async(
        self,
        vid: str,
        pid: str,
        use_cache: bool = True,
        timeout: float = DETECTION_TIMEOUT,
    ) -> BoardInfo:
        """Detect board by VID/PID asynchronously.

        Args:
            vid: Vendor ID (hex string)
            pid: Product ID (hex string)
            use_cache: Use cached result if available
            timeout: Detection timeout in seconds

        Returns:
            BoardInfo instance

        Raises:
            BoardNotFoundError: If board not found
            BoardTimeoutError: If detection times out
            BoardDetectionError: For other detection errors
        """
        # Run sync detection in executor to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.detect_board, vid, pid, use_cache, timeout
        )

    async def start_polling(self, boards: List[tuple[str, str]]) -> None:
        """Start async polling for board connect/disconnect events.

        Args:
            boards: List of (vid, pid) tuples to monitor
        """
        if self._polling_active:
            logger.warning("Polling already active")
            return

        self._polling_active = True
        self._last_detected_boards = {}

        logger.info(f"Starting board polling for {len(boards)} boards")

        while self._polling_active:
            try:
                for vid, pid in boards:
                    vid_clean, pid_clean, vid_pid_key = self._normalize_vid_pid(
                        vid, pid
                    )

                    try:
                        # Detect board
                        board = await self.detect_board_async(
                            vid_clean, pid_clean, use_cache=False
                        )

                        # Check if this is a new connection
                        if vid_pid_key not in self._last_detected_boards:
                            event = BoardEvent(
                                event_type="connected",
                                board=board,
                                timestamp=time.time(),
                            )
                            self._emit_event(event)
                            logger.info(f"Board connected: {vid_pid_key}")

                        self._last_detected_boards[vid_pid_key] = board

                    except BoardNotFoundError:
                        # Check if this is a disconnection
                        if vid_pid_key in self._last_detected_boards:
                            old_board = self._last_detected_boards[vid_pid_key]
                            disconnected_board = self._build_board_info(
                                vid_clean,
                                pid_clean,
                                None,
                                detected=False,
                                status=BoardStatus.DISCONNECTED,
                            )
                            event = BoardEvent(
                                event_type="disconnected",
                                board=disconnected_board,
                                timestamp=time.time(),
                            )
                            self._emit_event(event)
                            logger.info(f"Board disconnected: {vid_pid_key}")
                            del self._last_detected_boards[vid_pid_key]

                    except BoardDetectionError as e:
                        # Emit error event
                        error_board = self._build_board_info(
                            vid_clean,
                            pid_clean,
                            None,
                            detected=False,
                            status=BoardStatus.ERROR,
                            error=str(e),
                        )
                        event = BoardEvent(
                            event_type="error", board=error_board, timestamp=time.time()
                        )
                        self._emit_event(event)
                        logger.error(f"Board detection error for {vid_pid_key}: {e}")

                # Wait before next poll
                await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                logger.info("Polling cancelled")
                break
            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(self.poll_interval)

        self._polling_active = False
        logger.info("Board polling stopped")

    def stop_polling(self) -> None:
        """Stop async polling."""
        if self._polling_active:
            self._polling_active = False
            logger.info("Stopping board polling")

    def invalidate_cache(self, vid: Optional[str] = None, pid: Optional[str] = None) -> None:
        """Invalidate cache for specific board or all boards.

        Args:
            vid: Vendor ID (optional, invalidates all if None)
            pid: Product ID (optional, invalidates all if None)
        """
        if vid and pid:
            vid_clean, pid_clean, vid_pid_key = self._normalize_vid_pid(vid, pid)
            if vid_pid_key in self._cache:
                del self._cache[vid_pid_key]
                logger.debug(f"Invalidated cache for {vid_pid_key}")
        else:
            self._cache.clear()
            invalidate_usb_cache()
            logger.debug("Invalidated all board detection cache")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        return {
            "cached_boards": len(self._cache),
            "cache_ttl": self.cache_ttl,
            "polling_active": self._polling_active,
            "event_handlers": len(self._event_handlers),
        }


# Module-level singleton instance
_detection_service: Optional[BoardDetectionService] = None


def get_detection_service(
    usb_backend: Optional[USBBackendProtocol] = None,
    cache_ttl: float = DETECTION_CACHE_TTL,
) -> BoardDetectionService:
    """Get or create singleton detection service instance.

    Args:
        usb_backend: Injectable USB backend (only used on first call)
        cache_ttl: Cache TTL (only used on first call)

    Returns:
        BoardDetectionService instance
    """
    global _detection_service

    if _detection_service is None:
        _detection_service = BoardDetectionService(
            usb_backend=usb_backend, cache_ttl=cache_ttl
        )
        logger.info("Created board detection service")

    return _detection_service


def detect_board(
    vid: str,
    pid: str,
    use_cache: bool = True,
    timeout: float = DETECTION_TIMEOUT,
) -> BoardInfo:
    """Convenience function to detect board using singleton service.

    Args:
        vid: Vendor ID (hex string)
        pid: Product ID (hex string)
        use_cache: Use cached result if available
        timeout: Detection timeout in seconds

    Returns:
        BoardInfo instance

    Raises:
        BoardNotFoundError: If board not found
        BoardTimeoutError: If detection times out
        BoardDetectionError: For other detection errors
    """
    service = get_detection_service()
    return service.detect_board(vid, pid, use_cache=use_cache, timeout=timeout)
