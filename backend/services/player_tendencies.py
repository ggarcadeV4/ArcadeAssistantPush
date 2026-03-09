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


def _get_supabase_active_player(device_id: str = "CAB-0001") -> Optional[Dict[str, Any]]:
    """
    Check Supabase aa_lora_sessions for active_player field.
    Part of Phase 5 Split-Brain Fix: Supabase is source of truth.
    
    Args:
        device_id: Device identifier for session lookup
        
    Returns:
        active_player dict or None if not found/error
    """
    try:
        import os
        import httpx
        
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
        
        if not supabase_url or not supabase_key:
            return None
        
        # Query aa_lora_sessions for this device
        response = httpx.get(
            f"{supabase_url}/rest/v1/aa_lora_sessions",
            params={"device_id": f"eq.{device_id}", "select": "active_player"},
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}"
            },
            timeout=2.0
        )
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0 and data[0].get("active_player"):
                logger.info(f"Got active_player from Supabase: {data[0]['active_player']}")
                return data[0]["active_player"]
        
        return None
        
    except Exception as e:
        logger.debug(f"Supabase active_player check failed: {e}")
        return None

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



def _slugify_player_id(value: Optional[str], fallback: str) -> str:
    """Create a stable, URL-safe-ish player identifier."""
    raw = str(value or "").strip().lower()
    if not raw:
        raw = fallback
    cleaned = []
    for ch in raw:
        if ch.isalnum():
            cleaned.append(ch)
        elif ch in {"_", "-", " "}:
            cleaned.append("_")
    slug = "".join(cleaned).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return (slug or fallback)[:64]


def _normalize_players(players: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Normalize session roster data into canonical P1-P4 records."""
    if not isinstance(players, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for index, raw in enumerate(players[:4]):
        if not isinstance(raw, dict):
            continue

        fallback_position = index + 1
        try:
            position = int(raw.get("position") or raw.get("slot") or fallback_position)
        except Exception:
            position = fallback_position
        if position < 1 or position > 4:
            position = fallback_position

        user = str(raw.get("user") or raw.get("name") or "None").strip() or "None"
        occupied = str(raw.get("occupied", "")).strip().lower() == "true"
        if "occupied" not in raw:
            occupied = user.lower() != "none"

        name = str(raw.get("name") or (user if occupied else f"Open Seat {position}")).strip()
        if not name:
            name = f"Open Seat {position}"

        candidate_id = raw.get("id") or raw.get("player_id")
        fallback_id = f"guest_p{position}" if not occupied else f"player_{position}"
        player_id = _slugify_player_id(str(candidate_id or (user if occupied else fallback_id)), fallback_id)

        controller = str(raw.get("controller") or f"Joystick {position}").strip() or f"Joystick {position}"

        normalized.append({
            "id": player_id,
            "name": name,
            "user": user,
            "controller": controller,
            "position": position,
            "seat": f"P{position}",
            "occupied": occupied,
        })

    normalized.sort(key=lambda item: item.get("position", 99))
    return normalized
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
    
    # Phase 5 Split-Brain Fix: Check Supabase first
    supabase_player = _get_supabase_active_player()
    if supabase_player and supabase_player.get("player_name"):
        return supabase_player["player_name"]
    
    # Fallback to local session
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
    normalized_players = _normalize_players(players)
    resolved_player_id = player_id or _slugify_player_id(player_name, "guest")

    _active_session = {
        "player_name": player_name,
        "player_id": resolved_player_id,
        "voice_id": voice_id,
        "players": normalized_players,
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
    
    # Phase 5 Split-Brain Fix: Check Supabase first
    supabase_player = _get_supabase_active_player()
    if supabase_player and supabase_player.get("player_name"):
        local_session = _active_session or _load_session_from_disk() or {}
        local_players = _normalize_players(local_session.get("players"))
        now = datetime.now()
        return {
            "player_name": supabase_player["player_name"],
            "player_id": supabase_player.get("player_id"),
            "voice_id": local_session.get("voice_id"),
            "players": local_players,
            "source": "supabase",
            "started_at": local_session.get("started_at") or now.isoformat(),
            "expires_at": (now + timedelta(minutes=SESSION_TIMEOUT_MINUTES)).isoformat()
        }
    # Fallback to local session
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
