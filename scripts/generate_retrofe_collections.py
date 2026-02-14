#!/usr/bin/env python3
"""
Generate RetroFE collections from Arcade Assistant game library.

This script reads the game library JSON (originally from LaunchBox)
and generates RetroFE-compatible collections with:
- menu.txt files (game lists using sanitized titles for artwork matching)
- settings.conf (launcher configuration + media paths to LaunchBox Images)
- include.txt (title display mappings)

Key Design Decisions:
1. menu.txt uses SANITIZED GAME TITLES (not UUIDs) so RetroFE can find artwork
   - LaunchBox files are named like "1942-01.png" (title + suffix)
   - RetroFE looks for artwork matching menu item names
2. settings.conf has media.* paths pointing directly to LaunchBox Images folders
3. Launch bridge resolves title -> ID -> emulator launch

Usage:
    python generate_retrofe_collections.py

Output:
    A:\\Tools\\RetroFE\\RetroFE\\collections\\  (platform folders)
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any, Tuple
import re

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Paths - using A: drive directly (no env var needed for this standalone script)
GAME_LIBRARY_PATH = Path(r"A:\.aa\launchbox_games.json")
RETROFE_ROOT = Path(r"A:\Tools\RetroFE\RetroFE")
COLLECTIONS_DIR = RETROFE_ROOT / "collections"
LAUNCHERS_DIR = RETROFE_ROOT / "launchers.windows"

# LaunchBox paths
LAUNCHBOX_ROOT = Path(r"A:\LaunchBox")
LAUNCHBOX_IMAGES = LAUNCHBOX_ROOT / "Images"

# Arcade Assistant paths
AA_ROOT = Path(r"A:\Arcade Assistant Local")
AA_LAUNCHER = AA_ROOT / "scripts" / "aa_launch.bat"

# RetroFE media key -> LaunchBox subfolder mapping
MEDIA_MAPPING = {
    "media.artwork_front": "Box - Front",
    "media.artwork_back": "Box - Back",
    "media.logo": "Clear Logo",
    "media.screenshot": "Screenshot - Gameplay",
    "media.video": "Videos",
    "media.marquee": "Arcade - Marquee",
    "media.fanart": "Fanart",
}


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def sanitize_for_menu(name: str) -> str:
    """Sanitize game title for use in menu.txt.
    
    RetroFE uses the menu item name to look up artwork files.
    This should match LaunchBox's file naming (minus the -01 suffix).
    """
    if not name:
        return ""
    # Remove characters that are invalid in filenames
    safe = re.sub(r'[<>:"/\\|?*]', '', name)
    # Normalize whitespace
    safe = re.sub(r'\s+', ' ', safe)
    return safe.strip()


def sanitize_collection_name(platform: str) -> str:
    """Convert platform name to safe folder name for collections."""
    safe = re.sub(r'[<>:"/\\|?*]', '', platform)
    safe = re.sub(r'\s+', '_', safe)
    return safe.strip()


def load_game_library() -> Dict[str, Any]:
    """Load the game library JSON."""
    if not GAME_LIBRARY_PATH.exists():
        raise FileNotFoundError(f"Game library not found: {GAME_LIBRARY_PATH}")
    
    with open(GAME_LIBRARY_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def group_by_platform(games: List[Dict]) -> Dict[str, List[Dict]]:
    """Group games by platform."""
    platforms: Dict[str, List[Dict]] = {}
    for game in games:
        platform = game.get('platform', 'Unknown')
        if platform not in platforms:
            platforms[platform] = []
        platforms[platform].append(game)
    return platforms


# ==============================================================================
# SETTINGS.CONF MANAGEMENT (Idempotent)
# ==============================================================================

def parse_settings_conf(content: str) -> Tuple[Dict[str, str], List[str]]:
    """Parse settings.conf into key-value pairs and preserve comments/structure.
    
    Returns:
        Tuple of (settings_dict, original_lines)
    """
    settings = {}
    lines = content.split('\n')
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and '=' in stripped:
            key, value = stripped.split('=', 1)
            settings[key.strip()] = value.strip()
    return settings, lines


def write_media_settings(collection_dir: Path, platform: str) -> None:
    """Write/merge media.* paths into settings.conf (idempotent).
    
    This function:
    1. Reads existing settings.conf if present
    2. Updates/adds only media.* keys
    3. Preserves other settings
    4. Is safe to run multiple times
    """
    settings_path = collection_dir / "settings.conf"
    collection_name = collection_dir.name
    
    # Compute LaunchBox image paths for this platform
    lb_platform_images = LAUNCHBOX_IMAGES / platform
    
    # Build new media paths
    new_media = {}
    for retrofe_key, lb_subfolder in MEDIA_MAPPING.items():
        lb_path = lb_platform_images / lb_subfolder
        # Use forward slashes (RetroFE handles both on Windows)
        new_media[retrofe_key] = str(lb_path).replace('\\', '/')
    
    # Read existing settings if file exists
    existing_settings = {}
    if settings_path.exists():
        with open(settings_path, 'r', encoding='utf-8') as f:
            existing_settings, _ = parse_settings_conf(f.read())
    
    # Merge: keep existing non-media settings, update media settings
    merged = {}
    for key, value in existing_settings.items():
        if not key.startswith('media.'):
            merged[key] = value
    merged.update(new_media)
    
    # Write the file
    with open(settings_path, 'w', encoding='utf-8') as f:
        f.write(f"# RetroFE collection for {platform}\n")
        f.write(f"# Generated by Arcade Assistant\n")
        f.write(f"# Collection: {collection_name}\n\n")
        
        # Write standard settings first
        f.write("# Core settings\n")
        f.write(f"list.includeMissingItems = {merged.get('list.includeMissingItems', 'true')}\n")
        f.write(f"list.menuSort = {merged.get('list.menuSort', 'true')}\n")
        f.write(f"launcher = {merged.get('launcher', 'arcade_assistant')}\n\n")
        
        # Write media paths
        f.write("# ========================================\n")
        f.write("# Media paths - pointing to LaunchBox Images\n")
        f.write("# (No symlinks or copying required)\n")
        f.write("# ========================================\n")
        for key in sorted(new_media.keys()):
            f.write(f"{key} = {new_media[key]}\n")


# ==============================================================================
# COLLECTION CREATION
# ==============================================================================

def create_collection(platform: str, games: List[Dict]) -> None:
    """Create a RetroFE collection for a platform.
    
    Key change: menu.txt now uses SANITIZED GAME TITLES instead of UUIDs.
    This allows RetroFE to find artwork files (which are named by title).
    """
    collection_name = sanitize_collection_name(platform)
    collection_dir = COLLECTIONS_DIR / collection_name
    collection_dir.mkdir(parents=True, exist_ok=True)
    
    # Sort games for consistent output
    sorted_games = sorted(games, key=lambda x: x.get('sort_title', x.get('title', '')))
    
    # Build title -> ID mapping for launch bridge
    title_to_id: Dict[str, str] = {}
    
    # Create menu.txt using SANITIZED TITLES (for artwork matching)
    menu_path = collection_dir / "menu.txt"
    with open(menu_path, 'w', encoding='utf-8') as f:
        for game in sorted_games:
            game_id = game.get('id', '')
            title = game.get('title', '')
            
            if not title:
                continue
                
            # Use sanitized title as menu item (RetroFE uses this to find artwork)
            sanitized_title = sanitize_for_menu(title)
            if sanitized_title:
                f.write(f"{sanitized_title}\n")
                title_to_id[sanitized_title] = game_id
    
    # Write/merge media settings into settings.conf (idempotent)
    write_media_settings(collection_dir, platform)
    
    # Create title_map.json for launch bridge (title -> game ID lookup)
    title_map_path = collection_dir / "title_map.json"
    with open(title_map_path, 'w', encoding='utf-8') as f:
        json.dump(title_to_id, f, indent=2, ensure_ascii=False)
    
    print(f"  Created collection: {collection_name} ({len(sorted_games)} games)")


def create_main_menu(platforms: Dict[str, List[Dict]]) -> None:
    """Create the main menu collection."""
    main_dir = COLLECTIONS_DIR / "Main"
    main_dir.mkdir(parents=True, exist_ok=True)
    
    sorted_platforms = sorted(platforms.keys())
    
    # Create menu.txt (list of collections)
    menu_path = main_dir / "menu.txt"
    with open(menu_path, 'w', encoding='utf-8') as f:
        for platform in sorted_platforms:
            collection_name = sanitize_collection_name(platform)
            f.write(f"{collection_name}\n")
    
    # Create settings.conf for Main menu
    settings_path = main_dir / "settings.conf"
    with open(settings_path, 'w', encoding='utf-8') as f:
        f.write("# Main Menu - Generated by Arcade Assistant\n\n")
        f.write("# This is the root menu showing all platforms\n")
        f.write("list.includeMissingItems = true\n")
        f.write("list.menuSort = true\n")
    
    print(f"  Created Main menu with {len(sorted_platforms)} platforms")


def create_launcher_config() -> None:
    """Create the Arcade Assistant launcher configuration."""
    LAUNCHERS_DIR.mkdir(parents=True, exist_ok=True)
    
    launcher_path = LAUNCHERS_DIR / "arcade_assistant.conf"
    with open(launcher_path, 'w', encoding='utf-8') as f:
        f.write("# Arcade Assistant Launcher\n")
        f.write("# Routes game launches through Arcade Assistant backend\n\n")
        f.write('executable = cmd.exe\n')
        f.write(f'arguments = /c "{AA_LAUNCHER}" "%ITEM%" "%COLLECTION%"\n')
    
    print(f"  Created launcher config: {launcher_path}")


def create_launch_bridge() -> None:
    """Create the launch bridge batch script.
    
    Updated to accept both game name and collection name,
    and resolve via title_map.json for accurate game ID lookup.
    """
    AA_LAUNCHER.parent.mkdir(parents=True, exist_ok=True)
    
    with open(AA_LAUNCHER, 'w', encoding='utf-8') as f:
        f.write('@echo off\n')
        f.write('REM Arcade Assistant Launch Bridge\n')
        f.write('REM Called by RetroFE with game title and collection as arguments\n')
        f.write('REM Resolves title to game ID via title_map.json, then launches\n\n')
        f.write('setlocal EnableDelayedExpansion\n\n')
        f.write('set "GAME_TITLE=%~1"\n')
        f.write('set "COLLECTION=%~2"\n')
        f.write('echo RetroFE Launch: "%GAME_TITLE%" from collection "%COLLECTION%"\n\n')
        f.write('REM Call backend API with title (backend resolves to game ID)\n')
        f.write('curl -s -X POST "http://localhost:8787/api/launchbox/launch-by-title" ^\n')
        f.write('  -H "Content-Type: application/json" ^\n')
        f.write('  -H "x-panel: retrofe" ^\n')
        f.write('  -d "{\\"title\\": \\"%GAME_TITLE%\\", \\"collection\\": \\"%COLLECTION%\\"}"\n')
    
    print(f"  Created launch bridge: {AA_LAUNCHER}")


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

def main():
    """Main entry point."""
    print("=" * 60)
    print("RetroFE Collection Generator")
    print("=" * 60)
    
    # Load game library
    print(f"\nLoading game library from {GAME_LIBRARY_PATH}...")
    data = load_game_library()
    games = data.get('games', [])
    print(f"  Loaded {len(games)} games")
    
    # Group by platform
    print("\nGrouping games by platform...")
    platforms = group_by_platform(games)
    print(f"  Found {len(platforms)} platforms")
    
    # Create collections
    print("\nCreating RetroFE collections...")
    for platform, platform_games in platforms.items():
        create_collection(platform, platform_games)
    
    # Create main menu
    print("\nCreating main menu...")
    create_main_menu(platforms)
    
    # Create launcher config
    print("\nCreating launcher configuration...")
    create_launcher_config()
    
    # Create launch bridge
    print("\nCreating launch bridge script...")
    create_launch_bridge()
    
    print("\n" + "=" * 60)
    print("DONE!")
    print("=" * 60)
    print(f"\nRetroFE collections created at: {COLLECTIONS_DIR}")
    print(f"Total platforms: {len(platforms)}")
    print(f"Total games: {len(games)}")
    print("\nKey changes in this version:")
    print("1. menu.txt uses SANITIZED TITLES (not UUIDs) for artwork matching")
    print("2. settings.conf has media.* paths pointing to LaunchBox Images")
    print("3. title_map.json created for launch resolution")
    print("\nNext steps:")
    print("1. Run RetroFE to test artwork display")
    print("2. If artwork still missing, check LaunchBox file naming conventions")


if __name__ == "__main__":
    main()
