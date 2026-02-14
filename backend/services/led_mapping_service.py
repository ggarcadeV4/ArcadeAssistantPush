"""Map logical LED profiles to physical LED channels via Chuck's controls.json."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from .backup import create_backup
from .diffs import compute_diff, has_changes
from .led_engine.led_channel_mapping_service import LEDChannelMappingService
from .mapping_dictionary import MappingDictionaryService
from .policies import is_allowed_file


@dataclass
class LedChannel:
    """Resolved LED hardware channel for a logical button."""

    logical_button: str
    device_id: str
    channel_index: int
    label: Optional[str] = None
    vendor_id: Optional[str] = None
    product_id: Optional[str] = None
    board_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "logical_button": self.logical_button,
            "device_id": self.device_id,
            "channel_index": self.channel_index,
            "label": self.label,
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "board_name": self.board_name,
        }


@dataclass
class LEDPreviewResult:
    """Internal representation of a preview before applying a profile."""

    response: Dict[str, Any]
    document: Dict[str, Any]
    document_text: str
    current_text: str
    target_path: Path
    has_changes: bool

    @property
    def target_file(self) -> str:
        return self.response["target_file"]


class LEDMappingService:
    """High-level helper for LED profile preview + apply workflows."""

    PROFILES_RELATIVE = Path("configs/ledblinky/profiles")

    def __init__(self, drive_root: Path, manifest: Dict[str, Any]):
        self.drive_root = drive_root
        self.manifest = manifest or {}
        self._mapping_service = MappingDictionaryService(drive_root, self.manifest)
        self._channel_mapping_service = LEDChannelMappingService(drive_root, self.manifest)
        self._mapping_cache: Optional[Dict[str, Any]] = None

    def load_controls_mapping(self) -> Dict[str, Any]:
        """Return a copy of the current controls.json payload."""
        payload = self._load_mapping_payload()
        return json.loads(json.dumps(payload))

    def resolve_logical_button(self, logical_button: str) -> List[LedChannel]:
        """Return physical LED channels associated with a logical button."""
        mappings = self._logical_mappings()
        mapping_entry = mappings.get(logical_button)
        if not mapping_entry:
            return []

        binding = self._channel_mapping_service.resolve(logical_button)
        if binding is None:
            return []

        board = self._board_info()
        channel = LedChannel(
            logical_button=logical_button,
            device_id=binding.device_id,
            channel_index=binding.channel,
            label=mapping_entry.get("label", logical_button),
            vendor_id=board.get("vid"),
            product_id=board.get("pid"),
            board_name=board.get("name"),
        )
        return [channel]

    def preview(self, profile: Dict[str, Any]) -> LEDPreviewResult:
        """Resolve a logical profile without mutating files."""
        normalized = self._normalize_profile_payload(profile)
        target_path = self._profile_path(normalized["profile_name"])
        self._validate_profile_path(target_path)

        current_text = ""
        if target_path.exists():
            try:
                current_text = target_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to read LED profile: {exc}",
                ) from exc

        document = self._profile_document(normalized)
        document_text = json.dumps(document, indent=2, sort_keys=True)
        diff = compute_diff(
            current_text,
            document_text,
            str(target_path.relative_to(self.drive_root)).replace("\\", "/"),
        )
        preview_has_changes = has_changes(current_text, document_text)

        resolved_buttons, missing_buttons = self._resolve_buttons(document["buttons"])
        board = self._board_info()
        target_file = self._relative_profile_path(normalized["profile_name"])
        response = {
            "profile_name": document["profile_name"],
            "scope": document["scope"],
            "game": document.get("game"),
            "metadata": document.get("metadata", {}),
            "animation": document.get("animation"),
            "buttons": document["buttons"],
            "resolved_buttons": resolved_buttons,
            "missing_buttons": missing_buttons,
            "board": board,
            "target_file": target_file,
            "total_channels": sum(len(item["channels"]) for item in resolved_buttons),
            "diff": diff,
            "has_changes": preview_has_changes,
        }
        return LEDPreviewResult(
            response=response,
            document=document,
            document_text=document_text,
            current_text=current_text,
            target_path=target_path,
            has_changes=preview_has_changes,
        )

    def apply(
        self,
        profile: Dict[str, Any],
        *,
        dry_run: bool,
        backup_on_write: bool,
        preview: Optional[LEDPreviewResult] = None,
    ) -> Dict[str, Any]:
        """Apply a logical profile, optionally reusing a prior preview."""
        preview_result = preview or self.preview(profile)
        backup_path: Optional[Path] = None

        if preview_result.has_changes and not dry_run:
            target_path = preview_result.target_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists() and backup_on_write:
                backup_path = create_backup(target_path, self.drive_root)
            target_path.write_text(preview_result.document_text + "\n", encoding="utf-8")

        status = "no_changes"
        if preview_result.has_changes:
            status = "dry_run" if dry_run else "applied"

        return {
            "status": status,
            "dry_run": dry_run,
            "target_file": preview_result.target_file,
            "backup_path": self._as_relative_str(backup_path),
            "preview": preview_result.response,
        }

    def _resolve_buttons(
        self, buttons: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        resolved: List[Dict[str, Any]] = []
        missing: List[str] = []

        for logical_button, config in buttons.items():
            channels = self.resolve_logical_button(logical_button)
            if not channels:
                missing.append(logical_button)
                continue
            resolved.append(
                {
                    "logical_button": logical_button,
                    "settings": config,
                    "channels": [channel.to_dict() for channel in channels],
                }
            )
        return resolved, missing

    def _as_relative_str(self, value: Optional[Path]) -> Optional[str]:
        if value is None:
            return None
        try:
            return str(value.relative_to(self.drive_root)).replace("\\", "/")
        except ValueError:
            return str(value)

    def _profile_document(self, normalized: Dict[str, Any]) -> Dict[str, Any]:
        document: Dict[str, Any] = {
            "profile_name": normalized["profile_name"],
            "scope": normalized.get("scope", "default"),
            "game": normalized.get("game"),
            "metadata": normalized.get("metadata", {}),
            "buttons": normalized.get("buttons") or {},
        }
        if normalized.get("animation") is not None:
            document["animation"] = normalized["animation"]
        return document

    def _normalize_profile_payload(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        scope_raw = profile.get("scope", "game")
        scope = str(scope_raw).strip().lower()
        if scope not in {"default", "game", "shared", "profile"}:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid scope: {scope_raw}",
            )

        game_value = profile.get("game")
        game = str(game_value).strip() if isinstance(game_value, str) and game_value.strip() else None

        buttons_payload = profile.get("buttons")
        if not buttons_payload and isinstance(profile.get("mapping"), dict):
            buttons_payload = profile["mapping"]
        if not isinstance(buttons_payload, dict) or not buttons_payload:
            raise HTTPException(
                status_code=400,
                detail="buttons payload must include at least one logical mapping",
            )

        metadata = profile.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        normalized = {
            "scope": scope,
            "game": game if scope == "game" else None,
            "metadata": metadata,
            "animation": profile.get("animation"),
            "buttons": self._normalize_buttons(buttons_payload),
        }
        resolved_name = self._determine_profile_name(profile.get("profile_name"), scope, normalized["game"])
        normalized["profile_name"] = resolved_name
        return normalized

    def _determine_profile_name(
        self,
        profile_name: Optional[str],
        scope: str,
        game: Optional[str],
    ) -> str:
        if isinstance(profile_name, str) and profile_name.strip():
            return profile_name.strip()
        if scope == "default":
            return "default"
        if scope == "game" and game:
            return game
        return "profile"

    def _normalize_buttons(self, buttons: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        normalized: Dict[str, Dict[str, Any]] = {}
        for key, value in buttons.items():
            if not isinstance(key, str):
                continue
            trimmed = key.strip()
            if not trimmed:
                continue
            normalized[trimmed] = self._normalize_button_value(value)
        if not normalized:
            raise HTTPException(
                status_code=400,
                detail="buttons payload must resolve to at least one logical button",
            )
        return normalized

    def _normalize_button_value(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return {"color": text}
            return {}
        if value is None:
            return {}
        return {"color": str(value)}

    def _profile_path(self, profile_name: str) -> Path:
        safe_name = self._sanitize_name(profile_name)
        return (self.drive_root / self.PROFILES_RELATIVE) / f"{safe_name}.json"

    def _relative_profile_path(self, profile_name: str) -> str:
        return str(self._profile_path(profile_name).relative_to(self.drive_root)).replace(
            "\\", "/"
        )

    def load_profile_document(self, profile_name: str) -> Dict[str, Any]:
        """Load an existing stored profile for metadata lookups."""
        target_path = self._profile_path(profile_name)
        if not target_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"LED profile not found: {profile_name}",
            )

        try:
            document = json.loads(target_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Stored LED profile is invalid JSON: {exc}",
            ) from exc

        return {
            "path": self._relative_profile_path(profile_name),
            "document": document,
        }

    def _sanitize_name(self, value: str) -> str:
        sanitized = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
        return sanitized or "profile"

    def _validate_profile_path(self, path: Path) -> None:
        sanctioned = self.manifest.get("sanctioned_paths", [])
        if not sanctioned:
            raise HTTPException(
                status_code=403,
                detail="No sanctioned paths configured for LED profile writes",
            )
        if not is_allowed_file(path, self.drive_root, sanctioned):
            relative = path.relative_to(self.drive_root)
            raise HTTPException(
                status_code=403,
                detail=f"LED profile path not sanctioned: {relative}",
            )

    def _load_mapping_payload(self) -> Dict[str, Any]:
        if self._mapping_cache is None:
            payload = self._mapping_service.load_current()
            self._mapping_cache = payload or {}
        return self._mapping_cache

    def _logical_mappings(self) -> Dict[str, Any]:
        payload = self._load_mapping_payload()
        mappings = payload.get("mappings")
        if not isinstance(mappings, dict):
            return {}
        return mappings

    def _board_info(self) -> Dict[str, Any]:
        payload = self._load_mapping_payload()
        board = payload.get("board")
        if isinstance(board, dict):
            return board
        return {}
