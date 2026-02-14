import json
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app import app  # type: ignore  # noqa: E402
import backend.routers.controller as controller_module  # type: ignore  # noqa: E402
from backend.services.board_sanity import (  # type: ignore  # noqa: E402
    Issue,
    ModeFlags,
    PinStability,
    SanityReport,
)
from backend.services.chuck.detection import BoardInfo  # type: ignore  # noqa: E402


def _build_board_info() -> BoardInfo:
    return BoardInfo(
        vid="0x1209",
        pid="0x2000",
        vid_pid="1209:2000",
        name="PactoTech 2000T",
        manufacturer="PactoTech",
        product_string="PactoTech 2000T",
        manufacturer_string="PactoTech",
    )


def _build_report(with_issue: bool = False) -> SanityReport:
    board = _build_board_info()
    flags = ModeFlags(turbo=False, analog=False, twinstick=False, xinput=False, player_count=2, source="test")
    pin = PinStability(status="stable", sample_window_ms=10, transitions=2, ghost_pulses=0)
    issues = []
    if with_issue:
        issues.append(Issue(type="dual_mode_conflict", severity="high", description="Analog and turbo enabled"))
    return SanityReport(
        board_detected=True,
        board_info=board,
        firmware_version="1.2.3",
        mode_flags=flags,
        issues_detected=issues,
        pin_stability=pin,
        ghost_pulses_detected=False,
        recommendations=["Disable conflicting modes"] if with_issue else ["Board looks healthy"],
    )


class FakeScanner:
    def __init__(self, report: SanityReport):
        self.report = report
        self.calls = 0

    def scan(self):
        self.calls += 1
        return self.report


def _headers():
    return {
        "x-device-id": "USB\\VID_1209&PID_2000",
        "x-scope": "state",
        "x-panel": "controller",
    }


def test_board_sanity_route_success(monkeypatch, tmp_path):
    report = _build_report()
    scanner = FakeScanner(report)
    monkeypatch.setattr(controller_module, "BoardSanityScanner", lambda *args, **kwargs: scanner)
    client = TestClient(app)
    app.state.drive_root = tmp_path

    resp = client.get("/api/local/controller/board/sanity", headers=_headers())

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert payload["report"]["board_detected"] is True
    assert "healthy" in payload["summary"].lower()
    assert scanner.calls == 1


def test_board_sanity_missing_headers(tmp_path):
    client = TestClient(app)
    app.state.drive_root = tmp_path

    resp = client.get("/api/local/controller/board/sanity", headers={"x-scope": "state", "x-panel": "controller"})

    assert resp.status_code == 400
    assert "x-device-id" in resp.json()["detail"]


def test_board_diagnostics_stream(monkeypatch, tmp_path):
    report = _build_report(with_issue=True)
    scanners = []

    def factory(*args, **kwargs):
        scanner = FakeScanner(report)
        scanners.append(scanner)
        return scanner

    monkeypatch.setattr(controller_module, "BoardSanityScanner", factory)
    monkeypatch.setattr(controller_module, "BOARD_DIAGNOSTIC_STREAM_INTERVAL", 0.01, raising=False)
    client = TestClient(app)
    app.state.drive_root = tmp_path

    with client.stream("GET", "/api/local/controller/board/diagnostics/live", headers=_headers()) as stream:
        for line in stream.iter_lines():
            if not line:
                continue
            assert line.startswith("data: ")
            payload = json.loads(line.split("data: ", 1)[1])
            assert payload["event"] in {"sanity", "error"}
            if payload["event"] == "sanity":
                assert "mode_flags" in payload["report"]
                assert "turbo" in payload["report"]["mode_flags"]
            break

    assert scanners
    assert scanners[0].calls >= 1
