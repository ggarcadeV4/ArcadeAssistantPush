from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
import xml.etree.ElementTree as ET

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

try:  # Python 3.11+
    import tomllib  # type: ignore
except Exception:  # pragma: no cover
    tomllib = None

try:
    import tomli  # type: ignore
except Exception:  # pragma: no cover
    tomli = None

try:
    import tomli_w  # type: ignore
except Exception:  # pragma: no cover
    tomli_w = None

from .backup import create_backup
from .mame_config_generator import (
    MAMEConfigError,
    generate_mame_config,
    validate_mame_config,
)
from .controller_baseline import (
    ControllerBaselineError,
    DEFAULT_EMULATORS,
    build_encoder_snapshot,
    discover_and_expand_emulators,
    get_baseline_path,
    load_controller_baseline,
    save_controller_baseline,
    update_controller_baseline,
)
from .policies import is_allowed_file
from .emulator_registry import EmulatorRegistry
from . import audit_log

logger = logging.getLogger(__name__)

CASCADE_COMPONENT_LED = "led"
REGISTRY = EmulatorRegistry()

# Note: PCSX2-qt stores configs in user Documents folder, not emulator folder
# We use a special resolver for user-profile paths
DEFAULT_CONFIG_PATHS: Dict[str, Path] = {
    "retroarch": Path("Emulators") / "RetroArch" / "retroarch.cfg",
    "dolphin": Path("Emulators") / "Dolphin Tri-Force" / "User" / "Config" / "Dolphin.ini",
    "pcsx2": Path("~") / "Documents" / "PCSX2" / "inis" / "PCSX2.ini",  # PCSX2-qt uses PCSX2.ini
    "mame": Path("Emulators") / "MAME" / "cfg" / "default.cfg",
    "teknoparrot": Path("Emulators") / "TeknoParrot" / "UserProfiles",
    # Additional emulators
    "rpcs3": Path("LaunchBox") / "Emulators" / "rpcs3" / "config.yml",
    "cemu": Path("LaunchBox") / "Emulators" / "cemu_1.26.2" / "settings.xml",
    "ppsspp": Path("LaunchBox") / "Emulators" / "PPSSPPGold" / "memstick" / "PSP" / "SYSTEM" / "controls.ini",
    "yuzu": Path("LaunchBox") / "Emulators" / "yuzu" / "user" / "config" / "qt-config.ini",
    "duckstation": Path("Emulators") / "Duckstation" / "settings.ini",
    "redream": Path("LaunchBox") / "Emulators" / "redream.x86_64-windows-v1.5.0" / "redream.cfg",
}


def _default_config_hint_for_emulator(emulator: str) -> Optional[Path]:
    if emulator in DEFAULT_CONFIG_PATHS:
        return DEFAULT_CONFIG_PATHS[emulator]
    pattern = REGISTRY.get_pattern(emulator)
    if pattern and pattern.config_path_pattern:
        return Path("emulators") / emulator / pattern.config_path_pattern
    return None
MAX_VALIDATION_LINES = 2000
MAME_CLI_TIMEOUT_SEC = 90


@dataclass(frozen=True)
class RunnerSpec:
    priority: int
    runner: Callable[[str, Dict[str, Any], Path, Dict[str, Any], str, bool], Tuple[str, str]]


def _now_iso() -> str:
    return datetime.now().isoformat()


def _initial_component_state(status: str, message: Optional[str] = None) -> Dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "started_at": None,
        "completed_at": None,
    }


