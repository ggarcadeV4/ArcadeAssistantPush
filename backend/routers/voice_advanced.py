"""Voice Vicky Advanced NLP router with multi-stage parsing pipeline."""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import asyncio
import json
import structlog
import os
from backend.services.supabase_client import send_telemetry as sb_send_telemetry

from ..services.voice.pipeline import get_pipeline, ParsingPipeline, ParseResult
from ..services.voice.models import LightingIntent

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/voice", tags=["Voice Vicky Advanced"])


class ParsePreviewRequest(BaseModel):
    """Request for parse preview (no hardware application)."""
    transcript: str
    user_id: Optional[str] = None
    active_panel: Optional[str] = None  # Context for panel-aware parsing


class ParsePreviewResponse(BaseModel):
    """Response with parse candidates and confidence."""
    transcript: str
    best_intent: Optional[dict]
    confidence: float
    stage: str
    candidates: List[dict]  # Alternative interpretations
    suggestions: List[str]  # User-friendly suggestions


class LightingCommandRequest(BaseModel):
    """Request to process lighting command with advanced parsing."""
    transcript: str
    user_id: Optional[str] = None
    active_panel: Optional[str] = None
    confidence_threshold: Optional[float] = 0.6  # Minimum confidence to apply


# Dependency injection
async def get_parsing_pipeline() -> ParsingPipeline:
    """Get parsing pipeline instance."""
    import os
    test_mode = os.getenv('TEST_MODE', '').lower() in ('true', '1')
    return await get_pipeline(test_mode=test_mode)


@router.post("/parse-preview")
async def parse_preview(
    request: ParsePreviewRequest,
    pipeline: ParsingPipeline = Depends(get_parsing_pipeline)
):
    """
    Preview parse results without applying to hardware.

    Returns all candidates from multi-stage pipeline with confidence scores.
    Useful for:
    - Testing voice commands
    - Debugging low-confidence parses
    - Frontend preview/confirmation UI

    Example:
    ```bash
    curl -X POST http://localhost:8000/api/voice/parse-preview \\
      -H "Content-Type: application/json" \\
      -d '{"transcript": "light p1 blue", "active_panel": "gunner"}'
    ```
    """
    logger.info("parse_preview_request",
               transcript=request.transcript,
               user_id=request.user_id,
               active_panel=request.active_panel)

    try:
        # Build context
        context = {}
        if request.user_id:
            context['user_id'] = request.user_id
        if request.active_panel:
            context['active_panel'] = request.active_panel

        # Collect all parse results
        results = []
        best_result = None
        best_confidence = 0.0

        async for result in pipeline.parse(request.transcript, context):
            if result.intent:
                results.append(result)

                if result.confidence > best_confidence:
                    best_result = result
                    best_confidence = result.confidence

        # Generate suggestions for low confidence
        suggestions = []
        if best_confidence < 0.7:
            suggestions.append("Try speaking more clearly")
            suggestions.append("Use simple commands like 'light P1 red'")

        if best_confidence < 0.5:
            suggestions.append("Command not recognized - check examples")

        # Build response
        return ParsePreviewResponse(
            transcript=request.transcript,
            best_intent=best_result.intent.dict() if best_result and best_result.intent else None,
            confidence=best_confidence,
            stage=best_result.stage if best_result else "none",
            candidates=[
                {
                    "intent": r.intent.dict() if r.intent else None,
                    "confidence": r.confidence,
                    "stage": r.stage
                }
                for r in results
            ],
            suggestions=suggestions
        )

    except Exception as e:
        logger.error("parse_preview_failed", error=str(e))
        try:
            device_id = os.getenv('AA_DEVICE_ID', '')
            await asyncio.to_thread(sb_send_telemetry, device_id, 'WARN', 'NLP_PARSE_ERROR', f"Failed to parse preview: {str(e)}", {'input_text': request.transcript})
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/lighting-command-advanced")
async def process_lighting_command_advanced(
    request: LightingCommandRequest,
    pipeline: ParsingPipeline = Depends(get_parsing_pipeline)
):
    """
    Process lighting command with advanced multi-stage parsing.

    Returns Server-Sent Events with progress from each parsing stage.

    Example SSE responses:
    - data: {"stage": "keyword", "confidence": 0.9, "status": "parsed"}
    - data: {"stage": "spacy", "confidence": 0.75, "status": "parsed"}
    - data: {"stage": "best", "intent": {...}, "status": "applying"}
    - data: {"status": "complete", "success": true}
    """
    async def event_generator():
        try:
            yield f"data: {json.dumps({'status': 'parsing', 'transcript': request.transcript})}\n\n"

            # Build context
            context = {}
            if request.user_id:
                context['user_id'] = request.user_id
            if request.active_panel:
                context['active_panel'] = request.active_panel

            # Parse through pipeline
            best_result = None
            best_confidence = 0.0

            async for result in pipeline.parse(request.transcript, context):
                # Stream each stage result
                stage_update = {
                    "stage": result.stage,
                    "confidence": result.confidence,
                    "status": "parsed"
                }

                if result.intent:
                    stage_update["intent"] = result.intent.dict()

                yield f"data: {json.dumps(stage_update)}\n\n"

                # Track best
                if result.intent and result.confidence > best_confidence:
                    best_result = result
                    best_confidence = result.confidence

            # Check confidence threshold
            if not best_result or best_confidence < request.confidence_threshold:
                error_update = {
                    "status": "error",
                    "error": "Low confidence - command unclear",
                    "confidence": best_confidence,
                    "threshold": request.confidence_threshold,
                    "suggestion": "Try rephrasing or use 'parse-preview' to test"
                }
                yield f"data: {json.dumps(error_update)}\n\n"
                return

            # Apply best intent
            apply_update = {
                "status": "applying",
                "intent": best_result.intent.dict(),
                "confidence": best_confidence,
                "stage": best_result.stage
            }
            yield f"data: {json.dumps(apply_update)}\n\n"

            # TODO: Apply to LED hardware (placeholder)
            # For now, simulate success
            await asyncio.sleep(0.2)

            # Complete
            complete_update = {
                "status": "complete",
                "success": True,
                "intent": best_result.intent.dict(),
                "confidence": best_confidence,
                "stage": best_result.stage,
                "tts_response": f"Applied {best_result.intent.action} to {best_result.intent.target}"
            }
            yield f"data: {json.dumps(complete_update)}\n\n"

        except Exception as e:
            try:
                device_id = os.getenv('AA_DEVICE_ID', '')
                await asyncio.to_thread(sb_send_telemetry, device_id, 'ERROR', 'VOICE_ERROR', str(e))
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


