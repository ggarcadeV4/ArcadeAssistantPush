"""
Tendency File API Router
Provides endpoints for reading/writing user tendency files.
"""

from fastapi import APIRouter, HTTPException, Query, Request
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import logging

from backend.services.tendency_service import get_tendency_service, TendencyService

router = APIRouter(prefix="/api/local/tendencies", tags=["tendencies"])
logger = logging.getLogger(__name__)


class PanelUpdateRequest(BaseModel):
    """Request to update a panel's namespace in the tendency file."""
    panel: str = Field(..., description="Panel name (e.g., 'gunner', 'dewey')")
    data: Dict[str, Any] = Field(..., description="Data to merge into panel namespace")


class GameLaunchRequest(BaseModel):
    """Request to track a game launch."""
    game_id: str
    title: str
    platform: str
    genre: Optional[str] = None


class SessionEndRequest(BaseModel):
    """Request to track a session end."""
    game_id: str
    duration_minutes: int
    score: Optional[int] = None


class PreferencesUpdateRequest(BaseModel):
    """Request to update user preferences."""
    favorite_genres: Optional[List[str]] = None
    favorite_platforms: Optional[List[str]] = None
    favorite_eras: Optional[List[str]] = None
    difficulty_preference: Optional[str] = None
    session_length_preference: Optional[str] = None
    multiplayer_preference: Optional[str] = None


class CoreUpdateRequest(BaseModel):
    """Request to update core profile info."""
    display_name: Optional[str] = None
    initials: Optional[str] = None
    age_group: Optional[str] = None
    preferred_language: Optional[str] = None


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/profiles")
async def list_profiles():
    """
    List all available user profiles.
    """
    service = get_tendency_service()
    profiles = service.list_profiles()
    return {
        "profiles": profiles,
        "count": len(profiles)
    }


@router.get("/profile/{profile_id}")
async def get_profile_tendencies(profile_id: str):
    """
    Get the full tendency file for a profile.
    
    Creates a new profile with defaults if it doesn't exist.
    """
    service = get_tendency_service()
    data = service.load(profile_id)
    return data


@router.get("/profile/{profile_id}/summary")
async def get_profile_summary(profile_id: str):
    """
    Get just the AI summary for a profile.
    
    This is what panels inject into LLM prompts to understand the user.
    """
    service = get_tendency_service()
    summary = service.get_ai_context(profile_id)
    return {
        "profile_id": profile_id,
        "ai_summary": summary
    }


@router.get("/profile/{profile_id}/panel/{panel}")
async def get_panel_tendencies(profile_id: str, panel: str):
    """
    Get a specific panel's namespace from the tendency file.
    """
    service = get_tendency_service()
    panel_data = service.get_panel_data(profile_id, panel)
    return {
        "profile_id": profile_id,
        "panel": panel,
        "data": panel_data
    }


@router.put("/profile/{profile_id}/panel")
async def update_panel_tendencies(profile_id: str, request: PanelUpdateRequest):
    """
    Update a specific panel's namespace in the tendency file.
    
    Each panel should only update its own namespace.
    """
    valid_panels = [
        "vicky_voice", "controller_chuck", "console_wizard",
        "launchbox_lora", "scorekeeper_sam", "gunner",
        "led_blinky", "dewey", "doc"
    ]
    
    if request.panel not in valid_panels:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid panel '{request.panel}'. Valid: {valid_panels}"
        )
    
    service = get_tendency_service()
    service.update_panel_data(profile_id, request.panel, request.data)
    
    return {
        "success": True,
        "profile_id": profile_id,
        "panel": request.panel,
        "updated_fields": list(request.data.keys())
    }


@router.put("/profile/{profile_id}/preferences")
async def update_preferences(profile_id: str, request: PreferencesUpdateRequest):
    """
    Update user gaming preferences.
    """
    service = get_tendency_service()
    data = service.load(profile_id)
    
    if "preferences" not in data:
        data["preferences"] = {}
    
    updates = request.model_dump(exclude_none=True)
    data["preferences"].update(updates)
    
    service.save(profile_id, data)
    
    return {
        "success": True,
        "profile_id": profile_id,
        "updated_preferences": updates
    }


@router.put("/profile/{profile_id}/core")
async def update_core_info(profile_id: str, request: CoreUpdateRequest):
    """
    Update core profile information (name, initials, etc).
    """
    service = get_tendency_service()
    data = service.load(profile_id)
    
    if "core" not in data:
        data["core"] = {}
    
    updates = request.model_dump(exclude_none=True)
    data["core"].update(updates)
    
    service.save(profile_id, data)
    
    return {
        "success": True,
        "profile_id": profile_id,
        "updated_core": updates
    }


@router.post("/profile/{profile_id}/track/launch")
async def track_game_launch(profile_id: str, request: GameLaunchRequest):
    """
    Track a game launch for statistics and recommendations.
    
    Call this when a user starts playing a game.
    """
    service = get_tendency_service()
    service.track_game_launch(
        profile_id=profile_id,
        game_id=request.game_id,
        title=request.title,
        platform=request.platform,
        genre=request.genre
    )
    
    return {
        "success": True,
        "profile_id": profile_id,
        "tracked": {
            "game": request.title,
            "platform": request.platform
        }
    }


@router.post("/profile/{profile_id}/track/end")
async def track_session_end(profile_id: str, request: SessionEndRequest):
    """
    Track a game session ending.
    
    Call this when a user stops playing a game.
    """
    service = get_tendency_service()
    service.track_session_end(
        profile_id=profile_id,
        game_id=request.game_id,
        duration_minutes=request.duration_minutes,
        score=request.score
    )
    
    return {
        "success": True,
        "profile_id": profile_id,
        "tracked": {
            "game_id": request.game_id,
            "duration_minutes": request.duration_minutes
        }
    }


@router.get("/profile/{profile_id}/recommendations")
async def get_recommendations(
    profile_id: str,
    limit: int = Query(10, ge=1, le=50)
):
    """
    Get game recommendations based on user tendencies.
    
    Returns recommended genres, platforms, and recent activity
    that other services can use to filter games.
    """
    service = get_tendency_service()
    data = service.load(profile_id)
    
    return {
        "profile_id": profile_id,
        "recommended_genres": data.get("preferences", {}).get("favorite_genres", []),
        "recommended_platforms": data.get("preferences", {}).get("favorite_platforms", []),
        "avoid_genres": data.get("preferences", {}).get("disliked_genres", []),
        "recent_games": [g["title"] for g in data.get("recent", {}).get("last_10_games", [])],
        "difficulty": data.get("preferences", {}).get("difficulty_preference", "medium"),
        "ai_summary": data.get("ai_summary", "")
    }


@router.delete("/profile/{profile_id}")
async def delete_profile(profile_id: str):
    """
    Delete a profile's tendency file.
    
    Use with caution - this removes all user data.
    """
    import shutil
    
    service = get_tendency_service()
    profile_dir = service.profiles_root / profile_id.lower()
    
    if not profile_dir.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")
    
    # Create backup first
    backup_dir = service.profiles_root / f".deleted_{profile_id}_{int(__import__('time').time())}"
    shutil.move(str(profile_dir), str(backup_dir))
    
    return {
        "success": True,
        "profile_id": profile_id,
        "backup_location": str(backup_dir)
    }
