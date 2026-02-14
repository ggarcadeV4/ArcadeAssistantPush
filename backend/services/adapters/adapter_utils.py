from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import json
import os

from backend.constants.a_drive_paths import LaunchBoxPaths
from backend.constants.runtime_paths import aa_tmp_dir
from backend.services.archive_utils import _extract_zip as au_extract_zip  # type: ignore
from backend.services.archive_utils import _find_7z_exe as au_find_7z  # type: ignore
import shutil

_CONFIG_PATH = Path('configs/emulator_paths.json')


def _load_config() -> Dict[str, Any]:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding='utf-8'))
        except Exception:
            return {"emulators": {}, "platform_mappings": []}
    return {"emulators": {}, "platform_mappings": []}


def find_emulator_exe(hint: str) -> Optional[Path]:
    """Find emulator executable by matching hint against title/path.

    Resolves relative paths against LaunchBox root.
    """
    cfg = _load_config()
    emulators = cfg.get('emulators') or {}
    h = (hint or '').lower()
    for emu in emulators.values():
        title = (emu.get('title') or '').lower()
        exe_rel = emu.get('executable_path') or ''
        if h in title or h in exe_rel.lower():
            exe = Path(exe_rel)
            if not exe.is_absolute():
                exe = (LaunchBoxPaths.LAUNCHBOX_ROOT / exe).resolve()
            return exe
    return None


def get_game_rom_path(game: Any) -> Optional[Path]:
    for key in (
        'rom_path', 'application_path', 'applicationPath', 'romPath', 'path'
    ):
        v = None
        try:
            v = game.get(key) if isinstance(game, dict) else getattr(game, key)
        except Exception:
            v = None
        if v:
            return Path(str(v))
    return None


def dry_run_enabled() -> bool:
    return str(os.getenv('AA_ADAPTER_DRY_RUN', '0')).lower() in {'1', 'true', 'yes'}


def success_with_command(exe: Path, args: list[str]) -> Dict[str, Any]:
    cmd = ' '.join([str(exe)] + [str(a) for a in args])
    return {"success": True, "command": cmd, "message": "dry-run"}


def _env_bool(name: str, default: str) -> bool:
    try:
        return str(os.getenv(name, default)).lower() in {"1", "true", "yes"}
    except Exception:
        return str(default).lower() in {"1", "true", "yes"}


def launch_fullscreen_enabled() -> bool:
    """Default fullscreen on unless explicitly disabled via env.

    AA_LAUNCH_FULLSCREEN defaults to 1 per repository guidelines.
    """
    return _env_bool("AA_LAUNCH_FULLSCREEN", "1")


def launch_nogui_enabled() -> bool:
    """Default no-GUI (batch) on unless explicitly disabled via env.

    AA_LAUNCH_NOGUI defaults to 1 per repository guidelines.
    """
    return _env_bool("AA_LAUNCH_NOGUI", "1")


# Adapter extension preferences
PREFS: Dict[str, list[str]] = {
    'duckstation': ['.cue', '.chd', '.bin'],
    'dolphin': ['.iso', '.wbfs', '.gcm', '.ciso', '.gcz'],
    'flycast': ['.gdi', '.cdi', '.chd'],
    'model2': ['.zip'],
    'supermodel': ['.zip'],
}


