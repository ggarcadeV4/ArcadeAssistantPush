"""Arcade Controller Diagnostics Service

Health checks, diagnostic events, and system monitoring for controller boards.
Provides comprehensive diagnostic reporting and event streaming.

Features:
- Health check system
- Diagnostic event generation
- Device status monitoring
- Performance metrics
- Error tracking and reporting
- Diagnostic history
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health check status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class DiagnosticLevel(Enum):
    """Diagnostic event severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class DiagnosticsError(Exception):
    """Base exception for diagnostics errors."""
    pass


@dataclass
class HealthCheck:
    """Health check result."""
    component: str
    status: HealthStatus
    message: str
    timestamp: float = dataclass_field(default_factory=time.time)
    details: Dict[str, Any] = dataclass_field(default_factory=dict)
    metrics: Dict[str, float] = dataclass_field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "component": self.component,
            "status": self.status.value,
            "message": self.message,
            "timestamp": self.timestamp,
            "details": self.details,
            "metrics": self.metrics,
        }


@dataclass
class DiagnosticEvent:
    """Diagnostic event with context."""
    level: DiagnosticLevel
    code: str
    message: str
    component: str
    timestamp: float = dataclass_field(default_factory=time.time)
    data: Dict[str, Any] = dataclass_field(default_factory=dict)
    trace_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "level": self.level.value,
            "code": self.code,
            "message": self.message,
            "component": self.component,
            "timestamp": self.timestamp,
            "data": self.data,
            "trace_id": self.trace_id,
        }


@dataclass
class DiagnosticReport:
    """Comprehensive diagnostic report."""
    overall_status: HealthStatus
    health_checks: List[HealthCheck] = dataclass_field(default_factory=list)
    events: List[DiagnosticEvent] = dataclass_field(default_factory=list)
    summary: Dict[str, Any] = dataclass_field(default_factory=dict)
    generated_at: float = dataclass_field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "overall_status": self.overall_status.value,
            "health_checks": [hc.to_dict() for hc in self.health_checks],
            "events": [e.to_dict() for e in self.events],
            "summary": self.summary,
            "generated_at": self.generated_at,
        }


