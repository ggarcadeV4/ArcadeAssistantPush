from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MarqueeSafeArea(BaseModel):
    x: int = 0
    y: int = 0
    width: int = 1920
    height: int = 360


class MarqueeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: int = 1
    target_monitor_index: int = 1
    target_display: str = "Display 2 - Marquee"
    resolution: str = "1920x360"
    safe_area: MarqueeSafeArea = Field(default_factory=MarqueeSafeArea)
    images_root: Optional[str] = None
    videos_root: Optional[str] = None
    image_path: Optional[str] = None
    video_path: Optional[str] = None
    use_video_if_available: bool = True
    fallback_mode: str = "system"
    use_fallback: bool = True
    fullscreen: bool = True
    window_width: int = 1920
    window_height: int = 360
    launchbox_root: Optional[str] = None
    state_file: Optional[str] = None
    preview_file: Optional[str] = None
    idle_image: Optional[str] = None
    idle_video: Optional[str] = None
    image_display_seconds: float = 3.0
    scroll_debounce_ms: int = 150
    video_loop: bool = True
    poll_interval_ms: int = 500
    prefer_video: bool = True
    fallback_to_platform_image: bool = True
    # Future event types: "HIGH_SCORE_CELEBRATION", "VOICE_COMMAND",
    # "ATTRACT", "PLAYER_PROFILE". Consumers should treat unknown
    # event_type values as "GAME" (default display behavior).
    event_type: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_shapes(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        payload = dict(data)

        display = payload.get("display")
        if isinstance(display, dict):
            payload.setdefault("target_monitor_index", display.get("target_monitor_index"))
            payload.setdefault("safe_area", display.get("safe_area"))

        paths = payload.get("paths")
        if isinstance(paths, dict):
            payload.setdefault("images_root", paths.get("images_root"))
            payload.setdefault("videos_root", paths.get("videos_root"))

        behavior = payload.get("behavior")
        if isinstance(behavior, dict):
            payload.setdefault("use_video_if_available", behavior.get("use_video_if_available"))
            payload.setdefault("fallback_mode", behavior.get("fallback_mode"))

        legacy_pairs = {
            "targetDisplay": "target_display",
            "safeArea": "safe_area",
            "imagePath": "image_path",
            "videoPath": "video_path",
            "useVideo": "use_video_if_available",
            "useFallback": "use_fallback",
            "target_monitor": "target_monitor_index",
        }
        for old_key, new_key in legacy_pairs.items():
            if old_key in payload and new_key not in payload:
                payload[new_key] = payload.get(old_key)

        if "useVideo" in payload and "prefer_video" not in payload:
            payload["prefer_video"] = payload.get("useVideo")

        if "window_width" not in payload and "safe_area" in payload and isinstance(payload["safe_area"], dict):
            payload["window_width"] = payload["safe_area"].get("width")
        if "window_height" not in payload and "safe_area" in payload and isinstance(payload["safe_area"], dict):
            payload["window_height"] = payload["safe_area"].get("height")

        return payload

    @model_validator(mode="after")
    def finalize_defaults(self) -> "MarqueeConfig":
        self.target_monitor_index = int(self.target_monitor_index or 1)

        if not self.target_display:
            self.target_display = f"Display {self.target_monitor_index + 1} - Marquee"

        if not self.window_width:
            self.window_width = int(self.safe_area.width or 1920)
        if not self.window_height:
            self.window_height = int(self.safe_area.height or 360)

        if not self.resolution:
            self.resolution = f"{self.window_width}x{self.window_height}"
        else:
            parts = str(self.resolution).lower().split("x", 1)
            if len(parts) == 2:
                try:
                    self.window_width = int(parts[0])
                    self.window_height = int(parts[1])
                except ValueError:
                    self.resolution = f"{self.window_width}x{self.window_height}"
            else:
                self.resolution = f"{self.window_width}x{self.window_height}"

        if self.fallback_mode not in {"system", "global", "black"}:
            self.fallback_mode = "system"

        if self.image_path and not self.images_root:
            try:
                self.images_root = str(Path(self.image_path).parent)
            except Exception:
                pass
        if self.video_path and not self.videos_root:
            try:
                self.videos_root = str(Path(self.video_path).parent)
            except Exception:
                pass

        return self


class MarqueeState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    game_id: Optional[str] = None
    title: Optional[str] = None
    platform: Optional[str] = None
    region: str = "North America"
    rom_name: Optional[str] = None
    source: Optional[str] = None
    mode: str = "image"
    updated_at: Optional[str] = None
    # Future event types: "HIGH_SCORE_CELEBRATION", "VOICE_COMMAND",
    # "ATTRACT", "PLAYER_PROFILE". Consumers should treat unknown
    # event_type values as "GAME" (default display behavior).
    event_type: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        if "game_title" in payload and "title" not in payload:
            payload["title"] = payload.get("game_title")
        if "system" in payload and "platform" not in payload:
            payload["platform"] = payload.get("system")
        if "event_type" not in payload and payload.get("title"):
            payload["event_type"] = "GAME"
        return payload

    def is_idle(self) -> bool:
        return (self.event_type or "").upper() == "IDLE"

    def normalized_event_type(self) -> str:
        value = (self.event_type or "GAME").upper()
        return "GAME" if value not in {"GAME", "IDLE"} else value

    def to_state_dict(self) -> Dict[str, Any]:
        return self.model_dump()
