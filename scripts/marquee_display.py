#!/usr/bin/env python3
"""
Marquee Display - Python Desktop Application
=============================================
A lightweight marquee display for arcade cabinets.
Displays game marquee images and videos on a secondary monitor.

Features:
- Watches state/marquee_current.json for game changes
- Resolves media from LaunchBox folders
- Displays images, plays videos, then loops
- Runs as borderless fullscreen on target monitor
- Never steals focus from games

Usage:
    python marquee_display.py [--monitor 1] [--config path/to/config.json]

This script is designed to run on Windows. It uses tkinter for the
window and optional OpenCV+Pillow for video/image rendering. If those
libraries are missing, video playback will be skipped and a warning
will be logged.
"""

import ctypes
import json
import logging
import msvcrt
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, Thread
from typing import Any, Dict, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.models.marquee_config import MarqueeConfig as SharedMarqueeConfig
from backend.models.marquee_config import MarqueeState as SharedMarqueeState

# Watchdog for file monitoring
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    print("WARNING: watchdog not installed. Install with: pip install watchdog")

# GUI / media libs
try:
    import tkinter as tk
    TK_AVAILABLE = True
except ImportError:
    TK_AVAILABLE = False
    tk = None
    print("WARNING: tkinter not available; display window cannot be created")

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("WARNING: Pillow not installed. Install with: pip install pillow")

try:
    import cv2  # OpenCV for video
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("WARNING: OpenCV not installed. Video playback disabled. Install with: pip install opencv-python")

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

@dataclass
class MarqueeConfig:
    """Configuration for the marquee display."""
    # Display settings
    target_monitor: int = 1  # 0 = primary, 1 = secondary, etc.
    fullscreen: bool = True
    window_width: int = 1920
    window_height: int = 360  # Typical marquee aspect ratio
    
    # Paths
    launchbox_root: Path = field(default_factory=lambda: Path(os.environ.get("AA_DRIVE_ROOT", "A:\\")) / "LaunchBox")
    state_file: Path = field(default_factory=lambda: Path(os.environ.get("AA_DRIVE_ROOT", "A:\\")) / ".aa" / "state" / "marquee_current.json")
    preview_file: Path = field(default_factory=lambda: Path(os.environ.get("AA_DRIVE_ROOT", "A:\\")) / ".aa" / "state" / "marquee_preview.json")
    idle_image: Optional[Path] = None  # Shown when no game selected
    idle_video: Optional[Path] = None  # Loop when no game is active
    
    # Timing
    image_display_seconds: float = 3.0  # Show image before video starts (for "video" mode)
    scroll_debounce_ms: int = 150  # Debounce rapid scroll changes
    video_loop: bool = True  # Loop video or play once then show image
    poll_interval_ms: int = 500  # Fallback polling if watchdog fails
    
    # Behavior
    prefer_video: bool = True  # If both exist, show video (only in "video" mode)
    fallback_to_platform_image: bool = True  # Use platform image if game image not found
    
    # Mode behavior
    # "image" mode: Show image immediately (fast, for scrolling)
    # "video" mode: Show image briefly, then play video, then loop back to image


def load_config(config_path: Optional[Path] = None) -> MarqueeConfig:
    """Load configuration from JSON file or use defaults."""
    config = MarqueeConfig()
    
    if config_path and config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            parsed = SharedMarqueeConfig.model_validate(data)
            config.target_monitor = int(parsed.target_monitor_index)
            config.fullscreen = bool(parsed.fullscreen)
            config.window_width = int(parsed.window_width)
            config.window_height = int(parsed.window_height)
            if parsed.launchbox_root:
                config.launchbox_root = Path(parsed.launchbox_root)
            if parsed.state_file:
                config.state_file = Path(parsed.state_file)
            if parsed.preview_file:
                config.preview_file = Path(parsed.preview_file)
            if parsed.idle_image:
                config.idle_image = Path(parsed.idle_image)
            if parsed.idle_video:
                config.idle_video = Path(parsed.idle_video)
            config.image_display_seconds = float(parsed.image_display_seconds)
            config.scroll_debounce_ms = int(parsed.scroll_debounce_ms)
            config.video_loop = bool(parsed.video_loop)
            config.poll_interval_ms = int(parsed.poll_interval_ms)
            config.prefer_video = bool(parsed.prefer_video)
            config.fallback_to_platform_image = bool(parsed.fallback_to_platform_image)
                
            logging.info(f"Loaded config from {config_path}")
        except Exception as e:
            logging.warning(f"Failed to load config from {config_path}: {e}")
    
    return config


