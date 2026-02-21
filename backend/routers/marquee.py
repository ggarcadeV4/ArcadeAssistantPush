"""
Marquee configuration router (Third Screen).
Config-only layer: loads/saves marquee.json and exposes simple test endpoints.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from urllib.parse import quote

import asyncio
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.routers.content_manager import _load_content_paths  # reuse existing path loader
from backend.services.launchbox_parser import parser

router = APIRouter(prefix="/api/local/marquee", tags=["marquee"])

# State file location for external marquee apps (Python watcher, etc.)
def _state_file_path() -> Path:
    """Get state file path. Requires AA_DRIVE_ROOT (no hardcoded fallback)."""
    drive_root = os.environ.get("AA_DRIVE_ROOT")
    if not drive_root:
        drive_root = os.getcwd()  # Dev fallback only
    return Path(drive_root) / ".aa" / "state" / "marquee_current.json"

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _drive_root(request: Optional[Request]) -> Path:
    try:
        root = getattr(request.app.state, "drive_root", None) if request else None
        if root:
            return Path(root)
    except Exception:
        pass
    return Path(os.environ.get("AA_DRIVE_ROOT", os.getcwd())) / "Arcade Assistant"


def _config_path(request: Optional[Request]) -> Path:
    return _drive_root(request) / "config" / "marquee.json"


def _default_paths(drive_root: Path) -> Dict[str, Optional[str]]:
    paths = _load_content_paths(drive_root)
    artwork = paths.get("artwork", {})
    images = artwork.get("marqueeImages") or None
    videos = artwork.get("marqueeVideos") or None
    return {
        "images_root": images,
        "videos_root": videos,
    }


def get_default_marquee_config(drive_root: Path) -> Dict[str, Any]:
    defaults = _default_paths(drive_root)
    return {
        "version": 1,
        "display": {
            "target_monitor_index": 1,
            "safe_area": {"x": 0, "y": 0, "width": 1920, "height": 360},
        },
        "paths": defaults,
        "behavior": {
            "use_video_if_available": True,
            "fallback_mode": "system",
        },
    }


async def load_marquee_config(request: Optional[Request]) -> Dict[str, Any]:
    drive_root = _drive_root(request)
    target = _config_path(request)

    def _do_load():
        data = None
        try:
            if target.exists():
                data = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            data = None
        return data

    data = await asyncio.to_thread(_do_load)

    if not isinstance(data, dict):
        data = get_default_marquee_config(drive_root)
        await save_marquee_config(data, request, allow_backup=False)
    return data


async def save_marquee_config(cfg: Dict[str, Any], request: Optional[Request], allow_backup: bool = True) -> None:
    target = _config_path(request)
    drive_root = _drive_root(request)

    def _do_save():
        target.parent.mkdir(parents=True, exist_ok=True)

        if allow_backup and target.exists():
            backup_dir = drive_root / ".aa" / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = Path(target.name).stem + "_backup"
            shutil.copy2(target, backup_dir / f"{timestamp}.json")

        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        tmp.replace(target)

    await asyncio.to_thread(_do_save)


# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------


class SafeArea(BaseModel):
    x: int = 0
    y: int = 0
    width: int = 1920
    height: int = 360


class MarqueePaths(BaseModel):
    images_root: Optional[str] = None
    videos_root: Optional[str] = None


class MarqueeBehavior(BaseModel):
    use_video_if_available: bool = True
    fallback_mode: str = Field("system", description="system|global|black")

    @field_validator("fallback_mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        allowed = {"system", "global", "black"}
        if v not in allowed:
            raise ValueError(f"fallback_mode must be one of {sorted(allowed)}")
        return v


class MarqueeDisplay(BaseModel):
    target_monitor_index: int = 1
    safe_area: SafeArea = SafeArea()


class MarqueeConfig(BaseModel):
    version: int = 1
    display: MarqueeDisplay = MarqueeDisplay()
    paths: MarqueePaths = MarqueePaths()
    behavior: MarqueeBehavior = MarqueeBehavior()


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------


@router.get("/config")
async def get_config(request: Request):
    cfg = await load_marquee_config(request)
    return cfg


@router.post("/config")
async def post_config(payload: MarqueeConfig, request: Request):
    cfg = payload.model_dump()
    try:
        await save_marquee_config(cfg, request)
        return {"ok": True, "config": cfg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save marquee config: {e}")


@router.post("/test-image")
async def test_image(request: Request):
    cfg = await load_marquee_config(request)
    images_root = (cfg.get("paths") or {}).get("images_root")
    exists = bool(images_root) and Path(images_root).exists()
    return {
        "ok": True,
        "message": "Test image command accepted (rendering not implemented)",
        "images_root_exists": exists,
    }


@router.post("/test-video")
async def test_video(request: Request):
    cfg = await load_marquee_config(request)
    videos_root = (cfg.get("paths") or {}).get("videos_root")
    exists = bool(videos_root) and Path(videos_root).exists()
    return {
        "ok": True,
        "message": "Test video command accepted (rendering not implemented)",
        "videos_root_exists": exists,
    }


# -----------------------------------------------------------------------------
# Runtime State: Current Game & Media Resolution
# -----------------------------------------------------------------------------

# In-memory current game state (updated by frontend events or Pegasus hooks)
_current_game: Dict[str, Any] = {}

import logging
_marquee_logger = logging.getLogger(__name__)


def _seed_current_game_from_file() -> None:
    """
    Load existing marquee state from file on startup.
    
    This ensures the marquee state persists across backend restarts.
    Called once on module load.
    """
    global _current_game
    try:
        state_path = _state_file_path()
        if state_path.exists():
            data = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("game_id"):
                _current_game = {
                    "game_id": data.get("game_id"),
                    "title": data.get("title"),
                    "platform": data.get("platform"),
                    "region": data.get("region", "North America"),
                }
                _marquee_logger.info(f"Seeded marquee state from file: {data.get('title')}")
    except Exception as e:
        _marquee_logger.debug(f"Could not seed marquee state: {e}")


# Seed on module load to persist state across restarts
_seed_current_game_from_file()


def persist_current_game(game: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update in-memory marquee game and persist to state file for external apps.

    This is used by the API handler and by launch flows to keep the Python
    marquee watcher in sync.
    
    Also triggers LED profile lookup if a binding exists for this game.
    """
    global _current_game
    _current_game = {
        "game_id": game.get("game_id"),
        "title": game.get("title"),
        "platform": game.get("platform"),
        "region": game.get("region", "North America"),
    }
    try:
        state_path = _state_file_path()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(_current_game, ensure_ascii=False), encoding="utf-8")
    except Exception:
        # Persistence failures should not block marquee updates
        pass
    
    # Trigger LED profile lookup for displayed game (Task 5: LED updates for displayed game)
    _trigger_led_profile_for_game(game.get("game_id"))
    
    return _current_game


