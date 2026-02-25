"""Tests for Identity Service — VID:PID parsing and hardware bio scanning.

Feature: agentic-repair-self-healing
"""

from __future__ import annotations

import re
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.services.identity_service import (
    HardwareBio,
    USBDevice,
    parse_vid_pid,
    scan_hardware_bio,
    _VID_PID_RE,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_HEX4 = st.from_regex(r"[0-9A-Fa-f]{4}", fullmatch=True)


def _valid_usb_device_id() -> st.SearchStrategy[str]:
    """Generate a valid USB\\VID_XXXX&PID_XXXX device ID string."""
    return st.builds(
        lambda vid, pid, suffix: f"USB\\VID_{vid}&PID_{pid}\\{suffix}",
        _HEX4,
        _HEX4,
        st.from_regex(r"[A-Za-z0-9_]{0,20}", fullmatch=True),
    )


def _invalid_device_id() -> st.SearchStrategy[str]:
    """Generate device IDs that do NOT match the USB VID/PID pattern."""
    return st.one_of(
        st.just(""),
        st.just("PCI\\VEN_8086&DEV_1234"),
        st.just("ACPI\\PNP0303"),
        st.just("HID\\VID_1234"),
        st.just("ROOT\\SYSTEM"),
        st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=40).filter(
            lambda s: not re.search(r"USB\\VID_[0-9A-Fa-f]{4}&PID_[0-9A-Fa-f]{4}", s, re.IGNORECASE)
        ),
    )


_LOWERCASE_HEX_RE = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{4}$")


def _build_mock_entities(device_ids: list[str]) -> list:
    """Build mock WMI entity objects from device ID strings."""
    entities = []
    for did in device_ids:
        entity = MagicMock()
        entity.DeviceID = did
        entity.Description = f"Device {did[:20]}"
        entity.Name = f"Name {did[:20]}"
        entities.append(entity)
    return entities


# ---------------------------------------------------------------------------
# Property 1: VID:PID parsing produces valid, filtered output
# **Validates: Requirements 1.2, 1.3, 1.4**
# ---------------------------------------------------------------------------


class TestProperty1VidPidParsing:
    """Property 1: VID:PID parsing produces valid, filtered output.

    For any list of WMI PnP device entries containing a mix of valid USB
    device IDs and non-USB entries, scan_hardware_bio() should return a
    HardwareBio where:
    (a) every entry has a vid_pid in lowercase hex format xxxx:xxxx,
    (b) no entry from a non-USB or unparseable device ID appears, and
    (c) device_count equals len(devices).
    """

    @given(device_id=_valid_usb_device_id())
    @settings(max_examples=150)
    def test_parse_vid_pid_valid_always_lowercase_hex(self, device_id: str):
        """Any valid USB device ID produces a lowercase hex VID:PID."""
        result = parse_vid_pid(device_id)
        assert result is not None
        assert _LOWERCASE_HEX_RE.match(result), f"Expected lowercase hex, got '{result}'"

    @given(device_id=_invalid_device_id())
    @settings(max_examples=150)
    def test_parse_vid_pid_invalid_returns_none(self, device_id: str):
        """Any non-USB device ID returns None."""
        result = parse_vid_pid(device_id)
        assert result is None

    @given(
        valid_ids=st.lists(_valid_usb_device_id(), min_size=0, max_size=10),
        invalid_ids=st.lists(_invalid_device_id(), min_size=0, max_size=10),
    )
    @settings(max_examples=100)
    def test_mixed_device_list_filtering_and_count(
        self, valid_ids: list[str], invalid_ids: list[str]
    ):
        """Mixed device lists: only valid USB entries appear, count matches."""
        all_ids = valid_ids + invalid_ids
        entities = _build_mock_entities(all_ids)

        # Compute expected VID:PIDs from valid IDs
        expected_vid_pids = set()
        for did in valid_ids:
            parsed = parse_vid_pid(did)
            if parsed:
                expected_vid_pids.add(parsed)

        # Mock the wmi import and WMI() call
        mock_wmi_mod = MagicMock()
        mock_wmi_instance = MagicMock()
        mock_wmi_instance.Win32_PnPEntity.return_value = entities
        mock_wmi_mod.WMI.return_value = mock_wmi_instance

        import sys
        with patch.dict(sys.modules, {"wmi": mock_wmi_mod}):
            # Re-import to pick up the mocked wmi
            import importlib
            import backend.services.identity_service as mod
            importlib.reload(mod)
            bio = mod.scan_hardware_bio()

        # (a) Every vid_pid is lowercase hex xxxx:xxxx
        for device in bio["devices"]:
            assert _LOWERCASE_HEX_RE.match(device["vid_pid"]), (
                f"vid_pid '{device['vid_pid']}' is not lowercase hex"
            )

        # (b) Only valid USB entries appear
        for device in bio["devices"]:
            assert device["vid_pid"] in expected_vid_pids

        # (c) device_count == len(devices)
        assert bio["device_count"] == len(bio["devices"])

        # (d) scan_timestamp is valid ISO 8601
        datetime.fromisoformat(bio["scan_timestamp"])

        # (e) error is None on success
        assert bio["error"] is None


