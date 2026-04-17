"""Gunner configuration service for calibration profile management."""

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from backend.constants.drive_root import get_drive_root
logger = logging.getLogger(__name__)

DEFAULT_PROFILE = {
    "points": [
        {"x": 0.1, "y": 0.1},
        {"x": 0.5, "y": 0.1},
        {"x": 0.9, "y": 0.1},
        {"x": 0.1, "y": 0.5},
        {"x": 0.5, "y": 0.5},
        {"x": 0.9, "y": 0.5},
        {"x": 0.1, "y": 0.9},
        {"x": 0.5, "y": 0.9},
        {"x": 0.9, "y": 0.9},
    ],
    "sensitivity": 85,
    "deadzone": 2,
    "offset_x": 0,
    "offset_y": 0,
}


def _fallback_storage_path() -> Path:
    return Path(tempfile.gettempdir()) / "arcade-assistant" / "state" / "gun_profiles"


def _ensure_storage_path(candidate: Path) -> Path:
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate
    except Exception as exc:
        fallback = _fallback_storage_path()
        fallback.mkdir(parents=True, exist_ok=True)
        logger.warning(
            "Failed to initialize gunner storage at %s: %s. Falling back to %s",
            candidate,
            exc,
            fallback,
        )
        return fallback


class GunnerConfigService:
    """Calibration profile management backed by local JSON files."""

    def __init__(self, local_storage_path: Optional[Path] = None):
        if local_storage_path is None:
            drive_root = get_drive_root(context="gunner_config")
            local_storage_path = drive_root / '.aa' / 'state' / 'gun_profiles'

        self.local_storage_path = _ensure_storage_path(Path(local_storage_path))
        logger.info("Local gunner storage: %s", self.local_storage_path)

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
        if len(points) != 9:
            logger.error("Invalid points count: %s (expected 9)", len(points))
            return False

        for point in points:
            if not (0.0 <= point.get('x', -1) <= 1.0 and 0.0 <= point.get('y', -1) <= 1.0):
                logger.error("Invalid point coordinates: %s", point)
                return False

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
        return self._save_local(user_id, game, profile)

    def load_profile(self, user_id: str, game: str) -> List[Dict]:
        local_profile = self._load_local(user_id, game)
        if local_profile:
            logger.info("Profile loaded from local storage: %s/%s", user_id, game)
            return local_profile.get('points', DEFAULT_PROFILE['points'])

        logger.info("Using default profile for %s/%s", user_id, game)
        return DEFAULT_PROFILE['points']

    def list_profiles(self, user_id: str) -> List[Dict]:
        return self._list_local(user_id)

    def delete_profile(self, user_id: str, game: str) -> bool:
        return self._delete_local(user_id, game)

    def _get_profile_path(self, user_id: str, game: str) -> Path:
        safe_user = user_id.replace('/', '_').replace('\\', '_')
        safe_game = game.replace('/', '_').replace('\\', '_')
        return self.local_storage_path / f"{safe_user}_{safe_game}.json"

    def _save_local(self, user_id: str, game: str, profile: Dict) -> bool:
        try:
            profile_path = self._get_profile_path(user_id, game)
            existing = self._load_local(user_id, game) or {}
            merged = {**existing, **profile}
            profile_path.write_text(json.dumps(merged, indent=2) + "\n", encoding='utf-8')
            logger.info("Profile saved locally: %s", profile_path)
            return True
        except Exception as e:
            logger.error("Local save failed: %s", e, exc_info=True)
            return False

    def _load_local(self, user_id: str, game: str) -> Optional[Dict]:
        try:
            profile_path = self._get_profile_path(user_id, game)
            if profile_path.exists():
                return json.loads(profile_path.read_text(encoding='utf-8'))
        except Exception as e:
            logger.error("Local load failed: %s", e, exc_info=True)
        return None

    def _list_local(self, user_id: str) -> List[Dict]:
        profiles = []
        try:
            safe_user = user_id.replace('/', '_').replace('\\', '_')
            pattern = f"{safe_user}_*.json"

            for profile_file in self.local_storage_path.glob(pattern):
                try:
                    profile = json.loads(profile_file.read_text(encoding='utf-8'))
                    profiles.append({
                        'user_id': profile.get('user_id', user_id),
                        'game': profile.get('game', 'unknown'),
                        'created_at': profile.get('created_at', '')
                    })
                except Exception as e:
                    logger.error("Failed to read %s: %s", profile_file, e)
        except Exception as e:
            logger.error("Local list failed: %s", e, exc_info=True)

        return profiles

    def _delete_local(self, user_id: str, game: str) -> bool:
        try:
            profile_path = self._get_profile_path(user_id, game)
            if profile_path.exists():
                profile_path.unlink()
                logger.info("Profile deleted locally: %s", profile_path)
                return True
        except Exception as e:
            logger.error("Local delete failed: %s", e, exc_info=True)
        return False


gunner_config = GunnerConfigService()
