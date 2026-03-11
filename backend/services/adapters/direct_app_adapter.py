"""Direct Application Path Adapter

Launches games using their ApplicationPath from LaunchBox XML.
This is used for games that have custom launch scripts (AHK, batch files, etc.)
or standalone executables configured in LaunchBox.

Supports:
- Taito Type X games with AHK gamepad scripts
- Any game with a custom ApplicationPath in LaunchBox
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import platform
import re
import os
import shutil

from backend.constants.a_drive_paths import LaunchBoxPaths
from backend.constants.drive_root import get_drive_root


def _is_wsl() -> bool:
    return platform.system() == "Linux" and "microsoft" in platform.release().lower()


def _norm_path(p: str) -> Path:
    """Normalize A:/ style paths to /mnt/a when under WSL; leave Windows paths on Windows."""
    if not p:
        return Path("")
    s = p.replace("\\", "/")
    if _is_wsl():
        # A:/ → /mnt/a/, generic X:/ → /mnt/x/
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
    """Parse AHK script to extract TeknoParrot profile name.

    Looks for lines like:
    Run, D:\Emulators\Teknoparrot Gamepad\TeknoParrotUi.exe --profile=BBCF.xml

    Returns the profile name (e.g., "BBCF.xml") or None if not found.
    """
    try:
        content = ahk_path.read_text(encoding="utf-8-sig")  # Handle BOM
        for line in content.split("\n"):
            line = line.strip()
            if "TeknoParrotUi.exe" in line and "--profile=" in line:
                # Extract profile name
                match = re.search(r'--profile=([^\s]+)', line)
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


def can_handle(game: Any, manifest: Dict[str, Any]) -> bool:
    """Check if game has ApplicationPath configured in LaunchBox.

    This adapter handles games that use custom launch scripts or standalone executables.
    Supports: Taito Type X, Daphne, American Laser Games
    """
    # Only handle if game has an ApplicationPath
    app_path = _get(game, "application_path")
    if not app_path:
        return False

    # Only handle when ApplicationPath points to a script/launcher we can execute directly
    ext = Path(app_path).suffix.lower()
    allowed_exts = {".ahk", ".exe", ".bat", ".cmd", ".lnk"}
    if ext not in allowed_exts:
        return False

    # Handle platforms that use AHK scripts or custom launchers
    platform_name = (_get(game, "platform") or "").strip().lower()
    supported_platforms = [
        "taito type x",
        "daphne",
        "american laser games",
        "pc games",
        "windows",
        "windows games",
        "ms-dos",
        "dos"
    ]

    if platform_name in supported_platforms:
        return True

    # Also handle any game with .exe ApplicationPath (standalone PC games)
    if ext == ".exe":
        return True

    return False


def _parse_daphne_ahk_command(ahk_path: Path) -> Optional[Dict[str, Any]]:
    """Parse Daphne/Hypseus/Singe AHK script to extract the Run command.

    AHK scripts follow this pattern:
        SetWorkingDir %A_ScriptDir%
        Run, <exe> <args...>

    Returns dict with exe, args, cwd if parseable, None otherwise.
    """
    import shlex
    import logging
    _logger = logging.getLogger(__name__)

    # Known Daphne-family executables (lowercase for matching)
    KNOWN_EXES = {"daphne.exe", "hypseus", "hypseus.exe", "singe.exe",
                  "hypseus_subsystem.exe"}

    try:
        content = ahk_path.read_text(encoding="utf-8-sig")
        for line in content.split("\n"):
            stripped = line.strip()
            # Match "Run," or "Run ," with optional whitespace
            if not stripped.lower().startswith("run,") and not stripped.lower().startswith("run ,"):
                continue

            # Extract everything after "Run,"
            idx = stripped.index(",")
            cmd_str = stripped[idx + 1:].strip()

            # Split into exe and args
            parts = cmd_str.split(None, 1)
            if not parts:
                continue

            exe_name = parts[0]
            args_str = parts[1] if len(parts) > 1 else ""

            if exe_name.lower() not in KNOWN_EXES:
                continue

            # Resolve exe relative to AHK script directory
            script_dir = ahk_path.parent
            exe_path = script_dir / exe_name

            # AHK scripts may omit .exe extension (e.g., "Run, Hypseus" for hypseus.exe)
            if not exe_path.exists() and not exe_name.lower().endswith(".exe"):
                exe_path_with_ext = script_dir / (exe_name + ".exe")
                if exe_path_with_ext.exists():
                    exe_path = exe_path_with_ext
                    exe_name = exe_name + ".exe"

            if not exe_path.exists():
                _logger.warning(
                    "[DaphneAHK] Exe %s not found in %s", exe_name, script_dir
                )
                continue

            # Parse args — use simple split (shlex may choke on Windows paths)
            args = args_str.split() if args_str else []

            _logger.info(
                "[DaphneAHK] Bypassing AHK, launching directly: %s %s (cwd=%s)",
                exe_path, " ".join(args), script_dir,
            )
            return {
                "exe": str(exe_path),
                "args": args,
                "cwd": str(script_dir),
            }
    except Exception as exc:
        _logger.debug("[DaphneAHK] Failed to parse %s: %s", ahk_path, exc)

    return None


def resolve(game: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve direct application launch config.

    Returns a dict with keys: exe, args, cwd. Empty dict if cannot resolve.
    """
    app_path = (_get(game, "application_path") or "").strip()
    if not app_path:
        return {}

    # ApplicationPath in LaunchBox XML is relative to LaunchBox root
    # Format: ..\Roms\TTX\_AHK Gamepad\Akai Katana Shin.ahk
    # The ".." means go up from LaunchBox root, not from Data/Platforms

    # Normalize backslashes to forward slashes for cross-platform compatibility
    app_path = app_path.replace("\\", "/")

    # Resolve relative path against LaunchBox root (not Data/Platforms)
    launchbox_root = LaunchBoxPaths.LAUNCHBOX_ROOT
    resolved_path = (launchbox_root / app_path).resolve()

    # Normalize for WSL/Windows
    normalized_path = _norm_path(str(resolved_path))

    if not normalized_path.exists():
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"ApplicationPath not found: {normalized_path}")
        return {}

    # Determine how to launch based on file extension
    ext = normalized_path.suffix.lower()

    if ext == ".ahk":
        # ── Daphne / Hypseus / Singe direct-launch (bypass AutoHotkey) ──
        # Parse the AHK script; if it references a known laserdisc emulator
        # exe, launch that exe directly instead of invoking AutoHotkey.
        daphne_cmd = _parse_daphne_ahk_command(normalized_path)
        if daphne_cmd:
            return daphne_cmd

        # Special handling for TeknoParrot AHK scripts
        # Parse the script to extract the profile name and launch directly
        # This avoids issues with hardcoded paths in AHK scripts
        profile_name = _extract_teknoparrot_profile_from_ahk(normalized_path)
        if profile_name:
            # Launch TeknoParrot directly with the profile
            tp_exe = _get_teknoparrot_exe_from_manifest(manifest)
            if tp_exe and tp_exe.exists():
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Bypassing AHK script, launching TeknoParrot directly with profile: {profile_name}")

                # Use cmd.exe to handle the launch
                cmd_exe = Path(os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"))
                return {
                    "exe": str(_norm_path(str(cmd_exe))),
                    "args": ["/c", "start", "/D", f'"{tp_exe.parent}"', '""', f'"{tp_exe}"', "-run", f"--profile={profile_name}"],
                    "cwd": str(_norm_path(str(tp_exe.parent)))
                }

        # Fall back to launching AHK script directly if profile extraction fails
        # Drive-letter agnostic: try AHK_PATH env, shutil.which, then Tools folder
        ahk_exe = None
        ahk_env = os.environ.get("AHK_PATH")
        if ahk_env and Path(ahk_env).exists():
            ahk_exe = Path(ahk_env)
        if not ahk_exe:
            ahk_which = shutil.which("AutoHotkey.exe") or shutil.which("AutoHotkey")
            if ahk_which:
                ahk_exe = Path(ahk_which)
        if not ahk_exe:
            # Try drive letter root Tools folder (A:\Tools, not project folder)
            drive_root = get_drive_root(allow_cwd_fallback=True)
            # Extract drive letter root (e.g., A:\ from A:\Arcade Assistant Local)
            if drive_root.drive:
                drive_letter_root = Path(drive_root.drive + "\\")
            else:
                drive_letter_root = drive_root
            # Check multiple possible AHK locations
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
                "cwd": str(normalized_path.parent)
            }

        return {
            "exe": str(_norm_path(str(ahk_exe))),
            "args": [str(normalized_path)],
            "cwd": str(normalized_path.parent)
        }

    elif ext == ".exe":
        # Direct executable
        return {
            "exe": str(normalized_path),
            "args": [],
            "cwd": str(normalized_path.parent)
        }

    elif ext in [".bat", ".cmd"]:
        # Batch file - run via cmd.exe
        cmd_exe = Path(os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"))
        return {
            "exe": str(_norm_path(str(cmd_exe))),
            "args": ["/c", str(normalized_path)],
            "cwd": str(normalized_path.parent)
        }

    else:
        # Unknown extension - try launching directly
        return {
            "exe": str(normalized_path),
            "args": [],
            "cwd": str(normalized_path.parent)
        }


def launch(game: Any, manifest: Dict[str, Any], runner) -> Dict[str, Any]:
    """Launch game using its ApplicationPath."""
    cfg = resolve(game, manifest)
    if not cfg:
        return {"success": False, "message": "ApplicationPath config unresolved"}
    return runner.run(cfg)
