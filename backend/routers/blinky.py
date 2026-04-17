"""LED Blinky FastAPI router with streaming endpoints.

Provides REST endpoints for per-game LED lighting control with real-time
streaming updates. Integrates with the blinky service for pattern resolution
and hardware application.

Endpoints:
    POST /game-lights/{rom} - Apply game pattern with SSE streaming
    GET /game-lights/{rom}/preview - Preview pattern without hardware
    POST /tutor-sequence/{rom} - Run interactive tutor sequence
    GET /test-pattern - Rainbow hardware test
    POST /all-dark - Turn all LEDs off
    GET /patterns - List all loaded patterns
    GET /patterns/{rom} - Get specific pattern details
"""
import logging
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.services.blinky import (
    BlinkyService,
    PatternResolver,
    TutorMode,
    get_input_poller,
    get_resolver,
    get_service,
    run_tutor_sequence
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    tags=["LED Blinky"],
    responses={404: {"description": "Not found"}}
)


# ============================================================================
# Request/Response Models
# ============================================================================

class ApplyPatternRequest(BaseModel):
    """Request body for applying LED pattern."""
    device_id: int = Field(default=0, description="LED device ID")
    preview_only: bool = Field(default=False, description="Preview without hardware")
    overrides: Optional[Dict] = Field(None, description="Pattern overrides (brightness, colors)")
    tutor_mode: Optional[str] = Field(None, description="Enable coaching mode (kid/standard/pro)")


class TutorSequenceRequest(BaseModel):
    """Request body for tutor sequence."""
    mode: str = Field(default="standard", description="Difficulty mode (kid/standard/pro)")
    device_id: int = Field(default=0, description="LED device ID")
    preview_only: bool = Field(default=False, description="Preview without hardware")


# ============================================================================
# Endpoints
# ============================================================================

def validate_rom_name(rom: str) -> str:
    """Validate ROM name for security.

    Args:
        rom: ROM name to validate

    Returns:
        Sanitized ROM name

    Raises:
        HTTPException: If ROM name contains invalid characters
    """
    # Prevent path traversal attacks
    if '..' in rom or '/' in rom or '\\' in rom:
        raise HTTPException(
            status_code=400,
            detail="Invalid ROM name: path traversal characters not allowed"
        )

    # Limit length to prevent buffer overflow
    if len(rom) > 100:
        raise HTTPException(
            status_code=400,
            detail="Invalid ROM name: maximum 100 characters"
        )

    return rom.strip()