# -----------------------------------------------------------------------------
# Monitor helpers (Windows)
# -----------------------------------------------------------------------------

def list_monitors() -> list:
    """
    Return a list of monitor bounds as (left, top, right, bottom).
    Falls back to the primary display if enumeration fails.
    """
    monitors = []
    user32 = ctypes.windll.user32

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long)]

    MONITORENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.POINTER(RECT), ctypes.c_double)

    def _callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
        r = lprcMonitor.contents
        monitors.append((r.left, r.top, r.right, r.bottom))
        return 1

    try:
        user32.EnumDisplayMonitors(0, 0, MONITORENUMPROC(_callback), 0)
    except Exception:
        pass

    # Fallback to primary
    if not monitors:
        try:
            w = user32.GetSystemMetrics(0)
            h = user32.GetSystemMetrics(1)
            monitors.append((0, 0, w, h))
        except Exception:
            monitors.append((0, 0, 1920, 1080))
    return monitors


def monitor_bounds(index: int) -> Tuple[int, int, int, int]:
    mons = list_monitors()
    if index < 0 or index >= len(mons):
        index = 0
    return mons[index]


# -----------------------------------------------------------------------------
# Media Resolution
# -----------------------------------------------------------------------------

def find_media_file(directory: Path, game_name: str, extensions: list) -> Optional[Path]:
    """
    Find a media file matching the game name in the given directory.
    Uses case-insensitive prefix matching.
    """
    if not directory.exists():
        return None
    
    # Clean game name for matching
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


