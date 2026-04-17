from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import re

from backend.constants.drive_root import (
    get_emulators_root,
    get_launchbox_root,
    resolve_runtime_path,
)


@dataclass
class PCSX2Config:
    exe: Path
    romfile: Path
    flags: List[str]


def _norm_path(p: str) -> Path:
    """Normalize paths through the shared runtime root contract."""
    return resolve_runtime_path(p) or Path("")


def _get(obj: Any, key: str) -> Optional[str]:
    """Get attribute or dict key from a Game-like object."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _get_pcsx2_config(manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not manifest:
        return None
    for key in ("emulators", "launchers"):
        block = manifest.get(key)
        if isinstance(block, dict) and isinstance(block.get("pcsx2"), dict):
            return block.get("pcsx2")
    if isinstance(manifest.get("pcsx2"), dict):
        return manifest.get("pcsx2")
    return None


def can_handle(game: Any, manifest: Dict[str, Any]) -> bool:
    plat = (_get(game, "platform") or "").strip().lower()
    return "playstation 2" in plat or "ps2" in plat or plat == "sony playstation 2"


def is_enabled(manifest: Dict[str, Any]) -> bool:
    """Always enabled for direct launch."""
    return True


def _find_pcsx2_exe() -> Optional[Path]:
    """Find PCSX2 executable in shared runtime locations."""
    launchbox_root = get_launchbox_root()
    emulators_root = get_emulators_root()
    candidates = [
        launchbox_root / "Emulators" / "PCSX2" / "pcsx2-qt.exe",
        launchbox_root / "Emulators" / "PCSX2" / "pcsx2.exe",
        emulators_root / "PCSX2" / "pcsx2-qt.exe",
        emulators_root / "PCSX2" / "pcsx2.exe",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def resolve_config(game: Any, manifest: Dict[str, Any]) -> Optional[PCSX2Config]:
    """Resolve PCSX2 config for a given game based on manifest mapping."""
    if not manifest:
        return None
    emu = _get_pcsx2_config(manifest)
    if not emu:
        return None

    exe = _norm_path(str(emu.get("exe", "")))
    if not str(exe):
        return None

    rom = _get(game, "rom_path") or _get(game, "application_path") or _get(game, "romPath")
    if not rom:
        return None

    rom_str = str(rom).replace("\\", "/")
    is_abs = bool(re.match(r"^[A-Za-z]:/", rom_str) or rom_str.startswith("/mnt/"))
    if is_abs:
        romfile = _norm_path(rom_str)
    else:
        romfile = (get_launchbox_root() / rom_str).resolve()

    flags = [str(f) for f in (emu.get("flags") or []) if isinstance(f, str) and f]
    return PCSX2Config(exe=exe, romfile=romfile, flags=flags)


def build_command(cfg: PCSX2Config) -> List[str]:
    """Build a PCSX2 command line from PCSX2Config."""
    cmd: List[str] = [str(cfg.exe)]
    if cfg.flags:
        cmd.extend(cfg.flags)
    cmd.append(str(cfg.romfile))
    return cmd


def to_command(game: Any, manifest: Dict[str, Any]) -> Optional[List[str]]:
    """High-level helper: guard flag, resolve config, and emit command list."""
    if not is_enabled(manifest):
        return None
    if not can_handle(game, manifest):
        return None
    cfg = resolve_config(game, manifest)
    if not cfg:
        return None
    return build_command(cfg)


def resolve(game: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve a simple dict config for PCSX2."""
    exe = _find_pcsx2_exe()
    if not exe:
        return {"success": False, "message": "MISSING-EMU: PCSX2 not found"}

    rom = _get(game, "rom_path") or _get(game, "application_path") or _get(game, "romPath")
    if not rom:
        return {"success": False, "message": "MISSING-ROM: no rom_path or application_path"}

    rom_path = Path(str(rom).replace("\\", "/"))
    if not rom_path.is_absolute():
        rom_path = (get_launchbox_root() / rom_path).resolve()

    if not rom_path.exists():
        return {"success": False, "message": f"MISSING-ROM: {rom_path} does not exist"}

    args = ["-fullscreen", "-batch", str(rom_path)]
    return {
        "exe": str(exe),
        "args": args,
        "cwd": str(exe.parent),
        "romfile": str(rom_path),
    }


def launch(game: Any, manifest: Dict[str, Any], runner) -> Dict[str, Any]:
    """Adapter-level launch using provided runner shim."""
    cfg = resolve(game, manifest)
    if not cfg:
        return {"success": False, "message": "PCSX2 config unresolved"}
    return runner.run(cfg)
