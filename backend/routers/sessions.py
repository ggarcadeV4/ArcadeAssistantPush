"""
Session Management Router
Handles gaming session creation, tracking, and player roster management.

Used by:
- Vicky Voice: Create sessions with player rosters
- ScoreKeeper Sam: Get session info, address session owner
- LaunchBox LoRa: Auto-assign launches to active session
"""

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from pathlib import Path
import httpx

from backend.services.session_manager import get_session_manager, Session

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


# Pydantic Models
class PlayerInfo(BaseModel):
    """Player information for session roster."""
    id: str = Field(..., description="Profile ID (e.g., 'dad', 'mom', 'viki')")
    name: str = Field(..., description="Display name (e.g., 'Dad', 'Mom', 'Viki')")
    position: Optional[int] = Field(None, description="Player position (1-4)")


class SessionCreateRequest(BaseModel):
    """Request to create a new gaming session."""
    owner_id: str = Field(..., description="Profile ID of session owner")
    owner_name: str = Field(..., description="Display name of session owner")
    players: List[PlayerInfo] = Field(..., description="List of players in session")
    session_id: Optional[str] = Field(None, description="Optional custom session ID")


class SessionResponse(BaseModel):
    """Session information response."""
    session_id: str
    owner_id: str
    owner_name: str
    players: List[Dict[str, Any]]
    created_at: str
    last_activity: str
    games_played: List[Dict[str, Any]]


class SessionEndRequest(BaseModel):
    """Request to end a session."""
    session_id: str


# Endpoints
@router.post("/create", response_model=SessionResponse)
async def create_session(request: SessionCreateRequest):
    """
    Create a new gaming session with player roster.
    
    Example:
    ```json
    {
      "owner_id": "dallas",
      "owner_name": "Dallas",
      "players": [
        {"id": "dad", "name": "Dad", "position": 1},
        {"id": "mom", "name": "Mom", "position": 2},
        {"id": "sister", "name": "Sister", "position": 3},
        {"id": "dallas", "name": "Dallas", "position": 4}
      ]
    }
    ```
    """
    manager = get_session_manager()
    if not manager:
        raise HTTPException(status_code=500, detail="Session manager not initialized")
    
    # Convert PlayerInfo to dict
    players_dict = [p.dict() for p in request.players]
    
    session = manager.create_session(
        owner_id=request.owner_id,
        owner_name=request.owner_name,
        players=players_dict,
        session_id=request.session_id
    )
    
    # Broadcast session creation to frontend via Gateway Event Bus
    try:
        httpx.post(
            "http://localhost:8787/api/session/broadcast",
            json={
                "type": "session_created",
                "session_id": session.session_id,
                "owner_id": session.owner_id,
                "owner_name": session.owner_name,
                "players": players_dict,
                "source": "sessions_router"
            },
            timeout=2.0
        )
    except Exception as e:
        pass  # Don't fail session creation if broadcast fails
    
    return SessionResponse(**session.to_dict())


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get session information by ID."""
    manager = get_session_manager()
    if not manager:
        raise HTTPException(status_code=500, detail="Session manager not initialized")
    
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    return SessionResponse(**session.to_dict())


@router.get("/player/{player_id}", response_model=Optional[SessionResponse])
async def get_active_session_for_player(player_id: str):
    """Get the active session for a specific player."""
    manager = get_session_manager()
    if not manager:
        raise HTTPException(status_code=500, detail="Session manager not initialized")
    
    session = manager.get_active_session_for_player(player_id)
    if not session:
        return None
    
    return SessionResponse(**session.to_dict())


@router.get("/", response_model=List[SessionResponse])
async def get_all_sessions():
    """Get all active sessions."""
    manager = get_session_manager()
    if not manager:
        raise HTTPException(status_code=500, detail="Session manager not initialized")
    
    sessions = manager.get_all_active_sessions()
    return [SessionResponse(**s.to_dict()) for s in sessions]


@router.post("/end")
async def end_session(request: SessionEndRequest):
    """End a gaming session."""
    manager = get_session_manager()
    if not manager:
        raise HTTPException(status_code=500, detail="Session manager not initialized")
    
    success = manager.end_session(request.session_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Session {request.session_id} not found")
    
    # Broadcast session end to frontend via Gateway Event Bus
    try:
        httpx.post(
            "http://localhost:8787/api/session/broadcast",
            json={
                "type": "session_ended",
                "session_id": request.session_id,
                "source": "sessions_router"
            },
            timeout=2.0
        )
    except Exception as e:
        pass  # Don't fail if broadcast fails
    
    return {"success": True, "message": f"Session {request.session_id} ended"}


@router.post("/{session_id}/log-game")
async def log_game_to_session(
    session_id: str,
    game_id: str,
    game_title: str
):
    """Log a game played to a session."""
    manager = get_session_manager()
    if not manager:
        raise HTTPException(status_code=500, detail="Session manager not initialized")
    
    success = manager.log_game_to_session(session_id, game_id, game_title)
    if not success:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    return {"success": True, "message": "Game logged to session"}


@router.post("/cleanup")
async def cleanup_old_sessions(max_age_hours: int = 24):
    """Remove sessions older than max_age_hours."""
    manager = get_session_manager()
    if not manager:
        raise HTTPException(status_code=500, detail="Session manager not initialized")
    
    removed_count = manager.cleanup_old_sessions(max_age_hours)
    return {
        "success": True,
        "removed_count": removed_count,
        "message": f"Removed {removed_count} old session(s)"
    }
