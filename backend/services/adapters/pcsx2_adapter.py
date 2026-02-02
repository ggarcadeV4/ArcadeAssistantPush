from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import platform
import re


@dataclass
class PCSX2Config:
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


def _get_pcsx2_config(manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not manifest:
        return None
    # Support multiple schema shapes: emulators, launchers, or top-level
    for key in ("emulators", "launchers"):
        block = manifest.get(key)
        if isinstance(block, dict) and isinstance(block.get("pcsx2"), dict):
            return block.get("pcsx2")
    if isinstance(manifest.get("pcsx2"), dict):
        return manifest.get("pcsx2")
    return None


def can_handle(game: Any, manifest: Dict[str, Any]) -> bool:
    plat = (_get(game, "platform") or "").strip().lower()
    # Handle various PS2 naming conventions
    return "playstation 2" in plat or "ps2" in plat or plat == "sony playstation 2"


def is_enabled(manifest: Dict[str, Any]) -> bool:
    """Always enabled for direct launch."""
    return True


def _find_pcsx2_exe() -> Optional[Path]:
    """Find PCSX2 executable in common locations."""
    from backend.constants.drive_root import get_drive_root
    
    drive_root = get_drive_root(allow_cwd_fallback=True)
    if drive_root.drive:
        drive_letter_root = Path(drive_root.drive + "\\")
    else:
        drive_letter_root = drive_root
    
    candidates = [
        drive_letter_root / "LaunchBox" / "Emulators" / "PCSX2" / "pcsx2-qt.exe",
        drive_letter_root / "LaunchBox" / "Emulators" / "PCSX2" / "pcsx2.exe",
        drive_letter_root / "Emulators" / "PCSX2" / "pcsx2-qt.exe",
        drive_letter_root / "Emulators" / "PCSX2" / "pcsx2.exe",
    ]
    
    for candidate in candidates:
        if candidate.exists():
            return candidate
    
    return None


def resolve_config(game: Any, manifest: Dict[str, Any]) -> Optional[PCSX2Config]:
    """Resolve PCSX2 config for a given game based on manifest mapping.

    Returns None if mapping is missing or inputs are incomplete.
    """
    if not manifest:
        return None
    emu = _get_pcsx2_config(manifest)
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

    # Flags (PCSX2 supports --fullscreen, --nogui, etc.)
    flags = [str(f) for f in (emu.get("flags") or []) if isinstance(f, str) and f]

    return PCSX2Config(exe=exe, romfile=romfile, flags=flags)


def build_command(cfg: PCSX2Config) -> List[str]:
    """Build a PCSX2 command line from PCSX2Config."""
    cmd: List[str] = [str(cfg.exe)]
    if cfg.flags:
        cmd.extend(cfg.flags)
    # PCSX2 expects the ROM as the last argument
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
    """Resolve a simple dict config for PCSX2.

    Returns keys: exe, args, cwd. Empty dict if not resolvable.
    """
    from backend.constants.a_drive_paths import LaunchBoxPaths
    
    # Find PCSX2 executable
    exe = _find_pcsx2_exe()
    if not exe:
        return {"success": False, "message": "MISSING-EMU: PCSX2 not found"}
    
    # Get ROM path
    rom = _get(game, "rom_path") or _get(game, "application_path") or _get(game, "romPath")
    if not rom:
        return {"success": False, "message": "MISSING-ROM: no rom_path or application_path"}
    
    # Resolve ROM path
    rom_path = Path(str(rom).replace('\\', '/'))
    if not rom_path.is_absolute():
        rom_path = (LaunchBoxPaths.LAUNCHBOX_ROOT / rom_path).resolve()
    
    if not rom_path.exists():
        return {"success": False, "message": f"MISSING-ROM: {rom_path} does not exist"}
    
    # Build args (fullscreen by default)
    args = ["-fullscreen", str(rom_path)]
    
    return {
        "exe": str(exe),
        "args": args,
        "cwd": str(exe.parent),
        "romfile": str(rom_path),
    }


def launch(game: Any, manifest: Dict[str, Any], runner) -> Dict[str, Any]:
    """Adapter-level launch using provided runner shim.

    Runner is expected to have .run(cfg: {exe,args,cwd}) -> dict
    """
    cfg = resolve(game, manifest)
    if not cfg:
        return {"success": False, "message": "PCSX2 config unresolved"}
    return runner.run(cfg)
