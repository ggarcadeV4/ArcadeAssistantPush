"""
Drive Root Helper (Golden Drive Contract)

Single source of truth for drive root path resolution.
All modules should import get_drive_root() from here instead of
duplicating AA_DRIVE_ROOT lookup logic.

Golden Drive Rules:
1. No hardcoded drive letters (A:, C:, etc.)
2. AA_DRIVE_ROOT environment variable is required
3. If not set, return a clear error - no silent fallbacks
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env early to ensure AA_DRIVE_ROOT is available at import time
# This must happen before any module reads os.environ.get('AA_DRIVE_ROOT')
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


def get_drive_root(allow_cwd_fallback: bool = False, context: str = "") -> Path:
    """
    Get the drive root path from AA_DRIVE_ROOT environment variable.
    
    Args:
        allow_cwd_fallback: If True, fall back to current working directory
                           when AA_DRIVE_ROOT is not set. Only use this for
                           development/testing scenarios.
        context: Optional context string for error messages.
    
    Returns:
        Path to the drive root.
    
    Raises:
        DriveRootNotSetError: If AA_DRIVE_ROOT is not set and fallback not allowed.
    
    Examples:
        >>> from backend.constants.drive_root import get_drive_root
        >>> drive = get_drive_root()
        >>> launchbox = drive / "LaunchBox"
    """
    raw = os.environ.get("AA_DRIVE_ROOT", "").strip()
    
    if raw:
        if len(raw) >= 2 and raw[1] == ':' and raw[0].isalpha():
            if len(raw) == 2:
                return Path(raw + "\\")
            if len(raw) == 3 and raw[2] in ("\\", "/"):
                return Path(raw[0:2] + "\\")
        # Normalize: strip trailing separators for non-root paths
        return Path(raw.rstrip("\\/"))
    
    if allow_cwd_fallback:
        # Development fallback - use current working directory
        return Path(os.getcwd()).resolve()
    
    raise DriveRootNotSetError(context)


def get_drive_root_or_none() -> Optional[Path]:
    """
    Get drive root if set, otherwise return None.
    
    Use this when you need to check if drive root is configured
    without raising an exception.
    """
    raw = os.environ.get("AA_DRIVE_ROOT", "").strip()
    if raw:
        return Path(raw.rstrip("\\/"))
    return None


def require_drive_root(context: str = "") -> Path:
    """
    Get drive root, raising an error if not set.
    
    Same as get_drive_root(allow_cwd_fallback=False) but with
    a more explicit name.
    """
    return get_drive_root(allow_cwd_fallback=False, context=context)


def get_aa_root(drive_root: Optional[Path] = None) -> Path:
    """
    Get the .aa directory path under drive root.
    
    Args:
        drive_root: Optional explicit drive root. If None, uses get_drive_root().
    
    Returns:
        Path to <drive_root>/.aa
    """
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
    """Get the canonical audit log path: .aa/logs/changes.jsonl"""
    return get_aa_logs(drive_root) / "changes.jsonl"