class DiagnosticsService:
    """Service for controller diagnostics and health monitoring."""

    def __init__(
        self,
        log_file: Optional[Path] = None,
        max_history: int = 100,
        enable_metrics: bool = True,
    ):
        """Initialize diagnostics service.

        Args:
            log_file: Path to diagnostic log file (optional)
            max_history: Maximum events to keep in history
            enable_metrics: Enable performance metrics collection
        """
        self.log_file = log_file
        self.max_history = max_history
        self.enable_metrics = enable_metrics

        # Event history
        self._event_history: List[DiagnosticEvent] = []

        # Health check registry
        self._health_checks: Dict[str, Callable[[], HealthCheck]] = {}

        # Event handlers
        self._event_handlers: List[Callable[[DiagnosticEvent], None]] = []

        # Metrics
        self._metrics: Dict[str, List[float]] = {}

    def register_health_check(
        self, component: str, check_func: Callable[[], HealthCheck]
    ) -> None:
        """Register a health check function.

        Args:
            component: Component name
            check_func: Function that returns HealthCheck
        """
        self._health_checks[component] = check_func
        logger.debug(f"Registered health check for {component}")

    def unregister_health_check(self, component: str) -> None:
        """Unregister a health check.

        Args:
            component: Component name to unregister
        """
        if component in self._health_checks:
            del self._health_checks[component]
            logger.debug(f"Unregistered health check for {component}")

    def run_health_checks(self) -> List[HealthCheck]:
        """Run all registered health checks.

        Returns:
            List of HealthCheck results
        """
        results = []
        for component, check_func in self._health_checks.items():
            try:
                result = check_func()
                results.append(result)
            except Exception as e:
                logger.error(f"Health check failed for {component}: {e}")
                results.append(
                    HealthCheck(
                        component=component,
                        status=HealthStatus.UNHEALTHY,
                        message=f"Health check failed: {str(e)}",
                        details={"error": str(e)},
                    )
                )
        return results

    def run_health_check(self, component: str) -> Optional[HealthCheck]:
        """Run health check for specific component.

        Args:
            component: Component name

        Returns:
            HealthCheck result or None if not registered
        """
        check_func = self._health_checks.get(component)
        if check_func:
            try:
                return check_func()
            except Exception as e:
                logger.error(f"Health check failed for {component}: {e}")
                return HealthCheck(
                    component=component,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Health check failed: {str(e)}",
                    details={"error": str(e)},
                )
        return None

    def log_event(self, event: DiagnosticEvent) -> None:
        """Log a diagnostic event.

        Args:
            event: DiagnosticEvent to log
        """
        # Add to history
        self._event_history.append(event)

        # Trim history if needed
        if len(self._event_history) > self.max_history:
            self._event_history = self._event_history[-self.max_history :]

        # Write to log file if configured
        if self.log_file:
            try:
                self.log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event.to_dict()) + "\n")
            except Exception as e:
                logger.error(f"Failed to write diagnostic event to log: {e}")

        # Emit to handlers
        self._emit_event(event)

        # Log to standard logger
        log_func = {
            DiagnosticLevel.INFO: logger.info,
            DiagnosticLevel.WARNING: logger.warning,
            DiagnosticLevel.ERROR: logger.error,
            DiagnosticLevel.CRITICAL: logger.critical,
        }.get(event.level, logger.info)

        log_func(f"[{event.component}] {event.code}: {event.message}")

    def register_event_handler(
        self, handler: Callable[[DiagnosticEvent], None]
    ) -> None:
        """Register event handler for diagnostic events.

        Args:
            handler: Callback function that receives DiagnosticEvent
        """
        self._event_handlers.append(handler)
        logger.debug("Registered diagnostic event handler")

    def unregister_event_handler(
        self, handler: Callable[[DiagnosticEvent], None]
    ) -> None:
        """Unregister event handler.

        Args:
            handler: Callback function to remove
        """
        if handler in self._event_handlers:
            self._event_handlers.remove(handler)
            logger.debug("Unregistered diagnostic event handler")

    def _emit_event(self, event: DiagnosticEvent) -> None:
        """Emit event to all registered handlers.

        Args:
            event: DiagnosticEvent to emit
        """
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler failed: {e}")

    def get_event_history(
        self,
        component: Optional[str] = None,
        level: Optional[DiagnosticLevel] = None,
        limit: Optional[int] = None,
    ) -> List[DiagnosticEvent]:
        """Get event history with optional filtering.

        Args:
            component: Filter by component name
            level: Filter by diagnostic level
            limit: Maximum number of events to return

        Returns:
            List of DiagnosticEvent objects
        """
        events = self._event_history

        # Filter by component
        if component:
            events = [e for e in events if e.component == component]

        # Filter by level
        if level:
            events = [e for e in events if e.level == level]

        # Apply limit
        if limit:
            events = events[-limit:]

        return events

    def clear_event_history(self) -> None:
        """Clear all event history."""
        self._event_history.clear()
        logger.debug("Cleared diagnostic event history")

    def record_metric(self, metric_name: str, value: float) -> None:
        """Record a performance metric.

        Args:
            metric_name: Name of the metric
            value: Metric value
        """
        if not self.enable_metrics:
            return

        if metric_name not in self._metrics:
            self._metrics[metric_name] = []

        self._metrics[metric_name].append(value)

        # Keep only last 1000 values
        if len(self._metrics[metric_name]) > 1000:
            self._metrics[metric_name] = self._metrics[metric_name][-1000:]

    def get_metrics(self, metric_name: Optional[str] = None) -> Dict[str, Any]:
        """Get performance metrics with statistics.

        Args:
            metric_name: Specific metric name (optional, returns all if None)

        Returns:
            Dictionary with metric statistics
        """
        if metric_name:
            values = self._metrics.get(metric_name, [])
            return self._compute_metric_stats(metric_name, values)
        else:
            return {
                name: self._compute_metric_stats(name, values)
                for name, values in self._metrics.items()
            }

    def _compute_metric_stats(
        self, name: str, values: List[float]
    ) -> Dict[str, Any]:
        """Compute statistics for a metric.

        Args:
            name: Metric name
            values: List of metric values

        Returns:
            Dictionary with statistics
        """
        if not values:
            return {
                "name": name,
                "count": 0,
                "min": None,
                "max": None,
                "avg": None,
                "latest": None,
            }

        return {
            "name": name,
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "latest": values[-1] if values else None,
        }

    def generate_report(self) -> DiagnosticReport:
        """Generate comprehensive diagnostic report.

        Returns:
            DiagnosticReport with all health checks and events
        """
        # Run all health checks
        health_checks = self.run_health_checks()

        # Determine overall status
        overall_status = HealthStatus.HEALTHY
        if any(hc.status == HealthStatus.UNHEALTHY for hc in health_checks):
            overall_status = HealthStatus.UNHEALTHY
        elif any(hc.status == HealthStatus.DEGRADED for hc in health_checks):
            overall_status = HealthStatus.DEGRADED
        elif any(hc.status == HealthStatus.UNKNOWN for hc in health_checks):
            overall_status = HealthStatus.UNKNOWN

        # Get recent events
        events = self.get_event_history(limit=50)

        # Build summary
        summary = {
            "total_health_checks": len(health_checks),
            "healthy_components": sum(
                1 for hc in health_checks if hc.status == HealthStatus.HEALTHY
            ),
            "degraded_components": sum(
                1 for hc in health_checks if hc.status == HealthStatus.DEGRADED
            ),
            "unhealthy_components": sum(
                1 for hc in health_checks if hc.status == HealthStatus.UNHEALTHY
            ),
            "total_events": len(self._event_history),
            "recent_errors": sum(
                1
                for e in events
                if e.level in (DiagnosticLevel.ERROR, DiagnosticLevel.CRITICAL)
            ),
            "metrics": self.get_metrics(),
        }

        return DiagnosticReport(
            overall_status=overall_status,
            health_checks=health_checks,
            events=events,
            summary=summary,
        )


