"""Gunner configuration service for calibration profile management.

Provides persistent storage for calibration profiles with:
- Supabase cloud storage with local fallback
- Per-user, per-game profile isolation
- Tendency-aware sensitivity offsets
- LRU cache for fast profile retrieval
- Graceful offline mode

Profile Schema:
{
    "user_id": "dad",
    "game": "area51",
    "points": [{"x": 0.1, "y": 0.1}, ...],  # 9 points
    "sensitivity": 85,
    "deadzone": 2,
    "offset_x": 3,
    "offset_y": -1,
    "created_at": "2025-10-28T12:00:00Z"
}
"""

import logging
import os
import json
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
from functools import lru_cache

logger = logging.getLogger(__name__)

# Try importing Supabase, gracefully fallback if unavailable
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning("Supabase client not available - using local fallback only")


# ============================================================================
# Configuration Constants
# ============================================================================

DEFAULT_PROFILE = {
    "points": [
        {"x": 0.1, "y": 0.1},  # Top-left
        {"x": 0.5, "y": 0.1},  # Top-center
        {"x": 0.9, "y": 0.1},  # Top-right
        {"x": 0.1, "y": 0.5},  # Mid-left
        {"x": 0.5, "y": 0.5},  # Center
        {"x": 0.9, "y": 0.5},  # Mid-right
        {"x": 0.1, "y": 0.9},  # Bottom-left
        {"x": 0.5, "y": 0.9},  # Bottom-center
        {"x": 0.9, "y": 0.9},  # Bottom-right
    ],
    "sensitivity": 85,
    "deadzone": 2,
    "offset_x": 0,
    "offset_y": 0,
}


# ============================================================================
# Gunner Config Service
# ============================================================================

