"""
LaunchBox XML parser with in-memory cache.
Parses all platform XMLs on startup, provides fast filtering/search.

Performance targets:
- Initial parse: <3 seconds for 14k+ games
- Filter operations: <500ms
"""
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional
import logging
from datetime import datetime, timedelta
import random
import threading
import json
import os

from backend.models.game import Game
from backend.constants.a_drive_paths import LaunchBoxPaths, is_on_a_drive
from backend.constants.paths import Paths
from backend.services.image_scanner import scanner as image_scanner

logger = logging.getLogger(__name__)


VIDEO_EXTENSIONS = [".mp4", ".avi", ".mkv", ".webm"]
IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg"]
MARQUEE_REGIONS = ["North America", "World", "Europe", "Japan", ""]


def _sanitize_media_title(title: str) -> str:
    return (title or "").replace(":", "").replace("?", "").replace("*", "").replace("/", "").replace("\\", "").replace('"', "")


def _find_media_file(directory: Path, game_name: str, extensions: List[str]) -> Optional[Path]:
    if not directory.exists():
        return None

    game_lower = game_name.lower()
    try:
        for file in directory.iterdir():
            if not file.is_file():
                continue
            if file.suffix.lower() not in extensions:
                continue
            if file.stem.lower().startswith(game_lower):
                return file
    except Exception:
        return None

    return None


def _resolve_video_snap_path(launchbox_root: Path, platform_name: str, game_title: str) -> Optional[str]:
    clean_title = _sanitize_media_title(game_title)
    if not clean_title:
        return None

    video_file = _find_media_file(launchbox_root / "Videos" / platform_name, clean_title, VIDEO_EXTENSIONS)
    return str(video_file) if video_file else None


def _resolve_marquee_image_path(launchbox_root: Path, platform_name: str, game_title: str) -> Optional[str]:
    clean_title = _sanitize_media_title(game_title)
    if not clean_title:
        return None

    images_base = launchbox_root / "Images" / platform_name
    marquee_dirs = [
        images_base / "Arcade - Marquee",
        images_base / f"{platform_name} - Marquee",
        images_base / "Marquee",
        images_base / "Banner",
    ]

    for marquee_dir in marquee_dirs:
        for region in MARQUEE_REGIONS:
            search_dir = marquee_dir / region if region else marquee_dir
            image_file = _find_media_file(search_dir, clean_title, IMAGE_EXTENSIONS)
            if image_file:
                return str(image_file)

    return None


def get_platform_games(platform_name: str) -> List[Dict[str, str]]:
    """
    Parse games for a single platform directly from its XML file.

    Uses deterministic Paths constants so downstream endpoints can rely on
    A:\\LaunchBox\\Data\\Platforms without discovery.
    """
    xml_path = Paths.LaunchBox.platform_xml(platform_name)
    if not xml_path.exists():
        raise FileNotFoundError(f"Platform XML not found: {xml_path}")

    tree = ET.parse(xml_path)
    root = tree.getroot()
    games: List[Dict[str, str]] = []

    for elem in root.findall("Game"):
        gid = elem.findtext("ID") or elem.findtext("DatabaseID") or ""
        title = elem.findtext("Title") or "Unknown"
        application_path = elem.findtext("ApplicationPath") or ""
        command_line = elem.findtext("CommandLine") or ""

        games.append({
            "id": gid,
            "title": title,
            "platform": platform_name,
            "applicationPath": application_path,
            "commandLine": command_line,
        })

    return games


