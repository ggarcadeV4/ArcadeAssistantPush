"""Unit tests for backend.services.board_sanity."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.board_sanity import BoardSanityScanner, ModeFlags  # noqa: E402
from services.chuck.detection import BoardInfo, BoardNotFoundError  # noqa: E402


class MockDetectionService:
    """Injection helper that mimics the detection service interface."""

    def __init__(self, board: BoardInfo | None):
        self.board = board
        self.calls: list[tuple[str, str]] = []

    def detect_board(self, vid: str, pid: str, use_cache: bool = False) -> BoardInfo:
        self.calls.append((vid, pid))
        if not self.board:
            raise BoardNotFoundError("board not connected")
        return self.board


def make_board() -> BoardInfo:
    return BoardInfo(
        vid="0x1209",
        pid="0x2000",
        vid_pid="1209:2000",
        name="PactoTech 2000T Encoder",
        manufacturer="PactoTech",
        product_string="PactoTech 2000T",
        manufacturer_string="PactoTech",
    )


def test_scan_detects_dual_mode_conflict() -> None:
    board = make_board()
    service = MockDetectionService(board)

    def mode_reader(_: BoardInfo | None) -> ModeFlags:
        return ModeFlags(turbo=True, analog=True, source="test")

    scanner = BoardSanityScanner(
        device_id="USB\\VID_1209&PID_2000",
        detection_service=service,
        mode_reader=mode_reader,
        pin_sampler=lambda: [],
    )

    report = scanner.scan()

    assert report.board_detected is True
    assert report.mode_flags.turbo is True
    issue_types = {issue.type for issue in report.issues_detected}
    assert "dual_mode_conflict" in issue_types


def test_scan_handles_pin_instability() -> None:
    board = make_board()
    service = MockDetectionService(board)

    samples = [
        {"timestamp_ms": 0, "control": "p1.button1"},
        {"timestamp_ms": 4, "control": "p1.button1", "ghost": True},
        {"timestamp_ms": 8, "control": "p1.button1"},
        {"timestamp_ms": 12, "control": "p1.button1", "ghost": True},
    ]

    scanner = BoardSanityScanner(
        device_id="USB\\VID_1209&PID_2000",
        detection_service=service,
        mode_reader=lambda _: ModeFlags(source="test"),
        pin_sampler=lambda: samples,
    )

    report = scanner.scan()

    assert report.pin_stability.status in {"unstable", "critical"}
    assert report.pin_stability.ghost_pulses == 2
    assert report.ghost_pulses_detected is True
    issue_types = {issue.type for issue in report.issues_detected}
    assert "pin_instability" in issue_types


def test_scan_reports_missing_board() -> None:
    service = MockDetectionService(None)

    scanner = BoardSanityScanner(
        device_id=None,
        detection_service=service,
        mode_reader=lambda _: ModeFlags(source="test"),
        pin_sampler=lambda: [],
    )

    report = scanner.scan()

    assert report.board_detected is False
    issue_types = {issue.type for issue in report.issues_detected}
    assert "board_not_detected" in issue_types


def test_scan_reports_healthy_board() -> None:
    board = make_board()
    service = MockDetectionService(board)

    scanner = BoardSanityScanner(
        device_id="USB\\VID_1209&PID_2000",
        detection_service=service,
        mode_reader=lambda _: ModeFlags(turbo=False, analog=False, source="test"),
        pin_sampler=lambda: [],
    )

    report = scanner.scan()

    assert report.board_detected is True
    assert not report.issues_detected
    assert report.recommendations
    assert any("healthy" in rec.lower() or "ready" in rec.lower() for rec in report.recommendations)
