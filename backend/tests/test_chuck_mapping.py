"""Comprehensive pytest tests for chuck/mapping.py.

Coverage Goals:
- >80% line coverage
- All validation paths tested
- Conflict detection edge cases
- Capability validation
- Diff generation

Test Categories:
1. Basic validation (structure, board, mappings)
2. Pin conflict detection
3. Hardware capability validation
4. Diff generation
5. Concurrent edit detection
6. Board capabilities profiles
7. Error handling
"""

import pytest
from typing import Dict, Any

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.chuck.mapping import (
    MappingService,
    MappingError,
    ValidationError,
    ConflictError,
    CapabilityError,
    ValidationResult,
    ValidationIssue,
    ValidationLevel,
    BoardCapabilities,
    validate_mapping_structure,
    detect_pin_conflicts,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def valid_mapping():
    """Valid mapping data for testing."""
    return {
        "version": "1.0",
        "board": {
            "vid": "0x045e",
            "pid": "0x028e",
            "name": "Test Board",
        },
        "mappings": {
            "p1.button1": {"pin": 1, "type": "button"},
            "p1.button2": {"pin": 2, "type": "button"},
            "p1.joystick_x": {"pin": 10, "type": "axis"},
        },
        "last_modified": "2024-01-01T00:00:00",
    }


@pytest.fixture
def mapping_with_conflicts():
    """Mapping with pin conflicts."""
    return {
        "version": "1.0",
        "board": {
            "vid": "0x045e",
            "pid": "0x028e",
            "name": "Test Board",
        },
        "mappings": {
            "p1.button1": {"pin": 1, "type": "button"},
            "p1.button2": {"pin": 1, "type": "button"},  # Conflict!
            "p1.button3": {"pin": 3, "type": "button"},
        },
    }


@pytest.fixture
def mapping_service():
    """Create mapping service instance."""
    return MappingService()


@pytest.fixture
def strict_mapping_service():
    """Create strict mapping service."""
    return MappingService(strict_validation=True)


@pytest.fixture
def ipac2_capabilities():
    """I-PAC 2 board capabilities."""
    return BoardCapabilities.from_board_type("ipac2")


# ============================================================================
# Basic Validation Tests
# ============================================================================


def test_validate_valid_mapping(mapping_service, valid_mapping):
    """Test validation of valid mapping."""
    result = mapping_service.validate_structure(valid_mapping)

    assert result.valid is True
    assert len(result.errors) == 0


def test_validate_missing_version(mapping_service):
    """Test validation catches missing version."""
    mapping = {
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Test"},
        "mappings": {},
    }

    result = mapping_service.validate_structure(mapping)

    assert result.valid is False
    assert any(e.code == "MISSING_KEY" for e in result.errors)
    assert any("version" in e.message for e in result.errors)


def test_validate_missing_board(mapping_service):
    """Test validation catches missing board."""
    mapping = {
        "version": "1.0",
        "mappings": {},
    }

    result = mapping_service.validate_structure(mapping)

    assert result.valid is False
    assert any(e.code == "MISSING_KEY" for e in result.errors)


def test_validate_missing_mappings(mapping_service):
    """Test validation catches missing mappings."""
    mapping = {
        "version": "1.0",
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Test"},
    }

    result = mapping_service.validate_structure(mapping)

    assert result.valid is False
    assert any(e.code == "MISSING_KEY" for e in result.errors)


def test_validate_invalid_vid_format(mapping_service):
    """Test validation catches invalid VID format."""
    mapping = {
        "version": "1.0",
        "board": {
            "vid": "invalid",  # Not hex
            "pid": "0x028e",
            "name": "Test",
        },
        "mappings": {},
    }

    result = mapping_service.validate_structure(mapping)

    assert result.valid is False
    assert any(e.code == "INVALID_VID" for e in result.errors)


def test_validate_invalid_pid_format(mapping_service):
    """Test validation catches invalid PID format."""
    mapping = {
        "version": "1.0",
        "board": {
            "vid": "0x045e",
            "pid": "xyz",  # Not hex
            "name": "Test",
        },
        "mappings": {},
    }

    result = mapping_service.validate_structure(mapping)

    assert result.valid is False
    assert any(e.code == "INVALID_PID" for e in result.errors)


def test_validate_missing_board_fields(mapping_service):
    """Test validation catches missing board fields."""
    mapping = {
        "version": "1.0",
        "board": {
            "vid": "0x045e",
            # Missing pid and name
        },
        "mappings": {},
    }

    result = mapping_service.validate_structure(mapping)

    assert result.valid is False
    assert any(e.code == "MISSING_BOARD_KEY" for e in result.errors)
    error_messages = [e.message for e in result.errors]
    assert any("pid" in msg for msg in error_messages)
    assert any("name" in msg for msg in error_messages)


# ============================================================================
# Mapping Validation Tests
# ============================================================================


def test_validate_invalid_control_structure(mapping_service):
    """Test validation catches invalid control structure."""
    mapping = {
        "version": "1.0",
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Test"},
        "mappings": {
            "p1.button1": "not a dict",  # Invalid
        },
    }

    result = mapping_service.validate_structure(mapping)

    assert result.valid is False
    assert any(e.code == "INVALID_CONTROL" for e in result.errors)


def test_validate_missing_pin(mapping_service):
    """Test validation catches missing pin."""
    mapping = {
        "version": "1.0",
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Test"},
        "mappings": {
            "p1.button1": {"type": "button"},  # No pin
        },
    }

    result = mapping_service.validate_structure(mapping)

    assert result.valid is False
    assert any(e.code == "MISSING_PIN" for e in result.errors)


def test_validate_missing_type_warning(mapping_service):
    """Test validation warns about missing type."""
    mapping = {
        "version": "1.0",
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Test"},
        "mappings": {
            "p1.button1": {"pin": 1},  # No type
        },
    }

    result = mapping_service.validate_structure(mapping)

    assert result.valid is True  # Warning, not error
    assert any(w.code == "MISSING_TYPE" for w in result.warnings)


# ============================================================================
# Pin Conflict Tests
# ============================================================================


def test_detect_pin_conflict(mapping_service, mapping_with_conflicts):
    """Test detection of pin conflicts."""
    result = mapping_service.validate_structure(mapping_with_conflicts)

    assert result.valid is False
    assert any(e.code == "PIN_CONFLICT" for e in result.errors)

    # Check conflict details
    conflict_errors = [e for e in result.errors if e.code == "PIN_CONFLICT"]
    assert len(conflict_errors) > 0
    assert conflict_errors[0].details["pin"] == 1


def test_detect_conflicts_function(mapping_with_conflicts):
    """Test standalone conflict detection function."""
    conflicts = detect_pin_conflicts(mapping_with_conflicts["mappings"])

    assert len(conflicts) > 0
    assert conflicts[0]["type"] == "pin_conflict"
    assert conflicts[0]["pin"] == 1
    assert len(conflicts[0]["controls"]) == 2


def test_no_conflicts_in_valid_mapping(mapping_service, valid_mapping):
    """Test that valid mapping has no conflicts."""
    conflicts = mapping_service.detect_conflicts(valid_mapping["mappings"])

    assert len(conflicts) == 0


def test_multiple_pin_conflicts(mapping_service):
    """Test detection of multiple pin conflicts."""
    mapping = {
        "version": "1.0",
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Test"},
        "mappings": {
            "p1.button1": {"pin": 1, "type": "button"},
            "p1.button2": {"pin": 1, "type": "button"},  # Conflict on pin 1
            "p1.button3": {"pin": 2, "type": "button"},
            "p1.button4": {"pin": 2, "type": "button"},  # Conflict on pin 2
        },
    }

    result = mapping_service.validate_structure(mapping)

    assert result.valid is False
    conflict_errors = [e for e in result.errors if e.code == "PIN_CONFLICT"]
    assert len(conflict_errors) == 2  # Two conflicts


# ============================================================================
# Hardware Capability Tests
# ============================================================================


def test_board_capabilities_ipac2(ipac2_capabilities):
    """Test I-PAC 2 board capabilities."""
    assert ipac2_capabilities.max_buttons == 32
    assert ipac2_capabilities.supports_analog is False
    assert ipac2_capabilities.name == "I-PAC 2"


def test_board_capabilities_generic():
    """Test generic board capabilities."""
    caps = BoardCapabilities.from_board_type("unknown")
    assert caps.max_buttons == 32
    assert caps.supports_analog is True


def test_validate_exceeds_button_capacity():
    """Test validation catches exceeding button capacity."""
    caps = BoardCapabilities(max_buttons=2)
    service = MappingService(capabilities=caps)

    mapping = {
        "version": "1.0",
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Test"},
        "mappings": {
            "p1.button1": {"pin": 1, "type": "button"},
            "p1.button2": {"pin": 2, "type": "button"},
            "p1.button3": {"pin": 3, "type": "button"},  # Exceeds capacity
        },
    }

    result = service.validate_structure(mapping)

    assert result.valid is False
    assert any(e.code == "TOO_MANY_BUTTONS" for e in result.errors)


def test_validate_exceeds_axis_capacity():
    """Test validation catches exceeding axis capacity."""
    caps = BoardCapabilities(max_axes=1)
    service = MappingService(capabilities=caps)

    mapping = {
        "version": "1.0",
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Test"},
        "mappings": {
            "p1.joystick_x": {"pin": 10, "type": "axis"},
            "p1.joystick_y": {"pin": 11, "type": "axis"},  # Exceeds capacity
        },
    }

    result = service.validate_structure(mapping)

    assert result.valid is False
    assert any(e.code == "TOO_MANY_AXES" for e in result.errors)


def test_validate_invalid_pin_for_board():
    """Test validation catches pins not available on board."""
    caps = BoardCapabilities(available_pins={1, 2, 3})  # Only pins 1-3
    service = MappingService(capabilities=caps)

    mapping = {
        "version": "1.0",
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Test"},
        "mappings": {
            "p1.button1": {"pin": 10, "type": "button"},  # Pin 10 not available
        },
    }

    result = service.validate_structure(mapping)

    assert result.valid is False
    assert any(e.code == "INVALID_PIN" for e in result.errors)


# ============================================================================
# Diff Generation Tests
# ============================================================================


def test_generate_diff_added_controls(mapping_service):
    """Test diff generation for added controls."""
    current = {
        "version": "1.0",
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Test"},
        "mappings": {
            "p1.button1": {"pin": 1, "type": "button"},
        },
    }

    new = {
        "version": "1.0",
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Test"},
        "mappings": {
            "p1.button1": {"pin": 1, "type": "button"},
            "p1.button2": {"pin": 2, "type": "button"},  # Added
        },
    }

    diff = mapping_service.generate_diff(current, new)

    assert len(diff["added"]) == 1
    assert diff["added"][0]["control"] == "p1.button2"


def test_generate_diff_removed_controls(mapping_service):
    """Test diff generation for removed controls."""
    current = {
        "version": "1.0",
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Test"},
        "mappings": {
            "p1.button1": {"pin": 1, "type": "button"},
            "p1.button2": {"pin": 2, "type": "button"},
        },
    }

    new = {
        "version": "1.0",
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Test"},
        "mappings": {
            "p1.button1": {"pin": 1, "type": "button"},
            # button2 removed
        },
    }

    diff = mapping_service.generate_diff(current, new)

    assert len(diff["removed"]) == 1
    assert diff["removed"][0]["control"] == "p1.button2"


def test_generate_diff_modified_controls(mapping_service):
    """Test diff generation for modified controls."""
    current = {
        "version": "1.0",
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Test"},
        "mappings": {
            "p1.button1": {"pin": 1, "type": "button"},
        },
    }

    new = {
        "version": "1.0",
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Test"},
        "mappings": {
            "p1.button1": {"pin": 2, "type": "button"},  # Pin changed
        },
    }

    diff = mapping_service.generate_diff(current, new)

    assert len(diff["modified"]) == 1
    assert diff["modified"][0]["control"] == "p1.button1"
    assert diff["modified"][0]["old_value"]["pin"] == 1
    assert diff["modified"][0]["new_value"]["pin"] == 2


def test_generate_diff_board_change(mapping_service):
    """Test diff generation detects board changes."""
    current = {
        "version": "1.0",
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Board A"},
        "mappings": {},
    }

    new = {
        "version": "1.0",
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Board B"},  # Name changed
        "mappings": {},
    }

    diff = mapping_service.generate_diff(current, new)

    assert diff.get("board_changed") is True
    assert "board_diff" in diff


def test_generate_diff_no_changes(mapping_service, valid_mapping):
    """Test diff generation with no changes."""
    diff = mapping_service.generate_diff(valid_mapping, valid_mapping)

    assert len(diff["added"]) == 0
    assert len(diff["removed"]) == 0
    assert len(diff["modified"]) == 0
    assert len(diff["unchanged"]) > 0


# ============================================================================
# Concurrent Edit Tests
# ============================================================================


def test_concurrent_edit_no_conflict(mapping_service):
    """Test concurrent edit check passes with matching timestamps."""
    mapping = {
        "last_modified": "2024-01-01T00:00:00",
    }

    result = mapping_service.check_concurrent_edit(mapping, "2024-01-01T00:00:00")

    assert result is True


def test_concurrent_edit_conflict(mapping_service):
    """Test concurrent edit check detects conflict."""
    mapping = {
        "last_modified": "2024-01-01T00:00:00",
    }

    result = mapping_service.check_concurrent_edit(mapping, "2023-12-31T00:00:00")

    assert result is False


def test_concurrent_edit_no_timestamp(mapping_service):
    """Test concurrent edit check allows edit when no timestamp."""
    mapping = {}

    result = mapping_service.check_concurrent_edit(mapping, None)

    assert result is True


# ============================================================================
# ValidationResult Tests
# ============================================================================


def test_validation_result_add_error():
    """Test adding error to ValidationResult."""
    result = ValidationResult(valid=True)
    issue = ValidationIssue(
        level=ValidationLevel.ERROR,
        code="TEST_ERROR",
        message="Test error",
    )

    result.add_issue(issue)

    assert result.valid is False
    assert len(result.errors) == 1
    assert result.has_errors() is True


def test_validation_result_add_warning():
    """Test adding warning to ValidationResult."""
    result = ValidationResult(valid=True)
    issue = ValidationIssue(
        level=ValidationLevel.WARNING,
        code="TEST_WARNING",
        message="Test warning",
    )

    result.add_issue(issue)

    assert result.valid is True  # Warnings don't invalidate
    assert len(result.warnings) == 1
    assert result.has_warnings() is True


def test_validation_result_to_dict():
    """Test ValidationResult to_dict conversion."""
    result = ValidationResult(valid=False)
    result.add_issue(
        ValidationIssue(
            level=ValidationLevel.ERROR,
            code="TEST",
            message="Test error",
            field="test.field",
        )
    )

    data = result.to_dict()

    assert data["valid"] is False
    assert len(data["errors"]) == 1
    assert data["errors"][0]["code"] == "TEST"


def test_validation_issue_to_dict():
    """Test ValidationIssue to_dict conversion."""
    issue = ValidationIssue(
        level=ValidationLevel.ERROR,
        code="TEST_CODE",
        message="Test message",
        field="test.field",
        details={"key": "value"},
    )

    data = issue.to_dict()

    assert data["level"] == "error"
    assert data["code"] == "TEST_CODE"
    assert data["message"] == "Test message"
    assert data["field"] == "test.field"
    assert data["details"]["key"] == "value"


# ============================================================================
# Comprehensive Validation Tests
# ============================================================================


def test_validate_and_report(mapping_service, valid_mapping):
    """Test comprehensive validation and report."""
    result = mapping_service.validate_and_report(valid_mapping)

    assert result.valid is True
    assert len(result.errors) == 0


def test_validate_and_report_with_conflicts(mapping_service, mapping_with_conflicts):
    """Test comprehensive validation detects conflicts."""
    result = mapping_service.validate_and_report(mapping_with_conflicts)

    assert result.valid is False
    assert any(e.code == "CONFLICT_DETECTED" or e.code == "PIN_CONFLICT" for e in result.errors)


# ============================================================================
# Legacy Function Tests
# ============================================================================


def test_legacy_validate_mapping_structure(valid_mapping):
    """Test legacy validation function."""
    result = validate_mapping_structure(valid_mapping)

    assert result["valid"] is True
    assert len(result["errors"]) == 0


def test_legacy_detect_pin_conflicts(mapping_with_conflicts):
    """Test legacy conflict detection function."""
    conflicts = detect_pin_conflicts(mapping_with_conflicts["mappings"])

    assert len(conflicts) > 0
    assert conflicts[0]["type"] == "pin_conflict"


# ============================================================================
# Edge Case Tests
# ============================================================================


def test_validate_empty_mappings(mapping_service):
    """Test validation with empty mappings."""
    mapping = {
        "version": "1.0",
        "board": {"vid": "0x045e", "pid": "0x028e", "name": "Test"},
        "mappings": {},
    }

    result = mapping_service.validate_structure(mapping)

    assert result.valid is True  # Empty is valid


def test_validate_hex_without_prefix(mapping_service):
    """Test validation accepts hex without 0x prefix."""
    mapping = {
        "version": "1.0",
        "board": {
            "vid": "045e",  # No 0x prefix
            "pid": "028e",
            "name": "Test",
        },
        "mappings": {},
    }

    result = mapping_service.validate_structure(mapping)

    assert result.valid is True


def test_validate_uppercase_hex(mapping_service):
    """Test validation accepts uppercase hex."""
    mapping = {
        "version": "1.0",
        "board": {
            "vid": "0X045E",  # Uppercase
            "pid": "0X028E",
            "name": "Test",
        },
        "mappings": {},
    }

    result = mapping_service.validate_structure(mapping)

    assert result.valid is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
