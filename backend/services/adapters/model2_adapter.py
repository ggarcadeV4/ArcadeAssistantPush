from typing import Any, Dict
from pathlib import Path
from .adapter_utils import (
    find_emulator_exe,
    dry_run_enabled,
    success_with_command,
    get_game_rom_path,
)
from backend.services.platform_names import normalize_key


def is_enabled(manifest: Dict[str, Any]) -> bool:
    return True


def can_handle(game: Any, manifest: Dict[str, Any], return_reason: bool = False):
    key = normalize_key((getattr(game, 'platform', None) or (game.get('platform') if isinstance(game, dict) else '') or ''))
    ok = key == 'sega model 2'
    if return_reason:
        return ok, f"platform_key={key}"
    return ok


def resolve(game: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    exe = find_emulator_exe('model 2') or find_emulator_exe('model2')
    if not exe:
        return {"success": False, "message": "MISSING-EMU: emulators.Model 2.executable_path"}

    rp = get_game_rom_path(game)
    if not rp:
        return {"success": False, "message": "MISSING-ROM: stem='', tried_exts=['.zip']"}

    p = Path(str(rp))
    if not p.is_absolute():
        try:
            from backend.constants.a_drive_paths import LaunchBoxPaths
            p = (LaunchBoxPaths.LAUNCHBOX_ROOT / p).resolve()
        except Exception:
            p = p.resolve()

    # Resolve stale LaunchBox rom paths by probing current emulator rom directories.
    if not p.exists():
        for cand in (exe.parent / 'roms' / p.name, exe.parent / p.name):
            if cand.exists():
                p = cand
                break

    if not p.exists():
        return {"success": False, "message": f"MISSING-ROM: {p}"}

    romname = p.stem
    args = [romname]
    return {
        "exe": str(exe),
        "args": args,
        "cwd": str(exe.parent),
        "extracted_root": None,
        "notes": f"model2:rom={romname}",
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
            "resolved_file": cfg.get('cwd') or "",
            "extracted": cfg.get('extracted_root'),
            "message": cfg.get('notes', 'dry-run'),
        })
        return out
    return runner.run(cfg)
