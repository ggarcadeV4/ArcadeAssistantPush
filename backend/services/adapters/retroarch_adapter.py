from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import platform
import re
import os
from backend.constants.a_drive_paths import LaunchBoxPaths


@dataclass
class RAConfig:
    exe: Path
    core: str
    romfile: Path
    flags: List[str]
    platform: str = ""


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
        # Generic X:/ -> /mnt/x/
        m = re.match(r"^([A-Za-z]):/(.*)$", p)
        if m:
            p = f"/mnt/{m.group(1).lower()}/{m.group(2)}"
    return Path(p)


def _get(obj: Any, key: str) -> Optional[str]:
    """Get attribute or dict key from a Game-like object."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


# Safe platform synonyms to reduce mapping friction
SAFE_PLATFORM_SYNONYMS: Dict[str, str] = {
    "Sega Mega Drive": "Sega Genesis",
    "Genesis": "Sega Genesis",
    "Super Famicom": "Super Nintendo Entertainment System",
    "SNES": "Super Nintendo Entertainment System",
    "Super Nintendo": "Super Nintendo Entertainment System",
    "NES": "Nintendo Entertainment System",
}

# Default bezel target by LaunchBox platform.
# Values are relative to the RetroArch executable directory.
DEFAULT_PLATFORM_OVERLAY_MAP: Dict[str, str] = {
    "Atari 2600": "overlays/Atari-2600.cfg",
    "Atari 7800": "overlays/Atari-7800.cfg",
    "Nintendo Entertainment System": "overlays/Nintendo-Entertainment-System.cfg",
    "Super Nintendo Entertainment System": "overlays/Super-Nintendo-Entertainment-System.cfg",
    "Nintendo GameCube": "overlays/Nintendo-GameCube.cfg",
    "Sega Genesis": "overlays/Sega-Genesis.cfg",
    "Nintendo Game Boy": "overlays/Nintendo-Game-Boy.cfg",
    "Nintendo Game Boy Advance": "overlays/Nintendo-Game-Boy-Advance.cfg",
    "Nintendo Game Boy Color": "overlays/Nintendo-Game-Boy-Color.cfg",
    "Sega Game Gear": "overlays/Sega-Game-Gear.cfg",
    "Sega Master System": "overlays/Sega-Master-System.cfg",
    "Atari Lynx": "overlays/Atari-Lynx-Horizontal.cfg",
    "Atari Jaguar": "overlays/Atari-Jaguar.cfg",
    "NEC TurboGrafx-16": "overlays/NEC-TurboGrafx-16.cfg",
    "Sega 32X": "overlays/Sega-32X.cfg",
    "Sega CD": "overlays/Sega-CD.cfg",
    "Sony Playstation": "overlays/Sony-PlayStation.cfg",
    "Sony PSP": "overlays/Sony-PSP.cfg",
    "Sony PSP Minis": "overlays/Sony-PSP.cfg",
    "Neo Geo Pocket": "overlays/SNK-Neo-Geo-Pocket.cfg",
    "Neo Geo Pocket Color": "overlays/SNK-Neo-Geo-Pocket-Color.cfg",
    "WonderSwan": "overlays/Bandai-WonderSwan-Horizontal.cfg",
    "WonderSwan Color": "overlays/Bandai-WonderSwan-Color-Horizontal.cfg",
    "Sega Dreamcast": "overlays/Dreamcast.cfg",
    "Sega Naomi": "overlays/Naomi.cfg",
    "Sammy Atomiswave": "overlays/Atomiswave.cfg",
}


def _normalize_platform_name(name: str) -> str:
    return SAFE_PLATFORM_SYNONYMS.get(name, name)


def _platform_name_for_game(game: Any) -> str:
    override = (_get(game, "retroarch_platform_override") or "").strip()
    if override:
        return override
    return ((_get(game, "platform") or "").strip())


def _get_ra_config(manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not manifest:
        return None
    # Support multiple schema shapes: emulators, launchers, or top-level
    for key in ("emulators", "launchers"):
        block = manifest.get(key)
        if isinstance(block, dict) and isinstance(block.get("retroarch"), dict):
            return block.get("retroarch")
    if isinstance(manifest.get("retroarch"), dict):
        return manifest.get("retroarch")
    return None


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "_", (value or "").strip().lower())
    slug = slug.strip("._-")
    return slug or "platform"


def _resolve_overlay_path(overlay_ref: str, exe: Path) -> Optional[Path]:
    if not overlay_ref:
        return None
    raw = str(overlay_ref).strip()
    p = _norm_path(raw)
    candidates: List[Path] = []
    if p.is_absolute():
        candidates.append(p)
    else:
        # Relative values resolve from RetroArch install first.
        candidates.append((exe.parent / raw).resolve())
        # Also support repo-local relative references.
        repo_root = Path(__file__).resolve().parents[3]
        candidates.append((repo_root / raw).resolve())
    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate
        except Exception:
            continue
    return None


def _ensure_platform_override(platform_name: str, overlay_cfg: Path) -> Optional[Path]:
    try:
        repo_root = Path(__file__).resolve().parents[3]
        state_root = os.getenv("AA_RUNTIME_STATE_DIR")
        base_dir = Path(state_root) if state_root else (repo_root / ".aa" / "state")
        out_dir = base_dir / "retroarch" / "platform_overrides"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{_safe_slug(platform_name)}.cfg"
        overlay_text = str(overlay_cfg).replace("\\", "/")
        content = (
            'auto_overrides_enable = "false"\n'
            f'input_overlay = "{overlay_text}"\n'
            'input_overlay_enable = "true"\n'
            'input_overlay_opacity = "1.000000"\n'
        )
        current = ""
        if out_file.exists():
            try:
                current = out_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                current = ""
        if current != content:
            out_file.write_text(content, encoding="utf-8")
        return out_file
    except Exception:
        return None


def can_handle(game: Any, manifest: Dict[str, Any]) -> bool:
    emu = _get_ra_config(manifest)
    if not emu:
        return False
    plat = _normalize_platform_name(_platform_name_for_game(game))
    core_key = (emu.get("platform_map") or {}).get(plat)
    return bool(core_key)


def is_enabled(manifest: Dict[str, Any]) -> bool:
    """Flag gate for direct RetroArch launch.

    ARCHITECTURE (2025-12-11): Direct-to-Emulator Model
    ====================================================
    RetroArch is ALWAYS enabled. The direct-to-emulator model means
    Pegasus -> Arcade Assistant -> RetroArch (no LaunchBox in chain).

    The manifest check is kept for backwards compatibility but defaults to True.
    """
    # Always enabled in direct-to-emulator model
    # Fall back to config check for explicit disable only
    explicit_disable = (manifest.get("global") or {}).get("disable_direct_retroarch")
    if explicit_disable:
        return False
    return True


def resolve_config(game: Any, manifest: Dict[str, Any]) -> Optional[RAConfig]:
    """Resolve RetroArch config for a given game based on manifest mapping.

    Returns None if mapping is missing or inputs are incomplete.
    """
    if not manifest:
        return None
    emu = _get_ra_config(manifest)
    if not emu:
        return None

    plat = _normalize_platform_name(_platform_name_for_game(game))
    core_key = ((_get(game, "retroarch_core_override") or "").strip() or (emu.get("platform_map") or {}).get(plat))
    if not core_key:
        return None

    cores = emu.get("cores") or {}
    core_rel = cores.get(core_key)
    if not core_rel:
        return None

    exe_override = (_get(game, "retroarch_exe_override") or "").strip()
    exe = _norm_path(exe_override or str(emu.get("exe", "")))
    # Fallback discovery: if exe missing, try common LaunchBox locations
    if not str(exe) or not exe.exists():
        try:
            # Prefer LaunchBox embedded RetroArch
            lb_emus = LaunchBoxPaths.LAUNCHBOX_ROOT / "Emulators"
            candidates: List[Path] = []
            for base in [lb_emus, LaunchBoxPaths.EMULATORS_ROOT]:
                try:
                    if base.exists():
                        candidates.extend(base.rglob("retroarch.exe"))
                except Exception:
                    continue
            # Choose the first matching exe deterministically
            if candidates:
                exe = candidates[0]
        except Exception:
            pass
    if not str(exe) or not exe.exists():
        return None

    # Core path may be relative to RetroArch directory
    core_path = Path(core_rel)
    if not core_path.is_absolute():
        candidate = exe.parent / core_rel
        if not candidate.exists():
            # Common layout: cores/<dll>
            candidate2 = exe.parent / "cores" / core_rel
            core_path = candidate2
        else:
            core_path = candidate

    # ROM path from game
    rom = _get(game, "rom_path") or _get(game, "application_path") or _get(game, "romPath")
    if not rom:
        return None
    # Resolve ROM path: absolute stays absolute; relative is resolved against LaunchBox root
    rom_str = str(rom).replace('\\', '/')
    is_abs = bool(re.match(r"^[A-Za-z]:/", rom_str) or rom_str.startswith('/mnt/'))
    if is_abs:
        romfile = _norm_path(rom_str)
    else:
        # Resolve relative to LaunchBox root (e.g., ..\\Console ROMs\\...)
        base = LaunchBoxPaths.LAUNCHBOX_ROOT
        rom_abs = (base / rom_str).resolve()
        romfile = rom_abs

    # Flags
    flags = [str(f) for f in (emu.get("flags") or []) if isinstance(f, str) and f]

    # Bezel correction layer:
    # 1) pick overlay by platform (manifest overlay_map wins over defaults)
    # 2) append platform-specific config
    # 3) disable legacy per-game overrides for this launch to avoid wrong-system carryover
    overlay_map = emu.get("overlay_map") or {}
    overlay_ref = overlay_map.get(plat) or DEFAULT_PLATFORM_OVERLAY_MAP.get(plat)
    if overlay_ref:
        overlay_path = _resolve_overlay_path(str(overlay_ref), exe)
        if overlay_path:
            platform_cfg = _ensure_platform_override(plat, overlay_path)
            if platform_cfg:
                flags.extend(["--appendconfig", str(platform_cfg)])

    return RAConfig(exe=exe, core=str(core_path), romfile=romfile, flags=flags, platform=plat)


def build_command(cfg: RAConfig) -> List[str]:
    """Build a RetroArch command line from RAConfig."""
    cmd: List[str] = [str(cfg.exe), "-L", cfg.core]
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
    """Resolve a simple dict config for RetroArch.

    Returns keys: exe, core, romfile, flags. Empty dict if not resolvable.
    Mirrors the structure suggested by the adapter starter snippet.
    """
    cfg = resolve_config(game, manifest)
    if not cfg:
        return {}
    args = ["-L", cfg.core]
    if cfg.flags:
        args.extend(cfg.flags)
    args.append(str(cfg.romfile))
    return {
        "exe": str(cfg.exe),
        "args": args,
        "cwd": str(Path(cfg.exe).parent),
        # extras (optional)
        "core": cfg.core,
        "romfile": str(cfg.romfile),
        "flags": list(cfg.flags),
    }


def launch(game: Any, manifest: Dict[str, Any], runner) -> Dict[str, Any]:
    """Adapter-level launch using provided runner shim.

    Runner is expected to have .run(cfg: {exe,args,cwd}) -> dict
    """
    cfg = resolve(game, manifest)
    if not cfg:
        return {"success": False, "message": "RetroArch config unresolved"}
    return runner.run(cfg)


# --- Diagnostics helpers ----------------------------------------------------

def list_installed_cores(exe: str) -> List[str]:
    try:
        cores_dir = Path(exe).parent / "cores"
        if not cores_dir.is_dir():
            return []
        return sorted([p.name for p in cores_dir.glob("*libretro.*")])
    except Exception:
        return []


def parse_core_info_files(exe: str) -> Dict[str, Dict[str, List[str]]]:
    """Parse RetroArch *.info files to discover supported_extensions and firmware.

    Returns: { core_basename: { 'supported_extensions': [...], 'firmware': [...] } }
    """
    out: Dict[str, Dict[str, List[str]]] = {}
    try:
        info_dir = Path(exe).parent / "info"
        if not info_dir.is_dir():
            return out
        for f in info_dir.glob("*.info"):
            core_name = f.stem
            data = {"supported_extensions": [], "firmware": []}
            try:
                for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                    s = line.strip()
                    if not s or s.startswith(("#", ";")):
                        continue
                    if s.startswith("supported_extensions"):
                        parts = s.split("=", 1)
                        if len(parts) == 2:
                            exts = parts[1].strip().strip('"').split(",")
                            data["supported_extensions"] = [e.strip().lower() for e in exts if e.strip()]
                    elif s.startswith("firmware"):
                        parts = s.split("=", 1)
                        if len(parts) == 2:
                            val = parts[1].strip().strip('"')
                            if val:
                                data.setdefault("firmware", []).append(val)
            except Exception:
                pass
            out[core_name] = data
    except Exception:
        pass
    return out


def propose_mapping_from_installed(cores_listing: List[str]) -> Dict[str, str]:
    """Pick preferred cores from what's installed (heuristic)."""
    present = set(cores_listing)
    preferred = {
        "Atari 2600": ["stella2014_libretro.dll", "stella_libretro.dll"],
        "Nintendo Entertainment System": ["mesen_libretro.dll", "fceumm_libretro.dll", "nestopia_libretro.dll"],
        "Super Nintendo Entertainment System": ["snes9x_libretro.dll", "bsnes_libretro.dll"],
        "Sega Genesis": ["genesis_plus_gx_libretro.dll", "picodrive_libretro.dll"],
    }
    result: Dict[str, str] = {}
    for core_key, candidates in preferred.items():
        match = next((c for c in candidates if c in present), None)
        if match:
            result[core_key] = match
    return result

