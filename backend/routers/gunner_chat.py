"""
Gunner chat router.

POST /api/local/gunner/chat
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.services.drive_a_ai_client import PanelConfigNotFound, PanelDisabled
from backend.services.gunner_chat_service import chat_with_gunner
from backend.services.policies import require_scope

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gunner"])


class ChatTurn(BaseModel):
    role: str
    content: str


class GunnerChatRequest(BaseModel):
    messages: List[ChatTurn] = Field(default_factory=list)
    message: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    history: List[ChatTurn] = Field(default_factory=list)
    cabinet_id: Optional[str] = None
    isDiagnosisMode: bool = False
    extraContext: Optional[Dict] = None


class GunnerChatResponse(BaseModel):
    reply: str
    persona: str
    provider: str
    model: str
    isDiagnosisMode: bool


def _normalize_messages(payload: GunnerChatRequest) -> List[Dict[str, str]]:
    if payload.messages:
        return [
            {"role": turn.role, "content": turn.content}
            for turn in payload.messages
        ]

    normalized_history = [
        {"role": turn.role, "content": turn.content}
        for turn in payload.history
    ]
    if payload.message:
        normalized_history.append({"role": "user", "content": payload.message})
    return normalized_history


@router.post("/chat")
async def gunner_chat(request: Request, payload: GunnerChatRequest) -> GunnerChatResponse:
    require_scope(request, "state")

    header_cabinet_id = request.headers.get("x-device-id")
    effective_cabinet_id = payload.cabinet_id or header_cabinet_id
    normalized_messages = _normalize_messages(payload)
    history_turns = max(len(normalized_messages) - 1, 0)

    logger.info(
        "panel=gunner route_start route=/api/local/gunner/chat cabinet_id=%s requested_diagnosis_mode=%s history_turns=%s",
        effective_cabinet_id or "missing",
        payload.isDiagnosisMode,
        history_turns,
    )

    try:
        result = await asyncio.to_thread(
            chat_with_gunner,
            messages=normalized_messages,
            cabinet_id=effective_cabinet_id,
            extra_context=payload.extraContext,
            is_diagnosis_mode=payload.isDiagnosisMode,
        )
        logger.info(
            "panel=gunner route_complete route=/api/local/gunner/chat cabinet_id=%s provider=%s model=%s",
            result.get("cabinet_id", effective_cabinet_id or "unknown-cabinet"),
            result.get("provider", "unknown"),
            result.get("model", "unknown"),
        )
        return GunnerChatResponse(
            reply=result["reply"],
            persona="gunner",
            provider=str(result.get("provider", "unknown")),
            model=str(result.get("model", "unknown")),
            isDiagnosisMode=bool(result.get("isDiagnosisMode", False)),
        )
    except PanelConfigNotFound as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except PanelDisabled as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("panel=gunner route_error route=/api/local/gunner/chat")
        raise HTTPException(status_code=500, detail=f"Gunner AI error: {exc}")
