from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import platform
import re
import os

from backend.constants.a_drive_paths import LaunchBoxPaths


# Structured error codes for diagnostics and ScoreKeeper Sam
class TeknoParrotAdapterError:
    """Structured error codes for TeknoParrot adapter failures."""
    MISSING_PROFILE = "missing_profile"
    EXE_NOT_FOUND = "exe_not_found"
    STARTUP_TIMEOUT = "startup_timeout"
    UPDATER_STUCK = "updater_stuck"
    CONFIG_UNRESOLVED = "config_unresolved"
    TITLE_EMPTY = "title_empty"
    USERPROFILES_MISSING = "userprofiles_missing"
    PROFILE_NOT_FOUND = "profile_not_found"


class TeknoParrotLaunchError(Exception):
    """Exception raised when TeknoParrot pre-launch checks fail."""
    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.error_code = error_code


def _is_wsl() -> bool:
    return platform.system() == "Linux" and "microsoft" in platform.release().lower()


def _norm_path(p: str) -> Path:
    """Normalize A:/ style paths to /mnt/a when under WSL; leave Windows paths on Windows.

    This mirrors the adapter path handling used elsewhere and honors the
    fixed-structure doctrine (no dynamic discovery).
    """
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


def _routing_policy_path() -> Path:
    # A:/configs/routing-policy.json (via AA_DRIVE_ROOT)
    return Path(LaunchBoxPaths.AA_DRIVE_ROOT) / "configs" / "routing-policy.json"


_POLICY_CACHE: Optional[Dict[str, Any]] = None
_POLICY_MTIME: Optional[float] = None
_ALIAS_CACHE: Optional[Dict[str, str]] = None
_ALIAS_MTIME: Optional[float] = None


def _get_policy() -> Dict[str, Any]:
    global _POLICY_CACHE, _POLICY_MTIME
    try:
        target = _routing_policy_path()
        if not target.exists():
            _POLICY_CACHE, _POLICY_MTIME = {}, None
            return {}
        mtime = target.stat().st_mtime
        if _POLICY_CACHE is None or _POLICY_MTIME != mtime:
            import json
            _POLICY_CACHE = json.loads(target.read_text(encoding="utf-8")) or {}
            _POLICY_MTIME = mtime
        return _POLICY_CACHE or {}
    except Exception:
        return {}


def _alias_file_path() -> Path:
    return Path(LaunchBoxPaths.AA_DRIVE_ROOT) / "configs" / "teknoparrot-aliases.json"


def _get_profile_alias(title: str) -> Optional[str]:
    """Return profile filename override (e.g., VT4.xml) for a given title, if defined.

    Reads A:/configs/teknoparrot-aliases.json with a simple mtime cache.
    Keys are matched case-insensitively by normalized title.
    
    Falls back to universal profile scanner if alias not found.
    """
    global _ALIAS_CACHE, _ALIAS_MTIME
    
    # First try manual alias file
    try:
        p = _alias_file_path()
        if p.exists():
            m = p.stat().st_mtime
            if _ALIAS_CACHE is None or _ALIAS_MTIME != m:
                import json
                raw = json.loads(p.read_text(encoding="utf-8")) or {}
                # Normalize keys to lowercase for case-insensitive lookup
                _ALIAS_CACHE = {str(k).strip().lower(): str(v) for k, v in raw.items()}
                _ALIAS_MTIME = m
            key = (title or "").strip().lower()
            alias = _ALIAS_CACHE.get(key) if _ALIAS_CACHE else None
            if alias:
                return alias
    except Exception:
        pass
    
    # Fallback: Use universal profile scanner (scans <GameName> from XMLs)
    try:
        from backend.services.adapters import teknoparrot_universal_adapter
        profile = teknoparrot_universal_adapter.find_profile(title)
        if profile:
            return profile
    except Exception:
        pass
    
    return None


def _use_ahk_wrapper_for_lightgun() -> bool:
    policy = _get_policy()
    profiles = (policy.get("profiles") or {}) if isinstance(policy, dict) else {}
    lightgun = (profiles.get("lightgun") or {}) if isinstance(profiles, dict) else {}
    return bool(lightgun.get("ahk_wrapper", True))


def _kill_existing_enabled() -> bool:
    policy = _get_policy()
    profiles = (policy.get("profiles") or {}) if isinstance(policy, dict) else {}
    # Default true to avoid TeknoParrot single-instance prompt
    # Allow override via profiles.lightgun.kill_existing / profiles.general.kill_existing
    lg = (profiles.get("lightgun") or {}) if isinstance(profiles, dict) else {}
    gen = (profiles.get("general") or {}) if isinstance(profiles, dict) else {}
    if isinstance(lg.get("kill_existing"), bool):
        return bool(lg.get("kill_existing"))
    if isinstance(gen.get("kill_existing"), bool):
        return bool(gen.get("kill_existing"))
    return True


