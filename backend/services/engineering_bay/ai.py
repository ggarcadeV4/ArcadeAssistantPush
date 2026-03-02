"""
Engineering Bay AI Service — unified chat backend for Vicky, Blinky, Gunner, Doc.

Mirrors services/wiz/ai.py pattern.
Each persona loads its own prompt file, splits on ---DIAGNOSIS---,
caches both variants independently.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import anthropic

logger = logging.getLogger(__name__)

_DIAGNOSIS_DELIMITER = "---DIAGNOSIS---"
_prompt_cache: Dict[str, Dict[str, str]] = {}  # {persona: {"chat": ..., "diagnosis": ...}}

_VALID_PERSONAS = {"vicky", "blinky", "gunner", "doc"}

# Doc is always in diagnosis mode — no chat variant needed
_ALWAYS_DIAGNOSIS = {"doc"}


def _load_prompt(persona: str) -> None:
    if persona in _prompt_cache:
        return

    root = Path(os.getenv("AA_DRIVE_ROOT", r"A:\Arcade Assistant Local"))
    prompt_file = root / "prompts" / f"{persona}.prompt"

    if not prompt_file.exists():
        fallback = f"You are {persona.capitalize()}, an Arcade Assistant specialist. Help the user."
        _prompt_cache[persona] = {"chat": fallback, "diagnosis": fallback}
        logger.warning("Prompt file not found for persona '%s' at %s", persona, prompt_file)
        return

    raw = prompt_file.read_text(encoding="utf-8")

    if _DIAGNOSIS_DELIMITER in raw:
        parts = raw.split(_DIAGNOSIS_DELIMITER, maxsplit=1)
        _prompt_cache[persona] = {
            "chat": parts[0].strip(),
            "diagnosis": parts[1].strip(),
        }
    else:
        _prompt_cache[persona] = {
            "chat": raw.strip(),
            "diagnosis": raw.strip(),
        }


def _resolve_prompt(persona: str, is_diagnosis_mode: bool) -> str:
    _load_prompt(persona)
    if persona in _ALWAYS_DIAGNOSIS or is_diagnosis_mode:
        return _prompt_cache[persona]["diagnosis"]
    return _prompt_cache[persona]["chat"]


def _build_system(persona: str, is_diagnosis_mode: bool, extra_context: Optional[Dict[str, Any]]) -> str:
    base = _resolve_prompt(persona, is_diagnosis_mode)
    if not extra_context:
        return base

    ctx_lines = ["\n\n--- CURRENT CABINET CONTEXT ---"]
    for key, val in extra_context.items():
        if isinstance(val, list):
            ctx_lines.append(f"\n{key}:")
            for item in val[:6]:
                ctx_lines.append(f"  • {item}")
        elif val is not None:
            ctx_lines.append(f"\n{key}: {val}")

    return base + "\n".join(ctx_lines)


async def engineering_bay_chat(
    persona: str,
    message: str,
    history: List[Dict[str, str]],
    *,
    is_diagnosis_mode: bool = False,
    extra_context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Route a chat message to the correct Engineering Bay persona AI.

    Args:
        persona: One of 'vicky', 'blinky', 'gunner', 'doc'
        message: The user's latest message.
        history: Prior turns as [{"role": "user"|"assistant", "content": "..."}]
        is_diagnosis_mode: When True, uses the Diagnosis prompt variant.
        extra_context: Optional dict of runtime state.

    Returns:
        The assistant reply as a plain string.
    """
    if persona not in _VALID_PERSONAS:
        raise ValueError(f"Unknown Engineering Bay persona: '{persona}'. Valid: {_VALID_PERSONAS}")

    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set — Engineering Bay cannot chat.")

    client = anthropic.AsyncAnthropic(api_key=api_key)
    system_prompt = _build_system(persona, is_diagnosis_mode, extra_context)

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
        logger.error("Engineering Bay AI error (persona=%s): %s", persona, exc)
        raise
