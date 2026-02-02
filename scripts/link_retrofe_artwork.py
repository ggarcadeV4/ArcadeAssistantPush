#!/usr/bin/env python3
"""
Link RetroFE artwork directories to existing LaunchBox Images.

Creates symbolic links (junctions on Windows) from RetroFE's meta/ folders
to LaunchBox's Images/ folders, so RetroFE can display existing artwork
without copying anything.

Usage:
    python link_retrofe_artwork.py

Requires: Admin privileges for creating junctions on Windows
"""

import os
import subprocess
from pathlib import Path
import json

# Paths
GAME_LIBRARY_PATH = Path(r"A:\.aa\launchbox_games.json")
RETROFE_META = Path(r"A:\Tools\RetroFE\RetroFE\meta")
LAUNCHBOX_IMAGES = Path(r"A:\LaunchBox\Images")

# Mapping: RetroFE folder name -> LaunchBox folder name
ARTWORK_MAPPING = {
    "artwork_front": "Box - Front",
    "artwork_back": "Box - Back",
    "logo": "Clear Logo",
    "screenshot": "Screenshot - Gameplay",
    "marquee": "Arcade - Marquee",
    "video": "Video",  # If LaunchBox has videos
}

# Platform name mapping: RetroFE collection name -> LaunchBox platform folder
# (Generated from our collection names back to LaunchBox platform names)


def get_platform_mapping() -> dict:
    """Build mapping from RetroFE collection names to LaunchBox platform folders."""
    # Load game library to get original platform names
    if not GAME_LIBRARY_PATH.exists():
        print(f"Warning: Game library not found: {GAME_LIBRARY_PATH}")
        return {}
    
    with open(GAME_LIBRARY_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    platforms = set()
    for game in data.get('games', []):
        platform = game.get('platform', '')
        if platform:
            platforms.add(platform)
    
    # Build mapping: sanitized name -> original name
    mapping = {}
    for platform in platforms:
        # Same sanitization as in generate_retrofe_collections.py
        import re
        safe = re.sub(r'[<>:"/\\|?*]', '', platform)
        safe = re.sub(r'\s+', '_', safe).strip()
        mapping[safe] = platform
    
    return mapping


def create_junction(link_path: Path, target_path: Path) -> bool:
    """Create a directory junction (Windows) or symlink (Linux)."""
    if link_path.exists():
        # Already exists - skip
        return True
    
    try:
        # On Windows, use mklink /J for directory junctions
        if os.name == 'nt':
            # mklink /J link target
            result = subprocess.run(
                ['cmd', '/c', 'mklink', '/J', str(link_path), str(target_path)],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        else:
            # On Linux/Mac, use symlink
            link_path.symlink_to(target_path)
            return True
    except Exception as e:
        print(f"    Error creating link: {e}")
        return False


def link_artwork_for_platform(retrofe_collection: str, launchbox_platform: str) -> dict:
    """Create artwork links for a single platform."""
    stats = {"created": 0, "skipped": 0, "failed": 0}
    
    lb_platform_dir = LAUNCHBOX_IMAGES / launchbox_platform
    if not lb_platform_dir.exists():
        print(f"  Warning: LaunchBox folder not found: {lb_platform_dir}")
        return stats
    
    retrofe_platform_dir = RETROFE_META / retrofe_collection
    retrofe_platform_dir.mkdir(parents=True, exist_ok=True)
    
    for retrofe_name, lb_name in ARTWORK_MAPPING.items():
        lb_art_dir = lb_platform_dir / lb_name
        retrofe_art_link = retrofe_platform_dir / retrofe_name
        
        if not lb_art_dir.exists():
            # LaunchBox doesn't have this artwork type for this platform
            continue
        
        if retrofe_art_link.exists():
            stats["skipped"] += 1
            continue
        
        # Remove the directory we created earlier (if empty)
        if retrofe_art_link.is_dir():
            try:
                retrofe_art_link.rmdir()
            except OSError:
                pass  # Not empty, skip
        
        if create_junction(retrofe_art_link, lb_art_dir):
            stats["created"] += 1
        else:
            stats["failed"] += 1
    
    return stats


def main():
    print("=" * 60)
    print("RetroFE Artwork Linker")
    print("=" * 60)
    print(f"\nLinking from: {LAUNCHBOX_IMAGES}")
    print(f"Linking to:   {RETROFE_META}")
    
    # Get platform mapping
    print("\nBuilding platform mapping...")
    platform_map = get_platform_mapping()
    print(f"  Found {len(platform_map)} platforms")
    
    # Process each platform
    print("\nCreating artwork links...")
    total_created = 0
    total_skipped = 0
    total_failed = 0
    
    for retrofe_name, lb_name in sorted(platform_map.items()):
        stats = link_artwork_for_platform(retrofe_name, lb_name)
        total_created += stats["created"]
        total_skipped += stats["skipped"]
        total_failed += stats["failed"]
        
        if stats["created"] > 0:
            print(f"  {retrofe_name}: {stats['created']} links created")
    
    print("\n" + "=" * 60)
    print("DONE!")
    print("=" * 60)
    print(f"\nLinks created: {total_created}")
    print(f"Links skipped (already exist): {total_skipped}")
    print(f"Links failed: {total_failed}")
    
    if total_failed > 0:
        print("\nNote: Some links failed. Try running as Administrator.")


if __name__ == "__main__":
    main()
