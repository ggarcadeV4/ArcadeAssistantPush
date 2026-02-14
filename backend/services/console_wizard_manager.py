"""Console Wizard backend helpers.

Responsible for turning Chuck's logical controls (`config/mappings/controls.json`)
into per-emulator configuration snapshots that live under
`configs/console_wizard/<...>`. The service also snapshots defaults,
computes health, restores configs, and keeps an audit log trail.

The implementation intentionally routes all file writes through the sanctioned
`configs` tree and always runs controller_cascade's JSON writer so it stays
consistent with the existing PreviewApply flows.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException

from . import controller_cascade
from .backup import create_backup
from .diffs import compute_diff, has_changes
from .emulator_discovery import EmulatorDiscoveryService, EmulatorInfo
from .mapping_dictionary import MappingDictionaryService
from .policies import is_allowed_file

logger = logging.getLogger(__name__)

PROFILES_DIR = Path("backend/profiles/console_wizard")


class ConsoleWizardManager:
    """High-level orchestration for Console Wizard backend operations."""

    CURRENT_ROOT = Path("configs/console_wizard/current")
    DEFAULTS_ROOT = Path("configs/console_wizard/defaults")
    STATE_ROOT = Path("state/console_wizard")
    SIGNATURE_PATH = STATE_ROOT / "controls_signature.json"
    LOG_RELATIVE = Path("logs/changes.jsonl")

    REQUIRED_LOGICAL_KEYS = {
        "p1.up", "p1.down", "p1.left", "p1.right",
        "p1.button1", "p1.button2", "p1.button3", "p1.button4",
        "p1.start", "p1.coin",
        "p2.up", "p2.down", "p2.left", "p2.right",
        "p2.button1", "p2.button2", "p2.button3", "p2.button4",
        "p2.start", "p2.coin",
    }

    RETROARCH_BUTTON_MAPPING = {
        "button1": "b_btn",
        "button2": "a_btn",
        "button3": "y_btn",
        "button4": "x_btn",
        "button5": "l_btn",
        "button6": "r_btn",
        "button7": "l2_btn",
        "button8": "r2_btn",
    }

    RETROARCH_SPECIAL_CONTROLS = {
        "start": "start_btn",
        "coin": "select_btn",
        "up": "up_btn",
        "down": "down_btn",
        "left": "left_btn",
        "right": "right_btn",
    }

    def __init__(self, drive_root: Path, manifest: Dict[str, Any]):
        self.drive_root = Path(drive_root)
        self.manifest = manifest or {}
        self.sanctioned_paths: List[str] = self.manifest.get("sanctioned_paths", [])
        self.discovery = EmulatorDiscoveryService(self.drive_root, self.manifest)
        self.mapping_service = MappingDictionaryService(self.drive_root, self.manifest)
        self._json_writer = controller_cascade.CONFIG_WRITERS.get("json")
        if self._json_writer is None:  # pragma: no cover - sanity guard
            raise RuntimeError("controller_cascade JSON writer unavailable")
        self._profile_cache: Dict[str, Optional[Dict[str, Any]]] = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def list_emulators(self) -> List[Dict[str, Any]]:
        infos = self.discovery.discover_emulators(console_only=True)
        payload: List[Dict[str, Any]] = []
        for info in infos:
            payload.append(
                {
                    "id": info.type,
                    "name": info.name,
                    "config_format": info.config_format,
                    "priority": info.priority,
                    "path_hint": self._relative_or_none(info.config_path),
                    "enabled": info.enabled,
                }
            )
        return payload

    def generate_configs(
        self,
        emulator_filter: Optional[Iterable[str]] = None,
        *,
        dry_run: bool = False,
        log_action: str = "generate_configs",
        device_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        controls_blob = self.mapping_service.load_current()
        controls = controls_blob.get("mappings") or {}
        if not controls:
            raise HTTPException(
                status_code=404,
                detail="controls.json is empty - run Controller Chuck first.",
            )

        missing_keys = self.REQUIRED_LOGICAL_KEYS - set(controls.keys())
        if missing_keys:
            sorted_missing = sorted(missing_keys)
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "incomplete_mapping",
                    "message": "Controller mapping is missing required logical keys",
                    "missing_keys": sorted_missing,
                },
            )

        emulators = self._filter_emulators(emulator_filter)
        results: List[Dict[str, Any]] = []
        backups: List[str] = []
        target_files: List[str] = []

        written_emulators: List[str] = []
        snapshot_needed: List[str] = []

        for info in emulators:
            mapping = self._build_mapping_for_emulator(info.type, controls)
            if not mapping:
                results.append(
                    {
                        "emulator": info.type,
                        "status": "skipped",
                        "reason": "unsupported_emulator",
                    }
                )
                continue

            target_path = self._current_config_path(info.type)
            self._ensure_sanctioned(target_path)
            rel_target = self._relative_or_none(target_path)
            default_path = self._default_config_path(info.type)
            if not default_path.exists():
                snapshot_needed.append(info.type)

            new_text = json.dumps(mapping, indent=2, sort_keys=True)
            existing_text = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
            diff = compute_diff(existing_text, new_text, rel_target or target_path.name)
            changed = has_changes(existing_text, new_text)

            backup_path: Optional[Path] = None
            if not dry_run and changed:
                if target_path.exists():
                    backup_path = create_backup(target_path, self.drive_root)
                    target_path.unlink()
                target_path.parent.mkdir(parents=True, exist_ok=True)
                self._json_writer(  # type: ignore[arg-type]
                    target_path,
                    mapping=mapping,
                    drive_root=self.drive_root,
                    backup_on_write=False,
                )
                target_files.append(rel_target or str(target_path))

                # CRITICAL: Also apply to the actual emulator config file (99.9% automation)
                real_config_path = self._apply_to_emulator_config(
                    info.type, mapping, info, backup=True
                )
                if real_config_path:
                    logger.info(f"Applied {info.type} mapping to real config: {real_config_path}")
                    target_files.append(real_config_path)

            if backup_path:
                backups.append(self._relative_or_none(backup_path) or str(backup_path))

            status = "written" if changed and not dry_run else "preview"
            if status == "written":
                written_emulators.append(info.type)

            results.append(
                {
                    "emulator": info.type,
                    "status": status,
                    "diff": diff,
                    "target_file": rel_target,
                    "has_changes": changed,
                }
            )

        if not dry_run and written_emulators:
            self._append_log(
                action=log_action,
                emulators=written_emulators,
                backup_paths=backups if backups else None,
                target_files=target_files if target_files else None,
                device_id=device_id,
            )

        # Ensure defaults exist after successful writes to clear health warnings
        if not dry_run and (written_emulators or snapshot_needed):
            snapshot_targets = snapshot_needed or written_emulators
            try:
                self.snapshot_defaults(snapshot_targets)
            except Exception as exc:  # pragma: no cover - best-effort snapshot
                logger.warning("Failed to snapshot defaults after apply: %s", exc)

        return results

    def snapshot_defaults(
        self, emulator_filter: Optional[Iterable[str]] = None
    ) -> List[Dict[str, Any]]:
        emulators = self._filter_emulators(emulator_filter)
        results: List[Dict[str, Any]] = []
        backups: List[str] = []

        snapshotted: List[str] = []

        for info in emulators:
            current_path = self._current_config_path(info.type)
            if not current_path.exists():
                results.append(
                    {"emulator": info.type, "status": "skipped", "reason": "no_current_config"}
                )
                continue

            default_path = self._default_config_path(info.type)
            self._ensure_sanctioned(default_path)
            default_path.parent.mkdir(parents=True, exist_ok=True)

            backup_path: Optional[Path] = None
            if default_path.exists():
                backup_path = create_backup(default_path, self.drive_root)

            shutil.copy2(current_path, default_path)
            if backup_path:
                backups.append(self._relative_or_none(backup_path) or str(backup_path))

            snapshotted.append(info.type)
            results.append(
                {
                    "emulator": info.type,
                    "status": "snapshotted",
                    "defaults_path": self._relative_or_none(default_path),
                }
            )

        if snapshotted:
            self._append_log(
                action="set_defaults",
                emulators=snapshotted,
                backup_paths=backups if backups else None,
            )

        return results

    def health(self) -> List[Dict[str, Any]]:
        emulators = self._filter_emulators(None)
        statuses: List[Dict[str, Any]] = []

        for info in emulators:
            current_path = self._current_config_path(info.type)
            default_path = self._default_config_path(info.type)

            status = "healthy"
            detail = None

            try:
                current_text = (
                    current_path.read_text(encoding="utf-8") if current_path.exists() else ""
                )
                default_text = (
                    default_path.read_text(encoding="utf-8") if default_path.exists() else ""
                )
            except OSError as exc:
                status = "corrupted"
                detail = str(exc)
                current_text = default_text = ""

            if not default_path.exists():
                if current_path.exists():
                    status = "pending_defaults"
                    detail = "Defaults not yet captured (run apply to snapshot)"
                else:
                    status = "missing"
                    detail = "Default snapshot not found"
            elif not current_path.exists():
                status = "missing"
                detail = "Current config missing"
            elif status != "corrupted" and has_changes(current_text, default_text):
                status = "modified"

            statuses.append(
                {
                    "emulator": info.type,
                    "status": status,
                    "details": detail,
                    "current_file": self._relative_or_none(current_path),
                    "defaults_file": self._relative_or_none(default_path),
                }
            )

        return statuses

    def restore_emulator(self, emulator: str, *, dry_run: bool = False) -> Dict[str, Any]:
        default_path = self._default_config_path(emulator)
        if not default_path.exists():
            raise HTTPException(
                status_code=404, detail=f"No defaults available for emulator '{emulator}'."
            )

        current_path = self._current_config_path(emulator)
        self._ensure_sanctioned(current_path)

        default_text = default_path.read_text(encoding="utf-8")
        existing_text = current_path.read_text(encoding="utf-8") if current_path.exists() else ""
        diff = compute_diff(
            existing_text, default_text, self._relative_or_none(current_path) or emulator
        )
        changed = has_changes(existing_text, default_text)

        backup_path: Optional[Path] = None
        if changed and not dry_run:
            if current_path.exists():
                backup_path = create_backup(current_path, self.drive_root)
            current_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(default_path, current_path)

        if changed and not dry_run:
            backup_payload = None
            if backup_path:
                backup_payload = [self._relative_or_none(backup_path) or str(backup_path)]
            self._append_log(
                action="restore_emu",
                emulators=[emulator],
                backup_paths=backup_payload,
            )

        return {
            "emulator": emulator,
            "restored": changed and not dry_run,
            "backup_path": self._relative_or_none(backup_path),
            "diff": diff,
        }

    def restore_all(self, *, dry_run: bool = False) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []

        for info in self._filter_emulators(None):
            try:
                result = self.restore_emulator(info.type, dry_run=dry_run)
                results.append(result)
            except HTTPException as exc:
                if exc.status_code == 404:
                    results.append(
                        {
                            "emulator": info.type,
                            "restored": False,
                            "error": exc.detail,
                        }
                    )
                else:
                    raise

        if not dry_run:
            restored = [item for item in results if item.get("restored")]
            if restored:
                backup_list = [
                    item["backup_path"]
                    for item in restored
                    if item.get("backup_path")
                ] or None
                self._append_log(
                    action="restore_all",
                    emulators=[item["emulator"] for item in restored],
                    backup_paths=backup_list,
                )

        return results

    def sync_from_chuck(
        self, emulator_filter: Optional[Iterable[str]] = None, *, force: bool = False, dry_run: bool = False, device_id: Optional[str] = None
    ) -> Dict[str, Any]:
        signature = self._controls_signature()
        previous = self._load_signature()
        changed = signature != previous

        if not changed and not force:
            return {"changed": False, "results": [], "skipped": True}

        results = self.generate_configs(
            emulator_filter, dry_run=dry_run, log_action="sync_from_chuck", device_id=device_id
        )
        if not dry_run:
            self._store_signature(signature)
        return {"changed": True, "results": results, "skipped": False}

    def get_chuck_status(self) -> Dict[str, Any]:
        """Return Chuck sync status with mapping hash comparison."""
        current_hash = self._controls_signature()
        last_synced_hash = self._load_signature()
        is_out_of_sync = (last_synced_hash is None) or (current_hash != last_synced_hash)

        return {
            "currentMappingHash": current_hash,
            "lastSyncedHash": last_synced_hash,
            "isOutOfSync": is_out_of_sync,
        }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _filter_emulators(
        self, emulator_filter: Optional[Iterable[str]]
    ) -> List[EmulatorInfo]:
        wanted = {name.lower() for name in emulator_filter or []}
        infos = self.discovery.discover_emulators(console_only=True)
        if not wanted:
            return infos
        filtered = [info for info in infos if info.type.lower() in wanted]
        if not filtered:
            raise HTTPException(
                status_code=404,
                detail=f"No emulators matched filter: {sorted(wanted)}",
            )
        return filtered

    def _current_config_path(self, emulator: str) -> Path:
        return self.drive_root / self.CURRENT_ROOT / emulator / "mapping.json"

    def _default_config_path(self, emulator: str) -> Path:
        return self.drive_root / self.DEFAULTS_ROOT / emulator / "mapping.json"

    def _ensure_sanctioned(self, path: Path) -> None:
        if not is_allowed_file(path, self.drive_root, self.sanctioned_paths):
            raise HTTPException(
                status_code=403,
                detail=f"Path not sanctioned by manifest: {self._relative_or_none(path) or path}",
            )

    def _apply_to_emulator_config(
        self, emulator_type: str, mapping: Dict[str, Any], info: EmulatorInfo, backup: bool = True
    ) -> Optional[str]:
        """
        Apply mapping to the actual emulator config file (e.g., mame.ini, retroarch.cfg).
        Returns the relative path of the config file if successful, None if skipped/failed.
        """
        # Use discovered config_path from EmulatorInfo (already absolute path)
        # This is more reliable than DEFAULT_CONFIG_PATHS since it's based on actual discovery
        config_path = None
        if info.config_path:
            config_path = Path(info.config_path) if isinstance(info.config_path, str) else info.config_path
        
        # Fallback to DEFAULT_CONFIG_PATHS resolved against drive letter root
        if not config_path or not config_path.exists():
            config_hint = controller_cascade.DEFAULT_CONFIG_PATHS.get(emulator_type.lower())
            if config_hint:
                # Check if path starts with ~ (user profile path)
                config_hint_str = str(config_hint)
                if config_hint_str.startswith("~"):
                    import os
                    config_path = Path(os.path.expanduser(config_hint_str))
                else:
                    # Resolve against drive letter root, not project folder
                    drive_letter_root = Path(self.drive_root.drive + "\\") if self.drive_root.drive else self.drive_root
                    config_path = drive_letter_root / config_hint

        if not config_path:
            logger.warning(f"No config path for {emulator_type}, skipping real config write")
            return None

        # Check if path exists
        if not config_path.exists():
            logger.warning(f"Config path does not exist: {config_path}, skipping")
            return None

        # Sanctioned path check: use drive letter root for emulator paths
        # since emulators are at A:\Emulators, not A:\Arcade Assistant Local\Emulators
        drive_letter_root = Path(self.drive_root.drive + "\\") if self.drive_root.drive else self.drive_root
        if not is_allowed_file(config_path, drive_letter_root, self.sanctioned_paths):
            # Also try relative to project folder for configs inside project
            if not is_allowed_file(config_path, self.drive_root, self.sanctioned_paths):
                logger.warning(f"Config path not sanctioned: {config_path}, skipping")
                return None

        # Determine format and call appropriate apply function
        format_hint = info.config_format.lower() if info.config_format else "ini"

        try:
            if emulator_type.lower() == "teknoparrot":
                # TeknoParrot uses per-profile XML files in UserProfiles/
                # We don't write directly here; instead, we log the mapping
                # and let the cascade or preview/apply endpoints handle it.
                logger.info(f"TeknoParrot mapping prepared ({len(mapping.get('bindings', {}))} bindings)")
                return self._relative_or_none(config_path) or str(config_path)
            elif emulator_type.lower() == "mame":
                # MAME has a special apply function
                controller_cascade._apply_mame_mapping(
                    config_path,
                    mapping,
                    drive_root=self.drive_root,
                    backup_on_write=backup,
                )
            elif format_hint in ("cfg", "ini"):
                # Use INI writer for RetroArch, Dolphin, etc.
                writer = controller_cascade.CONFIG_WRITERS.get("ini")
                if writer:
                    writer(
                        config_path,
                        mapping=mapping,
                        drive_root=self.drive_root,
                        backup_on_write=backup,
                    )
            else:
                # Try to use the appropriate writer based on format
                writer = controller_cascade.CONFIG_WRITERS.get(format_hint)
                if writer:
                    writer(
                        config_path,
                        mapping=mapping,
                        drive_root=self.drive_root,
                        backup_on_write=backup,
                    )
                else:
                    logger.warning(f"No writer for format {format_hint}, skipping")
                    return None

            rel_path = self._relative_or_none(config_path)
            logger.info(f"Applied mapping to {emulator_type} config: {rel_path or config_path}")
            return rel_path or str(config_path)

        except Exception as exc:
            logger.exception(f"Failed to apply mapping to {emulator_type} config: {exc}")
            return None

    def _load_profile(self, emulator_type: str) -> Optional[Dict[str, Any]]:
        """Load emulator profile from JSON file, with caching."""
        if emulator_type in self._profile_cache:
            return self._profile_cache[emulator_type]

        profile_path = self.drive_root / PROFILES_DIR / f"{emulator_type}.json"
        if not profile_path.exists():
            self._profile_cache[emulator_type] = None
            return None

        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                profile = json.load(f)
            self._profile_cache[emulator_type] = profile
            logger.info(f"Loaded profile for {emulator_type} from {profile_path}")
            return profile
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Failed to load profile for {emulator_type}: {exc}")
            self._profile_cache[emulator_type] = None
            return None

    def _build_mapping_for_emulator(
        self, emulator: str, controls: Dict[str, Any]
    ) -> Dict[str, Any]:
        emulator = emulator.lower()

        profile = self._load_profile(emulator)
        if profile:
            return self._build_mapping_from_profile(emulator, controls, profile)

        if emulator == "retroarch":
            return self._retroarch_mapping(controls)
        if emulator == "mame":
            return self._mame_mapping(controls)
        if emulator == "teknoparrot":
            return self._teknoparrot_mapping(controls)
        return self._default_mapping(controls)

    def _build_mapping_from_profile(
        self, emulator: str, controls: Dict[str, Any], profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build mapping using profile-based approach."""
        button_mapping = profile.get("button_mapping", {})
        special_controls = profile.get("special_controls", {})
        supported_players = profile.get("supported_players", 2)

        mapping: Dict[str, Any] = {}
        for logical, payload in controls.items():
            parsed = self._parse_logical(logical)
            if not parsed:
                continue
            player_idx, control_name = parsed

            if int(player_idx) > supported_players:
                continue

            mapped_key = button_mapping.get(control_name) or special_controls.get(control_name)
            if not mapped_key:
                continue

            if emulator == "retroarch":
                config_key = f"input_player{player_idx}_{mapped_key}"
                mapping[config_key] = str(payload.get("pin"))
            elif emulator == "dolphin":
                config_key = f"GCPad{player_idx}/{mapped_key}"
                mapping[config_key] = str(payload.get("pin"))
            elif emulator == "pcsx2":
                config_key = f"Pad{player_idx}/{mapped_key}"
                mapping[config_key] = str(payload.get("pin"))
            else:
                config_key = f"p{player_idx}.{control_name}"
                mapping[config_key] = str(payload.get("pin"))

        return {"input": mapping} if emulator == "retroarch" else mapping

    def _retroarch_mapping(self, controls: Dict[str, Any]) -> Dict[str, Any]:
        mapping: Dict[str, Any] = {}
        for logical, payload in controls.items():
            parsed = self._parse_logical(logical)
            if not parsed:
                continue
            player_idx, control_name = parsed
            retro_key = None
            if control_name in self.RETROARCH_BUTTON_MAPPING:
                retro_key = self.RETROARCH_BUTTON_MAPPING[control_name]
            elif control_name in self.RETROARCH_SPECIAL_CONTROLS:
                retro_key = self.RETROARCH_SPECIAL_CONTROLS[control_name]
            if not retro_key:
                continue
            config_key = f"input_player{player_idx}_{retro_key}"
            mapping[config_key] = str(payload.get("pin"))
        return {"input": mapping}

    def _mame_mapping(self, controls: Dict[str, Any]) -> Dict[str, Any]:
        mapping: Dict[str, Dict[str, Any]] = {"input_general": {}}
        for logical, payload in controls.items():
            parsed = self._parse_logical(logical)
            if not parsed:
                continue
            player_idx, control_name = parsed
            key = None
            if control_name.startswith("button"):
                suffix = "".join(ch for ch in control_name if ch.isdigit())
                key = f"P{player_idx}_BUTTON{suffix or ''}"
            elif control_name == "coin":
                key = f"P{player_idx}_COIN"
            elif control_name == "start":
                key = f"P{player_idx}_START"
            elif control_name in {"up", "down", "left", "right"}:
                key = f"P{player_idx}_JOYSTICK_{control_name.upper()}"
            if not key:
                continue
            mapping["input_general"][key] = str(payload.get("pin"))
        return mapping

    def _teknoparrot_mapping(self, controls: Dict[str, Any]) -> Dict[str, Any]:
        """Build TeknoParrot-compatible mapping from arcade panel controls.
        
        Maps panel controls to TeknoParrot input binding format.
        Uses the canonical schema from teknoparrot_config_generator.
        """
        # TeknoParrot uses a different format - we map to TP's XML element names
        # Example: p1.button1 -> InputButton1, p1.start -> InputStart
        TP_CONTROL_MAP = {
            "button1": "InputButton1",
            "button2": "InputButton2",
            "button3": "InputButton3",
            "button4": "InputButton4",
            "button5": "InputButton5",
            "button6": "InputButton6",
            "button7": "InputButton7",
            "button8": "InputButton8",
            "start": "InputStart",
            "coin": "InputCoin",
            "up": "InputUp",
            "down": "InputDown",
            "left": "InputLeft",
            "right": "InputRight",
        }
        
        mapping: Dict[str, Any] = {"category": "generic", "bindings": {}}
        
        for logical, payload in controls.items():
            parsed = self._parse_logical(logical)
            if not parsed:
                continue
            player_idx, control_name = parsed
            
            # Only support player 1 for now (TeknoParrot is typically single-player focus)
            if int(player_idx) > 1:
                continue
            
            tp_key = TP_CONTROL_MAP.get(control_name)
            if not tp_key:
                continue
            
            pin = payload.get("pin")
            if pin is not None:
                # TeknoParrot uses DirectInput format for bindings
                mapping["bindings"][tp_key] = {
                    "type": payload.get("type", "button"),
                    "pin": pin,
                    "raw_value": f"DirectInput/0/Button {pin}",
                }
        
        return mapping

    def _default_mapping(self, controls: Dict[str, Any]) -> Dict[str, Any]:
        players: Dict[str, Dict[str, Any]] = {}
        for logical, payload in controls.items():
            parsed = self._parse_logical(logical, preserve_player_key=True)
            if not parsed:
                continue
            player_key, control_name = parsed
            players.setdefault(player_key, {})[control_name] = {
                "pin": payload.get("pin"),
                "type": payload.get("type"),
                "label": payload.get("label"),
            }
        return {"players": players}

    def _parse_logical(
        self, logical: str, preserve_player_key: bool = False
    ) -> Optional[Tuple[str, str]]:
        if "." not in logical:
            return None
        player, control = logical.split(".", 1)
        if preserve_player_key:
            return player, control
        if not player.startswith("p"):
            return None
        try:
            idx = int(player[1:])
            return str(idx), control
        except ValueError:
            return None

    def _relative_or_none(self, path: Optional[Path]) -> Optional[str]:
        if not path:
            return None
        try:
            return path.relative_to(self.drive_root).as_posix()
        except ValueError:
            return path.as_posix()

    def _append_log(
        self,
        *,
        action: str,
        emulators: List[str],
        backup_paths: Optional[List[str]] = None,
        target_files: Optional[List[str]] = None,
        device_id: Optional[str] = None,
    ) -> None:
        entry = {
            "panel": "console_wizard",
            "action": action,
            "emulators": emulators,
            "backup_path": backup_paths if backup_paths else None,
            "target_files": target_files if target_files else None,
            "device_id": device_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        log_path = self.drive_root / self.LOG_RELATIVE
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.error("Failed to append console wizard log entry: %s", exc)

    def _controls_signature(self) -> str:
        controls_blob = self.mapping_service.load_current()
        canonical = json.dumps(controls_blob, sort_keys=True).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def get_config_contents(self, emulator: str, *, max_bytes: int = 200_000) -> Dict[str, Any]:
        """Return current/default config file contents for an emulator (read-only helper)."""
        current_path = self._current_config_path(emulator)
        default_path = self._default_config_path(emulator)

        # Ensure paths are sanctioned before reading
        self._ensure_sanctioned(current_path)
        self._ensure_sanctioned(default_path)

        def _read_safe(path: Path) -> Tuple[str, bool]:
            if not path.exists():
                return "", False
            data = path.read_bytes()
            truncated = False
            if len(data) > max_bytes:
                data = data[:max_bytes]
                truncated = True
            return data.decode("utf-8", errors="replace"), truncated

        current_text, current_truncated = _read_safe(current_path)
        default_text, default_truncated = _read_safe(default_path)

        return {
            "emulator": emulator,
            "current_file": self._relative_or_none(current_path),
            "defaults_file": self._relative_or_none(default_path),
            "current_text": current_text,
            "defaults_text": default_text,
            "current_truncated": current_truncated,
            "defaults_truncated": default_truncated,
        }

    def _load_signature(self) -> Optional[str]:
        signature_path = self.drive_root / self.SIGNATURE_PATH
        if not signature_path.exists():
            return None
        try:
            payload = json.loads(signature_path.read_text(encoding="utf-8"))
            return payload.get("hash")
        except (json.JSONDecodeError, OSError):
            return None

    def _store_signature(self, signature: str) -> None:
        signature_path = self.drive_root / self.SIGNATURE_PATH
        signature_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"hash": signature, "updated_at": datetime.now(timezone.utc).isoformat()}
        signature_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
