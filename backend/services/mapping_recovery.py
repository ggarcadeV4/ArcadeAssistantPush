"""Mapping recovery scaffolding for Controller Chuck."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .backup import create_backup
from .policies import is_allowed_file


@dataclass
class MappingSession:
    """Metadata for a pin-listening session."""

    started_at: datetime
    duration_ms: int
    samples_collected: int


@dataclass
class DetectedPin:
    """Single pin observation from a mapping recovery session."""

    logical_key: Optional[str]
    pin: Optional[int]
    physical_code: Optional[str]
    sample_count: int
    control_type: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class MappingComparison:
    """Differences between expected and detected mappings."""

    mismatches: List[Dict[str, Any]] = field(default_factory=list)
    unmapped_logical: List[str] = field(default_factory=list)
    unmapped_physical: List[str] = field(default_factory=list)


@dataclass
class MappingRecoveryResult:
    """Bundled result returned to Controller Chuck."""

    session: MappingSession
    detected_pins: List[DetectedPin]
    comparison: MappingComparison
    proposed_mapping: Dict[str, Any]
    summary: str


@dataclass
class MappingApplyReport:
    """Outcome metadata for applying a mapping dictionary."""

    success: bool
    dry_run: bool
    device_id: str
    backup_path: Optional[str]
    actions_taken: List[str]
    warnings: List[str]
    errors: List[str]
    changes_count: int
    summary: str


class MappingRecoveryService:
    """High-level helpers for recovering and applying controller mappings."""

    MAPPING_RELATIVE = Path("config/mappings/controls.json")
    EVENTS_RELATIVE = Path("state/controller/teach_events.jsonl")

    def __init__(
        self,
        device_id: str,
        drive_root: Optional[Path] = None,
        manifest: Optional[Dict[str, Any]] = None,
    ):
        """Initialize mapping recovery for a given device_id."""
        self.device_id = device_id
        self.drive_root = drive_root
        self.manifest = manifest or {}

    def start_listening_session(self, duration_ms: int = 30000) -> MappingSession:
        """Stub: start a logical 'listening' session; no real HID capture yet."""
        return MappingSession(
            started_at=datetime.utcnow(),
            duration_ms=duration_ms,
            samples_collected=0,
        )

    def detect_active_pins(self) -> List[DetectedPin]:
        """Aggregate teach events into detected pin summaries."""
        events = self._load_teach_events()
        aggregated: Dict[str, DetectedPin] = {}
        for entry in events:
            logical_key = entry.get("control_key")
            if not logical_key:
                continue
            try:
                pin_value = int(entry.get("pin")) if entry.get("pin") is not None else None
            except (TypeError, ValueError):
                pin_value = None
            detected = aggregated.get(logical_key)
            if detected is None:
                detected = DetectedPin(
                    logical_key=logical_key,
                    pin=pin_value,
                    physical_code=entry.get("keycode"),
                    sample_count=0,
                    control_type=entry.get("control_type"),
                )
                aggregated[logical_key] = detected
            detected.sample_count += 1
            # Always keep the latest reading for pin/code to reflect current state.
            if pin_value is not None:
                detected.pin = pin_value
            if entry.get("keycode"):
                detected.physical_code = entry.get("keycode")
            if entry.get("control_type"):
                detected.control_type = entry.get("control_type")
        return list(aggregated.values())

    def compare_to_dictionary(self, detected: List[DetectedPin]) -> MappingComparison:
        """Compare detected pins to controls.json."""
        comparison = MappingComparison()
        mapping_path = self._mapping_path()
        current_data, _, _ = self._load_current_mapping(mapping_path)
        existing = current_data.get("mappings", {})
        detected_map = {
            pin.logical_key: pin for pin in detected if pin.logical_key
        }

        for control_key, entry in existing.items():
            if control_key not in detected_map:
                comparison.unmapped_logical.append(control_key)
                continue
            detected_pin = detected_map[control_key]
            expected = entry.get("pin")
            if expected is not None and detected_pin.pin is not None and expected != detected_pin.pin:
                comparison.mismatches.append(
                    {
                        "control_key": control_key,
                        "expected_pin": expected,
                        "detected_pin": detected_pin.pin,
                    }
                )

        for logical_key, pin in detected_map.items():
            if logical_key not in existing:
                descriptor = f"{logical_key}:{pin.pin}"
                comparison.unmapped_physical.append(descriptor)

        return comparison

    def build_proposed_mapping(self, detected: List[DetectedPin]) -> Dict[str, Any]:
        """Build a mapping patch using detected pins."""
        proposal: Dict[str, Any] = {"mappings": {}}
        for pin in detected:
            if not pin.logical_key or pin.pin is None:
                continue
            proposal["mappings"][pin.logical_key] = {
                "pin": pin.pin,
                "type": pin.control_type or "button",
            }
        return proposal

    def preview_recovery(self, duration_ms: int = 30000) -> MappingRecoveryResult:
        """Run a teach preview using captured input events."""
        detected_pins = self.detect_active_pins()
        total_samples = sum(pin.sample_count for pin in detected_pins)
        session = MappingSession(
            started_at=datetime.utcnow(),
            duration_ms=duration_ms,
            samples_collected=total_samples,
        )
        comparison = self.compare_to_dictionary(detected_pins)
        proposed_mapping = self.build_proposed_mapping(detected_pins)

        if not detected_pins:
            summary = "No teach events recorded yet. Capture inputs to generate a mapping proposal."
        else:
            summary = (
                f"Captured {len(detected_pins)} unique controls "
                f"with {total_samples} total samples; "
                f"{len(comparison.mismatches)} mismatches vs controls.json."
            )
        return MappingRecoveryResult(
            session=session,
            detected_pins=detected_pins,
            comparison=comparison,
            proposed_mapping=proposed_mapping,
            summary=summary,
        )

    def apply_mapping(
        self, new_mapping: Dict[str, Any], dry_run: bool = True
    ) -> Tuple[MappingApplyReport, Dict[str, Any]]:
        """Preview + optionally write a new controls.json mapping.

        The pipeline enforces sanctioned-path checks, produces a preview/changed
        keys list, creates backups via backup.create_backup, and applies changes
        only when dry_run=False.
        """
        actions: List[str] = []
        warnings: List[str] = []
        errors: List[str] = []

        target_path = self._mapping_path()
        actions.append(f"Resolved mapping path to {target_path}")

        if not self._is_sanctioned(target_path):
            message = "Target mapping file is not in sanctioned paths; refusing to write."
            errors.append(message)
            report = MappingApplyReport(
                success=False,
                dry_run=dry_run,
                device_id=self.device_id,
                backup_path=None,
                actions_taken=actions,
                warnings=warnings,
                errors=errors,
                changes_count=0,
                summary="Cannot apply mapping; target path is not approved in the manifest.",
            )
            preview = self._build_preview_data(target_path, [], 0)
            return report, preview

        current_data, load_error, file_exists = self._load_current_mapping(target_path)
        if not file_exists:
            actions.append("Existing mapping file not found; would create new mapping file.")

        if load_error:
            errors.append(load_error)
            report = MappingApplyReport(
                success=False,
                dry_run=dry_run,
                device_id=self.device_id,
                backup_path=None,
                actions_taken=actions,
                warnings=warnings,
                errors=errors,
                changes_count=0,
                summary="Failed to read current mapping; cannot apply changes.",
            )
            preview = self._build_preview_data(target_path, [], 0)
            return report, preview

        changed_keys = self._compute_changed_keys(
            current_data.get("mappings", current_data),
            new_mapping.get("mappings", new_mapping),
        )
        changes_count = len(changed_keys)
        preview = self._build_preview_data(target_path, changed_keys, changes_count)

        if changes_count == 0:
            actions.append("No differences detected between existing and supplied mappings.")
            report = MappingApplyReport(
                success=True,
                dry_run=dry_run,
                device_id=self.device_id,
                backup_path=None,
                actions_taken=actions,
                warnings=warnings,
                errors=errors,
                changes_count=0,
                summary="No changes required; mapping already matches.",
            )
            return report, preview

        backup_rel: Optional[str] = None

        if dry_run:
            actions.append("Dry run: no changes written.")
            summary = (
                f"Would update mapping with {changes_count} changes for device {self.device_id}; "
                "no files were written (dry run)."
            )
            report = MappingApplyReport(
                success=True,
                dry_run=True,
                device_id=self.device_id,
                backup_path=None,
                actions_taken=actions,
                warnings=warnings,
                errors=errors,
                changes_count=changes_count,
                summary=summary,
            )
            return report, preview

        if target_path.exists():
            try:
                backup = create_backup(target_path, self.drive_root)
            except Exception as exc:
                errors.append(f"Failed to create backup; aborting apply ({exc}).")
                return (
                    MappingApplyReport(
                        success=False,
                        dry_run=False,
                        device_id=self.device_id,
                        backup_path=None,
                        actions_taken=actions,
                        warnings=warnings,
                        errors=errors,
                        changes_count=0,
                        summary="Mapping apply failed during backup step.",
                    ),
                    preview,
                )
            backup_rel = self._relative_path(backup)
            actions.append(f"Created backup at {backup_rel}.")
        else:
            warnings.append("Existing mapping file not found; creating new file.")

        self._write_mapping(target_path, new_mapping)
        actions.append(f"Wrote updated mapping to {target_path}.")

        verify_data, verify_error, _ = self._load_current_mapping(target_path)
        if verify_error or self._compute_changed_keys(
            verify_data.get("mappings", verify_data),
            new_mapping.get("mappings", new_mapping),
        ):
            errors.append("Post-write verification failed; file may not match supplied mapping.")
            return (
                MappingApplyReport(
                    success=False,
                    dry_run=False,
                    device_id=self.device_id,
                    backup_path=backup_rel,
                    actions_taken=actions,
                    warnings=warnings,
                    errors=errors,
                    changes_count=changes_count,
                    summary="Mapping apply encountered errors during verification.",
                ),
                preview,
            )

        summary = (
            f"Applied mapping for device {self.device_id}; {changes_count} entries updated. "
            f"Backup saved at {backup_rel or 'N/A'}."
        )
        report = MappingApplyReport(
            success=True,
            dry_run=False,
            device_id=self.device_id,
            backup_path=backup_rel,
            actions_taken=actions,
            warnings=warnings,
            errors=errors,
            changes_count=changes_count,
            summary=summary,
        )
        return report, preview

    def _mapping_path(self) -> Path:
        if not self.drive_root:
            raise RuntimeError("drive_root is not configured for MappingRecoveryService")
        return (self.drive_root / self.MAPPING_RELATIVE).resolve()

    def _events_path(self) -> Path:
        if not self.drive_root:
            raise RuntimeError("drive_root is not configured for MappingRecoveryService")
        return (self.drive_root / self.EVENTS_RELATIVE).resolve()

    def _is_sanctioned(self, path: Path) -> bool:
        sanctioned = self.manifest.get("sanctioned_paths", [])
        return is_allowed_file(path, self.drive_root, sanctioned)

    def _load_current_mapping(self, path: Path) -> Tuple[Dict[str, Any], Optional[str], bool]:
        if not path.exists():
            return {}, None, False
        try:
            text = path.read_text(encoding="utf-8")
            return (json.loads(text) if text else {}), None, True
        except (OSError, json.JSONDecodeError) as exc:
            return {}, f"Failed to read current mapping file: {exc}", True

    def _compute_changed_keys(
        self, current: Dict[str, Any], new: Dict[str, Any]
    ) -> List[str]:
        keys = set(current.keys()) | set(new.keys())
        return [key for key in sorted(keys) if current.get(key) != new.get(key)]

    def _build_preview_data(
        self, target_path: Path, changed_keys: List[str], changes_count: int
    ) -> Dict[str, Any]:
        return {
            "target_file": self._relative_path(target_path),
            "changed_keys": changed_keys,
            "changes_count": changes_count,
        }

    def _write_mapping(self, target_path: Path, new_mapping: Dict[str, Any]) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(new_mapping, indent=2, sort_keys=True)
        target_path.write_text(serialized + "\n", encoding="utf-8")

    def _relative_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.drive_root))
        except Exception:
            return str(path)

    def _load_teach_events(self, limit: int = 200) -> List[Dict[str, Any]]:
        path = self._events_path()
        if not path.exists():
            return []
        events: List[Dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8") as handle:
                lines = handle.readlines()
        except OSError:
            return events

        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    # rest????
