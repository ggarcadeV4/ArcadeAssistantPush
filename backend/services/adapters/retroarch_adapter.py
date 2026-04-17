from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import re
import os
from backend.constants.a_drive_paths import EmulatorPaths
from backend.constants.drive_root import (
    get_emulators_root,
    get_gun_emulators_root,
    get_launchbox_root,
    resolve_runtime_path,
)


@dataclass
class RAConfig:
    exe: Path
    core: str
    romfile: Path
    flags: List[str]
    platform: str = ""


def _norm_path(p: str) -> Path:
    """Normalize paths through the shared runtime root contract."""
    return resolve_runtime_path(p) or Path("")


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
    "Sega Naomi": "overlays/Naomi.cfg",
    "Sammy Atomiswave": "overlays/Atomiswave.cfg",
}

INSTANCE_REGISTRY: Dict[str, Dict[str, str]] = {
    # Standard RetroArch instance
    "Atari 2600": {"instance": "retroarch", "core": "stella_libretro.dll"},
    "Atari 7800": {"instance": "retroarch", "core": "prosystem_libretro.dll"},
    "Super Nintendo Entertainment System": {"instance": "retroarch", "core": "snes9x_libretro.dll"},
    "Sega Genesis": {"instance": "retroarch", "core": "genesis_plus_gx_libretro.dll"},
    "Sega Game Gear": {"instance": "retroarch", "core": "genesis_plus_gx_libretro.dll"},
    "Sega Master System": {"instance": "retroarch", "core": "genesis_plus_gx_libretro.dll"},
    "Atari Lynx": {"instance": "retroarch", "core": "handy_libretro.dll"},
    "Atari Jaguar": {"instance": "retroarch", "core": "virtualjaguar_libretro.dll"},
    "NEC TurboGrafx-16": {"instance": "retroarch", "core": "mednafen_pce_fast_libretro.dll"},
    "Sega 32X": {"instance": "retroarch", "core": "picodrive_libretro.dll"},
    "Sega CD": {"instance": "retroarch", "core": "genesis_plus_gx_libretro.dll"},
    "Sony Playstation": {"instance": "retroarch", "core": "mednafen_psx_hw_libretro.dll"},
    "Neo Geo Pocket": {"instance": "retroarch", "core": "mednafen_ngp_libretro.dll"},
    "Neo Geo Pocket Color": {"instance": "retroarch", "core": "mednafen_ngp_libretro.dll"},
    "WonderSwan": {"instance": "retroarch", "core": "mednafen_wswan_libretro.dll"},
    "WonderSwan Color": {"instance": "retroarch", "core": "mednafen_wswan_libretro.dll"},
    "Sega Naomi": {"instance": "retroarch", "core": "flycast_libretro.dll"},
    "Sammy Atomiswave": {"instance": "retroarch", "core": "flycast_libretro.dll"},
    # Gamepad instance
    "Nintendo Entertainment System": {"instance": "retroarch_gamepad", "core": "mesen_libretro.dll"},
    "Nintendo Game Boy": {"instance": "retroarch_gamepad", "core": "gambatte_libretro.dll"},
    "Nintendo Game Boy Color": {"instance": "retroarch_gamepad", "core": "gambatte_libretro.dll"},
    "Nintendo Game Boy Advance": {"instance": "retroarch_gamepad", "core": "mgba_libretro.dll"},
    # Nintendo GameCube: routed to standalone Dolphin.exe (dolphin_adapter).
    # dolphin_libretro is blacklisted — black screen with audio on this cabinet.
    # "Nintendo GameCube": {DISABLED},
    # Gun instance
    "NES Gun Games": {"instance": "retroarch_gun", "core": "nestopia_libretro.dll"},
    "Master System Gun Games": {"instance": "retroarch_gun", "core": "genesis_plus_gx_libretro.dll"},
    "Saturn Gun Games": {"instance": "retroarch_gun", "core": "mednafen_saturn_libretro.dll"},
    "American Laser Games": {"instance": "retroarch_gun", "core": "opera_libretro.dll"},
}

