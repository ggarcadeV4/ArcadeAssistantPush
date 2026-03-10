"""
Launch Remediation Service — LoRa's Agentic Repair Loop.

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

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

MAX_REMEDIATION_ATTEMPTS = 2
CRASH_THRESHOLD_SECONDS = 10.0  # Exit faster than this = probable crash


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


# ─────────────────────────────────────────────────────────
# Gemini Query — Ask the "Gem Brain" for a fix
# ─────────────────────────────────────────────────────────

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
    if not GEMINI_API_KEY:
        logger.warning("No GEMINI_API_KEY set — remediation query skipped")
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

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 256,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{GEMINI_ENDPOINT}?key={GEMINI_API_KEY}",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            result = response.json()

        # Parse Gemini response
        text = (
            result.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )

        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        fix = json.loads(text)
        logger.info(f"Gemini remediation suggestion: {fix}")
        return fix

    except httpx.HTTPStatusError as exc:
        logger.error(f"Gemini API error: {exc.response.status_code}")
        return None
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.error(f"Failed to parse Gemini remediation response: {exc}")
        return None
    except Exception as exc:
        logger.error(f"Gemini query failed: {exc}")
        return None


# ─────────────────────────────────────────────────────────
# JIT Fix Application
# ─────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────
# Main Remediation Loop
# ─────────────────────────────────────────────────────────

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
        f"🔧 LoRa remediation started: {game_title} ({platform}/{emulator})"
    )

    for attempt in range(1, MAX_REMEDIATION_ATTEMPTS + 1):
        logger.info(f"Remediation attempt {attempt}/{MAX_REMEDIATION_ATTEMPTS}")

        # 1. Query Gemini for a fix
        fix = await _query_gemini_for_fix(
            game_title=game_title,
            platform=platform,
            emulator=emulator,
            error_context=error_context,
            attempt_number=attempt,
        )

        if not fix or fix.get("fix_type") == "skip":
            logger.info("Gemini has no actionable fix — skipping")
            return RemediationResult(
                success=False,
                fix_type="skip",
                fix_detail="No actionable fix found",
                attempts=attempt,
            )

        # 2. Check confidence threshold
        confidence = fix.get("confidence", 0.0)
        if confidence < 0.3:
            logger.warning(f"Low confidence fix ({confidence}) — skipping")
            continue

        # 3. Apply the fix
        result = apply_jit_fix(fix, drive_root)

        if result.get("applied"):
            return RemediationResult(
                success=True,
                fix_type=fix.get("fix_type"),
                fix_detail=fix.get("fix_value"),
                attempts=attempt,
            )

        # Fix didn't apply — next attempt with updated context
        error_context += f"\nPrevious fix attempt ({fix.get('fix_type')}) failed."

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
