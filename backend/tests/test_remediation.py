"""Property and unit tests for the Remediation Loop.

Feature: agentic-repair-self-healing
Properties 4–8
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.services.remediation import (
    parse_gemini_flags,
    build_remediation_prompt,
    get_remediation_log_path,
    MAX_RETRIES,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_FLAG_STRINGS = st.from_regex(r"-[a-z][a-z0-9_-]{0,20}", fullmatch=True)

_VALID_FLAGS_RESPONSE = st.lists(_FLAG_STRINGS, min_size=1, max_size=8).map(
    lambda flags: {
        "content": [
            {"type": "text", "text": json.dumps({"flags": flags})}
        ]
    }
)

_RANDOM_TEXT = st.text(min_size=0, max_size=500)


# ---------------------------------------------------------------------------
# Property 4: Gemini response parsing extracts flags correctly
# ---------------------------------------------------------------------------

@given(flags=st.lists(_FLAG_STRINGS, min_size=1, max_size=8))
@settings(max_examples=150, deadline=5000)
def test_valid_flags_extracted_correctly(flags: List[str]):
    """For any valid JSON with a flags array, parse_gemini_flags returns those flags.

    **Validates: Requirements 4.3, 4.8**
    """
    response = {
        "content": [
            {"type": "text", "text": json.dumps({"flags": flags})}
        ]
    }
    result = parse_gemini_flags(response)
    assert result == flags


@given(text=_RANDOM_TEXT)
@settings(max_examples=150, deadline=5000)
def test_malformed_response_returns_none(text: str):
    """For any non-JSON or JSON without valid flags, returns None.

    **Validates: Requirements 4.3, 4.8**
    """
    # Wrap in Claude-compatible format but with arbitrary text
    response = {"content": [{"type": "text", "text": text}]}
    result = parse_gemini_flags(response)
    # If it happens to be valid JSON with a flags list of strings, that's OK
    try:
        parsed = json.loads(text)
        flags = parsed.get("flags")
        if isinstance(flags, list) and all(isinstance(f, str) for f in flags):
            assert result == flags
            return
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    assert result is None


# ---------------------------------------------------------------------------
# Property 5: Remediation retry count never exceeds maximum
# ---------------------------------------------------------------------------

@given(num_failures=st.integers(min_value=1, max_value=10))
@settings(max_examples=100, deadline=10000)
def test_retry_count_never_exceeds_max(num_failures: int):
    """For any sequence of consecutive failures, retries ≤ max_retries.

    **Validates: Requirements 4.4**
    """
    import asyncio
    from unittest.mock import AsyncMock, patch

    call_count = 0

    def fake_launch(cmd):
        nonlocal call_count
        call_count += 1
        return {
            "success": False,
            "command": " ".join(cmd),
            "return_code": 1,
            "stderr": f"error {call_count}",
            "timestamp": "2026-01-01T00:00:00Z",
        }

    # Mock Gemini to always return valid flags
    mock_response = {
        "content": [{"type": "text", "text": json.dumps({"flags": ["-fix"]})}]
    }

    async def run():
        from backend.services.remediation import attempt_remediation
        with patch("backend.services.remediation._call_gemini_proxy", new_callable=AsyncMock, return_value=mock_response), \
             patch("backend.services.remediation._broadcast_sys_announce", new_callable=AsyncMock):
            result = await attempt_remediation(
                stderr_trap_result={
                    "success": False, "command": "emu rom", "return_code": 1,
                    "stderr": "crash", "timestamp": "2026-01-01T00:00:00Z",
                },
                hardware_bio={"devices": [], "device_count": 0, "scan_timestamp": "", "error": None},
                original_command=["emu", "rom"],
                max_retries=MAX_RETRIES,
                launch_fn=fake_launch,
            )
        return result

    result = asyncio.get_event_loop().run_until_complete(run())
    assert result["retries"] <= MAX_RETRIES


# ---------------------------------------------------------------------------
# Property 6: Invalid Gemini responses handled gracefully
# ---------------------------------------------------------------------------

@given(text=st.text(min_size=0, max_size=1000))
@settings(max_examples=150, deadline=5000)
def test_invalid_gemini_response_no_exception(text: str):
    """For any random string as response text, parse_gemini_flags never raises.

    **Validates: Requirements 4.6**
    """
    # Various malformed response shapes
    for response in [
        {"content": [{"type": "text", "text": text}]},
        {"content": []},
        {"content": None},
        {},
        {"content": [{"type": "image", "data": text}]},
        text,  # not even a dict
    ]:
        result = parse_gemini_flags(response)
        assert result is None or isinstance(result, list)


# ---------------------------------------------------------------------------
# Property 7: Remediation prompt includes all required context
# ---------------------------------------------------------------------------

_VID_PID = st.from_regex(r"[0-9a-f]{4}:[0-9a-f]{4}", fullmatch=True)

@given(
    stderr=st.text(min_size=1, max_size=200),
    command=st.text(min_size=1, max_size=100),
    vid_pids=st.lists(_VID_PID, min_size=1, max_size=5),
)
@settings(max_examples=150, deadline=5000)
def test_prompt_includes_required_context(stderr: str, command: str, vid_pids: List[str]):
    """Prompt must contain stderr, command, and VID:PIDs.

    **Validates: Requirements 4.2**
    """
    devices = [{"vid_pid": vp, "name": "dev", "device_id": "USB\\..."} for vp in vid_pids]
    bio = {"devices": devices, "device_count": len(devices), "scan_timestamp": "", "error": None}

    prompt = build_remediation_prompt(stderr, command, bio)

    # stderr present (truncated at 2000 chars in prompt)
    assert stderr[:100] in prompt or stderr[:2000] in prompt
    assert command in prompt
    for vp in vid_pids:
        assert vp in prompt


# ---------------------------------------------------------------------------
# Property 8: Remediation log path is always relative to drive root
# ---------------------------------------------------------------------------

@given(
    drive_letter=st.sampled_from(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")),
    subpath=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=20,
    ),
)
@settings(max_examples=150, deadline=5000)
def test_log_path_relative_to_drive_root(drive_letter: str, subpath: str):
    """Log path must be {drive_root}/.aa/logs/remediation.jsonl — no hardcoded drives.

    **Validates: Requirements 6.3**
    """
    drive_root = Path(f"{drive_letter}:/{subpath}")
    log_path = get_remediation_log_path(drive_root)

    expected = drive_root / ".aa" / "logs" / "remediation.jsonl"
    assert log_path == expected

    # Must not contain hardcoded C:\ or A:\ unless that IS the drive root
    log_str = str(log_path)
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if letter == drive_letter:
            continue
        assert f"{letter}:\\" not in log_str and f"{letter}:/" not in log_str
