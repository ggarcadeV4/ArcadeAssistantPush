from __future__ import annotations

import os
import tempfile
from pathlib import Path
from datetime import datetime
import uuid

from backend.constants.drive_root import get_drive_root


def _drive_root() -> Path:
    """Resolve AA_DRIVE_ROOT to a Path with safe fallback.

    Uses central drive_root helper. Falls back to cwd for dev.
    No hardcoded drive letters.
    """
    try:
        return get_drive_root(allow_cwd_fallback=True)
    except Exception:
        return Path(tempfile.gettempdir()) / "arcade-assistant"


def get_runtime_root() -> Path:
    """Return the runtime working root under the .aa/state folder.

    Example: <AA_DRIVE_ROOT>/.aa/state/runtime
    Fallback: <tmp>/arcade-assistant/runtime
    """
    base = _drive_root()
    # Use .aa/state/runtime (Golden Drive compliant)
    target = base / ".aa" / "state" / "runtime"
    try:
        target.mkdir(parents=True, exist_ok=True)
        return target
    except Exception:
        pass
    # Last resort
    fallback = Path(tempfile.gettempdir()) / "arcade-assistant" / "runtime"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def get_extracts_root(namespace: str = "pcsx2") -> Path:
    """Return (and create) the extraction root directory for a namespace."""
    root = get_runtime_root() / "extracts" / namespace
    root.mkdir(parents=True, exist_ok=True)
    return root


def make_unique_run_dir(namespace: str = "pcsx2") -> Path:
    """Create a unique subdirectory for a single launch run.

    Directory name format: YYYYMMDD_HHMMSS-<uuid4>
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    d = get_extracts_root(namespace) / f"{ts}-{uid}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def aa_tmp_dir() -> Path:
    """
    Resolve Arcade Assistant temp dir for large extracts.
    Priority:
      1) env AA_TMP_DIR (absolute path)
      2) <AA_DRIVE_ROOT>/ArcadeAssistant/_tmp
      3) system temp dir (as last resort)
    Ensures directory exists.
    """
    env_dir = os.getenv("AA_TMP_DIR")
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    try:
        drive = get_drive_root(allow_cwd_fallback=False)
        p = drive / "ArcadeAssistant" / "_tmp"
        p.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        pass

    # fallback: system temp
    base = Path(os.getenv("TEMP") or os.getenv("TMP") or tempfile.gettempdir())
    p = base / "aa"
    p.mkdir(parents=True, exist_ok=True)
    return p


def aa_overrides_dir() -> Path:
    """
    Overrides are written only under sanctioned paths.
    Priority:
      1) AA_OVERRIDES_DIR env (absolute)
      2) <AA_DRIVE_ROOT>/configs/overrides
      3) <cwd>/configs/overrides
    """
    env_dir = os.getenv("AA_OVERRIDES_DIR")
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p
    
    try:
        drive = get_drive_root(allow_cwd_fallback=False)
        p = drive / "configs" / "overrides"
        p.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        pass
    
    p = Path("configs") / "overrides"
    p.mkdir(parents=True, exist_ok=True)
    return p


def ps2_overrides_path() -> Path:
    return aa_overrides_dir() / "ps2-paths.json"

