import json
import os
from datetime import datetime
from pathlib import Path


def _get_drive_root() -> Path:
    """Get the drive root from AA_DRIVE_ROOT environment variable (required).
    
    Golden Drive Contract: AA_DRIVE_ROOT must be set; no fallback to hardcoded A:\\.
    If not set, returns current working directory as last resort (for dev/testing).
    """
    drive_root = os.getenv("AA_DRIVE_ROOT")
    if not drive_root:
        # No hardcoded A:\ fallback - use cwd for dev environments only
        drive_root = os.getcwd()
    return Path(drive_root)


def _pause_log_path() -> Path:
    """Get pause event log path under .aa/logs/pause/ from drive root.
    
    Golden Drive Contract: All logs go under .aa/logs/ - no fallback to other paths.
    """
    drive_root = _get_drive_root()
    base = drive_root / ".aa" / "logs" / "pause"
    base.mkdir(parents=True, exist_ok=True)
    return base / "events.jsonl"


def append_pause_event(emulator: str, action: str, result: str, message: str = "") -> None:
    """Append a JSONL record for pause-related actions.

    Args:
        emulator: Name like 'retroarch', 'mame', or 'unknown'
        action: 'pause' | 'resume' | 'save' | 'load' | 'quit' | 'status' | 'preflight'
        result: 'ok' | 'error'
        message: Optional diagnostic message
    """
    rec = {
        "ts": datetime.utcnow().isoformat(),
        "emulator": emulator or "unknown",
        "action": action,
        "result": result,
        "msg": message or "",
    }
    path = _pause_log_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        # Do not raise from logging
        pass


def _audit_log_path() -> Path:
    """General audit log path for config/state changes under .aa/logs/audit/.
    
    Golden Drive Contract: All logs go under .aa/logs/ - no fallback to other paths.
    """
    drive_root = _get_drive_root()
    base = drive_root / ".aa" / "logs" / "audit"
    base.mkdir(parents=True, exist_ok=True)
    return base / "changes.jsonl"


def append(entry: dict) -> None:
    """Append a general JSONL record for audit logging.

    Args:
        entry: Dictionary with log data (scope, action, etc.)
    """
    rec = {
        "ts": datetime.utcnow().isoformat(),
        **entry,
    }
    path = _audit_log_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        # Do not raise from logging
        pass


