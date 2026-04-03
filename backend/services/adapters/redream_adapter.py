from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from backend.constants.a_drive_paths import EmulatorPaths, LaunchBoxPaths
from backend.services.platform_names import normalize_key


def _get(obj: Any, key: str) -> Optional[str]:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def is_enabled(manifest: Dict[str, Any]) -> bool:
    # Always enabled — Redream is the preferred standalone for Sega Dreamcast
    return True


def can_handle(game: Any, manifest: Dict[str, Any], return_reason: bool = False):
    key = normalize_key((_get(game, "platform") or "").strip())
    ok = key in {"sega dreamcast", "dreamcast"}
    if return_reason:
        return ok, f"platform_key={key}"
    return ok


def _resolve_exe() -> Optional[Path]:
    """Prefer Redream; fallback to None if absent."""
    exe = EmulatorPaths.redream()
    if exe.exists():
        return exe
    return None


def _resolve_rom(game: Any) -> Optional[Path]:
    rom_ref = (
        _get(game, "rom_path")
        or _get(game, "application_path")
        or _get(game, "romPath")
    )
    if not rom_ref:
        return None
    raw = str(rom_ref).replace("\\", "/")
    p = Path(raw)
    if p.is_absolute():
        return p
    return (LaunchBoxPaths.LAUNCHBOX_ROOT / raw).resolve()


def resolve(game: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    exe = _resolve_exe()
    if not exe:
        return {
            "success": False,
            "message": (
                f"MISSING-EMU: Redream not found at {EmulatorPaths.redream()} — "
                "install Redream or configure flycast_adapter as fallback."
            ),
        }

    rom = _resolve_rom(game)
    if not rom:
        return {"success": False, "message": "MISSING-ROM: no rom_path or application_path"}
    if not rom.exists():
        return {"success": False, "message": f"MISSING-ROM: {rom}"}

    return {
        "exe": str(exe),
        "args": [str(rom)],
        "cwd": str(exe.parent),
        "romfile": str(rom),
    }


def launch(game: Any, manifest: Dict[str, Any], runner) -> Dict[str, Any]:
    cfg = resolve(game, manifest)
    if not cfg.get("exe"):
        return cfg
    return runner.run(cfg)
