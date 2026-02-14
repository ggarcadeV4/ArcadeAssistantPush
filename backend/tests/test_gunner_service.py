"""Comprehensive pytest tests for gunner_service.py.

Coverage Goals:
- >80% line coverage
- All critical paths tested
- Edge cases handled
- Mocked dependencies (Supabase, hardware)

Test Categories:
1. Pydantic model validation
2. Service orchestration
3. Supabase integration (mocked)
4. Hardware detection integration
5. Telemetry logging
6. Error handling
"""

import pytest
import os
import json
import time
from pathlib import Path
from typing import List, Dict, Optional
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from pydantic import ValidationError

# Import models and service
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.gunner_service import (
    CalibPoint,
    CalibData,
    CalibrationResult,
    GunnerService,
    get_supabase_client,
    get_config_service,
    get_gunner_service
)
from services.gunner_hardware import MockDetector, HardwareDetector
from services.gunner_config import GunnerConfigService


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_detector():
    """Create mock hardware detector."""
    detector = MockDetector()
    return detector


@pytest.fixture
def mock_supabase_client():
    """Create mock Supabase client."""
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client._get_client.return_value.table.return_value = mock_table

    # Mock select chain
    mock_select = MagicMock()
    mock_select.in_.return_value = mock_select
    mock_select.eq.return_value = mock_select
    mock_select.execute.return_value.data = []
    mock_table.select.return_value = mock_select

    # Mock upsert chain
    mock_upsert = MagicMock()
    mock_upsert.execute.return_value.data = [{"id": "test_id"}]
    mock_table.upsert.return_value = mock_upsert

    return mock_client


@pytest.fixture
def mock_config_service(tmp_path):
    """Create mock config service with temp storage."""
    config_service = GunnerConfigService(local_storage_path=tmp_path / "gunner")
    return config_service


@pytest.fixture
def temp_telemetry_path(tmp_path):
    """Create temporary telemetry log path."""
    telemetry_path = tmp_path / "logs" / "gunner_telemetry.jsonl"
    telemetry_path.parent.mkdir(parents=True, exist_ok=True)
    return str(telemetry_path)


@pytest.fixture
def gunner_service(mock_detector, mock_config_service, mock_supabase_client, temp_telemetry_path):
    """Create GunnerService instance with mocked dependencies."""
    return GunnerService(
        detector=mock_detector,
        config_service=mock_config_service,
        supabase_client=mock_supabase_client,
        telemetry_path=temp_telemetry_path
    )


@pytest.fixture
def valid_calib_points():
    """Generate valid 9-point calibration data."""
    return [
        CalibPoint(x=0.1, y=0.1, confidence=0.98),
        CalibPoint(x=0.5, y=0.1, confidence=0.95),
        CalibPoint(x=0.9, y=0.1, confidence=0.97),
        CalibPoint(x=0.1, y=0.5, confidence=0.96),
        CalibPoint(x=0.5, y=0.5, confidence=0.99),
        CalibPoint(x=0.9, y=0.5, confidence=0.94),
        CalibPoint(x=0.1, y=0.9, confidence=0.93),
        CalibPoint(x=0.5, y=0.9, confidence=0.92),
        CalibPoint(x=0.9, y=0.9, confidence=0.91),
    ]


@pytest.fixture
def valid_calib_data(valid_calib_points):
    """Generate valid CalibData instance."""
    return CalibData(
        device_id="gun_sinden_01",
        points=valid_calib_points,
        user_id="dad",
        timestamp=time.time(),
        metadata={"game": "area51", "session": "test"}
    )


# ============================================================================
# Test CalibPoint Model
# ============================================================================

class TestCalibPoint:
    """Test CalibPoint Pydantic model validation."""

    def test_valid_point(self):
        """Test valid calibration point creation."""
        point = CalibPoint(x=0.5, y=0.5, confidence=0.95)
        assert point.x == 0.5
        assert point.y == 0.5
        assert point.confidence == 0.95

    def test_default_confidence(self):
        """Test default confidence value of 1.0."""
        point = CalibPoint(x=0.3, y=0.7)
        assert point.confidence == 1.0

    def test_x_out_of_bounds_high(self):
        """Test x coordinate > 1.0 raises ValidationError."""
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            CalibPoint(x=1.5, y=0.5)

    def test_x_out_of_bounds_low(self):
        """Test x coordinate < 0.0 raises ValidationError."""
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            CalibPoint(x=-0.1, y=0.5)

    def test_y_out_of_bounds_high(self):
        """Test y coordinate > 1.0 raises ValidationError."""
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            CalibPoint(x=0.5, y=1.2)

    def test_y_out_of_bounds_low(self):
        """Test y coordinate < 0.0 raises ValidationError."""
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            CalibPoint(x=0.5, y=-0.3)

    def test_confidence_out_of_bounds(self):
        """Test confidence > 1.0 raises ValidationError."""
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            CalibPoint(x=0.5, y=0.5, confidence=1.5)


