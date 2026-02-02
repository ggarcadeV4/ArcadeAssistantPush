"""Arcade Controller Mapping Service

Validation, conflict detection, and diff generation for controller mappings.
Provides injectable backend for testing and comprehensive validation logic.

Features:
- Mapping structure validation
- Pin conflict detection
- Hardware capability validation
- Diff generation
- Concurrent edit protection (optimistic locking)
- Comprehensive error reporting
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from functools import lru_cache

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """Validation severity levels."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class MappingError(Exception):
    """Base exception for mapping errors."""
    pass


class ValidationError(MappingError):
    """Mapping validation failed."""
    pass


class ConflictError(MappingError):
    """Pin or resource conflict detected."""
    pass


class CapabilityError(MappingError):
    """Hardware capability exceeded."""
    pass


@dataclass
class ValidationIssue:
    """Single validation issue."""
    level: ValidationLevel
    code: str
    message: str
    field: Optional[str] = None
    details: Dict[str, Any] = dataclass_field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "level": self.level.value,
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "details": self.details,
        }


@dataclass
class ValidationResult:
    """Validation result with issues."""
    valid: bool
    errors: List[ValidationIssue] = dataclass_field(default_factory=list)
    warnings: List[ValidationIssue] = dataclass_field(default_factory=list)
    info: List[ValidationIssue] = dataclass_field(default_factory=list)

    def has_errors(self) -> bool:
        """Check if any errors exist."""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """Check if any warnings exist."""
        return len(self.warnings) > 0

    def add_issue(self, issue: ValidationIssue) -> None:
        """Add issue to appropriate list."""
        if issue.level == ValidationLevel.ERROR:
            self.errors.append(issue)
            self.valid = False
        elif issue.level == ValidationLevel.WARNING:
            self.warnings.append(issue)
        else:
            self.info.append(issue)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "info": [i.to_dict() for i in self.info],
        }


@dataclass
class BoardCapabilities:
    """Hardware board capabilities."""
    max_buttons: int = 32
    max_axes: int = 8
    available_pins: Set[int] = dataclass_field(default_factory=lambda: set(range(1, 33)))
    supports_analog: bool = True
    supports_digital: bool = True
    name: str = "Generic Board"

    @classmethod
    def from_board_type(cls, board_type: str) -> BoardCapabilities:
        """Create capabilities from board type.

        Args:
            board_type: Board type identifier

        Returns:
            BoardCapabilities instance
        """
        # Common arcade board profiles
        profiles = {
            "ipac2": cls(
                max_buttons=32,
                available_pins=set(range(1, 33)),
                supports_analog=False,
                name="I-PAC 2",
            ),
            "ipac4": cls(
                max_buttons=64,
                available_pins=set(range(1, 65)),
                supports_analog=False,
                name="I-PAC 4",
            ),
            "zerog": cls(
                max_buttons=12,
                max_axes=2,
                available_pins=set(range(1, 13)),
                supports_analog=True,
                name="Zero Delay",
            ),
        }
        return profiles.get(board_type.lower(), cls())


