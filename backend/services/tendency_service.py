"""
Unified Tendency Service for Arcade Assistant
Manages the per-profile tendency file that ALL panels read/write.

The tendency file is the "long-term memory" of each user - their preferences,
play history, controller settings, and panel-specific data. This service
implements the TENDENCIES_CONTRACT.md specification.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import Counter

logger = logging.getLogger(__name__)

# Default tendency file structure (v2 - human-readable)
DEFAULT_TENDENCY_SCHEMA = {
    "profile_id": "",
    
    # Core identity - WHO is this person?
    "core": {
        "display_name": "",
        "initials": "",
        "age_group": "adult",  # kid, teen, adult, senior
        "preferred_language": "en",
        "avatar": None
    },
    
    # Gaming preferences - WHAT do they like?
    "preferences": {
        "favorite_genres": [],         # ["Fighting", "Platformer", "Shmup"]
        "favorite_platforms": [],       # ["Arcade", "SNES", "PlayStation"]
        "favorite_eras": [],           # ["80s", "90s", "2000s"]
        "favorite_games": [],          # Top 10 games by play count
        "disliked_genres": [],         # Genres to avoid in recommendations
        "difficulty_preference": "medium",  # easy, medium, hard, expert
        "session_length_preference": "medium",  # quick (15m), medium (30m), long (60m+)
        "multiplayer_preference": "both"  # solo, coop, versus, both
    },
    
    # Play statistics - HOW do they play?
    "stats": {
        "total_sessions": 0,
        "total_play_time_minutes": 0,
        "games_played_count": 0,
        "avg_session_minutes": 0,
        "longest_session_minutes": 0,
        "first_session": None,
        "last_session": None,
        "peak_play_time": "evening",    # morning, afternoon, evening, night
        "most_active_day": "saturday"   # day of week
    },
    
    # Recent activity - WHAT have they done lately?
    "recent": {
        "last_10_games": [],  # [{game_id, title, platform, played_at, duration_mins}]
        "last_genre": None,
        "last_platform": None,
        "current_streak_days": 0
    },
    
    # Panel-specific namespaces - each panel owns its section
    "panels": {
        "vicky_voice": {
            "voice_id": None,           # ElevenLabs voice clone ID
            "wake_word_enabled": True,
            "tts_speed": 1.0,
            "custom_vocabulary": [],    # Custom words for STT
            "greeting_style": "friendly"  # friendly, formal, playful
        },
        
        "controller_chuck": {
            "preferred_layout": "default",
            "owned_controllers": [],    # [{type, name, player_slot}]
            "button_remap_profile": None,
            "sensitivity": 1.0,
            "invert_y_axis": False
        },
        
        "console_wizard": {
            "auto_config_enabled": True,
            "preferred_emulators": {},  # {platform: emulator_name}
            "shader_preference": "crt"  # none, crt, lcd, custom
        },
        
        "launchbox_lora": {
            "show_favorites_first": True,
            "hide_played_recently": False,
            "recommendation_style": "adventurous"  # safe, balanced, adventurous
        },
        
        "scorekeeper_sam": {
            "display_on_leaderboard": True,
            "initials_for_hiscore": "",
            "tournament_wins": 0,
            "elo_rating": 1200
        },
        
        "gunner": {
            "handedness": "right",      # left, right
            "gun_sensitivity": 1.0,
            "calibration_profile": None,
            "preferred_reticle": "crosshair"
        },
        
        "led_blinky": {
            "brightness": 0.8,
            "theme": "default",
            "reactive_mode": True
        },
        
        "dewey": {
            "trivia_difficulty": "medium",
            "trivia_categories": ["arcade", "console", "mixed"],
            "trivia_best_streak": 0
        },
        
        "doc": {
            "explanation_style": "concise",  # concise, detailed, eli5
            "show_technical_details": False
        }
    },
    
    # AI context - summary for LLM prompts
    "ai_summary": "",
    
    # Metadata
    "meta": {
        "version": 2,
        "created_at": None,
        "last_modified": None,
        "schema_version": "2.0"
    }
}


class TendencyService:
    """
    Unified service for reading/writing tendency files.
    
    All panels should use this service to access user preferences.
    Each panel can only write to its own namespace under 'panels'.
    """
    
    def __init__(self, profiles_root: Optional[Path] = None):
        """
        Initialize the tendency service.
        
        Args:
            profiles_root: Root directory for profiles. Defaults to A:/Arcade Assistant/profiles
        """
        if profiles_root:
            self.profiles_root = Path(profiles_root)
        else:
            drive_root = os.getenv("AA_DRIVE_ROOT", "A:")
            self.profiles_root = Path(drive_root) / "Arcade Assistant" / "profiles"
        
        self.profiles_root.mkdir(parents=True, exist_ok=True)
    
    def _get_tendency_path(self, profile_id: str) -> Path:
        """Get the path to a profile's tendency file."""
        # Sanitize profile_id
        safe_id = "".join(c for c in profile_id if c.isalnum() or c in "-_").lower()
        if not safe_id:
            safe_id = "guest"
        
        profile_dir = self.profiles_root / safe_id
        profile_dir.mkdir(parents=True, exist_ok=True)
        return profile_dir / "tendencies.json"
    
    def load(self, profile_id: str) -> Dict[str, Any]:
        """
        Load a profile's tendency file, creating if needed.
        
        Args:
            profile_id: Unique profile identifier
            
        Returns:
            The tendency data dictionary
        """
        path = self._get_tendency_path(profile_id)
        
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # Migrate if needed
                data = self._migrate_schema(data, profile_id)
                return data
                
            except json.JSONDecodeError:
                logger.warning(f"Corrupt tendency file for {profile_id}, creating new")
        
        # Create new tendency file
        data = self._create_default(profile_id)
        self.save(profile_id, data)
        return data
    
    def save(self, profile_id: str, data: Dict[str, Any]) -> None:
        """
        Save a profile's tendency file.
        
        Args:
            profile_id: Unique profile identifier
            data: The tendency data to save
        """
        path = self._get_tendency_path(profile_id)
        
        # Update metadata
        data["meta"]["last_modified"] = datetime.now(timezone.utc).isoformat()
        
        # Regenerate AI summary
        data["ai_summary"] = self._generate_ai_summary(data)
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.debug(f"Saved tendency file for {profile_id}")
    
    def _create_default(self, profile_id: str) -> Dict[str, Any]:
        """Create a new tendency file with defaults."""
        import copy
        data = copy.deepcopy(DEFAULT_TENDENCY_SCHEMA)
        
        data["profile_id"] = profile_id
        data["core"]["display_name"] = profile_id.title()
        data["core"]["initials"] = profile_id[:3].upper()
        data["meta"]["created_at"] = datetime.now(timezone.utc).isoformat()
        data["meta"]["last_modified"] = datetime.now(timezone.utc).isoformat()
        
        return data
    
    def _migrate_schema(self, data: Dict[str, Any], profile_id: str) -> Dict[str, Any]:
        """Migrate old schema to new version if needed."""
        version = data.get("meta", {}).get("version", 1)
        
        if version < 2:
            # Migrate v1 flat structure to v2 namespaced structure
            logger.info(f"Migrating tendency file for {profile_id} from v{version} to v2")
            
            new_data = self._create_default(profile_id)
            
            # Migrate flat fields to new structure
            if "favorite_game" in data:
                new_data["preferences"]["favorite_games"] = [data["favorite_game"]]
            if "favorite_genre" in data:
                new_data["preferences"]["favorite_genres"] = [data["favorite_genre"]]
            if "total_sessions" in data:
                new_data["stats"]["total_sessions"] = data["total_sessions"]
            if "peak_play_time" in data:
                new_data["stats"]["peak_play_time"] = data["peak_play_time"]
            if "most_used_platform" in data:
                new_data["preferences"]["favorite_platforms"] = [data["most_used_platform"]]
            if "top_3_games" in data:
                new_data["preferences"]["favorite_games"] = data["top_3_games"]
            if "top_10_games" in data:
                new_data["preferences"]["favorite_games"] = data["top_10_games"][:10]
            if "preferred_difficulty" in data:
                new_data["preferences"]["difficulty_preference"] = data["preferred_difficulty"].lower()
            if "average_session_duration" in data:
                # Parse "45 minutes" -> 45
                try:
                    mins = int(data["average_session_duration"].split()[0])
                    new_data["stats"]["avg_session_minutes"] = mins
                except:
                    pass
            
            # Preserve panel-specific data if it exists
            for panel in ["vicky_voice", "controller_chuck", "gunner", "dewey", "scorekeeper_sam"]:
                if panel in data:
                    new_data["panels"][panel].update(data[panel])
            
            # Preserve any custom fields under 'legacy'
            legacy_keys = set(data.keys()) - set(DEFAULT_TENDENCY_SCHEMA.keys()) - {"favorite_game", "favorite_genre", "total_sessions", "peak_play_time", "most_used_platform", "top_3_games", "top_10_games", "preferred_difficulty", "average_session_duration"}
            if legacy_keys:
                new_data["legacy"] = {k: data[k] for k in legacy_keys if k in data}
            
            return new_data
        
        return data
    
    def _generate_ai_summary(self, data: Dict[str, Any]) -> str:
        """
        Generate a concise summary for AI prompts.
        
        This is what panels can inject into their LLM context to understand
        the user without sending the entire tendency file.
        """
        parts = []
        
        name = data.get("core", {}).get("display_name", "Guest")
        parts.append(f"{name}")
        
        # Age/type
        age = data.get("core", {}).get("age_group", "adult")
        if age == "kid":
            parts.append("(kid-friendly mode)")
        
        # Favorites
        genres = data.get("preferences", {}).get("favorite_genres", [])
        if genres:
            parts.append(f"loves {', '.join(genres[:3])}")
        
        platforms = data.get("preferences", {}).get("favorite_platforms", [])
        if platforms:
            parts.append(f"plays {', '.join(platforms[:2])}")
        
        games = data.get("preferences", {}).get("favorite_games", [])
        if games:
            parts.append(f"favorites: {', '.join(games[:3])}")
        
        # Experience level
        sessions = data.get("stats", {}).get("total_sessions", 0)
        if sessions > 100:
            parts.append("veteran player")
        elif sessions > 20:
            parts.append("regular player")
        elif sessions > 0:
            parts.append("newer player")
        
        # Difficulty
        diff = data.get("preferences", {}).get("difficulty_preference", "medium")
        if diff in ("hard", "expert"):
            parts.append("prefers challenge")
        elif diff == "easy":
            parts.append("prefers casual")
        
        return "; ".join(parts)
    
    # =========================================================================
    # Convenience methods for common operations
    # =========================================================================
    
    def get_ai_context(self, profile_id: str) -> str:
        """Get the AI summary for injection into prompts."""
        data = self.load(profile_id)
        return data.get("ai_summary", f"User: {profile_id}")
    
    def get_panel_data(self, profile_id: str, panel: str) -> Dict[str, Any]:
        """Get a specific panel's namespace data."""
        data = self.load(profile_id)
        return data.get("panels", {}).get(panel, {})
    
    def update_panel_data(self, profile_id: str, panel: str, updates: Dict[str, Any]) -> None:
        """Update a specific panel's namespace data."""
        data = self.load(profile_id)
        
        if "panels" not in data:
            data["panels"] = {}
        if panel not in data["panels"]:
            data["panels"][panel] = {}
        
        data["panels"][panel].update(updates)
        self.save(profile_id, data)
    
    def track_game_launch(
        self,
        profile_id: str,
        game_id: str,
        title: str,
        platform: str,
        genre: Optional[str] = None
    ) -> None:
        """
        Track a game launch and update statistics.
        
        Called by LaunchBox/LoRa when a game is launched.
        """
        data = self.load(profile_id)
        now = datetime.now(timezone.utc)
        
        # Update stats
        data["stats"]["total_sessions"] = data["stats"].get("total_sessions", 0) + 1
        data["stats"]["games_played_count"] = data["stats"].get("games_played_count", 0) + 1
        data["stats"]["last_session"] = now.isoformat()
        
        if not data["stats"].get("first_session"):
            data["stats"]["first_session"] = now.isoformat()
        
        # Update play time patterns
        hour = now.hour
        if 6 <= hour < 12:
            data["stats"]["peak_play_time"] = "morning"
        elif 12 <= hour < 17:
            data["stats"]["peak_play_time"] = "afternoon"
        elif 17 <= hour < 21:
            data["stats"]["peak_play_time"] = "evening"
        else:
            data["stats"]["peak_play_time"] = "night"
        
        data["stats"]["most_active_day"] = now.strftime("%A").lower()
        
        # Update recent games
        recent = data.get("recent", {}).get("last_10_games", [])
        recent.insert(0, {
            "game_id": game_id,
            "title": title,
            "platform": platform,
            "genre": genre,
            "played_at": now.isoformat(),
            "duration_mins": 0  # Updated on completion
        })
        data["recent"]["last_10_games"] = recent[:10]
        data["recent"]["last_genre"] = genre
        data["recent"]["last_platform"] = platform
        
        # Update favorite platforms/genres based on frequency
        all_platforms = [g["platform"] for g in recent if g.get("platform")]
        if all_platforms:
            platform_counts = Counter(all_platforms)
            data["preferences"]["favorite_platforms"] = [p for p, _ in platform_counts.most_common(5)]
        
        if genre:
            all_genres = [g["genre"] for g in recent if g.get("genre")]
            if all_genres:
                genre_counts = Counter(all_genres)
                data["preferences"]["favorite_genres"] = [g for g, _ in genre_counts.most_common(5)]
        
        self.save(profile_id, data)
        logger.info(f"Tracked game launch for {profile_id}: {title}")
    
    def track_session_end(
        self,
        profile_id: str,
        game_id: str,
        duration_minutes: int,
        score: Optional[int] = None
    ) -> None:
        """
        Track session completion and update duration.
        
        Called when a game session ends.
        """
        data = self.load(profile_id)
        
        # Update total play time
        data["stats"]["total_play_time_minutes"] = data["stats"].get("total_play_time_minutes", 0) + duration_minutes
        
        # Update average session
        sessions = data["stats"].get("total_sessions", 1)
        total_time = data["stats"].get("total_play_time_minutes", duration_minutes)
        data["stats"]["avg_session_minutes"] = int(total_time / sessions)
        
        # Update longest session
        if duration_minutes > data["stats"].get("longest_session_minutes", 0):
            data["stats"]["longest_session_minutes"] = duration_minutes
        
        # Update duration in recent games
        for game in data.get("recent", {}).get("last_10_games", []):
            if game.get("game_id") == game_id and game.get("duration_mins", 0) == 0:
                game["duration_mins"] = duration_minutes
                break
        
        self.save(profile_id, data)
        logger.info(f"Tracked session end for {profile_id}: {game_id} ({duration_minutes}m)")
    
    def list_profiles(self) -> List[str]:
        """List all profile IDs."""
        profiles = []
        for item in self.profiles_root.iterdir():
            if item.is_dir() and (item / "tendencies.json").exists():
                profiles.append(item.name)
        return sorted(profiles)


# Global service instance
_service: Optional[TendencyService] = None


def get_tendency_service() -> TendencyService:
    """Get the global tendency service instance."""
    global _service
    if _service is None:
        _service = TendencyService()
    return _service