# ---------------------------------------------------------------------------
# Unit tests for Identity Service error paths
# Requirements: 1.5, 1.6
# ---------------------------------------------------------------------------


class TestIdentityServiceErrorPaths:
    """Unit tests for graceful degradation when WMI is unavailable."""

    def test_wmi_unavailable_returns_empty_bio_with_error(self):
        """When wmi library is not installed, return empty bio with error."""
        import sys
        import importlib

        # Remove wmi from modules to simulate ImportError
        saved = sys.modules.pop("wmi", None)
        try:
            # Ensure the import inside scan_hardware_bio raises ImportError
            sys.modules["wmi"] = None  # Forces ImportError on `import wmi`
            import backend.services.identity_service as mod
            importlib.reload(mod)
            bio = mod.scan_hardware_bio()

            assert bio["devices"] == []
            assert bio["device_count"] == 0
            assert bio["error"] is not None
            assert "wmi" in bio["error"].lower() or "unavailable" in bio["error"].lower()
        finally:
            if saved is not None:
                sys.modules["wmi"] = saved
            else:
                sys.modules.pop("wmi", None)

    def test_wmi_query_exception_returns_empty_bio_with_error(self):
        """When WMI query raises an exception, return empty bio with error."""
        import sys
        import importlib

        mock_wmi_mod = MagicMock()
        mock_wmi_mod.WMI.side_effect = RuntimeError("WMI connection failed")

        with patch.dict(sys.modules, {"wmi": mock_wmi_mod}):
            import backend.services.identity_service as mod
            importlib.reload(mod)
            bio = mod.scan_hardware_bio()

        assert bio["devices"] == []
        assert bio["device_count"] == 0
        assert bio["error"] is not None
        assert "WMI" in bio["error"] or "failed" in bio["error"].lower()

    def test_empty_device_list_returns_zero_count(self):
        """When WMI returns no devices, bio has empty list and count 0."""
        import sys
        import importlib

        mock_wmi_mod = MagicMock()
        mock_wmi_instance = MagicMock()
        mock_wmi_instance.Win32_PnPEntity.return_value = []
        mock_wmi_mod.WMI.return_value = mock_wmi_instance

        with patch.dict(sys.modules, {"wmi": mock_wmi_mod}):
            import backend.services.identity_service as mod
            importlib.reload(mod)
            bio = mod.scan_hardware_bio()

        assert bio["devices"] == []
        assert bio["device_count"] == 0
        assert bio["error"] is None

    def test_scan_timestamp_is_valid_iso8601(self):
        """scan_timestamp should always be valid ISO 8601."""
        import sys
        import importlib

        mock_wmi_mod = MagicMock()
        mock_wmi_instance = MagicMock()
        mock_wmi_instance.Win32_PnPEntity.return_value = []
        mock_wmi_mod.WMI.return_value = mock_wmi_instance

        with patch.dict(sys.modules, {"wmi": mock_wmi_mod}):
            import backend.services.identity_service as mod
            importlib.reload(mod)
            bio = mod.scan_hardware_bio()

        # Should not raise
        ts = datetime.fromisoformat(bio["scan_timestamp"])
        assert ts is not None

    def test_wmi_unavailable_import_error_scan_timestamp_valid(self):
        """Even on ImportError, scan_timestamp is valid ISO 8601."""
        import sys
        import importlib

        sys.modules["wmi"] = None
        try:
            import backend.services.identity_service as mod
            importlib.reload(mod)
            bio = mod.scan_hardware_bio()
            ts = datetime.fromisoformat(bio["scan_timestamp"])
            assert ts is not None
        finally:
            sys.modules.pop("wmi", None)
