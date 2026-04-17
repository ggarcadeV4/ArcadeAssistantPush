"""
Launch Remediation Service â€” LoRa's Agentic Repair Loop.

When an emulator crashes (exit within <10s), LoRa:
1. Captures the error context (process info, game metadata)
2. Queries Gemini for a specific CLI fix or ephemeral config tweak
3. Applies the fix (JIT flag injection or temp config)
4. Re-launches the game

@persona: LoRa (The Operator)
@owner: Arcade Assistant / Agentic Repair Ecosystem
@status: active
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from backend.constants.drive_root import get_drive_root
logger = logging.getLogger(__name__)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Configuration
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Route through Supabase Edge Function (gemini-proxy) â€” keeps raw API key
# in Supabase secrets rather than local .env.
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_SERVICE_KEY", "")
)
GEMINI_PROXY_URL = f"{SUPABASE_URL}/functions/v1/gemini-proxy" if SUPABASE_URL else ""

MAX_REMEDIATION_ATTEMPTS = 2
CRASH_THRESHOLD_SECONDS = 10.0  # Exit faster than this = probable crash

REMEDIATION_LOG_PATH = get_drive_root(context="launch_remediation") / ".aa" / "logs" / "remediation.jsonl"


def _log_remediation_result(
    game_title: str,
    platform: str,
    emulator: Optional[str],
    attempt_number: int,
    gemini_suggestion: Optional[Dict[str, Any]],
    fix_applied: bool,
    fix_type: Optional[str],
    fix_detail: Optional[str],
    success: bool,
    error: Optional[str] = None,
) -> None:
    """Append a remediation attempt record to the persistent JSONL log."""
    try:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "game_title": game_title,
            "platform": platform,
            "emulator": emulator,
            "attempt_number": attempt_number,
            "gemini_suggestion": gemini_suggestion,
            "fix_applied": fix_applied,
            "fix_type": fix_type,
            "fix_detail": fix_detail,
            "success": success,
            "error": error,
        }
        REMEDIATION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(REMEDIATION_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        print(f"[GEMINI] Logged to {REMEDIATION_LOG_PATH}", flush=True)
    except Exception as log_exc:
        print(f"[GEMINI] WARNING: Failed to write remediation log: {log_exc}", flush=True)


class RemediationResult:
    """Outcome of a remediation attempt."""

    def __init__(
        self,
        success: bool,
        fix_type: Optional[str] = None,
        fix_detail: Optional[str] = None,
        attempts: int = 0,
        error: Optional[str] = None,
    ):
        self.success = success
        self.fix_type = fix_type        # "cli_flag" | "config_tweak" | "skip"
        self.fix_detail = fix_detail    # The actual fix applied
        self.attempts = attempts
        self.error = error
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "fix_type": self.fix_type,
            "fix_detail": self.fix_detail,
            "attempts": self.attempts,
            "error": self.error,
            "timestamp": self.timestamp,
        }


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Gemini Query â€” Ask the "Gem Brain" for a fix
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def _query_gemini_for_fix(
    game_title: str,
    platform: str,
    emulator: Optional[str],
    error_context: str,
    attempt_number: int,
) -> Optional[Dict[str, Any]]:
    """
    Query Gemini to diagnose an emulator crash and suggest a CLI fix.

    Returns:
        Dict with fix_type and fix_value, or None if no suggestion.
    """
    if not GEMINI_PROXY_URL or not SUPABASE_SERVICE_KEY:
        print("[GEMINI] Proxy NOT CONFIGURED (SUPABASE_URL or SERVICE_KEY missing) -- skipped", flush=True)
        logger.warning(
            "Gemini proxy not configured (SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY missing) "
            "-- remediation query skipped"
        )
        return None

    prompt = (
        f"You are an arcade emulator troubleshooter. An emulator crashed immediately.\n\n"
        f"Game: {game_title}\n"
        f"Platform: {platform}\n"
        f"Emulator: {emulator or 'unknown'}\n"
        f"Error context: {error_context}\n"
        f"Attempt: {attempt_number} of {MAX_REMEDIATION_ATTEMPTS}\n\n"
        f"Respond ONLY with a JSON object containing:\n"
        f'- "fix_type": one of "cli_flag", "config_tweak", "skip"\n'
        f'- "fix_value": the exact flag or config change (e.g., "-skip_gameinfo", "-nowindow")\n'
        f'- "explanation": brief one-line reason\n'
        f'- "confidence": float 0-1\n\n'
        f"If you cannot determine a fix, use fix_type: \"skip\"."
    )

    # Build payload in the proxy's Claude-compatible format
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 256,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                GEMINI_PROXY_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "apikey": SUPABASE_SERVICE_KEY,
                },
            )
            response.raise_for_status()
            result = response.json()

        # Parse proxy response (Claude-compatible format)
        # The proxy returns: { content: [{ type: "text", text: "..." }], ... }
        text = ""
        for block in result.get("content", []):
            if block.get("type") == "text" and block.get("text"):
                text = block["text"]
                break

        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        fix = json.loads(text)
        logger.info(f"Gemini remediation suggestion: {fix}")
        print(f"[GEMINI] Suggestion: {json.dumps(fix, indent=2)}", flush=True)
        return fix

    except httpx.HTTPStatusError as exc:
        logger.error(f"Gemini API error: {exc.response.status_code}")
        print(f"[GEMINI] HTTP error: {exc.response.status_code}", flush=True)
        return None
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.error(f"Failed to parse Gemini remediation response: {exc}")
        print(f"[GEMINI] Parse error: {exc}", flush=True)
        return None
    except Exception as exc:
        logger.error(f"Gemini query failed: {exc}")
        print(f"[GEMINI] Query failed: {exc}", flush=True)
        return None


# ——————————————————————————————————————————————————————————————————————————
# JIT Fix Application
# ——————————————————————————————————————————————————————————————————————————

def apply_jit_fix(
    fix_spec: Dict[str, Any],
    drive_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Apply a Gemini-suggested fix.

    For CLI flags: Returns the flag to append to the next launch command.
    For config tweaks: Writes an ephemeral config file.

    Returns:
        Dict with applied fix details.
    """
    fix_type = fix_spec.get("fix_type", "skip")
    fix_value = fix_spec.get("fix_value", "")
    explanation = fix_spec.get("explanation", "")

    if fix_type == "cli_flag":
        logger.info(f"JIT CLI flag: {fix_value} — {explanation}")
        return {
            "applied": True,
            "fix_type": "cli_flag",
            "cli_args": fix_value.split() if fix_value else [],
            "explanation": explanation,
        }

    elif fix_type == "config_tweak" and drive_root:
        # Write ephemeral config to temp area
        temp_dir = drive_root / "config" / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        config_file = temp_dir / "lora_remediation.ini"

        try:
            config_file.write_text(fix_value, encoding="utf-8")
            logger.info(f"JIT config written: {config_file} — {explanation}")
            return {
                "applied": True,
                "fix_type": "config_tweak",
                "config_path": str(config_file),
                "explanation": explanation,
            }
        except Exception as exc:
            logger.error(f"Failed to write JIT config: {exc}")
            return {"applied": False, "error": str(exc)}

    else:
        logger.info(f"No actionable fix (type={fix_type})")
        return {"applied": False, "fix_type": "skip", "explanation": explanation}


