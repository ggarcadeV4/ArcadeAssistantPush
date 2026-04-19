"""
LaunchBox image scanner with fuzzy matching and performance optimization.

This service solves the filename sanitization mismatch problem between XML titles
and actual image filenames. It pre-scans all image directories on startup and builds
a fast lookup cache with fuzzy matching support.

Performance targets:
- Scan time: <5s for ~10k images across 50 platforms
- Query time: <5ms per lookup
- Memory usage: <100MB for full cache
"""
import os
import re
import threading
import logging
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from difflib import SequenceMatcher
from datetime import datetime, timedelta
from collections import defaultdict
import time

from backend.constants.a_drive_paths import LaunchBoxPaths, is_on_a_drive

logger = logging.getLogger(__name__)


class ImageScanner:
    """
    Scans LaunchBox image directories and provides fuzzy-matched lookups.

    Singleton pattern with thread-safe lazy initialization.
    Maintains an in-memory cache of all image paths with fast lookups.
    """

    # Singleton instance management
    _instance = None
    _lock = threading.Lock()
    _initialized = False
    _loaded_from_disk = False  # Track whether cache was loaded from disk

    # Cache structure: {platform: {image_type: {sanitized_title: full_path}}}
    _image_cache: Dict[str, Dict[str, Dict[str, str]]] = {}

    # Reverse lookup for fuzzy matching: {platform: {image_type: [all_sanitized_titles]}}
    _title_lists: Dict[str, Dict[str, List[str]]] = {}

    # Statistics
    _scan_stats = {
        "platforms_scanned": 0,
        "images_found": 0,
        "scan_duration": 0.0,
        "cache_memory_mb": 0.0,
        "last_scan": None,
        "cache_source": "memory_scan"  # Track source: "disk" or "memory_scan"
    }

    # Configuration
    FUZZY_THRESHOLD = 0.85  # Minimum similarity ratio for fuzzy matches
    SCAN_TIMEOUT = 30.0  # Maximum scan time in seconds

    # Cache configuration
    CACHE_DIR = Path(__file__).parent.parent / "cache"
    CACHE_FILE = CACHE_DIR / "image_cache.json"
    CACHE_MAX_AGE_DAYS = 7
    CACHE_VERSION = "1.1"

    # Image type mappings (directory names in LaunchBox)
    IMAGE_TYPES = {
        "clear_logo": "Clear Logo",
        "box_front": "Box - Front",
        "screenshot": "Screenshot - Gameplay",
        "marquee": "Arcade - Marquee",
        "cart_front": "Cart - Front"
    }

    # Platform name mappings (handle inconsistencies)
    PLATFORM_MAPPINGS = {
        "Arcade MAME": "Arcade MAME",  # Keep separate from "Arcade"
        "Arcade": "Arcade",  # Original arcade platform
    }

    def __new__(cls):
        """Singleton pattern implementation."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize scanner (actual work done in _ensure_initialized)."""
        pass

    def _ensure_initialized(self):
        """Thread-safe lazy initialization."""
        if not self._initialized:
            with self._lock:
                if not self._initialized:  # Double-check pattern
                    self._scan_all_images()
                    self._initialized = True

    def _save_cache_to_disk(self):
        """
        Save the current image cache to disk for faster subsequent startups.

        The cache file includes metadata for validation and statistics tracking.
        This method is thread-safe as it's called within locked contexts.
        """
        try:
            # Create cache directory if it doesn't exist
            self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

            # Prepare cache data with metadata
            cache_data = {
                "version": self.CACHE_VERSION,
                "created_at": datetime.now().isoformat(),
                "scan_duration_seconds": self._scan_stats.get("scan_duration", 0),
                "platforms_scanned": self._scan_stats.get("platforms_scanned", 0),
                "images_found": self._scan_stats.get("images_found", 0),
                "cache_memory_mb": self._scan_stats.get("cache_memory_mb", 0),
                "cache": self._image_cache,
                "title_lists": self._title_lists,
                "scan_stats": {
                    k: v.isoformat() if isinstance(v, datetime) else v
                    for k, v in self._scan_stats.items()
                }
            }

            # Write cache to disk
            with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, separators=(',', ':'))  # Compact JSON

            logger.info(
                f"✅ Cache saved to disk: {self.CACHE_FILE} "
                f"({self._scan_stats.get('images_found', 0):,} images, "
                f"{os.path.getsize(self.CACHE_FILE) / (1024*1024):.1f}MB)"
            )

        except Exception as e:
            logger.error(f"Failed to save cache to disk: {e}")
            # Non-critical error - continue without disk cache

    def _load_cache_from_disk(self) -> bool:
        """
        Load image cache from disk if available and valid.

        Returns:
            True if cache was successfully loaded, False otherwise.
        """
        try:
            # Check if cache file exists
            if not self.CACHE_FILE.exists():
                logger.info("No cache file found - will perform full scan")
                return False

            # Load cache data
            with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            # Validate cache version (for future compatibility)
            cache_version = cache_data.get("version", "0.0")
            if cache_version != self.CACHE_VERSION:
                logger.warning(f"Incompatible cache version {cache_version} - will rescan")
                return False

            # Check cache age
            created_at_str = cache_data.get("created_at")
            if not created_at_str:
                logger.warning("Cache missing creation timestamp - will rescan")
                return False

            created_at = datetime.fromisoformat(created_at_str)
            cache_age = datetime.now() - created_at

            if cache_age > timedelta(days=self.CACHE_MAX_AGE_DAYS):
                logger.info(
                    f"Cache is stale ({cache_age.days} days old, max {self.CACHE_MAX_AGE_DAYS}) "
                    f"- will rescan"
                )
                return False

            # Load cache into memory
            self._image_cache = cache_data.get("cache", {})
            self._title_lists = cache_data.get("title_lists", {})

            # --- WSL path normalization for caches created on Windows ---
            # If running inside WSL, convert any absolute Windows A:\ paths
            # to their /mnt/a equivalents to ensure os.path.exists checks succeed.
            try:
                import platform  # local import to avoid module-level side effects

                def _is_wsl() -> bool:
                    try:
                        return platform.system() == "Linux" and "microsoft" in platform.release().lower()
                    except Exception:
                        return False

                def _normalize_windows_path(p: str) -> str:
                    if not isinstance(p, str):
                        return p
                    # Detect generic Windows path "X:\"
                    if len(p) > 2 and p[1] == ':' and p[2] in ('\\', '/'):
                        drive = p[0].lower()
                        # strip leading 'X:' and any leading slash/backslash
                        rest = p[2:]
                        if rest.startswith("\\") or rest.startswith("/"):
                            rest = rest[1:]
                        rest = rest.replace("\\", "/")
                        return f"/mnt/{drive}/{rest}"
                    return p

                if _is_wsl() and isinstance(self._image_cache, dict):
                    for plat, types in self._image_cache.items():
                        if not isinstance(types, dict):
                            continue
                        for tkey, title_map in types.items():
                            if not isinstance(title_map, dict):
                                continue
                            for title, path_str in list(title_map.items()):
                                normalized = _normalize_windows_path(path_str)
                                if normalized != path_str:
                                    title_map[title] = normalized

                    # Additional normalization pass for alternate cache shapes
                    # (defensive): if cache ever stores per-game entries
                    def _normalize_path(p: str) -> str:
                        if not isinstance(p, str):
                            return p
                        # Detect generic Windows path "X:\"
                        if len(p) > 2 and p[1] == ':' and p[2] in ('\\', '/'):
                            drive = p[0].lower()
                            return p.replace(f"{p[0].upper()}:\\", f"/mnt/{drive}/").replace("\\", "/")
                        return p

                    for _gid, entry in list(self._image_cache.items()):
                        if isinstance(entry, dict):
                            for k, v in list(entry.items()):
                                if isinstance(v, str):
                                    entry[k] = _normalize_path(v)
                                elif isinstance(v, list):
                                    entry[k] = [_normalize_path(x) for x in v]
            except Exception:
                # Non-fatal; continue with original cache if normalization fails
                pass

            # Load statistics
            scan_stats = cache_data.get("scan_stats", {})
            for key, value in scan_stats.items():
                if key == "last_scan" and value:
                    # Convert ISO string back to datetime
                    self._scan_stats[key] = datetime.fromisoformat(value)
                else:
                    self._scan_stats[key] = value

            # Update cache source indicator
            self._scan_stats["cache_source"] = "disk"
            self._loaded_from_disk = True

            # Calculate file size for logging
            file_size_mb = os.path.getsize(self.CACHE_FILE) / (1024 * 1024)

            logger.info(
                f"✅ Cache loaded from disk: {cache_data.get('images_found', 0):,} images "
                f"from {cache_data.get('platforms_scanned', 0)} platforms "
                f"(cache age: {cache_age.days} days, {cache_age.seconds//3600} hours, "
                f"file size: {file_size_mb:.1f}MB)"
            )

            return True

        except json.JSONDecodeError as e:
            logger.error(f"Cache file is corrupted: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to load cache from disk: {e}")
            return False

    def _scan_all_images(self):
        """
        Scan all image directories and build lookup cache.
        Supports multiple image directories via IMAGE_DIRS environment variable.
        Optimized for performance with minimal file system calls.
        Attempts to load from disk cache first for faster startup.
        """
        if not is_on_a_drive():
            logger.info("Drive root not configured/detected - image scanning disabled")
            return

        # Try to load from disk cache first (2-3s instead of 30-35s)
        if self._load_cache_from_disk():
            logger.info("Using cached image data - skipping directory scan")
            return

        # Get image directories to scan (support multiple via env var)
        import os
        image_dirs_str = os.getenv('IMAGE_DIRS', None)

        if image_dirs_str:
            # Parse comma-separated list from env
            image_dirs = [Path(d.strip()) for d in image_dirs_str.split(',') if d.strip()]
            logger.info(f"Scanning {len(image_dirs)} custom image directories from IMAGE_DIRS")
        else:
            # Default: LaunchBox images directory
            image_dirs = [LaunchBoxPaths.IMAGES_DIR]

        # Validate at least one directory exists
        existing_dirs = [d for d in image_dirs if d.exists()]
        if not existing_dirs:
            logger.warning(f"No image directories found. Checked: {[str(d) for d in image_dirs]}")
            return

        logger.info(f"Starting image directory scan of {len(existing_dirs)} location(s)...")
        scan_start = time.time()
        self._scan_stats["cache_source"] = "memory_scan"  # Reset source indicator
        total_images = 0

        try:
            # Scan each image directory location
            for images_dir in existing_dirs:
                logger.info(f"Scanning: {images_dir}")

                # Get all platform directories
                platform_dirs = [d for d in images_dir.iterdir() if d.is_dir()]

                # Filter out cache directories and non-platform folders
                platform_dirs = [
                    d for d in platform_dirs
                    if not d.name.startswith("Cache") and d.name != "Badges"
                ]

                for platform_dir in platform_dirs:
                    platform_name = platform_dir.name

                    # Initialize cache structures for this platform
                    if platform_name not in self._image_cache:
                        self._image_cache[platform_name] = {}
                        self._title_lists[platform_name] = {}

                    # Scan each image type directory
                    for type_key, type_dirname in self.IMAGE_TYPES.items():
                        type_dir = platform_dir / type_dirname

                        if not type_dir.exists():
                            continue

                        # Initialize type-specific caches
                        if type_key not in self._image_cache[platform_name]:
                            self._image_cache[platform_name][type_key] = {}
                            self._title_lists[platform_name][type_key] = []

                        # Index both root artwork files and one-level-deep region folders.
                        # Many LaunchBox installs keep the only usable art under folders
                        # like "World", "North America", or "United States".
                        image_files = []
                        for ext in ['*.png', '*.jpg', '*.jpeg']:
                            image_files.extend(type_dir.rglob(ext))

                        image_files.sort(
                            key=lambda p: (len(p.relative_to(type_dir).parts), str(p).lower())
                        )

                        # Process each image file
                        for image_path in image_files:
                            # Extract base title from filename
                            # Format: "Game Title-01.png" or "Game Title.png"
                            filename = image_path.stem  # Remove extension

                            # Remove suffix like "-01", "-02", etc.
                            base_title = re.sub(r'-\d+$', '', filename)

                            # Sanitize for consistent lookups
                            sanitized_title = self._sanitize_for_lookup(base_title)

                            # Store in cache (keep first occurrence if duplicates)
                            if sanitized_title not in self._image_cache[platform_name][type_key]:
                                self._image_cache[platform_name][type_key][sanitized_title] = str(image_path)
                                self._title_lists[platform_name][type_key].append(sanitized_title)
                                total_images += 1

                        # Sort title lists for consistent fuzzy matching
                        self._title_lists[platform_name][type_key].sort()

                    self._scan_stats["platforms_scanned"] += 1

            # Calculate statistics
            scan_duration = time.time() - scan_start
            self._scan_stats["images_found"] = total_images
            self._scan_stats["scan_duration"] = scan_duration
            self._scan_stats["last_scan"] = datetime.now()

            # Estimate memory usage (rough approximation)
            avg_path_size = 100  # bytes per path string
            avg_title_size = 50  # bytes per title string
            memory_bytes = (total_images * (avg_path_size + avg_title_size))
            self._scan_stats["cache_memory_mb"] = memory_bytes / (1024 * 1024)

            logger.info(
                f"✅ Image scan complete: {total_images:,} images found across "
                f"{self._scan_stats['platforms_scanned']} platforms in {scan_duration:.2f}s "
                f"(~{self._scan_stats['cache_memory_mb']:.1f}MB cache)"
            )

            # Save cache to disk for faster future startups
            self._save_cache_to_disk()

        except Exception as e:
            logger.error(f"Error during image scan: {e}")
            # Continue with partial cache rather than failing completely

    def _sanitize_title(self, title: str) -> str:
        """
        Sanitize game title to match LaunchBox image naming conventions.

        LaunchBox sanitization rules (reverse-engineered):
        - Colons (:) -> underscores (_)
        - Forward slashes (/) -> underscores (_)
        - Backslashes (\\) -> underscores (_)
        - Question marks (?) -> removed
        - Asterisks (*) -> removed
        - Angle brackets (<>) -> removed
        - Pipe (|) -> removed
        - Double quotes (") -> removed
        - Leading/trailing spaces -> trimmed
        """
        if not title:
            return ""

        # Apply LaunchBox sanitization rules
        sanitized = title

        # Replace invalid filename characters with underscores
        sanitized = sanitized.replace(':', '_')
        sanitized = sanitized.replace('/', '_')
        sanitized = sanitized.replace('\\', '_')

        # Remove other invalid characters
        sanitized = re.sub(r'[?*<>|"]', '', sanitized)

        # Clean up multiple spaces/underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        sanitized = re.sub(r'\s+', ' ', sanitized)

        # Trim
        sanitized = sanitized.strip()

        return sanitized

    def _sanitize_for_lookup(self, title: str) -> str:
        """
        Sanitize title for cache lookup (case-insensitive, normalized).
        """
        return self._sanitize_title(title).lower()

    def _get_lookup_candidates(self, title: str) -> List[str]:
        """
        Generate lookup candidates for image matching.

        This keeps the original title as the primary candidate, then adds a few
        conservative LaunchBox-friendly fallbacks for common naming differences.
        """
        raw_title = (title or "").strip()
        if not raw_title:
            return []

        candidates: List[str] = []

        def add_candidate(value: str):
            sanitized = self._sanitize_for_lookup(value)
            if sanitized and sanitized not in candidates:
                candidates.append(sanitized)

        add_candidate(raw_title)

        stripped = re.sub(r"\s*[\(\[].*?[\)\]]", "", raw_title).strip()
        add_candidate(stripped)

        base_for_split = stripped or raw_title
        for separator in (" - ", ": ", " – ", " — "):
            if separator in base_for_split:
                add_candidate(base_for_split.split(separator, 1)[0].strip())

        if "&" in base_for_split:
            add_candidate(base_for_split.replace("&", "and"))
        if re.search(r"\band\b", base_for_split, flags=re.IGNORECASE):
            add_candidate(re.sub(r"\band\b", "&", base_for_split, flags=re.IGNORECASE))

        return candidates

    def _fuzzy_match(self, title: str, candidates: List[str], threshold: float = None) -> Optional[str]:
        """
        Find best fuzzy match for title among candidates.

        Args:
            title: Title to match (already sanitized for lookup)
            candidates: List of candidate titles (sanitized)
            threshold: Minimum similarity ratio (default: FUZZY_THRESHOLD)

        Returns:
            Best matching candidate or None if no good match
        """
        if not candidates:
            return None

        threshold = threshold or self.FUZZY_THRESHOLD

        # First try exact match (fastest)
        if title in candidates:
            return title

        # Find best fuzzy match
        best_match = None
        best_ratio = 0.0

        for candidate in candidates:
            # Use SequenceMatcher for fuzzy string matching
            ratio = SequenceMatcher(None, title, candidate).ratio()

            if ratio > best_ratio:
                best_ratio = ratio
                best_match = candidate

            # Early exit if perfect match found
            if ratio >= 0.99:
                break

        # Return match if above threshold
        if best_ratio >= threshold:
            logger.debug(
                f"Fuzzy match: '{title}' -> '{best_match}' "
                f"(similarity: {best_ratio:.2%})"
            )
            return best_match

        return None

    def get_image_path(
        self,
        title: str,
        platform: str,
        image_type: str = "clear_logo"
    ) -> Optional[str]:
        """
        Get image path for a game title with fuzzy matching support.

        Args:
            title: Game title from XML (may not match filename exactly)
            platform: Platform name (e.g., "Arcade MAME", "Nintendo Entertainment System")
            image_type: Type of image (clear_logo, box_front, screenshot, marquee, cart_front)

        Returns:
            Full path to image file or None if not found
        """
        self._ensure_initialized()

        # Validate image type
        if image_type not in self.IMAGE_TYPES:
            logger.warning(f"Unknown image type: {image_type}")
            return None

        # Apply platform mappings if needed
        lookup_platform = self.PLATFORM_MAPPINGS.get(platform, platform)

        # Check if platform exists in cache
        if lookup_platform not in self._image_cache:
            logger.debug(f"Platform not found in image cache: {lookup_platform}")
            return None

        # Check if image type exists for this platform
        if image_type not in self._image_cache[lookup_platform]:
            logger.debug(f"Image type '{image_type}' not found for platform '{lookup_platform}'")
            return None

        lookup_candidates = self._get_lookup_candidates(title)

        # Try exact matches first across a small set of title variants.
        for candidate in lookup_candidates:
            exact_match = self._image_cache[lookup_platform][image_type].get(candidate)
            if exact_match:
                return exact_match

        # Fall back to fuzzy matching
        candidates = self._title_lists[lookup_platform][image_type]
        for index, candidate in enumerate(lookup_candidates):
            threshold = self.FUZZY_THRESHOLD if index == 0 else max(self.FUZZY_THRESHOLD, 0.9)
            fuzzy_match = self._fuzzy_match(candidate, candidates, threshold=threshold)
            if fuzzy_match:
                return self._image_cache[lookup_platform][image_type][fuzzy_match]

        # No match found
        logger.debug(
            f"No image found for '{title}' (platform: {lookup_platform}, "
            f"type: {image_type}, candidates: {lookup_candidates})"
        )
        return None

    def get_all_images(self, title: str, platform: str) -> Dict[str, Optional[str]]:
        """
        Get all available image types for a game.

        Returns:
            Dictionary of {image_type: path} for all found images
        """
        self._ensure_initialized()

        results = {}
        for image_type in self.IMAGE_TYPES:
            results[image_type] = self.get_image_path(title, platform, image_type)

        return results

    def get_cache_stats(self) -> dict:
        """
        Get statistics about the image cache.

        Returns:
            Dictionary with scan statistics and cache metrics
        """
        self._ensure_initialized()

        # Calculate additional runtime stats
        platform_stats = {}
        for platform in self._image_cache:
            total_images = sum(
                len(self._image_cache[platform].get(img_type, {}))
                for img_type in self.IMAGE_TYPES
            )
            platform_stats[platform] = total_images

        # Check if cache file exists and get its info
        cache_file_info = {}
        if self.CACHE_FILE.exists():
            try:
                file_stat = self.CACHE_FILE.stat()
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
            **self._scan_stats,
            **cache_file_info,
            "platforms": platform_stats,
            "fuzzy_threshold": self.FUZZY_THRESHOLD,
            "is_initialized": self._initialized,
            "loaded_from_disk": self._loaded_from_disk,
            "cache_max_age_days": self.CACHE_MAX_AGE_DAYS
        }

    def refresh_cache(self):
        """
        Force a cache refresh by rescanning all images.
        Useful after adding new images to LaunchBox.
        This will also update the disk cache with fresh data.
        """
        with self._lock:
            logger.info("Refreshing image cache...")
            self._image_cache.clear()
            self._title_lists.clear()
            self._scan_stats = {
                "platforms_scanned": 0,
                "images_found": 0,
                "scan_duration": 0.0,
                "cache_memory_mb": 0.0,
                "last_scan": None,
                "cache_source": "memory_scan"
            }
            self._initialized = False
            self._loaded_from_disk = False  # Force fresh scan on refresh
            self._ensure_initialized()