def _trigger_led_profile_for_game(game_id: Optional[str]) -> None:
    """
    Look up and trigger LED profile for the given game.
    
    This is called when a game is selected/previewed to update LED lighting
    to match the game's profile (if one exists).
    """
    if not game_id:
        return
    
    try:
        from backend.services.led_game_profiles import LEDGameProfileStore
        
        drive_root = Path(os.environ.get("AA_DRIVE_ROOT", os.getcwd()))
        store = LEDGameProfileStore(drive_root)
        binding = store.get_binding(game_id)
        
        if binding and binding.get("profile_name"):
            # Write the profile name to a state file for LED engine to pick up
            led_state_path = drive_root / ".aa" / "state" / "led_current_profile.json"
            led_state_path.parent.mkdir(parents=True, exist_ok=True)
            led_state = {
                "game_id": game_id,
                "profile_name": binding.get("profile_name"),
                "triggered_at": datetime.now(timezone.utc).isoformat(),
                "source": "marquee_preview",
            }
            led_state_path.write_text(json.dumps(led_state, ensure_ascii=False), encoding="utf-8")
            _marquee_logger.debug(f"LED profile triggered for {game_id}: {binding.get('profile_name')}")
    except Exception as e:
        # LED failures should not block marquee updates
        _marquee_logger.debug(f"LED profile lookup failed for {game_id}: {e}")


class SetGamePayload(BaseModel):
    game_id: str
    title: str
    platform: str = "Arcade"
    region: str = "North America"


# -----------------------------------------------------------------------------
# Preview State (for scroll/hover - separate from current-game/launched)
# -----------------------------------------------------------------------------

_preview_game: Dict[str, Any] = {}
_preview_mode: str = "image"  # "image" for scroll preview, "video" for launched


def _preview_state_file_path() -> Path:
    """Get preview state file path for external marquee apps."""
    drive_root = os.environ.get("AA_DRIVE_ROOT", os.getcwd())
    return Path(drive_root) / ".aa" / "state" / "marquee_preview.json"


