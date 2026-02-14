"""
TeknoParrot Universal Adapter

Scans TeknoParrot UserProfiles/*.xml to build a runtime cache of game names,
eliminating the need for manual alias mapping.

Architecture:
- Pegasus → AA Backend → This Adapter → TeknoParrot
- No brittle per-game aliases required
- Matches by <GameName> field in profile XML
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import os
import re
import logging
from difflib import SequenceMatcher

from backend.constants.a_drive_paths import LaunchBoxPaths

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Profile Cache (built on first use, refreshed if directory mtime changes)
# -----------------------------------------------------------------------------

_PROFILE_CACHE: Optional[Dict[str, str]] = None  # {game_name_lower: profile_stem}
_PROFILE_CACHE_MTIME: Optional[float] = None
_PROFILE_DIR: Optional[Path] = None


def _get_teknoparrot_root() -> Path:
    """Find TeknoParrot installation directory."""
    # Prioritize "Latest" version first
    candidates = [
        LaunchBoxPaths.EMULATORS_ROOT / "TeknoParrot Latest",
        LaunchBoxPaths.EMULATORS_ROOT / "TeknoParrot",
        LaunchBoxPaths.LAUNCHBOX_ROOT / "Emulators" / "TeknoParrot",
    ]
    for p in candidates:
        if (p / "TeknoParrotUi.exe").exists():
            return p
    # Default fallback
    return LaunchBoxPaths.EMULATORS_ROOT / "TeknoParrot"


def _get_profiles_dir() -> Path:
    """Get UserProfiles directory."""
    return _get_teknoparrot_root() / "UserProfiles"


def _parse_game_name_from_xml(xml_path: Path) -> Optional[str]:
    """Extract game name from a TeknoParrot profile XML.
    
    Checks both <GameName> (older versions) and <GameNameInternal> (newer versions).
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        # Try newer format first (GameNameInternal), then older (GameName)
        for tag in ("GameNameInternal", "GameName"):
            elem = root.find(tag)
            if elem is not None and elem.text:
                return elem.text.strip()
    except Exception as e:
        logger.debug(f"Failed to parse {xml_path}: {e}")
    return None


def _build_profile_cache() -> Dict[str, str]:
    """
    Scan all UserProfiles/*.xml and build a mapping:
    {game_name_lower: profile_filename_stem}
    
    Example:
    {"after burner climax": "abc", "akai katana shin": "AkaiKatanaShinNesica"}
    """
    global _PROFILE_CACHE, _PROFILE_CACHE_MTIME, _PROFILE_DIR
    
    profiles_dir = _get_profiles_dir()
    _PROFILE_DIR = profiles_dir
    
    if not profiles_dir.exists():
        logger.warning(f"TeknoParrot UserProfiles not found: {profiles_dir}")
        return {}
    
    cache: Dict[str, str] = {}
    profile_count = 0
    
    for xml_file in profiles_dir.glob("*.xml"):
        game_name = _parse_game_name_from_xml(xml_file)
        if game_name:
            # Store lowercase for case-insensitive matching
            cache[game_name.lower()] = xml_file.stem
            profile_count += 1
            logger.debug(f"Cached profile: '{game_name}' -> {xml_file.stem}")
    
    logger.info(f"TeknoParrot profile cache built: {profile_count} profiles from {profiles_dir}")
    
    try:
        _PROFILE_CACHE_MTIME = profiles_dir.stat().st_mtime
    except Exception:
        _PROFILE_CACHE_MTIME = None
    
    return cache


def _get_profile_cache() -> Dict[str, str]:
    """Get or refresh the profile cache."""
    global _PROFILE_CACHE, _PROFILE_CACHE_MTIME, _PROFILE_DIR
    
    profiles_dir = _get_profiles_dir()
    
    # Check if cache needs refresh
    try:
        current_mtime = profiles_dir.stat().st_mtime
        if _PROFILE_CACHE is not None and _PROFILE_CACHE_MTIME == current_mtime:
            return _PROFILE_CACHE
    except Exception:
        pass
    
    # Rebuild cache
    _PROFILE_CACHE = _build_profile_cache()
    return _PROFILE_CACHE


def _normalize_title(title: str) -> str:
    """Normalize title for matching (lowercase, remove special chars)."""
    # Remove common suffixes/prefixes that might differ
    normalized = title.lower().strip()
    # Remove special characters but keep spaces
    normalized = re.sub(r'[^\w\s]', '', normalized)
    # Collapse multiple spaces
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized


def _fuzzy_match(title: str, cache: Dict[str, str], threshold: float = 0.85) -> Optional[str]:
    """
    Find best matching profile using fuzzy string matching.
    Returns profile stem if match found above threshold.
    """
    normalized_title = _normalize_title(title)
    best_match = None
    best_ratio = 0.0
    
    for game_name, profile_stem in cache.items():
        normalized_game = _normalize_title(game_name)
        
        # Try exact normalized match first
        if normalized_title == normalized_game:
            return profile_stem
        
        # Check if one contains the other
        if normalized_title in normalized_game or normalized_game in normalized_title:
            ratio = 0.9  # High confidence for containment
        else:
            # Fuzzy ratio
            ratio = SequenceMatcher(None, normalized_title, normalized_game).ratio()
        
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = profile_stem
    
    if best_ratio >= threshold:
        logger.info(f"Fuzzy matched '{title}' -> '{best_match}' (ratio: {best_ratio:.2f})")
        return best_match
    
    return None


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def find_profile(title: str) -> Optional[str]:
    """
    Find TeknoParrot profile for a game title.
    
    Searches by:
    1. Exact match on <GameName>
    2. Fuzzy match with high threshold
    
    Returns profile filename (without .xml) or None.
    """
    if not title:
        return None
    
    cache = _get_profile_cache()
    title_lower = title.lower().strip()
    
    # 1. Exact match
    if title_lower in cache:
        logger.debug(f"Exact match: '{title}' -> {cache[title_lower]}")
        return cache[title_lower]
    
    # 2. Fuzzy match
    fuzzy_result = _fuzzy_match(title, cache)
    if fuzzy_result:
        return fuzzy_result
    
    logger.warning(f"No TeknoParrot profile found for: '{title}'")
    return None


def can_handle(game: Any, manifest: Dict[str, Any]) -> bool:
    """
    Check if this adapter can handle the game.
    
    Returns True for platforms routed to TeknoParrot.
    """
    platform = ""
    if isinstance(game, dict):
        platform = game.get("platform", "")
    else:
        platform = getattr(game, "platform", "") or ""
    
    platform_lower = platform.lower().strip()
    
    # Platforms that use TeknoParrot
    tp_platforms = {
        "teknoparrot arcade",
        "teknoparrot",
        "taito type x",
        "taito type x2",
        "taito type x3",
        "sega lindbergh",
        "sega ringedge",
        "sega ringedge 2",
        "sega ringwide",
        "sega nu",
        "namco system es1",
        "namco system es3",
        "namco system 357",
        "examu exboard",
    }
    
    return platform_lower in tp_platforms


def resolve(game: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve TeknoParrot launch configuration.
    
    Returns:
        Dict with exe, args, cwd, adapter, profile keys
        Or error dict with error_code
    """
    # Get game title
    title = ""
    if isinstance(game, dict):
        title = game.get("title", "")
    else:
        title = getattr(game, "title", "") or ""
    
    title = title.strip()
    if not title:
        return {
            "success": False,
            "message": "Game title is empty",
            "error_code": "title_empty",
            "adapter": "teknoparrot_universal",
        }
    
    # Find profile
    profile = find_profile(title)
    if not profile:
        return {
            "success": False,
            "message": f"No TeknoParrot profile found for '{title}'",
            "error_code": "profile_not_found",
            "adapter": "teknoparrot_universal",
        }
    
    # Get TeknoParrot exe
    tp_root = _get_teknoparrot_root()
    tp_exe = tp_root / "TeknoParrotUi.exe"
    
    if not tp_exe.exists():
        return {
            "success": False,
            "message": f"TeknoParrotUi.exe not found at {tp_exe}",
            "error_code": "exe_not_found",
            "adapter": "teknoparrot_universal",
        }
    
    # Build launch command
    # TeknoParrot uses: TeknoParrotUi.exe -run --profile=ProfileName.xml
    profile_arg = f"{profile}.xml"
    args = f'-run --profile={profile_arg}'
    
    # Use cmd.exe /c start for proper window handling (drive-letter agnostic)
    exe = os.environ.get("COMSPEC", "cmd.exe")
    full_args = f'/c start /D "{tp_root}" "" "{tp_exe}" {args}'
    
    return {
        "success": True,
        "exe": exe,
        "args": full_args,
        "cwd": str(tp_root),
        "adapter": "teknoparrot_universal",
        "profile": profile,
        "emulator": "TeknoParrot",
        "command": f'{exe} {full_args}',
    }


def launch(game: Any, manifest: Dict[str, Any], runner: Any) -> Dict[str, Any]:
    """
    Launch a TeknoParrot game.
    
    Returns structured result with adapter/emulator metadata.
    """
    cfg = resolve(game, manifest)
    
    if not cfg.get("success", False):
        return cfg
    
    # Run the launch
    result = runner.run(cfg)
    
    # Enrich result with adapter metadata
    if isinstance(result, dict):
        result["adapter"] = "teknoparrot_universal"
        result["profile"] = cfg.get("profile")
        result["emulator"] = "TeknoParrot"
    
    return result


def get_all_profiles() -> List[Dict[str, str]]:
    """
    Get all cached profiles for diagnostics.
    
    Returns list of {game_name, profile_stem} dicts.
    """
    cache = _get_profile_cache()
    return [
        {"game_name": name, "profile": stem}
        for name, stem in sorted(cache.items())
    ]


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics for health endpoint."""
    cache = _get_profile_cache()
    return {
        "profile_count": len(cache),
        "profiles_dir": str(_get_profiles_dir()),
        "cache_mtime": _PROFILE_CACHE_MTIME,
    }
