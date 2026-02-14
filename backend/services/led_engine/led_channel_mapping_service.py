"""Manage logical-to-physical LED channel wiring."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request

from ..backup import create_backup
from ..diffs import compute_diff, has_changes
from ..policies import is_allowed_file


@dataclass
class LEDChannelBinding:
    """Resolved hardware binding for a logical LED button."""

    logical_button: str
    device_id: str
    channel: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "logical_button": self.logical_button,
            "device_id": self.device_id,
            "channel": self.channel,
        }


@dataclass
class LEDChannelMappingPreview:
    """Preview payload returned prior to applying changes."""

    response: Dict[str, Any]
    document: Dict[str, Any]
    document_text: str
    current_text: str
    target_path: Path
    has_changes: bool

    @property
    def target_file(self) -> str:
        return self.response["target_file"]


class LEDChannelMappingService:
    """Preview + apply helper for configs/ledblinky/led_channels.json."""

    RELATIVE_PATH = Path("configs/ledblinky/led_channels.json")

    def __init__(self, drive_root: Path, manifest: Optional[Dict[str, Any]] = None) -> None:
        self.drive_root = Path(drive_root)
        self.manifest = manifest or {}
        self._target_path = self.drive_root / self.RELATIVE_PATH
        self._document_cache: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Public document helpers
    # ------------------------------------------------------------------

    def load_document(self) -> Dict[str, Any]:
        """Return a deep copy of the currently stored mapping document."""
        if self._document_cache is None:
            self._document_cache = self._read_document()
        return json.loads(json.dumps(self._document_cache))

    def load_channels(self) -> Dict[str, Dict[str, Any]]:
        """Return the channels mapping from the stored document."""
        document = self.load_document()
        return dict(document.get("channels", {}))

    def resolve(self, logical_button: str) -> Optional[LEDChannelBinding]:
        """Resolve a logical button to a hardware binding, if configured."""
        normalized = self._normalize_logical_button(logical_button, error_status=500, required=False)
        if not normalized:
            return None
        channels = self.load_channels()
        entry = channels.get(normalized)
        if not isinstance(entry, dict):
            return None
        try:
            device_id = self._normalize_device_id(entry.get("device_id"), error_status=500)
            channel = self._normalize_channel(entry.get("channel"), error_status=500)
        except HTTPException as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Invalid LED channel mapping for {logical_button}: {exc.detail}",
            ) from exc
        return LEDChannelBinding(logical_button=normalized, device_id=device_id, channel=channel)

    def set_mapping(
        self,
        logical_button: str,
        device_id: str,
        channel: int,
        *,
        document: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Apply/update a single mapping inside a working document."""
        working = self._clone_document(document or self.load_document())
        channels = working.setdefault("channels", {})
        normalized_button = self._normalize_logical_button(logical_button)
        channels[normalized_button] = {
            "device_id": self._normalize_device_id(device_id),
            "channel": self._normalize_channel(channel),
        }
        working["channels"] = self._normalize_channels(channels)
        return working

    def remove_mapping(
        self,
        logical_button: str,
        *,
        document: Optional[Dict[str, Any]] = None,
        required: bool = True,
    ) -> Dict[str, Any]:
        """Remove a logical mapping from a working document."""
        working = self._clone_document(document or self.load_document())
        channels = working.get("channels") or {}
        normalized_button = self._normalize_logical_button(
            logical_button,
            required=required,
            error_status=404 if required else 400,
        )
        if normalized_button and normalized_button in channels:
            channels.pop(normalized_button, None)
        elif required:
            raise HTTPException(
                status_code=404,
                detail=f"LED channel mapping not found for {logical_button}",
            )
        working["channels"] = self._normalize_channels(channels)
        return working

    def preview(self, document: Dict[str, Any]) -> LEDChannelMappingPreview:
        """Generate a diff between the stored mapping and a proposed payload."""
        self._ensure_allowed_path()
        normalized = self._normalize_document(document)
        current_text = ""
        if self._target_path.exists():
            try:
                current_text = self._target_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to read LED channel mapping: {exc}",
                ) from exc

        proposed_text = json.dumps(normalized, indent=2, sort_keys=True)
        diff = compute_diff(
            current_text,
            proposed_text,
            self._relative_target(),
        )
        preview = LEDChannelMappingPreview(
            response={
                "target_file": self._relative_target(),
                "channels": normalized["channels"],
                "total_channels": len(normalized["channels"]),
                "diff": diff,
                "has_changes": has_changes(current_text, proposed_text),
            },
            document=normalized,
            document_text=proposed_text,
            current_text=current_text,
            target_path=self._target_path,
            has_changes=has_changes(current_text, proposed_text),
        )
        return preview

    def apply(
        self,
        document: Dict[str, Any],
        *,
        dry_run: bool,
        request: Optional[Request] = None,
        preview: Optional[LEDChannelMappingPreview] = None,
    ) -> Dict[str, Any]:
        """Apply a sanitized mapping document to disk with backup/logging."""
        preview_result = preview or self.preview(document)

        backup_path: Optional[Path] = None
        if preview_result.has_changes and not dry_run:
            self._ensure_allowed_path()
            target_path = preview_result.target_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists():
                backup_path = create_backup(target_path, self.drive_root)
            target_path.write_text(preview_result.document_text + "\n", encoding="utf-8")
            self._document_cache = json.loads(preview_result.document_text)

        status = "no_changes"
        if preview_result.has_changes:
            status = "dry_run" if dry_run else "applied"

        self._log_event(
            request,
            status=status,
            backup_path=backup_path,
            total_channels=len(preview_result.response["channels"]),
        )

        return {
            "status": status,
            "dry_run": dry_run,
            "target_file": preview_result.target_file,
            "backup_path": self._as_relative_str(backup_path),
            "preview": preview_result.response,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_document(self) -> Dict[str, Any]:
        self._ensure_allowed_path()
        if not self._target_path.exists():
            return {"channels": {}}
        try:
            payload = json.loads(self._target_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"LED channel mapping is invalid JSON: {exc}",
            ) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to read LED channel mapping: {exc}",
            ) from exc
        return self._normalize_document(payload, error_status=500)

    def _normalize_document(self, document: Any, *, error_status: int = 400) -> Dict[str, Any]:
        if not isinstance(document, dict):
            document = {}
        channels = self._normalize_channels(document.get("channels"), error_status=error_status)
        return {"channels": channels}

    def _normalize_channels(
        self,
        channels: Any,
        *,
        error_status: int = 400,
    ) -> Dict[str, Dict[str, Any]]:
        normalized: Dict[str, Dict[str, Any]] = {}
        if isinstance(channels, dict):
            for key, value in channels.items():
                if not isinstance(value, dict):
                    continue
                logical_name = self._normalize_logical_button(key, error_status=error_status)
                try:
                    normalized[logical_name] = {
                        "device_id": self._normalize_device_id(value.get("device_id"), error_status=error_status),
                        "channel": self._normalize_channel(value.get("channel"), error_status=error_status),
                    }
                except HTTPException as exc:
                    raise HTTPException(
                        status_code=error_status,
                        detail=f"{logical_name}: {exc.detail}",
                    ) from exc
        return dict(sorted(normalized.items()))

    def _normalize_logical_button(
        self,
        value: Any,
        *,
        error_status: int = 400,
        required: bool = True,
    ) -> str:
        text = str(value or "").strip().lower()
        if not text:
            if required:
                raise HTTPException(
                    status_code=error_status,
                    detail="logical_button is required for LED channel mapping",
                )
            return ""
        return text

    def _normalize_device_id(self, value: Any, *, error_status: int = 400) -> str:
        device = str(value or "").strip()
        if not device:
            raise HTTPException(
                status_code=error_status,
                detail="device_id is required for LED channel mapping",
            )
        return device

    def _normalize_channel(self, value: Any, *, error_status: int = 400) -> int:
        try:
            channel = int(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=error_status,
                detail="channel must be an integer >= 1",
            ) from exc
        if channel < 1:
            raise HTTPException(
                status_code=error_status,
                detail="channel must be an integer >= 1",
            )
        return channel

    def _clone_document(self, document: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not document:
            return {"channels": {}}
        return json.loads(json.dumps(document))

    def _ensure_allowed_path(self) -> None:
        sanctioned = self.manifest.get("sanctioned_paths", [])
        if not sanctioned or not is_allowed_file(self._target_path, self.drive_root, sanctioned):
            raise HTTPException(
                status_code=403,
                detail=f"LED channel mapping path not sanctioned: {self._relative_target()}",
            )

    def _relative_target(self) -> str:
        return str(self.RELATIVE_PATH).replace("\\", "/")

    @property
    def relative_target(self) -> str:
        """Expose the relative target path for API responses."""
        return self._relative_target()

    def _as_relative_str(self, value: Optional[Path]) -> Optional[str]:
        if value is None:
            return None
        try:
            return str(value.relative_to(self.drive_root)).replace("\\", "/")
        except ValueError:
            return str(value)

    def _log_event(
        self,
        request: Optional[Request],
        *,
        status: str,
        backup_path: Optional[Path],
        total_channels: int,
    ) -> None:
        log_file = self.drive_root / ".aa" / "logs" / "changes.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        device = "unknown"
        panel = "unknown"
        if request is not None:
            device = request.headers.get("x-device-id", device)
            panel = request.headers.get("x-panel", panel)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scope": "led_channel_mapping",
            "action": "led_channel_mapping_apply",
            "status": status,
            "target_file": self._relative_target(),
            "backup_path": self._as_relative_str(backup_path),
            "total_channels": total_channels,
            "device": device,
            "panel": panel,
        }
        serialized = json.dumps(entry, ensure_ascii=False)
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(serialized + "\n")
