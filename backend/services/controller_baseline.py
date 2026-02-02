from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .backup import create_backup
from .emulator_discovery import EmulatorDiscoveryService
from .audit_log import append as append_audit_log
from .policies import is_allowed_file

logger = logging.getLogger(__name__)


class ControllerBaselineError(Exception):
    """Raised when baseline operations fail."""


BASELINE_VERSION = "1.0.0"
BASELINE_RELATIVE_PATH = Path("state") / "controller" / "baseline.json"
DEFAULT_EMULATORS = ("mame", "retroarch", "dolphin", "pcsx2", "teknoparrot")
MAX_HISTORY_ENTRIES = 10
PRUNE_THRESHOLD_DAYS = 30
DEFAULT_CASCADE_PREFERENCE = "ask"


def _now() -> datetime:
    return datetime.now()


def _now_iso() -> str:
    return _now().isoformat()


def _default_emulator_state() -> Dict[str, Any]:
    return {
        "status": "unknown",
        "last_synced": None,
        "mapping": {},
        "config_path": None,
        "config_format": None,
        "last_job_id": None,
        "message": None,
        "last_seen": None,
    }


def _default_led_state() -> Dict[str, Any]:
    return {
        "status": "unknown",
        "profile": None,
        "mapping": {},
        "last_synced": None,
        "last_job_id": None,
        "message": None,
    }


def _default_cascade_state() -> Dict[str, Any]:
    return {
        "status": "idle",
        "current_job": None,
        "history": [],
        "preference": DEFAULT_CASCADE_PREFERENCE,
    }


def _default_encoder_state() -> Dict[str, Any]:
    return {
        "board": None,
        "mapping": {},
        "controls_count": 0,
        "last_modified": None,
        "modified_by": None,
        "summary": {},
    }


