"""
High Score API Router
Provides endpoints for ScoreKeeper Sam to access and manage high scores.

@router: hiscore
@role: High score retrieval and management
@owner: Arcade Assistant / ScoreKeeper Sam
@status: active
"""

from fastapi import APIRouter, HTTPException, Query
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import logging

from backend.services.hiscore_watcher import get_hiscore_watcher

router = APIRouter(prefix="/api/local/hiscore", tags=["hiscore"])
logger = logging.getLogger(__name__)


@router.get("/game/{rom_name}")
async def get_game_hiscores(rom_name: str) -> Dict[str, Any]:
    """
    Get high scores for a specific game.
    
    Args:
        rom_name: MAME ROM name (e.g., "pacman", "galaga", "dkong")
    
    Returns:
        High score table for the game
    """
    watcher = get_hiscore_watcher()
    if not watcher:
        raise HTTPException(status_code=503, detail="Hiscore watcher not initialized")
    
    scores = watcher.get_game_scores(rom_name)
    
    return {
        "game": rom_name,
        "scores": scores,
        "count": len(scores),
        "supported": watcher.dat_parser.has_game(rom_name) if watcher.dat_parser else False
    }


@router.get("/games")
async def list_games_with_hiscores() -> Dict[str, Any]:
    """
    List all games that have saved high scores.
    
    Returns:
        List of games with .hi files
    """
    watcher = get_hiscore_watcher()
    if not watcher:
        raise HTTPException(status_code=503, detail="Hiscore watcher not initialized")
    
    all_scores = watcher.scan_all_hiscores()
    
    games = []
    for rom_name, scores in all_scores.items():
        if scores:
            top_score = max(scores, key=lambda s: s.get('score', 0))
            games.append({
                "rom_name": rom_name,
                "top_score": top_score.get('score', 0),
                "top_player": top_score.get('initials', '???'),
                "entry_count": len(scores)
            })
    
    # Sort by top score descending
    games.sort(key=lambda g: g['top_score'], reverse=True)
    
    return {
        "games": games,
        "total_games": len(games)
    }


@router.get("/leaderboard")
async def get_house_leaderboard(
    limit: int = Query(default=20, ge=1, le=100)
) -> Dict[str, Any]:
    """
    Get house-wide leaderboard across all games.
    
    Returns top scores from all games, useful for "Top Dog" display.
    """
    watcher = get_hiscore_watcher()
    if not watcher:
        raise HTTPException(status_code=503, detail="Hiscore watcher not initialized")
    
    all_scores = watcher.scan_all_hiscores()
    
    # Flatten all scores with game info
    all_entries = []
    for rom_name, scores in all_scores.items():
        for score in scores:
            all_entries.append({
                "game": rom_name,
                "player": score.get('initials', '???'),
                "score": score.get('score', 0),
                "rank_in_game": score.get('rank', 0)
            })
    
    # Sort by score descending
    all_entries.sort(key=lambda e: e['score'], reverse=True)
    
    return {
        "leaderboard": all_entries[:limit],
        "total_entries": len(all_entries),
        "games_counted": len(all_scores)
    }


@router.get("/player/{initials}")
async def get_player_scores(initials: str) -> Dict[str, Any]:
    """
    Get all high scores for a player by their initials.
    
    Args:
        initials: Player initials (e.g., "AAA", "DAD", "MOM")
    
    Returns:
        All games where this player has a high score
    """
    watcher = get_hiscore_watcher()
    if not watcher:
        raise HTTPException(status_code=503, detail="Hiscore watcher not initialized")
    
    initials_upper = initials.upper()
    all_scores = watcher.scan_all_hiscores()
    
    player_scores = []
    for rom_name, scores in all_scores.items():
        for score in scores:
            if score.get('initials', '').upper() == initials_upper:
                player_scores.append({
                    "game": rom_name,
                    "score": score.get('score', 0),
                    "rank": score.get('rank', 0)
                })
    
    # Sort by score descending
    player_scores.sort(key=lambda s: s['score'], reverse=True)
    
    return {
        "player": initials_upper,
        "scores": player_scores,
        "games_count": len(player_scores),
        "total_score": sum(s['score'] for s in player_scores)
    }


@router.get("/supported")
async def get_supported_games(
    search: Optional[str] = Query(default=None, description="Search filter for ROM names")
) -> Dict[str, Any]:
    """
    List games supported by hiscore.dat.
    
    Returns:
        List of ROM names that have hiscore definitions
    """
    watcher = get_hiscore_watcher()
    if not watcher or not watcher.dat_parser:
        raise HTTPException(status_code=503, detail="Hiscore watcher not initialized")
    
    games = list(watcher.dat_parser.game_definitions.keys())
    
    if search:
        search_lower = search.lower()
        games = [g for g in games if search_lower in g.lower()]
    
    games.sort()
    
    return {
        "supported_games": games[:500],  # Limit response size
        "total_supported": len(watcher.dat_parser.game_definitions),
        "filtered_count": len(games)
    }