def persist_preview_game(game: Dict[str, Any], mode: str = "image") -> Dict[str, Any]:
    """
    Update preview state and persist for external apps.
    
    Mode:
    - "image": Show static marquee image only (fast, for scrolling)
    - "video": Play video then show image (for game launch/select)
    """
    global _preview_game, _preview_mode
    _preview_game = {
        "game_id": game.get("game_id"),
        "title": game.get("title"),
        "platform": game.get("platform"),
        "region": game.get("region", "North America"),
        "mode": mode,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    _preview_mode = mode
    
    try:
        state_path = _preview_state_file_path()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(_preview_game, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return _preview_game


@router.get("/current-game")
async def get_current_game():
    """Get the currently selected game for marquee display."""
    if not _current_game:
        return {"game_id": None, "title": None, "platform": None}
    return _current_game


@router.post("/current-game")
async def set_current_game(payload: SetGamePayload):
    """Set the currently selected game (called by frontend or Pegasus hook)."""
    game = {
        "game_id": payload.game_id,
        "title": payload.title,
        "platform": payload.platform,
        "region": payload.region,
    }
    return {"ok": True, "game": persist_current_game(game)}


# -----------------------------------------------------------------------------
# Preview Endpoints (for scroll/hover marquee updates)
# -----------------------------------------------------------------------------

class PreviewPayload(BaseModel):
    """Payload for marquee preview (scroll/hover)."""
    game_id: str = ""
    title: str
    platform: str = "Arcade"
    region: str = "North America"
    mode: str = "image"  # "image" for scroll, "video" for select


@router.get("/preview")
async def get_preview():
    """
    Get current preview state.
    
    Returns the game being previewed (scrolled to) and display mode.
    """
    if not _preview_game:
        return {"game_id": None, "title": None, "platform": None, "mode": "idle"}
    return _preview_game


@router.post("/preview")
async def set_preview(payload: PreviewPayload):
    """
    Set marquee preview (for scroll/hover).
    
    Call this when user scrolls to a game in Pegasus/LaunchBox.
    Uses mode="image" for fast preview, mode="video" when game is selected.
    
    Flow:
    1. User scrolls through games → POST /preview with mode="image"
    2. User selects/launches game → POST /preview with mode="video"
    3. Marquee shows image immediately, then plays video if mode="video"
    """
    # Start with provided values
    resolved_game_id = payload.game_id
    
    # Resolve game_id from title if not provided (enables LED profile lookup)
    if not resolved_game_id and payload.title:
        try:
            # Search through all games for a title match
            all_games = parser.get_all_games() or []
            title_lower = payload.title.lower().strip()
            platform_lower = (payload.platform or "").lower().strip()
            
            for game in all_games:
                game_title = (getattr(game, "title", "") or "").lower().strip()
                game_platform = (getattr(game, "platform", "") or "").lower().strip()
                
                if game_title == title_lower:
                    # If platform specified, match both; otherwise just title
                    if not platform_lower or game_platform == platform_lower:
                        resolved_game_id = game.id
                        _marquee_logger.debug(f"Resolved game_id '{resolved_game_id}' from title '{payload.title}'")
                        break
        except Exception as e:
            _marquee_logger.debug(f"Could not resolve game_id from title: {e}")
    
    game = {
        "game_id": resolved_game_id,
        "title": payload.title,
        "platform": payload.platform,
        "region": payload.region,
    }
    result = persist_preview_game(game, payload.mode)
    
    # If mode is "video" (game selected), also update current_game for legacy compatibility
    if payload.mode == "video":
        persist_current_game(game)
    
    return {"ok": True, "preview": result}


@router.post("/preview/clear")
async def clear_preview():
    """Clear the preview state (e.g., when returning to menu)."""
    global _preview_game, _preview_mode
    _preview_game = {}
    _preview_mode = "image"
    
    try:
        state_path = _preview_state_file_path()
        if state_path.exists():
            state_path.write_text("{}", encoding="utf-8")
    except Exception:
        pass
    
    return {"ok": True, "cleared": True}


# -----------------------------------------------------------------------------
# Queue/Cascade API (Pixelcade-style chaining)
# -----------------------------------------------------------------------------

# In-memory queue for marquee display items
_display_queue: List[Dict[str, Any]] = []
_queue_active: bool = False


class QueueItem(BaseModel):
    """Single item in a marquee display queue."""
    type: str = "image"  # "image", "video", "text", "game"
    # For game type
    game_id: Optional[str] = None
    title: Optional[str] = None
    platform: Optional[str] = None
    # For text type
    text: Optional[str] = None
    scroll: bool = False
    # Timing
    duration_ms: int = 5000  # How long to show this item (0 = indefinite)


class QueuePayload(BaseModel):
    """Payload for queue/cascade display."""
    items: List[QueueItem]
    loop: bool = False  # Loop the queue after finishing
    clear_existing: bool = True  # Clear existing queue before adding


def _queue_state_file_path() -> Path:
    """Get queue state file path for external marquee apps."""
    drive_root = os.environ.get("AA_DRIVE_ROOT", os.getcwd())
    return Path(drive_root) / ".aa" / "state" / "marquee_queue.json"


def _persist_queue() -> None:
    """Persist queue state to file for external apps."""
    try:
        state_path = _queue_state_file_path()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "items": _display_queue,
            "active": _queue_active,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        state_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


@router.get("/queue")
async def get_queue():
    """
    Get current marquee display queue.
    
    Returns the list of queued display items and whether the queue is active.
    """
    return {
        "items": _display_queue,
        "active": _queue_active,
        "count": len(_display_queue)
    }


@router.post("/queue")
async def set_queue(payload: QueuePayload):
    """
    Set marquee display queue (Pixelcade-style cascade).
    
    Queue items are displayed in sequence. Each item has a type and duration.
    Useful for:
    - Attract mode sequences
    - Game intro animations (image → video → image)
    - Scrolling text announcements
    
    Example:
    ```json
    {
      "items": [
        {"type": "image", "game_id": "pacman", "duration_ms": 3000},
        {"type": "video", "game_id": "pacman", "duration_ms": 0},
        {"type": "text", "text": "INSERT COIN", "scroll": true, "duration_ms": 5000}
      ],
      "loop": true
    }
    ```
    """
    global _display_queue, _queue_active
    
    if payload.clear_existing:
        _display_queue = []
    
    # Add items to queue
    for item in payload.items:
        queue_item = {
            "type": item.type,
            "game_id": item.game_id,
            "title": item.title,
            "platform": item.platform,
            "text": item.text,
            "scroll": item.scroll,
            "duration_ms": item.duration_ms,
            "added_at": datetime.now(timezone.utc).isoformat()
        }
        _display_queue.append(queue_item)
    
    _queue_active = len(_display_queue) > 0
    _persist_queue()
    
    # If queue has items, set first item as current preview
    if _display_queue:
        first = _display_queue[0]
        if first.get("type") in ("image", "video", "game") and first.get("title"):
            persist_preview_game({
                "game_id": first.get("game_id", ""),
                "title": first.get("title", ""),
                "platform": first.get("platform", "Arcade"),
            }, mode="image" if first.get("type") == "image" else "video")
    
    return {
        "ok": True,
        "queue_length": len(_display_queue),
        "loop": payload.loop,
        "active": _queue_active
    }


@router.post("/queue/next")
async def advance_queue():
    """
    Advance to the next item in the queue.
    
    Called by the marquee display when an item's duration expires.
    Returns the next item to display.
    """
    global _display_queue, _queue_active
    
    if not _display_queue:
        _queue_active = False
        return {"ok": True, "item": None, "remaining": 0}
    
    # Remove first item (already displayed)
    _display_queue.pop(0)
    _persist_queue()
    
    if not _display_queue:
        _queue_active = False
        return {"ok": True, "item": None, "remaining": 0}
    
    # Return next item
    next_item = _display_queue[0]
    
    # Update preview if it's a game
    if next_item.get("type") in ("image", "video", "game") and next_item.get("title"):
        persist_preview_game({
            "game_id": next_item.get("game_id", ""),
            "title": next_item.get("title", ""),
            "platform": next_item.get("platform", "Arcade"),
        }, mode="image" if next_item.get("type") == "image" else "video")
    
    return {
        "ok": True,
        "item": next_item,
        "remaining": len(_display_queue) - 1
    }


@router.post("/queue/clear")
async def clear_queue():
    """Clear the display queue."""
    global _display_queue, _queue_active
    _display_queue = []
    _queue_active = False
    _persist_queue()
    return {"ok": True, "cleared": True}


@router.post("/queue/text")
async def queue_text(text: str = Query(...), scroll: bool = False, duration_ms: int = 5000):
    """
    Quick endpoint to queue scrolling text.
    
    Useful for announcements like "INSERT COIN", high score alerts, etc.
    """
    global _display_queue, _queue_active
    
    text_item = {
        "type": "text",
        "text": text,
        "scroll": scroll,
        "duration_ms": duration_ms,
        "added_at": datetime.now(timezone.utc).isoformat()
    }
    _display_queue.append(text_item)
    _queue_active = True
    _persist_queue()
    
    return {"ok": True, "queued": text_item, "queue_length": len(_display_queue)}


def _escape_glob(s: str) -> str:
    """Escape special glob characters in a string."""
    import re
    return re.sub(r'([\[\]?*])', r'[\1]', s)


def _find_media_file(directory: Path, game_name: str, extensions: list) -> Optional[Path]:
    """
    Find a media file matching the game name in the given directory.
    Uses case-insensitive prefix matching.
    """
    if not directory.exists():
        return None
    
    game_lower = game_name.lower()
    
    for file in directory.iterdir():
        if not file.is_file():
            continue
        if file.suffix.lower() not in extensions:
            continue
        # Check if filename starts with game name (case-insensitive)
        if file.stem.lower().startswith(game_lower):
            return file
    
    return None


@router.get("/media")
async def get_media(request: Request, game_id: str, platform: str = "Arcade"):
    """
    Resolve video and marquee image URLs for a given game.
    Searches LaunchBox folder structure for matching media.
    """
    launchbox_root = Path(os.environ.get("AA_DRIVE_ROOT", os.getcwd())) / "LaunchBox"

    # If a UUID is provided, look up the game to get its title for filename matching
    game_title = None
    try:
        game = parser.get_game_by_id(game_id)
        if game:
            game_title = getattr(game, "title", None)
            platform = platform or getattr(game, "platform", platform)
    except Exception:
        game_title = None
    
    # Normalize game_id for filename matching (remove special chars that aren't in filenames)
    name_for_match = game_title or game_id
    game_name = name_for_match.replace(":", "").replace("?", "").replace("*", "").replace("/", "").replace("\\", "")
    
    video_url = None
    image_url = None
    
    # Search for video in LaunchBox/Videos/{platform}/
    videos_dir = launchbox_root / "Videos" / platform
    video_file = _find_media_file(videos_dir, game_name, [".mp4", ".avi", ".mkv", ".webm"])
    if video_file:
        encoded = quote(video_file.as_posix(), safe="/:\\")
        video_url = f"/api/local/marquee/serve-media?path={encoded}"
    
    # Search for marquee image in LaunchBox/Images/{platform}/Arcade - Marquee/ or similar
    # LaunchBox structure: Images/{Platform}/{ImageType}/{Region}/{filename}
    images_base = launchbox_root / "Images" / platform
    marquee_dirs = [
        images_base / "Arcade - Marquee",
        images_base / f"{platform} - Marquee",
        images_base / "Marquee",
    ]
    
    # Also check region subfolders
    regions = ["North America", "World", "Europe", "Japan", ""]
    image_extensions = [".png", ".jpg", ".jpeg"]
    
    for marquee_dir in marquee_dirs:
        if image_url:
            break
        for region in regions:
            search_dir = marquee_dir / region if region else marquee_dir
            image_file = _find_media_file(search_dir, game_name, image_extensions)
            if image_file:
                encoded = quote(image_file.as_posix(), safe="/:\\")
                image_url = f"/api/local/marquee/serve-media?path={encoded}"
                break
    
    return {
        "game_id": game_id,
        "platform": platform,
        "video_url": video_url,
        "image_url": image_url,
    }


@router.get("/serve-media")
async def serve_media(path: str):
    """Serve a local media file (video or image) to the browser."""
    from fastapi.responses import FileResponse
    
    # Security: only allow files under LaunchBox directory
    launchbox_root = Path(os.environ.get("AA_DRIVE_ROOT", os.getcwd())) / "LaunchBox"
    
    # Convert path back to Path object
    file_path = Path(path)
    
    # Validate path is under LaunchBox
    try:
        file_path.resolve().relative_to(launchbox_root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: path outside LaunchBox")
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Determine media type
    suffix = file_path.suffix.lower()
    media_types = {
        ".mp4": "video/mp4",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
    }
    media_type = media_types.get(suffix, "application/octet-stream")
    
    return FileResponse(file_path, media_type=media_type)


# -----------------------------------------------------------------------------
# Enhanced Media Resolution with Fallback Priority Chain
# -----------------------------------------------------------------------------

def _find_platform_marquee(launchbox_root: Path, platform: str) -> Optional[Path]:
    """Find a platform-level marquee image as fallback."""
    images_base = launchbox_root / "Images" / platform
    
    # Try platform marquee locations
    platform_marquee_dirs = [
        images_base / "Arcade - Marquee",
        images_base / f"{platform} - Marquee", 
        images_base / "Marquee",
        images_base / "Banner",
    ]
    
    image_extensions = [".png", ".jpg", ".jpeg"]
    
    for marquee_dir in platform_marquee_dirs:
        if not marquee_dir.exists():
            continue
        # Look for platform-named file or any marquee
        for ext in image_extensions:
            platform_file = marquee_dir / f"{platform}{ext}"
            if platform_file.exists():
                return platform_file
        # Take first available image
        for f in marquee_dir.iterdir():
            if f.is_file() and f.suffix.lower() in image_extensions:
                return f
    
    return None


def _find_default_idle_art(launchbox_root: Path) -> Optional[Path]:
    """Find default idle artwork when no game-specific media exists."""
    # Check common default locations
    candidates = [
        launchbox_root / "Images" / "Idle" / "default.png",
        launchbox_root / "Images" / "Idle" / "idle.png",
        launchbox_root / "Images" / "Marquee" / "default.png",
        Path(os.environ.get("AA_DRIVE_ROOT", os.getcwd())) / "Arcade Assistant Local" / "assets" / "marquee_idle.png",
    ]
    
    for path in candidates:
        if path.exists():
            return path
    
    return None


@router.get("/media-with-fallback")
async def get_media_with_fallback(request: Request, game_id: str, platform: str = "Arcade"):
    """
    Resolve media for a game with full fallback priority chain.
    
    Priority order:
    1. Game video (if exists and prefer_video enabled)
    2. Game marquee image
    3. Platform marquee image
    4. Default idle art
    
    Returns:
        - primary_url: The URL to display (video or image)
        - primary_type: "video" | "image" | "idle"
        - fallback_used: Which fallback level was used
        - all_urls: Dict of all resolved URLs for advanced clients
    """
    launchbox_root = Path(os.environ.get("AA_DRIVE_ROOT", os.getcwd())) / "LaunchBox"
    cfg = load_marquee_config(request)
    prefer_video = cfg.get("behavior", {}).get("use_video_if_available", True)
    
    # Resolve game title
    game_title = None
    try:
        game = parser.get_game_by_id(game_id)
        if game:
            game_title = getattr(game, "title", None)
            platform = platform or getattr(game, "platform", platform)
    except Exception:
        pass
    
    name_for_match = game_title or game_id
    game_name = name_for_match.replace(":", "").replace("?", "").replace("*", "").replace("/", "").replace("\\", "")
    
    # Initialize result
    result = {
        "game_id": game_id,
        "platform": platform,
        "primary_url": None,
        "primary_type": "idle",
        "fallback_used": "none",
        "all_urls": {
            "game_video": None,
            "game_image": None,
            "platform_image": None,
            "idle_image": None,
        }
    }
    
    # 1. Try game video
    videos_dir = launchbox_root / "Videos" / platform
    video_file = _find_media_file(videos_dir, game_name, [".mp4", ".avi", ".mkv", ".webm"])
    if video_file:
        encoded = quote(video_file.as_posix(), safe="/:\\")
        result["all_urls"]["game_video"] = f"/api/local/marquee/serve-media?path={encoded}"
    
    # 2. Try game marquee image
    images_base = launchbox_root / "Images" / platform
    marquee_dirs = [
        images_base / "Arcade - Marquee",
        images_base / f"{platform} - Marquee",
        images_base / "Marquee",
        images_base / "Banner",
    ]
    regions = ["North America", "World", "Europe", "Japan", ""]
    image_extensions = [".png", ".jpg", ".jpeg"]
    
    game_image_file = None
    for marquee_dir in marquee_dirs:
        if game_image_file:
            break
        for region in regions:
            search_dir = marquee_dir / region if region else marquee_dir
            game_image_file = _find_media_file(search_dir, game_name, image_extensions)
            if game_image_file:
                break
    
    if game_image_file:
        encoded = quote(game_image_file.as_posix(), safe="/:\\")
        result["all_urls"]["game_image"] = f"/api/local/marquee/serve-media?path={encoded}"
    
    # 3. Try platform marquee
    platform_image_file = _find_platform_marquee(launchbox_root, platform)
    if platform_image_file:
        encoded = quote(platform_image_file.as_posix(), safe="/:\\")
        result["all_urls"]["platform_image"] = f"/api/local/marquee/serve-media?path={encoded}"
    
    # 4. Try default idle art
    idle_file = _find_default_idle_art(launchbox_root)
    if idle_file:
        encoded = quote(idle_file.as_posix(), safe="/:\\")
        result["all_urls"]["idle_image"] = f"/api/local/marquee/serve-media?path={encoded}"
    
    # Determine primary based on priority
    if prefer_video and result["all_urls"]["game_video"]:
        result["primary_url"] = result["all_urls"]["game_video"]
        result["primary_type"] = "video"
        result["fallback_used"] = "none"
    elif result["all_urls"]["game_image"]:
        result["primary_url"] = result["all_urls"]["game_image"]
        result["primary_type"] = "image"
        result["fallback_used"] = "none" if not prefer_video else "game_image"
    elif result["all_urls"]["platform_image"]:
        result["primary_url"] = result["all_urls"]["platform_image"]
        result["primary_type"] = "image"
        result["fallback_used"] = "platform_image"
    elif result["all_urls"]["idle_image"]:
        result["primary_url"] = result["all_urls"]["idle_image"]
        result["primary_type"] = "idle"
        result["fallback_used"] = "idle_image"
    else:
        result["fallback_used"] = "no_media_found"
    
    return result


# =============================================================================
# MESSAGE QUEUE SYSTEM (MVP)
# =============================================================================
# Provides scrolling messages and alerts for Marquee MVP.
# Storage: .aa/state/marquee/messages.jsonl (append-only JSONL)
# Log: .aa/logs/marquee/events.jsonl

import logging
import uuid

_msg_logger = logging.getLogger(__name__ + ".messages")


def _get_aa_root() -> Path:
    """Get the .aa directory path from drive root. No hardcoded A:\\ fallback."""
    drive_root = Path(os.environ.get("AA_DRIVE_ROOT", os.getcwd()))
    return drive_root / ".aa"


def _messages_file_path() -> Path:
    """Get the messages queue file path under .aa/state/marquee/."""
    aa_root = _get_aa_root()
    path = aa_root / "state" / "marquee" / "messages.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _marquee_log_path() -> Path:
    """Get the marquee events log path under .aa/logs/marquee/."""
    aa_root = _get_aa_root()
    path = aa_root / "logs" / "marquee" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _log_marquee_event(event_type: str, details: Dict[str, Any]) -> None:
    """Log a marquee event to JSONL (best-effort, non-blocking)."""
    try:
        log_path = _marquee_log_path()
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            **details
        }
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Best-effort logging


# -----------------------------------------------------------------------------
# Message Models
# -----------------------------------------------------------------------------

class MarqueeMessagePayload(BaseModel):
    """Payload for posting a marquee message."""
    text: str = Field(..., min_length=1, max_length=500, description="Message text to display")
    type: str = Field("message", description="Type: 'message' or 'alert'")
    severity: Optional[str] = Field(None, description="Severity for alerts: 'info', 'warn', 'error'")
    ttl_seconds: Optional[int] = Field(None, ge=1, le=86400, description="Time-to-live in seconds (optional)")
    source: Optional[str] = Field(None, description="Source module/component (optional)")
    sticky: bool = Field(False, description="If true, message persists until manually cleared")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"message", "alert"}
        if v not in allowed:
            raise ValueError(f"type must be one of {sorted(allowed)}")
        return v

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        allowed = {"info", "warn", "error"}
        if v not in allowed:
            raise ValueError(f"severity must be one of {sorted(allowed)}")
        return v


class MarqueeMessage(BaseModel):
    """A marquee message entry."""
    id: str
    text: str
    type: str
    severity: Optional[str] = None
    source: Optional[str] = None
    sticky: bool = False
    created_at: str
    expires_at: Optional[str] = None


# -----------------------------------------------------------------------------
# Message Queue Functions
# -----------------------------------------------------------------------------

def _read_all_messages() -> List[Dict[str, Any]]:
    """Read all messages from the JSONL file."""
    path = _messages_file_path()
    if not path.exists():
        return []
    
    messages = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass
    return messages


def _append_message(msg: Dict[str, Any]) -> None:
    """Append a message to the JSONL file."""
    path = _messages_file_path()
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(msg) + "\n")


