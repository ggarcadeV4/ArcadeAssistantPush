#!/usr/bin/env python3
"""
Generate Pegasus metadata files from LaunchBox game library.

This script reads the existing launchbox_games.json and creates
metadata.pegasus.txt files for each platform that Pegasus can read.

Usage:
    python generate_pegasus_metadata.py [--platform "Arcade MAME"] [--dry-run]

Output:
    A:\Tools\Pegasus\metadata\{platform}\metadata.pegasus.txt
"""

import os
import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Derive all paths from AA_DRIVE_ROOT for cloned drive support
AA_DRIVE_ROOT = Path(os.environ.get("AA_DRIVE_ROOT", "A:\\"))
LAUNCHBOX_IMAGES = AA_DRIVE_ROOT / "LaunchBox" / "Images"
LAUNCHBOX_VIDEOS = AA_DRIVE_ROOT / "LaunchBox" / "Videos"
PEGASUS_ROOT = AA_DRIVE_ROOT / "Tools" / "Pegasus"
PEGASUS_METADATA = PEGASUS_ROOT / "metadata"
GAME_LIBRARY_PATH = AA_DRIVE_ROOT / ".aa" / "launchbox_games.json"
AA_LAUNCH_SCRIPT = AA_DRIVE_ROOT / "Arcade Assistant Local" / "scripts" / "aa_launch_pegasus_simple.bat"

# Collection artwork folder - place custom logos here
# Naming: {collection_name}_logo.png, {collection_name}_poster.png, etc.
COLLECTION_ARTWORK_DIR = AA_DRIVE_ROOT / "Tools" / "Pegasus" / "collection_artwork"

# Pegasus asset type -> LaunchBox folder name(s) (in priority order)
ASSET_MAP = {
    "boxFront": ["Box - Front", "Box - Front - Reconstructed"],
    "logo": ["Clear Logo"],
    "screenshot": ["Screenshot - Gameplay", "Screenshot - Game Title"],
    "marquee": ["Arcade - Marquee", "Banner"],
    "background": ["Fanart - Background", "Fanart"],
    "video": ["Videos"],
}


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def sanitize_collection_name(platform: str) -> str:
    """Convert platform name to safe folder name."""
    safe = re.sub(r'[<>:"/\\|?*]', '', platform)
    safe = re.sub(r'\s+', '_', safe)
    return safe.strip().lower()


def escape_pegasus_value(value: str) -> str:
    """Escape special characters for Pegasus metadata values."""
    if not value:
        return ""
    # Multi-line values need to be indented
    lines = value.split('\n')
    if len(lines) > 1:
        # First line as-is, subsequent lines indented with 2 spaces
        return lines[0] + '\n' + '\n'.join('  ' + line for line in lines[1:])
    return value


def find_asset_folder(platform: str, asset_type: str) -> Optional[Path]:
    """Find the LaunchBox folder for a given asset type."""
    folder_names = ASSET_MAP.get(asset_type, [])
    
    for folder_name in folder_names:
        if asset_type == "video":
            # Videos are in a different location
            path = LAUNCHBOX_VIDEOS / platform
        else:
            path = LAUNCHBOX_IMAGES / platform / folder_name
        
        if path.exists():
            return path
    
    return None


