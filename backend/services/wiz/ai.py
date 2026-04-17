"""
Wiz AI Service — Console Wizard chat backend.

Mirrors services/chuck/ai.py pattern with hot-swap prompt on isDiagnosisMode.
Reads controller_wizard.prompt, splits on ---DIAGNOSIS--- delimiter, caches
both variants so neither re-loads from disk after the first call.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import anthropic
from backend.constants.drive_root import get_drive_root

logger = logging.getLogger(__name__)

# ── Prompt paths ──────────────────────────────────────────────────────────────
_PROMPT_FILE = Path("prompts/controller_wizard.prompt")
_DIAGNOSIS_DELIMITER = "---DIAGNOSIS---"

# ── Module-level cache ────────────────────────────────────────────────────────
_prompt_cache: Dict[str, str] = {}   # keys: "chat", "diagnosis"


def _load_prompts() -> None:
    """Load and split the prompt file once; populate _prompt_cache."""
    if "chat" in _prompt_cache:
        return  # already loaded

    root = get_drive_root(context="wiz_ai")
    prompt_path = root / _PROMPT_FILE

    if not prompt_path.exists():
        logger.warning("controller_wizard.prompt not found at %s — using fallback", prompt_path)
        _prompt_cache["chat"] = "You are Wiz, the Console Wizard. Help with console controllers and emulator configs."
        _prompt_cache["diagnosis"] = _prompt_cache["chat"]
        return

    raw = prompt_path.read_text(encoding="utf-8")

    if _DIAGNOSIS_DELIMITER in raw:
        parts = raw.split(_DIAGNOSIS_DELIMITER, maxsplit=1)
        _prompt_cache["chat"] = parts[0].strip()
        _prompt_cache["diagnosis"] = parts[1].strip()
    else:
        _prompt_cache["chat"] = raw.strip()
        _prompt_cache["diagnosis"] = raw.strip()
        logger.warning("controller_wizard.prompt has no %s delimiter — same prompt for both modes", _DIAGNOSIS_DELIMITER)


def _resolve_prompt(is_diagnosis_mode: bool) -> str:
    _load_prompts()
    return _prompt_cache["diagnosis"] if is_diagnosis_mode else _prompt_cache["chat"]


def _build_system(is_diagnosis_mode: bool, extra_context: Optional[Dict[str, Any]]) -> str:
    """Combine base prompt with runtime context block."""
    base = _resolve_prompt(is_diagnosis_mode)

    if not extra_context:
        return base

    ctx_lines = ["\n\n--- CURRENT CABINET CONTEXT ---"]

    # Emulator health summary
    emulator_health = extra_context.get("emulatorHealth", [])
    if emulator_health:
        ctx_lines.append("\nEmulator Health:")
        for entry in emulator_health[:8]:  # cap to avoid token blowup
            status = entry.get("status", "unknown")
            emu_id = entry.get("id") or entry.get("emulator", "?")
            ctx_lines.append(f"  • {emu_id}: {status}")

    # Detected controllers
    controllers = extra_context.get("detectedControllers", [])
    if controllers:
        ctx_lines.append("\nDetected Controllers:")
        for ctrl in controllers[:4]:
            name = ctrl.get("name") or ctrl.get("id", "Unknown")
            player = ctrl.get("player", "?")
            ctx_lines.append(f"  • P{player}: {name}")
    else:
        ctx_lines.append("\nDetected Controllers: None")

    # Active emulators
    emulators = extra_context.get("emulators", [])
    if emulators:
        names = [e.get("displayName", e.get("id", "?")) for e in emulators[:6]]
        ctx_lines.append(f"\nKnown Emulators: {', '.join(names)}")

    # Session timestamp
    ts = extra_context.get("timestamp")
    if ts:
        ctx_lines.append(f"\nSession timestamp: {ts}")

    return base + "\n".join(ctx_lines)


async def wizard_ai_chat(
    message: str,
    history: List[Dict[str, str]],
    *,
    is_diagnosis_mode: bool = False,
    extra_context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Send a chat message to the Wiz AI and return the text reply.

    Args:
        message: The user's latest message.
        history: Prior turns as [{"role": "user"|"assistant", "content": "..."}]
        is_diagnosis_mode: When True, uses the Diagnosis prompt variant.
        extra_context: Optional dict of runtime state (emulator health, controllers, etc.)

    Returns:
        The assistant's reply as a plain string.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set — Wiz cannot chat.")

    client = anthropic.AsyncAnthropic(api_key=api_key)
    system_prompt = _build_system(is_diagnosis_mode, extra_context)

    # Build messages list — history + current message
    messages: List[Dict[str, str]] = []
    for turn in history or []:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": message})

    try:
        response = await client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )
        return response.content[0].text

    except anthropic.APIError as exc:
        logger.error("Wiz AI API error: %s", exc)
        raise
