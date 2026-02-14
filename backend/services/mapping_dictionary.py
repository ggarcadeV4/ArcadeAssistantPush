"""Safe preview/apply helpers for controls.json mapping dictionary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException

from .audit_log import append as append_audit_log
from .backup import create_backup
from .diffs import compute_diff, has_changes
from .policies import is_allowed_file


@dataclass
class MappingPreview:
    target_file: str
    has_changes: bool
    diff: str
    current: Dict[str, Any]
    proposed: Dict[str, Any]


class MappingDictionaryService:
    """Preview + apply helper for controls.json."""

    RELATIVE_PATH = Path("config/mappings/controls.json")

    def __init__(self, drive_root: Path, manifest: Dict[str, Any]):
        self.drive_root = drive_root
        self.manifest = manifest or {}
        self.target_path = self.drive_root / self.RELATIVE_PATH
        self._validate_path()

    def _validate_path(self) -> None:
        sanctioned = self.manifest.get("sanctioned_paths", [])
        if not is_allowed_file(self.target_path, self.drive_root, sanctioned):
            raise HTTPException(
                status_code=403,
                detail=f"Mapping file outside sanctioned paths: {self.RELATIVE_PATH}",
            )

    def load_current(self) -> Dict[str, Any]:
        if not self.target_path.exists():
            return {}
        try:
            text = self.target_path.read_text(encoding="utf-8")
            return json.loads(text) if text else {}
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to read mapping dictionary: {exc}",
            ) from exc

    def preview(self, proposed: Dict[str, Any]) -> MappingPreview:
        current = self.load_current()
        current_text = json.dumps(current, indent=2, sort_keys=True)
        proposed_text = json.dumps(proposed, indent=2, sort_keys=True)
        diff = compute_diff(current_text, proposed_text, str(self.RELATIVE_PATH))
        preview = MappingPreview(
            target_file=str(self.RELATIVE_PATH),
            has_changes=has_changes(current_text, proposed_text),
            diff=diff,
            current=current,
            proposed=proposed,
        )
        return preview

    def apply(
        self,
        proposed: Dict[str, Any],
        dry_run: bool = True,
    ) -> Tuple[MappingPreview, Optional[Path]]:
        preview = self.preview(proposed)
        backup_path: Optional[Path] = None

        if not dry_run and preview.has_changes:
            if self.target_path.exists():
                backup_path = create_backup(self.target_path, self.drive_root)
            self.target_path.parent.mkdir(parents=True, exist_ok=True)
            serialized = json.dumps(proposed, indent=2, sort_keys=True)
            self.target_path.write_text(serialized + "\n", encoding="utf-8")
            change_count = self._count_changed_keys(preview.current, preview.proposed)
            try:
                append_audit_log(
                    {
                        "scope": "controller",
                        "action": "mapping_dictionary_write",
                        "target_file": str(self.RELATIVE_PATH),
                        "changes_count": change_count,
                    }
                )
            except Exception:  # pragma: no cover - audit log best effort
                pass

        return preview, backup_path

    @staticmethod
    def _count_changed_keys(current: Dict[str, Any], proposed: Dict[str, Any]) -> int:
        keys = set(current.keys()) | set(proposed.keys())
        return sum(1 for key in keys if current.get(key) != proposed.get(key))
