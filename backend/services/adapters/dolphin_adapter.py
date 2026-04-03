from typing import Any, Dict, Optional
from pathlib import Path
from .adapter_utils import (
    dry_run_enabled,
    success_with_command,
    resolve_rom_for_launch,
    get_game_rom_path,
    launch_nogui_enabled,
)
from backend.constants.a_drive_paths import EmulatorPaths
from backend.services.platform_names import normalize_key


def is_enabled(manifest: Dict[str, Any]) -> bool:
    return True


def can_handle(game: Any, manifest: Dict[str, Any], return_reason: bool = False):
    key = normalize_key((getattr(game, 'platform', None) or (game.get('platform') if isinstance(game, dict) else '') or ''))
    # Standalone Dolphin handles both Wii and GameCube.
    # dolphin_libretro (RetroArch core) is blacklisted — it produces audio
    # with no visible gameplay (black screen) on this cabinet build.
    ok = key in {'nintendo wii', 'nintendo gamecube', 'gamecube'}
    if return_reason:
        return ok, f"platform_key={key}"
    return ok


def _resolve_exe(platform_key: str) -> Optional[Path]:
    """
    Return the correct Dolphin executable for the given platform.

    GameCube  → Dolphin Joystick  (arcade gamepad layout, standard GC controller mapping)
    Wii       → Dolphin Joystick  (same build, Wiimote/nunchuk emulated via gamepad)

    We use EmulatorPaths directly to avoid the ambiguous find_emulator_exe('dolphin')
    lookup which can match Dolphin Triforce, Dolphin-Controller, or DolphinWX variants.
    """
    exe = EmulatorPaths.dolphin_joystick()
    if exe.exists():
        return exe
    # Fallback: standard Dolphin build
    fallback = EmulatorPaths.dolphin()
    if fallback.exists():
        return fallback
    return None


def resolve(game: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    platform_key = normalize_key(
        (getattr(game, 'platform', None) or (game.get('platform') if isinstance(game, dict) else '') or '')
    )
    exe = _resolve_exe(platform_key)
    if not exe:
        return {
            "success": False,
            "message": (
                "MISSING-EMU: Dolphin Joystick not found at "
                f"{EmulatorPaths.dolphin_joystick()} — "
                f"fallback {EmulatorPaths.dolphin()} also missing"
            )
        }
    resolved, extracted_root, notes = resolve_rom_for_launch(game, 'dolphin')
    if not resolved:
        rp = get_game_rom_path(game)
        stem = Path(str(rp)).stem if rp else ""
        tried = ['.iso', '.wbfs', '.gcm', '.ciso', '.gcz']
        return {
            "success": False,
            "message": f"MISSING-ROM: stem='{stem}', tried_exts={tried}"
        }
    args = []
    if launch_nogui_enabled():
        args.append('-b')
    args += ['-e', str(resolved)]
    return {
        "exe": str(exe),
        "args": args,
        "cwd": str(exe.parent),
        "extracted_root": str(extracted_root) if extracted_root else None
    }


def launch(game: Any, manifest: Dict[str, Any], runner) -> Dict[str, Any]:
    cfg = resolve(game, manifest)
    if not cfg.get('exe'):
        return cfg
    exe = Path(cfg['exe'])
    args = cfg['args']
    if dry_run_enabled():
        out = success_with_command(exe, args)
        out.update({
            "resolved_file": args[-1] if args else "",
            "extracted": cfg.get('extracted_root')
        })
        return out
    return runner.run(cfg)