def _component_names(
    emulator_names: Iterable[str],
    *,
    skip_led: bool = False,
    skip_emulators: Optional[Iterable[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    skip_emulators = set(skip_emulators or [])
    components: Dict[str, Dict[str, Any]] = {}

    if skip_led:
        components[CASCADE_COMPONENT_LED] = _initial_component_state(
            "skipped", "LED cascade skipped by request"
        )
    else:
        components[CASCADE_COMPONENT_LED] = _initial_component_state("queued")

    for emulator in emulator_names:
        if emulator in skip_emulators:
            components[emulator] = _initial_component_state(
                "skipped", f"{emulator} cascade skipped by request"
            )
        else:
            components[emulator] = _initial_component_state("queued")

    return components


def enqueue_cascade_job(
    drive_root: Path,
    *,
    requested_by: Optional[str],
    metadata: Optional[Dict[str, Any]] = None,
    skip_led: bool = False,
    skip_emulators: Optional[Iterable[str]] = None,
    backup: bool = False,
    emulator_names: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Create a cascade job entry and persist it to the baseline."""
    job_id = str(uuid.uuid4())
    baseline = load_controller_baseline(drive_root)
    available = (
        list(emulator_names)
        if emulator_names is not None
        else sorted((baseline.get("emulators") or {}).keys())
    )
    if not available:
        available = list(DEFAULT_EMULATORS)
    components = _component_names(
        available,
        skip_led=skip_led,
        skip_emulators=skip_emulators,
    )

    job_record: Dict[str, Any] = {
        "job_id": job_id,
        "requested_at": _now_iso(),
        "requested_by": requested_by,
        "status": "queued",
        "summary": {
            "success": 0,
            "failed": 0,
            "skipped": len([c for c in components.values() if c["status"] == "skipped"]),
            "pending": len([c for c in components.values() if c["status"] == "queued"]),
            "total": len(components),
        },
        "components": components,
        "options": {
            "skip_led": skip_led,
            "skip_emulators": list(skip_emulators or []),
        },
        "metadata": metadata or {},
    }

    cascade_state = baseline.setdefault("cascade", {})

    history: List[Dict[str, Any]] = cascade_state.get("history", [])
    if cascade_state.get("current_job"):
        history.append(cascade_state["current_job"])

    cascade_state["current_job"] = job_record
    cascade_state["status"] = "queued"
    cascade_state["history"] = history[-10:]

    baseline["cascade"] = cascade_state
    save_controller_baseline(drive_root, baseline, backup=backup)

    return job_record


def update_job_status(
    drive_root: Path,
    job_id: str,
    *,
    status: str,
    message: Optional[str] = None,
    summary: Optional[Dict[str, Any]] = None,
    backup: bool = False,
) -> Dict[str, Any]:
    """Update top-level job status."""
    baseline = load_controller_baseline(drive_root)
    cascade_state = baseline.get("cascade") or {}
    job = cascade_state.get("current_job")

    if not job or job.get("job_id") != job_id:
        raise ControllerBaselineError(f"Cascade job {job_id} not found")

    job["status"] = status
    if message:
        job["message"] = message

    if summary:
        job["summary"].update(summary)

    if status in {"completed", "failed", "degraded"}:
        job["completed_at"] = _now_iso()

    cascade_state["current_job"] = job
    cascade_state["status"] = status

    baseline["cascade"] = cascade_state
    return save_controller_baseline(drive_root, baseline, backup=backup)


def update_component_status(
    drive_root: Path,
    job_id: str,
    component: str,
    *,
    status: str,
    message: Optional[str] = None,
    backup: bool = False,
) -> Dict[str, Any]:
    """Update the status for a specific cascade component."""
    baseline = load_controller_baseline(drive_root)
    cascade_state = baseline.get("cascade") or {}
    job = cascade_state.get("current_job")

    if not job or job.get("job_id") != job_id:
        raise ControllerBaselineError(f"Cascade job {job_id} not found")

    components = job.get("components") or {}
    if component not in components:
        raise ControllerBaselineError(f"Cascade component '{component}' not tracked in job {job_id}")

    component_state = components[component]
    previous_status = component_state.get("status")

    component_state["status"] = status
    component_state["message"] = message

    timestamp = _now_iso()
    if previous_status in {"queued", "pending"} and status not in {"queued", "pending"}:
        component_state["completed_at"] = timestamp
    elif status == "running" and component_state.get("started_at") is None:
        component_state["started_at"] = timestamp

    components[component] = component_state
    job["components"] = components

    job_summary = job.get("summary") or {}
    job_summary["success"] = len(
        [info for info in components.values() if info.get("status") == "completed"]
    )
    job_summary["failed"] = len(
        [info for info in components.values() if info.get("status") == "failed"]
    )
    job_summary["pending"] = len(
        [
            info
            for info in components.values()
            if info.get("status") in {"queued", "pending", "running"}
        ]
    )
    job_summary["skipped"] = len(
        [info for info in components.values() if info.get("status") == "skipped"]
    )
    job_summary["total"] = len(components)
    job["summary"] = job_summary

    cascade_state["current_job"] = job
    baseline["cascade"] = cascade_state
    return save_controller_baseline(drive_root, baseline, backup=backup)


def get_cascade_status(drive_root: Path) -> Dict[str, Any]:
    baseline = load_controller_baseline(drive_root)
    return baseline.get("cascade", {})


def _flatten_mapping(mapping: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    for key, value in mapping.items():
        scoped_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flat.update(_flatten_mapping(value, scoped_key))
        else:
            flat[scoped_key] = value
    return flat


def _resolve_config_path(drive_root: Path, path_value: Optional[str]) -> Optional[Path]:
    if not path_value:
        return None
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = drive_root / candidate
    return candidate


def _relative_path_string(path: Path, drive_root: Path) -> str:
    try:
        return path.relative_to(drive_root).as_posix()
    except ValueError:
        return str(path)


def _format_value(value: Any, *, quote_strings: bool) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    value_str = str(value)
    if quote_strings and not (value_str.startswith('"') and value_str.endswith('"')):
        escaped = value_str.replace('"', '\\"')
        return f'"{escaped}"'
    return value_str


def _apply_key_value_patch(
    config_path: Path,
    updates: Dict[str, Any],
    *,
    quote_strings: bool,
    backup_on_write: bool,
    drive_root: Path,
) -> None:
    updates = {k: _format_value(v, quote_strings=quote_strings) for k, v in updates.items()}

    lines: List[str] = []
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()

    updated_lines = list(lines)
    for key, value in updates.items():
        replacement = f"{key} = {value}"
        found = False
        for idx, line in enumerate(updated_lines):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", ";")):
                continue
            if "=" not in line:
                continue
            existing_key = line.split("=", 1)[0].strip()
            if existing_key == key:
                updated_lines[idx] = replacement
                found = True
                break
        if not found:
            updated_lines.append(replacement)

    new_content = "\n".join(updated_lines) + ("\n" if updated_lines else "")

    if config_path.exists() and backup_on_write:
        create_backup(config_path, drive_root)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as handle:
        handle.write(new_content)


def _split_config_path(key: str) -> List[str]:
    candidate = key.replace("\\", "/")
    segments = [segment for segment in candidate.split("/") if segment]
    if len(segments) <= 1 and "." in candidate and "/" not in candidate:
        segments = [segment for segment in candidate.split(".") if segment]
    return segments or [key]


def _apply_ini_mapping(
    config_path: Path,
    mapping: Dict[str, Any],
    *,
    drive_root: Path,
    backup_on_write: bool,
    quote_strings: bool,
) -> None:
    flat = _flatten_mapping(mapping)
    _apply_key_value_patch(
        config_path,
        flat,
        quote_strings=quote_strings,
        backup_on_write=backup_on_write,
        drive_root=drive_root,
    )


def _set_nested_dict_value(container: Dict[str, Any], key_path: List[str], value: Any) -> None:
    node: Dict[str, Any] = container
    for part in key_path[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[key_path[-1]] = value


def _apply_yaml_mapping(
    config_path: Path,
    mapping: Dict[str, Any],
    *,
    drive_root: Path,
    backup_on_write: bool,
) -> None:
    if yaml is None:
        logger.warning(
            "PyYAML not available; falling back to INI writer for %s",
            config_path,
        )
        _apply_ini_mapping(
            config_path,
            mapping,
            drive_root=drive_root,
            backup_on_write=backup_on_write,
            quote_strings=False,
        )
        return

    data: Dict[str, Any] = {}
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
                if isinstance(loaded, dict):
                    data = loaded
                else:
                    logger.warning("Existing YAML at %s is not a dict; replacing.", config_path)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to read YAML config %s: %s", config_path, exc)

    updates = _flatten_mapping(mapping)
    for key, value in updates.items():
        path = _split_config_path(key)
        _set_nested_dict_value(data, path, value)

    if config_path.exists() and backup_on_write:
        create_backup(config_path, drive_root)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False)


def _apply_json_mapping(
    config_path: Path,
    mapping: Dict[str, Any],
    *,
    drive_root: Path,
    backup_on_write: bool,
) -> None:
    data: Dict[str, Any] = {}
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
                if isinstance(loaded, dict):
                    data = loaded
                else:
                    logger.warning("JSON config %s is not an object; replacing.", config_path)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to read JSON config %s: %s", config_path, exc)

    updates = _flatten_mapping(mapping)
    for key, value in updates.items():
        path = _split_config_path(key)
        _set_nested_dict_value(data, path, value)

    if config_path.exists() and backup_on_write:
        create_backup(config_path, drive_root)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def _find_or_create_child(node: ET.Element, tag: str) -> ET.Element:
    for child in node:
        if child.tag == tag:
            return child
    return ET.SubElement(node, tag)


def _apply_xml_mapping(
    config_path: Path,
    mapping: Dict[str, Any],
    *,
    drive_root: Path,
    backup_on_write: bool,
) -> None:
    root: ET.Element
    tree: ET.ElementTree
    if config_path.exists():
        try:
            tree = ET.parse(config_path)
            root = tree.getroot()
        except ET.ParseError:
            root = ET.Element("config")
            tree = ET.ElementTree(root)
    else:
        root = ET.Element("config")
        tree = ET.ElementTree(root)

    updates = _flatten_mapping(mapping)
    for key, value in updates.items():
        path = _split_config_path(key)
        node = root
        for segment in path:
            node = _find_or_create_child(node, segment)
        node.text = str(value)

    if config_path.exists() and backup_on_write:
        create_backup(config_path, drive_root)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(config_path, encoding="utf-8", xml_declaration=True)


def _apply_toml_mapping(
    config_path: Path,
    mapping: Dict[str, Any],
    *,
    drive_root: Path,
    backup_on_write: bool,
) -> None:
    if tomllib is None and tomli is None:
        logger.warning(
            "tomllib/tomli unavailable; falling back to INI writer for %s",
            config_path,
        )
        _apply_ini_mapping(
            config_path,
            mapping,
            drive_root=drive_root,
            backup_on_write=backup_on_write,
            quote_strings=True,
        )
        return

    if tomli_w is None:
        logger.warning(
            "tomli_w not available; falling back to INI writer for %s",
            config_path,
        )
        _apply_ini_mapping(
            config_path,
            mapping,
            drive_root=drive_root,
            backup_on_write=backup_on_write,
            quote_strings=True,
        )
        return

    data: Dict[str, Any] = {}
    if config_path.exists():
        try:
            with open(config_path, "rb") as handle:
                if tomllib is not None:
                    loaded = tomllib.load(handle)
                else:
                    loaded = tomli.load(handle)  # type: ignore[arg-type]
                if isinstance(loaded, dict):
                    data = loaded
                else:
                    logger.warning("TOML config %s is not a table; replacing.", config_path)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to read TOML config %s: %s", config_path, exc)

    updates = _flatten_mapping(mapping)
    for key, value in updates.items():
        path = _split_config_path(key)
        _set_nested_dict_value(data, path, value)

    if config_path.exists() and backup_on_write:
        create_backup(config_path, drive_root)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "wb") as handle:
        tomli_w.dump(data, handle)  # type: ignore[arg-type]


def _ini_writer(
    config_path: Path,
    mapping: Dict[str, Any],
    *,
    drive_root: Path,
    backup_on_write: bool,
) -> None:
    _apply_ini_mapping(
        config_path,
        mapping,
        drive_root=drive_root,
        backup_on_write=backup_on_write,
        quote_strings=False,
    )


def _cfg_writer(
    config_path: Path,
    mapping: Dict[str, Any],
    *,
    drive_root: Path,
    backup_on_write: bool,
) -> None:
    _apply_ini_mapping(
        config_path,
        mapping,
        drive_root=drive_root,
        backup_on_write=backup_on_write,
        quote_strings=True,
    )


def _normalize_config_format(emulator: str, format_hint: Optional[str]) -> str:
    if format_hint:
        lowered = format_hint.lower()
        if lowered in {"yml"}:
            return "yaml"
        return lowered
    if emulator == "retroarch":
        return "cfg"
    return "ini"


def _resolve_config_format(emulator: str, emulator_state: Dict[str, Any]) -> str:
    hint = emulator_state.get("config_format")
    if not hint:
        pattern = REGISTRY.get_pattern(emulator)
        hint = pattern.config_format if pattern else None
    return _normalize_config_format(emulator, hint)



def _update_led_baseline(
    drive_root: Path,
    *,
    status: str,
    message: Optional[str],
    job_id: str,
    backup: bool,
) -> Dict[str, Any]:
    return update_controller_baseline(
        drive_root,
        {
            "led": {
                "status": status,
                "message": message,
                "last_synced": _now_iso(),
                "last_job_id": job_id,
            }
        },
        backup=backup,
    )


def _update_emulator_baseline(
    drive_root: Path,
    emulator: str,
    *,
    status: str,
    message: Optional[str],
    job_id: str,
    mapping: Optional[Dict[str, Any]],
    config_path: Optional[Path],
    backup: bool,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "emulators": {
            emulator: {
                "status": status,
                "message": message,
                "last_synced": _now_iso(),
                "last_job_id": job_id,
            }
        }
    }

    if mapping is not None:
        payload["emulators"][emulator]["mapping"] = mapping
    if config_path is not None:
        payload["emulators"][emulator]["config_path"] = _relative_path_string(config_path, drive_root)

    result = update_controller_baseline(drive_root, payload, backup=backup)
    try:
        audit_log.append(
            {
                "scope": "controller_cascade",
                "action": "cascade_component_result",  # one entry per emulator component applied in a cascade
                "emulator": emulator,
                "status": status,
                "job_id": job_id,
                "config_path": _relative_path_string(config_path, drive_root) if config_path else None,
                "mapping_keys": list(mapping.keys()) if mapping else [],
            }
        )
    except Exception:  # pragma: no cover
        pass

    return result


def _apply_mame_xml_config(
    config_path: Path,
    controls_json: Dict[str, Any],
    *,
    drive_root: Path,
    backup_on_write: bool,
) -> str:
    """Generate MAME default.cfg XML from controls.json and write it.

    Uses the same ``generate_mame_config`` / ``validate_mame_config`` pipeline
    as the legacy ``/learn-wizard/save`` endpoint so that both code paths
    produce identical XML output targeting ``Emulators/MAME/cfg/default.cfg``.
    """
    xml_content = generate_mame_config(controls_json)

    validation_errors = validate_mame_config(xml_content)
    if validation_errors:
        raise MAMEConfigError(
            f"Generated MAME XML failed validation: {validation_errors[:3]}"
        )

    config_path.parent.mkdir(parents=True, exist_ok=True)
    if backup_on_write and config_path.exists():
        create_backup(config_path, drive_root)

    with open(config_path, "w", encoding="utf-8") as handle:
        handle.write(xml_content)

    return xml_content


def _validate_mame_cli(executable: Path, rom_filter: Iterable[str]) -> Tuple[bool, str]:
    if not executable.exists():
        return False, f"MAME executable missing at {executable}"

    if not os.access(executable, os.X_OK):
        return False, f"MAME executable not executable: {executable}"

    command = [str(executable), "-listxml"]
    captured_stdout: deque[str] = deque(maxlen=MAX_VALIDATION_LINES)
    stderr_capture = ""
    start_time = time.time()

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        return False, f"Failed to launch MAME CLI: {exc}"

    try:
        assert process.stdout is not None
        for idx, line in enumerate(process.stdout):
            if idx < MAX_VALIDATION_LINES:
                captured_stdout.append(line)
        if process.stderr:
            stderr_capture = process.stderr.read()
        return_code = process.wait(timeout=MAME_CLI_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        process.kill()
        return False, f"MAME CLI timed out after {MAME_CLI_TIMEOUT_SEC} seconds"
    finally:
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()

    duration = time.time() - start_time
    excerpt = "".join(captured_stdout)

    if return_code != 0:
        truncated = excerpt.splitlines()[:10]
        snippet = " | ".join(truncated)
        message = stderr_capture.strip() or f"MAME CLI exited with code {return_code}"
        if snippet:
            message = f"{message} (excerpt: {snippet[:200]})"
        return False, message

    if rom_filter:
        missing_roms = [rom for rom in rom_filter if rom and rom not in excerpt]
        if missing_roms:
            preview = ", ".join(missing_roms[:5])
            return False, f"MAME CLI ok but ROMs missing from listxml: {preview}"

    return True, f"MAME CLI validated in {duration:.1f}s"


def _run_led_step(
    drive_root: Path,
    manifest: Dict[str, Any],
    job_id: str,
    *,
    backup: bool,
) -> Tuple[str, str]:
    baseline = load_controller_baseline(drive_root)
    led_state = baseline.get("led") or {}

    exe_path = drive_root / "LED" / "Blinky.exe"
    sanctioned_paths: List[str] = manifest.get("sanctioned_paths", [])

    if not is_allowed_file(exe_path, drive_root, sanctioned_paths):
        message = f"LED executable not permitted by manifest: {exe_path}"
        _update_led_baseline(drive_root, status="failed", message=message, job_id=job_id, backup=backup)
        return "failed", message

    if not exe_path.exists():
        message = f"LED Blinky executable not found at {exe_path}"
        _update_led_baseline(drive_root, status="skipped", message=message, job_id=job_id, backup=backup)
        return "skipped", message

    if platform.system().lower() != "windows":
        message = "LED cascade mocked on non-Windows host."
        _update_led_baseline(
            drive_root,
            status="completed",
            message=message,
            job_id=job_id,
            backup=backup,
        )
        return "completed", message

    baseline_snapshot = build_encoder_snapshot(
        baseline.get("encoder", {}),
        modified_by=led_state.get("modified_by"),
    )
    update_controller_baseline(
        drive_root,
        {"encoder": baseline_snapshot},
        backup=backup,
    )

    command = [
        str(exe_path),
        "--apply-baseline",
        str(get_baseline_path(drive_root)),
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        message = completed.stdout.strip() or "LED cascade applied successfully."
        status = "completed"
    except subprocess.TimeoutExpired:
        message = "LED cascade timed out after 60 seconds."
        status = "failed"
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or f"LED cascade failed: {exc.returncode}"
        status = "failed"
    except OSError as exc:
        message = f"LED cascade invocation failed: {exc}"
        status = "failed"

    _update_led_baseline(drive_root, status=status, message=message, job_id=job_id, backup=backup)
    return status, message


def _run_mame_step(
    drive_root: Path,
    manifest: Dict[str, Any],
    job_id: str,
    *,
    backup: bool,
) -> Tuple[str, str]:
    controls_path = drive_root / "config" / "mappings" / "controls.json"
    if not controls_path.exists():
        message = "controls.json not found; skipping MAME cascade."
        _update_emulator_baseline(
            drive_root,
            "mame",
            status="skipped",
            message=message,
            job_id=job_id,
            mapping=None,
            config_path=None,
            backup=backup,
        )
        return "skipped", message

    try:
        with open(controls_path, "r", encoding="utf-8") as fh:
            controls_json = json.load(fh)
    except Exception as exc:
        message = f"Failed to read controls.json: {exc}"
        _update_emulator_baseline(
            drive_root,
            "mame",
            status="failed",
            message=message,
            job_id=job_id,
            mapping=None,
            config_path=None,
            backup=backup,
        )
        return "failed", message

    if not controls_json.get("mappings"):
        message = "controls.json has no mappings; skipping MAME cascade."
        _update_emulator_baseline(
            drive_root,
            "mame",
            status="skipped",
            message=message,
            job_id=job_id,
            mapping=None,
            config_path=None,
            backup=backup,
        )
        return "skipped", message

    mame_manifest = manifest.get("emulators", {}).get("mame", {}) or {}
    baseline = load_controller_baseline(drive_root)
    emulator_state = baseline.get("emulators", {}).get("mame", {}) or {}
    config_override = emulator_state.get("config_path")
    config_hint = (
        config_override
        or mame_manifest.get("cfg")
        or mame_manifest.get("config")
        or DEFAULT_CONFIG_PATHS["mame"]
    )
    config_path = _resolve_config_path(drive_root, config_hint)
    sanctioned_paths: List[str] = manifest.get("sanctioned_paths", [])

    if config_path is None or not is_allowed_file(config_path, drive_root, sanctioned_paths):
        message = f"MAME config path not permitted: {config_hint}"
        _update_emulator_baseline(
            drive_root,
            "mame",
            status="failed",
            message=message,
            job_id=job_id,
            mapping=controls_json.get("mappings"),
            config_path=None,
            backup=backup,
        )
        return "failed", message

    try:
        _apply_mame_xml_config(
            config_path,
            controls_json,
            drive_root=drive_root,
            backup_on_write=backup,
        )
        write_message = f"MAME XML config written to {config_path.name}."
        status = "completed"
    except (MAMEConfigError, Exception) as exc:
        logger.exception("Failed to generate/write MAME XML config: %s", exc)
        message = f"MAME XML config generation failed: {exc}"
        _update_emulator_baseline(
            drive_root,
            "mame",
            status="failed",
            message=message,
            job_id=job_id,
            mapping=controls_json.get("mappings"),
            config_path=config_path,
            backup=backup,
        )
        return "failed", message

    executable_hint = (
        mame_manifest.get("executable")
        or mame_manifest.get("exe")
        or mame_manifest.get("binary")
        or (Path("emulators") / "mame" / "mame.exe")
    )
    executable_path = _resolve_config_path(drive_root, executable_hint)
    if executable_path is None or not is_allowed_file(executable_path, drive_root, sanctioned_paths):
        message = f"MAME executable not permitted: {executable_hint}"
        _update_emulator_baseline(
            drive_root,
            "mame",
            status="failed",
            message=message,
            job_id=job_id,
            mapping=controls_json.get("mappings"),
            config_path=config_path,
            backup=backup,
        )
        return "failed", message

    rom_filter = emulator_state.get("roms") or []
    valid, cli_message = _validate_mame_cli(executable_path, rom_filter)
    final_status = "completed" if valid else "failed"
    message = f"{write_message} {cli_message}".strip()

    _update_emulator_baseline(
        drive_root,
        "mame",
        status=final_status,
        message=message,
        job_id=job_id,
        mapping=controls_json.get("mappings"),
        config_path=config_path,
        backup=backup,
    )

    return final_status, message


def _run_emulator_step(
    emulator: str,
    *,
    drive_root: Path,
    manifest: Dict[str, Any],
    job_id: str,
    backup: bool,
) -> Tuple[str, str]:
    baseline = load_controller_baseline(drive_root)
    emulator_state = baseline.get("emulators", {}).get(emulator, {})
    mapping = emulator_state.get("mapping") or {}

    if not mapping:
        message = "No mapping provided; nothing to apply."
        _update_emulator_baseline(
            drive_root,
            emulator,
            status="skipped",
            message=message,
            job_id=job_id,
            mapping=None,
            config_path=None,
            backup=backup,
        )
        return "skipped", message

    config_override = emulator_state.get("config_path")
    config_path = _resolve_config_path(
        drive_root,
        config_override or _default_config_hint_for_emulator(emulator),
    )

    if config_path is None:
        message = "Config path not defined for emulator."
        _update_emulator_baseline(
            drive_root,
            emulator,
            status="failed",
            message=message,
            job_id=job_id,
            mapping=mapping,
            config_path=None,
            backup=backup,
        )
        return "failed", message

    sanctioned_paths: List[str] = manifest.get("sanctioned_paths", [])
    if not is_allowed_file(config_path, drive_root, sanctioned_paths):
        message = f"Config path not permitted by manifest: {config_path}"
        _update_emulator_baseline(
            drive_root,
            emulator,
            status="failed",
            message=message,
            job_id=job_id,
            mapping=mapping,
            config_path=config_path,
            backup=backup,
        )
        return "failed", message

    format_hint = _resolve_config_format(emulator, emulator_state)
    writer = CONFIG_WRITERS.get(format_hint, _ini_writer)
    flat_mapping = _flatten_mapping(mapping)
    write_count = len(flat_mapping)
    try:
        writer(
            config_path,
            mapping=mapping,
            drive_root=drive_root,
            backup_on_write=backup,
        )
        message = f"{emulator} config updated ({write_count} keys, format={format_hint})."
        status = "completed"
    except Exception as exc:
        logger.exception("Failed to update %s config: %s", emulator, exc)
        message = f"{emulator} config update failed: {exc}"
        status = "failed"

    _update_emulator_baseline(
        drive_root,
        emulator,
        status=status,
        message=message,
        job_id=job_id,
        mapping=mapping,
        config_path=config_path,
        backup=backup,
    )

    return status, message


def _led_runner(
    component: str,
    component_state: Dict[str, Any],
    drive_root: Path,
    manifest: Dict[str, Any],
    job_id: str,
    backup: bool,
) -> Tuple[str, str]:
    return _run_led_step(drive_root, manifest, job_id, backup=backup)


def _mame_runner(
    component: str,
    component_state: Dict[str, Any],
    drive_root: Path,
    manifest: Dict[str, Any],
    job_id: str,
    backup: bool,
) -> Tuple[str, str]:
    return _run_mame_step(drive_root, manifest, job_id, backup=backup)


def _generic_emulator_runner(
    component: str,
    component_state: Dict[str, Any],
    drive_root: Path,
    manifest: Dict[str, Any],
    job_id: str,
    backup: bool,
) -> Tuple[str, str]:
    return _run_emulator_step(
        component,
        drive_root=drive_root,
        manifest=manifest,
        job_id=job_id,
        backup=backup,
    )


def _run_teknoparrot_step(
    drive_root: Path,
    manifest: Dict[str, Any],
    job_id: str,
    *,
    backup: bool,
) -> Tuple[str, str]:
    """Run TeknoParrot cascade step.
    
    Unlike other emulators, TeknoParrot uses XML UserProfiles.
    This step uses the teknoparrot_config_generator to map arcade
    panel controls to TP input bindings.
    """
    baseline = load_controller_baseline(drive_root)
    emulator_state = baseline.get("emulators", {}).get("teknoparrot", {}) or {}
    
    # Get the canonical mapping from baseline
    mapping = emulator_state.get("mapping") or {}
    
    if not mapping:
        message = "No TeknoParrot mapping provided; skipping."
        _update_emulator_baseline(
            drive_root,
            "teknoparrot",
            status="skipped",
            message=message,
            job_id=job_id,
            mapping=None,
            config_path=None,
            backup=backup,
        )
        return "skipped", message
    
    # Get profile path from baseline or default
    config_override = emulator_state.get("config_path")
    profiles_dir = _resolve_config_path(
        drive_root,
        config_override or DEFAULT_CONFIG_PATHS.get("teknoparrot"),
    )
    
    if profiles_dir is None or not profiles_dir.exists():
        message = f"TeknoParrot UserProfiles directory not found: {profiles_dir}"
        _update_emulator_baseline(
            drive_root,
            "teknoparrot",
            status="skipped",
            message=message,
            job_id=job_id,
            mapping=mapping,
            config_path=None,
            backup=backup,
        )
        return "skipped", message
    
    sanctioned_paths: List[str] = manifest.get("sanctioned_paths", [])
    if not is_allowed_file(profiles_dir, drive_root, sanctioned_paths):
        message = f"TeknoParrot path not permitted: {profiles_dir}"
        _update_emulator_baseline(
            drive_root,
            "teknoparrot",
            status="failed",
            message=message,
            job_id=job_id,
            mapping=mapping,
            config_path=profiles_dir,
            backup=backup,
        )
        return "failed", message
    
    # For now, we just mark TeknoParrot as ready; actual XML writes
    # happen through Console Wizard's preview/apply flow.
    # The cascade registers TP as available and stores the mapping.
    message = f"TeknoParrot cascade registered ({len(mapping)} controls mapped)."
    status = "completed"
    
    _update_emulator_baseline(
        drive_root,
        "teknoparrot",
        status=status,
        message=message,
        job_id=job_id,
        mapping=mapping,
        config_path=profiles_dir,
        backup=backup,
    )
    
    return status, message


def _teknoparrot_runner(
    component: str,
    component_state: Dict[str, Any],
    drive_root: Path,
    manifest: Dict[str, Any],
    job_id: str,
    backup: bool,
) -> Tuple[str, str]:
    return _run_teknoparrot_step(drive_root, manifest, job_id, backup=backup)


RUNNER_REGISTRY: Dict[str, RunnerSpec] = {
    CASCADE_COMPONENT_LED: RunnerSpec(priority=0, runner=_led_runner),
    "mame": RunnerSpec(priority=10, runner=_mame_runner),
    "retroarch": RunnerSpec(priority=20, runner=_generic_emulator_runner),
    "dolphin": RunnerSpec(priority=30, runner=_generic_emulator_runner),
    "pcsx2": RunnerSpec(priority=40, runner=_generic_emulator_runner),
    "teknoparrot": RunnerSpec(priority=45, runner=_teknoparrot_runner),
}

CONFIG_WRITERS: Dict[str, Callable[..., None]] = {
    "ini": _ini_writer,
    "cfg": _cfg_writer,
    "yaml": _apply_yaml_mapping,
    "yml": _apply_yaml_mapping,
    "xml": _apply_xml_mapping,
    "toml": _apply_toml_mapping,
    "json": _apply_json_mapping,
}


def _get_runner_spec(component: str) -> RunnerSpec:
    return RUNNER_REGISTRY.get(component, RunnerSpec(priority=50, runner=_generic_emulator_runner))


def run_cascade_job(
    drive_root: Path,
    manifest: Dict[str, Any],
    job_id: str,
    *,
    backup: bool = False,
) -> None:
    try:
        baseline = discover_and_expand_emulators(drive_root, manifest, backup=backup)
        update_job_status(
            drive_root,
            job_id,
            status="running",
            message="Cascade orchestration started",
            backup=backup,
        )

        cascade_state = baseline.get("cascade") or {}
        job = cascade_state.get("current_job") or {}
        components = job.get("components") or {}

        if not job or job.get("job_id") != job_id:
            raise ControllerBaselineError(f"Cascade job {job_id} not found")

        available_emulators = sorted((baseline.get("emulators") or {}).keys()) or list(
            DEFAULT_EMULATORS
        )
        component_updated = False
        for emulator_name in available_emulators:
            if emulator_name not in components:
                components[emulator_name] = _initial_component_state("queued")
                component_updated = True
        if CASCADE_COMPONENT_LED not in components:
            components[CASCADE_COMPONENT_LED] = _initial_component_state("queued")
            component_updated = True

        if component_updated:
            job["components"] = components
            cascade_state["current_job"] = job
            baseline["cascade"] = cascade_state
            save_controller_baseline(drive_root, baseline, backup=backup)

        results: List[str] = []
        has_failure = False
        summary_counts = {"success": 0, "failed": 0, "skipped": 0}

        ordered_components = sorted(
            components.items(),
            key=lambda item: _get_runner_spec(item[0]).priority,
        )

        for component_name, component_state in ordered_components:
            if component_state.get("status") == "skipped":
                results.append(f"{component_name}=skipped")
                summary_counts["skipped"] += 1
                continue

            spec = _get_runner_spec(component_name)
            update_component_status(
                drive_root,
                job_id,
                component_name,
                status="running",
                message=f"Applying {component_name} cascade",
                backup=backup,
            )
            status, message = spec.runner(
                component_name,
                component_state,
                drive_root,
                manifest,
                job_id,
                backup,
            )
            update_component_status(
                drive_root,
                job_id,
                component_name,
                status=status,
                message=message,
                backup=backup,
            )
            results.append(f"{component_name}={status}")
            has_failure = has_failure or status == "failed"
            if status == "failed":
                summary_counts["failed"] += 1
            elif status == "skipped":
                summary_counts["skipped"] += 1
            else:
                summary_counts["success"] += 1

        final_status = "degraded" if has_failure else "completed"
        total_components = len(components)
        summary_payload = {
            "success": summary_counts["success"],
            "failed": summary_counts["failed"],
            "skipped": summary_counts["skipped"],
            "pending": max(
                0,
                total_components
                - (
                    summary_counts["success"]
                    + summary_counts["failed"]
                    + summary_counts["skipped"]
                ),
            ),
            "total": total_components,
        }
        update_job_status(
            drive_root,
            job_id,
            status=final_status,
            message="; ".join(results),
            summary=summary_payload,
            backup=backup,
        )
    except ControllerBaselineError as exc:
        logger.error("Cascade job %s failed: %s", job_id, exc)
        update_job_status(
            drive_root,
            job_id,
            status="failed",
            message=str(exc),
            backup=backup,
        )
    except Exception as exc:
        logger.exception("Cascade job %s encountered an error", job_id)
        update_job_status(
            drive_root,
            job_id,
            status="failed",
            message=str(exc),
            backup=backup,
        )
