#!/usr/bin/env python3
"""
Flatten LaunchBox artwork for RetroFE compatibility.

This script creates a flattened media structure that RetroFE can read,
using symbolic links (junctions on Windows) to avoid duplicating files.

Problem:
  - LaunchBox stores images like: Images/Arcade MAME/Box - Front/North America/1942-01.png
  - RetroFE expects: collections/Arcade_MAME/medium_artwork/front/1942.png

Solution:
  - Create a flat 'media' folder structure under RetroFE
  - Use symbolic links to LaunchBox images
  - Strip the -01, -02 suffixes (use first match)
  - Flatten region subfolders

Usage:
    python flatten_retrofe_artwork.py [--platform "Arcade MAME"] [--dry-run]

Output:
    A:\Tools\RetroFE\RetroFE\media\{Platform}\{media_type}\{GameTitle}.{ext}
"""

import os
import re
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Set
import subprocess

# ==============================================================================
# CONFIGURATION
# ==============================================================================

LAUNCHBOX_IMAGES = Path(r"A:\LaunchBox\Images")
RETROFE_ROOT = Path(r"A:\Tools\RetroFE\RetroFE")
RETROFE_MEDIA = RETROFE_ROOT / "media"
GAME_LIBRARY_PATH = Path(r"A:\.aa\launchbox_games.json")

# Map RetroFE media type -> LaunchBox folder name
MEDIA_TYPE_MAP = {
    "artwork_front": ["Box - Front", "Box - Front - Reconstructed"],
    "artwork_back": ["Box - Back", "Box - Back - Reconstructed"],
    "logo": ["Clear Logo"],
    "screenshot": ["Screenshot - Gameplay", "Screenshot - Game Title"],
    "marquee": ["Arcade - Marquee", "Banner"],
    "fanart": ["Fanart - Background", "Fanart"],
    "video": ["Videos"],
}

# Common region subfolder names to check
REGION_FOLDERS = [
    "North America", "United States", "USA",
    "World", "Europe", "Japan", "Asia",
    "Australia", "Germany", "France", "UK",
    "Korea", "China", "Hong Kong", "Brazil",
]


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def sanitize_collection_name(platform: str) -> str:
    """Convert platform name to RetroFE collection folder name."""
    safe = re.sub(r'[<>:"/\\|?*]', '', platform)
    safe = re.sub(r'\s+', '_', safe)
    return safe.strip()


def strip_suffix(filename: str) -> str:
    """Strip -01, -02 etc. suffixes from LaunchBox image names.
    
    LaunchBox names images like 'Game Title-01.png', 'Game Title-02.png'
    We want just 'Game Title' for RetroFE matching.
    """
    stem = Path(filename).stem
    ext = Path(filename).suffix
    
    # Match pattern: ends with -01, -02, -03, etc.
    match = re.match(r'^(.+?)-0*\d+$', stem)
    if match:
        return match.group(1) + ext
    return filename


def normalize_for_matching(text: str) -> str:
    """Normalize a string for matching between menu.txt and filenames.
    
    LaunchBox converts : to _ in filenames, and may have other differences.
    This normalizes both sides for comparison.
    """
    # Replace colons with underscores (LaunchBox does this)
    text = text.replace(':', '_')
    # Normalize hyphens - some files use spaces instead
    text = text.replace('-', ' ')
    # Normalize apostrophes and quotes
    text = text.replace("'", "")
    text = text.replace('"', "")
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove other problematic characters
    text = re.sub(r'[<>"/\\|?*]', '', text)
    # Lowercase for comparison
    return text.lower().strip()


def find_best_image(folder: Path, game_title: str) -> Optional[Path]:
    """Find the best matching image for a game title.
    
    Checks the folder and any region subfolders.
    Returns the first match found (preferring direct folder, then North America).
    """
    if not folder.exists():
        return None
    
    # Normalize the game title for matching
    normalized_title = normalize_for_matching(game_title)
    
    # Check priority: direct folder first, then region folders in order
    folders_to_check = [folder]
    for region in REGION_FOLDERS:
        region_path = folder / region
        if region_path.exists():
            folders_to_check.append(region_path)
    
    for check_folder in folders_to_check:
        try:
            for file in check_folder.iterdir():
                if not file.is_file():
                    continue
                if file.suffix.lower() not in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                    continue
                
                # Strip suffix and normalize for comparison
                clean_name = strip_suffix(file.name)
                clean_stem = Path(clean_name).stem
                normalized_stem = normalize_for_matching(clean_stem)
                
                if normalized_stem == normalized_title:
                    return file
        except PermissionError:
            continue
    
    return None


