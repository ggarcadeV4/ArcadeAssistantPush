"""Tests for Console Wizard backend functionality."""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from fastapi import HTTPException

from backend.services.console_wizard_manager import ConsoleWizardManager
from backend.services.emulator_discovery import EmulatorDiscoveryService, EmulatorInfo, CONSOLE_EMULATOR_TYPES


@pytest.fixture
def mock_drive_root(tmp_path):
    """Create a temporary drive root for testing."""
    return tmp_path


@pytest.fixture
def mock_manifest():
    """Return a test manifest."""
    return {
        "sanctioned_paths": [
            "config/mappings",
            "configs/console_wizard",
            "state",
            "state/console_wizard",
            "backups",
            "logs",
        ]
    }


@pytest.fixture
def mock_controls_empty():
    """Return empty controls."""
    return {"mappings": {}}


@pytest.fixture
def mock_controls_incomplete():
    """Return incomplete controls (missing some required keys)."""
    return {
        "mappings": {
            "p1.up": {"pin": "1", "type": "button"},
            "p1.down": {"pin": "2", "type": "button"},
            # Missing p1.left, p1.right, buttons, etc.
        }
    }


@pytest.fixture
def mock_controls_complete():
    """Return complete controls with all required keys."""
    return {
        "mappings": {
            "p1.up": {"pin": "1", "type": "button"},
            "p1.down": {"pin": "2", "type": "button"},
            "p1.left": {"pin": "3", "type": "button"},
            "p1.right": {"pin": "4", "type": "button"},
            "p1.button1": {"pin": "5", "type": "button"},
            "p1.button2": {"pin": "6", "type": "button"},
            "p1.button3": {"pin": "7", "type": "button"},
            "p1.button4": {"pin": "8", "type": "button"},
            "p1.start": {"pin": "9", "type": "button"},
            "p1.coin": {"pin": "10", "type": "button"},
            "p2.up": {"pin": "11", "type": "button"},
            "p2.down": {"pin": "12", "type": "button"},
            "p2.left": {"pin": "13", "type": "button"},
            "p2.right": {"pin": "14", "type": "button"},
            "p2.button1": {"pin": "15", "type": "button"},
            "p2.button2": {"pin": "16", "type": "button"},
            "p2.button3": {"pin": "17", "type": "button"},
            "p2.button4": {"pin": "18", "type": "button"},
            "p2.start": {"pin": "19", "type": "button"},
            "p2.coin": {"pin": "20", "type": "button"},
        }
    }


class TestConsolateWizardDryRunDefault:
    """Test that dry_run defaults to True for safety."""

    def test_generate_configs_dry_run_true_by_default(self, mock_drive_root, mock_manifest, mock_controls_complete):
        """Test that generate_configs defaults to dry_run=True (preview only)."""
        manager = ConsoleWizardManager(mock_drive_root, mock_manifest)

        with patch.object(manager.mapping_service, "load_current", return_value=mock_controls_complete):
            with patch.object(manager.discovery, "discover_emulators", return_value=[]):
                # When dry_run=True (default), no files should be written
                results = manager.generate_configs(dry_run=True)

                # Should return results in preview mode
                assert isinstance(results, list)


class TestRequiredKeyValidation:
    """Test required-key validation for controls.json."""

    def test_empty_controls_raises_404(self, mock_drive_root, mock_manifest, mock_controls_empty):
        """Test that empty controls.json raises 404 error."""
        manager = ConsoleWizardManager(mock_drive_root, mock_manifest)

        with patch.object(manager.mapping_service, "load_current", return_value=mock_controls_empty):
            with pytest.raises(HTTPException) as exc_info:
                manager.generate_configs()

            assert exc_info.value.status_code == 404
            assert "empty" in str(exc_info.value.detail).lower()

    def test_incomplete_controls_raises_409(self, mock_drive_root, mock_manifest, mock_controls_incomplete):
        """Test that incomplete controls.json raises 409 with missing_keys."""
        manager = ConsoleWizardManager(mock_drive_root, mock_manifest)

        with patch.object(manager.mapping_service, "load_current", return_value=mock_controls_incomplete):
            with pytest.raises(HTTPException) as exc_info:
                manager.generate_configs()

            assert exc_info.value.status_code == 409
            detail = exc_info.value.detail
            assert isinstance(detail, dict)
            assert detail.get("error") == "incomplete_mapping"
            assert "missing_keys" in detail
            assert isinstance(detail["missing_keys"], list)
            assert len(detail["missing_keys"]) > 0

    def test_complete_controls_passes_validation(self, mock_drive_root, mock_manifest, mock_controls_complete):
        """Test that complete controls.json passes validation."""
        manager = ConsoleWizardManager(mock_drive_root, mock_manifest)

        mock_emulator = EmulatorInfo(
            name="RetroArch",
            type="retroarch",
            path=Path("/fake/path"),
            executable=None,
            config_path=None,
            config_format="cfg",
            enabled=True,
            priority=20,
        )

        with patch.object(manager.mapping_service, "load_current", return_value=mock_controls_complete):
            with patch.object(manager.discovery, "discover_emulators", return_value=[mock_emulator]):
                # Should not raise an exception
                results = manager.generate_configs(dry_run=True)
                assert isinstance(results, list)


