"""Persistent classification store for detected devices."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from .audit_log import append as append_audit_log
from .policies import is_allowed_file

logger = logging.getLogger(__name__)

_LOCK = Lock()
_RELATIVE_PATH = Path("state") / "controller" / "known_devices.json"


def _resolve_path(drive_root: Path, sanctioned_paths: Optional[List[str]]) -> Path:
    path = (drive_root / _RELATIVE_PATH).resolve()
    if sanctioned_paths is not None and not is_allowed_file(path, drive_root, sanctioned_paths):
        raise PermissionError(f"{path} is not within sanctioned paths")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_raw(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data or []
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse %s: %s", path, exc)
        return []


def _write_raw(path: Path, payload: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def list_classifications(
    drive_root: Path,
    sanctioned_paths: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Return persisted classifications scoped to the provided drive root."""
    path = _resolve_path(drive_root, sanctioned_paths)
    with _LOCK:
        return _load_raw(path)


def upsert_classification(
    *,
    drive_root: Path,
    device_id: str,
    role: str,
    label: str,
    panels: Optional[List[str]] = None,
    sanctioned_paths: Optional[List[str]] = None,
    audit_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist a classification entry and append an audit log entry."""
    path = _resolve_path(drive_root, sanctioned_paths)
    entry = {
        "device_id": device_id,
        "role": role,
        "label": label,
        "panels": panels or [],
        "last_seen": datetime.utcnow().isoformat(),
    }
    with _LOCK:
        data = _load_raw(path)
        remaining = [item for item in data if item.get("device_id") != device_id]
        remaining.append(entry)
        _write_raw(path, remaining)

    payload = {
        "scope": "devices",
        "action": "classification_upsert",
        "device_id": device_id,
        "role": role,
        "label": label,
        "panels": panels or [],
    }
    if audit_metadata:
        payload.update(audit_metadata)
    try:
        append_audit_log(payload)
    except Exception:  # pragma: no cover - audit logging best effort
        logger.debug("Failed to append audit log for device classification.", exc_info=True)
    return entry


def find_classification(
    device_id: str,
    *,
    drive_root: Path,
    sanctioned_paths: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Lookup a classification entry for a device."""
    for item in list_classifications(drive_root, sanctioned_paths):
        if item.get("device_id") == device_id:
            return item
    return None


def remove_classification(
    device_id: str,
    *,
    drive_root: Path,
    sanctioned_paths: Optional[List[str]] = None,
    audit_metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """Remove a classification entry for a device.
    
    Returns True if the device was found and removed, False if not found.
    """
    path = _resolve_path(drive_root, sanctioned_paths)
    with _LOCK:
        data = _load_raw(path)
        remaining = [item for item in data if item.get("device_id") != device_id]
        if len(remaining) == len(data):
            # Device not found
            return False
        _write_raw(path, remaining)

    payload = {
        "scope": "devices",
        "action": "classification_remove",
        "device_id": device_id,
    }
    if audit_metadata:
        payload.update(audit_metadata)
    try:
        append_audit_log(payload)
    except Exception:  # pragma: no cover
        logger.debug("Failed to append audit log for device unclassification.", exc_info=True)
    return True


__all__ = ["list_classifications", "upsert_classification", "find_classification", "remove_classification"]