def _is_lightgun_game(game: Any) -> bool:
    # Treat TeknoParrot (Light Guns) platform or category containing "Light Gun" as lightgun profile
    plat = (_get(game, "platform") or "").strip()
    if plat.lower() == "teknoparrot (light guns)".lower():
        return True
    try:
        cats = [str(c).lower() for c in (_get(game, "categories") or [])]
        return any("light gun" in c or "lightgun" in c for c in cats)
    except Exception:
        return False


def can_handle(game: Any, manifest: Dict[str, Any]) -> bool:
    """Predicate: claim TeknoParrot platforms (including light-gun variant).

    This remains scoped to TeknoParrot only (won't claim MAME/console).
    Checks both platform name pattern AND manifest platform list.
    """
    plat = (_get(game, "platform") or "").strip().lower()

    # Check if "teknoparrot" is in platform name (original behavior)
    if "teknoparrot" in plat:
        return True

    # Check manifest for additional platforms (e.g., "Taito Type X")
    try:
        emus = (manifest.get("emulators") or {}) if isinstance(manifest, dict) else {}
        tp_config = emus.get("teknoparrot") if isinstance(emus, dict) else None
        if isinstance(tp_config, dict):
            platforms = tp_config.get("platforms", [])
            if isinstance(platforms, list):
                plat_original = (_get(game, "platform") or "").strip()
                return plat_original in platforms
    except Exception:
        pass

    return False


def _teknoparrot_exe(manifest: Optional[Dict[str, Any]] = None) -> Path:
    """Resolve TeknoParrotUi.exe from manifest or fixed roots.

    Search order:
    1) Read from manifest (launchers.json): emulators.teknoparrot.exe
    2) A:/Emulators/TeknoParrot Latest/TeknoParrotUi.exe (prioritize Latest)
    3) A:/Emulators/TeknoParrot/TeknoParrotUi.exe
    4) A:/LaunchBox/Emulators/TeknoParrot/TeknoParrotUi.exe
    """
    # Try to read from manifest first
    if manifest:
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

    # Fall back to fixed paths - prioritize Latest version
    latest_path = LaunchBoxPaths.EMULATORS_ROOT / "TeknoParrot Latest" / "TeknoParrotUi.exe"
    if latest_path.exists():
        return latest_path

    std_path = LaunchBoxPaths.EMULATORS_ROOT / "TeknoParrot" / "TeknoParrotUi.exe"
    if std_path.exists():
        return std_path

    lb_path = LaunchBoxPaths.LAUNCHBOX_ROOT / "Emulators" / "TeknoParrot" / "TeknoParrotUi.exe"
    return lb_path


def _ahk_wrapper_path() -> Path:
    # Conventional tools location under AA_DRIVE_ROOT
    return Path(LaunchBoxPaths.AA_DRIVE_ROOT) / "Tools" / "lightgun_wrapper.ahk"


