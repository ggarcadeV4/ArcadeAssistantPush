"""
Hypseus (Modern Daphne) Adapter for Arcade Assistant.

Launches Hypseus games using the correct command format:
  hypseus.exe <rom_name> vldp -framefile "<path/to/framefile.txt>" -fullscreen -xinput

Hypseus is the modern fork of Daphne that supports laserdisc games like:
- Dragon's Lair
- Space Ace
- Batman (Sega/Taito)
- Cliff Hanger
- etc.

Module interface (adapter pattern):
  - can_handle(game, manifest) -> bool
  - is_enabled(manifest) -> bool
  - resolve(game, manifest) -> Dict[str, Any]
  - launch(game, manifest, runner) -> Dict[str, Any]
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import platform
import re
import os
import logging

from backend.constants.a_drive_paths import LaunchBoxPaths

logger = logging.getLogger(__name__)


# Structured error codes for diagnostics
class HypseusAdapterError:
    """Structured error codes for Hypseus adapter failures."""
    EXE_NOT_FOUND = "exe_not_found"
    FRAMEFILE_NOT_FOUND = "framefile_not_found"
    INVALID_FRAMEFILE = "invalid_framefile"
    CONFIG_UNRESOLVED = "config_unresolved"
    ROM_PATH_MISSING = "rom_path_missing"


@dataclass
class HypseusConfig:
    """Configuration for launching a Hypseus game."""
    exe: Path
    rom_name: str  # e.g., "lair", "batman"
    framefile: Path  # Full path to .txt or .m2v file
    flags: List[str]


def _is_wsl() -> bool:
    return platform.system() == "Linux" and "microsoft" in platform.release().lower()


def _norm_path(p: str) -> Path:
    """Normalize A:/ style paths to /mnt/a when under WSL; leave Windows paths on Windows."""
    if not p:
        return Path("")
    s = p.replace("\\", "/")
    if _is_wsl():
        s = s.replace("A:/", "/mnt/a/")
        m = re.match(r"^([A-Za-z]):/(.*)$", s)
        if m:
            s = f"/mnt/{m.group(1).lower()}/{m.group(2)}"
    return Path(s)


def _get(obj: Any, key: str) -> Optional[str]:
    """Get attribute or dict key from a Game-like object."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _get_hypseus_config(manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Get Hypseus configuration from manifest."""
    if not manifest:
        return None
    # Support multiple schema shapes: emulators, launchers, or top-level
    for key in ("emulators", "launchers"):
        block = manifest.get(key)
        if isinstance(block, dict):
            # Try hypseus first, then daphne as alias
            for emu_key in ("hypseus", "daphne"):
                if isinstance(block.get(emu_key), dict):
                    return block.get(emu_key)
    # Top-level keys
    for emu_key in ("hypseus", "daphne"):
        if isinstance(manifest.get(emu_key), dict):
            return manifest.get(emu_key)
    return None


def can_handle(game: Any, manifest: Dict[str, Any]) -> bool:
    """Check if this adapter can handle the given game.
    
    Matches platforms: "Daphne", "Hypseus", "Laserdisc"
    Also checks for .txt or .m2v file extensions in the ROM path.
    """
    plat = (_get(game, "platform") or "").strip().lower()

    # Many Daphne entries in this build are AHK launch wrappers; those should
    # route to direct_app_adapter instead of Hypseus framefile mode.
    rom_path = _get(game, "rom_path") or _get(game, "application_path") or ""
    if rom_path:
        ext = Path(str(rom_path)).suffix.lower()
        if ext in (".ahk", ".bat", ".cmd"):
            return False
    
    # Match platform names
    if any(term in plat for term in ("daphne", "hypseus", "laserdisc")):
        return True
    
    # Check manifest for platform list
    cfg = _get_hypseus_config(manifest)
    if cfg:
        platforms = cfg.get("platforms", [])
        if isinstance(platforms, list):
            plat_original = (_get(game, "platform") or "").strip()
            if plat_original in platforms:
                return True
    
    # Check file extension (.txt framefile or .m2v video)
    rom_path = _get(game, "rom_path") or _get(game, "application_path") or ""
    if rom_path:
        ext = Path(str(rom_path)).suffix.lower()
        if ext in (".txt", ".m2v"):
            return True
    
    return False


def is_enabled(manifest: Dict[str, Any]) -> bool:
    """Check if Hypseus adapter is enabled. Always enabled for laserdisc games."""
    return True