@router.get("/pipeline-stats")
async def get_pipeline_stats(
    pipeline: ParsingPipeline = Depends(get_parsing_pipeline)
):
    """
    Get pipeline statistics and configuration.

    Returns cache hit rate, worker queue status, etc.
    """
    stats = {
        "config": {
            "keyword_threshold": pipeline.config.keyword_threshold,
            "spacy_threshold": pipeline.config.spacy_threshold,
            "context_threshold": pipeline.config.context_threshold,
            "cache_enabled": pipeline.config.enable_cache,
            "worker_queue_enabled": pipeline.config.enable_worker_queue
        },
        "cache": {
            "size": len(pipeline._intent_cache),
            "max_size": 100
        },
        "stages": {
            "keyword": pipeline.keyword_stage.get_stage_name(),
            "spacy": pipeline.spacy_stage.get_stage_name(),
            "context": pipeline.context_stage.get_stage_name()
        }
    }

    if pipeline.worker_queue:
        stats["worker_queue"] = {
            "max_size": pipeline.worker_queue.queue.maxsize,
            "current_size": pipeline.worker_queue.queue.qsize(),
            "running": pipeline.worker_queue._running
        }

    return stats


@router.post("/clear-cache")
async def clear_cache(
    pipeline: ParsingPipeline = Depends(get_parsing_pipeline)
):
    """Clear intent cache (useful for testing)."""
    pipeline._intent_cache.clear()
    logger.info("cache_cleared")

    return {"status": "success", "message": "Cache cleared"}


@router.post("/update-user-vocab")
async def update_user_vocab(
    user_id: str,
    alias: str,
    canonical: str,
    pipeline: ParsingPipeline = Depends(get_parsing_pipeline)
):
    """
    Update user-specific vocabulary learning.

    Example:
    - User says "boo" but means "blue"
    - After correction, add alias: boo → blue
    - Future "boo" commands auto-correct to "blue"

    Args:
        user_id: User identifier
        alias: Misheard word
        canonical: Correct word

    Example:
    ```bash
    curl -X POST "http://localhost:8000/api/voice/update-user-vocab?user_id=user1&alias=boo&canonical=blue"
    ```
    """
    try:
        pipeline.context_stage.update_user_vocab(user_id, alias, canonical)

        return {
            "status": "success",
            "message": f"Updated vocab for {user_id}: {alias} → {canonical}"
        }

    except Exception as e:
        logger.error("vocab_update_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
