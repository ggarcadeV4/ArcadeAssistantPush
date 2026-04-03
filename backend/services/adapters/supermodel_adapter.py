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
from backend.constants.a_drive_paths import EmulatorPaths
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
    """Resolve Supermodel executable path.

    Priority:
      1. emulator_paths.json 'Supermodel Gun' entry (for gun game platforms)
      2. emulator_paths.json any entry containing 'supermodel'
      3. EmulatorPaths.supermodel() — deterministic cabinet path (guaranteed fallback)
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
        # Fallback: any supermodel entry in emulator_paths.json
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

    # Guaranteed fallback: deterministic cabinet path constant
    fallback = EmulatorPaths.supermodel()
    if fallback.exists():
        return fallback

    return None


def resolve(game: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    exe = _prefer_supermodel_exe_for_platform(game)
    if not exe:
        return {"success": False, "message": "MISSING-EMU: emulators.Supermodel.executable_path"}
    rp = get_game_rom_path(game)
    if not rp:
        return {"success": False, "message": "MISSING-ROM: stem='', tried_exts=['.zip']"}
    p = Path(str(rp))
    if not p.is_absolute():
        # Priority 1: relative to Supermodel exe dir — the most common LaunchBox
        # setup stores ROMs as e.g. "ROMs\dirtdvlsj.zip" relative to the emulator folder.
        exe_relative = (exe.parent / p).resolve()
        if exe_relative.exists():
            p = exe_relative
        else:
            # Priority 2: relative to LaunchBox root
            try:
                from backend.constants.a_drive_paths import LaunchBoxPaths
                p = (LaunchBoxPaths.LAUNCHBOX_ROOT / p).resolve()
            except Exception:
                p = p.resolve()

    # Fallback: physical ROMs under A:\Roms\MODEL3 regardless of what LaunchBox reports
    if not p.exists():
        alt = Path(r"A:\Roms\MODEL3") / p.name
        if alt.exists():
            p = alt

    args = []
    if launch_fullscreen_enabled():
        args.append('-fullscreen')
    # Supermodel needs to run from its own install dir so it can find Config/Games.xml.
    # Pass the absolute ROM path on the command line.
    extracted_root = None
    if p.suffix.lower() == '.zip':
        rom_arg = str(p)
        cwd = str(exe.parent)
    else:
        rom_arg = str(p)
        cwd = str(exe.parent)

    args.append(rom_arg)
    # no_pipe: Supermodel uses OpenGL which requires a real display context.
    # The stderr trap's stdout=PIPE, stderr=PIPE prevents OpenGL init.
    return {
        "exe": str(exe),
        "args": args,
        "cwd": cwd,
        "extracted_root": str(extracted_root) if extracted_root else None,
        "notes": f"supermodel:rom={Path(rom_arg).name}",
        "no_pipe": True,
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
