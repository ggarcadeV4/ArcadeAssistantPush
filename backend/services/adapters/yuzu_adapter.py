from typing import Any, Dict
from pathlib import Path
from .adapter_utils import (
    find_emulator_exe,
    dry_run_enabled,
    success_with_command,
    resolve_rom_for_launch,
    get_game_rom_path,
    launch_nogui_enabled,
)
from backend.services.platform_names import normalize_key
from backend.constants.drive_root import get_emulators_root, get_launchbox_root


def is_enabled(manifest: Dict[str, Any]) -> bool:
    return True


def can_handle(game: Any, manifest: Dict[str, Any], return_reason: bool = False):
    key = normalize_key((getattr(game, 'platform', None) or (game.get('platform') if isinstance(game, dict) else '') or ''))
    ok = key in {'nintendo switch'}
    if return_reason:
        return ok, f"platform_key={key}"
    return ok


def _find_yuzu_exe() -> Path:
    """Find Yuzu executable in common locations."""
    # Try standard emulator finder first
    exe = find_emulator_exe('yuzu')
    if exe:
        return exe

    launchbox_root = get_launchbox_root()
    emulators_root = get_emulators_root()
    candidates = [
        launchbox_root / "Emulators" / "yuzu" / "yuzu.exe",
        emulators_root / "yuzu" / "yuzu.exe",
        emulators_root / "Yuzu" / "yuzu.exe",
    ]
    
    for candidate in candidates:
        if candidate.exists():
            return candidate
    
    return None


def resolve(game: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    exe = _find_yuzu_exe()
    if not exe:
        return {"success": False, "message": "MISSING-EMU: Yuzu not found at LaunchBox/Emulators/yuzu/yuzu.exe"}
    
    # Get ROM path and resolve relative paths against LaunchBox root
    rp = get_game_rom_path(game)
    if not rp:
        return {"success": False, "message": "MISSING-ROM: no rom_path or application_path"}
    
    rom_path = Path(str(rp))
    if not rom_path.is_absolute():
        rom_path = (get_launchbox_root() / rom_path).resolve()
    
    if not rom_path.exists():
        return {
            "success": False,
            "message": f"MISSING-ROM: {rom_path} does not exist"
        }
    
    args = []
    if launch_nogui_enabled():
        args.append('-f')  # Fullscreen
    args.append(str(rom_path))
    
    return {
        "exe": str(exe),
        "args": args,
        "cwd": str(exe.parent),
        "extracted_root": None
    }


def launch(game: Any, manifest: Dict[str, Any], runner) -> Dict[str, Any]:
    cfg = resolve(game, manifest)
    if not cfg.get('exe'):
        return cfg
    exe = Path(cfg['exe'])
    args = cfg['args']
    if dry_run_enabled():
        out = success_with_command(exe, args)
        out.update({
            "resolved_file": args[-1] if args else "",
            "extracted": cfg.get('extracted_root')
        })
        return out
    return runner.run(cfg)
