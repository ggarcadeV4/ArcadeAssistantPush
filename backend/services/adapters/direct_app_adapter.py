"""Direct Application Path Adapter

Launches games using their ApplicationPath from LaunchBox XML.
This is used for games that have custom launch scripts (AHK, batch files, etc.)
or standalone executables configured in LaunchBox.

Supports:
- Taito Type X games with AHK gamepad scripts
- Any game with a custom ApplicationPath in LaunchBox
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import platform
import re
import os
import shutil
import shlex
import logging

from backend.constants.a_drive_paths import LaunchBoxPaths
from backend.constants.drive_root import get_drive_root

logger = logging.getLogger(__name__)


def _is_wsl() -> bool:
    return platform.system() == "Linux" and "microsoft" in platform.release().lower()


def _norm_path(p: str) -> Path:
    """Normalize A:/ style paths to /mnt/a when under WSL; leave Windows paths on Windows."""
    if not p:
        return Path("")
    s = p.replace("\\", "/")
    if _is_wsl():
        s = s.replace("A:/", "/mnt/a/")
        m = re.match(r"^([A-Za-z]):/(.*)$", s)
        if m:
            s = f"/mnt/{m.group(1).lower()}/{m.group(2)}"
    return Path(s)


def _get(obj: Any, key: str) -> Optional[str]:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _extract_teknoparrot_profile_from_ahk(ahk_path: Path) -> Optional[str]:
    """Parse AHK script to extract TeknoParrot profile name."""
    try:
        content = ahk_path.read_text(encoding="utf-8-sig")
        for line in content.split("\n"):
            line = line.strip()
            if "TeknoParrotUi.exe" in line and "--profile=" in line:
                match = re.search(r"--profile=([^\s]+)", line)
                if match:
                    return match.group(1)
    except Exception:
        pass
    return None


def _get_teknoparrot_exe_from_manifest(manifest: Optional[Dict[str, Any]]) -> Optional[Path]:
    """Get TeknoParrotUi.exe path from manifest."""
    if not manifest:
        return None

    try:
        emus = (manifest.get("emulators") or {}) if isinstance(manifest, dict) else {}
        tp_config = emus.get("teknoparrot") if isinstance(emus, dict) else None
        if isinstance(tp_config, dict):
            exe_path = tp_config.get("exe")
            if exe_path:
                p = _norm_path(str(exe_path))
                if p.exists():
                    return p
    except Exception:
        pass

    return None


def _extract_ahk_command_field(line: str) -> Optional[str]:
    """Extract the first AHK Run/RunWait command field, respecting quoted commas."""
    match = re.match(r"^(?:Run|RunWait)\s*,\s*", line, re.IGNORECASE)
    if not match:
        return None

    remainder = line[match.end():]
    in_quotes = False
    for idx, char in enumerate(remainder):
        if char == '"':
            in_quotes = not in_quotes
        elif char == "," and not in_quotes:
            return remainder[:idx].strip()
    return remainder.strip()


def _extract_run_target_from_ahk(ahk_path: Path) -> Tuple[Optional[str], Optional[list[str]]]:
    """Extract executable/command target and argument tokens from the first Run line."""
    try:
        content = ahk_path.read_text(encoding="utf-8-sig")
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lower = line.lower()
            if not (lower.startswith("run,") or lower.startswith("runwait,")):
                continue

            command_text = _extract_ahk_command_field(line)
            if not command_text:
                continue

            try:
                tokens = shlex.split(command_text, posix=False)
            except Exception:
                tokens = command_text.split()
            if not tokens:
                continue

            target = tokens[0].strip().strip('"')
            args = [tok.strip() for tok in tokens[1:]]
            return target, args
    except Exception:
        pass
    return None, None


def _parse_daphne_ahk_command(ahk_path: Path, manifest: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Parse Daphne/Hypseus/Singe AHK scripts into a direct executable launch."""
    run_target, run_args = _extract_run_target_from_ahk(ahk_path)
    if not run_target or run_args is None:
        logger.debug("[DirectApp] AHK parse skip: no_run_command_found in %s", ahk_path)
        return None

    target_name = Path(run_target).name
    exe_name = target_name.lower()
    known_exes = {"daphne.exe", "daphne", "hypseus", "hypseus.exe", "singe.exe", "singe"}
    if exe_name not in known_exes:
        logger.debug(
            "[DirectApp] AHK parse skip: unsupported_target ('%s' not in allowed list)",
            target_name,
        )
        return None

    script_dir = ahk_path.parent
    target_path = Path(run_target.replace("\\", "/"))
    if target_path.is_absolute():
        exe_path = target_path
    else:
        exe_path = (script_dir / target_path).resolve()

    if not exe_path.exists() and not exe_path.suffix:
        exe_candidate = exe_path.with_suffix(".exe")
        if exe_candidate.exists():
            exe_path = exe_candidate

    if not exe_path.exists():
        manifest_exe = None
        if exe_name in {"daphne", "daphne.exe", "hypseus", "hypseus.exe"}:
            manifest_exe = _get_hypseus_exe_from_manifest(manifest)
        if manifest_exe and Path(manifest_exe).exists():
            exe_path = Path(manifest_exe)
        else:
            which_match = shutil.which(target_name) or shutil.which(f"{target_name}.exe")
            if which_match:
                exe_path = Path(which_match)

    if not exe_path.exists():
        logger.debug("[DirectApp] AHK parse skip: missing_executable (tried %s)", exe_path)
        return None

    return {
        "exe": str(_norm_path(str(exe_path))),
        "args": run_args,
        "cwd": str(_norm_path(str(script_dir))),
    }


