#!/usr/bin/env python3
"""
LaunchBox JSON Cache Builder

Parses LaunchBox XML files and creates a JSON cache file for faster startup.
This eliminates the need for runtime XML parsing, reducing first-request latency
from 10-30 seconds to <1 second.

Usage:
    python scripts/build_launchbox_cache.py

Output:
    Creates/updates: {AA_DRIVE_ROOT}/.aa/launchbox_games.json
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone

# Add backend to path for imports
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from backend.services.launchbox_parser import LaunchBoxParser
from backend.services.image_scanner import ImageScanner

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_cache_path() -> Path:
    """Get the path for the JSON cache file."""
    aa_drive_root = os.environ.get('AA_DRIVE_ROOT', 'A:\\')
    cache_dir = Path(aa_drive_root) / '.aa'
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / 'launchbox_games.json'


def serialize_game(game) -> dict:
    """
    Serialize a Game object to a JSON-compatible dictionary.
    Includes all fields required by LoRa panel.
    """
    return {
        # Core identifiers (REQUIRED)
        'id': game.id,
        'title': game.title,
        'sort_title': game.title.lower() if game.title else '',
        
        # Metadata (REQUIRED for LoRa UI)
        'platform': game.platform,
        'year': game.year,
        'genre': game.genre,
        'developer': game.developer,
        'publisher': game.publisher,
        'region': game.region,
        
        # Artwork paths (REQUIRED for image endpoint)
        'clear_logo_path': game.clear_logo_path,
        'box_front_path': game.box_front_path,
        'screenshot_path': game.screenshot_path,
        
        # Launch info (REQUIRED for launching)
        'rom_path': game.rom_path,
        'application_path': game.application_path,
        'emulator_id': game.emulator_id,
        
        # Categories
        'categories': game.categories or [],
    }


def build_cache() -> dict:
    """
    Build the JSON cache from LaunchBox XML files.
    
    Returns:
        Cache dictionary with metadata and games list.
    """
    start_time = time.time()
    
    logger.info("Initializing LaunchBox parser...")
    parser = LaunchBoxParser()
    parser.initialize()
    
    logger.info("Initializing image scanner...")
    scanner = ImageScanner()
    scanner._ensure_initialized()
    
    # Get all games from parser
    games = parser.get_all_games()
    logger.info(f"Found {len(games)} games in LaunchBox")
    
    # Serialize all games
    logger.info("Serializing games to JSON format...")
    serialized_games = [serialize_game(game) for game in games]
    
    # Get unique platforms and genres for stats
    platforms = list(set(g['platform'] for g in serialized_games if g['platform']))
    genres = list(set(g['genre'] for g in serialized_games if g['genre']))
    
    # Build cache structure
    cache = {
        'metadata': {
            'version': '1.0',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'generator': 'build_launchbox_cache.py',
            'game_count': len(serialized_games),
            'platform_count': len(platforms),
            'genre_count': len(genres),
            'build_time_seconds': round(time.time() - start_time, 2),
        },
        'platforms': sorted(platforms),
        'genres': sorted(genres),
        'games': serialized_games,
    }
    
    return cache


def write_cache(cache: dict, path: Path) -> None:
    """Write cache to JSON file."""
    logger.info(f"Writing cache to {path}...")
    
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    
    file_size_mb = path.stat().st_size / (1024 * 1024)
    logger.info(f"Cache written: {file_size_mb:.2f} MB")


def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("LaunchBox JSON Cache Builder")
    logger.info("=" * 60)
    
    try:
        # Build cache
        cache = build_cache()
        
        # Write to file
        cache_path = get_cache_path()
        write_cache(cache, cache_path)
        
        # Summary
        logger.info("=" * 60)
        logger.info("BUILD COMPLETE")
        logger.info(f"  Games: {cache['metadata']['game_count']}")
        logger.info(f"  Platforms: {cache['metadata']['platform_count']}")
        logger.info(f"  Genres: {cache['metadata']['genre_count']}")
        logger.info(f"  Build time: {cache['metadata']['build_time_seconds']}s")
        logger.info(f"  Cache file: {cache_path}")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"Build failed: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