# ——————————————————————————————————————————————————————————————————————————
# Main Remediation Loop
# ——————————————————————————————————————————————————————————————————————————

async def attempt_remediation(
    game_title: str,
    platform: str,
    emulator: Optional[str] = None,
    error_context: str = "",
    drive_root: Optional[Path] = None,
) -> RemediationResult:
    """
    LoRa's remediation loop: query Gemini, apply fix, return result.

    Called by game_lifecycle when a crash is detected (exit < 10s).
    Max 2 attempts before declaring unrecoverable.

    Returns:
        RemediationResult with fix details or failure reason.
    """
    logger.info(
        f"[FIX] LoRa remediation started: {game_title} ({platform}/{emulator})"
    )
    print(f"[GEMINI] LoRa remediation started: {game_title} ({platform}/{emulator})", flush=True)

    for attempt in range(1, MAX_REMEDIATION_ATTEMPTS + 1):
        logger.info(f"Remediation attempt {attempt}/{MAX_REMEDIATION_ATTEMPTS}")
        print(f"[GEMINI] Attempt {attempt}/{MAX_REMEDIATION_ATTEMPTS}", flush=True)

        # 1. Query Gemini for a fix
        fix = await _query_gemini_for_fix(
            game_title=game_title,
            platform=platform,
            emulator=emulator,
            error_context=error_context,
            attempt_number=attempt,
        )

        if not fix or fix.get("fix_type") == "skip":
            logger.info("Gemini has no actionable fix -- skipping")
            print("[GEMINI] No actionable fix returned", flush=True)
            _log_remediation_result(
                game_title=game_title, platform=platform, emulator=emulator,
                attempt_number=attempt, gemini_suggestion=fix,
                fix_applied=False, fix_type="skip", fix_detail="No actionable fix found",
                success=False,
            )
            return RemediationResult(
                success=False,
                fix_type="skip",
                fix_detail="No actionable fix found",
                attempts=attempt,
            )

        # 2. Check confidence threshold
        confidence = fix.get("confidence", 0.0)
        if confidence < 0.3:
            logger.warning(f"Low confidence fix ({confidence}) -- skipping")
            print(f"[GEMINI] Low confidence ({confidence}) -- skipping fix", flush=True)
            _log_remediation_result(
                game_title=game_title, platform=platform, emulator=emulator,
                attempt_number=attempt, gemini_suggestion=fix,
                fix_applied=False, fix_type=fix.get("fix_type"), fix_detail=fix.get("fix_value"),
                success=False, error=f"Low confidence: {confidence}",
            )
            continue

        # 3. Apply the fix
        result = apply_jit_fix(fix, drive_root)
        print(f"[GEMINI] Fix applied: {json.dumps(result, indent=2, default=str)}", flush=True)

        if result.get("applied"):
            _log_remediation_result(
                game_title=game_title, platform=platform, emulator=emulator,
                attempt_number=attempt, gemini_suggestion=fix,
                fix_applied=True, fix_type=fix.get("fix_type"), fix_detail=fix.get("fix_value"),
                success=True,
            )
            return RemediationResult(
                success=True,
                fix_type=fix.get("fix_type"),
                fix_detail=fix.get("fix_value"),
                attempts=attempt,
            )

        # Fix didn't apply â€” next attempt with updated context
        _log_remediation_result(
            game_title=game_title, platform=platform, emulator=emulator,
            attempt_number=attempt, gemini_suggestion=fix,
            fix_applied=False, fix_type=fix.get("fix_type"), fix_detail=fix.get("fix_value"),
            success=False, error="Fix not applied",
        )
        error_context += f"\nPrevious fix attempt ({fix.get('fix_type')}) failed."

    print("[GEMINI] Max attempts exhausted -- giving up", flush=True)
    _log_remediation_result(
        game_title=game_title, platform=platform, emulator=emulator,
        attempt_number=MAX_REMEDIATION_ATTEMPTS, gemini_suggestion=None,
        fix_applied=False, fix_type=None, fix_detail=None,
        success=False, error="Max remediation attempts exhausted",
    )
    return RemediationResult(
        success=False,
        fix_type=None,
        fix_detail=None,
        attempts=MAX_REMEDIATION_ATTEMPTS,
        error="Max remediation attempts exhausted",
    )


def is_probable_crash(play_duration_seconds: float) -> bool:
    """Check if the game exited too fast to be a normal exit."""
    return play_duration_seconds < CRASH_THRESHOLD_SECONDS