class LaunchBoxParser:
    """
    Singleton parser service for LaunchBox platform XMLs.
    Maintains in-memory cache of all games for fast filtering.
    """

    _instance = None
    _lock = threading.Lock()
    _cache: Dict[str, Game] = {}
    _platforms: List[str] = []
    _genres: List[str] = []
    _xml_files_parsed: int = 0
    _last_updated: Optional[datetime] = None
    _loaded_from_disk: bool = False  # Track whether cache was loaded from disk

    # Cache configuration
    CACHE_DIR = Path(__file__).parent.parent / "cache"
    PARSER_CACHE_FILE = CACHE_DIR / "launchbox_parser_cache.json"
    PARSER_CACHE_MAX_AGE_DAYS = 7

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Lazy initialization - parse on first use or explicit initialize()
        pass

    def initialize(self):
        """
        Explicitly initialize the parser. Call after server startup.

        Attempts to load from disk cache first for faster startup (2-3s vs 10s).
        Falls back to parsing XML files if cache is unavailable or stale.
        """
        if not self._cache:
            # Try to load from disk cache first
            if self._load_parser_cache_from_disk():
                logger.info("Using cached parser data - skipping XML parse")
                return

            # Fall back to full XML parse if cache load failed
            self._parse_all_platforms()

            # Save the parsed data to disk for next time
            if self._cache and is_on_a_drive():
                self._save_parser_cache_to_disk()

    def _parse_all_platforms(self):
        """Parse all platform XMLs in Data/Platforms directory."""

        if not is_on_a_drive():
            logger.warning("Drive root not configured/detected - loading mock data")
            self._load_mock_data()
            return

        # Initialize ImageScanner first (it will scan in parallel)
        logger.info("Initializing image scanner...")
        image_scanner._ensure_initialized()

        platforms_dir = LaunchBoxPaths.PLATFORMS_DIR

        if not platforms_dir.exists():
            logger.error(f"Platforms directory not found: {platforms_dir}")
            self._load_mock_data()
            return

        xml_files = LaunchBoxPaths.get_platform_xml_files()

        if not xml_files:
            logger.error(f"No XML files found in {platforms_dir}")
            self._load_mock_data()
            return

        logger.info(f"Parsing {len(xml_files)} platform XML files from drive root...")

        platforms_set = set()
        genres_set = set()
        parse_start = datetime.now()
        self._parse_start_time = parse_start  # Track for duration calculation

        for xml_file in xml_files:
            try:
                tree = ET.parse(xml_file)
                root = tree.getroot()

                for game_elem in root.findall('Game'):
                    try:
                        game = self._parse_game_element(game_elem)
                        self._cache[game.id] = game

                        if game.platform:
                            platforms_set.add(game.platform)
                        if game.genre:
                            genres_set.add(game.genre)

                    except Exception as e:
                        # Skip individual game parse errors
                        logger.debug(f"Failed to parse game in {xml_file.name}: {e}")
                        continue

                self._xml_files_parsed += 1

            except Exception as e:
                logger.error(f"Failed to parse {xml_file.name}: {e}")
                continue

        self._platforms = sorted(platforms_set)
        self._genres = sorted(genres_set)
        self._last_updated = datetime.now()

        parse_duration = (self._last_updated - parse_start).total_seconds()

        logger.info(
            f"✅ Parsed {len(self._cache)} games across {len(self._platforms)} platforms "
            f"in {parse_duration:.2f}s"
        )

    def _parse_game_element(self, elem: ET.Element) -> Game:
        """Parse single <Game> XML element into Game model."""

        # Helper to safely get text
        def get_text(tag: str, default=None):
            child = elem.find(tag)
            if child is not None and child.text is not None:
                return child.text.strip()
            return default

        # Extract year from ReleaseDate (format: YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD)
        release_date = get_text('ReleaseDate', '')
        year = None
        if release_date:
            try:
                year = int(release_date[:4])
            except (ValueError, IndexError):
                pass

        # Core fields
        game_id = get_text('ID', '')
        game_title = get_text('Title', 'Unknown')
        platform_name = get_text('Platform', 'Unknown')
        launchbox_root = LaunchBoxPaths._get_launchbox_root_dynamic()

        # Use ImageScanner to get actual image paths with fuzzy matching
        # This handles filename sanitization mismatches automatically
        clear_logo_path = image_scanner.get_image_path(game_title, platform_name, "clear_logo")
        box_front_path = image_scanner.get_image_path(game_title, platform_name, "box_front")
        screenshot_path = image_scanner.get_image_path(game_title, platform_name, "screenshot")

        # Fall back to constructed paths if scanner not initialized (development mode)
        if not any([clear_logo_path, box_front_path, screenshot_path]):
            # Map platform names for fallback
            image_platform = platform_name
            if platform_name == "Arcade MAME":
                image_platform = "Arcade"

            # Construct fallback paths (may not exist)
            if not box_front_path:
                box_front = LaunchBoxPaths.IMAGES_DIR / image_platform / "Box - Front" / f"{game_title}-01.png"
                box_front_path = str(box_front)
            if not screenshot_path:
                screenshot = LaunchBoxPaths.IMAGES_DIR / image_platform / "Screenshot - Gameplay" / f"{game_title}-01.png"
                screenshot_path = str(screenshot)
            if not clear_logo_path:
                clear_logo = LaunchBoxPaths.IMAGES_DIR / image_platform / "Clear Logo" / f"{game_title}-01.png"
                clear_logo_path = str(clear_logo)

        video_snap_path = _resolve_video_snap_path(launchbox_root, platform_name, game_title)
        marquee_image_path = _resolve_marquee_image_path(launchbox_root, platform_name, game_title)

        # Categories (single or list)
        categories: List[str] = []
        # Single Category element
        single_cat = get_text('Category', '')
        if single_cat:
            categories.append(single_cat)
        # Categories container
        cats_elem = elem.find('Categories')
        if cats_elem is not None:
            for c in cats_elem.findall('Category'):
                if c is not None and c.text:
                    categories.append(c.text.strip())
        # De-duplicate and normalize spacing
        categories = [c for c in {c.strip(): None for c in categories if c and c.strip()}.keys()]

        return Game(
            id=game_id,
            title=game_title,
            platform=platform_name,
            genre=get_text('Genre', ''),
            developer=get_text('Developer', ''),
            publisher=get_text('Publisher', ''),
            year=year,
            region=get_text('Region', ''),
            rom_path=get_text('ApplicationPath', ''),
            emulator_id=get_text('Emulator', ''),
            application_path=get_text('ApplicationPath', ''),
            box_front_path=box_front_path,
            screenshot_path=screenshot_path,
            clear_logo_path=clear_logo_path,
            video_snap_path=video_snap_path,
            marquee_image_path=marquee_image_path,
            categories=categories or None,
        )

    def _load_mock_data(self):
        """Load mock games for development without A: drive."""
        mock_games = [
            Game(id="1", title="Street Fighter II", platform="Arcade", genre="Fighting", year=1991),
            Game(id="2", title="Pac-Man", platform="Arcade", genre="Maze", year=1980),
            Game(id="3", title="Donkey Kong", platform="Arcade", genre="Platform", year=1981),
            Game(id="4", title="Galaga", platform="Arcade", genre="Shooter", year=1981),
            Game(id="5", title="Ms. Pac-Man", platform="Arcade", genre="Maze", year=1982),
            Game(id="6", title="Mortal Kombat", platform="Arcade", genre="Fighting", year=1992),
            Game(id="7", title="Super Mario Bros.", platform="NES", genre="Platform", year=1985),
            Game(id="8", title="The Legend of Zelda", platform="NES", genre="Adventure", year=1986),
            Game(id="9", title="Metroid", platform="NES", genre="Action", year=1986),
            Game(id="10", title="Contra", platform="NES", genre="Shooter", year=1987),
            Game(id="11", title="Super Mario World", platform="SNES", genre="Platform", year=1990),
            Game(id="12", title="Sonic the Hedgehog", platform="Sega Genesis", genre="Platform", year=1991),
            Game(id="13", title="Tetris", platform="Arcade", genre="Puzzle", year=1984),
            Game(id="14", title="Space Invaders", platform="Arcade", genre="Shooter", year=1978),
            Game(id="15", title="Asteroids", platform="Arcade", genre="Shooter", year=1979),
        ]

        for game in mock_games:
            self._cache[game.id] = game

        self._platforms = ["Arcade", "NES", "SNES", "Sega Genesis"]
        self._genres = ["Fighting", "Maze", "Platform", "Shooter", "Adventure", "Action", "Puzzle"]
        self._last_updated = datetime.now()
        self._xml_files_parsed = 0

        logger.info(f"📦 Loaded {len(mock_games)} mock games (Drive root not available)")

    def _save_parser_cache_to_disk(self):
        """
        Save the current parser cache to disk for faster subsequent startups.

        The cache file includes all parsed games, platforms, genres, and metadata.
        This method is thread-safe as it's called within locked contexts.
        """
        try:
            # Create cache directory if it doesn't exist
            self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

            # Convert Game objects to dictionaries for JSON serialization
            cache_dict = {}
            for game_id, game in self._cache.items():
                cache_dict[game_id] = {
                    "id": game.id,
                    "title": game.title,
                    "platform": game.platform,
                    "genre": game.genre,
                    "developer": game.developer,
                    "publisher": game.publisher,
                    "year": game.year,
                    "region": game.region,
                    "rom_path": game.rom_path,
                    "emulator_id": game.emulator_id,
                    "application_path": game.application_path,
                    "box_front_path": game.box_front_path,
                    "screenshot_path": game.screenshot_path,
                    "clear_logo_path": game.clear_logo_path,
                    "video_snap_path": game.video_snap_path,
                    "marquee_image_path": game.marquee_image_path,
                }

            # Calculate parse duration (if we just parsed)
            parse_duration = 0
            if hasattr(self, '_parse_start_time'):
                parse_duration = (datetime.now() - self._parse_start_time).total_seconds()

            # Prepare cache data with metadata
            cache_data = {
                "version": "1.0",
                "created_at": datetime.now().isoformat(),
                "parse_duration_seconds": parse_duration,
                "games_count": len(self._cache),
                "platforms_count": len(self._platforms),
                "genres_count": len(self._genres),
                "xml_files_parsed": self._xml_files_parsed,
                "last_updated": self._last_updated.isoformat() if self._last_updated else None,
                "cache": cache_dict,
                "platforms": self._platforms,
                "genres": self._genres,
            }

            # Write cache to disk
            with open(self.PARSER_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, separators=(',', ':'))  # Compact JSON

            # Calculate file size for logging
            file_size_mb = os.path.getsize(self.PARSER_CACHE_FILE) / (1024 * 1024)

            logger.info(
                f"✅ Parser cache saved to disk: {self.PARSER_CACHE_FILE} "
                f"({len(self._cache):,} games, {file_size_mb:.1f}MB)"
            )

        except Exception as e:
            logger.error(f"Failed to save parser cache to disk: {e}")
            # Non-critical error - continue without disk cache

    def _load_parser_cache_from_disk(self) -> bool:
        """
        Load parser cache from disk if available and valid.

        Returns:
            True if cache was successfully loaded, False otherwise.
        """
        try:
            # Check if cache file exists
            if not self.PARSER_CACHE_FILE.exists():
                logger.info("No parser cache file found - will perform full XML parse")
                return False

            # Load cache data
            with open(self.PARSER_CACHE_FILE, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            # Validate cache version
            cache_version = cache_data.get("version", "0.0")
            if cache_version != "1.0":
                logger.warning(f"Incompatible parser cache version {cache_version} - will reparse")
                return False

            # Check cache age
            created_at_str = cache_data.get("created_at")
            if not created_at_str:
                logger.warning("Parser cache missing creation timestamp - will reparse")
                return False

            created_at = datetime.fromisoformat(created_at_str)
            cache_age = datetime.now() - created_at

            if cache_age > timedelta(days=self.PARSER_CACHE_MAX_AGE_DAYS):
                logger.info(
                    f"Parser cache is stale ({cache_age.days} days old, max {self.PARSER_CACHE_MAX_AGE_DAYS}) "
                    f"- will reparse XML files"
                )
                return False

            # Load cache into memory
            cache_dict = cache_data.get("cache", {})

            # Normalize cached Windows paths when running under WSL
            # Ensures any A:\ absolute paths work on /mnt/a in WSL
            try:
                import platform

                def _is_wsl() -> bool:
                    try:
                        return platform.system() == 'Linux' and 'microsoft' in platform.release().lower()
                    except Exception:
                        return False

                def _normalize_path(p: str) -> str:
                    if not isinstance(p, str):
                        return p
                    # Convert absolute X:\ paths to /mnt/x POSIX when under WSL
                    # Detect generic Windows path "X:\"
                    if len(p) > 2 and p[1] == ':' and p[2] in ('\\', '/'):
                        drive = p[0].lower()
                        return p.replace(f"{p[0].upper()}:\\", f"/mnt/{drive}/").replace("\\", "/")
                    return p

                if _is_wsl() and isinstance(cache_dict, dict):
                    for _gid, entry in list(cache_dict.items()):
                        if isinstance(entry, dict):
                            for k, v in list(entry.items()):
                                if isinstance(v, str):
                                    entry[k] = _normalize_path(v)
                                elif isinstance(v, list):
                                    entry[k] = [_normalize_path(x) for x in v]
            except Exception:
                # Non-fatal; proceed with original cache if normalization fails
                pass

            self._cache = {}

            # Convert dictionaries back to Game objects
            for game_id, game_dict in cache_dict.items():
                self._cache[game_id] = Game(**game_dict)

            # Load platforms and genres
            self._platforms = cache_data.get("platforms", [])
            self._genres = cache_data.get("genres", [])
            self._xml_files_parsed = cache_data.get("xml_files_parsed", 0)

            # Load last updated timestamp
            last_updated_str = cache_data.get("last_updated")
            if last_updated_str:
                self._last_updated = datetime.fromisoformat(last_updated_str)

            # Set cache source indicator
            self._loaded_from_disk = True

            # Calculate file size for logging
            file_size_mb = os.path.getsize(self.PARSER_CACHE_FILE) / (1024 * 1024)

            logger.info(
                f"✅ Parser cache loaded from disk: {cache_data.get('games_count', 0):,} games "
                f"from {cache_data.get('platforms_count', 0)} platforms "
                f"(cache age: {cache_age.days} days, {cache_age.seconds//3600} hours, "
                f"file size: {file_size_mb:.1f}MB)"
            )

            return True

        except json.JSONDecodeError as e:
            logger.error(f"Parser cache file is corrupted: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to load parser cache from disk: {e}")
            return False

    # Public API

    def _ensure_initialized(self):
        """Ensure parser is initialized (thread-safe lazy loading)."""
        if not self._cache:
            with self._lock:
                if not self._cache:  # Double-check pattern
                    self.initialize()

    def get_all_games(self) -> List[Game]:
        """Get all games from cache."""
        self._ensure_initialized()
        return list(self._cache.values())

    def get_paginated_games(
        self,
        platform: Optional[str] = None,
        genre: Optional[str] = None,
        search: Optional[str] = None,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
        sort_by: str = 'title',
        sort_order: str = 'asc',
        page: int = 1,
        limit: int = 50,
    ) -> Dict[str, any]:
        """
        Filter, sort, and paginate games from the cache.
        Returns a dictionary containing the list of games for the page and the total count.
        """
        self._ensure_initialized()
        
        # Start with all games
        results = list(self._cache.values())

        # Apply filters
        if platform:
            platform_lower = platform.lower()
            results = [g for g in results if g.platform and g.platform.lower() == platform_lower]
        
        if genre:
            genre_lower = genre.lower()
            results = [g for g in results if g.genre and g.genre.lower() == genre_lower]

        if search:
            search_lower = search.lower()
            results = [
                g for g in results
                if search_lower in g.title.lower()
                or (g.developer and search_lower in g.developer.lower())
                or (g.publisher and search_lower in g.publisher.lower())
            ]

        # Apply year range filter (inclusive)
        if year_min is not None:
            try:
                year_min_int = int(year_min)
            except (TypeError, ValueError):
                year_min_int = None
            if year_min_int is not None:
                results = [g for g in results if isinstance(g.year, int) and g.year >= year_min_int]

        if year_max is not None:
            try:
                year_max_int = int(year_max)
            except (TypeError, ValueError):
                year_max_int = None
            if year_max_int is not None:
                results = [g for g in results if isinstance(g.year, int) and g.year <= year_max_int]
        
        # Apply sorting
        if sort_by:
            # Safely get attribute, default to empty string for sorting
            results.sort(
                key=lambda g: (getattr(g, sort_by, None) or '').lower() if isinstance(getattr(g, sort_by, None), str) else getattr(g, sort_by, 0) or 0,
                reverse=(sort_order == 'desc')
            )

        # Get total count before pagination
        total_games = len(results)

        # Apply pagination
        start_index = (page - 1) * limit
        end_index = start_index + limit
        paginated_results = results[start_index:end_index]

        return {
            "games": paginated_results,
            "total": total_games,
            "page": page,
            "limit": limit
        }

    def get_game_by_id(self, game_id: str) -> Optional[Game]:
        """Get single game by ID."""
        self._ensure_initialized()
        return self._cache.get(game_id)

    def get_platforms(self) -> List[str]:
        """Get list of all platforms."""
        self._ensure_initialized()
        return self._platforms

    def get_genres(self) -> List[str]:
        """Get list of all genres."""
        self._ensure_initialized()
        return self._genres

    def filter_games(
        self,
        platform: Optional[str] = None,
        genre: Optional[str] = None,
        decade: Optional[int] = None,
        search: Optional[str] = None,
    ) -> List[Game]:
        """
        Filter games by multiple criteria.

        Args:
            platform: Filter by exact platform name
            genre: Filter by exact genre name
            decade: Filter by decade (e.g., 1980 for 1980-1989)
            search: Search in title, developer, publisher (case-insensitive)

        Returns:
            Filtered list of games
        """
        results = self.get_all_games()

        if platform:
            results = [g for g in results if g.platform == platform]

        if genre:
            results = [g for g in results if g.genre == genre]

        if decade:
            decade_end = decade + 10
            results = [g for g in results if g.year and decade <= g.year < decade_end]

        if search:
            search_lower = search.lower()
            results = [
                g for g in results
                if search_lower in g.title.lower()
                or (g.developer and search_lower in g.developer.lower())
                or (g.publisher and search_lower in g.publisher.lower())
            ]

        return results

    def get_random_game(self, **filter_kwargs) -> Optional[Game]:
        """Get random game, optionally filtered."""
        filtered = self.filter_games(**filter_kwargs)
        return random.choice(filtered) if filtered else None

    def get_cache_stats(self) -> dict:
        """Get cache statistics for debugging."""
        self._ensure_initialized()

        # Check if cache file exists and get its info
        cache_file_info = {}
        if self.PARSER_CACHE_FILE.exists():
            try:
                file_stat = self.PARSER_CACHE_FILE.stat()
                cache_file_info = {
                    "cache_file_exists": True,
                    "cache_file_size_mb": file_stat.st_size / (1024 * 1024),
                    "cache_file_modified": datetime.fromtimestamp(file_stat.st_mtime).isoformat()
                }
            except Exception:
                cache_file_info = {"cache_file_exists": False}
        else:
            cache_file_info = {"cache_file_exists": False}

        return {
            "total_games": len(self._cache),
            "platforms_count": len(self._platforms),
            "genres_count": len(self._genres),
            "xml_files_parsed": self._xml_files_parsed,
            "last_updated": self._last_updated.isoformat() if self._last_updated else None,
            "is_mock_data": not is_on_a_drive() or self._xml_files_parsed == 0,
            "a_drive_status": LaunchBoxPaths.get_status_message(),
            "cache_source": "disk" if self._loaded_from_disk else "xml_parse",
            "loaded_from_disk": self._loaded_from_disk,
            **cache_file_info,
            "cache_max_age_days": self.PARSER_CACHE_MAX_AGE_DAYS,
        }


# Singleton instance
parser = LaunchBoxParser()