# Singleton instance
scanner = ImageScanner()


# Performance optimization utilities
def preload_images_async():
    """
    Preload image cache in a background thread.
    Call this on server startup to avoid blocking first request.
    """
    def _preload():
        try:
            scanner._ensure_initialized()
            logger.info("Image cache preloaded successfully")
        except Exception as e:
            logger.error(f"Failed to preload image cache: {e}")

    thread = threading.Thread(target=_preload, daemon=True)
    thread.start()
    return thread


# Testing utilities (only in development)
if __name__ == "__main__":
    # Test the scanner
    logging.basicConfig(level=logging.DEBUG)

    # Initialize scanner
    scanner._ensure_initialized()

    # Test lookups
    test_cases = [
        ("1944: The Loop Master", "Arcade MAME", "clear_logo"),
        ("Street Fighter II", "Arcade", "box_front"),
        ("Pac-Man", "Arcade", "clear_logo"),
        ("NonExistentGame", "Arcade", "clear_logo"),
    ]

    print("\n=== Image Scanner Test Results ===\n")
    for title, platform, img_type in test_cases:
        path = scanner.get_image_path(title, platform, img_type)
        status = "✓" if path else "✗"
        print(f"{status} {title} ({platform}) -> {path or 'Not found'}")

    print("\n=== Cache Statistics ===")
    stats = scanner.get_cache_stats()
    for key, value in stats.items():
        if key != "platforms":
            print(f"{key}: {value}")

    if stats.get("platforms"):
        print("\nImages per platform:")
        for platform, count in stats["platforms"].items():
            print(f"  {platform}: {count:,} images")
