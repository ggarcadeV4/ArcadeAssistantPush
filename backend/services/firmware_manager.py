"""Firmware management scaffolding for PactoTech boards."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .policies import is_allowed_file


@dataclass
class FirmwarePreview:
    """Dry-run preview of a firmware flash operation."""

    firmware_file: str
    current_version: Optional[str] = None
    new_version: Optional[str] = None
    file_size_bytes: Optional[int] = None
    compatibility_check: str = "warning"
    changes: List[str] = field(default_factory=list)
    backup_required: bool = True
    backup_suggested_path: Optional[str] = None
    backup_created: bool = False
    backup_path: Optional[str] = None
    board_model: Optional[str] = None
    microcontroller: Optional[str] = None


@dataclass
class FlashReport:
    """Result of attempting to flash firmware onto a board."""

    firmware_flashing_supported: bool = False
    flash_successful: bool = False
    firmware_version_before: Optional[str] = None
    firmware_version_after: Optional[str] = None
    verification_passed: bool = False
    post_flash_sanity_check: str = "skipped"
    backup_path: Optional[str] = None
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)


class FirmwareManager:
    """High-level firmware operations for Controller Chuck workflows."""

    def __init__(self, device_id: str, drive_root: Path, manifest: Dict[str, Any]):
        """Initialize firmware manager for a given device_id."""
        self.device_id = device_id
        self.drive_root = drive_root
        self.manifest = manifest or {}

    def preview_firmware(self, firmware_file: str) -> FirmwarePreview:
        """Run read-only preflight checks without flashing.

        Validates sanctioned paths, gathers file metadata, infers versions, and
        suggests a backup location so callers can review results before issuing
        any mutating operation.
        """
        path, error = self._safe_resolve_path(firmware_file)
        rel_path = self._relative_path(path) if path else firmware_file
        changes: List[str] = []

        if error:
            changes.append(error)
            return FirmwarePreview(
                firmware_file=rel_path,
                compatibility_check="failed",
                changes=changes,
                backup_required=False,
                backup_suggested_path=None,
                backup_created=False,
                backup_path=None,
            )

        if not path.exists():
            changes.append(f"Firmware file not found at {path}.")
            return FirmwarePreview(
                firmware_file=rel_path,
                file_size_bytes=None,
                compatibility_check="failed",
                changes=changes,
                backup_required=False,
                backup_suggested_path=None,
            )

        file_stats = path.stat()
        changes.append(f"Detected firmware file of size {file_stats.st_size} bytes.")

        new_version = self._infer_version_from_name(path.name)
        if new_version:
            changes.append(f"Detected candidate firmware version {new_version}.")
        else:
            changes.append("Could not infer firmware version from filename.")

        current_version = self.get_current_version()
        if not current_version:
            changes.append("Current firmware version unknown (hardware query not implemented yet).")

        compatibility = self._infer_compatibility(path, path_exists=True, version=new_version)
        backup_hint = self._plan_backup_stub(path)

        return FirmwarePreview(
            firmware_file=rel_path,
            current_version=current_version,
            new_version=new_version,
            file_size_bytes=file_stats.st_size,
            compatibility_check=compatibility,
            changes=changes,
            backup_required=True,
            backup_suggested_path=backup_hint,
            backup_created=False,
            backup_path=None,
        )

    def apply_firmware(self, firmware_file: str, confirm: bool = False) -> FlashReport:
        """Confirmation-gated stub that writes backup metadata only.

        When confirm=True and preview checks pass, a JSON metadata backup is
        written under the sanctioned backups tree; no HID/ST-Link flashing
        occurs yet.
        """
        if not confirm:
            return FlashReport(
                message="Firmware apply requires explicit confirmation; no action taken.",
                firmware_version_before=self.get_current_version(),
                firmware_version_after=None,
                post_flash_sanity_check="skipped",
            )

        preview = self.preview_firmware(firmware_file)
        if preview.compatibility_check == "failed":
            return FlashReport(
                message="Firmware preview failed; not applying.",
                firmware_version_before=preview.current_version,
                firmware_version_after=None,
                post_flash_sanity_check="skipped",
            )

        backup_path = self._write_backup_metadata(preview)
        return FlashReport(
            firmware_version_before=preview.current_version,
            firmware_version_after=None,
            post_flash_sanity_check="skipped",
            message="Firmware apply stub completed: backup metadata written; flashing not implemented.",
            backup_path=backup_path,
        )

    def get_current_version(self) -> Optional[str]:
        """Read-only placeholder for future BoardSanityScanner integration."""
        return None

    def validate_firmware_file(self, firmware_file: str) -> bool:
        """Verify firmware file exists and resides in sanctioned paths."""
        exists = self._safe_resolve_path(firmware_file)[0]
        return bool(exists and exists.exists())

    def _safe_resolve_path(self, firmware_file: str) -> Tuple[Optional[Path], Optional[str]]:
        path = Path(firmware_file)
        if not path.is_absolute():
            path = self.drive_root / path
        path = path.resolve()
        sanctioned = self.manifest.get("sanctioned_paths", [])
        if not is_allowed_file(path, self.drive_root, sanctioned):
            return None, "Firmware file is not in a sanctioned location; cannot proceed."
        return path, None

    def _relative_path(self, path: Optional[Path]) -> str:
        if not path:
            return ""
        try:
            return str(path.relative_to(self.drive_root))
        except ValueError:
            return str(path)

    def _infer_version_from_name(self, filename: str) -> Optional[str]:
        pattern = re.compile(r"(?:v|version|fw)[-_]?(\d+(?:[._]\d+)*)", re.I)
        match = pattern.search(filename)
        if match:
            return match.group(1).replace("_", ".")
        digits = re.search(r"(\d{4}(?:\d{2})?)", filename)
        return digits.group(1) if digits else None

    def _infer_compatibility(self, path: Path, path_exists: bool, version: Optional[str]) -> str:
        if not path_exists:
            return "failed"
        name = path.name.lower()
        if "pacto" in name or "stm32" in name or version:
            return "passed"
        return "warning"

    def _plan_backup_stub(self, firmware_path: Path) -> str:
        timestamp = datetime.utcnow()
        date_dir = self.drive_root / ".aa" / "backups" / "firmware" / timestamp.strftime("%Y%m%d")
        filename = f"{timestamp.strftime('%H%M%S')}_firmware_{firmware_path.name}"
        return str((date_dir / filename).relative_to(self.drive_root))

    def _write_backup_metadata(self, preview: FirmwarePreview) -> str:
        timestamp = datetime.utcnow()
        date_dir = self.drive_root / ".aa" / "backups" / "firmware" / timestamp.strftime("%Y%m%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{timestamp.strftime('%H%M%S')}_{self.device_id or 'controller'}_firmware.json"
        target_path = date_dir / filename
        metadata = {
            "device_id": self.device_id,
            "timestamp": timestamp.isoformat(),
            "firmware_file": preview.firmware_file,
            "current_version": preview.current_version,
            "new_version": preview.new_version,
            "changes": preview.changes,
        }
        with open(target_path, "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2)
        return str(target_path.relative_to(self.drive_root))