@router.post("/refresh")
async def refresh_all_hiscores() -> Dict[str, Any]:
    """
    Manually refresh and re-parse all hiscore files.
    
    Useful after bulk imports or manual file changes.
    """
    watcher = get_hiscore_watcher()
    if not watcher:
        raise HTTPException(status_code=503, detail="Hiscore watcher not initialized")
    
    all_scores = watcher.scan_all_hiscores()
    
    # Update the index file
    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).isoformat()
    
    index = {
        'version': 1,
        'last_updated': timestamp,
        'games': []
    }
    
    for rom_name, scores in all_scores.items():
        if scores:
            index['games'].append({
                'game_title': rom_name,
                'game_id': None,
                'top_scores': [
                    {
                        'player': s.get('initials', '???'),
                        'score': s.get('score', 0),
                        'rank': s.get('rank', 0),
                        'timestamp': timestamp
                    }
                    for s in scores[:10]
                ]
            })
    
    # Save index
    try:
        with open(watcher.high_scores_index_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving index: {e}")
    
    return {
        "status": "refreshed",
        "games_processed": len(all_scores),
        "games_with_scores": len(index['games']),
        "timestamp": timestamp
    }


# =============================================================================
# AI Vision Score Endpoints
# =============================================================================

from pydantic import BaseModel


class GameExitRequest(BaseModel):
    """Request body for game exit processing."""
    rom_name: str
    player_name: Optional[str] = None


class ManualScoreRequest(BaseModel):
    """Request body for manual score entry."""
    rom_name: str
    score: int
    initials: str = "???"
    player_name: Optional[str] = None


@router.post("/vision/game-exit")
async def vision_process_game_exit(request: GameExitRequest) -> Dict[str, Any]:
    """
    Process a game exit event with AI Vision.
    
    1. Captures screenshot of current screen
    2. Sends to Gemini Vision to extract score
    3. Saves to scores database
    4. Broadcasts to ScoreKeeper Sam
    
    Call this endpoint when MAME exits.
    """
    from backend.services.vision_score_service import get_vision_score_service
    
    service = get_vision_score_service()
    if not service:
        raise HTTPException(
            status_code=503,
            detail="Vision score service not initialized"
        )
    
    result = await service.process_game_exit(
        game_rom=request.rom_name,
        player_name=request.player_name
    )
    
    if result:
        return {
            "status": "success",
            "game": request.rom_name,
            "score_extracted": result.get("score"),
            "initials": result.get("initials"),
            "confidence": result.get("confidence"),
            "screen_type": result.get("screen_type")
        }
    else:
        return {
            "status": "failed",
            "game": request.rom_name,
            "message": "Could not extract score from screenshot"
        }


@router.post("/vision/capture")
async def vision_capture_screenshot(request: GameExitRequest) -> Dict[str, Any]:
    """
    Capture a screenshot for a game (without AI processing).
    
    Useful for testing or manual extraction later.
    """
    from backend.services.vision_score_service import get_vision_score_service
    
    service = get_vision_score_service()
    if not service:
        raise HTTPException(
            status_code=503,
            detail="Vision score service not initialized"
        )
    
    screenshot_path = service.capture_screen(request.rom_name)
    
    if screenshot_path:
        return {
            "status": "captured",
            "game": request.rom_name,
            "screenshot_path": str(screenshot_path)
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Screenshot capture failed"
        )


@router.get("/vision/scores/{rom_name}")
async def vision_get_game_scores(rom_name: str) -> Dict[str, Any]:
    """
    Get AI-extracted high scores for a game.
    
    Returns scores from the AI Vision system (separate from hiscore.dat).
    """
    from backend.services.vision_score_service import get_vision_score_service
    
    service = get_vision_score_service()
    if not service:
        raise HTTPException(
            status_code=503,
            detail="Vision score service not initialized"
        )
    
    scores = service.get_high_scores(rom_name)
    
    return {
        "game": rom_name,
        "scores": scores,
        "count": len(scores),
        "source": "ai_vision"
    }


@router.post("/vision/manual")
async def vision_manual_score_entry(request: ManualScoreRequest) -> Dict[str, Any]:
    """
    Manually enter a score (fallback when AI can't extract).
    
    Useful for user corrections or games AI struggles with.
    """
    from backend.services.vision_score_service import get_vision_score_service
    from datetime import datetime, timezone
    
    service = get_vision_score_service()
    if not service:
        raise HTTPException(
            status_code=503,
            detail="Vision score service not initialized"
        )
    
    score_data = {
        "score": request.score,
        "initials": request.initials.upper()[:3],
        "screen_type": "manual_entry",
        "confidence": 1.0,
        "game_rom": request.rom_name,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "source": "manual"
    }
    
    if request.player_name:
        score_data["player_name"] = request.player_name
    
    await service.save_score(request.rom_name, score_data)
    
    return {
        "status": "saved",
        "game": request.rom_name,
        "score": request.score,
        "initials": score_data["initials"]
    }


@router.get("/vision/status")
async def vision_service_status() -> Dict[str, Any]:
    """
    Get status of the AI Vision Score service.
    """
    from backend.services.vision_score_service import get_vision_score_service
    
    service = get_vision_score_service()
    
    if service:
        return {
            "status": "active",
            "scores_dir": str(service.scores_dir),
            "screenshots_dir": str(service.screenshots_dir),
            "games_tracked": len(service._scores_cache),
            "gemini_configured": bool(service.gemini_api_key)
        }
    else:
        return {
            "status": "not_initialized",
            "message": "Vision score service not started"
        }