# ============================================================================
# Test CalibData Model
# ============================================================================

class TestCalibData:
    """Test CalibData Pydantic model validation."""

    def test_valid_calib_data(self, valid_calib_points):
        """Test valid calibration data creation."""
        data = CalibData(
            device_id="test_device",
            points=valid_calib_points,
            user_id="test_user"
        )
        assert data.device_id == "test_device"
        assert len(data.points) == 9
        assert data.user_id == "test_user"
        assert data.timestamp is not None

    def test_exactly_9_points_required(self, valid_calib_points):
        """Test that exactly 9 points are required."""
        # Too few points
        with pytest.raises(ValidationError, match="at least 9 items"):
            CalibData(
                device_id="test",
                points=valid_calib_points[:8],
                user_id="test"
            )

        # Too many points
        with pytest.raises(ValidationError, match="at most 9 items"):
            CalibData(
                device_id="test",
                points=valid_calib_points + [CalibPoint(x=0.5, y=0.5)],
                user_id="test"
            )

    def test_empty_device_id_rejected(self, valid_calib_points):
        """Test empty device_id is rejected."""
        with pytest.raises(ValidationError, match="at least 1 character"):
            CalibData(
                device_id="",
                points=valid_calib_points,
                user_id="test"
            )

    def test_empty_user_id_rejected(self, valid_calib_points):
        """Test empty user_id is rejected."""
        with pytest.raises(ValidationError, match="at least 1 character"):
            CalibData(
                device_id="test",
                points=valid_calib_points,
                user_id=""
            )

    def test_negative_coordinates_rejected(self):
        """Test negative coordinates are rejected via root validator."""
        points_with_negative = [
            CalibPoint(x=-0.1, y=0.5) if i == 4 else CalibPoint(x=0.1 * i, y=0.1 * i)
            for i in range(9)
        ]

        # This should be caught by CalibPoint validation before root validator
        with pytest.raises(ValidationError):
            CalibData(
                device_id="test",
                points=points_with_negative,
                user_id="test"
            )


# ============================================================================
# Test GunnerService - Device Query
# ============================================================================

class TestGunnerServiceDevices:
    """Test GunnerService.get_devices_with_calib()."""

    @pytest.mark.asyncio
    async def test_get_devices_no_supabase(self, gunner_service):
        """Test device query without Supabase."""
        # Remove Supabase client
        gunner_service.supabase = None

        devices = await gunner_service.get_devices_with_calib()

        # Should return mock devices without calibration data
        assert len(devices) == 2
        assert devices[0]["name"] == "Sinden Light Gun (Mock)"
        assert devices[0]["calib"]["accuracy"] == 0.0
        assert devices[0]["calib"]["points_count"] == 0

    @pytest.mark.asyncio
    async def test_get_devices_with_supabase(self, gunner_service, mock_supabase_client):
        """Test device query with Supabase calibration data."""
        # Mock Supabase response with calibration data
        mock_table = mock_supabase_client._get_client.return_value.table.return_value
        mock_select = mock_table.select.return_value
        mock_select.execute.return_value.data = [
            {
                "device_id": "1",
                "user_id": "dad",
                "points": [{"x": 0.1, "y": 0.1, "confidence": 0.95} for _ in range(9)],
                "created_at": "2025-10-28T12:00:00Z"
            }
        ]

        devices = await gunner_service.get_devices_with_calib()

        assert len(devices) == 2
        assert devices[0]["calib"]["accuracy"] == 0.95
        assert devices[0]["calib"]["user_id"] == "dad"
        assert devices[0]["calib"]["points_count"] == 9

    @pytest.mark.asyncio
    async def test_get_devices_supabase_failure(self, gunner_service, mock_supabase_client):
        """Test device query when Supabase fails (graceful degradation)."""
        # Mock Supabase failure
        mock_table = mock_supabase_client._get_client.return_value.table.return_value
        mock_select = mock_table.select.return_value
        mock_select.execute.side_effect = Exception("Supabase connection failed")

        # Should not raise, should return devices without calib data
        devices = await gunner_service.get_devices_with_calib()

        assert len(devices) == 2
        assert devices[0]["calib"]["accuracy"] == 0.0


