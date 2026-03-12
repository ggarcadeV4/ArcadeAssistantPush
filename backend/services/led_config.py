"""LED configuration service backed by local cabinet state files."""

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class LEDConfigService:
    """Singleton service for LED configuration management with local storage."""

    _instance = None
    _event_callbacks: Dict[str, List[Callable]] = {"led_config_updated": [], "led_config_error": []}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        drive_root = Path(os.getenv("AA_DRIVE_ROOT", "."))
        self.state_root = drive_root / ".aa" / "state"
        self.config_dir = self.state_root / "led_configs"
        self.map_dir = self.state_root / "led_maps"
        self.user_dir = self.state_root / "user_tendencies"

        for path in (self.config_dir, self.map_dir, self.user_dir):
            path.mkdir(parents=True, exist_ok=True)

    @lru_cache(maxsize=100)
    def get_config(self, device_id: str, game: str, user_id: Optional[str] = None) -> Dict:
        """Get LED configuration with optional user preference merge."""
        try:
            config = self._read_json(self._config_path(device_id, game, user_id))
            if not config:
                config = self._get_default_config()
            else:
                config = {
                    "buttons": config.get("buttons", {}),
                    "animation": config.get("animation", "solid"),
                    "brightness": config.get("brightness", 100),
                    "colors": config.get("colors", {"primary": "#00FF00", "secondary": "#FF0000"}),
                }

            if user_id:
                tendencies = self._get_user_tendencies(user_id)
                if tendencies:
                    config["brightness"] = tendencies.get("favorite_brightness", config["brightness"])
                    preferred_colors = tendencies.get("preferred_colors")
                    if isinstance(preferred_colors, dict):
                        config["colors"].update(preferred_colors)
            return config
        except Exception as e:
            logger.error("Failed to get config: %s", e)
            self._emit_event("led_config_error", {"error": str(e), "device_id": device_id, "game": game})
            return self._get_default_config()

    def save_config(self, device_id: str, game: str, config: Dict, user_id: Optional[str] = None) -> bool:
        """Save LED configuration to local cabinet state."""
        if not all(k in config for k in ["animation", "brightness"]):
            logger.error("Missing required config keys")
            return False
        try:
            payload = {
                "device_id": device_id,
                "game_id": game,
                "user_id": user_id,
                "buttons": config.get("buttons", {}),
                "animation": config.get("animation", "solid"),
                "brightness": config.get("brightness", 100),
                "colors": config.get("colors", {}),
            }
            self._write_json(self._config_path(device_id, game, user_id), payload)
            self._invalidate_cache()
            self._emit_event("led_config_updated", {"device_id": device_id, "game": game, "user_id": user_id})
            return True
        except Exception as e:
            logger.error("Failed to save config: %s", e)
            self._emit_event("led_config_error", {"error": str(e)})
            return False

    def delete_config(self, device_id: str, game: str, user_id: Optional[str] = None) -> bool:
        """Delete LED configuration from local cabinet state."""
        try:
            path = self._config_path(device_id, game, user_id)
            if path.exists():
                path.unlink()
            self._invalidate_cache()
            return True
        except Exception as e:
            logger.error("Failed to delete config: %s", e)
            return False

    def get_map(self, device_id: str, user_id: str = "default") -> Dict:
        """Get button remapping configuration."""
        try:
            return self._read_json(self._map_path(device_id))
        except Exception as e:
            logger.error("Failed to get map: %s", e)
            return {}

    def save_map(self, device_id: str, user_id: str, map_data: Dict) -> bool:
        """Save button remapping configuration."""
        try:
            payload = dict(map_data)
            payload.setdefault("device_id", device_id)
            self._write_json(self._map_path(device_id), payload)
            return True
        except Exception as e:
            logger.error("Failed to save map: %s", e)
            return False

    def apply_remap(self, logical_button: str, port: int) -> Dict:
        return {"logical": logical_button, "physical": port}

    def _invalidate_cache(self):
        self.get_config.cache_clear()

    def _get_default_config(self) -> Dict:
        return {
            "buttons": {},
            "animation": "solid",
            "brightness": 100,
            "colors": {"primary": "#00FF00", "secondary": "#FF0000"},
        }

    def _get_user_tendencies(self, user_id: str) -> Dict:
        data = self._read_json(self._user_path(user_id))
        if isinstance(data.get("preferences"), dict):
            return data["preferences"]
        return data if isinstance(data, dict) else {}

    def _config_path(self, device_id: str, game: str, user_id: Optional[str]) -> Path:
        suffix = self._safe_key(user_id or "default")
        return self.config_dir / f"{self._safe_key(device_id)}_{self._safe_key(game)}_{suffix}.json"

    def _map_path(self, device_id: str) -> Path:
        return self.map_dir / f"{self._safe_key(device_id)}.json"

    def _user_path(self, user_id: str) -> Path:
        return self.user_dir / f"{self._safe_key(user_id)}.json"

    def _read_json(self, path: Path) -> Dict:
        try:
            if not path.exists():
                return {}
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_json(self, path: Path, data: Dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def _safe_key(self, value: str) -> str:
        return str(value).replace('\\', '_').replace('/', '_').replace(':', '_')

    def _emit_event(self, event: str, data: Dict):
        for callback in self._event_callbacks.get(event, []):
            try:
                callback(data)
            except Exception as e:
                logger.debug("Config operation skipped: %s", e)


config_service = LEDConfigService()
