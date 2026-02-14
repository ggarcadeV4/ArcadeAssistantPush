"""
TeknoParrot Direct Loader Adapter

This adapter launches TeknoParrot games by directly invoking the appropriate
loader executable (BudgieLoader, OpenParrotLoader, etc.) based on the game's
EmulatorType in its GameProfile XML.

Architecture:
- Pegasus → AA Backend → This Adapter → Direct Loader → Game
- No TeknoParrotUi.exe in the launch chain
- Reads EmulatorType from GameProfiles/{profile}.xml
- Selects correct loader and builds command line
- Logs all launch attempts to state/teknoparrot_launches.jsonl
"""

from __future__ import annotations

import json
import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.constants.a_drive_paths import LaunchBoxPaths

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Emulator Type → Loader Mapping
# -----------------------------------------------------------------------------

EMULATOR_LOADERS = {
    # Type: (loader_subdir, loader_exe, is_64bit)
    "Lindbergh": ("TeknoParrot", "BudgieLoader.exe", False),
    "OpenParrot": ("OpenParrotWin32", "OpenParrotLoader.exe", False),
    "OpenParrotx64": ("OpenParrotx64", "OpenParrotLoader64.exe", True),
    "N2": ("N2", "BudgieLoader.exe", False),
    "ElfLdr2": ("ElfLdr2", "BudgieLoader.exe", False),
    "RingEdge": ("TeknoParrot", "BudgieLoader.exe", False),
    "RingEdge2": ("TeknoParrot", "BudgieLoader.exe", False),
    "RingWide": ("TeknoParrot", "BudgieLoader.exe", False),
    "Europa": ("TeknoParrot", "BudgieLoader.exe", False),
    "EuropaR": ("TeknoParrot", "BudgieLoader.exe", False),
    "SegaToolsIDZ": ("SegaTools", None, False),  # Special handling
    "TeknoParrot": ("TeknoParrot", "BudgieLoader.exe", False),  # Generic fallback
}

# Platforms that this adapter handles
TEKNOPARROT_PLATFORMS = {
    "TeknoParrot",
    "TeknoParrot Arcade", 
    "Taito Type X",
    "Taito Type X2",
    "Taito Type X3",
    "Sega Lindbergh",
    "Sega RingEdge",
    "Sega RingEdge 2",
    "Sega RingWide",
    "Sega Europa-R",
    "Namco System N2",
    "Namco System ES3",
}


def _get_teknoparrot_root() -> Path:
    """Get TeknoParrot installation directory."""
    candidates = [
        LaunchBoxPaths.EMULATORS_ROOT / "TeknoParrot Latest",
        LaunchBoxPaths.EMULATORS_ROOT / "TeknoParrot",
        LaunchBoxPaths.LAUNCHBOX_ROOT / "Emulators" / "TeknoParrot",
    ]
    for p in candidates:
        if (p / "TeknoParrotUi.exe").exists():
            return p
    return candidates[0]


def _get_game_profile_path(profile_name: str) -> Optional[Path]:
    """Get the GameProfile XML path for a profile."""
    tp_root = _get_teknoparrot_root()
    # Try with and without .xml extension
    name = profile_name.replace(".xml", "")
    candidates = [
        tp_root / "GameProfiles" / f"{name}.xml",
        tp_root / "UserProfiles" / f"{name}.xml",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _get_user_profile_path(profile_name: str) -> Optional[Path]:
    """Get the UserProfile XML path (contains GamePath)."""
    tp_root = _get_teknoparrot_root()
    name = profile_name.replace(".xml", "")
    path = tp_root / "UserProfiles" / f"{name}.xml"
    return path if path.exists() else None


def _read_emulator_type(profile_name: str) -> Optional[str]:
    """Read EmulatorType from GameProfile XML."""
    game_profile = _get_game_profile_path(profile_name)
    if not game_profile:
        return None
    try:
        tree = ET.parse(game_profile)
        root = tree.getroot()
        elem = root.find("EmulatorType")
        if elem is not None and elem.text:
            return elem.text.strip()
    except Exception as e:
        logger.warning(f"Failed to read EmulatorType from {game_profile}: {e}")
    return None


def _read_game_path(profile_name: str) -> Optional[str]:
    """Read GamePath from UserProfile XML."""
    user_profile = _get_user_profile_path(profile_name)
    if not user_profile:
        return None
    try:
        tree = ET.parse(user_profile)
        root = tree.getroot()
        elem = root.find("GamePath")
        if elem is not None and elem.text:
            return elem.text.strip()
    except Exception as e:
        logger.warning(f"Failed to read GamePath from {user_profile}: {e}")
    return None


def _read_game_name(profile_name: str) -> Optional[str]:
    """Read game name from UserProfile XML."""
    user_profile = _get_user_profile_path(profile_name)
    if not user_profile:
        return None
    try:
        tree = ET.parse(user_profile)
        root = tree.getroot()
        for tag in ("GameNameInternal", "GameName"):
            elem = root.find(tag)
            if elem is not None and elem.text:
                return elem.text.strip()
    except Exception:
        pass
    return None


def _get_loader_path(emulator_type: str) -> Optional[Path]:
    """Get the loader executable path for an emulator type."""
    tp_root = _get_teknoparrot_root()
    
    loader_info = EMULATOR_LOADERS.get(emulator_type)
    if not loader_info:
        # Try OpenParrot as default for unknown types
        loader_info = EMULATOR_LOADERS.get("OpenParrot")
    
    if not loader_info or loader_info[1] is None:
        return None
    
    subdir, exe_name, _ = loader_info
    loader_path = tp_root / subdir / exe_name
    
    if loader_path.exists():
        return loader_path
    
    logger.warning(f"Loader not found: {loader_path}")
    return None


def _log_launch_attempt(
    profile: str,
    game_name: Optional[str],
    emulator_type: Optional[str],
    loader_path: Optional[Path],
    game_path: Optional[str],
    command: Optional[List[str]],
    success: bool,
    error: Optional[str] = None
) -> None:
    """Log launch attempt to state/teknoparrot_launches.jsonl"""
    try:
        state_dir = Path(LaunchBoxPaths.AA_DRIVE_ROOT) / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        log_file = state_dir / "teknoparrot_launches.jsonl"
        
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "profile": profile,
            "game_name": game_name,
            "emulator_type": emulator_type,
            "loader_path": str(loader_path) if loader_path else None,
            "game_path": game_path,
            "command": command,
            "success": success,
            "error": error,
        }
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"Failed to log launch attempt: {e}")