# ============================================================================
# Test GunnerService - Calibration Workflow
# ============================================================================

class TestGunnerServiceCalibration:
    """Test GunnerService.calibrate() workflow."""

    @pytest.mark.asyncio
    async def test_calibrate_success(self, gunner_service, valid_calib_data, temp_telemetry_path):
        """Test successful calibration workflow."""
        result = await gunner_service.calibrate(valid_calib_data)

        # Verify result
        assert result.status == "calibrated"
        assert result.accuracy > 0.9  # High confidence points
        assert result.device_id == "gun_sinden_01"
        assert result.user_id == "dad"
        assert result.points_count == 9
        assert result.supabase_synced is True

        # Verify telemetry logging
        assert os.path.exists(temp_telemetry_path)
        with open(temp_telemetry_path, 'r') as f:
            logs = [json.loads(line) for line in f]
            assert any(log["event"] == "calibration_start" for log in logs)
            assert any(log["event"] == "calibration_complete" for log in logs)

    @pytest.mark.asyncio
    async def test_calibrate_device_not_found(self, gunner_service, valid_calib_data):
        """Test calibration fails when device not found."""
        # Use invalid device ID
        valid_calib_data.device_id = "non_existent_device"

        with pytest.raises(ValueError, match="Device not found"):
            await gunner_service.calibrate(valid_calib_data)

    @pytest.mark.asyncio
    async def test_calibrate_no_supabase(self, gunner_service, valid_calib_data):
        """Test calibration works without Supabase (local fallback)."""
        # Remove Supabase client
        gunner_service.supabase = None

        # Use valid mock device ID
        valid_calib_data.device_id = "1"

        result = await gunner_service.calibrate(valid_calib_data)

        assert result.status == "calibrated"
        assert result.supabase_synced is False  # No cloud sync

    @pytest.mark.asyncio
    async def test_calibrate_supabase_failure(self, gunner_service, valid_calib_data, mock_supabase_client):
        """Test calibration continues when Supabase fails (local fallback)."""
        # Mock Supabase failure
        mock_table = mock_supabase_client._get_client.return_value.table.return_value
        mock_table.upsert.return_value.execute.side_effect = Exception("Supabase write failed")

        # Use valid mock device ID
        valid_calib_data.device_id = "1"

        result = await gunner_service.calibrate(valid_calib_data)

        # Should still succeed via local fallback
        assert result.status == "calibrated"
        assert result.supabase_synced is False

    @pytest.mark.asyncio
    async def test_accuracy_calculation(self, gunner_service):
        """Test accuracy calculation from confidence scores."""
        # Create points with known confidence values
        points = [CalibPoint(x=0.1 * i, y=0.1 * i, confidence=0.9) for i in range(9)]

        accuracy = gunner_service._calc_accuracy(points)

        assert accuracy == 0.9

    @pytest.mark.asyncio
    async def test_accuracy_varying_confidence(self, gunner_service):
        """Test accuracy calculation with varying confidence."""
        points = [
            CalibPoint(x=0.1, y=0.1, confidence=1.0),
            CalibPoint(x=0.2, y=0.2, confidence=0.8),
            CalibPoint(x=0.3, y=0.3, confidence=0.9),
            CalibPoint(x=0.4, y=0.4, confidence=0.7),
            CalibPoint(x=0.5, y=0.5, confidence=1.0),
            CalibPoint(x=0.6, y=0.6, confidence=0.6),
            CalibPoint(x=0.7, y=0.7, confidence=0.95),
            CalibPoint(x=0.8, y=0.8, confidence=0.85),
            CalibPoint(x=0.9, y=0.9, confidence=0.75),
        ]

        accuracy = gunner_service._calc_accuracy(points)

        expected = sum(p.confidence for p in points) / 9
        assert abs(accuracy - expected) < 0.001


# ============================================================================
# Test Telemetry Logging
# ============================================================================

