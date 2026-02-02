"""
Tournament Mode API Router

Endpoints for managing tournament mode integration between
MAME's Tab menu plugin and ScoreKeeper Sam.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import json
from pathlib import Path

from backend.services.match_watcher import get_match_watcher

router = APIRouter(prefix="/api/tournament", tags=["Tournament"])


class SetMatchRequest(BaseModel):
    """Request to set the current match for MAME to display."""
    p1_name: str
    p2_name: str
    tournament_id: Optional[str] = None
    match_id: Optional[str] = None


class MatchResult(BaseModel):
    """Match result from MAME plugin."""
    game: str
    winner: str  # "p1" or "p2"
    winner_name: str
    loser_name: Optional[str] = None
    tournament_id: Optional[str] = None
    match_id: Optional[str] = None


@router.post("/match/set")
async def set_current_match(request: SetMatchRequest):
    """
    **Set Current Match for MAME**
    
    Writes the current matchup to current_match.json.
    MAME's Tab menu will read this and display:
    "Current Match: [P1 Name] vs [P2 Name]"
    """
    watcher = get_match_watcher()
    match_data = watcher.set_current_match(
        p1_name=request.p1_name,
        p2_name=request.p2_name,
        tournament_id=request.tournament_id,
        match_id=request.match_id
    )
    
    return {
        "status": "match_set",
        "match": match_data
    }


@router.get("/match/current")
async def get_current_match():
    """
    **Get Current Match**
    
    Returns the current match being tracked (if any).
    """
    watcher = get_match_watcher()
    match = watcher.get_current_match()
    
    if not match:
        return {"status": "no_active_match"}
    
    return {
        "status": "active",
        "match": match
    }


@router.delete("/match/clear")
async def clear_current_match():
    """
    **Clear Current Match**
    
    Clears the current match. Call this when moving to next match.
    """
    watcher = get_match_watcher()
    watcher.clear_current_match()
    
    return {"status": "cleared"}


@router.get("/match/result")
async def get_last_result():
    """
    **Get Last Match Result**
    
    Returns the most recent match result written by MAME.
    """
    results_path = Path(r"A:\.aa\state\scorekeeper\match_results.json")
    
    if not results_path.exists():
        return {"status": "no_results"}
    
    try:
        with open(results_path, 'r') as f:
            result = json.load(f)
        
        return {
            "status": "result_found",
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/watcher/status")
async def get_watcher_status():
    """
    **Get Tournament Watcher Status**
    
    Returns whether the match result watcher is running.
    """
    watcher = get_match_watcher()
    return watcher.get_status()


@router.post("/watcher/start")
async def start_watcher():
    """
    **Start Tournament Watcher**
    
    Starts the background watcher for match results.
    """
    watcher = get_match_watcher()
    watcher.start()
    return {"status": "started"}


@router.post("/watcher/stop")
async def stop_watcher():
    """
    **Stop Tournament Watcher**
    
    Stops the background watcher.
    """
    watcher = get_match_watcher()
    watcher.stop()
    return {"status": "stopped"}