class GunnerConfigService:
    """Calibration profile management with cloud sync and local fallback.

    Features:
    - Supabase gun_profiles table integration
    - Local JSON file fallback when offline
    - LRU cache for fast retrieval
    - Tendency-aware defaults (planned)
    """

    def __init__(self, local_storage_path: Optional[Path] = None):
        """Initialize config service.

        Args:
            local_storage_path: Path for local JSON storage (default: ./state/gunner/)
        """
        # Supabase client (if available)
        self.supabase: Optional[Client] = None
        self.supabase_enabled = False

        if SUPABASE_AVAILABLE:
            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = os.getenv('SUPABASE_ANON_KEY')

            if supabase_url and supabase_key:
                try:
                    self.supabase = create_client(supabase_url, supabase_key)
                    self.supabase_enabled = True
                    logger.info("Supabase client initialized for gunner profiles")
                except Exception as e:
                    logger.error(f"Supabase init failed: {e}", exc_info=True)

        # Local storage setup
        if local_storage_path is None:
            aa_root = os.getenv('AA_DRIVE_ROOT', '.')
            local_storage_path = Path(aa_root) / 'state' / 'gunner'

        self.local_storage_path = local_storage_path
        self.local_storage_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Local gunner storage: {self.local_storage_path}")

    def save_profile(
        self,
        user_id: str,
        game: str,
        points: List[Dict],
        sensitivity: int = 85,
        deadzone: int = 2,
        offset_x: int = 0,
        offset_y: int = 0
    ) -> bool:
        """Save calibration profile to cloud and local storage.

        Args:
            user_id: User identifier (e.g., "dad", "mom")
            game: Game identifier (e.g., "area51", "timeCrisis")
            points: List of 9 calibration points with x, y
            sensitivity: Sensitivity percentage (0-100)
            deadzone: Deadzone in pixels
            offset_x: X offset in pixels
            offset_y: Y offset in pixels

        Returns:
            True if save successful (either cloud or local)
        """
        # Validate points
        if len(points) != 9:
            logger.error(f"Invalid points count: {len(points)} (expected 9)")
            return False

        for point in points:
            if not (0.0 <= point.get('x', -1) <= 1.0 and 0.0 <= point.get('y', -1) <= 1.0):
                logger.error(f"Invalid point coordinates: {point}")
                return False

        # Build profile data
        profile = {
            "user_id": user_id,
            "game": game,
            "points": points,
            "sensitivity": sensitivity,
            "deadzone": deadzone,
            "offset_x": offset_x,
            "offset_y": offset_y,
            "created_at": datetime.utcnow().isoformat(),
        }

        # Try saving to Supabase first
        supabase_success = False
        if self.supabase_enabled:
            try:
                # Upsert to gun_profiles table (create or update)
                result = self.supabase.table('gun_profiles').upsert(profile).execute()
                supabase_success = True
                logger.info(f"Profile saved to Supabase: {user_id}/{game}")
            except Exception as e:
                logger.error(f"Supabase save failed: {e}", exc_info=True)

        # Always save locally as backup
        local_success = self._save_local(user_id, game, profile)

        return supabase_success or local_success

    def load_profile(self, user_id: str, game: str) -> List[Dict]:
        """Load calibration profile from cloud or local storage.

        Attempts Supabase first, falls back to local, then default profile.

        Args:
            user_id: User identifier
            game: Game identifier

        Returns:
            List of 9 calibration points (always returns valid data)
        """
        # Try Supabase first
        if self.supabase_enabled:
            try:
                result = self.supabase.table('gun_profiles').select('*').eq('user_id', user_id).eq('game', game).execute()

                if result.data and len(result.data) > 0:
                    profile = result.data[0]
                    logger.info(f"Profile loaded from Supabase: {user_id}/{game}")
                    return profile.get('points', DEFAULT_PROFILE['points'])
            except Exception as e:
                logger.error(f"Supabase load failed: {e}", exc_info=True)

        # Try local storage
        local_profile = self._load_local(user_id, game)
        if local_profile:
            logger.info(f"Profile loaded from local storage: {user_id}/{game}")
            return local_profile.get('points', DEFAULT_PROFILE['points'])

        # Return default profile
        logger.info(f"Using default profile for {user_id}/{game}")
        return DEFAULT_PROFILE['points']

    def list_profiles(self, user_id: str) -> List[Dict]:
        """List all calibration profiles for a user.

        Args:
            user_id: User identifier

        Returns:
            List of profile metadata (user_id, game, created_at)
        """
        profiles = []

        # Get from Supabase
        if self.supabase_enabled:
            try:
                result = self.supabase.table('gun_profiles').select('user_id, game, created_at').eq('user_id', user_id).execute()

                if result.data:
                    profiles.extend(result.data)
                    logger.info(f"Found {len(result.data)} profiles in Supabase for {user_id}")
            except Exception as e:
                logger.error(f"Supabase list failed: {e}", exc_info=True)

        # Get from local storage
        local_profiles = self._list_local(user_id)
        profiles.extend(local_profiles)

        # Deduplicate by game
        seen_games = set()
        unique_profiles = []
        for profile in profiles:
            game = profile.get('game')
            if game and game not in seen_games:
                seen_games.add(game)
                unique_profiles.append(profile)

        return unique_profiles

    def delete_profile(self, user_id: str, game: str) -> bool:
        """Delete calibration profile from cloud and local storage.

        Args:
            user_id: User identifier
            game: Game identifier

        Returns:
            True if deletion successful
        """
        success = False

        # Delete from Supabase
        if self.supabase_enabled:
            try:
                self.supabase.table('gun_profiles').delete().eq('user_id', user_id).eq('game', game).execute()
                success = True
                logger.info(f"Profile deleted from Supabase: {user_id}/{game}")
            except Exception as e:
                logger.error(f"Supabase delete failed: {e}", exc_info=True)

        # Delete from local storage
        local_success = self._delete_local(user_id, game)

        return success or local_success

    # ========================================================================
    # Local Storage Helper Methods
    # ========================================================================

    def _get_profile_path(self, user_id: str, game: str) -> Path:
        """Get local file path for profile."""
        safe_user = user_id.replace('/', '_').replace('\\', '_')
        safe_game = game.replace('/', '_').replace('\\', '_')
        return self.local_storage_path / f"{safe_user}_{safe_game}.json"

    def _save_local(self, user_id: str, game: str, profile: Dict) -> bool:
        """Save profile to local JSON file."""
        try:
            profile_path = self._get_profile_path(user_id, game)
            with open(profile_path, 'w') as f:
                json.dump(profile, f, indent=2)
            logger.info(f"Profile saved locally: {profile_path}")
            return True
        except Exception as e:
            logger.error(f"Local save failed: {e}", exc_info=True)
            return False

    def _load_local(self, user_id: str, game: str) -> Optional[Dict]:
        """Load profile from local JSON file."""
        try:
            profile_path = self._get_profile_path(user_id, game)
            if profile_path.exists():
                with open(profile_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Local load failed: {e}", exc_info=True)
        return None

    def _list_local(self, user_id: str) -> List[Dict]:
        """List all local profiles for user."""
        profiles = []
        try:
            safe_user = user_id.replace('/', '_').replace('\\', '_')
            pattern = f"{safe_user}_*.json"

            for profile_file in self.local_storage_path.glob(pattern):
                try:
                    with open(profile_file, 'r') as f:
                        profile = json.load(f)
                        profiles.append({
                            'user_id': profile.get('user_id', user_id),
                            'game': profile.get('game', 'unknown'),
                            'created_at': profile.get('created_at', '')
                        })
                except Exception as e:
                    logger.error(f"Failed to read {profile_file}: {e}")
        except Exception as e:
            logger.error(f"Local list failed: {e}", exc_info=True)

        return profiles

    def _delete_local(self, user_id: str, game: str) -> bool:
        """Delete local profile file."""
        try:
            profile_path = self._get_profile_path(user_id, game)
            if profile_path.exists():
                profile_path.unlink()
                logger.info(f"Profile deleted locally: {profile_path}")
                return True
        except Exception as e:
            logger.error(f"Local delete failed: {e}", exc_info=True)
        return False


# ============================================================================
# Global Instance
# ============================================================================

gunner_config = GunnerConfigService()
