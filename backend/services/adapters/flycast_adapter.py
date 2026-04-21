from typing import Any, Dict
from pathlib import Path
from .adapter_utils import (
    find_emulator_exe,
    dry_run_enabled,
    success_with_command,
    resolve_rom_for_launch,
    get_game_rom_path,
    launch_fullscreen_enabled,
)
from backend.constants.a_drive_paths import EmulatorPaths
from backend.constants.drive_root import get_launchbox_root
from backend.services.platform_names import normalize_key


def is_enabled(manifest: Dict[str, Any]) -> bool:
    return True


def _redream_available() -> bool:
    candidates = [
        EmulatorPaths.redream(),
        get_launchbox_root() / "Emulators" / "redream.x86_64-windows-v1.5.0" / "redream.exe",
    ]
    return any(candidate.exists() for candidate in candidates)


def can_handle(game: Any, manifest: Dict[str, Any], return_reason: bool = False):
    raw = (getattr(game, 'platform', None) or (game.get('platform') if isinstance(game, dict) else '') or '')
    key = normalize_key(raw)
    ok = False
    if key in {'sega naomi', 'sammy atomiswave'}:
        ok = True
    elif key == 'sega dreamcast':
        # Dreamcast should prefer standalone Redream when it exists on disk.
        # Flycast is only the fallback when Redream is genuinely unavailable.
        try:
            ok = not _redream_available()
        except Exception:
            ok = False
    if return_reason:
        return ok, f"platform_key={key}"
    return ok


def resolve(game: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    exe = find_emulator_exe('flycast')
    if not exe:
        return {"success": False, "message": "MISSING-EMU: emulators.Flycast.executable_path"}
    resolved, extracted_root, notes = resolve_rom_for_launch(game, 'flycast')
    if not resolved:
        rp = get_game_rom_path(game)
        stem = Path(str(rp)).stem if rp else ""
        tried = ['.gdi', '.cdi', '.chd']
        return {
            "success": False,
            "message": f"MISSING-ROM: stem='{stem}', tried_exts={tried}"
        }
    args = []
    if launch_fullscreen_enabled():
        args.append('-fullscreen')
    args.append(str(resolved))
    return {"exe": str(exe), "args": args, "cwd": str(exe.parent), "extracted_root": str(extracted_root) if extracted_root else None}


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
