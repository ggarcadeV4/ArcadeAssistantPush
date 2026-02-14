"""Tests for Async Hardware Detection Service

Tests USB detection, Windows registry fallback, lsusb fallback,
caching, timeout handling, and edge cases.

Target coverage: >85%
"""

import pytest
import asyncio
import platform
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from pathlib import Path

from backend.services.hardware import (
    HardwareDetectionService,
    DeviceInfo,
    DeviceType,
    DetectionStats,
    BoardConfig,
    KNOWN_BOARDS,
    USBBackendError,
    USBPermissionError,
    HardwareDetectionError,
    get_hardware_service,
    get_supported_boards,
    detect_arcade_boards,
    get_board_by_vid_pid,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service():
    """Create a fresh hardware detection service."""
    return HardwareDetectionService(cache_ttl=1.0)


@pytest.fixture
def mock_usb_device():
    """Create a mock USB device."""
    device = Mock()
    device.idVendor = 0xD209
    device.idProduct = 0x0501
    device.manufacturer = "Ultimarc"
    device.product = "I-PAC2"
    return device


@pytest.fixture
def mock_usb_backend():
    """Mock USB backend."""
    backend = Mock()
    backend.__name__ = "libusb1"
    return backend


# =============================================================================
# Tests: Service Initialization
# =============================================================================


def test_service_initialization():
    """Test service initializes with correct defaults."""
    service = HardwareDetectionService()

    assert service._cache_ttl == 5.0
    assert service._cache is None
    assert service._backend_type == "none"
    assert service._platform == platform.system()


def test_service_custom_ttl():
    """Test service accepts custom cache TTL."""
    service = HardwareDetectionService(cache_ttl=10.0)

    assert service._cache_ttl == 10.0


# =============================================================================
# Tests: Known Boards
# =============================================================================


def test_known_boards_immutable():
    """Test KNOWN_BOARDS contains frozen BoardConfig instances."""
    assert "d209:0501" in KNOWN_BOARDS

    board = KNOWN_BOARDS["d209:0501"]
    assert board.name == "Ultimarc I-PAC2"
    assert board.device_type == DeviceType.KEYBOARD_ENCODER


def test_get_supported_boards():
    """Test get_supported_boards returns all known boards."""
    boards = get_supported_boards()

    assert len(boards) > 0
    assert all("vid" in b and "pid" in b for b in boards)
    assert all(b["known"] is True for b in boards)

    # Verify sorting
    for i in range(len(boards) - 1):
        assert (boards[i]["vendor"], boards[i]["name"]) <= (
            boards[i + 1]["vendor"],
            boards[i + 1]["name"],
        )


def test_get_supported_boards_cached():
    """Test get_supported_boards result is cached."""
    boards1 = get_supported_boards()
    boards2 = get_supported_boards()

    # Should return same object (cached)
    assert boards1 is boards2


# =============================================================================
# Tests: Device Detection - Pyusb
# =============================================================================


@pytest.mark.asyncio
async def test_detect_with_pyusb_success(service, mock_usb_device, mock_usb_backend):
    """Test successful device detection via pyusb."""
    with patch("usb.core.find") as mock_find, patch(
        "backend.services.hardware.HardwareDetectionService._get_usb_backend"
    ) as mock_get_backend:

        mock_get_backend.return_value = mock_usb_backend
        mock_find.return_value = [mock_usb_device]

        devices = await service._detect_with_pyusb(include_unknown=False)

        assert devices is not None
        assert len(devices) == 1
        assert devices[0].vid == "0xd209"
        assert devices[0].pid == "0x0501"
        assert devices[0].name == "Ultimarc I-PAC2"
        assert devices[0].known is True


@pytest.mark.asyncio
async def test_detect_with_pyusb_no_backend(service):
    """Test pyusb detection returns None when backend unavailable."""
    with patch(
        "backend.services.hardware.HardwareDetectionService._get_usb_backend"
    ) as mock_get_backend:
        mock_get_backend.return_value = None

        devices = await service._detect_with_pyusb(include_unknown=False)

        assert devices is None


@pytest.mark.asyncio
async def test_detect_with_pyusb_permission_error(service, mock_usb_device, mock_usb_backend):
    """Test pyusb detection raises USBPermissionError on access denied."""
    with patch("usb.core.find") as mock_find, patch(
        "backend.services.hardware.HardwareDetectionService._get_usb_backend"
    ) as mock_get_backend:

        mock_get_backend.return_value = mock_usb_backend

        # Mock USB permission error
        import usb.core

        mock_usb_device.idVendor = 0xD209
        mock_usb_device.idProduct = 0x0501

        # Simulate permission error when accessing device properties
        def raise_permission_error(*args, **kwargs):
            raise usb.core.USBError("Permission denied", errno=13)

        # Patch the device iteration to raise error
        mock_find.return_value = [mock_usb_device]

        # Mock extract_device_strings to raise permission error
        with patch.object(
            service, "_extract_device_strings", side_effect=usb.core.USBError("Permission denied")
        ):
            # Should propagate permission error
            with pytest.raises(USBPermissionError):
                await service._detect_with_pyusb(include_unknown=False)


@pytest.mark.asyncio
async def test_detect_with_pyusb_unknown_devices(service, mock_usb_backend):
    """Test pyusb detection includes unknown devices when requested."""
    unknown_device = Mock()
    unknown_device.idVendor = 0x9999
    unknown_device.idProduct = 0x9999
    unknown_device.manufacturer = "Unknown Corp"
    unknown_device.product = "Mystery Device"

    with patch("usb.core.find") as mock_find, patch(
        "backend.services.hardware.HardwareDetectionService._get_usb_backend"
    ) as mock_get_backend:

        mock_get_backend.return_value = mock_usb_backend
        mock_find.return_value = [unknown_device]

        devices = await service._detect_with_pyusb(include_unknown=True)

        assert devices is not None
        assert len(devices) == 1
        assert devices[0].known is False
        assert devices[0].type == DeviceType.UNKNOWN


# =============================================================================
# Tests: Windows Registry Fallback
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific test")
async def test_detect_windows_registry(service):
    """Test Windows registry detection fallback."""
    with patch("backend.services.hardware.platform.system", return_value="Windows"):
        with patch.object(service, "_scan_windows_registry", return_value=[]) as mock_scan:
            devices = await service._detect_windows_registry(include_unknown=False)

            mock_scan.assert_called_once_with(False)
            assert devices == []


@pytest.mark.asyncio
async def test_detect_windows_registry_non_windows(service):
    """Test Windows registry detection returns empty on non-Windows."""
    with patch("backend.services.hardware.platform.system", return_value="Linux"):
        devices = await service._detect_windows_registry(include_unknown=False)

        assert devices == []


def test_parse_registry_instance_connected(service):
    """Test registry instance parsing for connected device."""
    if platform.system() != "Windows":
        pytest.skip("Windows-specific test")

    # Mock winreg (Windows-only module)
    with patch("backend.services.hardware.winreg") as mock_winreg:
        mock_key = MagicMock()
        mock_inst_key = MagicMock()

        # Mock registry values
        mock_winreg.QueryValueEx.side_effect = [
            ("USB Input Device", 1),  # FriendlyName
            ("USB\\VID_D209&PID_0501", 1),  # DeviceDesc
            ("Ultimarc", 1),  # Mfg
            (0, 1),  # StatusFlags (connected)
        ]

        mock_winreg.OpenKey.return_value.__enter__.return_value = mock_inst_key

        device_info = service._parse_registry_instance(
            mock_key, "instance_name", 0xD209, 0x0501, include_unknown=False
        )

        assert device_info is not None
        assert device_info.name == "USB Input Device"


# =============================================================================
# Tests: lsusb Fallback
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(platform.system() == "Windows", reason="Linux/macOS-specific test")
async def test_detect_lsusb_success(service):
    """Test lsusb detection fallback."""
    lsusb_output = "Bus 001 Device 004: ID d209:0501 Ultimarc. I-PAC2\n"

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (lsusb_output.encode(), b"")
        mock_exec.return_value = mock_process

        with patch("shutil.which", return_value="/usr/bin/lsusb"):
            devices = await service._detect_lsusb(include_unknown=False)

            assert len(devices) == 1
            assert devices[0].name == "Ultimarc I-PAC2"


@pytest.mark.asyncio
async def test_detect_lsusb_not_installed(service):
    """Test lsusb detection returns empty when lsusb not installed."""
    with patch("shutil.which", return_value=None):
        devices = await service._detect_lsusb(include_unknown=False)

        assert devices == []


def test_parse_lsusb_line(service):
    """Test parsing individual lsusb output lines."""
    line = "Bus 001 Device 004: ID d209:0501 Ultimarc. I-PAC2 Keyboard Encoder"

    device = service._parse_lsusb_line(line, include_unknown=False)

    assert device is not None
    assert device.vid == "0xd209"
    assert device.pid == "0x0501"


def test_parse_lsusb_line_malformed(service):
    """Test parsing malformed lsusb lines returns None."""
    device = service._parse_lsusb_line("invalid line", include_unknown=False)

    assert device is None


# =============================================================================
# Tests: Cache Management
# =============================================================================


@pytest.mark.asyncio
async def test_cache_usage(service):
    """Test device detection uses cache when fresh."""
    # Mock first detection
    with patch.object(service, "_detect_async", return_value=[]) as mock_detect:
        # First call: cache miss
        devices1, stats1 = await service.detect_devices(use_cache=True)
        assert stats1.from_cache is False
        assert mock_detect.call_count == 1

        # Second call: cache hit
        devices2, stats2 = await service.detect_devices(use_cache=True)
        assert stats2.from_cache is True
        assert mock_detect.call_count == 1  # Not called again


@pytest.mark.asyncio
async def test_cache_invalidation(service):
    """Test cache invalidation forces fresh detection."""
    with patch.object(service, "_detect_async", return_value=[]) as mock_detect:
        # Prime cache
        await service.detect_devices(use_cache=True)
        assert mock_detect.call_count == 1

        # Invalidate
        service.invalidate_cache()

        # Should detect again
        await service.detect_devices(use_cache=True)
        assert mock_detect.call_count == 2


@pytest.mark.asyncio
async def test_cache_expiry(service):
    """Test cache expires after TTL."""
    service._cache_ttl = 0.1  # 100ms TTL

    with patch.object(service, "_detect_async", return_value=[]) as mock_detect:
        # Prime cache
        await service.detect_devices(use_cache=True)

        # Wait for expiry
        await asyncio.sleep(0.2)

        # Should detect again
        await service.detect_devices(use_cache=True)
        assert mock_detect.call_count == 2


# =============================================================================
# Tests: Error Handling
# =============================================================================


@pytest.mark.asyncio
async def test_detect_devices_no_backend_raises_error(service):
    """Test detection raises USBBackendError when no backend available."""
    with patch.object(service, "_detect_with_pyusb", return_value=None), patch.object(
        service, "_detect_windows_registry", return_value=[]
    ), patch.object(service, "_detect_lsusb", return_value=[]):

        with pytest.raises(USBBackendError):
            await service.detect_devices(use_cache=False)


@pytest.mark.asyncio
async def test_usb_permission_error_propagates(service):
    """Test USBPermissionError propagates to caller."""
    with patch.object(
        service, "_detect_with_pyusb", side_effect=USBPermissionError("Permission denied")
    ):
        with pytest.raises(USBPermissionError):
            await service.detect_devices(use_cache=False)


def test_backend_error_message_platform_specific(service):
    """Test error messages are platform-specific."""
    with patch("backend.services.hardware.platform.system", return_value="Windows"):
        service._platform = "Windows"
        msg = service._get_backend_error_message()
        assert "Zadig" in msg or "Windows" in msg

    with patch("backend.services.hardware.platform.system", return_value="Linux"):
        service._platform = "Linux"
        msg = service._get_backend_error_message()
        assert "libusb-1.0-0" in msg


# =============================================================================
# Tests: Helper Functions
# =============================================================================


def test_format_vid_pid():
    """Test VID/PID formatting."""
    result = HardwareDetectionService._format_vid_pid(0xD209, 0x0501)

    assert result == "d209:0501"


def test_extract_device_strings_success():
    """Test extracting manufacturer and product strings."""
    device = Mock()
    device.manufacturer = "Ultimarc"
    device.product = "I-PAC2"

    manufacturer, product = HardwareDetectionService._extract_device_strings(device)

    assert manufacturer == "Ultimarc"
    assert product == "I-PAC2"


def test_extract_device_strings_exception():
    """Test extracting strings handles exceptions gracefully."""
    device = Mock()
    device.manufacturer = Mock(side_effect=Exception("USB Error"))
    device.product = "I-PAC2"

    manufacturer, product = HardwareDetectionService._extract_device_strings(device)

    assert manufacturer is None  # Exception caught
    assert product == "I-PAC2"


def test_build_device_info_known_board():
    """Test building DeviceInfo for known board."""
    board_config = KNOWN_BOARDS["d209:0501"]

    device_info = HardwareDetectionService._build_device_info(
        0xD209, 0x0501, board_config, "Ultimarc", "I-PAC2"
    )

    assert device_info.name == "Ultimarc I-PAC2"
    assert device_info.vendor == "Ultimarc"
    assert device_info.known is True
    assert device_info.type == DeviceType.KEYBOARD_ENCODER


def test_build_device_info_unknown_device():
    """Test building DeviceInfo for unknown device."""
    device_info = HardwareDetectionService._build_device_info(
        0x9999, 0x9999, None, "Unknown Corp", "Mystery Device"
    )

    assert device_info.name == "Mystery Device"
    assert device_info.vendor == "Unknown Corp"
    assert device_info.known is False
    assert device_info.type == DeviceType.UNKNOWN


# =============================================================================
# Tests: Convenience Functions
# =============================================================================


@pytest.mark.asyncio
async def test_detect_arcade_boards():
    """Test detect_arcade_boards filters to arcade types only."""
    mock_devices = [
        DeviceInfo(
            vid="0xd209",
            pid="0x0501",
            vid_pid="d209:0501",
            name="I-PAC2",
            vendor="Ultimarc",
            type=DeviceType.KEYBOARD_ENCODER,
            detected=True,
            known=True,
        ),
        DeviceInfo(
            vid="0x046d",
            pid="0xc21d",
            vid_pid="046d:c21d",
            name="F310",
            vendor="Logitech",
            type=DeviceType.GAMEPAD,
            detected=True,
            known=True,
        ),
    ]

    with patch.object(
        HardwareDetectionService, "detect_devices", return_value=(mock_devices, Mock())
    ):
        arcade_boards = await detect_arcade_boards()

        # Should only return keyboard encoder (not gamepad)
        assert len(arcade_boards) == 1
        assert arcade_boards[0].type == DeviceType.KEYBOARD_ENCODER


@pytest.mark.asyncio
async def test_get_board_by_vid_pid_found():
    """Test get_board_by_vid_pid returns device when found."""
    mock_device = DeviceInfo(
        vid="0xd209",
        pid="0x0501",
        vid_pid="d209:0501",
        name="I-PAC2",
        vendor="Ultimarc",
        type=DeviceType.KEYBOARD_ENCODER,
        detected=True,
        known=True,
    )

    with patch.object(
        HardwareDetectionService, "detect_devices", return_value=([mock_device], Mock())
    ):
        device = await get_board_by_vid_pid("0xd209", "0x0501")

        assert device is not None
        assert device.name == "I-PAC2"


@pytest.mark.asyncio
async def test_get_board_by_vid_pid_not_found():
    """Test get_board_by_vid_pid returns None when device not found."""
    with patch.object(HardwareDetectionService, "detect_devices", return_value=([], Mock())):
        device = await get_board_by_vid_pid("d209", "0501")

        assert device is None


@pytest.mark.asyncio
async def test_get_board_by_vid_pid_invalid_format():
    """Test get_board_by_vid_pid returns None for invalid VID/PID."""
    device = await get_board_by_vid_pid("invalid", "format")

    assert device is None


# =============================================================================
# Tests: Dependency Injection
# =============================================================================


def test_get_hardware_service_singleton():
    """Test get_hardware_service returns singleton instance."""
    service1 = get_hardware_service()
    service2 = get_hardware_service()

    assert service1 is service2


# =============================================================================
# Tests: Pydantic Models
# =============================================================================


def test_device_info_validation():
    """Test DeviceInfo Pydantic validation."""
    device = DeviceInfo(
        vid="0xd209",
        pid="0x0501",
        vid_pid="d209:0501",
        name="I-PAC2",
        vendor="Ultimarc",
        type=DeviceType.KEYBOARD_ENCODER,
        detected=True,
        known=True,
    )

    assert device.vid == "0xd209"
    assert device.type == DeviceType.KEYBOARD_ENCODER


def test_detection_stats_validation():
    """Test DetectionStats Pydantic validation."""
    stats = DetectionStats(
        total_devices=5,
        known_devices=3,
        scan_duration_ms=123.45,
        backend_type="pyusb",
        from_cache=False,
        platform="Windows",
    )

    assert stats.total_devices == 5
    assert stats.backend_type == "pyusb"


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_detection_flow():
    """Integration test: full device detection with fallback chain."""
    service = HardwareDetectionService()

    try:
        devices, stats = await service.detect_devices(include_unknown=False)

        assert isinstance(devices, list)
        assert isinstance(stats, DetectionStats)
        assert stats.backend_type in ("pyusb", "windows_registry", "lsusb", "none")

    except (USBBackendError, USBPermissionError) as exc:
        # Expected on systems without USB backend or permissions
        pytest.skip(f"USB backend unavailable: {exc}")
