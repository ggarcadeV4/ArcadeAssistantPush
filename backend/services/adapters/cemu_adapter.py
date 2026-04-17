"""Cemu Adapter for Nintendo Wii U games.

Launches Wii U games via Cemu emulator.
Supports both .wud/.wux disc images and .rpx executables.
"""

from typing import Any, Dict, Optional
from pathlib import Path
import logging

from .adapter_utils import (
    find_emulator_exe,
    dry_run_enabled,
    success_with_command,
    get_game_rom_path,
)
from backend.constants.drive_root import resolve_runtime_path
from backend.services.platform_names import normalize_key

logger = logging.getLogger(__name__)


def is_enabled(manifest: Dict[str, Any]) -> bool:
    """Check if Cemu adapter should be enabled."""
    return True


def can_handle(game: Any, manifest: Dict[str, Any], return_reason: bool = False):
    """Check if this adapter can handle the given game.
    
    Handles Nintendo Wii U platform games.
    """
    platform = getattr(game, 'platform', None) or (game.get('platform') if isinstance(game, dict) else '')
    key = normalize_key(platform or '')
    
    # Match various Wii U platform naming conventions
    wii_u_keys = {'nintendo wii u', 'wii u', 'wiiu'}
    ok = key in wii_u_keys
    
    if return_reason:
        return ok, f"platform_key={key}"
    return ok


def resolve(game: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve Cemu launch configuration.
    
    Args:
        game: Game object with rom_path and other metadata
        manifest: Launcher configuration manifest
        
    Returns:
        Dict with exe, args, cwd keys for launching
    """
    # Find Cemu executable
    exe = None
    # Read from launchers.json manifest
    manifest_exe = manifest.get("emulators", {}).get("cemu", {}).get("exe", "")
    if manifest_exe:
        resolved = resolve_runtime_path(manifest_exe)
        if resolved and resolved.exists():
            exe = resolved

    if not exe:
        exe = find_emulator_exe('cemu')
    if not exe:
        return {"success": False, "message": "MISSING-EMU: emulators.cemu.exe - Cemu not found"}
    
    # Get ROM path
    rom_path = get_game_rom_path(game)
    if not rom_path:
        return {"success": False, "message": "MISSING-ROM: No ROM path found for Wii U game"}
    
    p = Path(str(rom_path))
    if not p.is_absolute():
        try:
            from backend.constants.a_drive_paths import LaunchBoxPaths
            p = (LaunchBoxPaths.LAUNCHBOX_ROOT / p).resolve()
        except Exception:
            p = p.resolve()
    
    if not p.exists():
        return {"success": False, "message": f"ROM not found: {p}"}
    
    # Build Cemu command line
    # Cemu uses: Cemu.exe -g "path/to/game.wud" [-f for fullscreen]
    args = ["-f", "-g", str(p)]
    
    # Get flags from manifest if available
    try:
        emus = manifest.get("emulators", {}) if isinstance(manifest, dict) else {}
        cemu_cfg = emus.get("cemu", {}) if isinstance(emus, dict) else {}
        custom_flags = cemu_cfg.get("flags", [])
        if custom_flags and isinstance(custom_flags, list):
            # Replace default flags with custom ones
            args = custom_flags + ["-g", str(p)]
    except Exception:
        pass
    
    return {
        "exe": str(exe),
        "args": args,
        "cwd": str(exe.parent),
        "notes": f"cemu:rom={p.name}"
    }


def launch(game: Any, manifest: Dict[str, Any], runner) -> Dict[str, Any]:
    """Launch Wii U game via Cemu.
    
    Args:
        game: Game object
        manifest: Launcher configuration
        runner: Process runner instance
        
    Returns:
        Launch result dict
    """
    cfg = resolve(game, manifest)
    if not cfg.get('exe'):
        return cfg
    
    exe = Path(cfg['exe'])
    args = cfg['args']
    
    if dry_run_enabled():
        out = success_with_command(exe, args)
        out.update({
            "resolved_file": cfg.get('cwd', ''),
            "message": cfg.get('notes', 'dry-run'),
        })
        return out
    
    return runner.run(cfg)