def load_game_library() -> Dict[str, List[Dict[str, Any]]]:
    """Load and group games by platform from the game library."""
    if not GAME_LIBRARY_PATH.exists():
        print(f"[ERROR] Game library not found: {GAME_LIBRARY_PATH}")
        return {}
    
    try:
        with open(GAME_LIBRARY_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load game library: {e}")
        return {}
    
    # Group games by platform
    games_by_platform: Dict[str, List[Dict[str, Any]]] = {}
    
    for game in data.get('games', []):
        platform = game.get('platform', 'Unknown')
        if platform not in games_by_platform:
            games_by_platform[platform] = []
        games_by_platform[platform].append(game)
    
    return games_by_platform


def find_collection_artwork(collection_name: str) -> Dict[str, Optional[str]]:
    """Find custom artwork for a collection.
    
    Looks in COLLECTION_ARTWORK_DIR for files named:
    - {collection_name}_logo.png (or .jpg)
    - {collection_name}_poster.png
    - {collection_name}_background.png
    - {collection_name}_banner.png
    
    Also checks LaunchBox platform images as fallback.
    """
    assets = {"logo": None, "poster": None, "background": None, "banner": None}
    safe_name = sanitize_collection_name(collection_name)
    
    # Check custom artwork folder first
    if COLLECTION_ARTWORK_DIR.exists():
        for asset_type in assets.keys():
            for ext in ['.png', '.jpg', '.jpeg', '.webp']:
                candidate = COLLECTION_ARTWORK_DIR / f"{safe_name}_{asset_type}{ext}"
                if candidate.exists():
                    assets[asset_type] = str(candidate).replace('\\', '/')
                    break
    
    # Fallback: Check LaunchBox platform images
    if not assets["logo"]:
        lb_platform_logos = LAUNCHBOX_IMAGES / collection_name / "Clear Logo"
        if lb_platform_logos.exists():
            # Look for any image in the folder
            for f in lb_platform_logos.iterdir():
                if f.suffix.lower() in ['.png', '.jpg', '.jpeg']:
                    assets["logo"] = str(f).replace('\\', '/')
                    break
    
    if not assets["banner"]:
        lb_banners = LAUNCHBOX_IMAGES / collection_name / "Banner"
        if lb_banners.exists():
            for f in lb_banners.iterdir():
                if f.suffix.lower() in ['.png', '.jpg', '.jpeg']:
                    assets["banner"] = str(f).replace('\\', '/')
                    break
    
    return assets


def generate_collection_header(platform: str, game_count: int) -> List[str]:
    """Generate the collection header for metadata.pegasus.txt."""
    
    # Find collection artwork
    artwork = find_collection_artwork(platform)
    
    lines = [
        f"# Pegasus metadata for {platform}",
        f"# Generated by Arcade Assistant on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"# Games: {game_count}",
        "",
        f"collection: {platform}",
        # NOTE: Pegasus only supports {file.path}, not {file.stem}. The batch script extracts the title.
        f'launch: A:\\Tools\\aa_pegasus.bat "{{file.path}}" "{platform}"',
    ]
    
    # Add collection-level artwork if found
    if artwork["logo"]:
        lines.append(f"assets.logo: {artwork['logo']}")
    if artwork["poster"]:
        lines.append(f"assets.poster: {artwork['poster']}")
    if artwork["banner"]:
        lines.append(f"assets.banner: {artwork['banner']}")
    if artwork["background"]:
        lines.append(f"assets.background: {artwork['background']}")
    
    lines.extend([
        "",
        "# " + "=" * 70,
        "# Games",
        "# " + "=" * 70,
        "",
    ])
    
    return lines


def find_game_asset(platform: str, asset_type: str, game_title: str) -> Optional[str]:
    """Find a specific game's asset file from LaunchBox.
    
    Handles LaunchBox naming conventions like -01, -02 suffixes.
    """
    folder = find_asset_folder(platform, asset_type)
    if not folder or not folder.exists():
        return None
    
    # Normalize game title for matching
    def normalize(s: str) -> str:
        s = s.replace(':', '_').replace('-', ' ')
        s = re.sub(r'[<>"/\\|?*\']', '', s)
        return re.sub(r'\s+', ' ', s).lower().strip()
    
    target = normalize(game_title)
    
    # Search in main folder and region subfolders
    folders_to_check = [folder]
    for region in ['North America', 'United States', 'Europe', 'Japan', 'World']:
        region_path = folder / region
        if region_path.exists():
            folders_to_check.append(region_path)
    
    for check_folder in folders_to_check:
        try:
            for file in check_folder.iterdir():
                if not file.is_file():
                    continue
                if file.suffix.lower() not in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.mkv', '.avi']:
                    continue
                
                # Strip -01, -02 etc suffixes
                stem = file.stem
                stem = re.sub(r'-0?\d+$', '', stem)
                
                if normalize(stem) == target:
                    return str(file).replace('\\', '/')
        except (PermissionError, OSError):
            continue
    
    return None


def generate_game_entry(game: Dict[str, Any], collection_dir: Path, platform: str, dry_run: bool = False) -> List[str]:
    """Generate metadata lines for a single game.
    
    Creates a placeholder .game file that Pegasus will accept.
    Includes per-game asset paths for artwork discovery.
    """
    lines = []
    
    title = game.get('title', 'Unknown')
    game_id = game.get('id', title)
    
    # Create a safe filename for the placeholder
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', title)
    safe_name = re.sub(r'\s+', ' ', safe_name).strip()
    placeholder_file = f"{safe_name}.game"
    
    # Create the placeholder file if not dry run
    if not dry_run:
        try:
            placeholder_path = collection_dir / placeholder_file
            # Write game info to placeholder (useful for debugging)
            placeholder_path.write_text(f"# Arcade Assistant Game Placeholder\n# Title: {title}\n# ID: {game_id}\n", encoding='utf-8')
        except Exception as e:
            print(f"    [WARN] Could not create placeholder for {title}: {e}")
    
    lines.append(f"game: {title}")
    lines.append(f"file: {placeholder_file}")
    lines.append(f"x-aa-guid: {game_id}")
    
    # Per-game assets
    asset_types = [
        ("boxFront", "boxFront"),
        ("logo", "logo"),
        ("screenshot", "screenshot"),
        ("marquee", "marquee"),
        ("background", "background"),
        ("video", "video"),
    ]
    
    for pegasus_name, asset_key in asset_types:
        asset_path = find_game_asset(platform, asset_key, title)
        if asset_path:
            lines.append(f"assets.{pegasus_name}: {asset_path}")
    
    # Developer
    if game.get('developer'):
        lines.append(f"developer: {game['developer']}")
    
    # Publisher
    if game.get('publisher'):
        lines.append(f"publisher: {game['publisher']}")
    
    # Release year
    if game.get('year'):
        lines.append(f"release: {game['year']}")
    
    # Genre
    if game.get('genre'):
        lines.append(f"genre: {game['genre']}")
    
    # Players
    if game.get('players'):
        lines.append(f"players: {game['players']}")
    
    # Rating (convert from 0-5 to percentage)
    if game.get('rating'):
        try:
            rating_pct = int(float(game['rating']) * 20)
            lines.append(f"rating: {rating_pct}%")
        except:
            pass
    
    # Description
    if game.get('description'):
        desc = escape_pegasus_value(game['description'][:500])  # Limit length
        lines.append(f"description: {desc}")
    
    lines.append("")  # Blank line between games
    
    return lines


# ==============================================================================
# MAIN PROCESSING
# ==============================================================================

def generate_platform_metadata(platform: str, games: List[Dict[str, Any]], dry_run: bool = False) -> int:
    """Generate metadata.pegasus.txt for a single platform."""
    collection_name = sanitize_collection_name(platform)
    output_dir = PEGASUS_METADATA / collection_name
    output_file = output_dir / "metadata.pegasus.txt"
    
    print(f"\nProcessing: {platform}")
    print(f"  Games: {len(games)}")
    print(f"  Output: {output_file}")
    
    # Create output directory first (needed for placeholder files)
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate metadata content
    lines = generate_collection_header(platform, len(games))
    
    for game in sorted(games, key=lambda g: g.get('title', '')):
        lines.extend(generate_game_entry(game, output_dir, platform, dry_run))
    
    if dry_run:
        print(f"  [DRY-RUN] Would write {len(lines)} lines and {len(games)} placeholder files")
        # Show first 20 lines as preview
        print("  --- Preview ---")
        for line in lines[:20]:
            print(f"    {line}")
        print("  ...")
        return len(games)
    
    # Create directory and write file
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        print(f"  ✓ Written: {output_file}")
        return len(games)
    except Exception as e:
        print(f"  [ERROR] Failed to write: {e}")
        return 0


def create_launch_bridge(dry_run: bool = False) -> bool:
    """Create the AA launch bridge script for Pegasus."""
    
    script_content = '''@echo off
REM ============================================
REM Arcade Assistant - Pegasus Launch Bridge
REM ============================================
REM This script is called by Pegasus to launch games.
REM It routes the request through the AA backend.
REM
REM Usage: aa_launch_pegasus.bat "game_file" "platform"

set "GAME_FILE=%~1"
set "PLATFORM=%~2"

echo Pegasus Launch: "%GAME_FILE%" from "%PLATFORM%"

REM Call backend API with game info
curl -s -X POST "http://localhost:8787/api/launchbox/launch-by-title" ^
  -H "Content-Type: application/json" ^
  -H "x-panel: pegasus" ^
  -d "{\\"title\\": \\"%GAME_FILE%\\", \\"collection\\": \\"%PLATFORM%\\"}"
'''
    
    if dry_run:
        print(f"\n[DRY-RUN] Would create launch bridge: {AA_LAUNCH_SCRIPT}")
        return True
    
    try:
        AA_LAUNCH_SCRIPT.parent.mkdir(parents=True, exist_ok=True)
        with open(AA_LAUNCH_SCRIPT, 'w', encoding='utf-8') as f:
            f.write(script_content)
        print(f"\n✓ Created launch bridge: {AA_LAUNCH_SCRIPT}")
        return True
    except Exception as e:
        print(f"\n[ERROR] Failed to create launch bridge: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Generate Pegasus metadata from LaunchBox")
    parser.add_argument("--platform", "-p", help="Process only this platform (default: all)")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would be done")
    parser.add_argument("--skip-bridge", action="store_true", help="Skip creating launch bridge script")
    args = parser.parse_args()
    
    print("=" * 60)
    print("Pegasus Metadata Generator")
    print("=" * 60)
    
    if args.dry_run:
        print("\n*** DRY RUN MODE - No changes will be made ***")
    
    # Load game library
    print(f"\nLoading game library: {GAME_LIBRARY_PATH}")
    games_by_platform = load_game_library()
    
    if not games_by_platform:
        print("[ERROR] No games found in library")
        return 1
    
    total_platforms = len(games_by_platform)
    total_games = sum(len(games) for games in games_by_platform.values())
    print(f"Found {total_games} games across {total_platforms} platforms")
    
    # Create launch bridge
    if not args.skip_bridge:
        create_launch_bridge(args.dry_run)
    
    # Filter platforms if specified
    if args.platform:
        if args.platform not in games_by_platform:
            print(f"[ERROR] Platform not found: {args.platform}")
            print(f"Available platforms: {', '.join(sorted(games_by_platform.keys())[:10])}...")
            return 1
        platforms_to_process = {args.platform: games_by_platform[args.platform]}
    else:
        platforms_to_process = games_by_platform
    
    # Generate metadata for each platform
    total_generated = 0
    platforms_processed = 0
    
    for platform, games in sorted(platforms_to_process.items()):
        count = generate_platform_metadata(platform, games, args.dry_run)
        total_generated += count
        platforms_processed += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Platforms processed: {platforms_processed}")
    print(f"Total games: {total_generated}")
    print(f"Metadata location: {PEGASUS_METADATA}")
    
    if args.dry_run:
        print("\n*** This was a dry run. Use without --dry-run to apply changes. ***")
    else:
        print("\n✓ Pegasus metadata generated successfully!")
        print("\nNext steps:")
        print("1. Launch Pegasus to verify games appear")
        print("2. Check artwork is displaying correctly")
        print("3. Test launching a game")
    
    return 0


if __name__ == "__main__":
    exit(main())