@router.post("/game-lights/{rom}")
async def apply_game_lights(
    rom: str,
    request: ApplyPatternRequest = ApplyPatternRequest(),
    service: BlinkyService = Depends(get_service)
):
    """Apply LED lighting pattern for a game with streaming updates.

    Streams JSON updates as pattern is applied to hardware, providing
    real-time progress and visualization data.

    Args:
        rom: ROM name identifier (e.g., 'sf2', 'dkong')
        request: Pattern application options
        service: BlinkyService (injected)

    Returns:
        StreamingResponse with application/x-ndjson content

    Stream format:
        Each line is a JSON object:
        {
            "status": "processing|applying|completed|error",
            "progress": 0.0-1.0,
            "batch": 1-N,
            "total_batches": N,
            "leds_updated": [...],
            "pattern": {...}
        }

    Example:
        POST /api/blinky/game-lights/sf2
        {
            "device_id": 0,
            "preview_only": false,
            "overrides": {"brightness": 80}
        }
    """
    # Validate ROM name for security
    rom = validate_rom_name(rom)

    logger.info(f"Applying game lights for ROM: {rom}")

    async def stream_generator():
        """Generate streaming responses."""
        import json

        try:
            async for update in service.process_game_lights(
                rom=rom,
                overrides=request.overrides,
                device_id=request.device_id,
                preview_only=request.preview_only,
                tutor_mode=request.tutor_mode  # NEW: Enable coaching sequences
            ):
                # Send as newline-delimited JSON
                yield f"{json.dumps(update)}\n"

        except Exception as e:
            logger.error(f"Stream error for {rom}: {e}", exc_info=True)
            error_update = {"status": "error", "error": str(e)}
            yield f"{json.dumps(error_update)}\n"

    return StreamingResponse(
        stream_generator(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.get("/game-lights/{rom}/preview")
async def preview_game_lights(
    rom: str,
    brightness: Optional[int] = Query(None, ge=0, le=100),
    total_leds: int = Query(32, ge=8, le=96),
    service: BlinkyService = Depends(get_service)
):
    """Get pattern preview without applying to hardware.

    Returns complete pattern data with all LED assignments for
    frontend visualization.

    Args:
        rom: ROM name
        brightness: Optional brightness override (0-100)
        total_leds: Total LED count for preview
        service: BlinkyService (injected)

    Returns:
        PatternPreview with LED assignments and metadata

    Example:
        GET /api/blinky/game-lights/sf2/preview?brightness=80
    """
    logger.debug(f"Generating preview for ROM: {rom}")

    try:
        overrides = {}
        if brightness is not None:
            overrides['brightness'] = brightness

        preview = await service.get_pattern_preview(
            rom=rom,
            overrides=overrides if overrides else None,
            total_leds=total_leds
        )

        return preview

    except Exception as e:
        logger.error(f"Preview error for {rom}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tutor-sequence/{rom}")
async def run_tutor_sequence_endpoint(
    rom: str,
    request: TutorSequenceRequest = TutorSequenceRequest(),
    resolver: PatternResolver = Depends(get_resolver)
):
    """Run interactive LED tutor sequence with streaming updates.

    Executes a step-by-step LED tutorial that guides the player through
    game controls with pulsing LEDs and adaptive difficulty.

    Args:
        rom: ROM name
        request: Tutor sequence options
        resolver: PatternResolver (injected)

    Returns:
        StreamingResponse with step-by-step updates

    Stream format:
        {
            "led_id": 1-96,
            "action": "pulse|hold|fade",
            "color": "#RRGGBB",
            "status": "executing|completed|retry|skipped",
            "step_index": 0-N,
            "total_steps": N,
            "progress": 0.0-1.0,
            "hint": "...",
            "retry_count": 0-3
        }

    Example:
        POST /api/blinky/tutor-sequence/sf2
        {"mode": "kid", "preview_only": false}
    """
    logger.info(f"Starting tutor sequence for ROM: {rom} (mode: {request.mode})")

    # Validate mode
    try:
        mode = TutorMode(request.mode.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{request.mode}'. Must be: kid, standard, pro"
        )

    # Get pattern
    pattern = resolver.get_pattern(rom)

    # Get input poller
    poller = get_input_poller(test_mode=request.preview_only)

    async def stream_generator():
        """Generate streaming sequence updates."""
        import json

        try:
            async for update in run_tutor_sequence(
                pattern=pattern,
                mode=mode,
                poller=poller,
                device_id=request.device_id,
                preview_only=request.preview_only
            ):
                # Convert StepUpdate to dict (Pydantic V2)
                update_dict = update.model_dump()
                yield f"{json.dumps(update_dict)}\n"

        except Exception as e:
            logger.error(f"Tutor sequence error for {rom}: {e}", exc_info=True)
            error_update = {"status": "error", "error": str(e)}
            yield f"{json.dumps(error_update)}\n"

    return StreamingResponse(
        stream_generator(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/test-pattern")
async def run_test_pattern(
    device_id: int = Query(0, description="LED device ID"),
    service: BlinkyService = Depends(get_service)
):
    """Run rainbow test pattern for hardware diagnostics.

    Cycles through all LEDs with rainbow colors to verify hardware
    connectivity and LED count.

    Args:
        device_id: LED device ID
        service: BlinkyService (injected)

    Returns:
        StreamingResponse with test progress

    Example:
        GET /api/blinky/test-pattern?device_id=0
    """
    logger.info(f"Running test pattern on device {device_id}")

    async def stream_generator():
        """Generate test pattern updates."""
        import json

        async for update in service.apply_test_pattern(device_id=device_id):
            yield f"{json.dumps(update)}\n"

    return StreamingResponse(
        stream_generator(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/all-dark")
async def turn_all_dark(
    device_id: int = Query(0, description="LED device ID"),
    total_leds: int = Query(32, ge=8, le=96, description="Total LED count"),
    service: BlinkyService = Depends(get_service)
):
    """Turn off all LEDs (set to black).

    Use cases:
    - Game exit cleanup
    - Panel switching
    - Power saving mode

    Args:
        device_id: LED device ID
        total_leds: Total LED count to darken
        service: BlinkyService (injected)

    Returns:
        Success message

    Example:
        POST /api/blinky/all-dark?device_id=0&total_leds=32
    """
    logger.info(f"Darkening all {total_leds} LEDs on device {device_id}")

    try:
        await service.apply_all_dark(device_id=device_id, total_leds=total_leds)
        return {
            "status": "success",
            "message": f"Darkened {total_leds} LEDs on device {device_id}"
        }
    except Exception as e:
        logger.error(f"Error darkening LEDs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns")
async def list_patterns(
    limit: int = Query(100, ge=1, le=1000, description="Max patterns to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    resolver: PatternResolver = Depends(get_resolver)
):
    """List all loaded LED patterns.

    Args:
        limit: Max patterns to return (pagination)
        offset: Offset for pagination
        resolver: PatternResolver (injected)

    Returns:
        Dict with patterns and metadata

    Example:
        GET /api/blinky/patterns?limit=50&offset=0
    """
    all_patterns = resolver.get_all_patterns()

    # Pagination
    pattern_items = list(all_patterns.items())[offset:offset + limit]

    patterns_list = []
    for rom, pattern in pattern_items:
        patterns_list.append({
            "rom": pattern.rom,
            "game_name": pattern.game_name,
            "platform": pattern.platform,
            "active_count": len(pattern.active_leds),
            "inactive_count": len(pattern.inactive_leds),
            "control_count": pattern.control_count
        })

    return {
        "total": len(all_patterns),
        "limit": limit,
        "offset": offset,
        "patterns": patterns_list
    }


@router.get("/patterns/{rom}")
async def get_pattern_details(
    rom: str,
    resolver: PatternResolver = Depends(get_resolver)
):
    """Get detailed pattern information for a ROM.

    Args:
        rom: ROM name
        resolver: PatternResolver (injected)

    Returns:
        Complete GamePattern details

    Example:
        GET /api/blinky/patterns/sf2
    """
    pattern = resolver.get_pattern(rom)

    return {
        "rom": pattern.rom,
        "game_name": pattern.game_name,
        "platform": pattern.platform,
        "active_leds": pattern.active_leds,
        "inactive_leds": pattern.inactive_leds,
        "inactive_color": pattern.inactive_color,
        "brightness": pattern.brightness,
        "control_count": pattern.control_count
    }


# ============================================================================
# Health & Status
# ============================================================================

@router.get("/health")
async def health_check(
    resolver: PatternResolver = Depends(get_resolver)
):
    """Health check endpoint.

    Returns:
        Service status and pattern count
    """
    patterns = resolver.get_all_patterns()

    return {
        "status": "healthy",
        "service": "LED Blinky",
        "patterns_loaded": len(patterns),
        "mock_mode": len(patterns) < 50  # Heuristic: <50 patterns = mock mode
    }


# ============================================================================
# Quest Guide Mode (NEW - 2025-10-31)
# ============================================================================

class QuestRequest(BaseModel):
    """Request body for quest sequence."""
    quest_id: str = Field(default="climb_quest", description="Quest preset ID")
    difficulty: str = Field(default="kid", description="Difficulty level (easy/kid/standard)")
    tts_enabled: bool = Field(default=True, description="Enable Voice Vicky narration")
    device_id: int = Field(default=0, description="LED device ID")


@router.post("/quest/{rom}")
async def run_quest(
    rom: str,
    request: QuestRequest = QuestRequest(),
    resolver: PatternResolver = Depends(get_resolver)
):
    """Run interactive quest sequence with story narration.

    Provides kid-friendly, story-driven LED tutorials with Voice Vicky
    integration, adaptive difficulty, and ScoreKeeper rewards.

    Args:
        rom: ROM name
        request: Quest configuration
        resolver: PatternResolver (injected)

    Returns:
        StreamingResponse with quest progress updates

    Stream format:
        {
            "status": "quest_intro|quest_step|quest_step_success|quest_step_retry|quest_completed|quest_error",
            "theme": {...},  // Quest theme metadata
            "step_index": 0-N,
            "total_steps": N,
            "led_id": 1-96,
            "color": "#RRGGBB",
            "hint": "...",
            "message": "...",
            "progress": 0.0-1.0,
            "reward_points": 0-100
        }

    Example:
        POST /api/blinky/quest/dkong
        {
            "quest_id": "climb_quest",
            "difficulty": "kid",
            "tts_enabled": true
        }
    """
    from backend.services.blinky.quest_guide import run_quest_sequence

    logger.info(f"Starting quest '{request.quest_id}' for ROM: {rom}")

    # Get pattern
    pattern = resolver.get_pattern(rom)

    async def stream_generator():
        """Generate streaming quest updates."""
        import json

        try:
            async for update in run_quest_sequence(
                pattern=pattern,
                quest_id=request.quest_id,
                difficulty=request.difficulty,
                tts_enabled=request.tts_enabled,
                device_id=request.device_id
            ):
                yield f"{json.dumps(update)}\n"

        except Exception as e:
            logger.error(f"Quest error for {rom}: {e}", exc_info=True)
            error_update = {"status": "quest_error", "error": str(e)}
            yield f"{json.dumps(error_update)}\n"

    return StreamingResponse(
        stream_generator(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/quests")
async def list_quests():
    """List all available quest presets.

    Returns:
        List of quest themes with metadata

    Example:
        GET /api/blinky/quests
    """
    from backend.services.blinky.quest_guide import get_available_quests

    quests = get_available_quests()
    return {
        "total": len(quests),
        "quests": quests
    }


@router.get("/quest-recommendation/{rom}")
async def get_quest_recommendation(
    rom: str,
    age: Optional[int] = Query(None, ge=3, le=18, description="Player age for recommendation"),
    resolver: PatternResolver = Depends(get_resolver)
):
    """Get recommended quest for a game based on pattern and player age.

    Args:
        rom: ROM name
        age: Optional player age
        resolver: PatternResolver (injected)

    Returns:
        Recommended quest ID and metadata

    Example:
        GET /api/blinky/quest-recommendation/sf2?age=8
    """
    from backend.services.blinky.quest_guide import get_quest_for_game

    pattern = resolver.get_pattern(rom)
    quest_id = get_quest_for_game(pattern, age)

    from backend.services.blinky.quest_guide import QUEST_PRESETS
    quest_theme = QUEST_PRESETS[quest_id]

    return {
        "rom": rom,
        "recommended_quest": quest_id,
        "quest_name": quest_theme.name,
        "quest_description": quest_theme.description,
        "reward_points": quest_theme.reward_points,
        "reason": f"Recommended based on game type and {'age ' + str(age) if age else 'default heuristics'}"
    }