def resolve_game_media(config: MarqueeConfig, title: str, platform: str) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Resolve video and image paths for a game.
    
    Returns:
        (video_path, image_path) - Either can be None if not found
    """
    video_path = None
    image_path = None
    
    # Clean title for filename matching
    clean_title = title.replace(":", "").replace("?", "").replace("*", "").replace("/", "").replace("\\", "").replace('"', "")
    
    # --- Video Resolution ---
    videos_dir = config.launchbox_root / "Videos" / platform
    video_path = find_media_file(videos_dir, clean_title, [".mp4", ".avi", ".mkv", ".webm"])
    
    # --- Image Resolution ---
    # Try multiple marquee folder locations
    images_base = config.launchbox_root / "Images" / platform
    marquee_dirs = [
        images_base / "Arcade - Marquee",
        images_base / f"{platform} - Marquee",
        images_base / "Marquee",
        images_base / "Banner",  # Some setups use Banner
    ]
    
    # Also check region subfolders
    regions = ["North America", "World", "Europe", "Japan", ""]
    image_extensions = [".png", ".jpg", ".jpeg"]
    
    for marquee_dir in marquee_dirs:
        if image_path:
            break
        for region in regions:
            search_dir = marquee_dir / region if region else marquee_dir
            image_path = find_media_file(search_dir, clean_title, image_extensions)
            if image_path:
                break
    
    # Fallback to platform image if configured
    if not image_path and config.fallback_to_platform_image:
        platform_image = images_base / "Platform" / f"{platform}.png"
        if platform_image.exists():
            image_path = platform_image
    
    return video_path, image_path


# -----------------------------------------------------------------------------
# State Management
# -----------------------------------------------------------------------------

@dataclass
class GameState:
    """Current game state from the state file."""
    game_id: Optional[str] = None
    title: Optional[str] = None
    platform: Optional[str] = None
    region: str = "North America"
    mode: str = "image"  # "image" for scroll preview, "video" for launched
    event_type: Optional[str] = None
    
    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'GameState':
        state = SharedMarqueeState.model_validate(data)
        return cls(
            game_id=state.game_id,
            title=state.title,
            platform=state.platform,
            region=state.region,
            mode=state.mode,
            event_type=state.event_type,
        )
    
    def is_valid(self) -> bool:
        return bool(self.title and self.platform)

    def normalized_event_type(self) -> str:
        value = (self.event_type or "GAME").upper()
        return "GAME" if value not in {"GAME", "IDLE"} else value


def load_game_state(state_file: Path) -> Optional[GameState]:
    """Load current game state from JSON file."""
    if not state_file.exists():
        return None
    
    try:
        with open(state_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return GameState.from_json(data)
    except Exception as e:
        logging.warning(f"Failed to load game state: {e}")
        return None


class SingleInstanceLock:
    """Best-effort single-instance guard using a lock file."""

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self._handle = None

    def acquire(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(self.lock_path, "a+b")
        try:
            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            self._handle.seek(0)
            self._handle.truncate()
            self._handle.write(str(os.getpid()).encode("utf-8"))
            self._handle.flush()
            return True
        except OSError:
            try:
                self._handle.close()
            except Exception:
                pass
            self._handle = None
            return False

    def release(self) -> None:
        if not self._handle:
            return
        try:
            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        try:
            self._handle.close()
        except Exception:
            pass
        self._handle = None


# -----------------------------------------------------------------------------
# File Watcher
# -----------------------------------------------------------------------------

class WatchedFileHandler(FileSystemEventHandler):
    """Watches a single file for changes."""

    def __init__(self, watched_file: Path, callback):
        super().__init__()
        self.watched_file = watched_file
        self.callback = callback
        self.last_modified = 0

    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent):
            if Path(event.src_path).resolve() == self.watched_file.resolve():
                now = time.time()
                if now - self.last_modified > 0.3:
                    self.last_modified = now
                    logging.debug("Watched file changed: %s", self.watched_file)
                    self.callback()

    def on_created(self, event):
        self.on_modified(event)


def start_file_watchers(watches: list[Tuple[Path, Any]]) -> Optional[Observer]:
    """Start watchdog observers for one or more files."""
    if not WATCHDOG_AVAILABLE:
        return None

    try:
        observer = Observer()
        for watched_file, callback in watches:
            if not watched_file:
                continue
            handler = WatchedFileHandler(watched_file, callback)
            observer.schedule(handler, str(watched_file.parent), recursive=False)
        observer.start()
        logging.info("File watcher started for %s", ", ".join(str(path) for path, _ in watches if path))
        return observer
    except Exception as e:
        logging.error("Failed to start file watcher: %s", e)
        return None


# -----------------------------------------------------------------------------
# Display Controller (PLACEHOLDER - NEEDS CODEX)
# -----------------------------------------------------------------------------

class MarqueeDisplay:
    """
    Controls the marquee display window.
    """
    
    def __init__(self, config: MarqueeConfig):
        self.config = config
        self.running = False
        self.current_state: Optional[GameState] = None
        self.current_preview: Optional[GameState] = None
        self.current_video: Optional[Path] = None
        self.current_image: Optional[Path] = None
        self._stop_event = Event()
        self._video_thread: Optional[Thread] = None
        self._video_stop = Event()
        self._preview_active = False
        self._media_generation = 0

        # Tkinter elements
        self.root: Optional["tk.Tk"] = None
        self.canvas: Optional["tk.Canvas"] = None
        self._photo_ref = None  # prevent GC
        self._hwnd: Optional[int] = None
        self._monitor_bounds: Tuple[int, int, int, int] = (0, 0, 1920, 1080)

    def _bump_media_generation(self) -> int:
        self._media_generation += 1
        return self._media_generation

    def _apply_preview_overlay(self, target_w: int, target_h: int) -> None:
        if not self.canvas or not self._preview_active:
            return
        padding = 16
        self.canvas.create_rectangle(
            padding,
            padding,
            target_w - padding,
            target_h - padding,
            outline="#c8ff00",
            width=3,
        )
        self.canvas.create_text(
            target_w - 28,
            28,
            text="PREVIEW",
            anchor="ne",
            fill="#c8ff00",
            font=("Segoe UI", 16, "bold"),
        )
    
    def initialize(self) -> bool:
        """
        Initialize the display window.
        """
        if not TK_AVAILABLE:
            logging.error("tkinter not available; cannot initialize display window.")
            return False

        self._monitor_bounds = monitor_bounds(self.config.target_monitor)
        left, top, right, bottom = self._monitor_bounds
        width = right - left
        height = bottom - top

        logging.info(f"Initializing display on monitor {self.config.target_monitor} ({width}x{height} @ {left},{top})")

        try:
            self.root = tk.Tk()
            self.root.configure(background="black")
            self.root.overrideredirect(True)  # borderless
            self.root.attributes("-topmost", True)
            self.root.geometry(f"{width}x{height}+{left}+{top}")

            # Prevent focus steal using extended window styles
            self.root.update_idletasks()
            hwnd = self.root.winfo_id()
            self._hwnd = hwnd
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_LAYERED = 0x00080000
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            # Ensure topmost without activation
            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

            # Canvas for drawing media
            self.canvas = tk.Canvas(self.root, width=width, height=height, highlightthickness=0, bg="black")
            self.canvas.pack(fill="both", expand=True)
        except Exception as exc:
            logging.error(f"Failed to initialize display: {exc}")
            return False

        return True
    
    def show_idle(self):
        """Show idle screen (no game selected)."""
        logging.info("Showing idle screen")
        self._bump_media_generation()
        self.current_state = None
        self.current_preview = None
        self._preview_active = False
        self.stop_video()
        if self.config.idle_video and self.config.idle_video.exists():
            self.play_video(self.config.idle_video, loop=True, preview=False)
            return
        if self.config.idle_image and self.config.idle_image.exists():
            self.show_image(self.config.idle_image, preview=False)
            return
        if self.canvas:
            self.canvas.delete("all")
            self.canvas.configure(bg="black")
    
    def show_image(self, image_path: Path, preview: bool = False):
        """Display a static image."""
        logging.info(f"Showing image: {image_path}")
        self.current_image = image_path
        self._preview_active = preview
        self.stop_video()

        if not (PIL_AVAILABLE and self.canvas and self.root):
            logging.warning("Pillow or tkinter not available; cannot display image.")
            return

        if not image_path.exists():
            logging.warning("Image not found: %s", image_path)
            return

        try:
            img = Image.open(image_path)
        except Exception as exc:
            logging.warning(f"Failed to open image {image_path}: {exc}")
            return

        # Scale to fit while preserving aspect ratio
        left, top, right, bottom = self._monitor_bounds
        target_w = right - left
        target_h = bottom - top
        img_ratio = img.width / img.height
        target_ratio = target_w / target_h
        if img_ratio > target_ratio:
            new_w = target_w
            new_h = int(target_w / img_ratio)
        else:
            new_h = target_h
            new_w = int(target_h * img_ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)

        photo = ImageTk.PhotoImage(img)
        self._photo_ref = photo  # prevent GC
        self.canvas.delete("all")
        self.canvas.configure(bg="black")
        self.canvas.create_image(target_w // 2, target_h // 2, image=photo, anchor="center")
        self._apply_preview_overlay(target_w, target_h)
    
    def play_video(self, video_path: Path, loop: bool = True, preview: bool = False):
        """Play a video file."""
        logging.info(f"Playing video: {video_path} (loop={loop})")
        self.current_video = video_path
        self._preview_active = preview
        if not CV2_AVAILABLE:
            logging.warning("OpenCV not available; cannot play video.")
            return
        if not video_path.exists():
            logging.warning("Video not found: %s", video_path)
            return

        # Stop previous playback
        self.stop_video()
        self._video_stop.clear()

        def _video_loop():
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                logging.warning("Failed to open video: %s", video_path)
                return
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            delay = max(1, int(1000 / fps))
            left, top, right, bottom = self._monitor_bounds
            target_w = right - left
            target_h = bottom - top

            while not self._video_stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    if loop:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    break
                # Convert BGR to RGB
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(frame)
                # Scale to fit
                img_ratio = pil_img.width / pil_img.height
                target_ratio = target_w / target_h
                if img_ratio > target_ratio:
                    new_w = target_w
                    new_h = int(target_w / img_ratio)
                else:
                    new_h = target_h
                    new_w = int(target_h * img_ratio)
                pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)

                if self.root and self.canvas:
                    photo = ImageTk.PhotoImage(pil_img)
                    self._photo_ref = photo
                    # UI updates must run on main thread
                    def _render():
                        if self.canvas:
                            self.canvas.delete("all")
                            self.canvas.create_image(target_w // 2, target_h // 2, image=photo, anchor="center")
                            self._apply_preview_overlay(target_w, target_h)
                    try:
                        self.root.after(0, _render)
                    except Exception:
                        pass

                # Sleep per frame
                time.sleep(delay / 1000.0)
            cap.release()

        self._video_thread = Thread(target=_video_loop, daemon=True)
        self._video_thread.start()
    
    def stop_video(self):
        """Stop any playing video."""
        logging.info("Stopping video")
        self.current_video = None
        if self._video_thread and self._video_thread.is_alive():
            self._video_stop.set()
            self._video_thread.join(timeout=1.0)
        self._video_thread = None
        self._video_stop.clear()
    
    def update_game(self, state: GameState):
        """Update display for a new game."""
        if not state.is_valid():
            self.show_idle()
            return
        generation = self._bump_media_generation()
        self.current_state = state
        self.current_preview = None
        self._preview_active = False
        
        # Resolve media
        video_path, image_path = resolve_game_media(
            self.config, 
            state.title, 
            state.platform
        )
        
        logging.info(f"Game: {state.title} | Video: {video_path} | Image: {image_path}")
        
        # Display logic: show image first, then video
        if image_path:
            self.show_image(image_path, preview=False)
        
        if video_path and self.config.prefer_video:
            # After image_display_seconds, switch to video
            def _start_video():
                if not self._stop_event.is_set() and generation == self._media_generation:
                    self.play_video(video_path, loop=self.config.video_loop, preview=False)
            if self.root:
                self.root.after(int(self.config.image_display_seconds * 1000), _start_video)
            else:
                _start_video()
        elif not image_path:
            self.show_idle()

    def show_preview(self, state: GameState):
        """Render a preview state without overriding an active game."""
        if not state.is_valid():
            return

        generation = self._bump_media_generation()
        self.current_preview = state
        self._preview_active = True

        video_path, image_path = resolve_game_media(
            self.config,
            state.title,
            state.platform,
        )

        logging.info(f"Preview: {state.title} | Video: {video_path} | Image: {image_path}")

        if image_path:
            self.show_image(image_path, preview=True)

        if video_path and self.config.prefer_video and state.mode == "video":
            def _start_video():
                if not self._stop_event.is_set() and generation == self._media_generation:
                    self.play_video(video_path, loop=self.config.video_loop, preview=True)
            if self.root:
                self.root.after(int(self.config.image_display_seconds * 1000), _start_video)
            else:
                _start_video()
        elif not image_path and video_path:
            self.play_video(video_path, loop=self.config.video_loop, preview=True)
    
    def run(self):
        """Main display loop."""
        self.running = True
        logging.info("Marquee display starting...")
        if not self.root:
            logging.error("Display not initialized; call initialize() first.")
            return

        while self.running and not self._stop_event.is_set():
            try:
                self.root.update_idletasks()
                self.root.update()
            except Exception:
                break
            time.sleep(0.01)
    
    def stop(self):
        """Stop the display."""
        self.running = False
        self._stop_event.set()
        self.stop_video()
        try:
            if self.root:
                self.root.destroy()
        except Exception:
            pass
        logging.info("Marquee display stopped")


# -----------------------------------------------------------------------------
# Main Application
# -----------------------------------------------------------------------------

class MarqueeApp:
    """Main application controller."""
    
    def __init__(self, config: MarqueeConfig):
        self.config = config
        self.display = MarqueeDisplay(config)
        self.observer: Optional[Observer] = None
        self.running = False
        self._last_state: Optional[GameState] = None
        self._last_preview_state: Optional[GameState] = None
        self._poll_thread: Optional[Thread] = None
        self._poll_stop = Event()
        self._state_mtime: Optional[float] = None
        self._preview_mtime: Optional[float] = None

    def _is_active_game(self) -> bool:
        return bool(
            self._last_state
            and self._last_state.is_valid()
            and self._last_state.normalized_event_type() == "GAME"
        )

    def _restore_current_display(self) -> None:
        if self._is_active_game():
            self.display.update_game(self._last_state)
        elif self._last_preview_state and self._last_preview_state.is_valid():
            self.display.show_preview(self._last_preview_state)
        else:
            self.display.show_idle()

    def on_state_change(self):
        """Called when the state file changes."""
        state = load_game_state(self.config.state_file)

        if not state:
            if self._last_state:
                logging.info("No game selected, showing idle")
                self._last_state = None
            self._restore_current_display()
            return

        event_type = state.normalized_event_type()
        if event_type == "IDLE" or not state.is_valid():
            logging.info("Idle marquee event received")
            self._last_state = None
            self._restore_current_display()
            return

        state_changed = (
            not self._last_state
            or state.game_id != self._last_state.game_id
            or state.title != self._last_state.title
            or state.platform != self._last_state.platform
            or state.mode != self._last_state.mode
            or state.normalized_event_type() != self._last_state.normalized_event_type()
        )
        if state_changed:
            logging.info(f"Game changed: {state.title} ({state.platform})")
            self._last_state = state
            self.display.update_game(state)

    def on_preview_change(self):
        """Called when the preview file changes."""
        if not self.config.preview_file:
            return

        state = load_game_state(self.config.preview_file)

        if not state or not state.is_valid():
            if self._last_preview_state:
                logging.info("Preview cleared, restoring current display")
            self._last_preview_state = None
            self._restore_current_display()
            return

        self._last_preview_state = state

        if self._is_active_game():
            logging.info("Preview change ignored because a game is actively playing")
            return

        logging.info(f"Preview changed: {state.title} ({state.platform})")
        self.display.show_preview(state)

    def _file_mtime(self, path: Optional[Path]) -> Optional[float]:
        if not path:
            return None
        try:
            return path.stat().st_mtime
        except OSError:
            return None

    def _start_polling_fallback(self) -> None:
        interval = max(100, int(self.config.poll_interval_ms)) / 1000.0
        logging.warning(
            "[MarqueeDisplay] Watchdog unavailable — using polling fallback at %sms",
            self.config.poll_interval_ms,
        )
        self._state_mtime = self._file_mtime(self.config.state_file)
        self._preview_mtime = self._file_mtime(self.config.preview_file)
        self._poll_stop.clear()

        def _poll_loop():
            while not self._poll_stop.wait(interval):
                new_state_mtime = self._file_mtime(self.config.state_file)
                if new_state_mtime != self._state_mtime:
                    self._state_mtime = new_state_mtime
                    self.on_state_change()

                if self.config.preview_file:
                    new_preview_mtime = self._file_mtime(self.config.preview_file)
                    if new_preview_mtime != self._preview_mtime:
                        self._preview_mtime = new_preview_mtime
                        self.on_preview_change()

        self._poll_thread = Thread(target=_poll_loop, name="marquee-poll", daemon=True)
        self._poll_thread.start()
    
    def run(self):
        """Run the marquee application."""
        logging.info("=" * 50)
        logging.info("Marquee Display Starting")
        logging.info("=" * 50)
        logging.info(f"Config: Monitor {self.config.target_monitor}, "
                    f"LaunchBox: {self.config.launchbox_root}")
        logging.info(f"State file: {self.config.state_file}")
        logging.info(f"Preview file: {self.config.preview_file}")
        
        # Ensure state directory exists
        self.config.state_file.parent.mkdir(parents=True, exist_ok=True)
        if self.config.preview_file:
            self.config.preview_file.parent.mkdir(parents=True, exist_ok=True)
        else:
            logging.info("[MarqueeDisplay] Preview file not configured — preview watching skipped")
        
        # Initialize display
        if not self.display.initialize():
            logging.error("Failed to initialize display")
            return
        
        # Start file watcher
        watches = [(self.config.state_file, self.on_state_change)]
        if self.config.preview_file:
            watches.append((self.config.preview_file, self.on_preview_change))
        self.observer = start_file_watchers(watches)
        if not self.observer:
            self._start_polling_fallback()
        
        # Load initial state
        self.on_state_change()
        if self.config.preview_file:
            self.on_preview_change()
        
        self.running = True
        
        try:
            # Run display loop
            self.display.run()
        except KeyboardInterrupt:
            logging.info("Interrupted by user")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the application."""
        self.running = False
        
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=2)
        self._poll_stop.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2)
        
        self.display.stop()
        logging.info("Marquee Display stopped")


# -----------------------------------------------------------------------------
# Entry Point
# -----------------------------------------------------------------------------

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Arcade Marquee Display")
    parser.add_argument("--monitor", type=int, default=1, 
                       help="Target monitor index (0=primary, 1=secondary, ...)")
    parser.add_argument("--config", type=str, default=None,
                       help="Path to config JSON file")
    parser.add_argument("--debug", action="store_true",
                       help="Enable debug logging")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S"
    )

    lock: Optional[SingleInstanceLock] = None
    single_instance_enabled = os.environ.get("AA_MARQUEE_SINGLE_INSTANCE", "1") != "0"
    if single_instance_enabled:
        drive_root = Path(os.environ.get("AA_DRIVE_ROOT", "A:\\"))
        lock = SingleInstanceLock(drive_root / ".aa" / "marquee.lock")
        if not lock.acquire():
            logging.info("[MarqueeDisplay] Already running — exiting")
            sys.exit(0)
    
    try:
        # Load config
        config_path = Path(args.config) if args.config else None
        config = load_config(config_path)
        config.target_monitor = args.monitor

        # Run app
        app = MarqueeApp(config)
        app.run()
    finally:
        if lock:
            lock.release()


if __name__ == "__main__":
    main()
