"""Player tendency tracking service for personalized game recommendations.

Manages player profiles, tracks game launches, and generates recommendations
based on play history stored in tendency files.
"""
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json
import logging
from collections import Counter

from backend.constants.drive_root import get_drive_root

logger = logging.getLogger(__name__)

# Global session storage (in-memory for V1, could move to Redis for multi-instance)
_active_session: Optional[Dict[str, Any]] = None
SESSION_TIMEOUT_MINUTES = 30


def _session_file() -> Path:
    drive_root = get_drive_root(allow_cwd_fallback=True)
    path = drive_root / ".aa" / "state" / "scorekeeper" / "active_session.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_session_from_disk() -> Optional[Dict[str, Any]]:
    try:
        path = _session_file()
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _save_session_to_disk(session: Optional[Dict[str, Any]]) -> None:
    path = _session_file()
    try:
        if not session:
            if path.exists():
                path.unlink(missing_ok=True)
            return
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(session, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        return


class PlayerTendencyService:
    """Service for managing player tendency files and sessions."""
    
    def __init__(self, drive_root: Path):
        self.drive_root = drive_root
        self.profiles_dir = drive_root / ".aa" / "state" / "voice" / "profiles"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
    
    def get_tendency_file(self, player_name: str) -> Path:
        """Get path to player's tendency file."""
        player_dir = self.profiles_dir / player_name
        player_dir.mkdir(parents=True, exist_ok=True)
        return player_dir / "tendencies.json"
    
    def load_tendencies(self, player_name: str) -> Dict[str, Any]:
        """Load player's tendency file or create new one."""
        tendency_file = self.get_tendency_file(player_name)
        
        if not tendency_file.exists():
            # Create new tendency file
            tendencies = {
                "player_name": player_name,
                "created_at": datetime.now().isoformat(),
                "total_sessions": 0,
                "favorite_genres": [],
                "favorite_platforms": [],
                "recent_games": [],
                "play_patterns": {
                    "preferred_time": "unknown",
                    "avg_session_duration": 0,
                    "most_active_day": "unknown"
                }
            }
            self.save_tendencies(player_name, tendencies)
            return tendencies
        
        with open(tendency_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def save_tendencies(self, player_name: str, tendencies: Dict[str, Any]) -> None:
        """Save player's tendency file."""
        tendency_file = self.get_tendency_file(player_name)
        with open(tendency_file, 'w', encoding='utf-8') as f:
            json.dump(tendencies, f, indent=2)
    
    def track_launch(
        self,
        player_name: str,
        game_id: str,
        game_title: str,
        platform: str,
        genre: Optional[str] = None
    ) -> None:
        """Track a game launch for a player."""
        tendencies = self.load_tendencies(player_name)
        
        # Update total sessions
        tendencies["total_sessions"] += 1
        
        # Find or create game entry in recent_games
        game_entry = None
        for game in tendencies["recent_games"]:
            if game["game_id"] == game_id:
                game_entry = game
                break
        
        if game_entry:
            # Update existing entry
            game_entry["last_played"] = datetime.now().isoformat()
            game_entry["play_count"] += 1
        else:
            # Create new entry
            game_entry = {
                "game_id": game_id,
                "title": game_title,
                "platform": platform,
                "genre": genre or "Unknown",
                "last_played": datetime.now().isoformat(),
                "play_count": 1,
                "total_duration_minutes": 0
            }
            tendencies["recent_games"].append(game_entry)
        
        # Sort recent_games by last_played (most recent first)
        tendencies["recent_games"].sort(
            key=lambda x: x["last_played"],
            reverse=True
        )
        
        # Keep only top 50 recent games
        tendencies["recent_games"] = tendencies["recent_games"][:50]
        
        # Update favorite platforms
        platforms = [g["platform"] for g in tendencies["recent_games"]]
        platform_counts = Counter(platforms)
        tendencies["favorite_platforms"] = [
            p for p, _ in platform_counts.most_common(5)
        ]
        
        # Update favorite genres (if we have genre data)
        genres = [g.get("genre", "Unknown") for g in tendencies["recent_games"] if g.get("genre")]
        if genres:
            genre_counts = Counter(genres)
            tendencies["favorite_genres"] = [
                g for g, _ in genre_counts.most_common(5)
            ]
        
        # Update play patterns
        now = datetime.now()
        hour = now.hour
        if 6 <= hour < 12:
            time_of_day = "morning"
        elif 12 <= hour < 17:
            time_of_day = "afternoon"
        elif 17 <= hour < 21:
            time_of_day = "evening"
        else:
            time_of_day = "night"
        
        tendencies["play_patterns"]["preferred_time"] = time_of_day
        tendencies["play_patterns"]["most_active_day"] = now.strftime("%A")
        
        self.save_tendencies(player_name, tendencies)
        logger.info(f"Tracked launch for {player_name}: {game_title} ({platform})")
    
    def track_completion(
        self,
        player_name: str,
        game_id: str,
        duration_seconds: int,
        score: Optional[int] = None
    ) -> None:
        """Track game completion and update duration."""
        tendencies = self.load_tendencies(player_name)
        
        # Find game entry
        for game in tendencies["recent_games"]:
            if game["game_id"] == game_id:
                # Add duration
                game["total_duration_minutes"] += duration_seconds / 60
                
                # Update average session duration
                total_games = len(tendencies["recent_games"])
                total_duration = sum(g["total_duration_minutes"] for g in tendencies["recent_games"])
                tendencies["play_patterns"]["avg_session_duration"] = int(total_duration / total_games) if total_games > 0 else 0
                
                self.save_tendencies(player_name, tendencies)
                logger.info(f"Tracked completion for {player_name}: {game_id} ({duration_seconds}s)")
                break
    
    def get_recommendations(
        self,
        player_name: str,
        all_games: List[Dict[str, Any]],
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Generate personalized game recommendations based on tendencies."""
        tendencies = self.load_tendencies(player_name)
        
        # Get player's favorite platforms and genres
        fav_platforms = set(tendencies.get("favorite_platforms", []))
        fav_genres = set(tendencies.get("favorite_genres", []))
        recent_game_ids = {g["game_id"] for g in tendencies.get("recent_games", [])}
        
        # Score each game
        scored_games = []
        for game in all_games:
            score = 0
            
            # Skip recently played games
            if game.get("id") in recent_game_ids:
                continue
            
            # Boost for favorite platforms
            if game.get("platform") in fav_platforms:
                score += 20
            
            # Boost for favorite genres
            game_genres = game.get("genres", [])
            if isinstance(game_genres, str):
                game_genres = [game_genres]
            for genre in game_genres:
                if genre in fav_genres:
                    score += 15
            
            scored_games.append((score, game))
        
        # Sort by score and return top N
        scored_games.sort(key=lambda x: x[0], reverse=True)
        return [game for _, game in scored_games[:limit]]


# Session management functions
def get_active_player() -> str:
    """Get the currently active player name."""
    global _active_session
    
    if not _active_session:
        _active_session = _load_session_from_disk()
    if not _active_session:
        return "Guest"
    
    # Check if session expired
    expires_at = datetime.fromisoformat(_active_session["expires_at"])
    if datetime.now() > expires_at:
        logger.info(f"Session expired for {_active_session['player_name']}")
        _active_session = None
        _save_session_to_disk(None)
        return "Guest"
    
    return _active_session["player_name"]


def set_active_player(
    player_name: str,
    voice_id: Optional[str] = None,
    player_id: Optional[str] = None,
    players: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Set the active player for the current session."""
    global _active_session
    
    now = datetime.now()
    expires_at = now + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    
    _active_session = {
        "player_name": player_name,
        "player_id": player_id,
        "voice_id": voice_id,
        "players": players or [],
        "started_at": now.isoformat(),
        "last_activity": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "games_launched": 0
    }

    _save_session_to_disk(_active_session)
    
    logger.info(f"Started session for {player_name} (expires at {expires_at})")
    return _active_session


def extend_session() -> None:
    """Extend the current session by resetting the expiry timer."""
    global _active_session
    
    if not _active_session:
        _active_session = _load_session_from_disk()
    if _active_session:
        now = datetime.now()
        expires_at = now + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
        _active_session["last_activity"] = now.isoformat()
        _active_session["expires_at"] = expires_at.isoformat()
        _save_session_to_disk(_active_session)


def end_session() -> None:
    """End the current player session."""
    global _active_session
    
    if _active_session:
        logger.info(f"Ended session for {_active_session['player_name']}")
        _active_session = None
        _save_session_to_disk(None)


def get_active_session() -> Optional[Dict[str, Any]]:
    """Get the current active session."""
    global _active_session
    
    if not _active_session:
        _active_session = _load_session_from_disk()
    if not _active_session:
        return None
    
    # Check if expired
    expires_at = datetime.fromisoformat(_active_session["expires_at"])
    if datetime.now() > expires_at:
        end_session()
        return None
    
    return _active_session
