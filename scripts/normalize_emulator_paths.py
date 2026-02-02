"""
Emulator Path Normalizer

Fixes hardcoded drive paths in emulator configurations to use AA_DRIVE_ROOT.
Designed to be extended for multiple emulator types.

Usage:
    python normalize_emulator_paths.py [--dry-run] [--emulator teknoparrot|all]

Supports:
    - TeknoParrot: UserProfiles/*.xml <GamePath> tags
    - (Extensible for RetroArch, MAME, etc.)
"""

import os
import re
import shutil
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import xml.etree.ElementTree as ET

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Default drive root
AA_DRIVE_ROOT = Path(os.environ.get("AA_DRIVE_ROOT", "A:\\"))

# Backup directory
BACKUP_DIR = AA_DRIVE_ROOT / "backups" / datetime.now().strftime("%Y%m%d")


def get_teknoparrot_paths() -> Tuple[Path, Path]:
    """Get TeknoParrot installation and profiles directories."""
    # Prioritize "Latest" version first
    candidates = [
        AA_DRIVE_ROOT / "Emulators" / "TeknoParrot Latest",
        AA_DRIVE_ROOT / "Emulators" / "TeknoParrot",
        AA_DRIVE_ROOT / "LaunchBox" / "Emulators" / "TeknoParrot",
    ]
    for p in candidates:
        if (p / "TeknoParrotUi.exe").exists():
            return p, p / "UserProfiles"
    # Default fallback
    return candidates[0], candidates[0] / "UserProfiles"


def backup_file(file_path: Path) -> Optional[Path]:
    """Create backup of file before modification."""
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup_name = f"{file_path.stem}_{datetime.now().strftime('%H%M%S')}{file_path.suffix}"
        backup_path = BACKUP_DIR / "teknoparrot_profiles" / backup_name
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, backup_path)
        return backup_path
    except Exception as e:
        logger.warning(f"Failed to backup {file_path}: {e}")
        return None


def normalize_path(path_str: str, target_root: Path = AA_DRIVE_ROOT) -> Tuple[str, bool]:
    """
    Normalize a path to use the target drive root.
    
    Handles:
    - D:\Roms\... -> A:\Roms\...
    - C:\Games\... -> A:\Games\... (if folder exists on A:)
    - Relative paths stay relative
    
    Returns: (normalized_path, was_changed)
    """
    if not path_str:
        return path_str, False
    
    original = path_str
    
    # Skip relative paths and UNC paths
    if not re.match(r'^[A-Za-z]:', path_str):
        return path_str, False
    
    # Extract drive letter and path
    match = re.match(r'^([A-Za-z]):(.*)$', path_str)
    if not match:
        return path_str, False
    
    source_drive, sub_path = match.groups()
    target_drive = str(target_root).rstrip('\\')[0]  # Get drive letter from AA_DRIVE_ROOT
    
    # Already on target drive
    if source_drive.upper() == target_drive.upper():
        return path_str, False
    
    # Build new path
    new_path = f"{target_drive}:{sub_path}"
    
    # Verify the new path exists (at least the parent directory)
    new_path_obj = Path(new_path)
    if new_path_obj.exists() or new_path_obj.parent.exists():
        return new_path, True
    
    # Path doesn't exist on target drive - still change it but warn
    logger.warning(f"Target path may not exist: {new_path}")
    return new_path, True