def _find_hypseus_exe(manifest: Optional[Dict[str, Any]] = None) -> Optional[Path]:
    """Find Hypseus executable in standard locations.
    
    Search order:
    1. Manifest (launchers.json): emulators.hypseus.exe or emulators.daphne.exe
    2. A:/Emulators/Hypseus/hypseus.exe
    3. A:/Emulators/Hypseus Singe/hypseus.exe  
    4. A:/Emulators/Daphne/hypseus.exe (upgraded Daphne installation)
    5. A:/LaunchBox/Emulators/Hypseus/hypseus.exe
    """
    # Try manifest first
    if manifest:
        cfg = _get_hypseus_config(manifest)
        if cfg:
            exe_path = cfg.get("exe")
            if exe_path:
                p = _norm_path(str(exe_path))
                if p.exists():
                    return p    # Standard locations
    candidates = [
        LaunchBoxPaths.EMULATORS_ROOT / "Hypseus" / "hypseus.exe",
        LaunchBoxPaths.EMULATORS_ROOT / "Hypseus" / "Hypseus Singe" / "hypseus.exe",
        LaunchBoxPaths.EMULATORS_ROOT / "Hypseus Singe" / "hypseus.exe",
        LaunchBoxPaths.EMULATORS_ROOT / "Daphne" / "hypseus.exe",
        LaunchBoxPaths.LAUNCHBOX_ROOT / "Emulators" / "Hypseus" / "hypseus.exe",
        LaunchBoxPaths.LAUNCHBOX_ROOT / "Emulators" / "Hypseus" / "Hypseus Singe" / "hypseus.exe",
        LaunchBoxPaths.LAUNCHBOX_ROOT / "Emulators" / "Hypseus Singe" / "hypseus.exe",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate
    
    return None


def _parse_rom_name(framefile_path: Path) -> str:
    """Extract ROM name from framefile path.
    
    Examples:
        lair.txt -> lair
        batman.m2v -> batman
        Dragon's Lair.txt -> lair (special case)
    """
    stem = framefile_path.stem.lower()
    
    # Handle known special cases (LaunchBox may use full game names)
    special_mappings = {
        "dragon's lair": "lair",
        "dragons lair": "lair",
        "dragonlair": "lair",
        "space ace": "ace",
        "spaceace": "ace",
        "cliff hanger": "cliff",
        "cliffhanger": "cliff",
        "batman returns": "batman",
        "super don quixote": "sdq",
        "don quixote": "sdq",
        "cobra command": "cobra",
        "road blaster": "roadblaster",
        "time gal": "timegal",
        "thayer's quest": "tq",
        "thayers quest": "tq",
    }
    
    # Check special mappings
    for full_name, short_name in special_mappings.items():
        if full_name in stem:
            return short_name
    
    # Default: use the stem, cleaned up
    # Remove spaces and special characters
    cleaned = re.sub(r"[^a-z0-9]", "", stem)
    return cleaned if cleaned else stem


def _validate_framefile(framefile: Path) -> bool:
    """Validate that the framefile exists and has correct extension."""
    if not framefile.exists():
        return False
    ext = framefile.suffix.lower()
    return ext in (".txt", ".m2v")


def resolve(game: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve Hypseus launch configuration.
    
    Returns dict with keys: exe, args, cwd, adapter, rom_name, framefile
    Returns error dict with error_code if cannot resolve.
    """
    # Find Hypseus executable
    exe = _find_hypseus_exe(manifest)
    if not exe:
        return {
            "success": False,
            "message": "MISSING-EMU: Hypseus/Daphne not found in standard locations",
            "error_code": HypseusAdapterError.EXE_NOT_FOUND,
            "adapter": "hypseus",
        }
    
    # Get framefile path from game
    rom_path = _get(game, "rom_path") or _get(game, "application_path")
    if not rom_path:
        return {
            "success": False,
            "message": "MISSING-ROM: no rom_path or application_path",
            "error_code": HypseusAdapterError.ROM_PATH_MISSING,
            "adapter": "hypseus",
        }
    
    # Resolve framefile path
    framefile = Path(str(rom_path).replace('\\', '/'))
    if not framefile.is_absolute():
        framefile = (LaunchBoxPaths.LAUNCHBOX_ROOT / framefile).resolve()
    framefile = _norm_path(str(framefile))
    
    # Validate framefile
    if not _validate_framefile(framefile):
        return {
            "success": False,
            "message": f"INVALID-FRAMEFILE: {framefile} does not exist or has wrong extension",
            "error_code": HypseusAdapterError.FRAMEFILE_NOT_FOUND,
            "adapter": "hypseus",
        }
    
    # Parse ROM name from framefile
    rom_name = _parse_rom_name(framefile)
    
    # Build command args:
    # hypseus.exe <rom_name> vldp -framefile "<framefile>" -fullscreen -xinput
    args = [
        rom_name,
        "vldp",
        "-framefile", str(framefile),
        "-fullscreen",
        "-xinput",
    ]
    
    # Add any extra flags from manifest
    cfg = _get_hypseus_config(manifest)
    if cfg and isinstance(cfg.get("flags"), list):
        extra_flags = [str(f) for f in cfg["flags"] if isinstance(f, str)]
        args.extend(extra_flags)
    
    logger.info(f"[Hypseus] Resolved: {rom_name} from {framefile}")
    
    return {
        "exe": str(exe),
        "args": args,
        "cwd": str(exe.parent),
        "adapter": "hypseus",
        "rom_name": rom_name,
        "framefile": str(framefile),
    }


def launch(game: Any, manifest: Dict[str, Any], runner) -> Dict[str, Any]:
    """Launch a Hypseus/Daphne game.
    
    Returns structured result with adapter name and rom_name for logging.
    """
    cfg = resolve(game, manifest)
    
    # Check for error from resolve()
    if cfg.get("error_code"):
        return {
            "success": False,
            "message": cfg.get("message", "Hypseus config unresolved"),
            "error_code": cfg.get("error_code"),
            "adapter": "hypseus",
        }
    
    # Run the launch
    result = runner.run(cfg)
    
    # Enrich result with adapter metadata
    if isinstance(result, dict):
        result["adapter"] = "hypseus"
        result["rom_name"] = cfg.get("rom_name")
        result["framefile"] = cfg.get("framefile")
    
    return result