def _extract_7z(archive: Path, out_dir: Path) -> bool:
    seven = au_find_7z()
    if not seven:
        try:
            import py7zr  # type: ignore
            with py7zr.SevenZipFile(archive, mode='r') as z:
                z.extractall(path=out_dir)
            return True
        except Exception:
            return False
    try:
        import subprocess, subprocess as sp
        cmd = [str(seven), 'x', '-y', f'-o{str(out_dir)}', str(archive)]
        sp.run(cmd, check=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        return True
    except Exception:
        return False


def _generic_extract(archive: Path) -> Optional[Path]:
    base = aa_tmp_dir()
    # Free space guard
    try:
        min_free_gb = float(os.getenv("AA_EXTRACT_MIN_FREE_GB", "10"))
    except Exception:
        min_free_gb = 10.0
    try:
        usage = shutil.disk_usage(base)
        free_gb = usage.free / (1024 ** 3)
        if free_gb < min_free_gb:
            return None
    except Exception:
        # if disk_usage fails, continue best-effort
        pass
    out = base / archive.stem
    i = 1
    while out.exists() and i < 999:
        out = base / f"{archive.stem}-{i}"
        i += 1
    out.mkdir(parents=True, exist_ok=True)
    ok = False
    if archive.suffix.lower() == '.zip':
        ok = au_extract_zip(archive, out)
    elif archive.suffix.lower() == '.7z':
        ok = _extract_7z(archive, out)
    if not ok:
        try:
            import shutil
            shutil.rmtree(out, ignore_errors=True)
        except Exception:
            pass
        return None
    return out


def _pick_by_pref(folder: Path, prefs: list[str]) -> Optional[Path]:
    for ext in prefs:
        cands = list(folder.glob(f"*{ext}"))
        if cands:
            return cands[0]
    # last resort: any file
    try:
        anyfile = next(folder.iterdir())
        return anyfile
    except StopIteration:
        return None


def resolve_rom_for_launch(game: Any, adapter: str) -> Tuple[Optional[Path], Optional[Path], str]:
    """Resolve final ROM path for launch supporting archives + preferences.

    Returns: (resolved_file, extracted_root, notes)
    - resolved_file: final file to pass to emulator
    - extracted_root: temp dir if archive was extracted, else None
    - notes: human-readable decisions (e.g., cue chosen, archive extracted)
    """
    prefs = PREFS.get(adapter, [])
    rom = get_game_rom_path(game)
    if not rom:
        return None, None, 'rom:missing'
    p = Path(str(rom))
    notes = []
    # Special-case: for model2/supermodel, keep .zip intact and pass stem/zip as needed
    if p.suffix.lower() == '.zip' and adapter in {'model2', 'supermodel'}:
        # Do not extract; keep original zip and signal via notes
        return p, None, 'zip:kept'
    # Archive handling for other adapters
    if p.suffix.lower() in {'.zip', '.7z'}:
        out = _generic_extract(p)
        if not out:
            return None, None, 'extract:failed'
        picked = _pick_by_pref(out, prefs) if prefs else None
        if not picked:
            return None, out, 'extract:ok but no preferred file found'
        notes.append('archive:extracted')
        # PS1 cue preference messaging
        if adapter == 'duckstation' and picked.suffix.lower() != '.cue':
            # look for any .cue
            cue = next(out.glob('*.cue'), None)
            if cue:
                picked = cue
                notes.append('cue:preferred')
        # Flycast gdi preference
        if adapter == 'flycast' and picked.suffix.lower() != '.gdi':
            gdi = next(out.glob('*.gdi'), None)
            if gdi:
                picked = gdi
                notes.append('gdi:preferred')
        return picked, out, ';'.join(notes)
    # Non-archive: apply preference tweaks
    if adapter == 'duckstation' and p.suffix.lower() in {'.bin', '.img', '.chd'}:
        cue = p.with_suffix('.cue')
        if cue.exists():
            notes.append('cue:preferred')
            return cue, None, ';'.join(notes)
        alt_cue = next(p.parent.glob('*.cue'), None)
        if alt_cue:
            notes.append('cue:preferred-folder')
            return alt_cue, None, ';'.join(notes)
    if adapter == 'flycast' and p.suffix.lower() in {'.bin', '.img'}:
        gdi = p.with_suffix('.gdi')
        if gdi.exists():
            notes.append('gdi:preferred')
            return gdi, None, ';'.join(notes)
        alt_gdi = next(p.parent.glob('*.gdi'), None)
        if alt_gdi:
            notes.append('gdi:preferred-folder')
            return alt_gdi, None, ';'.join(notes)
    # Default
    return p, None, ';'.join(notes)