def fix_teknoparrot_profile(xml_path: Path, dry_run: bool = False) -> Dict:
    """
    Fix paths in a single TeknoParrot profile XML.
    
    Returns dict with results.
    """
    result = {
        "file": str(xml_path),
        "game_name": None,
        "changes": [],
        "backed_up": False,
        "error": None,
    }
    
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Get game name for logging (check both new and old tag names)
        game_name_elem = root.find("GameNameInternal") or root.find("GameName")
        result["game_name"] = game_name_elem.text if game_name_elem is not None else xml_path.stem
        
        # Tags that contain paths
        path_tags = ["GamePath", "SavePath", "TestMenuExtraParameters"]
        changes_made = False
        
        for tag_name in path_tags:
            elem = root.find(tag_name)
            if elem is not None and elem.text:
                new_path, changed = normalize_path(elem.text)
                if changed:
                    result["changes"].append({
                        "tag": tag_name,
                        "old": elem.text,
                        "new": new_path,
                    })
                    if not dry_run:
                        elem.text = new_path
                    changes_made = True
        
        # Write changes
        if changes_made and not dry_run:
            backup_path = backup_file(xml_path)
            result["backed_up"] = backup_path is not None
            
            # Write with same encoding
            tree.write(xml_path, encoding="utf-8", xml_declaration=True)
            
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Error processing {xml_path}: {e}")
    
    return result


def fix_teknoparrot_profiles(dry_run: bool = False) -> List[Dict]:
    """Fix all TeknoParrot profile XMLs."""
    tp_root, profiles_dir = get_teknoparrot_paths()
    
    if not profiles_dir.exists():
        logger.error(f"TeknoParrot UserProfiles not found: {profiles_dir}")
        return []
    
    logger.info(f"Scanning TeknoParrot profiles in: {profiles_dir}")
    
    results = []
    fixed_count = 0
    
    for xml_file in sorted(profiles_dir.glob("*.xml")):
        result = fix_teknoparrot_profile(xml_file, dry_run=dry_run)
        results.append(result)
        
        if result["changes"]:
            fixed_count += 1
            action = "Would fix" if dry_run else "Fixed"
            logger.info(f"{action}: {result['game_name']}")
            for change in result["changes"]:
                logger.info(f"  {change['tag']}: {change['old']} -> {change['new']}")
    
    logger.info(f"\nSummary: {fixed_count} profiles {'would be' if dry_run else ''} fixed out of {len(results)} total")
    
    if dry_run and fixed_count > 0:
        logger.info("\nRun without --dry-run to apply changes")
    
    return results


# ============================================================================
# Extensible: Add more emulator fixers here
# ============================================================================

def fix_retroarch_playlists(dry_run: bool = False) -> List[Dict]:
    """Fix paths in RetroArch playlist files (future implementation)."""
    # TODO: Implement when needed
    # RetroArch playlists are JSON files in retroarch/playlists/*.lpl
    logger.info("RetroArch playlist fixer not yet implemented")
    return []


def fix_launchbox_paths(dry_run: bool = False) -> List[Dict]:
    """Fix paths in LaunchBox configuration (future implementation)."""
    # TODO: Implement when needed
    # LaunchBox stores paths in Data/*.xml files
    logger.info("LaunchBox path fixer not yet implemented")
    return []


# ============================================================================
# CLI
# ============================================================================

EMULATOR_FIXERS = {
    "teknoparrot": fix_teknoparrot_profiles,
    "retroarch": fix_retroarch_playlists,
    "launchbox": fix_launchbox_paths,
}


def main():
    parser = argparse.ArgumentParser(
        description="Normalize emulator paths to use AA_DRIVE_ROOT"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be changed without making changes"
    )
    parser.add_argument(
        "--emulator", "-e",
        choices=list(EMULATOR_FIXERS.keys()) + ["all"],
        default="all",
        help="Which emulator configs to fix (default: all)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show verbose output"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info(f"AA_DRIVE_ROOT: {AA_DRIVE_ROOT}")
    logger.info(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    logger.info("")
    
    if args.emulator == "all":
        emulators = ["teknoparrot"]  # Start with just TP, add more as implemented
    else:
        emulators = [args.emulator]
    
    all_results = {}
    for emu in emulators:
        logger.info(f"=== Processing {emu.upper()} ===")
        fixer = EMULATOR_FIXERS.get(emu)
        if fixer:
            all_results[emu] = fixer(dry_run=args.dry_run)
        logger.info("")
    
    return all_results


if __name__ == "__main__":
    main()
