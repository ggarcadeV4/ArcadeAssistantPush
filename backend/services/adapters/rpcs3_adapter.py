from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import re

from backend.constants.drive_root import get_launchbox_root, resolve_runtime_path


@dataclass
class RPCS3Config:
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


def _get_rpcs3_config(manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not manifest:
        return None
    for key in ("emulators", "launchers"):
        block = manifest.get(key)
        if isinstance(block, dict) and isinstance(block.get("rpcs3"), dict):
            return block.get("rpcs3")
    if isinstance(manifest.get("rpcs3"), dict):
        return manifest.get("rpcs3")
    return None


def can_handle(game: Any, manifest: Dict[str, Any]) -> bool:
    emu = _get_rpcs3_config(manifest)
    if not emu:
        return False
    plat = (_get(game, "platform") or "").strip().lower()
    return "playstation 3" in plat or "ps3" in plat or plat == "sony playstation 3"


def is_enabled(manifest: Dict[str, Any]) -> bool:
    """Flag gate for direct RPCS3 fallback."""
    return bool((manifest.get("global") or {}).get("allow_direct_rpcs3"))


def resolve_config(game: Any, manifest: Dict[str, Any]) -> Optional[RPCS3Config]:
    """Resolve RPCS3 config for a given game based on manifest mapping."""
    if not manifest:
        return None
    emu = _get_rpcs3_config(manifest)
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
    return RPCS3Config(exe=exe, romfile=romfile, flags=flags)


def build_command(cfg: RPCS3Config) -> List[str]:
    """Build an RPCS3 command line from RPCS3Config."""
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
    """Resolve a simple dict config for RPCS3."""
    cfg = resolve_config(game, manifest)
    if not cfg:
        return {}
    args = list(cfg.flags)
    args.append(str(cfg.romfile))
    return {
        "exe": str(cfg.exe),
        "args": args,
        "cwd": str(Path(cfg.exe).parent),
        "romfile": str(cfg.romfile),
        "flags": list(cfg.flags),
    }


def launch(game: Any, manifest: Dict[str, Any], runner) -> Dict[str, Any]:
    """Adapter-level launch using provided runner shim."""
    cfg = resolve(game, manifest)
    if not cfg:
        return {"success": False, "message": "RPCS3 config unresolved"}
    return runner.run(cfg)
