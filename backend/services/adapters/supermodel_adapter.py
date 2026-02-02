from typing import Any, Dict
from pathlib import Path
from .adapter_utils import (
    find_emulator_exe,
    dry_run_enabled,
    success_with_command,
    get_game_rom_path,
    launch_fullscreen_enabled,
    _load_config,
)
from backend.constants.runtime_paths import aa_tmp_dir
from backend.services.platform_names import normalize_key
from backend.services.archive_utils import _extract_zip as au_extract_zip  # type: ignore


def is_enabled(manifest: Dict[str, Any]) -> bool:
    return True


def can_handle(game: Any, manifest: Dict[str, Any], return_reason: bool = False):
    key = normalize_key((getattr(game, 'platform', None) or (game.get('platform') if isinstance(game, dict) else '') or ''))
    ok = key == 'sega model 3'
    if return_reason:
        return ok, f"platform_key={key}"
    return ok


def _prefer_supermodel_exe_for_platform(game: Any) -> Path | None:
    """Prefer Supermodel exe based on platform context.

    For 'Model 3 Gun Games', prefer the 'Supermodel Gun' entry if present in
    configs/emulator_paths.json. Otherwise, fall back to generic discovery.
    """
    try:
        plat = (getattr(game, 'platform', None) or (game.get('platform') if isinstance(game, dict) else '') or '')
        want_gun = isinstance(plat, str) and ('gun' in plat.lower())
        cfg = _load_config() or {}
        emus = (cfg.get('emulators') or {}) if isinstance(cfg, dict) else {}
        # Iterate deterministically
        for emu in emus.values():
            title = (emu.get('title') or '').lower()
            exe_rel = emu.get('executable_path') or ''
            if want_gun and ('supermodel' in title and 'gun' in title or 'supermodel' in exe_rel.lower() and 'gun build' in exe_rel.lower()):
                from backend.constants.a_drive_paths import LaunchBoxPaths
                exe = Path(exe_rel)
                if not exe.is_absolute():
                    exe = (LaunchBoxPaths.LAUNCHBOX_ROOT / exe).resolve()
                if exe.exists():
                    return exe
        # Fallback: any supermodel entry
        for emu in emus.values():
            exe_rel = emu.get('executable_path') or ''
            if 'supermodel' in (emu.get('title') or '').lower() or 'supermodel' in exe_rel.lower():
                from backend.constants.a_drive_paths import LaunchBoxPaths
                exe = Path(exe_rel)
                if not exe.is_absolute():
                    exe = (LaunchBoxPaths.LAUNCHBOX_ROOT / exe).resolve()
                if exe.exists():
                    return exe
    except Exception:
        pass
    # Last resort: generic discovery
    return find_emulator_exe('supermodel')


def resolve(game: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    exe = _prefer_supermodel_exe_for_platform(game)
    if not exe:
        return {"success": False, "message": "MISSING-EMU: emulators.Supermodel.executable_path"}
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
    args = []
    if launch_fullscreen_enabled():
        args.append('-fullscreen')
    # Prefer passing the ZIP directly to Supermodel; avoid extraction complexity.
    # Supermodel accepts the ROM set as a path or basename.
    extracted_root = None
    if p.suffix.lower() == '.zip':
        rom_arg = str(p)  # pass full path to zip
        cwd = str(p.parent)
    else:
        # Non-archive: pass full path (or basename)
        rom_arg = str(p)
        cwd = str(p.parent)

    args.append(rom_arg)
    return {"exe": str(exe), "args": args, "cwd": cwd, "extracted_root": str(extracted_root) if extracted_root else None, "notes": f"supermodel:rom={Path(rom_arg).name}"}


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
