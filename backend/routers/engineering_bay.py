"""
Engineering Bay Chat Router — unified AI chat for Vicky, Blinky, Gunner, and Doc.

POST /api/local/engineering-bay/chat
Body: { persona, message, history, isDiagnosisMode, extraContext }
"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

from backend.services.policies import require_scope

router = APIRouter(prefix="/local/engineering-bay", tags=["engineering-bay"])

VALID_PERSONAS = {"vicky", "gunner"}


class ChatTurn(BaseModel):
    role: str
    content: str


class EBChatRequest(BaseModel):
    persona: str = Field(..., description="One of: vicky, blinky, gunner, doc, chuck, wiz")
    message: str = Field(..., min_length=1, max_length=4000)
    history: List[ChatTurn] = Field(default_factory=list)
    isDiagnosisMode: bool = False
    extraContext: Optional[Dict] = None


class EBChatResponse(BaseModel):
    reply: str
    persona: str
    isDiagnosisMode: bool


@router.post("/chat")
async def engineering_bay_chat(request: Request, payload: EBChatRequest):
    """
    Unified AI chat for all Engineering Bay personas (EB-AI-01).
    Routes to the correct persona prompt automatically.
    """
    require_scope(request, "state")

    if payload.persona not in VALID_PERSONAS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown persona '{payload.persona}'. Valid: {sorted(VALID_PERSONAS)}"
        )

    try:
        from backend.services.engineering_bay.ai import engineering_bay_chat as _chat

        history = [{"role": t.role, "content": t.content} for t in payload.history]
        reply = await _chat(
            persona=payload.persona,
            message=payload.message,
            history=history,
            is_diagnosis_mode=payload.isDiagnosisMode,
            extra_context=payload.extraContext,
        )
        return EBChatResponse(
            reply=reply,
            persona=payload.persona,
            isDiagnosisMode=payload.isDiagnosisMode,
        )

    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Engineering Bay AI error: {exc}")
