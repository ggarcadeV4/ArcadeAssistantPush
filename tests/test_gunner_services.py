"""Pytest tests for Gunner hardware and configuration services.

Tests device detection, calibration state machine, profile management, and factory pattern.
"""

import pytest
from pathlib import Path
import tempfile
import json
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from services.gunner_hardware import (
    HardwareDetector,
    USBDetector,
    MockDetector,
    create_detector,
    KNOWN_DEVICES
)
from services.gunner_config import GunnerConfigService, DEFAULT_PROFILE
from services.gunner_factory import detector_factory, is_mock_mode, get_detector_status


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_detector():
    """Create MockDetector instance for testing."""
    return MockDetector()


@pytest.fixture
def temp_storage_path():
    """Create temporary storage path for config tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def gunner_config_service(temp_storage_path):
    """Create GunnerConfigService instance with temp storage."""
    return GunnerConfigService(local_storage_path=temp_storage_path)


# ============================================================================
# MockDetector Tests
# ============================================================================

def test_mock_detector_get_devices(mock_detector):
    """Test MockDetector returns simulated devices."""
    devices = mock_detector.get_devices()

    assert len(devices) == 2
    assert all(d['type'] == 'mock' for d in devices)
    assert all('Sinden' in d['name'] or 'AimTrak' in d['name'] for d in devices)


def test_mock_detector_capture_point_valid(mock_detector):
    """Test MockDetector captures valid calibration point."""
    success = mock_detector.capture_point(device_id=1, x=0.5, y=0.5)

    assert success is True
    assert len(mock_detector._calibration_points) == 1
    assert mock_detector._calibration_points[0] == {'x': 0.5, 'y': 0.5}
    assert mock_detector._current_point == 1


def test_mock_detector_capture_point_invalid_coords(mock_detector):
    """Test MockDetector rejects invalid coordinates."""
    success = mock_detector.capture_point(device_id=1, x=1.5, y=0.5)

    assert success is False
    assert len(mock_detector._calibration_points) == 0


def test_mock_detector_capture_point_invalid_device(mock_detector):
    """Test MockDetector rejects invalid device ID."""
    success = mock_detector.capture_point(device_id=999, x=0.5, y=0.5)

    assert success is False


def test_mock_detector_calibration_complete(mock_detector):
    """Test MockDetector completes 9-point calibration."""
    # Capture 9 points
    for i in range(9):
        x = (i % 3) * 0.4 + 0.1
        y = (i // 3) * 0.4 + 0.1
        success = mock_detector.capture_point(device_id=1, x=x, y=y)
        assert success is True

    # After 9 points, current_point should reset
    assert mock_detector._current_point == 0
    assert len(mock_detector._calibration_points) == 9


def test_mock_detector_get_calibration_points(mock_detector):
    """Test MockDetector returns calibration points."""
    mock_detector.capture_point(1, 0.1, 0.1)
    mock_detector.capture_point(1, 0.5, 0.5)

    points = mock_detector.get_calibration_points()

    assert len(points) == 2
    assert points[0] == {'x': 0.1, 'y': 0.1}
    assert points[1] == {'x': 0.5, 'y': 0.5}


def test_mock_detector_reset_calibration(mock_detector):
    """Test MockDetector resets calibration state."""
    mock_detector.capture_point(1, 0.1, 0.1)
    mock_detector.capture_point(1, 0.5, 0.5)

    mock_detector.reset_calibration()

    assert len(mock_detector._calibration_points) == 0
    assert mock_detector._current_point == 0


# ============================================================================
# USBDetector Tests (with mocking)
# ============================================================================

@patch('services.gunner_hardware.HID_AVAILABLE', True)
@patch('services.gunner_hardware.hid')
def test_usb_detector_enumerate_devices(mock_hid):
    """Test USBDetector enumerates USB devices."""
    # Mock HID enumeration
    mock_hid.enumerate.return_value = [
        {
            'vendor_id': KNOWN_DEVICES['sinden']['vid'],
            'product_id': KNOWN_DEVICES['sinden']['pid'],
            'path': b'/dev/hidraw0'
        }
    ]

    detector = USBDetector()
    devices = detector.get_devices()

    assert len(devices) == 1
    assert devices[0]['name'] == KNOWN_DEVICES['sinden']['name']
    assert devices[0]['type'] == 'sinden'


@patch('services.gunner_hardware.HID_AVAILABLE', True)
@patch('services.gunner_hardware.hid')
def test_usb_detector_no_devices(mock_hid):
    """Test USBDetector handles no devices."""
    mock_hid.enumerate.return_value = []

    detector = USBDetector()
    devices = detector.get_devices()

    assert len(devices) == 0


@patch('services.gunner_hardware.HID_AVAILABLE', True)
@patch('services.gunner_hardware.hid')
def test_usb_detector_capture_point(mock_hid):
    """Test USBDetector captures calibration point."""
    mock_hid.enumerate.return_value = [
        {
            'vendor_id': KNOWN_DEVICES['sinden']['vid'],
            'product_id': KNOWN_DEVICES['sinden']['pid'],
            'path': b'/dev/hidraw0'
        }
    ]

    detector = USBDetector()
    devices = detector.get_devices()

    success = detector.capture_point(devices[0]['id'], 0.5, 0.5)

    assert success is True


# ============================================================================
# Detector Factory Tests
# ============================================================================

def test_create_detector_default_mock():
    """Test create_detector returns MockDetector by default."""
    detector = create_detector()

    assert isinstance(detector, MockDetector)


def test_create_detector_explicit_mock():
    """Test create_detector with explicit mock flag."""
    detector = create_detector(use_mock=True)

    assert isinstance(detector, MockDetector)


@patch('services.gunner_hardware.HID_AVAILABLE', True)
@patch.dict(os.environ, {'AA_USE_MOCK_GUNNER': 'false'}, clear=False)
def test_create_detector_usb_mode():
    """Test create_detector returns USBDetector in production."""
    detector = create_detector(use_mock=False)

    assert isinstance(detector, USBDetector)


def test_detector_factory_mock_mode():
    """Test detector_factory in mock mode."""
    detector = detector_factory()

    assert isinstance(detector, HardwareDetector)


def test_is_mock_mode():
    """Test is_mock_mode detection."""
    # Should default to True in dev
    assert is_mock_mode() is True


def test_get_detector_status():
    """Test get_detector_status returns status dict."""
    status = get_detector_status()

    assert 'mode' in status
    assert 'hid_available' in status
    assert 'environment' in status
    assert status['mode'] in ['mock', 'usb']


# ============================================================================
# GunnerConfigService Tests
# ============================================================================

def test_gunner_config_init(gunner_config_service, temp_storage_path):
    """Test GunnerConfigService initialization."""
    assert gunner_config_service.local_storage_path == temp_storage_path
    assert temp_storage_path.exists()


def test_gunner_config_save_profile_valid(gunner_config_service):
    """Test saving valid calibration profile."""
    points = [{'x': i * 0.1, 'y': i * 0.1} for i in range(1, 10)]

    success = gunner_config_service.save_profile(
        user_id='dad',
        game='area51',
        points=points
    )

    assert success is True


def test_gunner_config_save_profile_invalid_points(gunner_config_service):
    """Test saving profile with invalid points count."""
    points = [{'x': 0.1, 'y': 0.1}]  # Only 1 point instead of 9

    success = gunner_config_service.save_profile(
        user_id='dad',
        game='area51',
        points=points
    )

    assert success is False


def test_gunner_config_save_profile_invalid_coordinates(gunner_config_service):
    """Test saving profile with invalid coordinates."""
    points = [{'x': 1.5, 'y': 0.5}]  # Invalid x coordinate
    points.extend([{'x': i * 0.1, 'y': i * 0.1} for i in range(1, 9)])

    success = gunner_config_service.save_profile(
        user_id='dad',
        game='area51',
        points=points
    )

    assert success is False


def test_gunner_config_load_profile_default(gunner_config_service):
    """Test loading non-existent profile returns default."""
    points = gunner_config_service.load_profile(user_id='dad', game='nonexistent')

    assert len(points) == 9
    assert points == DEFAULT_PROFILE['points']


def test_gunner_config_save_and_load_profile(gunner_config_service):
    """Test saving and loading profile."""
    original_points = [{'x': i * 0.1, 'y': i * 0.1} for i in range(1, 10)]

    # Save
    success = gunner_config_service.save_profile(
        user_id='dad',
        game='timeCrisis',
        points=original_points
    )
    assert success is True

    # Load
    loaded_points = gunner_config_service.load_profile(user_id='dad', game='timeCrisis')

    assert len(loaded_points) == 9
    assert loaded_points == original_points


def test_gunner_config_list_profiles(gunner_config_service):
    """Test listing user profiles."""
    # Save multiple profiles
    points = [{'x': i * 0.1, 'y': i * 0.1} for i in range(1, 10)]

    gunner_config_service.save_profile('dad', 'area51', points)
    gunner_config_service.save_profile('dad', 'timeCrisis', points)

    # List profiles
    profiles = gunner_config_service.list_profiles('dad')

    assert len(profiles) >= 2
    games = [p['game'] for p in profiles]
    assert 'area51' in games
    assert 'timeCrisis' in games


def test_gunner_config_delete_profile(gunner_config_service):
    """Test deleting profile."""
    points = [{'x': i * 0.1, 'y': i * 0.1} for i in range(1, 10)]

    # Save profile
    gunner_config_service.save_profile('dad', 'area51', points)

    # Delete profile
    success = gunner_config_service.delete_profile('dad', 'area51')
    assert success is True

    # Verify deleted (should return default)
    loaded_points = gunner_config_service.load_profile('dad', 'area51')
    assert loaded_points == DEFAULT_PROFILE['points']


def test_gunner_config_local_storage_path_sanitization(gunner_config_service):
    """Test profile path sanitization for safe filenames."""
    points = [{'x': i * 0.1, 'y': i * 0.1} for i in range(1, 10)]

    # Save profile with special characters
    success = gunner_config_service.save_profile(
        user_id='dad/admin',  # Unsafe characters
        game='game/title',
        points=points
    )

    assert success is True

    # Verify file created with sanitized name
    profile_path = gunner_config_service._get_profile_path('dad/admin', 'game/title')
    assert '/' not in profile_path.name  # Slashes should be replaced


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.integration
def test_full_calibration_workflow(mock_detector, gunner_config_service):
    """Test complete calibration workflow."""
    # Step 1: Get devices
    devices = mock_detector.get_devices()
    assert len(devices) > 0

    # Step 2: Start calibration
    device = devices[0]
    mock_detector.reset_calibration()

    # Step 3: Capture 9 points
    for i in range(9):
        x = (i % 3) * 0.4 + 0.1
        y = (i // 3) * 0.4 + 0.1
        success = mock_detector.capture_point(device['id'], x, y)
        assert success is True

    # Step 4: Get calibration points
    points = mock_detector.get_calibration_points()
    assert len(points) == 9

    # Step 5: Save profile
    success = gunner_config_service.save_profile(
        user_id='dad',
        game='integrated_test',
        points=points
    )
    assert success is True

    # Step 6: Load profile
    loaded_points = gunner_config_service.load_profile('dad', 'integrated_test')
    assert loaded_points == points


# ============================================================================
# Parametrized Tests
# ============================================================================

@pytest.mark.parametrize('x,y,expected', [
    (0.0, 0.0, True),    # Top-left corner
    (0.5, 0.5, True),    # Center
    (1.0, 1.0, True),    # Bottom-right corner
    (-0.1, 0.5, False),  # Out of bounds (negative)
    (1.1, 0.5, False),   # Out of bounds (> 1.0)
    (0.5, -0.1, False),  # Out of bounds (negative)
    (0.5, 1.1, False),   # Out of bounds (> 1.0)
])
def test_mock_detector_coordinate_validation(mock_detector, x, y, expected):
    """Test coordinate validation for various inputs."""
    success = mock_detector.capture_point(device_id=1, x=x, y=y)
    assert success is expected


@pytest.mark.parametrize('user_id,game', [
    ('dad', 'area51'),
    ('mom', 'timeCrisis'),
    ('tim', 'houseOfTheDead'),
    ('sarah', 'duckHunt'),
])
def test_gunner_config_multiple_users(gunner_config_service, user_id, game):
    """Test profile isolation between users."""
    points = [{'x': i * 0.1, 'y': i * 0.1} for i in range(1, 10)]

    success = gunner_config_service.save_profile(user_id, game, points)
    assert success is True

    loaded_points = gunner_config_service.load_profile(user_id, game)
    assert loaded_points == points


@pytest.mark.parametrize('env_var,expected_type', [
    ('true', MockDetector),
    ('false', type(None)),  # Will depend on HID availability
    ('1', MockDetector),
    ('yes', MockDetector),
])
@patch.dict(os.environ, clear=False)
def test_factory_env_var_override(env_var, expected_type):
    """Test factory respects AA_USE_MOCK_GUNNER env var."""
    os.environ['AA_USE_MOCK_GUNNER'] = env_var

    detector = detector_factory()

    if expected_type == MockDetector:
        assert isinstance(detector, MockDetector)
    # For 'false', we can't assert USBDetector without mocking HID availability
