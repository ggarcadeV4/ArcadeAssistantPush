#!/usr/bin/env python3
"""
Test script for LaunchBox parser disk caching.
Run this to verify caching is working correctly.
"""

import sys
import os
import time
from pathlib import Path
from datetime import datetime

# Add parent directory to path so we can import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup environment
os.environ.setdefault("AA_DRIVE_ROOT", str(Path(__file__).parent.parent))

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from backend.services.launchbox_parser import parser

def test_parser_caching():
    """Test parser disk caching functionality."""

    print("\n" + "="*80)
    print("LAUNCHBOX PARSER DISK CACHE TEST")
    print("="*80 + "\n")

    # Check if cache file exists before initialization
    cache_file = parser.PARSER_CACHE_FILE
    cache_existed = cache_file.exists()

    if cache_existed:
        print(f"[OK] Cache file exists: {cache_file}")
        print(f"  Size: {cache_file.stat().st_size / (1024*1024):.2f} MB")
        print(f"  Modified: {datetime.fromtimestamp(cache_file.stat().st_mtime)}")
    else:
        print(f"[--] No cache file found at: {cache_file}")
        print("  First run will create cache from XML parse")

    print("\n" + "-"*40)
    print("INITIALIZING PARSER...")
    print("-"*40)

    # Time the initialization
    start_time = time.time()
    parser.initialize()
    elapsed = time.time() - start_time

    print(f"\n[TIME] Initialization took: {elapsed:.2f} seconds")

    # Get cache statistics
    stats = parser.get_cache_stats()

    print("\n" + "-"*40)
    print("CACHE STATISTICS:")
    print("-"*40)

    print(f"Cache Source: {stats['cache_source']}")
    print(f"Loaded from Disk: {stats['loaded_from_disk']}")
    print(f"Total Games: {stats['total_games']:,}")
    print(f"Platforms: {stats['platforms_count']}")
    print(f"Genres: {stats['genres_count']}")
    print(f"XML Files Parsed: {stats['xml_files_parsed']}")
    print(f"Mock Data: {stats['is_mock_data']}")
    print(f"Cache File Exists: {stats.get('cache_file_exists', False)}")

    if stats.get('cache_file_exists'):
        print(f"Cache File Size: {stats['cache_file_size_mb']:.2f} MB")

    # Test some queries to verify data integrity
    print("\n" + "-"*40)
    print("TESTING DATA INTEGRITY:")
    print("-"*40)

    # Get all games
    games = parser.get_all_games()
    print(f"[OK] get_all_games() returned {len(games)} games")

    # Get platforms
    platforms = parser.get_platforms()
    print(f"[OK] get_platforms() returned {len(platforms)} platforms")
    if platforms[:5]:
        print(f"  Sample: {platforms[:5]}")

    # Get genres
    genres = parser.get_genres()
    print(f"[OK] get_genres() returned {len(genres)} genres")
    if genres[:5]:
        print(f"  Sample: {genres[:5]}")

    # Test filtering
    if games:
        # Filter by first available platform
        if platforms:
            platform_games = parser.filter_games(platform=platforms[0])
            print(f"[OK] filter_games(platform='{platforms[0]}') returned {len(platform_games)} games")

        # Get a random game
        random_game = parser.get_random_game()
        if random_game:
            print(f"[OK] get_random_game() returned: {random_game.title} ({random_game.platform})")

    # Performance comparison
    print("\n" + "-"*40)
    print("PERFORMANCE SUMMARY:")
    print("-"*40)

    if stats['loaded_from_disk']:
        print("[CACHED] Cache was loaded from disk (fast startup)")
        print(f"   Initialization: {elapsed:.2f}s")
        print("   Expected for cold start (no cache): ~10s")
        print("   Expected for warm start (with cache): ~2-3s")
    else:
        print("[PARSED] Cache was built from XML parse (first run)")
        print(f"   Initialization: {elapsed:.2f}s")
        print("   Next startup will be faster using disk cache")

    # Check if cache file was created
    if not cache_existed and cache_file.exists():
        print(f"\n[CREATED] Cache file created: {cache_file}")
        print(f"   Size: {cache_file.stat().st_size / (1024*1024):.2f} MB")

    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80 + "\n")

if __name__ == "__main__":
    test_parser_caching()