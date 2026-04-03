from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
import json
import shlex

from backend.constants.a_drive_paths import EmulatorPaths, LaunchBoxPaths
from backend.services.platform_names import normalize_key


_EMU_CONFIG_PATH = Path("configs/emulator_paths.json")


def _get(obj: Any, key: str) -> Optional[str]:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _load_emulator_paths() -> Dict[str, Any]:
    try:
        return json.loads(_EMU_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_relative_to_launchbox(raw_path: str) -> Path:
    raw = (raw_path or "").replace("/", "\\")
    path = Path(raw)
    if path.is_absolute():
        return path
    return (LaunchBoxPaths.LAUNCHBOX_ROOT / path).resolve()


def _resolve_emulator_entry(game: Any) -> Optional[Dict[str, Any]]:
    emulator_id = (_get(game, "emulator_id") or "").strip()
    if not emulator_id:
        return None
    entries = (_load_emulator_paths().get("emulators") or {})
    entry = entries.get(emulator_id)
    return entry if isinstance(entry, dict) else None


def _resolve_exe(game: Any) -> Optional[Path]:
    """
    Resolve PPSSPP executable path.
    Priority:
      1. emulator_id entry in configs/emulator_paths.json (LaunchBox-linked build)
      2. EmulatorPaths.ppsspp() constant (known cabinet location)
    """
    entry = _resolve_emulator_entry(game)
    if entry:
        exe = _resolve_relative_to_launchbox(str(entry.get("executable_path") or ""))
        if exe.exists():
            return exe

    # Fallback: direct path constant — always works on this cabinet
    fallback = EmulatorPaths.ppsspp()
    if fallback.exists():
        return fallback

    return None


def is_enabled(manifest: Dict[str, Any]) -> bool:
    return True


def can_handle(game: Any, manifest: Dict[str, Any], return_reason: bool = False):
    key = normalize_key((_get(game, "platform") or "").strip())
    ok = key in {"sony psp", "sony psp minis", "psp", "psp minis"}
    if return_reason:
        return ok, f"platform_key={key}"
    return ok


def resolve(game: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    exe = _resolve_exe(game)
    if not exe:
        return {
            "success": False,
            "message": (
                f"MISSING-EMU: PPSSPP not found at {EmulatorPaths.ppsspp()} — "
                "check Emulators/PPSSPP/PPSSPPWindows64.exe exists on the drive."
            ),
        }

    rom_ref = _get(game, "rom_path") or _get(game, "application_path") or _get(game, "romPath")
    if not rom_ref:
        return {"success": False, "message": "MISSING-ROM: no rom_path or application_path"}

    rom_path = _resolve_relative_to_launchbox(str(rom_ref))
    if not rom_path.exists():
        return {"success": False, "message": f"MISSING-ROM: {rom_path}"}

    # Preserve any command_line args from the emulator_paths entry if present
    args = []
    entry = _resolve_emulator_entry(game)
    if entry:
        command_line = str(entry.get("command_line") or "").strip()
        if command_line:
            args.extend(shlex.split(command_line, posix=False))
    args.append(str(rom_path))

    return {
        "exe": str(exe),
        "args": args,
        "cwd": str(exe.parent),
        "romfile": str(rom_path),
        "notes": f"ppsspp:rom={rom_path.name}",
    }


def launch(game: Any, manifest: Dict[str, Any], runner) -> Dict[str, Any]:
    cfg = resolve(game, manifest)
    if not cfg.get("exe"):
        return cfg
    return runner.run(cfg)
