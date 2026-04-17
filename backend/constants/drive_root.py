"""
Drive Root Helper (Golden Drive Contract)

Single source of truth for resolving the configured cabinet root and the
runtime paths derived from it. All modules should import helpers from here
instead of duplicating AA_DRIVE_ROOT lookup logic.
"""

from __future__ import annotations

import os
import platform
import re
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

# Load .env early to ensure AA_DRIVE_ROOT is available at import time.
_env_file = Path(__file__).resolve().parents[2] / ".env"
if _env_file.exists():
    load_dotenv(_env_file)


class DriveRootNotSetError(RuntimeError):
    """Raised when AA_DRIVE_ROOT is not set and no fallback is allowed."""

    def __init__(self, context: str = ""):
        msg = "AA_DRIVE_ROOT environment variable is not set."
        if context:
            msg = f"{msg} Context: {context}"
        super().__init__(msg)


def get_project_root() -> Path:
    """Return the Arcade Assistant repo root."""
    return Path(__file__).resolve().parents[2]


def _is_windows_absolute(raw: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", raw))


def _running_in_wsl() -> bool:
    return platform.system() == "Linux" and "microsoft" in platform.release().lower()


def _windows_to_wsl(raw: str) -> str:
    drive_letter = raw[0].lower()
    rest = raw[2:].replace("\\", "/").lstrip("/")
    return f"/mnt/{drive_letter}/{rest}".rstrip("/") if rest else f"/mnt/{drive_letter}"


def _wsl_to_windows(raw: str) -> str:
    drive_letter = raw[5].upper()
    rest = raw[6:].replace("/", "\\").lstrip("\\")
    return f"{drive_letter}:\\{rest}".rstrip("\\") if rest else f"{drive_letter}:\\"


def _translate_runtime_path(raw: str) -> str:
    value = raw.strip()
    if not value:
        return value

    if os.name == "nt" and value.lower().startswith("/mnt/") and len(value) >= 7:
        return _wsl_to_windows(value)

    if _running_in_wsl() and _is_windows_absolute(value):
        return _windows_to_wsl(value)

    return value


def _normalize_root_string(raw: str) -> str:
    value = raw.strip()
    if not value:
        return value

    if _is_windows_absolute(value):
        normalized = value.replace("/", "\\")
        prefix = f"{normalized[0].upper()}:"
        rest = normalized[2:].lstrip("\\/")
        return f"{prefix}\\{rest}".rstrip("\\") if rest else f"{prefix}\\"

    if re.match(r"^[A-Za-z]:$", value):
        return f"{value[0].upper()}:\\"

    if value.lower().startswith("/mnt/"):
        normalized = value.replace("\\", "/").rstrip("/")
        return normalized or value

    return value.rstrip("\\/")


def resolve_drive_root_input(raw: Optional[str], *, allow_project_root_fallback: bool = False) -> Optional[Path]:
    """Resolve a configured root string into a runtime Path."""
    value = (raw or "").strip()
    if not value:
        return get_project_root() if allow_project_root_fallback else None

    translated = _translate_runtime_path(value)
    if _is_windows_absolute(translated) or Path(translated).is_absolute():
        return Path(_normalize_root_string(translated))

    return (get_project_root() / translated).resolve()


def normalize_path_key(raw: Optional[str | Path]) -> str:
    """Create a comparable path key across Windows and WSL spellings."""
    if raw is None:
        return ""

    value = str(raw).strip()
    if not value:
        return ""

    translated = _translate_runtime_path(value)
    if translated.lower().startswith("/mnt/"):
        translated = _wsl_to_windows(translated)

    if _is_windows_absolute(translated) or re.match(r"^[A-Za-z]:$", translated):
        return _normalize_root_string(translated).replace("/", "\\").rstrip("\\").lower()

    resolved = resolve_drive_root_input(translated)
    if resolved is not None:
        return str(resolved).replace("\\", "/").rstrip("/").lower()

    return translated.replace("\\", "/").rstrip("/").lower()


def paths_equivalent(left: Optional[str | Path], right: Optional[str | Path]) -> bool:
    """Return True when two path strings refer to the same configured root."""
    left_key = normalize_path_key(left)
    right_key = normalize_path_key(right)
    return bool(left_key and right_key and left_key == right_key)


def get_drive_root(allow_cwd_fallback: bool = False, context: str = "") -> Path:
    """
    Get the configured cabinet root path from AA_DRIVE_ROOT.

    Args:
        allow_cwd_fallback: Legacy compatibility flag. When True and
            AA_DRIVE_ROOT is unset, use the repo root as an explicit
            development fallback.
        context: Optional context string for error messages.
    """
    resolved = resolve_drive_root_input(
        os.environ.get("AA_DRIVE_ROOT", ""),
        allow_project_root_fallback=allow_cwd_fallback,
    )
    if resolved is not None:
        return resolved

    raise DriveRootNotSetError(context)


def get_drive_root_or_none() -> Optional[Path]:
    """Get drive root if set, otherwise return None."""
    return resolve_drive_root_input(os.environ.get("AA_DRIVE_ROOT", ""))


def require_drive_root(context: str = "") -> Path:
    """Get drive root, raising an error if not set."""
    return get_drive_root(allow_cwd_fallback=False, context=context)


def get_aa_root(drive_root: Optional[Path] = None) -> Path:
    """Get the .aa directory path under the configured root."""
    if drive_root is None:
        drive_root = get_drive_root(allow_cwd_fallback=True)
    return drive_root / ".aa"


def get_aa_state(drive_root: Optional[Path] = None) -> Path:
    """Get .aa/state directory path. Creates if missing."""
    p = get_aa_root(drive_root) / "state"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_aa_logs(drive_root: Optional[Path] = None) -> Path:
    """Get .aa/logs directory path. Creates if missing."""
    p = get_aa_root(drive_root) / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_aa_backups(drive_root: Optional[Path] = None) -> Path:
    """Get .aa/backups directory path. Creates if missing."""
    p = get_aa_root(drive_root) / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_changes_log_path(drive_root: Optional[Path] = None) -> Path:
    """Get the canonical audit log path: .aa/logs/changes.jsonl."""
    return get_aa_logs(drive_root) / "changes.jsonl"


def get_manifest_path(drive_root: Optional[Path] = None) -> Path:
    """Get the cabinet manifest path under the configured root."""
    if drive_root is None:
        drive_root = get_drive_root()
    return Path(drive_root) / ".aa" / "manifest.json"


def resolve_optional_path(raw: Optional[str], *, base: Optional[Path] = None) -> Optional[Path]:
    """Resolve an optional path string relative to a base path when needed."""
    value = (raw or "").strip()
    if not value:
        return None

    translated = _translate_runtime_path(value)
    if _is_windows_absolute(translated) or Path(translated).is_absolute():
        return Path(_normalize_root_string(translated))

    if base is None:
        base = get_project_root()

    return (Path(base) / translated).resolve()


def get_launchbox_root(drive_root: Optional[Path] = None) -> Path:
    """Resolve the LaunchBox root from LAUNCHBOX_ROOT or the configured root."""
    if drive_root is None:
        drive_root = get_drive_root()

    override = resolve_optional_path(os.environ.get("LAUNCHBOX_ROOT"), base=drive_root)
    return override or (Path(drive_root) / "LaunchBox")


def get_emulators_root(drive_root: Optional[Path] = None) -> Path:
    if drive_root is None:
        drive_root = get_drive_root()
    return Path(drive_root) / "Emulators"


def get_gun_emulators_root(drive_root: Optional[Path] = None) -> Path:
    if drive_root is None:
        drive_root = get_drive_root()
    return Path(drive_root) / "Gun Build" / "Emulators"


def get_roms_root(drive_root: Optional[Path] = None) -> Path:
    if drive_root is None:
        drive_root = get_drive_root()
    return Path(drive_root) / "Roms"


def get_console_roms_root(drive_root: Optional[Path] = None) -> Path:
    if drive_root is None:
        drive_root = get_drive_root()
    return Path(drive_root) / "Console ROMs"


def get_bios_root(drive_root: Optional[Path] = None) -> Path:
    if drive_root is None:
        drive_root = get_drive_root()
    return Path(drive_root) / "Bios"


def get_tools_root(drive_root: Optional[Path] = None) -> Path:
    if drive_root is None:
        drive_root = get_drive_root()
    return Path(drive_root) / "Tools"


def get_ledblinky_root(drive_root: Optional[Path] = None) -> Path:
    if drive_root is None:
        drive_root = get_drive_root()
    return Path(drive_root) / "LEDBlinky"


def get_runtime_roots(drive_root: Optional[Path] = None) -> Dict[str, Path]:
    """Return the canonical runtime roots derived from AA_DRIVE_ROOT."""
    if drive_root is None:
        drive_root = get_drive_root(allow_cwd_fallback=True)

    root = Path(drive_root)
    return {
        "drive_root": root,
        "launchbox": get_launchbox_root(root),
        "emulators": get_emulators_root(root),
        "gun_emulators": get_gun_emulators_root(root),
        "roms": get_roms_root(root),
        "bios": get_bios_root(root),
        "tools": get_tools_root(root),
    }


def resolve_runtime_path(
    raw: Optional[str | Path],
    *,
    drive_root: Optional[Path] = None,
    base: Optional[Path] = None,
) -> Optional[Path]:
    """Resolve runtime paths against the configured root contract.

    Supports placeholder expansion and a narrow legacy compatibility remap for
    stale `A:\\...` paths that previously assumed the cabinet lived on the A:
    drive. All other absolute paths are preserved as configured.
    """
    if raw is None:
        return None

    value = str(raw).strip()
    if not value:
        return None

    roots = get_runtime_roots(drive_root)
    value = value.replace("${AA_DRIVE_ROOT}", str(roots["drive_root"]))
    value = value.replace("${LAUNCHBOX_ROOT}", str(roots["launchbox"]))

    windows_value = value.replace("/", "\\")
    windows_lower = windows_value.lower()
    if windows_lower == "a:\\":
        return roots["drive_root"]
    if windows_lower == "a:\\launchbox":
        return roots["launchbox"]
    if windows_lower.startswith("a:\\launchbox\\"):
        suffix = windows_value[len("A:\\LaunchBox\\"):].replace("\\", "/")
        return (roots["launchbox"] / suffix).resolve()
    if windows_lower.startswith("a:\\"):
        suffix = windows_value[len("A:\\"):].replace("\\", "/")
        return (roots["drive_root"] / suffix).resolve()

    translated = _translate_runtime_path(value)
    if _is_windows_absolute(translated) or Path(translated).is_absolute():
        return Path(_normalize_root_string(translated))

    anchor = Path(base) if base is not None else roots["drive_root"]
    return (anchor / translated).resolve()


def relativize_runtime_path(path: Path, drive_root: Optional[Path] = None) -> Path:
    """Return a stable relative path label under the configured runtime roots."""
    target = resolve_runtime_path(path, drive_root=drive_root) or Path(path)
    roots = get_runtime_roots(drive_root)
    aliases = [
        (None, roots["drive_root"]),
        (Path("LaunchBox"), roots["launchbox"]),
        (Path("Emulators"), roots["emulators"]),
        (Path("Gun Build") / "Emulators", roots["gun_emulators"]),
        (Path("Roms"), roots["roms"]),
        (Path("Bios"), roots["bios"]),
        (Path("Tools"), roots["tools"]),
    ]

    for prefix, root in aliases:
        try:
            relative = target.relative_to(root)
            if prefix is None:
                return relative
            return prefix / relative
        except ValueError:
            continue

    if target.name:
        return Path(target.parent.name) / target.name
    return Path(target.name)
