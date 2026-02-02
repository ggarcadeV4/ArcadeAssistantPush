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
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, Thread
from typing import Any, Dict, Optional, Tuple

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
            
            if 'target_monitor' in data:
                config.target_monitor = int(data['target_monitor'])
            if 'fullscreen' in data:
                config.fullscreen = bool(data['fullscreen'])
            if 'window_width' in data:
                config.window_width = int(data['window_width'])
            if 'window_height' in data:
                config.window_height = int(data['window_height'])
            if 'launchbox_root' in data:
                config.launchbox_root = Path(data['launchbox_root'])
            if 'state_file' in data:
                config.state_file = Path(data['state_file'])
            if 'idle_image' in data and data['idle_image']:
                config.idle_image = Path(data['idle_image'])
            if 'image_display_seconds' in data:
                config.image_display_seconds = float(data['image_display_seconds'])
            if 'prefer_video' in data:
                config.prefer_video = bool(data['prefer_video'])
                
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
    
    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'GameState':
        return cls(
            game_id=data.get('game_id'),
            title=data.get('title'),
            platform=data.get('platform'),
            region=data.get('region', 'North America'),
            mode=data.get('mode', 'image'),
        )
    
    def is_valid(self) -> bool:
        return bool(self.title and self.platform)


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


# -----------------------------------------------------------------------------
# File Watcher
# -----------------------------------------------------------------------------

class StateFileHandler(FileSystemEventHandler):
    """Watches the state file for changes."""
    
    def __init__(self, state_file: Path, callback):
        super().__init__()
        self.state_file = state_file
        self.callback = callback
        self.last_modified = 0
    
    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent):
            # Check if it's our file
            if Path(event.src_path).resolve() == self.state_file.resolve():
                # Debounce rapid changes
                now = time.time()
                if now - self.last_modified > 0.3:
                    self.last_modified = now
                    logging.debug("State file changed, triggering callback")
                    self.callback()


def start_file_watcher(state_file: Path, callback) -> Optional[Observer]:
    """Start watching the state file for changes."""
    if not WATCHDOG_AVAILABLE:
        logging.warning("Watchdog not available, using polling fallback")
        return None
    
    try:
        handler = StateFileHandler(state_file, callback)
        observer = Observer()
        observer.schedule(handler, str(state_file.parent), recursive=False)
        observer.start()
        logging.info(f"File watcher started for {state_file}")
        return observer
    except Exception as e:
        logging.error(f"Failed to start file watcher: {e}")
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
        self.current_video: Optional[Path] = None
        self.current_image: Optional[Path] = None
        self._stop_event = Event()
        self._video_thread: Optional[Thread] = None
        self._video_stop = Event()

        # Tkinter elements
        self.root: Optional["tk.Tk"] = None
        self.canvas: Optional["tk.Canvas"] = None
        self._photo_ref = None  # prevent GC
        self._hwnd: Optional[int] = None
        self._monitor_bounds: Tuple[int, int, int, int] = (0, 0, 1920, 1080)
    
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
        self.stop_video()
        if self.canvas:
            self.canvas.delete("all")
            self.canvas.configure(bg="black")
    
    def show_image(self, image_path: Path):
        """Display a static image."""
        logging.info(f"Showing image: {image_path}")
        self.current_image = image_path
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
    
    def play_video(self, video_path: Path, loop: bool = True):
        """Play a video file."""
        logging.info(f"Playing video: {video_path} (loop={loop})")
        self.current_video = video_path
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
        
        self.current_state = state
        
        # Resolve media
        video_path, image_path = resolve_game_media(
            self.config, 
            state.title, 
            state.platform
        )
        
        logging.info(f"Game: {state.title} | Video: {video_path} | Image: {image_path}")
        
        # Display logic: show image first, then video
        if image_path:
            self.show_image(image_path)
        
        if video_path and self.config.prefer_video:
            # After image_display_seconds, switch to video
            def _start_video():
                if not self._stop_event.is_set():
                    self.play_video(video_path, loop=self.config.video_loop)
            if self.root:
                self.root.after(int(self.config.image_display_seconds * 1000), _start_video)
            else:
                _start_video()
        elif not image_path:
            self.show_idle()
    
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
    
    def on_state_change(self):
        """Called when the state file changes."""
        state = load_game_state(self.config.state_file)
        
        # Only update if state actually changed
        if state and (not self._last_state or state.game_id != self._last_state.game_id):
            logging.info(f"Game changed: {state.title} ({state.platform})")
            self._last_state = state
            self.display.update_game(state)
        elif not state or not state.is_valid():
            if self._last_state:
                logging.info("No game selected, showing idle")
                self._last_state = None
                self.display.show_idle()
    
    def run(self):
        """Run the marquee application."""
        logging.info("=" * 50)
        logging.info("Marquee Display Starting")
        logging.info("=" * 50)
        logging.info(f"Config: Monitor {self.config.target_monitor}, "
                    f"LaunchBox: {self.config.launchbox_root}")
        logging.info(f"State file: {self.config.state_file}")
        
        # Ensure state directory exists
        self.config.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize display
        if not self.display.initialize():
            logging.error("Failed to initialize display")
            return
        
        # Start file watcher
        self.observer = start_file_watcher(self.config.state_file, self.on_state_change)
        
        # Load initial state
        self.on_state_change()
        
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
    
    # Load config
    config_path = Path(args.config) if args.config else None
    config = load_config(config_path)
    config.target_monitor = args.monitor
    
    # Run app
    app = MarqueeApp(config)
    app.run()


if __name__ == "__main__":
    main()
