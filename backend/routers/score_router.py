"""
Score Router
API endpoints for score reset and management.

@router: /api/scores
@role: Score reset, backup listing, restore
@owner: Arcade Assistant / ScoreKeeper Sam
"""

from fastapi import APIRouter, HTTPException, Path, Query, Request
from typing import Optional

from backend.services.score_service import score_service
from backend.services.score_service import get_ai_state_file, get_live_score_file
from backend.services.policies import require_scope

router = APIRouter(prefix="/api/scores", tags=["Scores"])


@router.delete("/reset/{rom_name}")
async def reset_game_score(
    request: Request,
    dry_run: bool = Query(default=False, description="Preview score reset without deleting files"),
    rom_name: str = Path(..., title="ROM Name", description="The MAME ROM name (e.g., galaga)")
):
    """
    **Factory Reset a High Score**
    
    - Archives current `.hi` file to `A:/.aa/backups/scores/`
    - Deletes active `.hi` file
    - Resets AI knowledge of the score
    
    ⚠️ **Requires MAME restart to take effect if game is running.**
    """
    try:
        require_scope(request, "state")
        return score_service.reset_score(rom_name, request=request, dry_run=dry_run)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset score: {str(e)}")


@router.delete("/reset-all")
async def reset_all_scores():
    """
    **Factory Reset ALL High Scores**
    
    - Archives all `.hi` files to backups
    - Deletes all active `.hi` files
    - Clears entire AI state
    
    ⚠️ **This is irreversible (but backups are kept).**
    """
    try:
        return score_service.reset_all_scores()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset all scores: {str(e)}")


@router.get("/backups")
async def list_backups(
    game: Optional[str] = Query(None, description="Filter by game ROM name")
):
    """
    **List Available Score Backups**
    
    Returns a list of all backed-up score files with timestamps.
    Optionally filter by game name.
    """
    try:
        backups = score_service.get_backups(game)
        return {
            "count": len(backups),
            "backups": backups
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list backups: {str(e)}")


@router.post("/restore")
async def restore_backup(
    backup_path: str = Query(..., description="Full path to the backup .hi file")
):
    """
    **Restore a Score Backup**
    
    Copies a backup file back to the active hiscore directory.
    
    ⚠️ **Requires MAME restart to take effect.**
    """
    try:
        return score_service.restore_backup(backup_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restore backup: {str(e)}")


@router.post("/sync")
async def sync_hiscores():
    """
    **Sync MAME High Scores from .hi Files**
    
    Uses hi2txt.exe to parse all .hi files from the hiscore directories
    and updates mame_scores.json with the results.
    
    This is the reliable approach - reads from files that MAME already saves.
    """
    try:
        from backend.services.hiscore_watcher import get_watcher
        watcher = get_watcher()
        result = watcher.sync_all()
        
        total_games = len(result)
        total_scores = sum(len(scores) for scores in result.values())
        
        # Get top score per game for display
        top_scores = []
        for rom, entries in result.items():
            if entries:
                top = max(entries, key=lambda x: x.get("score", 0))
                top_scores.append({
                    "game": rom,
                    "score": top.get("score", 0),
                    "player": top.get("name", "???")
                })
        
        return {
            "status": "synced",
            "total_games": total_games,
            "total_scores": total_scores,
            "games": list(result.keys()),
            "top_scores": top_scores
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.get("/watcher/status")
async def get_watcher_status():
    """
    **Get Hiscore Watcher Status**
    
    Returns whether the background watcher is running and what it's tracking.
    """
    try:
        from backend.services.hiscore_watcher import get_watcher
        watcher = get_watcher()
        return watcher.get_status()
    except Exception as e:
        return {
            "running": False,
            "error": str(e)
        }


@router.get("/mame")
async def get_mame_scores():
    """
    **Get MAME High Scores**
    
    Returns scores from mame_scores.json (populated by hi2txt sync).
    This is what ScoreKeeper Sam uses for AI awareness.
    """
    import json
    
    scores_file = get_ai_state_file()
    
    if not scores_file.exists():
        return {
            "games": {},
            "total_games": 0,
            "total_scores": 0,
            "message": "No scores yet. Run /api/scores/sync first."
        }
    
    try:
        with open(scores_file, 'r') as f:
            data = json.load(f)
        
        # Calculate stats
        total_games = len(data)
        total_scores = sum(len(scores) for scores in data.values())
        
        # Get top score per game
        leaderboard = []
        for game_rom, scores in data.items():
            if scores:
                top_score = max(scores, key=lambda x: x.get("score", 0))
                top_player = top_score.get("name", "???")
                leaderboard.append({
                    "game": game_rom,
                    "game_name": top_score.get("game_name", game_rom),
                    "top_score": top_score.get("score", 0),
                    "top_player": top_player,
                    "last_synced": top_score.get("timestamp"),
                    "score_count": len(scores)
                })
        
        # Sort by top score descending
        leaderboard.sort(key=lambda x: x["top_score"], reverse=True)
        
        return {
            "games": data,
            "leaderboard": leaderboard,
            "total_games": total_games,
            "total_scores": total_scores
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read scores: {str(e)}")


@router.get("/mame/{rom_name}")
async def get_game_scores(
    rom_name: str = Path(..., title="ROM Name", description="The MAME ROM name (e.g., galaga)")
):
    """
    **Get Scores for a Specific Game**
    
    Parses the .hi file directly using hi2txt for real-time data.
    """
    try:
        from backend.services.hi2txt_parser import get_parser
        parser = get_parser()
        result = parser.get_game_scores(rom_name)
        
        if not result:
            raise HTTPException(status_code=404, detail=f"No scores found for {rom_name}")
        
        return {
            "game": rom_name,
            "parsed_at": result.parsed_at,
            "scores": [
                {
                    "rank": e.rank,
                    "score": e.score,
                    "name": e.name
                }
                for e in result.entries
            ],
            "error": result.parse_error
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get scores: {str(e)}")


@router.get("/live")
async def get_live_score():
    """
    **Get Live Score from MAME Lua Plugin**
    
    Returns the current live score being broadcast by the arcade_assistant_scores
    Lua plugin during gameplay. This is real-time RAM reading.
    
    Separate from /mame which reads from .hi files (after game ends).
    """
    import json
    
    live_score_file = get_live_score_file()
    
    if not live_score_file.exists():
        return {
            "status": "no_live_data",
            "score": None,
            "message": "No live score - game may not be running or plugin not active"
        }
    
    try:
        with open(live_score_file, 'r') as f:
            data = json.load(f)
        
        # Check timestamp freshness (within last 10 seconds = considered live)
        from datetime import datetime, timezone
        if "timestamp" in data:
            try:
                ts = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - ts).total_seconds()
                
                return {
                    "status": "live" if age < 10 else "stale",
                    "age_seconds": round(age, 1),
                    "rom": data.get("rom"),
                    "score": data.get("score"),
                    "player": data.get("player", 1),
                    "timestamp": data.get("timestamp"),
                    "source": data.get("source", "unknown")
                }
            except:
                pass
        
        return {
            "status": "live",
            "rom": data.get("rom"),
            "score": data.get("score"),
            "player": data.get("player", 1),
            "timestamp": data.get("timestamp")
        }
    except Exception as e:
        return {
            "status": "error",
            "score": None,
            "message": str(e)
        }