def _apply_defaults(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure the baseline dictionary has all required keys."""
    normalised = deepcopy(data)

    normalised.setdefault("version", BASELINE_VERSION)

    created_at = normalised.get("created_at") or _now_iso()
    updated_at = normalised.get("updated_at") or created_at
    normalised["created_at"] = created_at
    normalised["updated_at"] = updated_at

    # Encoder state
    encoder_state = normalised.get("encoder") or {}
    defaults = _default_encoder_state()
    for key, value in defaults.items():
        encoder_state.setdefault(key, deepcopy(value))
    normalised["encoder"] = encoder_state

    # LED state
    led_state = normalised.get("led") or {}
    led_defaults = _default_led_state()
    for key, value in led_defaults.items():
        led_state.setdefault(key, deepcopy(value))
    normalised["led"] = led_state

    # Emulators
    emulators = normalised.get("emulators") or {}
    for state in emulators.values():
        state.setdefault("last_seen", None)
        state.setdefault("config_format", None)
    normalised["emulators"] = emulators

    # Metadata
    metadata = normalised.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    normalised["metadata"] = metadata

    # Cascade metadata
    cascade_state = normalised.get("cascade") or {}
    cascade_defaults = _default_cascade_state()
    for key, value in cascade_defaults.items():
        cascade_state.setdefault(key, deepcopy(value))
    cascade_state["preference"] = str(
        cascade_state.get("preference") or DEFAULT_CASCADE_PREFERENCE
    ).lower()

    # Ensure history size cap
    history = cascade_state.get("history") or []
    cascade_state["history"] = history[-MAX_HISTORY_ENTRIES:]
    normalised["cascade"] = cascade_state

    return normalised


def _baseline_path(drive_root: Path) -> Path:
    return drive_root / BASELINE_RELATIVE_PATH


def _relative_path_string(path: Path, drive_root: Path) -> str:
    try:
        return path.relative_to(drive_root).as_posix()
    except ValueError:
        return str(path)


def _load_drive_manifest(drive_root: Path) -> Dict[str, Any]:
    """Best-effort load of /.aa/manifest.json under the provided drive root."""
    manifest_path = drive_root / ".aa" / "manifest.json"
    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            data = json.load(handle) or {}
            if isinstance(data, dict):
                return data
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("Failed to read manifest at %s: %s", manifest_path, exc)
    return {}


def migrate_baseline_to_dynamic(
    baseline: Dict[str, Any],
    drive_root: Path,
    manifest: Dict[str, Any],
) -> Dict[str, Any]:
    """Migrate legacy baselines that only tracked the default emulator set."""
    metadata = baseline.setdefault("metadata", {})
    if metadata.get("migrated_to_dynamic"):
        return baseline

    emulators = baseline.get("emulators") or {}
    emulator_keys = list(emulators.keys())
    needs_migration = (
        len(emulator_keys) == len(DEFAULT_EMULATORS)
        and set(emulator_keys) == set(DEFAULT_EMULATORS)
    )

    if not needs_migration:
        return baseline

    logger.info("Migrating controller baseline to dynamic emulator registry")
    metadata["migrated_to_dynamic"] = True
    baseline["metadata"] = metadata
    updated_baseline = discover_and_expand_emulators(
        drive_root,
        manifest,
        baseline=baseline,
        backup=False,
    )
    return save_controller_baseline(drive_root, updated_baseline)


def prune_absent_emulators(
    baseline: Dict[str, Any],
    discovered_types: List[str],
    seen_timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Remove emulators that have been absent beyond the configured threshold."""
    emulators = baseline.setdefault("emulators", {})
    discovered_set = set(discovered_types)
    now = _now()
    threshold = now - timedelta(days=PRUNE_THRESHOLD_DAYS)
    timestamp = seen_timestamp or _now_iso()
    pruned: List[str] = []

    for emulator, state in list(emulators.items()):
        last_seen_value = state.get("last_seen")

        if emulator in discovered_set:
            state["last_seen"] = timestamp
            continue

        if not last_seen_value:
            state["last_seen"] = timestamp
            continue

        try:
            last_seen = datetime.fromisoformat(last_seen_value)
        except ValueError:
            state["last_seen"] = timestamp
            continue

        if last_seen < threshold:
            pruned.append(emulator)
            del emulators[emulator]

    if pruned:
        logger.info(
            "Pruned emulators absent for more than %d days: %s",
            PRUNE_THRESHOLD_DAYS,
            ", ".join(pruned),
        )

    baseline["emulators"] = emulators
    return baseline


def discover_and_expand_emulators(
    drive_root: Path,
    manifest: Dict[str, Any],
    *,
    baseline: Optional[Dict[str, Any]] = None,
    backup: bool = False,
) -> Dict[str, Any]:
    """Discover emulators, merge them into the baseline, and prune stale entries."""
    manifest = manifest or _load_drive_manifest(drive_root)
    working_baseline = baseline if baseline is not None else load_controller_baseline(drive_root)

    discovery = EmulatorDiscoveryService(drive_root, manifest or {})
    discovered_infos = discovery.discover_emulators()

    discovered_entries: List[Tuple[str, Optional[Path], str]] = [
        (
            info.type,
            Path(info.config_path) if info.config_path else None,
            (info.config_format or "ini").lower(),
        )
        for info in discovered_infos
    ]

    if not discovered_entries:
        discovered_entries = [(emu, None, "ini") for emu in DEFAULT_EMULATORS]

    emulators = working_baseline.setdefault("emulators", {})
    updated = False
    seen_timestamp = _now_iso()
    discovered_types: List[str] = []

    for emulator_type, config_path, config_format in discovered_entries:
        discovered_types.append(emulator_type)
        state = emulators.get(emulator_type)
        if state is None:
            state = _default_emulator_state()
            emulators[emulator_type] = state
            updated = True

        if config_path is not None:
            config_str = _relative_path_string(config_path, drive_root)
            if state.get("config_path") != config_str:
                state["config_path"] = config_str
                updated = True

        if state.get("config_format") != config_format:
            state["config_format"] = config_format
            updated = True

        if state.get("last_seen") != seen_timestamp:
            state["last_seen"] = seen_timestamp
            updated = True

    pre_prune_snapshot = {
        name: state.get("last_seen")
        for name, state in emulators.items()
        if name not in discovered_types
    }
    pre_prune_count = len(emulators)

    working_baseline = prune_absent_emulators(
        working_baseline,
        discovered_types,
        seen_timestamp=seen_timestamp,
    )

    post_emulators = working_baseline.get("emulators", {})
    if len(post_emulators) != pre_prune_count:
        updated = True
    else:
        for name, previous_last_seen in pre_prune_snapshot.items():
            state = post_emulators.get(name)
            if state and state.get("last_seen") != previous_last_seen:
                updated = True
                break

    if updated:
        return save_controller_baseline(drive_root, working_baseline, backup=backup)

    return working_baseline


def create_default_baseline() -> Dict[str, Any]:
    now = _now_iso()
    baseline = {
        "version": BASELINE_VERSION,
        "created_at": now,
        "updated_at": now,
        "encoder": _default_encoder_state(),
        "led": _default_led_state(),
        "emulators": {name: _default_emulator_state() for name in DEFAULT_EMULATORS},
        "cascade": _default_cascade_state(),
    }
    return baseline


def load_controller_baseline(
    drive_root: Path,
    *,
    create_if_missing: bool = True,
) -> Dict[str, Any]:
    """Load the controller baseline file, optionally creating a default one."""
    path = _baseline_path(drive_root)

    if not path.exists():
        if not create_if_missing:
            raise ControllerBaselineError(
                f"Baseline file does not exist: {path}"
            )

        baseline = create_default_baseline()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(baseline, f, indent=2)
        baseline = _apply_defaults(baseline)
        manifest_snapshot = _load_drive_manifest(drive_root)
        return migrate_baseline_to_dynamic(baseline, drive_root, manifest_snapshot)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ControllerBaselineError(f"Invalid baseline JSON at {path}: {exc}") from exc

    baseline = _apply_defaults(data)
    manifest_snapshot = _load_drive_manifest(drive_root)
    return migrate_baseline_to_dynamic(baseline, drive_root, manifest_snapshot)


def save_controller_baseline(
    drive_root: Path,
    baseline: Dict[str, Any],
    *,
    backup: bool = False,
    manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist the provided baseline dictionary to disk."""
    path = _baseline_path(drive_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    normalised = _apply_defaults(baseline)
    normalised["updated_at"] = _now_iso()

    manifest_data = manifest or _load_drive_manifest(drive_root)
    sanctioned_paths = manifest_data.get("sanctioned_paths", [])
    if sanctioned_paths and not is_allowed_file(path, drive_root, sanctioned_paths):
        raise ControllerBaselineError(f"Baseline path {path} not sanctioned.")

    if backup and path.exists():
        create_backup(path, drive_root)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalised, f, indent=2)

    try:
        append_audit_log(
            {
                "scope": "controller",
                "action": "baseline_save",
                "target_file": _relative_path_string(path, drive_root),
                "updated_at": normalised.get("updated_at"),
            }
        )
    except Exception:  # pragma: no cover - audit log failures ignored
        pass

    return normalised


def deep_merge(source: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge two dictionaries without mutating the source."""
    result = deepcopy(source)

    for key, value in updates.items():
        if (
            isinstance(value, dict)
            and isinstance(result.get(key), dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)

    return result


def update_controller_baseline(
    drive_root: Path,
    updates: Dict[str, Any],
    *,
    backup: bool = False,
) -> Dict[str, Any]:
    """Merge updates into the baseline and persist them."""
    existing = load_controller_baseline(drive_root)
    merged = deep_merge(existing, updates)
    return save_controller_baseline(drive_root, merged, backup=backup)


def record_cascade_history(
    drive_root: Path,
    entry: Dict[str, Any],
    *,
    backup: bool = False,
) -> Dict[str, Any]:
    """Append an entry to the cascade history."""
    baseline = load_controller_baseline(drive_root)
    history = baseline.setdefault("cascade", {}).setdefault("history", [])
    history.append(entry)
    baseline["cascade"]["history"] = history[-MAX_HISTORY_ENTRIES:]
    baseline["cascade"]["current_job"] = entry
    return save_controller_baseline(drive_root, baseline, backup=backup)


def build_encoder_snapshot(mapping: Dict[str, Any], *, modified_by: Optional[str] = None) -> Dict[str, Any]:
    """Create a canonical snapshot for encoder state."""
    board = mapping.get("board") or {}
    controls = mapping.get("mappings") or {}
    summary = {
        "players": len({key.split(".")[0] for key in controls.keys()}),
        "controls": len(controls),
    }

    snapshot = {
        "board": board,
        "mapping": controls,
        "controls_count": len(controls),
        "last_modified": _now_iso(),
        "modified_by": modified_by,
        "summary": summary,
    }

    return snapshot


def get_baseline_path(drive_root: Path) -> Path:
    """Expose the absolute baseline path for validation."""
    return _baseline_path(drive_root)


def get_cascade_preference(drive_root: Path) -> str:
    """Return the cascade preference stored in the baseline."""
    try:
        baseline = load_controller_baseline(drive_root)
    except ControllerBaselineError:
        return DEFAULT_CASCADE_PREFERENCE
    cascade = baseline.get("cascade") or {}
    preference = cascade.get("preference") or DEFAULT_CASCADE_PREFERENCE
    return str(preference).lower()


def set_cascade_preference(
    drive_root: Path,
    preference: str,
    *,
    backup: bool = False,
) -> None:
    """Persist a new cascade preference into the baseline."""
    normalized = str(preference).lower()
    if normalized not in {"auto", "ask", "manual"}:
        raise ValueError("Cascade preference must be 'auto', 'ask', or 'manual'")

    baseline = load_controller_baseline(drive_root)
    cascade = baseline.setdefault("cascade", {})
    cascade["preference"] = normalized
    baseline["cascade"] = cascade
    save_controller_baseline(drive_root, baseline, backup=backup)
