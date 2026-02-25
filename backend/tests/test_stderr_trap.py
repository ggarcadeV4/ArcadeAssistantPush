"""Property tests for Stderr Trap — bounded capture and watchdog timing.

Feature: agentic-repair-self-healing
Property 2: Stderr capture is bounded at 4 KB

**Validates: Requirements 3.2**
"""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_proc(exit_code: int, stderr_bytes: bytes, timeout_expired: bool = False):
    """Build a mock Popen that simulates fast crash or healthy launch."""
    proc = MagicMock(spec=subprocess.Popen)
    proc.pid = 99999
    proc.returncode = None if timeout_expired else exit_code

    stderr_stream = MagicMock()
    stderr_stream.read.return_value = stderr_bytes
    proc.stderr = stderr_stream
    proc.stdout = MagicMock()

    def _wait(timeout=None):
        if timeout_expired:
            raise subprocess.TimeoutExpired(cmd="test", timeout=timeout or 1.5)
        proc.returncode = exit_code

    proc.wait = MagicMock(side_effect=_wait)
    return proc


# ---------------------------------------------------------------------------
# Property 2: Stderr capture is bounded at 4 KB
# ---------------------------------------------------------------------------

@given(data=st.binary(min_size=0, max_size=100_000))
@settings(max_examples=150, deadline=5000)
def test_stderr_capture_bounded_at_4kb(data: bytes):
    """For any stderr output of arbitrary length, captured stderr ≤ 4096 bytes.

    **Validates: Requirements 3.2**
    """
    from backend.services.launcher import GameLauncher

    mock_proc = _make_mock_proc(exit_code=1, stderr_bytes=data)

    with patch("backend.services.launcher.subprocess.Popen", return_value=mock_proc):
        result = GameLauncher._launch_with_stderr_trap(["fake_emu.exe", "rom.zip"])

    # The stderr field must be at most 4096 bytes when encoded
    assert len(result["stderr"].encode("utf-8", errors="replace")) <= 4096
    assert result["success"] is False
    assert result["return_code"] == 1


# ---------------------------------------------------------------------------
# Property 3: Crash error payload is structurally complete
# ---------------------------------------------------------------------------

@given(
    exit_code=st.integers(min_value=1, max_value=255),
    stderr_text=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
        min_size=0,
        max_size=500,
    ),
)
@settings(max_examples=150, deadline=5000)
def test_crash_payload_structurally_complete(exit_code: int, stderr_text: str):
    """For any non-zero exit code and stderr string, the payload has all required fields.

    **Validates: Requirements 3.4, 3.5**
    """
    from backend.services.launcher import GameLauncher

    stderr_bytes = stderr_text.encode("utf-8", errors="replace")
    mock_proc = _make_mock_proc(exit_code=exit_code, stderr_bytes=stderr_bytes)

    with patch("backend.services.launcher.subprocess.Popen", return_value=mock_proc):
        result = GameLauncher._launch_with_stderr_trap(["emu.exe", "game.zip"])

    # All required fields must be present and non-null
    assert "return_code" in result and result["return_code"] is not None
    assert "command" in result and isinstance(result["command"], str)
    assert "timestamp" in result and isinstance(result["timestamp"], str)
    assert "stderr" in result and isinstance(result["stderr"], str)
    assert "success" in result and result["success"] is False
    assert result["return_code"] == exit_code


# ---------------------------------------------------------------------------
# Unit test: healthy launch (process still running after watchdog)
# ---------------------------------------------------------------------------

def test_healthy_launch_returns_success():
    """Process still running after 1.5s should be considered successful."""
    from backend.services.launcher import GameLauncher

    mock_proc = _make_mock_proc(exit_code=0, stderr_bytes=b"", timeout_expired=True)

    with patch("backend.services.launcher.subprocess.Popen", return_value=mock_proc):
        result = GameLauncher._launch_with_stderr_trap(["mame.exe", "sf2.zip"])

    assert result["success"] is True
    assert result["return_code"] is None
    assert result["stderr"] == ""
    assert "pid" in result


def test_clean_exit_returns_success():
    """Process exiting with code 0 within watchdog window is still success."""
    from backend.services.launcher import GameLauncher

    mock_proc = _make_mock_proc(exit_code=0, stderr_bytes=b"")

    with patch("backend.services.launcher.subprocess.Popen", return_value=mock_proc):
        result = GameLauncher._launch_with_stderr_trap(["mame.exe", "sf2.zip"])

    assert result["success"] is True
    assert result["return_code"] == 0


def test_empty_stderr_still_triggers_failure():
    """Non-zero exit with empty stderr should still report failure.

    **Validates: Requirements 3.5**
    """
    from backend.services.launcher import GameLauncher

    mock_proc = _make_mock_proc(exit_code=1, stderr_bytes=b"")

    with patch("backend.services.launcher.subprocess.Popen", return_value=mock_proc):
        result = GameLauncher._launch_with_stderr_trap(["mame.exe", "sf2.zip"])

    assert result["success"] is False
    assert result["return_code"] == 1
    assert result["stderr"] == ""
