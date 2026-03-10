"""LED configuration service with Supabase integration and local fallback."""
import json, logging, os
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Callable
from backend.services.supabase_client import get_client

logger = logging.getLogger(__name__)


class LEDConfigService:
    """Singleton service for LED configuration management with Supabase backend."""
    _instance = None
    _event_callbacks: Dict[str, List[Callable]] = {"led_config_updated": [], "led_config_error": []}

    def __new__(cls):
        """Enforce singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize service with fallback directory setup."""
        if self._initialized: return
        self._initialized = True
        self.fallback_dir = Path(os.getenv("AA_DRIVE_ROOT", ".")) / "state" / "led_configs"
        self.fallback_dir.mkdir(parents=True, exist_ok=True)
        self.fallback_path = self.fallback_dir / "fallback.json"

    @lru_cache(maxsize=100)
    def get_config(self, device_id: str, game: str, user_id: Optional[str] = None) -> Dict:
        """Get LED configuration with user tendency integration and caching."""
        try:
            client = get_client()
            if not client:
                return self._load_fallback_config(device_id, game, user_id)

            query = client.table("led_configs").select("*").eq("device_id", device_id).eq("game_id", game)
            if user_id:
                query = query.eq("user_id", user_id)

            result = query.maybeSingle().execute()
            if result.data:
                config = {
                    "buttons": result.data.get("colors", {}),
                    "animation": result.data.get("pattern", "solid"),
                    "brightness": result.data.get("brightness", 100),
                    "colors": result.data.get("colors", {"primary": "#00FF00", "secondary": "#FF0000"})
                }
                # Merge user tendencies if available
                if user_id:
                    tendencies = self._get_user_tendencies(client, user_id)
                    if tendencies:
                        config["brightness"] = tendencies.get("favorite_brightness", config["brightness"])
                        if "preferred_colors" in tendencies:
                            config["colors"].update(tendencies["preferred_colors"])
                return config
            return self._get_default_config()
        except Exception as e:
            logger.error(f"Failed to get config: {e}")
            self._emit_event("led_config_error", {"error": str(e), "device_id": device_id, "game": game})
            return self._load_fallback_config(device_id, game, user_id)

    def save_config(self, device_id: str, game: str, config: Dict, user_id: Optional[str] = None) -> bool:
        """Save LED configuration to Supabase with validation."""
        if not all(k in config for k in ["animation", "brightness"]):
            logger.error("Missing required config keys")
            return False
        try:
            client = get_client()
            if not client:
                return self._save_fallback_config(device_id, game, config, user_id)

            data = {
                "device_id": device_id, "game_id": game, "name": f"{game}_config",
                "pattern": config.get("animation", "solid"), "colors": config.get("colors", {}),
                "brightness": config.get("brightness", 100), "is_active": True
            }
            if user_id:
                data["user_id"] = user_id

            client.table("led_configs").upsert(data).execute()
            self._invalidate_cache()
            self._emit_event("led_config_updated", {"device_id": device_id, "game": game, "user_id": user_id})
            return True
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            self._emit_event("led_config_error", {"error": str(e)})
            return self._save_fallback_config(device_id, game, config, user_id)

    def delete_config(self, device_id: str, game: str, user_id: Optional[str] = None) -> bool:
        """Delete LED configuration from Supabase."""
        try:
            client = get_client()
            if not client: return False
            query = client.table("led_configs").delete().eq("device_id", device_id).eq("game_id", game)
            if user_id: query = query.eq("user_id", user_id)
            query.execute()
            self._invalidate_cache()
            return True
        except Exception as e:
            logger.error(f"Failed to delete config: {e}")
            return False

    def get_map(self, device_id: str, user_id: str = "default") -> Dict:
        """Get button remapping configuration."""
        try:
            client = get_client()
            if not client: return {}
            result = client.table("led_maps").select("button_map").eq("device_id", device_id).maybeSingle().execute()
            return result.data.get("button_map", {}) if result.data else {}
        except Exception as e:
            logger.error(f"Failed to get map: {e}")
            return {}

    def save_map(self, device_id: str, user_id: str, map_data: Dict) -> bool:
        """Save button remapping configuration."""
        try:
            client = get_client()
            if not client: return False
            client.table("led_maps").upsert({"device_id": device_id, "game_id": user_id, "button_map": map_data}).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to save map: {e}")
            return False

    def apply_remap(self, logical_button: str, port: int) -> Dict:
        """Apply button remapping from logical to physical port."""
        return {"logical": logical_button, "physical": port}

    def _invalidate_cache(self): self.get_config.cache_clear()

    def _get_default_config(self) -> Dict:
        """Return default configuration."""
        return {"buttons": {}, "animation": "solid", "brightness": 100, "colors": {"primary": "#00FF00", "secondary": "#FF0000"}}

    def _get_user_tendencies(self, client, user_id: str) -> Dict:
        """Get user preferences from tendencies table."""
        try:
            result = client.table("user_tendencies").select("preferences").eq("user_id", user_id).maybeSingle().execute()
            return result.data.get("preferences", {}) if result.data else {}
        except Exception as e: logger.debug("Config read fallback: %s", e); return {}

    def _load_fallback_config(self, device_id: str, game: str, user_id: Optional[str]) -> Dict:
        """Load configuration from local fallback."""
        try:
            if self.fallback_path.exists():
                with open(self.fallback_path) as f:
                    configs = json.load(f)
                    key = f"{device_id}:{game}:{user_id or 'none'}"
                    return configs.get(key, self._get_default_config())
        except Exception as e: logger.debug("Config operation skipped: %s", e)
        return self._get_default_config()

    def _save_fallback_config(self, device_id: str, game: str, config: Dict, user_id: Optional[str]) -> bool:
        """Save configuration to local fallback."""
        try:
            configs = {}
            if self.fallback_path.exists():
                with open(self.fallback_path) as f:
                    configs = json.load(f)
            key = f"{device_id}:{game}:{user_id or 'none'}"
            configs[key] = config
            with open(self.fallback_path, 'w') as f:
                json.dump(configs, f)
            return True
        except Exception as e:
            logger.error(f"Failed to save fallback: {e}")
            return False

    def _emit_event(self, event: str, data: Dict):
        """Emit event to registered callbacks."""
        for callback in self._event_callbacks.get(event, []):
            try: callback(data)
            except Exception as e: logger.debug("Config operation skipped: %s", e)


# Module-level singleton instance
config_service = LEDConfigService()