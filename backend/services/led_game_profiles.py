"""Manage LaunchBox ↔ LED profile bindings."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from .backup import create_backup
from .policies import is_allowed_file


class LEDGameProfileStore:
    """Simple JSON-backed store for LaunchBox game profile bindings."""

    STORE_RELATIVE = Path("configs/ledblinky/game_profiles.json")

    def __init__(self, drive_root: Path, manifest: Optional[Dict[str, Any]] = None) -> None:
        self.drive_root = drive_root
        self.manifest = manifest or {}

    def _store_path(self) -> Path:
        return self.drive_root / self.STORE_RELATIVE

    def _ensure_allowed(self, path: Path) -> None:
        sanctioned = self.manifest.get("sanctioned_paths", [])
        if not sanctioned or not is_allowed_file(path, self.drive_root, sanctioned):
            relative = path.relative_to(self.drive_root)
            raise HTTPException(
                status_code=403,
                detail=f"LED game profile store not sanctioned: {relative}",
            )

    def _read_document(self) -> Dict[str, Any]:
        path = self._store_path()
        if not path.exists():
            return {"version": 1, "bindings": []}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"LED game profile store is invalid JSON: {exc}",
            ) from exc

    def _write_document(self, payload: Dict[str, Any]) -> Optional[str]:
        path = self._store_path()
        self._ensure_allowed(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        backup_path: Optional[str] = None
        if path.exists():
            backup = create_backup(path, self.drive_root)
            backup_path = str(backup.relative_to(self.drive_root)).replace("\\", "/")

        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return backup_path

    def list_bindings(self) -> List[Dict[str, Any]]:
        document = self._read_document()
        bindings = document.get("bindings")
        if not isinstance(bindings, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for entry in bindings:
            if not isinstance(entry, dict):
                continue
            record = {
                "game_id": str(entry.get("game_id") or ""),
                "platform": entry.get("platform"),
                "title": entry.get("title") or "",
                "profile_name": entry.get("profile_name") or "",
                "updated_at": entry.get("updated_at"),
                "updated_by": entry.get("updated_by"),
            }
            normalized.append(record)
        return normalized

    def get_binding(self, game_id: str) -> Optional[Dict[str, Any]]:
        if not game_id:
            return None
        for entry in self.list_bindings():
            if entry.get("game_id") == game_id:
                return entry
        return None

    def set_binding(
        self,
        *,
        game_id: str,
        platform: str,
        title: str,
        profile_name: str,
        updated_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not game_id or not profile_name:
            raise HTTPException(
                status_code=400,
                detail="game_id and profile_name are required for bindings",
            )

        document = self._read_document()
        bindings = document.get("bindings")
        if not isinstance(bindings, list):
            bindings = []

        payload = {
            "game_id": game_id,
            "platform": platform,
            "title": title,
            "profile_name": profile_name,
            "updated_at": datetime.utcnow().isoformat(),
            "updated_by": updated_by or "unknown",
        }

        replaced = False
        for index, entry in enumerate(bindings):
            if isinstance(entry, dict) and entry.get("game_id") == game_id:
                bindings[index] = payload
                replaced = True
                break

        if not replaced:
            bindings.append(payload)

        document["bindings"] = bindings
        document["version"] = document.get("version", 1)
        document["updated_at"] = datetime.utcnow().isoformat()

        backup_path = self._write_document(document)
        result = dict(payload)
        if backup_path:
            result["backup_path"] = backup_path
        return result

    def delete_binding(self, game_id: str) -> Optional[str]:
        document = self._read_document()
        bindings = document.get("bindings")
        if not isinstance(bindings, list):
            raise HTTPException(
                status_code=404,
                detail="No game profile bindings recorded",
            )

        updated = [entry for entry in bindings if entry.get("game_id") != game_id]
        if len(updated) == len(bindings):
            raise HTTPException(
                status_code=404,
                detail=f"No LED profile binding found for {game_id}",
            )

        document["bindings"] = updated
        document["version"] = document.get("version", 1)
        document["updated_at"] = datetime.utcnow().isoformat()
        return self._write_document(document)
