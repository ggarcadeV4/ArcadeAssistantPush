"""
Engineering Bay AI Service — unified chat backend for all personas.

POST /api/local/engineering-bay/chat
Each persona loads its own prompt file, splits on ---DIAGNOSIS---,
caches both variants independently.

Uses Gemini (Google AI) as the LLM provider.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from backend.constants.drive_root import get_drive_root

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)
_CANONICAL_DRIVE_ROOT = get_drive_root(context="engineering_bay")

_DIAGNOSIS_DELIMITER = "---DIAGNOSIS---"
_prompt_cache: Dict[str, Dict[str, str]] = {}  # {persona: {"chat": ..., "diagnosis": ...}}
_knowledge_cache: Dict[str, str] = {}  # {persona: knowledge_text}

# Uncertainty markers — if response contains these, try Google Search grounding
_UNCERTAINTY_MARKERS = [
    "i'm not sure", "i don't have", "i'm not certain",
    "you might want to check", "i don't know",
    "beyond my current knowledge", "i cannot confirm",
    "you should verify", "not covered in my knowledge",
]

_VALID_PERSONAS = {"vicky", "blinky", "gunner", "doc", "chuck", "wiz"}

# Doc is always in diagnosis mode — no chat variant needed
_ALWAYS_DIAGNOSIS = {"doc"}

# Gemini configuration — 2.5 Flash for better instruction following
_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent"

# Persona ID → prompt filename mapping
# Some personas use different names for their prompt files
_PROMPT_FILENAMES = {
    "chuck": "controller_chuck",
    "wiz":   "controller_wizard",
    # All others use their persona ID directly (e.g., gunner → gunner.prompt)
}

# Knowledge file mapping — override filename per persona
_KNOWLEDGE_FILENAMES = {
    "chuck": "chuck_knowledge",
    # Others can have knowledge files too: "vicky": "vicky_knowledge", etc.
}


def _load_knowledge(persona: str) -> None:
    """Load the knowledge base file for a persona (if it exists)."""
    if persona in _knowledge_cache:
        return

    filename = _KNOWLEDGE_FILENAMES.get(persona, f"{persona}_knowledge")
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    candidates = [
        project_root / "prompts" / f"{filename}.md",
        _CANONICAL_DRIVE_ROOT / "prompts" / f"{filename}.md",
    ]

    for candidate in candidates:
        if candidate.exists():
            try:
                _knowledge_cache[persona] = candidate.read_text(encoding="utf-8")
                logger.info("Loaded knowledge base for '%s' from %s (%d chars)",
                            persona, candidate, len(_knowledge_cache[persona]))
                return
            except Exception as exc:
                logger.warning("Failed to read knowledge file %s: %s", candidate, exc)

    _knowledge_cache[persona] = ""  # No knowledge file found — cache empty string
    logger.debug("No knowledge file found for persona '%s'", persona)


def _load_prompt(persona: str) -> None:
    if persona in _prompt_cache:
        return

    # Resolve prompt filename (some personas have different file names)
    filename = _PROMPT_FILENAMES.get(persona, persona)

    # Try multiple paths to find the prompt file:
    # 1. Project-relative (backend/services/engineering_bay/ai.py → ../../.. → prompts/)
    # 2. AA_DRIVE_ROOT-based
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    candidates = [
        project_root / "prompts" / f"{filename}.prompt",
        _CANONICAL_DRIVE_ROOT / "prompts" / f"{filename}.prompt",
    ]

    prompt_file = None
    for candidate in candidates:
        if candidate.exists():
            prompt_file = candidate
            break

    if prompt_file is None:
        fallback = f"You are {persona.capitalize()}, an Arcade Assistant specialist. Help the user."
        _prompt_cache[persona] = {"chat": fallback, "diagnosis": fallback}
        logger.warning(
            "Prompt file not found for persona '%s'. Tried: %s",
            persona,
            [str(c) for c in candidates],
        )
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

    # Inject knowledge base between prompt and context
    _load_knowledge(persona)
    knowledge = _knowledge_cache.get(persona, "")
    if knowledge:
        base = base + "\n\n--- KNOWLEDGE BASE ---\n" + knowledge

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
    Route a chat message to the correct Engineering Bay persona AI via Gemini.

    Args:
        persona: One of 'vicky', 'blinky', 'gunner', 'doc', 'chuck', 'wiz'
        message: The user's latest message.
        history: Prior turns as [{"role": "user"|"assistant", "content": "..."}]
        is_diagnosis_mode: When True, uses the Diagnosis prompt variant.
        extra_context: Optional dict of runtime state.

    Returns:
        The assistant reply as a plain string.
    """
    if persona not in _VALID_PERSONAS:
        raise ValueError(f"Unknown Engineering Bay persona: '{persona}'. Valid: {_VALID_PERSONAS}")

    if not HTTPX_AVAILABLE:
        raise EnvironmentError("httpx not installed — Engineering Bay cannot chat.")

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not set — Engineering Bay cannot chat.")

    system_prompt = _build_system(persona, is_diagnosis_mode, extra_context)

    # Build Gemini-format conversation
    # Gemini uses a single "contents" array with alternating user/model roles
    contents: List[Dict[str, Any]] = []

    for turn in history or []:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if not content:
            continue
        # Gemini uses "model" instead of "assistant"
        gemini_role = "model" if role == "assistant" else "user"
        contents.append({
            "role": gemini_role,
            "parts": [{"text": content}]
        })

    # Add the current user message
    contents.append({
        "role": "user",
        "parts": [{"text": message}]
    })

    request_body = {
        "system_instruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1024,
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{_GEMINI_ENDPOINT}?key={api_key}",
                json=request_body,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            result = response.json()

        reply = _extract_reply(result)

        # ── Pass 2: Google Search grounding fallback ──────────────────────
        # If the reply shows uncertainty, retry with web search grounding
        reply_lower = reply.lower()
        if any(marker in reply_lower for marker in _UNCERTAINTY_MARKERS):
            logger.info("[%s] Uncertainty detected — retrying with Google Search grounding", persona)
            grounded_body = {
                **request_body,
                "tools": [{
                    "google_search": {}
                }],
            }
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    g_response = await client.post(
                        f"{_GEMINI_ENDPOINT}?key={api_key}",
                        json=grounded_body,
                        headers={"Content-Type": "application/json"}
                    )
                    g_response.raise_for_status()
                    g_result = g_response.json()
                grounded_reply = _extract_reply(g_result)
                if grounded_reply:
                    logger.info("[%s] Web grounded answer available (%d chars)", persona, len(grounded_reply))
                    return grounded_reply
            except Exception as g_exc:
                logger.warning("[%s] Google Search grounding failed, using RAG answer: %s", persona, g_exc)

        return reply

    except httpx.HTTPStatusError as exc:
        logger.error("Gemini API error (persona=%s): %s — %s", persona, exc.response.status_code, exc.response.text)
        raise
    except Exception as exc:
        logger.error("Engineering Bay AI error (persona=%s): %s", persona, exc)
        raise


def _extract_reply(result: Dict[str, Any]) -> str:
    """Extract text from Gemini response JSON."""
    candidates = result.get("candidates", [])
    if not candidates:
        raise ValueError("No response candidates from Gemini")

    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    if not parts:
        raise ValueError("Empty response from Gemini")

    return parts[0].get("text", "").strip()