def _filter_active_messages(messages: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    """Filter messages to only active (non-expired) ones."""
    active = []
    for msg in messages:
        expires_at = msg.get("expires_at")
        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if exp_dt < now:
                    continue  # Expired
            except Exception:
                pass  # Keep if parsing fails
        active.append(msg)
    return active


def _rewrite_messages(messages: List[Dict[str, Any]]) -> None:
    """Rewrite the messages file (used for clearing)."""
    path = _messages_file_path()
    tmp = path.with_suffix(".tmp")
    with open(tmp, 'w', encoding='utf-8') as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")
    tmp.replace(path)


# -----------------------------------------------------------------------------
# Helper: Emit Marquee Alert (for use by other modules)
# -----------------------------------------------------------------------------

def emit_marquee_alert(
    severity: str,
    text: str,
    source: Optional[str] = None,
    ttl_seconds: int = 60
) -> Dict[str, Any]:
    """
    Helper function to emit a marquee alert from any module.
    
    Args:
        severity: 'info', 'warn', or 'error'
        text: Alert message text
        source: Optional source module name
        ttl_seconds: Time-to-live (default 60 seconds)
    
    Returns:
        The created message entry
        
    Example:
        from backend.routers.marquee import emit_marquee_alert
        emit_marquee_alert("error", "Controller disconnected!", source="led_blinky")
    """
    now = datetime.now(timezone.utc)
    msg = {
        "id": str(uuid.uuid4())[:8],
        "text": text,
        "type": "alert",
        "severity": severity,
        "source": source,
        "sticky": False,
        "created_at": now.isoformat(),
        "expires_at": (now.replace(microsecond=0) + 
                      __import__('datetime').timedelta(seconds=ttl_seconds)).isoformat() if ttl_seconds else None
    }
    
    try:
        _append_message(msg)
        _log_marquee_event("alert_emitted", {"severity": severity, "source": source, "text": text[:50]})
    except Exception as e:
        _msg_logger.warning(f"Failed to emit marquee alert: {e}")
    
    return msg


def emit_marquee_message(
    text: str,
    source: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
    sticky: bool = False
) -> Dict[str, Any]:
    """
    Helper function to emit a marquee message from any module.
    
    Args:
        text: Message text
        source: Optional source module name
        ttl_seconds: Optional time-to-live
        sticky: If True, persists until manually cleared
    
    Returns:
        The created message entry
    """
    now = datetime.now(timezone.utc)
    expires_at = None
    if ttl_seconds:
        expires_at = (now.replace(microsecond=0) + 
                     __import__('datetime').timedelta(seconds=ttl_seconds)).isoformat()
    
    msg = {
        "id": str(uuid.uuid4())[:8],
        "text": text,
        "type": "message",
        "severity": None,
        "source": source,
        "sticky": sticky,
        "created_at": now.isoformat(),
        "expires_at": expires_at
    }
    
    try:
        _append_message(msg)
        _log_marquee_event("message_emitted", {"source": source, "text": text[:50], "sticky": sticky})
    except Exception as e:
        _msg_logger.warning(f"Failed to emit marquee message: {e}")
    
    return msg


# -----------------------------------------------------------------------------
# Message Queue Endpoints
# -----------------------------------------------------------------------------

def _require_scope(request: Request, allowed: List[str]) -> str:
    """Require x-scope header for mutating operations."""
    scope = request.headers.get("x-scope")
    if not scope:
        raise HTTPException(status_code=400, detail=f"Missing x-scope header. Allowed: {allowed}")
    if scope not in allowed:
        raise HTTPException(status_code=400, detail=f"x-scope '{scope}' not permitted. Allowed: {allowed}")
    return scope


@router.post("/messages")
async def post_message(request: Request, payload: MarqueeMessagePayload):
    """
    Post a new message or alert to the marquee queue.
    
    Requires x-scope: state header.
    """
    _require_scope(request, ["state"])
    
    now = datetime.now(timezone.utc)
    
    # Calculate expiration
    expires_at = None
    if payload.ttl_seconds:
        from datetime import timedelta
        expires_at = (now.replace(microsecond=0) + timedelta(seconds=payload.ttl_seconds)).isoformat()
    
    msg = {
        "id": str(uuid.uuid4())[:8],
        "text": payload.text,
        "type": payload.type,
        "severity": payload.severity,
        "source": payload.source,
        "sticky": payload.sticky,
        "created_at": now.isoformat(),
        "expires_at": expires_at
    }
    
    try:
        _append_message(msg)
        _log_marquee_event("message_posted", {
            "id": msg["id"],
            "type": payload.type,
            "severity": payload.severity,
            "source": payload.source
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to post message: {e}")
    
    return {"ok": True, "message": msg}


@router.get("/messages")
async def get_messages(
    request: Request,
    since: Optional[str] = Query(None, description="Timestamp to filter messages created after"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of messages to return"),
    include_expired: bool = Query(False, description="Include expired messages")
):
    """
    Get recent messages from the marquee queue.
    
    Returns active (non-expired) messages by default, newest first.
    Supports filtering by timestamp and limiting results.
    """
    now = datetime.now(timezone.utc)
    all_messages = _read_all_messages()
    
    # Filter expired unless requested
    if not include_expired:
        all_messages = _filter_active_messages(all_messages, now)
    
    # Filter by 'since' timestamp
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            all_messages = [
                m for m in all_messages
                if datetime.fromisoformat(m["created_at"].replace("Z", "+00:00")) > since_dt
            ]
        except Exception:
            pass  # Ignore invalid since parameter
    
    # Sort by created_at descending (newest first)
    all_messages.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    
    # Apply limit
    messages = all_messages[:limit]
    
    # Separate alerts with error/warn severity for priority display
    priority_alerts = [m for m in messages if m.get("type") == "alert" and m.get("severity") in ("error", "warn")]
    
    return {
        "ok": True,
        "count": len(messages),
        "priority_alerts": priority_alerts,
        "messages": messages,
        "timestamp": now.isoformat()
    }


@router.post("/messages/clear")
async def clear_messages(
    request: Request,
    clear_sticky: bool = Query(False, description="Also clear sticky messages")
):
    """
    Clear non-sticky and expired messages from the queue.
    
    Requires x-scope: state header.
    By default, sticky messages are preserved. Use clear_sticky=true to remove all.
    """
    _require_scope(request, ["state"])
    
    now = datetime.now(timezone.utc)
    all_messages = _read_all_messages()
    
    if clear_sticky:
        # Clear everything
        remaining = []
    else:
        # Keep only sticky non-expired messages
        remaining = [
            m for m in all_messages
            if m.get("sticky") and not (
                m.get("expires_at") and 
                datetime.fromisoformat(m["expires_at"].replace("Z", "+00:00")) < now
            )
        ]
    
    cleared_count = len(all_messages) - len(remaining)
    
    try:
        _rewrite_messages(remaining)
        _log_marquee_event("messages_cleared", {"cleared_count": cleared_count, "remaining": len(remaining)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear messages: {e}")
    
    return {
        "ok": True,
        "cleared": cleared_count,
        "remaining": len(remaining)
    }


# =============================================================================
# MARQUEE MEDIA SYSTEM
# =============================================================================
# Media settings and now-playing tracking for Marquee display.
# Storage: .aa/state/marquee/media_settings.json, .aa/state/now_playing.json(l)
# Log: .aa/logs/marquee/events.jsonl (reuses existing)

# -----------------------------------------------------------------------------
# Media Settings File Paths
# -----------------------------------------------------------------------------

def _media_settings_path() -> Path:
    """Get media settings file path under .aa/state/marquee/."""
    aa_root = _get_aa_root()
    path = aa_root / "state" / "marquee" / "media_settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _now_playing_json_path() -> Path:
    """Get current now_playing snapshot path (.aa/state/now_playing.json)."""
    aa_root = _get_aa_root()
    path = aa_root / "state" / "now_playing.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _now_playing_jsonl_path() -> Path:
    """Get now_playing history log path (.aa/state/now_playing.jsonl)."""
    aa_root = _get_aa_root()
    path = aa_root / "state" / "now_playing.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# -----------------------------------------------------------------------------
# Media Settings Models
# -----------------------------------------------------------------------------

class MediaSettingsPayload(BaseModel):
    """Payload for media settings configuration."""
    image_dir: Optional[str] = Field(None, description="Custom image directory path")
    video_dir: Optional[str] = Field(None, description="Custom video directory path")
    idle_image: Optional[str] = Field(None, description="Path to idle/default image")
    idle_video: Optional[str] = Field(None, description="Path to idle/default video")
    cycle_ms: int = Field(5000, ge=1000, le=60000, description="Still image display time before video (ms)")
    prefer_video: bool = Field(True, description="Prefer video over still if both available")


class NowPlayingPayload(BaseModel):
    """Payload for now-playing updates."""
    game_id: Optional[str] = Field(None, description="Game ID")
    game_title: str = Field(..., description="Game title (required)")
    platform: Optional[str] = Field(None, description="Platform name")
    system: Optional[str] = Field(None, description="System name (alias for platform)")
    region: str = Field("North America", description="Region")
    image: Optional[str] = Field(None, description="Override image URL")
    video: Optional[str] = Field(None, description="Override video URL")
    source: Optional[str] = Field(None, description="Source of the update (frontend, launchbox, etc.)")


class ResolvePayload(BaseModel):
    """Payload for media resolve requests."""
    game_id: Optional[str] = Field(None, description="Game ID to resolve")
    title: Optional[str] = Field(None, description="Game title to resolve")
    platform: str = Field("Arcade", description="Platform name")
    region: str = Field("North America", description="Region for artwork lookup")
    prefer_video: bool = Field(True, description="Prefer video over still if available")


# -----------------------------------------------------------------------------
# Media Settings Functions
# -----------------------------------------------------------------------------

def _load_media_settings() -> Dict[str, Any]:
    """Load media settings from JSON file."""
    path = _media_settings_path()
    if not path.exists():
        return {
            "image_dir": None,
            "video_dir": None,
            "idle_image": None,
            "idle_video": None,
            "cycle_ms": 5000,
            "prefer_video": True
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "image_dir": None,
            "video_dir": None,
            "idle_image": None,
            "idle_video": None,
            "cycle_ms": 5000,
            "prefer_video": True
        }


def _save_media_settings(settings: Dict[str, Any]) -> None:
    """Save media settings to JSON file."""
    path = _media_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    tmp.replace(path)


def _load_now_playing() -> Dict[str, Any]:
    """Load current now_playing snapshot."""
    path = _now_playing_json_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_now_playing(data: Dict[str, Any]) -> None:
    """Save current now_playing snapshot and append to history."""
    # Save snapshot
    json_path = _now_playing_json_path()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = json_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(json_path)
    
    # Append to history log
    jsonl_path = _now_playing_jsonl_path()
    with open(jsonl_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(data) + "\n")


def _log_marquee_event_with_identity(
    request: Request,
    event_type: str,
    details: Dict[str, Any]
) -> None:
    """Log a marquee event with device_id and frontend_source."""
    try:
        device_id = request.headers.get("x-device-id", "")
        frontend_source = request.headers.get("x-panel", "")
        
        log_path = _marquee_log_path()
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "device_id": device_id,
            "frontend_source": frontend_source,
            **details
        }
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Best-effort logging


# -----------------------------------------------------------------------------
# Media Settings Endpoints
# -----------------------------------------------------------------------------

@router.get("/media-settings")
async def get_media_settings():
    """
    Get current media settings for Marquee display.
    
    Returns image_dir, video_dir, idle_image, idle_video, cycle_ms, prefer_video.
    """
    settings = _load_media_settings()
    return {"ok": True, "settings": settings}


@router.post("/media-settings")
async def post_media_settings(request: Request, payload: MediaSettingsPayload):
    """
    Save media settings for Marquee display.
    
    Requires x-scope: config header.
    """
    _require_scope(request, ["config"])
    
    settings = payload.model_dump()
    
    try:
        _save_media_settings(settings)
        _log_marquee_event_with_identity(request, "media_settings_updated", {
            "image_dir": settings.get("image_dir"),
            "video_dir": settings.get("video_dir"),
            "cycle_ms": settings.get("cycle_ms")
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save media settings: {e}")
    
    return {"ok": True, "settings": settings}


# -----------------------------------------------------------------------------
# Now Playing Endpoints
# -----------------------------------------------------------------------------

@router.get("/now-playing")
async def get_now_playing():
    """
    Get the currently playing game info for Marquee display.
    
    Returns the last-set now_playing state, or empty if none.
    """
    data = _load_now_playing()
    if not data:
        return {"ok": True, "now_playing": None, "message": "No game currently playing"}
    return {"ok": True, "now_playing": data}


@router.post("/now-playing")
async def post_now_playing(request: Request, payload: NowPlayingPayload):
    """
    Update the currently playing game for Marquee display.
    
    Requires x-scope: state header.
    Appends to .aa/state/now_playing.jsonl and updates .aa/state/now_playing.json.
    Logs event to .aa/logs/marquee/events.jsonl with device_id and frontend_source.
    """
    _require_scope(request, ["state"])
    
    now = datetime.now(timezone.utc)
    
    data = {
        "game_id": payload.game_id,
        "game_title": payload.game_title,
        "platform": payload.platform or payload.system,
        "region": payload.region,
        "image": payload.image,
        "video": payload.video,
        "source": payload.source,
        "updated_at": now.isoformat()
    }
    
    try:
        _save_now_playing(data)
        
        # Also update the legacy current_game state for backward compatibility
        persist_current_game({
            "game_id": payload.game_id or "",
            "title": payload.game_title,
            "platform": payload.platform or payload.system or "Arcade",
            "region": payload.region
        })
        
        _log_marquee_event_with_identity(request, "now_playing", {
            "game_id": payload.game_id,
            "game_title": payload.game_title,
            "platform": payload.platform or payload.system,
            "source": payload.source
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update now_playing: {e}")
    
    return {"ok": True, "now_playing": data}


# -----------------------------------------------------------------------------
# Media Resolve Endpoint
# -----------------------------------------------------------------------------

@router.post("/resolve")
async def resolve_media(request: Request, payload: ResolvePayload):
    """
    Resolve best-match media (image/video) for a given game.
    
    Uses media_settings overrides (image_dir/video_dir) before LaunchBox defaults.
    Returns primary_url, primary_type, all_urls, and fallback_used.
    
    Requires x-scope: state header.
    """
    _require_scope(request, ["state", "local"])
    
    settings = _load_media_settings()
    drive_root = Path(os.environ.get("AA_DRIVE_ROOT", os.getcwd()))
    
    # Determine game name for file matching
    game_title = payload.title
    if not game_title and payload.game_id:
        # Try to look up title from game_id
        try:
            game = parser.get_game_by_id(payload.game_id)
            if game:
                game_title = getattr(game, "title", None)
        except Exception:
            pass
    
    if not game_title:
        return {
            "ok": False,
            "primary_url": None,
            "primary_type": None,
            "fallback_used": "no_title",
            "message": "NO MEDIA FOUND - No game title provided",
            "all_urls": {}
        }
    
    # Normalize game name for file matching
    game_name = game_title.replace(":", "").replace("?", "").replace("*", "").replace("/", "").replace("\\", "")
    platform = payload.platform
    
    # Initialize result
    result = {
        "ok": True,
        "game_id": payload.game_id,
        "game_title": game_title,
        "platform": platform,
        "primary_url": None,
        "primary_type": None,
        "fallback_used": "none",
        "all_urls": {
            "game_video": None,
            "game_image": None,
            "platform_image": None,
            "idle_image": None,
            "idle_video": None
        }
    }
    
    image_extensions = [".png", ".jpg", ".jpeg"]
    video_extensions = [".mp4", ".avi", ".mkv", ".webm"]
    
    # 1. Try custom image_dir from settings
    custom_image_dir = settings.get("image_dir")
    if custom_image_dir:
        custom_path = Path(custom_image_dir)
        if custom_path.exists():
            img_file = _find_media_file(custom_path, game_name, image_extensions)
            if img_file:
                encoded = quote(img_file.as_posix(), safe="/:\\")
                result["all_urls"]["game_image"] = f"/api/local/marquee/serve-media?path={encoded}"
    
    # 2. Try custom video_dir from settings
    custom_video_dir = settings.get("video_dir")
    if custom_video_dir:
        custom_path = Path(custom_video_dir)
        if custom_path.exists():
            vid_file = _find_media_file(custom_path, game_name, video_extensions)
            if vid_file:
                encoded = quote(vid_file.as_posix(), safe="/:\\")
                result["all_urls"]["game_video"] = f"/api/local/marquee/serve-media?path={encoded}"
    
    # 3. Try LaunchBox paths if custom dirs didn't find media
    launchbox_root = drive_root / "LaunchBox"
    
    if not result["all_urls"]["game_video"]:
        videos_dir = launchbox_root / "Videos" / platform
        vid_file = _find_media_file(videos_dir, game_name, video_extensions)
        if vid_file:
            encoded = quote(vid_file.as_posix(), safe="/:\\")
            result["all_urls"]["game_video"] = f"/api/local/marquee/serve-media?path={encoded}"
    
    if not result["all_urls"]["game_image"]:
        images_base = launchbox_root / "Images" / platform
        marquee_dirs = [
            images_base / "Arcade - Marquee",
            images_base / f"{platform} - Marquee",
            images_base / "Marquee",
            images_base / "Banner",
        ]
        regions = ["North America", "World", "Europe", "Japan", ""]
        
        for marquee_dir in marquee_dirs:
            if result["all_urls"]["game_image"]:
                break
            for region in regions:
                search_dir = marquee_dir / region if region else marquee_dir
                img_file = _find_media_file(search_dir, game_name, image_extensions)
                if img_file:
                    encoded = quote(img_file.as_posix(), safe="/:\\")
                    result["all_urls"]["game_image"] = f"/api/local/marquee/serve-media?path={encoded}"
                    break
    
    # 4. Try platform marquee as fallback
    platform_image_file = _find_platform_marquee(launchbox_root, platform)
    if platform_image_file:
        encoded = quote(platform_image_file.as_posix(), safe="/:\\")
        result["all_urls"]["platform_image"] = f"/api/local/marquee/serve-media?path={encoded}"
    
    # 5. Try idle image/video from settings
    idle_image = settings.get("idle_image")
    if idle_image and Path(idle_image).exists():
        encoded = quote(Path(idle_image).as_posix(), safe="/:\\")
        result["all_urls"]["idle_image"] = f"/api/local/marquee/serve-media?path={encoded}"
    else:
        # Try default idle locations
        idle_file = _find_default_idle_art(launchbox_root)
        if idle_file:
            encoded = quote(idle_file.as_posix(), safe="/:\\")
            result["all_urls"]["idle_image"] = f"/api/local/marquee/serve-media?path={encoded}"
    
    idle_video = settings.get("idle_video")
    if idle_video and Path(idle_video).exists():
        encoded = quote(Path(idle_video).as_posix(), safe="/:\\")
        result["all_urls"]["idle_video"] = f"/api/local/marquee/serve-media?path={encoded}"
    
    # Determine primary based on priority
    prefer_video = payload.prefer_video if payload.prefer_video is not None else settings.get("prefer_video", True)
    
    if prefer_video and result["all_urls"]["game_video"]:
        result["primary_url"] = result["all_urls"]["game_video"]
        result["primary_type"] = "video"
        result["fallback_used"] = "none"
    elif result["all_urls"]["game_image"]:
        result["primary_url"] = result["all_urls"]["game_image"]
        result["primary_type"] = "image"
        result["fallback_used"] = "none" if not prefer_video else "game_image"
    elif result["all_urls"]["platform_image"]:
        result["primary_url"] = result["all_urls"]["platform_image"]
        result["primary_type"] = "image"
        result["fallback_used"] = "platform_image"
    elif result["all_urls"]["idle_image"]:
        result["primary_url"] = result["all_urls"]["idle_image"]
        result["primary_type"] = "idle"
        result["fallback_used"] = "idle_image"
    elif result["all_urls"]["idle_video"]:
        result["primary_url"] = result["all_urls"]["idle_video"]
        result["primary_type"] = "idle_video"
        result["fallback_used"] = "idle_video"
    else:
        result["ok"] = False
        result["fallback_used"] = "no_media_found"
        result["message"] = "NO MEDIA FOUND"
    
    # Log the resolve attempt
    _log_marquee_event_with_identity(request, "media_resolved", {
        "game_id": payload.game_id,
        "game_title": game_title,
        "platform": platform,
        "primary_type": result["primary_type"],
        "fallback_used": result["fallback_used"]
    })
    
    return result