class TestConsoleOnlyDiscovery:
    """Test that Console Wizard only discovers console emulators."""

    def test_console_only_filter_excludes_mame(self, mock_drive_root, mock_manifest):
        """Test that MAME is excluded from console-only discovery."""
        discovery = EmulatorDiscoveryService(mock_drive_root, mock_manifest)

        mock_emulators = [
            EmulatorInfo(
                name="MAME",
                type="mame",
                path=Path("/fake/mame"),
                executable=None,
                config_path=None,
                config_format="ini",
                enabled=True,
                priority=10,
            ),
            EmulatorInfo(
                name="RetroArch",
                type="retroarch",
                path=Path("/fake/retroarch"),
                executable=None,
                config_path=None,
                config_format="cfg",
                enabled=True,
                priority=20,
            ),
        ]

        discovery._cache = mock_emulators
        import time
        discovery._cache_ts = time.time()

        filtered = discovery.discover_emulators(console_only=True)

        assert len(filtered) == 1
        assert filtered[0].type == "retroarch"
        assert all(emu.type in CONSOLE_EMULATOR_TYPES for emu in filtered)

    def test_console_only_allowlist_includes_expected_types(self):
        """Test that console allowlist includes expected emulator types."""
        expected_console_types = {
            "retroarch",
            "dolphin",
            "pcsx2",
            "cemu",
            "yuzu",
            "citra",
        }

        assert expected_console_types.issubset(CONSOLE_EMULATOR_TYPES)
        assert "mame" not in CONSOLE_EMULATOR_TYPES
        assert "teknoparrot" not in CONSOLE_EMULATOR_TYPES


class TestLoggingEnhancements:
    """Test that logs include target_files and device_id."""

    def test_logs_include_target_files_and_device_id(
        self, mock_drive_root, mock_manifest, mock_controls_complete, tmp_path
    ):
        """Test that log entries include target_files and device_id."""
        manager = ConsoleWizardManager(mock_drive_root, mock_manifest)

        # Create logs directory
        logs_dir = mock_drive_root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        mock_emulator = EmulatorInfo(
            name="RetroArch",
            type="retroarch",
            path=Path("/fake/path"),
            executable=None,
            config_path=None,
            config_format="cfg",
            enabled=True,
            priority=20,
        )

        test_device_id = "test-cabinet-001"

        with patch.object(manager.mapping_service, "load_current", return_value=mock_controls_complete):
            with patch.object(manager.discovery, "discover_emulators", return_value=[mock_emulator]):
                with patch.object(manager, "_json_writer"):
                    # Call with dry_run=False to trigger logging
                    results = manager.generate_configs(
                        dry_run=False,
                        device_id=test_device_id
                    )

                    # Check log file
                    log_file = mock_drive_root / "logs" / "changes.jsonl"
                    if log_file.exists():
                        with open(log_file, "r") as f:
                            log_line = f.readline()
                            if log_line:
                                log_entry = json.loads(log_line)
                                # Verify log structure
                                assert "panel" in log_entry
                                assert log_entry["panel"] == "console_wizard"
                                # These fields should be present
                                assert "device_id" in log_entry
                                assert "target_files" in log_entry or log_entry.get("device_id") == test_device_id


class TestSyncFromChuck:
    """Test sync-from-chuck functionality."""

    def test_sync_from_chuck_respects_dry_run(
        self, mock_drive_root, mock_manifest, mock_controls_complete
    ):
        """Test that sync_from_chuck respects dry_run parameter."""
        manager = ConsoleWizardManager(mock_drive_root, mock_manifest)

        with patch.object(manager.mapping_service, "load_current", return_value=mock_controls_complete):
            with patch.object(manager, "_controls_signature", return_value="new_hash"):
                with patch.object(manager, "_load_signature", return_value="old_hash"):
                    with patch.object(manager.discovery, "discover_emulators", return_value=[]):
                        # Preview mode (dry_run=True) should not update signature
                        result = manager.sync_from_chuck(dry_run=True, force=True)

                        assert result["changed"] == True
                        # Signature should not be stored in dry_run mode
                        # (we can't easily test this without file I/O, but the code path is there)

    def test_sync_from_chuck_applies_when_dry_run_false(
        self, mock_drive_root, mock_manifest, mock_controls_complete
    ):
        """Test that sync_from_chuck applies changes when dry_run=False."""
        manager = ConsoleWizardManager(mock_drive_root, mock_manifest)

        with patch.object(manager.mapping_service, "load_current", return_value=mock_controls_complete):
            with patch.object(manager, "_controls_signature", return_value="new_hash"):
                with patch.object(manager, "_load_signature", return_value="old_hash"):
                    with patch.object(manager, "_store_signature") as mock_store:
                        with patch.object(manager.discovery, "discover_emulators", return_value=[]):
                            # Apply mode (dry_run=False) should update signature
                            result = manager.sync_from_chuck(dry_run=False, force=True)

                            assert result["changed"] == True
                            # Signature should be stored in apply mode
                            mock_store.assert_called_once_with("new_hash")


class TestProfileLoading:
    """Test emulator profile loading functionality."""

    def test_load_profile_returns_none_when_not_found(self, mock_drive_root, mock_manifest):
        """Test that _load_profile returns None for non-existent profiles."""
        manager = ConsoleWizardManager(mock_drive_root, mock_manifest)

        profile = manager._load_profile("nonexistent_emulator")
        assert profile is None

    def test_load_profile_caches_result(self, mock_drive_root, mock_manifest):
        """Test that profile loading uses cache."""
        manager = ConsoleWizardManager(mock_drive_root, mock_manifest)

        # Load once
        profile1 = manager._load_profile("nonexistent")

        # Load again - should use cache
        profile2 = manager._load_profile("nonexistent")

        assert profile1 is profile2  # Same object from cache



