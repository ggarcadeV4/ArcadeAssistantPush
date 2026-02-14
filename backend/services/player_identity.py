"""Player identity calibration persistence.

Provides storage and retrieval for player identity bindings that map
source identifiers (board types) to logical player numbers (1-4).
This enables the wizard to learn which physical station is P1/P2/etc
even when encoder wiring is swapped.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from .backup import create_backup
from . import audit_log

logger = logging.getLogger(__name__)

_LOCK = Lock()
_RELATIVE_PATH = Path("state") / "controller" / "player_identity.json"


def _resolve_path(drive_root: Path) -> Path:
    """Get the player identity file path, creating parent dirs as needed."""
    path = (drive_root / _RELATIVE_PATH).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_bindings(drive_root: Path) -> Dict[str, Any]:
    """Load current identity bindings from disk.
    
    Returns:
        Dictionary with 'version', 'bindings', 'calibrated_at', and 'status'.
        Returns empty/unbound state if file doesn't exist.
    """
    path = _resolve_path(drive_root)
    with _LOCK:
        if not path.exists():
            return {
                "version": 1,
                "bindings": {},
                "calibrated_at": None,
                "status": "unbound",
            }
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                data["status"] = "bound" if data.get("bindings") else "unbound"
                return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load player identity from %s: %s", path, exc)
            return {
                "version": 1,
                "bindings": {},
                "calibrated_at": None,
                "status": "unbound",
            }


def save_bindings(
    drive_root: Path,
    bindings: Dict[str, int],
    create_backup_flag: bool = True,
) -> Optional[Path]:
    """Save identity bindings to disk with backup and audit log.
    
    Args:
        drive_root: AA drive root path.
        bindings: Map of source_id -> player number (1-4).
        create_backup_flag: Whether to create a backup of existing file.
    
    Returns:
        Path to backup file if created, else None.
    """
    path = _resolve_path(drive_root)
    backup_path: Optional[Path] = None
    
    with _LOCK:
        # Create backup if file exists
        if create_backup_flag and path.exists():
            try:
                backup_path = create_backup(path, drive_root)
            except Exception as exc:
                logger.warning("Failed to create backup for %s: %s", path, exc)
        
        # Write new bindings
        data = {
            "version": 1,
            "bindings": bindings,
            "calibrated_at": datetime.utcnow().isoformat(),
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    
    # Log to audit log
    try:
        audit_log.append({
            "scope": "controller",
            "action": "identity_apply",
            "bindings": bindings,
            "backup_path": str(backup_path) if backup_path else None,
        })
    except Exception:
        logger.debug("Failed to append audit log for identity apply.", exc_info=True)
    
    logger.info("Saved player identity bindings: %s", bindings)
    return backup_path


def reset_bindings(drive_root: Path) -> Optional[Path]:
    """Clear identity bindings, creating backup and logging the reset.
    
    Returns:
        Path to backup file if created, else None.
    """
    path = _resolve_path(drive_root)
    backup_path: Optional[Path] = None
    
    with _LOCK:
        if path.exists():
            try:
                backup_path = create_backup(path, drive_root)
            except Exception as exc:
                logger.warning("Failed to create backup for reset: %s", exc)
            
            # Remove the file
            try:
                path.unlink()
            except OSError as exc:
                logger.error("Failed to delete identity file: %s", exc)
    
    # Log to audit log
    try:
        audit_log.append({
            "scope": "controller",
            "action": "identity_reset",
            "backup_path": str(backup_path) if backup_path else None,
        })
    except Exception:
        logger.debug("Failed to append audit log for identity reset.", exc_info=True)
    
    logger.info("Reset player identity bindings.")
    return backup_path


def get_bindings_map(drive_root: Path) -> Dict[str, int]:
    """Get just the source_id -> player bindings map for runtime use.
    
    Returns:
        Dictionary mapping source_id strings to player numbers (1-4).
        Empty dict if no bindings exist.
    """
    data = load_bindings(drive_root)
    return data.get("bindings", {})


__all__ = [
    "load_bindings",
    "save_bindings",
    "reset_bindings",
    "get_bindings_map",
]