class MappingService:
    """Service for mapping validation and conflict detection."""

    def __init__(
        self,
        capabilities: Optional[BoardCapabilities] = None,
        strict_validation: bool = False,
    ):
        """Initialize mapping service.

        Args:
            capabilities: Board hardware capabilities (optional)
            strict_validation: Enable strict validation mode
        """
        self.capabilities = capabilities or BoardCapabilities()
        self.strict_validation = strict_validation

    def validate_structure(self, mapping_data: Dict[str, Any]) -> ValidationResult:
        """Validate mapping structure and detect issues.

        Args:
            mapping_data: Mapping dictionary to validate

        Returns:
            ValidationResult with errors, warnings, and info
        """
        result = ValidationResult(valid=True)

        # Check required top-level keys
        required_keys = ["version", "board", "mappings"]
        for key in required_keys:
            if key not in mapping_data:
                result.add_issue(
                    ValidationIssue(
                        level=ValidationLevel.ERROR,
                        code="MISSING_KEY",
                        message=f"Missing required key: {key}",
                        field=key,
                    )
                )

        # Early return if critical errors
        if result.has_errors():
            return result

        # Validate board structure
        self._validate_board(mapping_data.get("board", {}), result)

        # Validate mappings
        self._validate_mappings(mapping_data.get("mappings", {}), result)

        return result

    def _validate_board(
        self, board: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate board configuration.

        Args:
            board: Board configuration dictionary
            result: ValidationResult to update
        """
        board_required = ["vid", "pid", "name"]
        for key in board_required:
            if key not in board:
                result.add_issue(
                    ValidationIssue(
                        level=ValidationLevel.ERROR,
                        code="MISSING_BOARD_KEY",
                        message=f"Missing board key: {key}",
                        field=f"board.{key}",
                    )
                )

        # Validate VID/PID format
        vid = board.get("vid", "")
        pid = board.get("pid", "")
        if vid and not self._is_valid_hex(vid):
            result.add_issue(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code="INVALID_VID",
                    message=f"Invalid VID format: {vid} (expected hex like 0x045e)",
                    field="board.vid",
                )
            )
        if pid and not self._is_valid_hex(pid):
            result.add_issue(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code="INVALID_PID",
                    message=f"Invalid PID format: {pid} (expected hex like 0x028e)",
                    field="board.pid",
                )
            )

    def _validate_mappings(
        self, mappings: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate mappings and detect conflicts.

        Args:
            mappings: Mappings dictionary
            result: ValidationResult to update
        """
        pin_usage: Dict[int, str] = {}  # Track pin assignments
        button_count = 0
        axis_count = 0

        for control_key, control_data in mappings.items():
            # Validate control structure
            if not isinstance(control_data, dict):
                result.add_issue(
                    ValidationIssue(
                        level=ValidationLevel.ERROR,
                        code="INVALID_CONTROL",
                        message=f"Invalid mapping for {control_key}: must be object",
                        field=f"mappings.{control_key}",
                    )
                )
                continue

            # Check required fields
            if "pin" not in control_data:
                result.add_issue(
                    ValidationIssue(
                        level=ValidationLevel.ERROR,
                        code="MISSING_PIN",
                        message=f"Missing pin for {control_key}",
                        field=f"mappings.{control_key}.pin",
                    )
                )
                continue

            if "type" not in control_data:
                result.add_issue(
                    ValidationIssue(
                        level=ValidationLevel.WARNING,
                        code="MISSING_TYPE",
                        message=f"Missing type for {control_key}",
                        field=f"mappings.{control_key}.type",
                    )
                )

            # Validate pin
            pin = control_data["pin"]
            control_type = control_data.get("type", "button")

            # Check pin conflicts
            if pin in pin_usage:
                result.add_issue(
                    ValidationIssue(
                        level=ValidationLevel.ERROR,
                        code="PIN_CONFLICT",
                        message=f"Pin {pin} conflict: used by both {pin_usage[pin]} and {control_key}",
                        field=f"mappings.{control_key}.pin",
                        details={
                            "pin": pin,
                            "conflicting_controls": [pin_usage[pin], control_key],
                        },
                    )
                )
            else:
                pin_usage[pin] = control_key

            # Check pin availability
            if pin not in self.capabilities.available_pins:
                result.add_issue(
                    ValidationIssue(
                        level=ValidationLevel.ERROR,
                        code="INVALID_PIN",
                        message=f"Pin {pin} not available on {self.capabilities.name}",
                        field=f"mappings.{control_key}.pin",
                        details={
                            "pin": pin,
                            "available_pins": sorted(self.capabilities.available_pins),
                        },
                    )
                )

            # Count by type
            if control_type == "button":
                button_count += 1
            elif control_type in ("axis", "analog"):
                axis_count += 1

        # Check capability limits
        if button_count > self.capabilities.max_buttons:
            result.add_issue(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code="TOO_MANY_BUTTONS",
                    message=f"Button count ({button_count}) exceeds board capacity ({self.capabilities.max_buttons})",
                    field="mappings",
                    details={
                        "count": button_count,
                        "max": self.capabilities.max_buttons,
                    },
                )
            )

        if axis_count > self.capabilities.max_axes:
            result.add_issue(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code="TOO_MANY_AXES",
                    message=f"Axis count ({axis_count}) exceeds board capacity ({self.capabilities.max_axes})",
                    field="mappings",
                    details={"count": axis_count, "max": self.capabilities.max_axes},
                )
            )

    def _is_valid_hex(self, value: str) -> bool:
        """Check if string is valid hex format.

        Args:
            value: String to validate

        Returns:
            True if valid hex
        """
        try:
            # Accept both 0x prefix and without
            if value.lower().startswith("0x"):
                int(value, 16)
            else:
                int(value, 16)
            return True
        except ValueError:
            return False

    def detect_conflicts(
        self, mappings: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Detect all conflicts in mappings.

        Args:
            mappings: Mappings dictionary

        Returns:
            List of conflict descriptions
        """
        conflicts = []
        pin_usage: Dict[int, List[str]] = {}

        # Build pin usage map
        for control_key, control_data in mappings.items():
            if not isinstance(control_data, dict):
                continue
            pin = control_data.get("pin")
            if pin is not None:
                if pin not in pin_usage:
                    pin_usage[pin] = []
                pin_usage[pin].append(control_key)

        # Find conflicts
        for pin, controls in pin_usage.items():
            if len(controls) > 1:
                conflicts.append(
                    {
                        "type": "pin_conflict",
                        "pin": pin,
                        "controls": controls,
                        "severity": "error",
                        "message": f"Pin {pin} assigned to multiple controls: {', '.join(controls)}",
                    }
                )

        return conflicts

    def generate_diff(
        self,
        current_mappings: Dict[str, Any],
        new_mappings: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate diff between current and new mappings.

        Args:
            current_mappings: Current mapping data
            new_mappings: New mapping data

        Returns:
            Diff summary with changes
        """
        changes = {
            "added": [],
            "removed": [],
            "modified": [],
            "unchanged": [],
        }

        current_controls = current_mappings.get("mappings", {})
        new_controls = new_mappings.get("mappings", {})

        all_keys = set(current_controls.keys()) | set(new_controls.keys())

        for key in all_keys:
            if key not in current_controls:
                changes["added"].append(
                    {"control": key, "new_value": new_controls[key]}
                )
            elif key not in new_controls:
                changes["removed"].append(
                    {"control": key, "old_value": current_controls[key]}
                )
            elif current_controls[key] != new_controls[key]:
                changes["modified"].append(
                    {
                        "control": key,
                        "old_value": current_controls[key],
                        "new_value": new_controls[key],
                    }
                )
            else:
                changes["unchanged"].append(key)

        # Check board changes
        current_board = current_mappings.get("board", {})
        new_board = new_mappings.get("board", {})
        if current_board != new_board:
            changes["board_changed"] = True
            changes["board_diff"] = {
                "old": current_board,
                "new": new_board,
            }

        return changes

    def check_concurrent_edit(
        self,
        mapping_data: Dict[str, Any],
        last_modified: Optional[str] = None,
    ) -> bool:
        """Check for concurrent edit conflicts (optimistic locking).

        Args:
            mapping_data: Current mapping data
            last_modified: Expected last modified timestamp

        Returns:
            True if safe to edit, False if conflict detected
        """
        if last_modified is None:
            # No timestamp provided, allow edit
            return True

        current_modified = mapping_data.get("last_modified")
        if current_modified is None:
            # No current timestamp, allow edit
            return True

        # Compare timestamps
        return current_modified == last_modified

    def validate_and_report(
        self, mapping_data: Dict[str, Any]
    ) -> ValidationResult:
        """Comprehensive validation with full report.

        Args:
            mapping_data: Mapping data to validate

        Returns:
            ValidationResult with all issues
        """
        result = self.validate_structure(mapping_data)

        # Add conflict detection
        conflicts = self.detect_conflicts(mapping_data.get("mappings", {}))
        for conflict in conflicts:
            result.add_issue(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code="CONFLICT_DETECTED",
                    message=conflict["message"],
                    details=conflict,
                )
            )

        return result


# Module-level functions for backwards compatibility


def validate_mapping_structure(mapping_data: Dict[str, Any]) -> Dict[str, Any]:
    """Legacy validation function for backwards compatibility.

    Args:
        mapping_data: Mapping data to validate

    Returns:
        Dictionary with valid, errors, warnings keys
    """
    service = MappingService()
    result = service.validate_structure(mapping_data)

    return {
        "valid": result.valid,
        "errors": [e.message for e in result.errors],
        "warnings": [w.message for w in result.warnings],
    }


def detect_pin_conflicts(mappings: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Detect pin conflicts in mappings.

    Args:
        mappings: Mappings dictionary

    Returns:
        List of conflicts
    """
    service = MappingService()
    return service.detect_conflicts(mappings)
