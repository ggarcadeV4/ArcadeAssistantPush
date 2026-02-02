"""Voice Vicky router with lighting command endpoints."""

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import asyncio
import json
import structlog
import os
from backend.services.supabase_client import send_telemetry as sb_send_telemetry

from ..services.voice.service import VoiceService
from ..services.voice.models import LightingIntent

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/voice", tags=["Voice Vicky"])


class LightingCommandRequest(BaseModel):
    """Request to process lighting command."""
    transcript: str
    user_id: Optional[str] = None


class ParseCommandRequest(BaseModel):
    """Request to test command parsing."""
    transcript: str


# Dependency injection
def get_voice_service() -> VoiceService:
    """Get voice service instance."""
    # TODO: Inject actual LED service and Supabase client
    return VoiceService()


@router.post("/lighting-command")
async def process_lighting_command_stream(
    request: LightingCommandRequest,
    service: VoiceService = Depends(get_voice_service)
):
    """
    Process lighting command with streaming progress.

    Returns Server-Sent Events with progress updates.

    Example SSE responses:
    - data: {"status": "parsing", "transcript": "light P1 red"}
    - data: {"status": "parsed", "intent": {...}, "confidence": 0.9}
    - data: {"status": "applying", "target": "p1"}
    - data: {"status": "complete", "success": true, "tts_response": "..."}
    """
    async def event_generator():
        try:
            async for update in service.process_lighting_command(
                request.transcript,
                request.user_id
            ):
                yield f"data: {json.dumps(update)}\n\n"
        except asyncio.TimeoutError:
            try:
                device_id = os.getenv('AA_DEVICE_ID', '')
                await asyncio.to_thread(sb_send_telemetry, device_id, 'ERROR', 'STT_TIMEOUT', 'Speech-to-text request timed out', {'timeout_seconds': 10})
            except Exception:
                pass
            error_update = {"status": "error", "error": "STT timeout"}
            yield f"data: {json.dumps(error_update)}\n\n"
        except Exception as e:
            try:
                device_id = os.getenv('AA_DEVICE_ID', '')
                await asyncio.to_thread(sb_send_telemetry, device_id, 'ERROR', 'VOICE_PROCESSING_ERROR', str(e), {'error_type': type(e).__name__})
            except Exception:
                pass
            error_update = {"status": "error", "error": str(e)}
            yield f"data: {json.dumps(error_update)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/parse-command")
async def parse_command(
    request: ParseCommandRequest,
    service: VoiceService = Depends(get_voice_service)
):
    """
    Test parsing of lighting command (no application).

    Useful for testing command patterns without affecting hardware.
    """
    intent = await service.parser.parse(request.transcript)

    if not intent:
        raise HTTPException(
            status_code=400,
            detail="Could not parse lighting command"
        )

    return {
        "transcript": request.transcript,
        "intent": intent.dict(),
        "success": True
    }


@router.get("/command-history")
async def get_command_history(
    user_id: Optional[str] = None,
    limit: int = 50,
    service: VoiceService = Depends(get_voice_service)
):
    """Get recent voice command history."""
    if not service.supabase:
        raise HTTPException(
            status_code=501,
            detail={
                "code": "NOT_CONFIGURED",
                "message": "Supabase not configured for voice command history",
            },
        )

    try:
        query = service.supabase.table('voice_commands').select('*').order('timestamp', desc=True).limit(limit)

        if user_id:
            query = query.eq('user_id', user_id)

        response = await asyncio.to_thread(query.execute)

        return {
            "commands": response.data,
            "count": len(response.data)
        }

    except Exception as e:
        logger.error("history_fetch_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
