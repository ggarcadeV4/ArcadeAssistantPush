"""
Arcade Assistant Universal Launch Endpoint

Single entry point for all game launches:
  POST /api/aa/launch {"id": "<LaunchBox GUID>"}

Routes to the correct adapter based on platform.

Architecture:
  Pegasus → aa_launch_pegasus.bat → POST /api/aa/launch → Adapter → Emulator
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Dict, Optional
import logging
import subprocess
import os

from backend.services.launchbox_parser import parser
from backend.services.adapters import teknoparrot_universal_adapter
from backend.routers import marquee as marquee_router
from backend.services.runtime_state import update_runtime_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/aa", tags=["aa-launch"])


class LaunchRequest(BaseModel):
    """Launch request payload."""
    id: Optional[str] = None  # LaunchBox GUID
    title: Optional[str] = None  # Fallback: game title
    platform: Optional[str] = None  # Fallback: platform name


class LaunchResponse(BaseModel):
    """Launch response payload."""
    success: bool
    game_id: Optional[str] = None
    game_title: Optional[str] = None
    platform: Optional[str] = None
    adapter: Optional[str] = None
    emulator: Optional[str] = None
    profile: Optional[str] = None
    command: Optional[str] = None
    message: str = ""
    error_code: Optional[str] = None


# Platform -> Adapter routing
PLATFORM_ADAPTERS = {
    # TeknoParrot Universal handles these
    "teknoparrot arcade": "teknoparrot_universal",
    "teknoparrot": "teknoparrot_universal",
    "taito type x": "teknoparrot_universal",
    "taito type x2": "teknoparrot_universal",
    "taito type x3": "teknoparrot_universal",
    "sega lindbergh": "teknoparrot_universal",
    "sega ringedge": "teknoparrot_universal",
    "sega ringedge 2": "teknoparrot_universal",
    "sega ringwide": "teknoparrot_universal",
    "sega nu": "teknoparrot_universal",
    "namco system es1": "teknoparrot_universal",
    "namco system es3": "teknoparrot_universal",
    "namco system 357": "teknoparrot_universal",
    "examu exboard": "teknoparrot_universal",
    # Add more platform -> adapter mappings as needed
}


def _get_adapter_for_platform(platform: str) -> Optional[str]:
    """Get adapter name for a platform."""
    if not platform:
        return None
    return PLATFORM_ADAPTERS.get(platform.lower().strip())


def _run_command(command: str, cwd: str = None) -> Dict[str, Any]:
    """Execute a launch command."""
    try:
        # Use subprocess to launch
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0,
        )
        # Don't wait - game runs independently
        return {"success": True, "pid": process.pid}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/launch", response_model=LaunchResponse)
async def launch_game(request: Request, payload: LaunchRequest) -> LaunchResponse:
    """
    Universal game launch endpoint.
    
    Accepts:
    - id: LaunchBox GUID (preferred)
    - title + platform: Fallback lookup
    
    Routes to correct adapter based on platform.
    """
    game = None
    game_id = payload.id
    
    # Lookup game by GUID
    if game_id:
        try:
            game = parser.get_game_by_id(game_id)
        except Exception as e:
            logger.warning(f"Game lookup by ID failed: {e}")
    
    # Fallback: lookup by title + platform
    if not game and payload.title:
        try:
            # Try exact title match first using filter_games
            all_games = parser.filter_games(platform=payload.platform) if payload.platform else parser.get_all_games()
            title_lower = payload.title.lower().strip()
            
            # Exact match
            for g in all_games:
                if g.title.lower().strip() == title_lower:
                    game = g
                    game_id = g.id
                    break
            
            # Fuzzy match if no exact match
            if not game:
                from difflib import SequenceMatcher
                best_match = None
                best_ratio = 0.0
                for g in all_games:
                    ratio = SequenceMatcher(None, title_lower, g.title.lower().strip()).ratio()
                    if ratio > best_ratio and ratio >= 0.85:
                        best_ratio = ratio
                        best_match = g
                if best_match:
                    game = best_match
                    game_id = best_match.id
                    logger.info(f"Fuzzy matched '{payload.title}' -> '{game.title}' (ratio: {best_ratio:.2f})")
        except Exception as e:
            logger.warning(f"Game lookup by title failed: {e}")
    
    if not game:
        return LaunchResponse(
            success=False,
            message=f"Game not found: id={payload.id}, title={payload.title}",
            error_code="game_not_found",
        )
    
    # Get game info
    title = getattr(game, "title", "") or ""
    platform = getattr(game, "platform", "") or payload.platform or ""
    
    logger.info(f"Launching game: '{title}' on '{platform}' (id={game_id})")
    
    # Get adapter for platform
    adapter_name = _get_adapter_for_platform(platform)
    
    if not adapter_name:
        return LaunchResponse(
            success=False,
            game_id=game_id,
            game_title=title,
            platform=platform,
            message=f"No adapter configured for platform: {platform}",
            error_code="no_adapter",
        )
    
    # Route to adapter
    result = None
    
    if adapter_name == "teknoparrot_universal":
        # Use TeknoParrot Universal Adapter
        cfg = teknoparrot_universal_adapter.resolve(game, {})
        
        if not cfg.get("success", False):
            return LaunchResponse(
                success=False,
                game_id=game_id,
                game_title=title,
                platform=platform,
                adapter=cfg.get("adapter"),
                message=cfg.get("message", "Adapter resolve failed"),
                error_code=cfg.get("error_code"),
            )
        
        # Execute the command
        command = cfg.get("command", "")
        cwd = cfg.get("cwd")
        
        run_result = _run_command(command, cwd)
        
        if run_result.get("success"):
            result = {
                "success": True,
                "adapter": cfg.get("adapter"),
                "emulator": cfg.get("emulator"),
                "profile": cfg.get("profile"),
                "command": command,
            }
            
            # Track game for lifecycle monitoring (Vision capture on exit)
            try:
                from backend.services.game_lifecycle import track_game_launch
                track_game_launch(
                    game_id=game_id,
                    game_title=title,
                    platform=platform,
                    pid=run_result.get("pid", 0),
                    emulator=cfg.get("emulator"),
                    source="aa_launch",
                    launch_method=cfg.get("adapter") or "aa_launch"
                )
            except Exception as track_err:
                logger.debug(f"Game tracking failed: {track_err}")
        else:
            result = {
                "success": False,
                "adapter": cfg.get("adapter"),
                "message": f"Launch failed: {run_result.get('error')}",
                "error_code": "launch_failed",
            }
    else:
        # Unknown adapter
        return LaunchResponse(
            success=False,
            game_id=game_id,
            game_title=title,
            platform=platform,
            message=f"Unknown adapter: {adapter_name}",
            error_code="unknown_adapter",
        )
    
    # Update marquee state on success
    if result.get("success"):
        try:
            marquee_router.persist_current_game({
                "game_id": game_id,
                "title": title,
                "platform": platform,
                "region": getattr(game, "region", None) or "North America",
            })
        except Exception:
            pass
        
        # Update runtime state
        try:
            panel = request.headers.get("x-panel", "aa")
            update_runtime_state({
                "frontend": panel,
                "mode": "in_game",
                "system_id": platform,
                "game_title": title,
                "game_id": game_id,
            })
        except Exception:
            pass
    
    return LaunchResponse(
        success=result.get("success", False),
        game_id=game_id,
        game_title=title,
        platform=platform,
        adapter=result.get("adapter"),
        emulator=result.get("emulator"),
        profile=result.get("profile"),
        command=result.get("command"),
        message=result.get("message", "Launched successfully" if result.get("success") else "Launch failed"),
        error_code=result.get("error_code"),
    )


@router.get("/adapters")
async def list_adapters() -> Dict[str, Any]:
    """List available adapters and platform mappings."""
    return {
        "platform_mappings": PLATFORM_ADAPTERS,
        "adapters": ["teknoparrot_universal"],
    }


@router.get("/teknoparrot/profiles")
async def list_teknoparrot_profiles() -> Dict[str, Any]:
    """List all TeknoParrot profiles discovered by scanning."""
    profiles = teknoparrot_universal_adapter.get_all_profiles()
    stats = teknoparrot_universal_adapter.get_cache_stats()
    
    return {
        "profiles": profiles,
        "count": len(profiles),
        "cache_stats": stats,
    }


@router.get("/teknoparrot/find/{title}")
async def find_teknoparrot_profile(title: str) -> Dict[str, Any]:
    """Find TeknoParrot profile for a game title (debug endpoint)."""
    profile = teknoparrot_universal_adapter.find_profile(title)
    
    return {
        "title": title,
        "profile": profile,
        "found": profile is not None,
    }

