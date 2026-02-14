from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import platform
import re
import os


@dataclass
class RedreamConfig:
    exe: Path
    romfile: Path
    flags: List[str]


def _is_wsl() -> bool:
    return platform.system() == "Linux" and "microsoft" in platform.release().lower()


def _norm_path(p: str) -> Path:
    """Normalize paths across Windows/WSL for A:/ style manifest paths."""
    if not p:
        return Path("")
    if _is_wsl():
        # Convert drive-letter Windows paths like A:/ or D:\ to /mnt/<drive>/...
        p = p.replace("\\", "/")
        # Specific A: fast path
        p = p.replace("A:/", "/mnt/a/")
        # Generic X:/ → /mnt/x/
        m = re.match(r"^([A-Za-z]):/(.*)$", p)
        if m:
            p = f"/mnt/{m.group(1).lower()}/{m.group(2)}"
    return Path(p)


def _get(obj: Any, key: str) -> Optional[str]:
    """Get attribute or dict key from a Game-like object."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _get_redream_config(manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not manifest:
        return None
    # Support multiple schema shapes: emulators, launchers, or top-level
    for key in ("emulators", "launchers"):
        block = manifest.get(key)
        if isinstance(block, dict) and isinstance(block.get("redream"), dict):
            return block.get("redream")
    if isinstance(manifest.get("redream"), dict):
        return manifest.get("redream")
    return None


def can_handle(game: Any, manifest: Dict[str, Any]) -> bool:
    emu = _get_redream_config(manifest)
    if not emu:
        return False
    plat = (_get(game, "platform") or "").strip()
    # Handle both "Sega Dreamcast" and "Dreamcast"
    return "dreamcast" in plat.lower()


def is_enabled(manifest: Dict[str, Any]) -> bool:
    """Flag gate for direct Redream fallback."""
    return bool((manifest.get("global") or {}).get("allow_direct_redream"))


def resolve_config(game: Any, manifest: Dict[str, Any]) -> Optional[RedreamConfig]:
    """Resolve Redream config for a given game based on manifest mapping.

    Returns None if mapping is missing or inputs are incomplete.
    """
    if not manifest:
        return None
    emu = _get_redream_config(manifest)
    if not emu:
        return None

    exe = _norm_path(str(emu.get("exe", "")))
    if not str(exe):
        return None

    # ROM path from game
    rom = _get(game, "rom_path") or _get(game, "application_path") or _get(game, "romPath")
    if not rom:
        return None

    # Resolve ROM path (same logic as RetroArch)
    rom_str = str(rom).replace('\\', '/')
    is_abs = bool(re.match(r"^[A-Za-z]:/", rom_str) or rom_str.startswith('/mnt/'))
    if is_abs:
        romfile = _norm_path(rom_str)
    else:
        # Resolve relative to LaunchBox root
        from backend.constants.a_drive_paths import LaunchBoxPaths
        base = LaunchBoxPaths.LAUNCHBOX_ROOT
        rom_abs = (base / rom_str).resolve()
        romfile = rom_abs

    # Flags (Redream supports --fullscreen, --aspect, etc.)
    flags = [str(f) for f in (emu.get("flags") or []) if isinstance(f, str) and f]

    return RedreamConfig(exe=exe, romfile=romfile, flags=flags)


def build_command(cfg: RedreamConfig) -> List[str]:
    """Build a Redream command line from RedreamConfig."""
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
    """Resolve a simple dict config for Redream.

    Returns keys: exe, args, cwd. Empty dict if not resolvable.
    """
    cfg = resolve_config(game, manifest)
    if not cfg:
        return {}
    args = []
    if cfg.flags:
        args.extend(cfg.flags)
    args.append(str(cfg.romfile))
    return {
        "exe": str(cfg.exe),
        "args": args,
        "cwd": str(Path(cfg.exe).parent),
        # extras (optional)
        "romfile": str(cfg.romfile),
        "flags": list(cfg.flags),
    }


def launch(game: Any, manifest: Dict[str, Any], runner) -> Dict[str, Any]:
    """Adapter-level launch using provided runner shim.

    Runner is expected to have .run(cfg: {exe,args,cwd}) -> dict
    """
    cfg = resolve(game, manifest)
    if not cfg:
        return {"success": False, "message": "Redream config unresolved"}
    return runner.run(cfg)
