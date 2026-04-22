"""
Gunner chat service.

Routes Gunner AI calls through SecureAIClient using panel=gunner.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.constants.drive_root import get_drive_root
from backend.services.drive_a_ai_client import SecureAIClient

logger = logging.getLogger(__name__)

_CANONICAL_DRIVE_ROOT = get_drive_root(context="gunner_chat_service")
_PROMPT_CACHE: Dict[str, str] = {}
_KNOWLEDGE_CACHE: Optional[str] = None


def _prompt_candidates() -> List[Path]:
    project_root = Path(__file__).resolve().parents[2]
    return [
        project_root / "prompts" / "gunner.prompt",
        _CANONICAL_DRIVE_ROOT / "prompts" / "gunner.prompt",
    ]


def _knowledge_candidates() -> List[Path]:
    project_root = Path(__file__).resolve().parents[2]
    return [
        project_root / "prompts" / "gunner_knowledge.md",
        _CANONICAL_DRIVE_ROOT / "prompts" / "gunner_knowledge.md",
    ]


def _load_prompt_variants() -> Dict[str, str]:
    if _PROMPT_CACHE:
        return _PROMPT_CACHE

    prompt_text: Optional[str] = None
    for candidate in _prompt_candidates():
        if candidate.exists():
            prompt_text = candidate.read_text(encoding="utf-8").strip()
            break

    if prompt_text is None:
        raise FileNotFoundError(
            f"panel=gunner prompt file not found; tried: {_prompt_candidates()}"
        )

    if "---DIAGNOSIS---" in prompt_text:
        chat_prompt, diagnosis_prompt = prompt_text.split("---DIAGNOSIS---", 1)
        _PROMPT_CACHE["chat"] = chat_prompt.strip()
        _PROMPT_CACHE["diagnosis"] = diagnosis_prompt.strip()
    else:
        cleaned = prompt_text.strip()
        _PROMPT_CACHE["chat"] = cleaned
        _PROMPT_CACHE["diagnosis"] = cleaned

    return _PROMPT_CACHE


def _load_knowledge() -> str:
    global _KNOWLEDGE_CACHE

    if _KNOWLEDGE_CACHE is not None:
        return _KNOWLEDGE_CACHE

    for candidate in _knowledge_candidates():
        if candidate.exists():
            _KNOWLEDGE_CACHE = candidate.read_text(encoding="utf-8").strip()
            return _KNOWLEDGE_CACHE

    raise FileNotFoundError(
        f"panel=gunner knowledge file not found; tried: {_knowledge_candidates()}"
    )


def _build_system_prompt(
    *,
    extra_context: Optional[Dict[str, Any]],
    is_diagnosis_mode: bool,
) -> str:
    variants = _load_prompt_variants()
    prompt = variants["diagnosis"] if is_diagnosis_mode else variants["chat"]
    sections = [prompt, f"--- KNOWLEDGE BASE ---\n{_load_knowledge()}"]

    if extra_context:
        context_text = json.dumps(extra_context, indent=2, default=str)
        sections.append(f"--- CURRENT CABINET CONTEXT ---\n{context_text}")

    return "\n\n".join(section.strip() for section in sections if section.strip())


def _extract_reply(result: Dict[str, Any]) -> str:
    candidates = result.get("candidates")
    if isinstance(candidates, list) and candidates:
        parts = (candidates[0].get("content") or {}).get("parts", [])
        if isinstance(parts, list) and parts:
            text = parts[0].get("text", "")
            if text:
                return str(text).strip()

    text = result.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    content = result.get("content")
    if isinstance(content, list):
        text_parts = [
            str(block.get("text", "")).strip()
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        merged = "\n".join(part for part in text_parts if part).strip()
        if merged:
            return merged
    elif isinstance(content, str) and content.strip():
        return content.strip()

    response_text = result.get("response")
    if isinstance(response_text, str) and response_text.strip():
        return response_text.strip()

    return ""


def chat_with_gunner(
    *,
    messages: List[Dict[str, str]],
    cabinet_id: Optional[str],
    extra_context: Optional[Dict[str, Any]] = None,
    is_diagnosis_mode: bool = False,
) -> Dict[str, Any]:
    client = SecureAIClient()
    resolved_cabinet_id = cabinet_id or client.cabinet_id or "unknown-cabinet"

    logger.info(
        "panel=gunner service_start cabinet_id=%s requested_diagnosis_mode=%s message_turns=%s",
        resolved_cabinet_id,
        is_diagnosis_mode,
        len(messages or []),
    )

    normalized_messages: List[Dict[str, str]] = []
    for turn in messages or []:
        role = turn.get("role")
        content = turn.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            normalized_messages.append({"role": role, "content": content.strip()})

    if not normalized_messages:
        raise ValueError("panel=gunner requires at least one non-empty message")

    result = client.call_ai(
        panel="gunner",
        messages=normalized_messages,
        cabinet_id=resolved_cabinet_id,
        system=_build_system_prompt(
            extra_context=extra_context,
            is_diagnosis_mode=is_diagnosis_mode,
        ),
        max_tokens=1024,
        temperature=0.7,
    )

    reply = _extract_reply(result)
    if not reply:
        raise ValueError("panel=gunner SecureAIClient returned an empty response")

    provider = result.get("provider", "unknown")
    model = result.get("model", "unknown")
    logger.info(
        "panel=gunner service_complete cabinet_id=%s provider=%s model=%s",
        resolved_cabinet_id,
        provider,
        model,
    )

    return {
        "reply": reply,
        "provider": provider,
        "model": model,
        "cabinet_id": resolved_cabinet_id,
        "isDiagnosisMode": bool(is_diagnosis_mode),
    }