def _get_hypseus_exe_from_manifest(manifest: Optional[Dict[str, Any]]) -> Optional[Path]:
    """Find hypseus executable from manifest, then standard fallback locations."""
    if manifest and isinstance(manifest, dict):
        try:
            emus = manifest.get("emulators") or {}
            if isinstance(emus, dict):
                cfg = emus.get("hypseus")
                if isinstance(cfg, dict):
                    exe_path = cfg.get("exe")
                    if exe_path:
                        p = _norm_path(str(exe_path))
                        if p.exists():
                            return p
        except Exception:
            pass

    candidates = [
        LaunchBoxPaths.EMULATORS_ROOT / "Hypseus" / "hypseus.exe",
        LaunchBoxPaths.EMULATORS_ROOT / "Hypseus" / "Hypseus Singe" / "hypseus.exe",
        LaunchBoxPaths.EMULATORS_ROOT / "Hypseus Singe" / "hypseus.exe",
        LaunchBoxPaths.EMULATORS_ROOT / "Daphne" / "hypseus.exe",
        LaunchBoxPaths.LAUNCHBOX_ROOT / "Emulators" / "Hypseus" / "hypseus.exe",
        LaunchBoxPaths.LAUNCHBOX_ROOT / "Emulators" / "Hypseus" / "Hypseus Singe" / "hypseus.exe",
        LaunchBoxPaths.LAUNCHBOX_ROOT / "Emulators" / "Hypseus Singe" / "hypseus.exe",
    ]
    for candidate in candidates:
        p = _norm_path(str(candidate))
        if p.exists():
            return p
    return None


def _rewrite_framefile_arg(args: list[str], script_dir: Path) -> list[str]:
    """Convert relative -framefile argument to an absolute path."""
    rewritten = list(args)
    for idx, token in enumerate(rewritten):
        low = token.lower()
        if low == "-framefile" and idx + 1 < len(rewritten):
            frame_val = rewritten[idx + 1].strip().strip('"')
            frame_path = Path(frame_val.replace("\\", "/"))
            if not frame_path.is_absolute():
                frame_path = (script_dir / frame_path).resolve()
            rewritten[idx + 1] = str(_norm_path(str(frame_path)))
            return rewritten
        if low.startswith("-framefile="):
            frame_val = token.split("=", 1)[1].strip().strip('"')
            frame_path = Path(frame_val.replace("\\", "/"))
            if not frame_path.is_absolute():
                frame_path = (script_dir / frame_path).resolve()
            rewritten[idx] = f"-framefile={_norm_path(str(frame_path))}"
            return rewritten
    return rewritten


def can_handle(game: Any, manifest: Dict[str, Any]) -> bool:
    """Check if game has ApplicationPath configured in LaunchBox."""
    app_path = _get(game, "application_path")
    if not app_path:
        return False

    ext = Path(app_path).suffix.lower()
    allowed_exts = {".ahk", ".exe", ".bat", ".cmd", ".lnk"}
    if ext not in allowed_exts:
        return False

    platform_name = (_get(game, "platform") or "").strip().lower()
    supported_platforms = [
        "taito type x",
        "daphne",
        "american laser games",
        "pc games",
        "windows",
        "windows games",
        "ms-dos",
        "dos",
    ]

    if platform_name in supported_platforms:
        return True

    if ext == ".exe":
        return True

    return False


