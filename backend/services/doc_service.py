"""
Doc chat service.

Routes Doc AI calls through SecureAIClient using panel=doc.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.constants.drive_root import get_drive_root
from backend.services.drive_a_ai_client import SecureAIClient

logger = logging.getLogger(__name__)

_CANONICAL_DRIVE_ROOT = get_drive_root(context="doc_service")
_PROMPT_CACHE: Optional[str] = None


def _prompt_candidates() -> List[Path]:
    project_root = Path(__file__).resolve().parents[2]
    return [
        project_root / "prompts" / "doc.prompt",
        _CANONICAL_DRIVE_ROOT / "prompts" / "doc.prompt",
    ]


def _load_prompt() -> str:
    global _PROMPT_CACHE
    if _PROMPT_CACHE is not None:
        return _PROMPT_CACHE

    for candidate in _prompt_candidates():
        if candidate.exists():
            _PROMPT_CACHE = candidate.read_text(encoding="utf-8").strip()
            return _PROMPT_CACHE

    raise FileNotFoundError(f"panel=doc prompt file not found; tried: {_prompt_candidates()}")


def _build_system_prompt(extra_context: Optional[Dict[str, Any]]) -> str:
    prompt = _load_prompt()
    if not extra_context:
        return prompt

    context_text = json.dumps(extra_context, indent=2, default=str)
    return f"{prompt}\n\n--- CURRENT CABINET CONTEXT ---\n{context_text}"


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


def chat_with_doc(
    *,
    message: str,
    history: List[Dict[str, str]],
    cabinet_id: Optional[str],
    extra_context: Optional[Dict[str, Any]] = None,
    is_diagnosis_mode: bool = False,
) -> Dict[str, Any]:
    client = SecureAIClient()
    resolved_cabinet_id = cabinet_id or client.cabinet_id or "unknown-cabinet"
    effective_diagnosis_mode = True

    logger.info(
        "panel=doc service_start cabinet_id=%s requested_diagnosis_mode=%s effective_diagnosis_mode=%s history_turns=%s",
        resolved_cabinet_id,
        is_diagnosis_mode,
        effective_diagnosis_mode,
        len(history or []),
    )

    messages: List[Dict[str, str]] = []
    for turn in history or []:
        role = turn.get("role")
        content = turn.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content.strip()})
    messages.append({"role": "user", "content": message.strip()})

    result = client.call_ai(
        panel="doc",
        messages=messages,
        cabinet_id=resolved_cabinet_id,
        system=_build_system_prompt(extra_context),
        max_tokens=220,
        temperature=0.4,
    )

    reply = _extract_reply(result)
    if not reply:
        raise ValueError("panel=doc SecureAIClient returned an empty response")

    provider = result.get("provider", "unknown")
    model = result.get("model", "unknown")
    logger.info(
        "panel=doc service_complete cabinet_id=%s provider=%s model=%s",
        resolved_cabinet_id,
        provider,
        model,
    )

    return {
        "reply": reply,
        "provider": provider,
        "model": model,
        "cabinet_id": resolved_cabinet_id,
        "isDiagnosisMode": effective_diagnosis_mode,
    }
