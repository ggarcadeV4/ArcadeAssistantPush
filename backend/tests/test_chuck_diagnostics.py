"""Comprehensive pytest tests for chuck/diagnostics.py.

Coverage Goals:
- >80% line coverage
- All diagnostic paths tested
- Health check system
- Event handling and history
- Metrics collection

Test Categories:
1. Health check registration and execution
2. Diagnostic event logging
3. Event history management
4. Event handler system
5. Metrics collection and statistics
6. Report generation
7. Module-level functions
"""

import pytest
import time
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.chuck.diagnostics import (
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


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def diagnostics_service(tmp_path):
    """Create diagnostics service instance."""
    log_file = tmp_path / "diagnostics.jsonl"
    return DiagnosticsService(log_file=log_file, max_history=10, enable_metrics=True)


@pytest.fixture
def sample_health_check():
    """Sample health check result."""
    return HealthCheck(
        component="test_component",
        status=HealthStatus.HEALTHY,
        message="Component is healthy",
        details={"version": "1.0"},
        metrics={"latency_ms": 5.0},
    )


@pytest.fixture
def sample_diagnostic_event():
    """Sample diagnostic event."""
    return DiagnosticEvent(
        level=DiagnosticLevel.INFO,
        code="TEST_EVENT",
        message="Test event",
        component="test_component",
        data={"key": "value"},
    )


# ============================================================================
# Health Check Tests
# ============================================================================


def test_register_health_check(diagnostics_service):
    """Test health check registration."""

    def mock_check():
        return HealthCheck(
            component="test", status=HealthStatus.HEALTHY, message="OK"
        )

    diagnostics_service.register_health_check("test", mock_check)

    assert "test" in diagnostics_service._health_checks


def test_unregister_health_check(diagnostics_service):
    """Test health check unregistration."""

    def mock_check():
        return HealthCheck(
            component="test", status=HealthStatus.HEALTHY, message="OK"
        )

    diagnostics_service.register_health_check("test", mock_check)
    diagnostics_service.unregister_health_check("test")

    assert "test" not in diagnostics_service._health_checks


def test_run_health_check_success(diagnostics_service):
    """Test running a successful health check."""

    def mock_check():
        return HealthCheck(
            component="test", status=HealthStatus.HEALTHY, message="All good"
        )

    diagnostics_service.register_health_check("test", mock_check)
    result = diagnostics_service.run_health_check("test")

    assert result is not None
    assert result.status == HealthStatus.HEALTHY
    assert result.component == "test"


def test_run_health_check_not_registered(diagnostics_service):
    """Test running health check for unregistered component."""
    result = diagnostics_service.run_health_check("nonexistent")

    assert result is None


def test_run_health_check_exception(diagnostics_service):
    """Test health check handles exceptions."""

    def failing_check():
        raise Exception("Check failed")

    diagnostics_service.register_health_check("failing", failing_check)
    result = diagnostics_service.run_health_check("failing")

    assert result is not None
    assert result.status == HealthStatus.UNHEALTHY
    assert "failed" in result.message.lower()


def test_run_all_health_checks(diagnostics_service):
    """Test running all registered health checks."""

    def check1():
        return HealthCheck(
            component="comp1", status=HealthStatus.HEALTHY, message="OK"
        )

    def check2():
        return HealthCheck(
            component="comp2", status=HealthStatus.DEGRADED, message="Degraded"
        )

    diagnostics_service.register_health_check("comp1", check1)
    diagnostics_service.register_health_check("comp2", check2)

    results = diagnostics_service.run_health_checks()

    assert len(results) == 2
    assert any(r.component == "comp1" for r in results)
    assert any(r.component == "comp2" for r in results)


# ============================================================================
# Diagnostic Event Tests
# ============================================================================


def test_log_event_adds_to_history(diagnostics_service, sample_diagnostic_event):
    """Test that logging event adds to history."""
    diagnostics_service.log_event(sample_diagnostic_event)

    assert len(diagnostics_service._event_history) == 1
    assert diagnostics_service._event_history[0].code == "TEST_EVENT"


def test_log_event_trims_history(diagnostics_service):
    """Test that event history is trimmed when exceeding max."""
    # max_history = 10
    for i in range(15):
        event = DiagnosticEvent(
            level=DiagnosticLevel.INFO,
            code=f"EVENT_{i}",
            message=f"Event {i}",
            component="test",
        )
        diagnostics_service.log_event(event)

    assert len(diagnostics_service._event_history) == 10
    # Should keep the most recent events
    assert diagnostics_service._event_history[-1].code == "EVENT_14"


def test_log_event_writes_to_file(diagnostics_service, sample_diagnostic_event):
    """Test that events are written to log file."""
    diagnostics_service.log_event(sample_diagnostic_event)

    assert diagnostics_service.log_file.exists()
    content = diagnostics_service.log_file.read_text()
    assert "TEST_EVENT" in content


def test_log_event_emits_to_handlers(diagnostics_service, sample_diagnostic_event):
    """Test that events are emitted to handlers."""
    handler = Mock()
    diagnostics_service.register_event_handler(handler)

    diagnostics_service.log_event(sample_diagnostic_event)

    handler.assert_called_once()


# ============================================================================
# Event Handler Tests
# ============================================================================


def test_register_event_handler(diagnostics_service):
    """Test event handler registration."""
    handler = Mock()
    diagnostics_service.register_event_handler(handler)

    assert handler in diagnostics_service._event_handlers


def test_unregister_event_handler(diagnostics_service):
    """Test event handler unregistration."""
    handler = Mock()
    diagnostics_service.register_event_handler(handler)
    diagnostics_service.unregister_event_handler(handler)

    assert handler not in diagnostics_service._event_handlers


def test_event_handler_error_handling(diagnostics_service):
    """Test that event handler errors don't crash service."""

    def failing_handler(event):
        raise Exception("Handler error")

    diagnostics_service.register_event_handler(failing_handler)
    event = DiagnosticEvent(
        level=DiagnosticLevel.INFO,
        code="TEST",
        message="Test",
        component="test",
    )

    # Should not raise exception
    diagnostics_service.log_event(event)


# ============================================================================
# Event History Tests
# ============================================================================


def test_get_event_history_all(diagnostics_service):
    """Test getting all event history."""
    for i in range(5):
        event = DiagnosticEvent(
            level=DiagnosticLevel.INFO,
            code=f"EVENT_{i}",
            message=f"Event {i}",
            component="test",
        )
        diagnostics_service.log_event(event)

    history = diagnostics_service.get_event_history()

    assert len(history) == 5


def test_get_event_history_filter_by_component(diagnostics_service):
    """Test filtering event history by component."""
    for i in range(3):
        event = DiagnosticEvent(
            level=DiagnosticLevel.INFO,
            code=f"EVENT_{i}",
            message=f"Event {i}",
            component="comp1" if i < 2 else "comp2",
        )
        diagnostics_service.log_event(event)

    history = diagnostics_service.get_event_history(component="comp1")

    assert len(history) == 2
    assert all(e.component == "comp1" for e in history)


def test_get_event_history_filter_by_level(diagnostics_service):
    """Test filtering event history by level."""
    levels = [DiagnosticLevel.INFO, DiagnosticLevel.WARNING, DiagnosticLevel.ERROR]
    for i, level in enumerate(levels):
        event = DiagnosticEvent(
            level=level, code=f"EVENT_{i}", message=f"Event {i}", component="test"
        )
        diagnostics_service.log_event(event)

    history = diagnostics_service.get_event_history(level=DiagnosticLevel.ERROR)

    assert len(history) == 1
    assert history[0].level == DiagnosticLevel.ERROR


def test_get_event_history_with_limit(diagnostics_service):
    """Test limiting event history results."""
    for i in range(10):
        event = DiagnosticEvent(
            level=DiagnosticLevel.INFO,
            code=f"EVENT_{i}",
            message=f"Event {i}",
            component="test",
        )
        diagnostics_service.log_event(event)

    history = diagnostics_service.get_event_history(limit=3)

    assert len(history) == 3
    # Should return most recent
    assert history[-1].code == "EVENT_9"


def test_clear_event_history(diagnostics_service):
    """Test clearing event history."""
    event = DiagnosticEvent(
        level=DiagnosticLevel.INFO,
        code="TEST",
        message="Test",
        component="test",
    )
    diagnostics_service.log_event(event)

    diagnostics_service.clear_event_history()

    assert len(diagnostics_service._event_history) == 0


# ============================================================================
# Metrics Tests
# ============================================================================


def test_record_metric(diagnostics_service):
    """Test recording a metric."""
    diagnostics_service.record_metric("latency_ms", 5.0)

    assert "latency_ms" in diagnostics_service._metrics
    assert diagnostics_service._metrics["latency_ms"] == [5.0]


def test_record_multiple_metrics(diagnostics_service):
    """Test recording multiple metric values."""
    for i in range(5):
        diagnostics_service.record_metric("latency_ms", float(i))

    assert len(diagnostics_service._metrics["latency_ms"]) == 5


def test_metrics_trim_to_1000(diagnostics_service):
    """Test that metrics are trimmed to 1000 values."""
    for i in range(1500):
        diagnostics_service.record_metric("test_metric", float(i))

    assert len(diagnostics_service._metrics["test_metric"]) == 1000


def test_get_metrics_single(diagnostics_service):
    """Test getting statistics for a single metric."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    for val in values:
        diagnostics_service.record_metric("test_metric", val)

    stats = diagnostics_service.get_metrics("test_metric")

    assert stats["count"] == 5
    assert stats["min"] == 1.0
    assert stats["max"] == 5.0
    assert stats["avg"] == 3.0
    assert stats["latest"] == 5.0


def test_get_metrics_all(diagnostics_service):
    """Test getting all metrics."""
    diagnostics_service.record_metric("metric1", 1.0)
    diagnostics_service.record_metric("metric2", 2.0)

    all_metrics = diagnostics_service.get_metrics()

    assert "metric1" in all_metrics
    assert "metric2" in all_metrics


def test_get_metrics_empty(diagnostics_service):
    """Test getting metrics when none exist."""
    stats = diagnostics_service.get_metrics("nonexistent")

    assert stats["count"] == 0
    assert stats["min"] is None
    assert stats["max"] is None


def test_metrics_disabled(tmp_path):
    """Test that metrics are not recorded when disabled."""
    service = DiagnosticsService(enable_metrics=False)
    service.record_metric("test", 1.0)

    assert len(service._metrics) == 0


# ============================================================================
# Report Generation Tests
# ============================================================================


def test_generate_report_healthy(diagnostics_service):
    """Test generating report with all healthy checks."""

    def healthy_check():
        return HealthCheck(
            component="test", status=HealthStatus.HEALTHY, message="OK"
        )

    diagnostics_service.register_health_check("test", healthy_check)
    report = diagnostics_service.generate_report()

    assert report.overall_status == HealthStatus.HEALTHY
    assert len(report.health_checks) == 1
    assert report.summary["healthy_components"] == 1


def test_generate_report_degraded(diagnostics_service):
    """Test generating report with degraded status."""

    def degraded_check():
        return HealthCheck(
            component="test", status=HealthStatus.DEGRADED, message="Degraded"
        )

    diagnostics_service.register_health_check("test", degraded_check)
    report = diagnostics_service.generate_report()

    assert report.overall_status == HealthStatus.DEGRADED
    assert report.summary["degraded_components"] == 1


def test_generate_report_unhealthy(diagnostics_service):
    """Test generating report with unhealthy status."""

    def unhealthy_check():
        return HealthCheck(
            component="test", status=HealthStatus.UNHEALTHY, message="Unhealthy"
        )

    diagnostics_service.register_health_check("test", unhealthy_check)
    report = diagnostics_service.generate_report()

    assert report.overall_status == HealthStatus.UNHEALTHY
    assert report.summary["unhealthy_components"] == 1


def test_generate_report_includes_events(diagnostics_service):
    """Test that report includes recent events."""
    for i in range(10):
        event = DiagnosticEvent(
            level=DiagnosticLevel.INFO,
            code=f"EVENT_{i}",
            message=f"Event {i}",
            component="test",
        )
        diagnostics_service.log_event(event)

    report = diagnostics_service.generate_report()

    # Report should include last 50 events (all 10 in this case)
    assert len(report.events) == 10


def test_generate_report_includes_metrics(diagnostics_service):
    """Test that report includes metrics."""
    diagnostics_service.record_metric("test_metric", 5.0)

    report = diagnostics_service.generate_report()

    assert "metrics" in report.summary
    assert "test_metric" in report.summary["metrics"]


def test_report_to_dict(diagnostics_service):
    """Test converting report to dictionary."""

    def healthy_check():
        return HealthCheck(
            component="test", status=HealthStatus.HEALTHY, message="OK"
        )

    diagnostics_service.register_health_check("test", healthy_check)
    report = diagnostics_service.generate_report()

    report_dict = report.to_dict()

    assert report_dict["overall_status"] == "healthy"
    assert len(report_dict["health_checks"]) == 1
    assert "summary" in report_dict


# ============================================================================
# Data Model Tests
# ============================================================================


def test_health_check_to_dict(sample_health_check):
    """Test HealthCheck to_dict conversion."""
    data = sample_health_check.to_dict()

    assert data["component"] == "test_component"
    assert data["status"] == "healthy"
    assert data["message"] == "Component is healthy"
    assert "details" in data
    assert "metrics" in data


def test_diagnostic_event_to_dict(sample_diagnostic_event):
    """Test DiagnosticEvent to_dict conversion."""
    data = sample_diagnostic_event.to_dict()

    assert data["level"] == "info"
    assert data["code"] == "TEST_EVENT"
    assert data["message"] == "Test event"
    assert data["component"] == "test_component"
    assert "data" in data


# ============================================================================
# Module-level Function Tests
# ============================================================================


def test_get_diagnostics_service_singleton():
    """Test that get_diagnostics_service returns singleton."""
    service1 = get_diagnostics_service()
    service2 = get_diagnostics_service()

    assert service1 is service2


def test_log_diagnostic_function():
    """Test module-level log_diagnostic function."""
    service = get_diagnostics_service()
    initial_count = len(service._event_history)

    log_diagnostic(
        component="test",
        code="TEST",
        message="Test message",
        level=DiagnosticLevel.INFO,
    )

    assert len(service._event_history) > initial_count


def test_run_health_check_function():
    """Test module-level run_health_check function."""
    service = get_diagnostics_service()

    def mock_check():
        return HealthCheck(
            component="test", status=HealthStatus.HEALTHY, message="OK"
        )

    service.register_health_check("test", mock_check)
    result = run_health_check("test")

    assert result is not None
    assert result.status == HealthStatus.HEALTHY


# ============================================================================
# Edge Case Tests
# ============================================================================


def test_log_file_creation_on_first_event(tmp_path):
    """Test that log file is created on first event."""
    log_file = tmp_path / "new_log.jsonl"
    service = DiagnosticsService(log_file=log_file)

    assert not log_file.exists()

    event = DiagnosticEvent(
        level=DiagnosticLevel.INFO,
        code="TEST",
        message="Test",
        component="test",
    )
    service.log_event(event)

    assert log_file.exists()


def test_health_check_with_metrics(diagnostics_service):
    """Test health check with performance metrics."""

    def check_with_metrics():
        return HealthCheck(
            component="test",
            status=HealthStatus.HEALTHY,
            message="OK",
            metrics={"latency_ms": 5.0, "cpu_percent": 10.0},
        )

    diagnostics_service.register_health_check("test", check_with_metrics)
    result = diagnostics_service.run_health_check("test")

    assert "latency_ms" in result.metrics
    assert "cpu_percent" in result.metrics


def test_event_with_trace_id(diagnostics_service):
    """Test event with trace ID for correlation."""
    event = DiagnosticEvent(
        level=DiagnosticLevel.INFO,
        code="TEST",
        message="Test",
        component="test",
        trace_id="trace-123",
    )

    diagnostics_service.log_event(event)

    assert event.trace_id == "trace-123"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