def resolve(game: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve direct application launch config."""
    app_path = (_get(game, "application_path") or "").strip()
    if not app_path:
        return {}

    app_path = app_path.replace("\\", "/")

    launchbox_root = LaunchBoxPaths.LAUNCHBOX_ROOT
    resolved_path = (launchbox_root / app_path).resolve()
    normalized_path = _norm_path(str(resolved_path))

    if not normalized_path.exists():
        logger.warning("ApplicationPath not found: %s", normalized_path)
        return {}

    ext = normalized_path.suffix.lower()

    if ext == ".ahk":
        daphne_cmd = _parse_daphne_ahk_command(normalized_path, manifest)
        if daphne_cmd:
            logger.info("Bypassing AHK, launching Daphne-family exe directly: %s", daphne_cmd["exe"])
            return daphne_cmd
        logger.debug("[DirectApp] AHK direct bypass unavailable for %s", normalized_path)

        profile_name = _extract_teknoparrot_profile_from_ahk(normalized_path)
        if profile_name:
            tp_exe = _get_teknoparrot_exe_from_manifest(manifest)
            if tp_exe and tp_exe.exists():
                logger.info("Bypassing AHK script, launching TeknoParrot directly with profile: %s", profile_name)

                cmd_exe = Path(os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"))
                return {
                    "exe": str(_norm_path(str(cmd_exe))),
                    "args": ["/c", "start", "/D", f'"{tp_exe.parent}"', '""', f'"{tp_exe}"', "-run", f"--profile={profile_name}"],
                    "cwd": str(_norm_path(str(tp_exe.parent))),
                }

        ahk_exe = None
        ahk_env = os.environ.get("AHK_PATH")
        if ahk_env and Path(ahk_env).exists():
            ahk_exe = Path(ahk_env)
        if not ahk_exe:
            ahk_which = shutil.which("AutoHotkey.exe") or shutil.which("AutoHotkey")
            if ahk_which:
                ahk_exe = Path(ahk_which)
        if not ahk_exe:
            drive_root = get_drive_root(allow_cwd_fallback=True)
            if drive_root.drive:
                drive_letter_root = Path(drive_root.drive + "\\")
            else:
                drive_letter_root = drive_root
            ahk_candidates = [
                drive_letter_root / "Tools" / "AutoHotkey" / "AutoHotkey.exe",
                drive_letter_root / "Tools" / "AutoHotkey" / "AutoHotkeyU64.exe",
                drive_letter_root / "Tools" / "AutoHotkey" / "AutoHotkeyU32.exe",
                drive_letter_root / "Tools" / "Teknoparrot Auto Xinput" / "AutoHotkeyU32.exe",
            ]
            for candidate in ahk_candidates:
                if candidate.exists():
                    ahk_exe = candidate
                    break
        if not ahk_exe:
            return {
                "error": "AutoHotkey not found. Set AHK_PATH env var or install AutoHotkey.",
                "exe": None,
                "args": [],
                "cwd": str(normalized_path.parent),
            }

        return {
            "exe": str(_norm_path(str(ahk_exe))),
            "args": [str(normalized_path)],
            "cwd": str(normalized_path.parent),
        }

    if ext == ".exe":
        return {
            "exe": str(normalized_path),
            "args": [],
            "cwd": str(normalized_path.parent),
        }

    if ext in [".bat", ".cmd"]:
        cmd_exe = Path(os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"))
        return {
            "exe": str(_norm_path(str(cmd_exe))),
            "args": ["/c", str(normalized_path)],
            "cwd": str(normalized_path.parent),
        }

    return {
        "exe": str(normalized_path),
        "args": [],
        "cwd": str(normalized_path.parent),
    }


def launch(game: Any, manifest: Dict[str, Any], runner) -> Dict[str, Any]:
    """Launch game using its ApplicationPath."""
    cfg = resolve(game, manifest)
    if not cfg:
        return {"success": False, "message": "ApplicationPath config unresolved"}
    return runner.run(cfg)