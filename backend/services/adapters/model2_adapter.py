from typing import Any, Dict
from pathlib import Path
from .adapter_utils import (
    find_emulator_exe,
    dry_run_enabled,
    success_with_command,
    get_game_rom_path,
)
from backend.constants.runtime_paths import aa_tmp_dir
from backend.services.platform_names import normalize_key
from backend.services.archive_utils import _extract_zip as au_extract_zip  # type: ignore


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
    romname = p.stem
    cwd = exe.parent
    extracted_root = None
    if p.suffix.lower() == '.zip':
        # Extract to AA_TMP_DIR/<stem>
        out = aa_tmp_dir() / p.stem
        try:
            out.mkdir(parents=True, exist_ok=True)
            if not au_extract_zip(p, out):
                return {"success": False, "message": "extract:failed"}
            # Heuristic: if single subfolder inside, use its name as romname
            subdirs = [d for d in out.iterdir() if d.is_dir()]
            if len(subdirs) == 1:
                romname = subdirs[0].name
                cwd = subdirs[0]
            else:
                cwd = out
            extracted_root = out
        except Exception:
            return {"success": False, "message": "extract:failed"}
    args = [f"-rom={romname}"]
    return {"exe": str(exe), "args": args, "cwd": str(cwd), "extracted_root": str(extracted_root) if extracted_root else None, "notes": f"model2:rom={romname}"}


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
