"""Remediation Loop — AI-powered self-healing for failed launches.

Queries the Gemini API via the Supabase Edge Function proxy to analyse
stderr output and suggest CLI flag corrections.  The Gemini API key
(``GOOGLE_API_KEY``) lives in Supabase secrets; the backend only needs
``SUPABASE_URL`` and ``SUPABASE_SERVICE_ROLE_KEY``.

Part of Phase 4: Agentic Repair & Self-Healing Launch.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8787")

MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# sys_announce broadcast
# ---------------------------------------------------------------------------


async def _broadcast_sys_announce(
    announce_type: str,
    game_title: str,
    message: str,
    retry_number: Optional[int] = None,
    applied_flags: Optional[List[str]] = None,
) -> None:
    """Publish a sys_announce event to the event bus AND POST to the gateway.

    Non-blocking — failures are logged but never block the launch flow.
    """
    # 1. Publish to the internal event bus
    try:
        from backend.services.bus_events import publish_sys_announce
        await publish_sys_announce(
            announce_type=announce_type,
            game_title=game_title,
            message=message,
            retry_number=retry_number,
            applied_flags=applied_flags,
        )
    except Exception as exc:
        logger.debug("Event bus publish failed (non-critical): %s", exc)

    # 2. POST to the gateway broadcast endpoint
    try:
        import httpx
    except ImportError:
        return

    payload = {
        "type": "sys_announce",
        "announce_type": announce_type,
        "game_title": game_title,
        "message": message,
    }
    if retry_number is not None:
        payload["retry_number"] = retry_number
    if applied_flags is not None:
        payload["applied_flags"] = applied_flags

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(
                f"{GATEWAY_URL}/api/scorekeeper/broadcast",
                json=payload,
            )
    except Exception as exc:
        logger.debug("Gateway broadcast failed (non-critical): %s", exc)

# ---------------------------------------------------------------------------
# Gemini response parsing
# ---------------------------------------------------------------------------


def parse_gemini_flags(response_body: Dict[str, Any]) -> Optional[List[str]]:
    """Extract ``flags`` list from a Claude-compatible Gemini proxy response.

    The Supabase ``gemini-proxy`` Edge Function returns a Claude-compatible
    response with ``content`` as a list of blocks.  We look for the first
    ``text`` block, parse it as JSON, and extract the ``flags`` array.

    Returns:
        A list of flag strings, or ``None`` if parsing fails.
    """
    try:
        content = response_body.get("content")
        if not isinstance(content, list) or not content:
            return None

        # Find the first text block
        text = None
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                break

        if not text:
            return None

        # Parse JSON from the text
        payload = json.loads(text)
        flags = payload.get("flags")
        if isinstance(flags, list) and all(isinstance(f, str) for f in flags):
            return flags
        return None
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Gemini proxy call
# ---------------------------------------------------------------------------


async def _call_gemini_proxy(prompt: str) -> Optional[Dict[str, Any]]:
    """Call Gemini via the Supabase Edge Function proxy.

    Mirrors the ``callGeminiAPI`` pattern in ``gateway/routes/launchboxAI.js``.

    Returns the parsed JSON response body, or ``None`` on failure.
    """
    try:
        import httpx
    except ImportError:
        logger.warning("httpx not available — cannot call Gemini proxy")
        return None

    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")

    if not supabase_url or not service_key:
        logger.warning("Supabase not configured — skipping Gemini remediation")
        return None

    proxy_url = f"{supabase_url}/functions/v1/gemini-proxy"

    request_body = {
        "model": "gemini-2.0-flash",
        "max_tokens": 256,
        "temperature": 0.2,
        "messages": [
            {"role": "user", "content": prompt},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                proxy_url,
                json=request_body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {service_key}",
                },
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("Gemini proxy HTTP error %s: %s", exc.response.status_code, exc.response.text[:200])
    except Exception as exc:
        logger.error("Gemini proxy call failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def build_remediation_prompt(
    stderr: str,
    original_command: str,
    hardware_bio: Dict[str, Any],
) -> str:
    """Build the Gemini prompt for remediation.

    Includes stderr trace, original command flags, and hardware VID:PIDs.
    """
    devices = hardware_bio.get("devices", [])
    vid_pids = ", ".join(d.get("vid_pid", "?") for d in devices) if devices else "none detected"

    return (
        "You are an arcade emulator diagnostics AI. A launch just failed.\n\n"
        f"Error output:\n```\n{stderr[:2000]}\n```\n\n"
        f"Original command:\n```\n{original_command}\n```\n\n"
        f"Connected hardware (VID:PID): {vid_pids}\n\n"
        "Analyze the error and suggest corrected command-line flags.\n"
        'Return ONLY a JSON object: {"flags": ["-flag1", "value1", "-flag2", "value2"]}\n'
        "Do not include the executable path or ROM path in the flags.\n"
    )


# ---------------------------------------------------------------------------
# Remediation log
# ---------------------------------------------------------------------------


def _log_remediation_attempt(
    drive_root: Optional[Path],
    attempt: Dict[str, Any],
) -> None:
    """Append a remediation attempt to the JSONL log."""
    if not drive_root:
        return
    log_path = Path(drive_root) / ".aa" / "logs" / "remediation.jsonl"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(attempt, default=str) + "\n")
    except Exception as exc:
        logger.warning("Failed to write remediation log: %s", exc)


def get_remediation_log_path(drive_root: Path) -> Path:
    """Return the remediation log path for a given drive root.

    Always relative to drive_root — never hardcoded drive letters.
    """
    return Path(drive_root) / ".aa" / "logs" / "remediation.jsonl"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def attempt_remediation(
    stderr_trap_result: Dict[str, Any],
    hardware_bio: Dict[str, Any],
    original_command: List[str],
    game_title: str = "",
    drive_root: Optional[Path] = None,
    max_retries: int = MAX_RETRIES,
    launch_fn=None,
) -> Dict[str, Any]:
    """Attempt AI-driven remediation for a failed launch.

    Queries Gemini via the Supabase proxy for CLI flag corrections and
    retries the launch up to ``max_retries`` times.

    Args:
        stderr_trap_result: The initial StderrTrapResult from the failed launch.
        hardware_bio: HardwareBio dict from identity_service.
        original_command: The original command list that failed.
        game_title: Game title for logging/events.
        drive_root: Drive root for log file path.
        max_retries: Maximum retry attempts (default 2).
        launch_fn: Callable that accepts a command list and returns a
                   StderrTrapResult dict.  Defaults to
                   ``GameLauncher._launch_with_stderr_trap``.

    Returns:
        Dict with ``success``, ``method``, ``retries``, ``applied_flags``.
    """
    if launch_fn is None:
        from backend.services.launcher import GameLauncher
        launch_fn = GameLauncher._launch_with_stderr_trap

    current_result = stderr_trap_result
    retries = 0

    # Broadcast crash_detected
    try:
        await _broadcast_sys_announce(
            announce_type="crash_detected",
            game_title=game_title,
            message=f"Emulator crash detected. Doc is analyzing the trace...",
        )
    except Exception as exc:
        logger.debug("crash_detected broadcast failed (non-critical): %s", exc)

    while retries < max_retries:
        stderr_text = current_result.get("stderr", "")
        cmd_str = current_result.get("command", " ".join(original_command))

        prompt = build_remediation_prompt(stderr_text, cmd_str, hardware_bio)
        response = await _call_gemini_proxy(prompt)

        if response is None:
            logger.info("[Remediation] No response from Gemini — stopping retries")
            break

        flags = parse_gemini_flags(response)
        if not flags:
            logger.info("[Remediation] No valid flags in Gemini response — stopping")
            # Log the raw response for debugging
            _log_remediation_attempt(drive_root, {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "game_title": game_title,
                "retry_number": retries + 1,
                "gemini_response_raw": json.dumps(response, default=str)[:2000],
                "suggested_flags": None,
                "retry_success": False,
                "error": "no_valid_flags",
            })
            break

        retries += 1
        logger.info("[Remediation] Retry %d/%d with flags: %s", retries, max_retries, flags)

        # Broadcast remediation_attempt
        try:
            await _broadcast_sys_announce(
                announce_type="remediation_attempt",
                game_title=game_title,
                message=f"LoRa is applying an AI-recommended fix and relaunching.",
                retry_number=retries,
                applied_flags=flags,
            )
        except Exception as exc:
            logger.debug("remediation_attempt broadcast failed (non-critical): %s", exc)

        # Build new command: original exe + new flags + original ROM args
        new_command = [original_command[0]] + flags
        if len(original_command) > 1:
            new_command.append(original_command[-1])  # ROM path is typically last

        current_result = launch_fn(new_command)

        # Log attempt
        _log_remediation_attempt(drive_root, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "game_title": game_title,
            "original_command": cmd_str,
            "retry_number": retries,
            "suggested_flags": flags,
            "retry_command": " ".join(new_command),
            "retry_success": current_result.get("success", False),
            "retry_stderr": current_result.get("stderr", "")[:500],
        })

        if current_result.get("success"):
            logger.info("[Remediation] Retry %d succeeded with flags: %s", retries, flags)
            try:
                await _broadcast_sys_announce(
                    announce_type="remediation_success",
                    game_title=game_title,
                    message=f"Fix applied successfully. {game_title} is back in action.",
                    retry_number=retries,
                    applied_flags=flags,
                )
            except Exception as exc:
                logger.debug("remediation_success broadcast failed (non-critical): %s", exc)
            return {
                "success": True,
                "method": "remediation",
                "retries": retries,
                "applied_flags": flags,
            }

    # All retries exhausted
    try:
        await _broadcast_sys_announce(
            announce_type="remediation_failed",
            game_title=game_title,
            message=f"Unable to fix {game_title} after {retries} attempts. Manual intervention needed.",
        )
    except Exception as exc:
        logger.debug("remediation_failed broadcast failed (non-critical): %s", exc)

    return {
        "success": False,
        "method": "remediation",
        "retries": retries,
        "applied_flags": None,
    }