OVERLAY_DISABLED_PLATFORMS = {
    # GameCube is no longer routed through RetroArch — handled by dolphin_adapter.
    # Entry kept as empty set for future use.
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


def _state_base_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    state_root = os.getenv("AA_RUNTIME_STATE_DIR")
    return Path(state_root) if state_root else (repo_root / ".aa" / "state")


def _upsert_cfg_line(text: str, key: str, value: str) -> str:
    line = f'{key} = "{value}"'
    pattern = re.compile(rf"(?m)^{re.escape(key)}\s*=.*$")
    if pattern.search(text):
        return pattern.sub(line, text)
    body = text.rstrip("\n")
    if body:
        body += "\n"
    return f"{body}{line}\n"


def _ensure_runtime_base_config(exe: Path) -> Optional[Path]:
    try:
        source_cfg = exe.parent / "retroarch.cfg"
        if not source_cfg.exists():
            fallback_cfg = get_emulators_root() / exe.parent.name / "retroarch.cfg"
            if fallback_cfg.exists():
                source_cfg = fallback_cfg
            else:
                return None

        out_dir = _state_base_dir() / "retroarch" / "runtime_configs"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{_safe_slug(exe.parent.name)}.cfg"

        content = source_cfg.read_text(encoding="utf-8", errors="ignore")
        for key, value in (
            ("config_save_on_exit", "false"),
            ("auto_overrides_enable", "false"),
            ("auto_remaps_enable", "false"),
            ("input_overlay", ""),
            ("input_overlay_enable", "false"),
        ):
            content = _upsert_cfg_line(content, key, value)

        current = ""
        if out_file.exists():
            current = out_file.read_text(encoding="utf-8", errors="ignore")
        if current != content:
            out_file.write_text(content, encoding="utf-8")
        return out_file
    except Exception:
        return None


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


def _get_instance_exe(instance_name: str) -> Path:
    mapping = {
        "retroarch": EmulatorPaths.retroarch(),
        "retroarch_gamepad": EmulatorPaths.retroarch_gamepad(),
        "retroarch_gun": EmulatorPaths.retroarch_gun(),
        "retroarch_gun_win64": EmulatorPaths.retroarch_gun_win64(),
    }
    exe = Path(mapping.get(instance_name, EmulatorPaths.retroarch()))
    if exe.exists():
        return exe

    # Some cabinet installs keep auxiliary RetroArch builds under the
    # AA_DRIVE_ROOT project tree instead of the bare drive root.
    panel_root = get_emulators_root()
    gun_root = get_gun_emulators_root()
    fallback_dirs = {
        "retroarch": panel_root / "RetroArch",
        "retroarch_gamepad": panel_root / "RetroArch Gamepad",
        "retroarch_gun": gun_root / "RetroArch",
        "retroarch_gun_win64": gun_root / "RetroArch-Win64",
    }
    fallback_exe = fallback_dirs.get(instance_name, panel_root / "RetroArch") / "retroarch.exe"
    return fallback_exe


def _ensure_platform_override(platform_name: str, overlay_cfg: Path) -> Optional[Path]:
    try:
        base_dir = _state_base_dir()
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


def _ensure_platform_launch_override(platform_name: str, *, overlay_cfg: Optional[Path] = None) -> Optional[Path]:
    try:
        base_dir = _state_base_dir()
        out_dir = base_dir / "retroarch" / "platform_overrides"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{_safe_slug(platform_name)}.cfg"

        # Clear any previously active overlay first, then apply the requested
        # platform bezel for this launch. This prevents stale carryover from
        # prior RetroArch sessions or saved overrides.
        lines: List[str] = [
            'auto_overrides_enable = "false"',
            'input_overlay = ""',
            'input_overlay_enable = "false"',
        ]
        if overlay_cfg:
            overlay_text = str(overlay_cfg).replace("\\", "/")
            lines.extend([
                f'input_overlay = "{overlay_text}"',
                'input_overlay_enable = "true"',
                'input_overlay_opacity = "1.000000"',
            ])

        if platform_name == "Nintendo GameCube":
            # dolphin_libretro is currently black-screening on gameplay while audio
            # continues. Disable the two highest-risk global frontend features for
            # this core at launch time: rewind and shaders.
            lines.extend([
                'rewind_enable = "false"',
                'video_shader_enable = "false"',
            ])

        content = "\n".join(lines) + "\n"
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
    plat = _normalize_platform_name(_platform_name_for_game(game))
    if plat in INSTANCE_REGISTRY:
        return True
    emu = _get_ra_config(manifest)
    if not emu:
        return False
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
    manifest = manifest or {}
    emu = _get_ra_config(manifest) or {}
    plat = _normalize_platform_name(_platform_name_for_game(game))
    exe_override = (_get(game, "retroarch_exe_override") or "").strip()
    registry_entry = INSTANCE_REGISTRY.get(plat)

    core_path: Optional[Path] = None
    if exe_override:
        exe = _norm_path(exe_override)
        if registry_entry:
            core_path = exe.parent / "cores" / registry_entry["core"]
    elif registry_entry:
        exe = _get_instance_exe(registry_entry["instance"])
        core_path = exe.parent / "cores" / registry_entry["core"]
    else:
        manifest_exe = str(emu.get("exe", "") or "").strip()
        manifest_exe_path = _norm_path(manifest_exe)
        if (
            manifest_exe_path
            and manifest_exe_path.is_absolute()
            and manifest_exe_path.is_relative_to(get_launchbox_root())
        ):
            exe = EmulatorPaths.retroarch()
        else:
            exe = manifest_exe_path
        if not str(exe) or not exe.exists():
            exe = EmulatorPaths.retroarch()
    if not str(exe) or not exe.exists():
        return None

    if core_path is None:
        core_key = ((_get(game, "retroarch_core_override") or "").strip() or (emu.get("platform_map") or {}).get(plat))
        if not core_key:
            return None
        cores = emu.get("cores") or {}
        core_rel = cores.get(core_key)
        if not core_rel:
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
    # Resolve ROM path: absolute stays absolute; relative LaunchBox-style paths
    # are anchored from the configured LaunchBox root on disk.
    rom_str = str(rom).replace('\\', '/')
    is_abs = bool(re.match(r"^[A-Za-z]:/", rom_str) or rom_str.startswith('/mnt/'))
    if is_abs:
        romfile = _norm_path(rom_str)
    else:
        rom_abs = (get_launchbox_root() / rom_str).resolve()
        romfile = rom_abs

    # Flags
    flags: List[str] = []
    runtime_cfg = _ensure_runtime_base_config(exe)
    if runtime_cfg:
        flags.extend(["--config", str(runtime_cfg)])
    flags.extend([str(f) for f in (emu.get("flags") or []) if isinstance(f, str) and f])

    # Bezel correction layer:
    # 1) pick overlay by platform (manifest overlay_map wins over defaults)
    # 2) append platform-specific config
    # 3) disable legacy per-game overrides for this launch to avoid wrong-system carryover
    overlay_map = emu.get("overlay_map") or {}
    overlay_ref = None if plat in OVERLAY_DISABLED_PLATFORMS else (
        overlay_map.get(plat) or DEFAULT_PLATFORM_OVERLAY_MAP.get(plat)
    )
    overlay_path = _resolve_overlay_path(str(overlay_ref), exe) if overlay_ref else None
    platform_cfg = _ensure_platform_launch_override(plat, overlay_cfg=overlay_path)
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
        "Atari 7800": ["prosystem_libretro.dll"],
        "Nintendo GameCube": ["dolphin_libretro.dll"],
        "Nintendo Game Boy": ["gambatte_libretro.dll"],
        "Nintendo Game Boy Advance": ["mgba_libretro.dll"],
        "Nintendo Game Boy Color": ["gambatte_libretro.dll"],
        "Sega Game Gear": ["genesis_plus_gx_libretro.dll"],
        "Sega Master System": ["genesis_plus_gx_libretro.dll"],
        "Atari Lynx": ["handy_libretro.dll"],
        "Atari Jaguar": ["virtualjaguar_libretro.dll"],
        "NEC TurboGrafx-16": ["mednafen_pce_fast_libretro.dll"],
        "Sega 32X": ["picodrive_libretro.dll"],
        "Sega CD": ["genesis_plus_gx_libretro.dll"],
        "Sony Playstation": ["mednafen_psx_hw_libretro.dll"],
        "Sony PSP": ["ppsspp_libretro.dll"],
        "Sony PSP Minis": ["ppsspp_libretro.dll"],
        "Neo Geo Pocket": ["mednafen_ngp_libretro.dll"],
        "Neo Geo Pocket Color": ["mednafen_ngp_libretro.dll"],
        "WonderSwan": ["mednafen_wswan_libretro.dll"],
        "WonderSwan Color": ["mednafen_wswan_libretro.dll"],
        "Sega Naomi": ["flycast_libretro.dll"],
        "Sammy Atomiswave": ["flycast_libretro.dll"],
    }
    result: Dict[str, str] = {}
    for core_key, candidates in preferred.items():
        match = next((c for c in candidates if c in present), None)
        if match:
            result[core_key] = match
    return result