class TestTelemetryLogging:
    """Test structured telemetry logging."""

    def test_telemetry_file_created(self, gunner_service, temp_telemetry_path):
        """Test telemetry file is created on initialization."""
        assert os.path.exists(os.path.dirname(temp_telemetry_path))

    def test_telemetry_logging(self, gunner_service, temp_telemetry_path):
        """Test telemetry events are logged to JSONL."""
        gunner_service._log_telemetry(
            "test_event",
            device_id="test_device",
            status="success"
        )

        # Read telemetry file
        with open(temp_telemetry_path, 'r') as f:
            logs = [json.loads(line) for line in f]

        assert len(logs) >= 1
        last_log = logs[-1]
        assert "timestamp" in last_log
        assert last_log["event"] == "test_event"

    @pytest.mark.asyncio
    async def test_calibration_telemetry_events(self, gunner_service, valid_calib_data, temp_telemetry_path):
        """Test calibration emits start and complete telemetry."""
        # Use valid mock device ID
        valid_calib_data.device_id = "1"

        await gunner_service.calibrate(valid_calib_data)

        # Read telemetry
        with open(temp_telemetry_path, 'r') as f:
            logs = [json.loads(line) for line in f]

        events = [log["event"] for log in logs]
        assert "calibration_start" in events
        assert "calibration_complete" in events

    @pytest.mark.asyncio
    async def test_calibration_error_telemetry(self, gunner_service, valid_calib_data, temp_telemetry_path):
        """Test calibration errors are logged."""
        # Invalid device to trigger error
        valid_calib_data.device_id = "invalid_device"

        try:
            await gunner_service.calibrate(valid_calib_data)
        except ValueError:
            pass  # Expected

        # Read telemetry
        with open(temp_telemetry_path, 'r') as f:
            logs = [json.loads(line) for line in f]

        events = [log["event"] for log in logs]
        assert "calibration_error" in events


# ============================================================================
# Test Dependency Factories
# ============================================================================

class TestDependencyFactories:
    """Test dependency injection factories."""

    def test_get_config_service(self):
        """Test get_config_service factory."""
        service = get_config_service()
        assert isinstance(service, GunnerConfigService)

    @patch('services.gunner_service.get_client')
    def test_get_supabase_client_success(self, mock_get_client):
        """Test get_supabase_client when available."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        result = get_supabase_client()

        assert result == mock_client

    @patch('services.gunner_service.get_client', side_effect=Exception("Supabase not configured"))
    def test_get_supabase_client_failure(self, mock_get_client):
        """Test get_supabase_client returns None on failure."""
        result = get_supabase_client()

        assert result is None


# ============================================================================
# Test Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_points_accuracy(self, gunner_service):
        """Test accuracy calculation with empty points list."""
        accuracy = gunner_service._calc_accuracy([])
        assert accuracy == 0.0

    @pytest.mark.asyncio
    async def test_calibrate_with_metadata(self, gunner_service, valid_calib_data):
        """Test calibration with custom metadata."""
        valid_calib_data.device_id = "1"
        valid_calib_data.metadata = {
            "game": "time_crisis",
            "difficulty": "hard",
            "session": "tournament"
        }

        result = await gunner_service.calibrate(valid_calib_data)

        assert result.status == "calibrated"

    @pytest.mark.parametrize("confidence_values", [
        [1.0] * 9,  # Perfect confidence
        [0.0] * 9,  # Zero confidence
        [0.5] * 9,  # Mid confidence
    ])
    @pytest.mark.asyncio
    async def test_various_confidence_levels(self, gunner_service, confidence_values):
        """Test calibration with various confidence levels."""
        points = [
            CalibPoint(x=0.1 * i, y=0.1 * i, confidence=confidence_values[i])
            for i in range(9)
        ]

        data = CalibData(
            device_id="1",
            points=points,
            user_id="test"
        )

        result = await gunner_service.calibrate(data)

        expected_accuracy = sum(confidence_values) / 9
        assert abs(result.accuracy - expected_accuracy) < 0.001


# ============================================================================
# Test Coverage Report Helper
# ============================================================================

if __name__ == "__main__":
    """Run tests with coverage report."""
    pytest.main([
        __file__,
        "-v",
        "--cov=services.gunner_service",
        "--cov-report=term-missing",
        "--cov-report=html",
        "--cov-fail-under=80"
    ])
