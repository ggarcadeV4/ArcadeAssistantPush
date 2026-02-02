#!/usr/bin/env python3
"""
Clear all cache files for LaunchBox parser and image scanner.
Use this to force a fresh scan on next startup.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.launchbox_parser import parser
from backend.services.image_scanner import scanner

def clear_all_caches():
    """Clear all cache files."""

    print("="*60)
    print("CLEARING CACHE FILES")
    print("="*60)

    # Parser cache
    parser_cache = parser.PARSER_CACHE_FILE
    if parser_cache.exists():
        size_mb = parser_cache.stat().st_size / (1024 * 1024)
        parser_cache.unlink()
        print(f"[DELETED] Parser cache: {parser_cache}")
        print(f"          Size: {size_mb:.2f} MB")
    else:
        print(f"[SKIP] Parser cache not found: {parser_cache}")

    # Image scanner cache
    image_cache = scanner.CACHE_FILE
    if image_cache.exists():
        size_mb = image_cache.stat().st_size / (1024 * 1024)
        image_cache.unlink()
        print(f"[DELETED] Image cache: {image_cache}")
        print(f"          Size: {size_mb:.2f} MB")
    else:
        print(f"[SKIP] Image cache not found: {image_cache}")

    print("\n[DONE] All caches cleared.")
    print("Next startup will perform full scan from XML/filesystem.")
    print("="*60)

if __name__ == "__main__":
    clear_all_caches()