# Module-level singleton
_diagnostics_service: Optional[DiagnosticsService] = None


def get_diagnostics_service(
    log_file: Optional[Path] = None,
    max_history: int = 100,
    enable_metrics: bool = True,
) -> DiagnosticsService:
    """Get or create singleton diagnostics service.

    Args:
        log_file: Path to diagnostic log file (only used on first call)
        max_history: Maximum events in history (only used on first call)
        enable_metrics: Enable metrics (only used on first call)

    Returns:
        DiagnosticsService instance
    """
    global _diagnostics_service

    if _diagnostics_service is None:
        _diagnostics_service = DiagnosticsService(
            log_file=log_file, max_history=max_history, enable_metrics=enable_metrics
        )
        logger.info("Created diagnostics service")

    return _diagnostics_service


# Convenience functions


def log_diagnostic(
    component: str,
    code: str,
    message: str,
    level: DiagnosticLevel = DiagnosticLevel.INFO,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """Log a diagnostic event using singleton service.

    Args:
        component: Component name
        code: Diagnostic code
        message: Event message
        level: Diagnostic level
        data: Additional event data
    """
    service = get_diagnostics_service()
    event = DiagnosticEvent(
        level=level,
        code=code,
        message=message,
        component=component,
        data=data or {},
    )
    service.log_event(event)


def run_health_check(component: str) -> Optional[HealthCheck]:
    """Run health check for component using singleton service.

    Args:
        component: Component name

    Returns:
        HealthCheck result or None
    """
    service = get_diagnostics_service()
    return service.run_health_check(component)
