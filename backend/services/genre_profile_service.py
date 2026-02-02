"""
Genre Profile Service for Controller Chuck.

Provides genre-based controller configuration profiles that automatically apply
the correct button layout when a game launches, based on its genre.

Architecture:
- Loads profiles from config/mappings/genre_profiles.json
- Matches LaunchBox genres to profiles via exact match or alias lookup
- Generates emulator-specific mappings from base arcade panel controls
- Integrates with LED Blinky for per-genre LED color schemes

Usage:
    from backend.services.genre_profile_service import GenreProfileService
    
    service = GenreProfileService()
    profile = service.get_profile_for_genre("Fighting")
    mappings = service.get_emulator_mappings("teknoparrot", profile, base_controls)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Default path to genre profiles configuration
DEFAULT_GENRE_PROFILES_PATH = Path("config") / "mappings" / "genre_profiles.json"


class GenreProfileError(Exception):
    """Raised when genre profile operations fail."""
    pass


class GenreProfileService:
    """
    Service for managing genre-based controller profiles.
    
    Provides:
    - Profile lookup by genre name (with alias support)
    - Game-to-profile resolution via LaunchBox metadata
    - Emulator-specific mapping generation
    - LED color scheme retrieval
    """
    
    def __init__(self, drive_root: Optional[Path] = None):
        """
        Initialize the genre profile service.
        
        Args:
            drive_root: Optional drive root path. If None, uses cwd.
        """
        self._drive_root = drive_root or Path.cwd()
        self._profiles: Dict[str, Any] = {}
        self._genre_aliases: Dict[str, str] = {}
        self._loaded = False
        self._config_path: Optional[Path] = None
    
    def _ensure_loaded(self) -> None:
        """Load profiles if not already loaded."""
        if self._loaded:
            return
        self._load_profiles()
    
    def _load_profiles(self) -> None:
        """Load genre profiles from JSON configuration."""
        config_path = self._drive_root / DEFAULT_GENRE_PROFILES_PATH
        self._config_path = config_path
        
        if not config_path.exists():
            logger.warning(f"Genre profiles not found at {config_path}, using empty profiles")
            self._profiles = {}
            self._genre_aliases = {}
            self._loaded = True
            return
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self._profiles = data.get("profiles", {})
            self._genre_aliases = data.get("genre_aliases", {})
            self._loaded = True
            
            profile_names = list(self._profiles.keys())
            logger.info(f"Loaded {len(self._profiles)} genre profiles: {profile_names}")
            
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load genre profiles: {e}")
            self._profiles = {}
            self._genre_aliases = {}
            self._loaded = True
    
    def reload(self) -> None:
        """Force reload of profiles from disk."""
        self._loaded = False
        self._load_profiles()
    
    def list_profiles(self) -> List[Dict[str, Any]]:
        """
        Get list of all available genre profiles.
        
        Returns:
            List of profile summaries with name, description, icon, and genres.
        """
        self._ensure_loaded()
        
        profiles = []
        for key, profile in self._profiles.items():
            profiles.append({
                "key": key,
                "name": profile.get("name", key.title()),
                "description": profile.get("description", ""),
                "icon": profile.get("icon", "🎮"),
                "applies_to_genres": profile.get("applies_to_genres", []),
                "button_count": len(profile.get("button_layout", {})),
                "has_led_profile": bool(profile.get("led_profile")),
                "supported_emulators": list(profile.get("emulator_mappings", {}).keys()),
            })
        
        return profiles
    
    def get_profile(self, profile_key: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific profile by its key.
        
        Args:
            profile_key: Profile key (e.g., "fighting", "racing")
            
        Returns:
            Profile dict or None if not found.
        """
        self._ensure_loaded()
        return self._profiles.get(profile_key)
    
    def get_profile_for_genre(self, genre: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Find the matching profile for a LaunchBox genre.
        
        Args:
            genre: Genre name from LaunchBox (e.g., "Fighting", "Racing")
            
        Returns:
            Tuple of (profile_key, profile_dict) or (None, None) if no match.
        """
        self._ensure_loaded()
        
        if not genre:
            return None, None
        
        genre_lower = genre.lower().strip()
        
        # 1. Check aliases first (exact match)
        if genre in self._genre_aliases:
            profile_key = self._genre_aliases[genre]
            return profile_key, self._profiles.get(profile_key)
        
        # 2. Check aliases (case-insensitive)
        for alias, profile_key in self._genre_aliases.items():
            if alias.lower() == genre_lower:
                return profile_key, self._profiles.get(profile_key)
        
        # 3. Check each profile's applies_to_genres (exact match)
        for profile_key, profile in self._profiles.items():
            applies_to = profile.get("applies_to_genres", [])
            if genre in applies_to:
                return profile_key, profile
        
        # 4. Check applies_to_genres (case-insensitive)
        for profile_key, profile in self._profiles.items():
            applies_to = profile.get("applies_to_genres", [])
            for g in applies_to:
                if g.lower() == genre_lower:
                    return profile_key, profile
        
        # 5. Partial match (genre contains profile name or vice versa)
        for profile_key, profile in self._profiles.items():
            if profile_key == "default":
                continue  # Skip default for partial matching
            applies_to = profile.get("applies_to_genres", [])
            for g in applies_to:
                if genre_lower in g.lower() or g.lower() in genre_lower:
                    logger.debug(f"Partial genre match: '{genre}' -> {profile_key}")
                    return profile_key, profile
        
        # 6. Fall back to default
        if "default" in self._profiles:
            logger.debug(f"No genre match for '{genre}', using default profile")
            return "default", self._profiles["default"]
        
        return None, None
    
    def get_profile_for_game(
        self,
        game_id: Optional[str] = None,
        game_title: Optional[str] = None,
        genre: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Get the appropriate profile for a game.
        
        Lookup order:
        1. If genre is provided, use genre matching
        2. If game_id is provided, lookup genre from LaunchBox cache
        3. Fall back to default profile
        
        Args:
            game_id: LaunchBox game ID
            game_title: Game title (for logging)
            genre: Genre string (if already known)
            platform: Platform name (for additional context)
            
        Returns:
            Tuple of (profile_key, profile_dict)
        """
        self._ensure_loaded()
        
        # If genre already provided, use it directly
        if genre:
            profile_key, profile = self.get_profile_for_genre(genre)
            if profile:
                logger.info(f"Game '{game_title or game_id}' matched profile '{profile_key}' via genre '{genre}'")
                return profile_key, profile
        
        # Try to lookup genre from LaunchBox if we have a game_id
        if game_id:
            try:
                from backend.services.launchbox_parser import parser
                game = parser.get_game_by_id(game_id)
                if game and hasattr(game, 'genre') and game.genre:
                    profile_key, profile = self.get_profile_for_genre(game.genre)
                    if profile:
                        logger.info(
                            f"Game '{game.title}' matched profile '{profile_key}' "
                            f"via LaunchBox genre '{game.genre}'"
                        )
                        return profile_key, profile
            except Exception as e:
                logger.debug(f"Failed to lookup game genre from LaunchBox: {e}")
        
        # Fall back to default
        if "default" in self._profiles:
            return "default", self._profiles["default"]
        
        return None, None
    
    def get_button_layout(self, profile_key: str) -> Dict[str, Dict[str, Any]]:
        """
        Get the button layout for a profile.
        
        Args:
            profile_key: Profile key (e.g., "fighting")
            
        Returns:
            Dict mapping button IDs to their role/label/color.
        """
        self._ensure_loaded()
        profile = self._profiles.get(profile_key, {})
        return profile.get("button_layout", {})
    
    def get_led_profile(self, profile_key: str) -> Dict[str, Dict[str, Any]]:
        """
        Get the LED color scheme for a profile.
        
        Args:
            profile_key: Profile key
            
        Returns:
            Dict mapping button IDs to LED settings (color, label).
        """
        self._ensure_loaded()
        profile = self._profiles.get(profile_key, {})
        return profile.get("led_profile", {})
    
    def get_emulator_mappings(
        self,
        emulator: str,
        profile_key: str,
        base_controls: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Generate emulator-specific mappings from a genre profile.
        
        Args:
            emulator: Emulator name (e.g., "teknoparrot", "pcsx2", "mame")
            profile_key: Profile key
            base_controls: Base arcade panel controls from controls.json
            
        Returns:
            Dict of emulator-specific mappings, or None if not supported.
        """
        self._ensure_loaded()
        
        profile = self._profiles.get(profile_key)
        if not profile:
            logger.warning(f"Profile '{profile_key}' not found")
            return None
        
        emulator_config = profile.get("emulator_mappings", {}).get(emulator)
        if not emulator_config:
            logger.debug(f"No emulator mappings for '{emulator}' in profile '{profile_key}'")
            return None
        
        # Build the result mapping
        result: Dict[str, Any] = {
            "profile_key": profile_key,
            "profile_name": profile.get("name", profile_key.title()),
            "emulator": emulator,
        }
        
        # If there's a button_map, resolve it against base_controls
        button_map = emulator_config.get("button_map", {})
        if button_map:
            resolved_map = {}
            for emu_input, panel_control in button_map.items():
                # Get the pin/keycode from base_controls
                if panel_control in base_controls:
                    control_info = base_controls[panel_control]
                    resolved_map[emu_input] = {
                        "panel_control": panel_control,
                        "pin": control_info.get("pin"),
                        "keycode": control_info.get("keycode"),
                        "type": control_info.get("type"),
                    }
                else:
                    resolved_map[emu_input] = {
                        "panel_control": panel_control,
                        "pin": None,
                        "keycode": None,
                        "type": None,
                        "warning": f"Control '{panel_control}' not found in base controls",
                    }
            result["button_map"] = resolved_map
        
        # Include other emulator-specific config
        for key in ["map_template", "ctrlr_file", "profile", "core_override", "category"]:
            if key in emulator_config:
                result[key] = emulator_config[key]
        
        return result
    
    def get_all_matching_genres(self) -> Dict[str, List[str]]:
        """
        Get a mapping of profile keys to all genres that match them.
        
        Useful for debugging and UI display.
        
        Returns:
            Dict mapping profile_key -> list of matching genre names.
        """
        self._ensure_loaded()
        
        result: Dict[str, List[str]] = {}
        
        for profile_key, profile in self._profiles.items():
            genres = list(profile.get("applies_to_genres", []))
            
            # Add aliases
            for alias, target_key in self._genre_aliases.items():
                if target_key == profile_key:
                    genres.append(f"{alias} (alias)")
            
            result[profile_key] = genres
        
        return result
    
    def save_profiles(self, profiles_data: Dict[str, Any]) -> bool:
        """
        Save updates to the genre profiles configuration.
        
        Args:
            profiles_data: Complete profiles configuration to save.
            
        Returns:
            True if saved successfully.
        """
        if not self._config_path:
            self._ensure_loaded()
        
        if not self._config_path:
            logger.error("Cannot save profiles: config path not set")
            return False
        
        try:
            # Ensure parent directory exists
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(profiles_data, f, indent=2)
            
            # Reload to update cache
            self.reload()
            logger.info(f"Saved genre profiles to {self._config_path}")
            return True
            
        except OSError as e:
            logger.error(f"Failed to save genre profiles: {e}")
            return False


# Singleton instance
_service_instance: Optional[GenreProfileService] = None


def get_genre_profile_service(drive_root: Optional[Path] = None) -> GenreProfileService:
    """
    Get the singleton GenreProfileService instance.
    
    Args:
        drive_root: Optional drive root to initialize with.
        
    Returns:
        GenreProfileService singleton.
    """
    global _service_instance
    
    if _service_instance is None:
        _service_instance = GenreProfileService(drive_root)
    
    return _service_instance
