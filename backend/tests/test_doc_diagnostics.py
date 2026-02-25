"""Tests for Doc Diagnostics Router — GET /vitals endpoint.

Feature: agentic-repair-self-healing
Requirements: 2.1, 2.5, 2.6
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers.doc_diagnostics import router


def _create_test_app(drive_root: Path | None = None) -> FastAPI:
    """Create a minimal FastAPI app with the doc_diagnostics router."""
    app = FastAPI()
    app.include_router(router, prefix="/api/doc")
    if drive_root is not None:
        app.state.drive_root = drive_root
    return app


class TestGetVitals:
    """Unit tests for GET /api/doc/vitals."""

    def test_successful_vitals_response_schema(self):
        """Vitals response contains all required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app = _create_test_app(Path(tmpdir))
            client = TestClient(app)

            # Mock WMI to avoid Windows dependency
            import sys
            mock_wmi = MagicMock()
            mock_wmi.WMI.return_value.Win32_PnPEntity.return_value = []
            with patch.dict(sys.modules, {"wmi": mock_wmi}):
                resp = client.get("/api/doc/vitals")

            assert resp.status_code == 200
            data = resp.json()

            # Required top-level keys
            assert "drive_latency_ms" in data
            assert "cpu_percent" in data
            assert "memory_percent" in data
            assert "memory_used_gb" in data
            assert "memory_total_gb" in data
            assert "hardware_bio" in data
            assert "timestamp" in data
            assert "errors" in data

            # drive_latency_ms should be a number (temp dir is accessible)
            assert isinstance(data["drive_latency_ms"], (int, float))

            # hardware_bio should have expected structure
            bio = data["hardware_bio"]
            assert "devices" in bio
            assert "device_count" in bio
            assert "scan_timestamp" in bio

    def test_drive_latency_failure_returns_null(self):
        """When drive latency test fails, drive_latency_ms is null."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app = _create_test_app(Path(tmpdir))
            client = TestClient(app)

            import sys
            mock_wmi = MagicMock()
            mock_wmi.WMI.return_value.Win32_PnPEntity.return_value = []

            # Mock the latency function to simulate failure
            with patch.dict(sys.modules, {"wmi": mock_wmi}):
                with patch("backend.routers.doc_diagnostics._measure_drive_latency", return_value=None):
                    resp = client.get("/api/doc/vitals")

            assert resp.status_code == 200
            data = resp.json()
            assert data["drive_latency_ms"] is None
            assert any("latency" in e.lower() or "inaccessible" in e.lower() for e in data["errors"])

    def test_no_drive_root_returns_error(self):
        """When drive_root is not set on app.state, errors list is populated."""
        app = FastAPI()
        app.include_router(router, prefix="/api/doc")
        # Don't set app.state.drive_root
        client = TestClient(app)

        import sys
        mock_wmi = MagicMock()
        mock_wmi.WMI.return_value.Win32_PnPEntity.return_value = []
        with patch.dict(sys.modules, {"wmi": mock_wmi}):
            resp = client.get("/api/doc/vitals")

        assert resp.status_code == 200
        data = resp.json()
        assert data["drive_latency_ms"] is None
        assert any("drive_root" in e.lower() for e in data["errors"])

    def test_psutil_unavailable_fallback(self):
        """When psutil is unavailable, cpu/memory are null with error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app = _create_test_app(Path(tmpdir))
            client = TestClient(app)

            import sys
            mock_wmi = MagicMock()
            mock_wmi.WMI.return_value.Win32_PnPEntity.return_value = []

            with patch.dict(sys.modules, {"wmi": mock_wmi, "psutil": None}):
                # Need to reload the module to pick up the mocked psutil
                import importlib
                import backend.routers.doc_diagnostics as mod
                importlib.reload(mod)

                # Re-create app with reloaded router
                app2 = FastAPI()
                app2.include_router(mod.router, prefix="/api/doc")
                app2.state.drive_root = Path(tmpdir)
                client2 = TestClient(app2)
                resp = client2.get("/api/doc/vitals")

            assert resp.status_code == 200
            data = resp.json()
            assert data["cpu_percent"] is None
            assert data["memory_percent"] is None
            assert any("psutil" in e.lower() for e in data["errors"])
