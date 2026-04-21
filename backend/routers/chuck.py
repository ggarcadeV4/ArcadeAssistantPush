"""
Chuck chat router.

POST /api/local/chuck/chat
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.services.chuck_service import chat_with_chuck
from backend.services.drive_a_ai_client import PanelConfigNotFound, PanelDisabled
from backend.services.policies import require_scope

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chuck"])


class ChatTurn(BaseModel):
    role: str
    content: str


class ChuckChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: List[ChatTurn] = Field(default_factory=list)
    isDiagnosisMode: bool = False
    extraContext: Optional[Dict] = None


class ChuckChatResponse(BaseModel):
    reply: str
    persona: str
    isDiagnosisMode: bool


@router.post("/chat")
async def chuck_chat(request: Request, payload: ChuckChatRequest) -> ChuckChatResponse:
    require_scope(request, "state")

    cabinet_id = request.headers.get("x-device-id")
    logger.info(
        "panel=chuck route_start route=/api/local/chuck/chat cabinet_id=%s requested_diagnosis_mode=%s history_turns=%s",
        cabinet_id or "missing",
        payload.isDiagnosisMode,
        len(payload.history),
    )

    try:
        result = await asyncio.to_thread(
            chat_with_chuck,
            message=payload.message,
            history=[{"role": turn.role, "content": turn.content} for turn in payload.history],
            cabinet_id=cabinet_id,
            extra_context=payload.extraContext,
            is_diagnosis_mode=payload.isDiagnosisMode,
        )
        logger.info(
            "panel=chuck route_complete route=/api/local/chuck/chat cabinet_id=%s provider=%s model=%s",
            result.get("cabinet_id", cabinet_id or "unknown-cabinet"),
            result.get("provider", "unknown"),
            result.get("model", "unknown"),
        )
        return ChuckChatResponse(
            reply=result["reply"],
            persona="chuck",
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
        logger.exception("panel=chuck route_error route=/api/local/chuck/chat")
        raise HTTPException(status_code=500, detail=f"Chuck AI error: {exc}")