def pre_launch_check(manifest: Optional[Dict[str, Any]] = None, profile: Optional[str] = None) -> Dict[str, Any]:
    """Perform pre-launch validation for TeknoParrot.
    
    Checks:
    1. License Guard: Verify UserProfiles folder exists (indicates valid installation/license)
    2. Profile Guard: If profile specified, verify the XML profile file exists
    
    Args:
        manifest: Optional launcher manifest for exe path resolution
        profile: Optional profile name to validate (e.g., "VT4.xml")
    
    Returns:
        Dict with 'valid' key (bool) and optional 'error_code'/'message' on failure
    
    Raises:
        TeknoParrotLaunchError: If validation fails (alternative to returning error dict)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Find TeknoParrot installation
    tp_exe = _teknoparrot_exe(manifest)
    if not tp_exe.exists():
        return {
            "valid": False,
            "error_code": TeknoParrotAdapterError.EXE_NOT_FOUND,
            "message": f"TeknoParrot executable not found: {tp_exe}",
        }
    
    tp_root = tp_exe.parent
    
    # License Guard: Check UserProfiles folder exists
    user_profiles_dir = tp_root / "UserProfiles"
    if not user_profiles_dir.exists():
        error_msg = (
            "TeknoParrot UserProfiles folder missing. "
            "This may indicate an invalid license or incomplete installation. "
            f"Expected at: {user_profiles_dir}"
        )
        logger.warning(f"[TeknoParrot] {error_msg}")
        return {
            "valid": False,
            "error_code": TeknoParrotAdapterError.USERPROFILES_MISSING,
            "message": error_msg,
        }
    
    # Profile Guard: If profile is specified, verify it exists
    if profile:
        # Ensure .xml extension
        profile_name = profile if profile.lower().endswith('.xml') else f"{profile}.xml"
        profile_path = user_profiles_dir / profile_name
        
        if not profile_path.exists():
            # Also check GameProfiles folder (some versions use this)
            game_profiles_dir = tp_root / "GameProfiles"
            alt_profile_path = game_profiles_dir / profile_name
            
            if not alt_profile_path.exists():
                error_msg = (
                    f"TeknoParrot profile not found: {profile_name}. "
                    f"Checked: {profile_path} and {alt_profile_path}"
                )
                logger.warning(f"[TeknoParrot] {error_msg}")
                return {
                    "valid": False,
                    "error_code": TeknoParrotAdapterError.PROFILE_NOT_FOUND,
                    "message": error_msg,
                }
    
    logger.info(f"[TeknoParrot] Pre-launch check passed for {tp_root}")
    return {"valid": True}


def resolve(game: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve TeknoParrot launch config.

    Returns a dict with keys: exe, args, cwd, adapter, profile.
    Returns error dict with error_code if cannot resolve.
    When lightgun profile applies and policy enables AHK wrapper, returns a
    cmd.exe invocation that first launches the AHK wrapper then TeknoParrot.
    """
    title = (_get(game, "title") or "").strip()
    if not title:
        return {
            "success": False,
            "message": "Game title is empty",
            "error_code": TeknoParrotAdapterError.TITLE_EMPTY,
            "adapter": "teknoparrot",
        }

    tp_exe = _teknoparrot_exe(manifest)
    # Resolve profile filename via alias when available; otherwise pass the title as-is.
    # Many TeknoParrot profiles are short names (e.g., VT4.xml) rather than full titles.
    prof = _get_profile_alias(title) or title
    # Ensure .xml extension for auto-launch to work
    if not prof.lower().endswith('.xml'):
        prof = f"{prof}.xml"
    
    # Pre-launch validation: license and profile guards
    check_result = pre_launch_check(manifest=manifest, profile=prof)
    if not check_result.get("valid", False):
        return {
            "success": False,
            "message": check_result.get("message", "Pre-launch check failed"),
            "error_code": check_result.get("error_code", TeknoParrotAdapterError.CONFIG_UNRESOLVED),
            "adapter": "teknoparrot",
        }
    
    # Build args - --profile selects game, --startGame auto-launches it
    # Note: --startGame is the correct flag for newer TeknoParrot (not --start)
    args: List[str] = [f"--profile={prof}", "--startGame"]

    # If lightgun profile and policy requests AHK, wrap via cmd.exe
    use_kill = _kill_existing_enabled()
    if _is_lightgun_game(game) and _use_ahk_wrapper_for_lightgun():
        ahk = _ahk_wrapper_path()
        # Use Windows cmd for a simple one-shot wrapper with pre-kill
        exe = Path(os.environ.get("COMSPEC", r"C:\\Windows\\System32\\cmd.exe"))
        # cmd /c taskkill /IM TeknoParrotUi.exe /F & start "" <ahk> & start "" <teknoparrot> -run --profile=Title
        wrapped_args: List[str] = ["/c"]
        if use_kill:
            wrapped_args += ["taskkill", "/IM", "TeknoParrotUi.exe", "/F", "&"]
        wrapped_args += [
            "start", "", str(ahk), "&",
            "start", "", str(tp_exe), *args,
        ]
        return {
            "exe": str(_norm_path(str(exe))),
            "args": wrapped_args,
            "cwd": str(_norm_path(str(tp_exe.parent))),
            "adapter": "teknoparrot",
            "profile": prof,
            "ahk_wrapper": True,
        }

    # Simple direct TeknoParrot launch - just open the UI with the profile
    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"[TeknoParrot] Launching profile: {prof} for game: {title}")
    logger.info(f"[TeknoParrot] Executable: {tp_exe}")

    # Direct launch - TeknoParrot will open with the game ready
    return {
        "exe": str(_norm_path(str(tp_exe))),
        "args": args,
        "cwd": str(_norm_path(str(tp_exe.parent))),
        "adapter": "teknoparrot",
        "profile": prof,
    }


def launch(game: Any, manifest: Dict[str, Any], runner) -> Dict[str, Any]:
    """Launch a TeknoParrot game.
    
    Returns structured result with adapter name and profile for ScoreKeeper Sam.
    """
    cfg = resolve(game, manifest)
    
    # Check for error from resolve()
    if not cfg or cfg.get("error_code"):
        return {
            "success": False,
            "message": cfg.get("message", "TeknoParrot config unresolved"),
            "error_code": cfg.get("error_code", TeknoParrotAdapterError.CONFIG_UNRESOLVED),
            "adapter": "teknoparrot",
        }
    
    # Run the launch
    result = runner.run(cfg)
    
    # Enrich result with adapter metadata for logging
    if isinstance(result, dict):
        result["adapter"] = "teknoparrot"
        result["profile"] = cfg.get("profile")
    
    return result