def can_handle(game: Any, manifest: Dict[str, Any]) -> bool:
    """Check if this adapter can handle the game."""
    platform = getattr(game, "platform", None) or ""
    
    # Check if platform matches
    if platform in TEKNOPARROT_PLATFORMS:
        return True
    
    # Check for TeknoParrot in platform name
    if "teknoparrot" in platform.lower():
        return True
    
    # Check for Taito Type X
    if "taito" in platform.lower() and "type" in platform.lower():
        return True
    
    return False


def find_profile_for_title(title: str) -> Optional[str]:
    """Find TeknoParrot profile matching a game title."""
    # Import universal adapter's profile finder
    try:
        from backend.services.adapters import teknoparrot_universal_adapter
        return teknoparrot_universal_adapter.find_profile(title)
    except Exception as e:
        logger.warning(f"Failed to find profile for '{title}': {e}")
        return None


def resolve(game: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve TeknoParrot launch configuration using direct loader.
    
    Returns dict with:
    - exe: Path to loader executable
    - args: Arguments (game path)
    - cwd: Working directory
    - profile: Profile name used
    - emulator_type: Type from GameProfile
    - game_name: Display name
    """
    title = getattr(game, "title", "") or ""
    
    if not title:
        return {
            "success": False,
            "message": "Game title is empty",
            "error_code": "title_empty",
        }
    
    # Find profile for this game
    profile = find_profile_for_title(title)
    if not profile:
        _log_launch_attempt(
            profile="",
            game_name=title,
            emulator_type=None,
            loader_path=None,
            game_path=None,
            command=None,
            success=False,
            error=f"No profile found for '{title}'"
        )
        return {
            "success": False,
            "message": f"No TeknoParrot profile found for '{title}'",
            "error_code": "missing_profile",
        }
    
    # Read emulator type
    emulator_type = _read_emulator_type(profile)
    if not emulator_type:
        logger.warning(f"No EmulatorType found for profile '{profile}', defaulting to OpenParrot")
        emulator_type = "OpenParrot"
    
    # Read game path
    game_path = _read_game_path(profile)
    if not game_path:
        _log_launch_attempt(
            profile=profile,
            game_name=title,
            emulator_type=emulator_type,
            loader_path=None,
            game_path=None,
            command=None,
            success=False,
            error="GamePath not configured in profile"
        )
        return {
            "success": False,
            "message": f"GamePath not configured in profile '{profile}'",
            "error_code": "config_unresolved",
        }
    
    # Check game path exists
    if not Path(game_path).exists():
        _log_launch_attempt(
            profile=profile,
            game_name=title,
            emulator_type=emulator_type,
            loader_path=None,
            game_path=game_path,
            command=None,
            success=False,
            error=f"Game file not found: {game_path}"
        )
        return {
            "success": False,
            "message": f"Game file not found: {game_path}",
            "error_code": "exe_not_found",
        }
    
    # Get loader path
    loader_path = _get_loader_path(emulator_type)
    if not loader_path:
        _log_launch_attempt(
            profile=profile,
            game_name=title,
            emulator_type=emulator_type,
            loader_path=None,
            game_path=game_path,
            command=None,
            success=False,
            error=f"Loader not found for EmulatorType '{emulator_type}'"
        )
        return {
            "success": False,
            "message": f"Loader not found for EmulatorType '{emulator_type}'",
            "error_code": "exe_not_found",
        }
    
    # Build command
    game_name = _read_game_name(profile) or title
    command = [str(loader_path), game_path]
    
    # Log successful resolution
    _log_launch_attempt(
        profile=profile,
        game_name=game_name,
        emulator_type=emulator_type,
        loader_path=loader_path,
        game_path=game_path,
        command=command,
        success=True,
    )
    
    logger.info(f"[TeknoParrot Direct] Resolved: {game_name}")
    logger.info(f"  Profile: {profile}")
    logger.info(f"  EmulatorType: {emulator_type}")
    logger.info(f"  Loader: {loader_path}")
    logger.info(f"  GamePath: {game_path}")
    
    return {
        "exe": str(loader_path),
        "args": [game_path],
        "cwd": str(loader_path.parent),
        "profile": profile,
        "emulator_type": emulator_type,
        "game_name": game_name,
        "adapter": "teknoparrot_direct",
    }


def launch(game: Any, manifest: Dict[str, Any], runner=None) -> Dict[str, Any]:
    """Launch a TeknoParrot game via direct loader."""
    cfg = resolve(game, manifest)
    
    if not cfg.get("exe"):
        return cfg  # Return error from resolve
    
    # The actual execution is handled by the launcher service
    # We just return the resolved config
    return cfg
