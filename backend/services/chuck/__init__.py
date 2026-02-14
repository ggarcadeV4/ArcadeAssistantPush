"""Controller Chuck Service Package

Modular services for arcade controller board detection, mapping, and diagnostics.
Provides injectable backends for testing and async event-driven architecture.
"""

from .detection import (
    BoardDetectionService,
    BoardDetectionError,
    BoardNotFoundError,
    BoardTimeoutError,
    detect_board,
    get_detection_service,
)

from .mapping import (
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

from .diagnostics import (
    DiagnosticsService,
    DiagnosticsError,
    HealthCheck,
    HealthStatus,
    DiagnosticEvent,
    DiagnosticLevel,
    DiagnosticReport,
    get_diagnostics_service,
    log_diagnostic,
    run_health_check,
)
from .pactotech import PactoTechBoard

__all__ = [
    # Detection
    "BoardDetectionService",
    "BoardDetectionError",
    "BoardNotFoundError",
    "BoardTimeoutError",
    "detect_board",
    "get_detection_service",
    # Mapping
    "MappingService",
    "MappingError",
    "ValidationError",
    "ConflictError",
    "CapabilityError",
    "ValidationResult",
    "ValidationIssue",
    "ValidationLevel",
    "BoardCapabilities",
    "validate_mapping_structure",
    "detect_pin_conflicts",
    # Diagnostics
    "DiagnosticsService",
    "DiagnosticsError",
    "HealthCheck",
    "HealthStatus",
    "DiagnosticEvent",
    "DiagnosticLevel",
    "DiagnosticReport",
    "get_diagnostics_service",
    "log_diagnostic",
    "run_health_check",
    # Hardware helpers
    "PactoTechBoard",
]