def create_junction(source: Path, target: Path, dry_run: bool = False) -> bool:
    """Create a Windows junction (symbolic link for directories not needed here).
    
    For files, we'll create a hard link or copy.
    Actually, for artwork, we'll create a symbolic link to the file.
    """
    if dry_run:
        print(f"  [DRY-RUN] Would link: {target.name} -> {source}")
        return True
    
    try:
        # Ensure parent directory exists
        target.parent.mkdir(parents=True, exist_ok=True)
        
        # Remove existing link/file if present
        if target.exists() or target.is_symlink():
            target.unlink()
        
        # Create symbolic link (requires admin or developer mode on Windows)
        # Fall back to hard link if symlink fails
        try:
            target.symlink_to(source)
        except OSError:
            # Try hard link instead (works for files on same drive)
            try:
                os.link(source, target)
            except OSError:
                # Last resort: create a small text file pointing to source
                # (This won't work for actual images, but logs the intent)
                print(f"  [WARN] Could not create link for {target.name}, skipping")
                return False
        
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to create link for {target.name}: {e}")
        return False


def load_game_titles(platform: str) -> Set[str]:
    """Load game titles for a platform from the game library."""
    titles = set()
    
    if not GAME_LIBRARY_PATH.exists():
        return titles
    
    try:
        with open(GAME_LIBRARY_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        for game in data.get('games', []):
            if game.get('platform') == platform:
                title = game.get('title', '')
                if title:
                    titles.add(title)
    except Exception as e:
        print(f"[WARN] Could not load game library: {e}")
    
    return titles


# ==============================================================================
# MAIN PROCESSING
# ==============================================================================

def process_platform(platform: str, dry_run: bool = False) -> Dict[str, int]:
    """Process artwork for a single platform."""
    stats = {
        "games": 0,
        "links_created": 0,
        "already_exists": 0,
        "not_found": 0,
        "errors": 0,
    }
    
    collection_name = sanitize_collection_name(platform)
    lb_platform_folder = LAUNCHBOX_IMAGES / platform
    rfe_media_folder = RETROFE_MEDIA / collection_name
    
    print(f"\nProcessing: {platform}")
    print(f"  LaunchBox: {lb_platform_folder}")
    print(f"  RetroFE:   {rfe_media_folder}")
    
    if not lb_platform_folder.exists():
        print(f"  [SKIP] LaunchBox folder not found")
        return stats
    
    # Load game titles
    game_titles = load_game_titles(platform)
    if not game_titles:
        # Fall back to reading menu.txt
        menu_file = RETROFE_ROOT / "collections" / collection_name / "menu.txt"
        if menu_file.exists():
            with open(menu_file, 'r', encoding='utf-8') as f:
                game_titles = {line.strip() for line in f if line.strip()}
    
    stats["games"] = len(game_titles)
    print(f"  Games: {len(game_titles)}")
    
    # Process each media type
    for media_type, lb_folders in MEDIA_TYPE_MAP.items():
        type_folder = rfe_media_folder / media_type
        links_for_type = 0
        
        for game_title in game_titles:
            # Try each possible LaunchBox folder for this media type
            source_found = None
            for lb_folder_name in lb_folders:
                lb_folder = lb_platform_folder / lb_folder_name
                source = find_best_image(lb_folder, game_title)
                if source:
                    source_found = source
                    break
            
            if source_found:
                # Create the target filename (clean, no suffix)
                target_name = game_title + source_found.suffix.lower()
                # Sanitize for filesystem
                target_name = re.sub(r'[<>:"/\\|?*]', '', target_name)
                target = type_folder / target_name
                
                if target.exists():
                    stats["already_exists"] += 1
                elif create_junction(source_found, target, dry_run):
                    stats["links_created"] += 1
                    links_for_type += 1
                else:
                    stats["errors"] += 1
            else:
                stats["not_found"] += 1
        
        if links_for_type > 0:
            print(f"  {media_type}: {links_for_type} links created")
    
    return stats


def update_settings_conf(platform: str, dry_run: bool = False) -> bool:
    """Update the collection's settings.conf to use the new media paths."""
    collection_name = sanitize_collection_name(platform)
    settings_path = RETROFE_ROOT / "collections" / collection_name / "settings.conf"
    
    if not settings_path.exists():
        print(f"  [SKIP] No settings.conf found for {collection_name}")
        return False
    
    new_media_base = RETROFE_MEDIA / collection_name
    
    new_lines = [
        f"# RetroFE collection for {platform}",
        f"# Generated by Arcade Assistant",
        f"# Collection: {collection_name}",
        f"# Artwork: Flattened structure with symlinks to LaunchBox",
        "",
        "# Core settings",
        "list.includeMissingItems = true",
        "list.menuSort = true",
        "launcher = arcade_assistant",
        "",
        "# ========================================",
        "# Media paths - Flattened for RetroFE",
        "# (Symlinks to LaunchBox Images)",
        "# ========================================",
        f"media.artwork_front = {str(new_media_base / 'artwork_front').replace(os.sep, '/')}",
        f"media.artwork_back = {str(new_media_base / 'artwork_back').replace(os.sep, '/')}",
        f"media.logo = {str(new_media_base / 'logo').replace(os.sep, '/')}",
        f"media.screenshot = {str(new_media_base / 'screenshot').replace(os.sep, '/')}",
        f"media.marquee = {str(new_media_base / 'marquee').replace(os.sep, '/')}",
        f"media.fanart = {str(new_media_base / 'fanart').replace(os.sep, '/')}",
        f"media.video = {str(new_media_base / 'video').replace(os.sep, '/')}",
        "",
    ]
    
    if dry_run:
        print(f"  [DRY-RUN] Would update: {settings_path}")
        return True
    
    try:
        # Backup first
        backup_path = settings_path.with_suffix('.conf.bak')
        if settings_path.exists():
            import shutil
            shutil.copy2(settings_path, backup_path)
        
        with open(settings_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        
        print(f"  Updated: {settings_path}")
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to update settings.conf: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Flatten LaunchBox artwork for RetroFE")
    parser.add_argument("--platform", "-p", help="Process only this platform (default: all)")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--update-settings", "-u", action="store_true", help="Update settings.conf files")
    args = parser.parse_args()
    
    print("=" * 60)
    print("RetroFE Artwork Flattening Tool")
    print("=" * 60)
    
    if args.dry_run:
        print("\n*** DRY RUN MODE - No changes will be made ***\n")
    
    # Get list of platforms to process
    if args.platform:
        platforms = [args.platform]
    else:
        # Get all platforms from collections folder
        collections_dir = RETROFE_ROOT / "collections"
        platforms = []
        if collections_dir.exists():
            for d in collections_dir.iterdir():
                if d.is_dir() and d.name != "Main":
                    # Convert underscore back to space for LaunchBox lookup
                    platforms.append(d.name.replace("_", " "))
    
    print(f"Platforms to process: {len(platforms)}")
    
    total_stats = {
        "platforms": 0,
        "games": 0,
        "links_created": 0,
        "not_found": 0,
        "errors": 0,
    }
    
    for platform in platforms:
        stats = process_platform(platform, args.dry_run)
        total_stats["platforms"] += 1
        total_stats["games"] += stats["games"]
        total_stats["links_created"] += stats["links_created"]
        total_stats["not_found"] += stats["not_found"]
        total_stats["errors"] += stats["errors"]
        
        if args.update_settings:
            update_settings_conf(platform, args.dry_run)
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Platforms processed: {total_stats['platforms']}")
    print(f"Total games: {total_stats['games']}")
    print(f"Links created: {total_stats['links_created']}")
    print(f"Images not found: {total_stats['not_found']}")
    print(f"Errors: {total_stats['errors']}")
    
    if args.dry_run:
        print("\n*** This was a dry run. Use without --dry-run to apply changes. ***")


if __name__ == "__main__":
    main()
