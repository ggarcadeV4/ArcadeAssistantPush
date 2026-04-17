import sys
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime, timezone
import os

from backend.constants.sanctioned_paths import DEFAULT_SANCTIONED_PATHS
from backend.constants.drive_root import get_drive_root_or_none, get_manifest_path, paths_equivalent

try:
    import yaml
except Exception as e:  # pragma: no cover
    raise RuntimeError("PyYAML is required for manifest validation") from e


MANIFEST_REL_PATH = Path("docs/config/operational_sequence_manifest.yaml")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _manifest_path() -> Path:
    root = _repo_root()
    return (root / MANIFEST_REL_PATH).resolve()


def load_manifest() -> Dict[str, Any]:
    path = _manifest_path()
    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("Manifest root must be a mapping")
    return data


def validate_manifest(data: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    if "global_invariants" not in data:
        errors.append("Missing required key: global_invariants")
    elif not isinstance(data["global_invariants"], list) or not all(isinstance(x, str) for x in data["global_invariants"]):
        errors.append("global_invariants must be a list of strings")

    if "paths" not in data:
        errors.append("Missing required key: paths")
    elif not isinstance(data["paths"], dict):
        errors.append("paths must be a mapping")
    else:
        for k, v in data["paths"].items():
            if not isinstance(k, str):
                errors.append("paths keys must be strings")
                break
            if not isinstance(v, (str, list)):
                errors.append(f"paths[{k}] must be string or list")
            if isinstance(v, list) and not all(isinstance(x, str) for x in v):
                errors.append(f"paths[{k}] list must contain strings")

    if "startup_sequence" not in data:
        errors.append("Missing required key: startup_sequence")
    else:
        ss = data["startup_sequence"]
        if isinstance(ss, list):
            for i, step in enumerate(ss):
                if not isinstance(step, (dict, str)):
                    errors.append(f"startup_sequence[{i}] must be mapping or string")
        elif isinstance(ss, dict):
            order = ss.get("order")
            if not isinstance(order, list) or not all(isinstance(x, str) for x in order):
                errors.append("startup_sequence.order must be a list of strings")
            # Optional phase keys
            for phase_key in ("backend:init", "gateway:init", "frontend:init"):
                if phase_key in ss and not (
                    isinstance(ss[phase_key], list) and all(isinstance(x, str) for x in ss[phase_key])
                ):
                    errors.append(f"startup_sequence.{phase_key} must be a list of strings if present")
        else:
            errors.append("startup_sequence must be a list or mapping")

    # Semantic checks: AA_DRIVE_ROOT existence and /.aa/manifest.json presence
    # These are warnings, not fatal errors - startup_manager.py handles them by blocking writes
    configured_root = get_drive_root_or_none()
    if configured_root is None:
        # Don't add to errors - allow startup with writes disabled (handled by startup_manager)
        print("WARNING: AA_DRIVE_ROOT environment variable is not set")
    else:
        root_path = Path(configured_root)
        if not root_path.exists() or not root_path.is_dir():
            print(f"WARNING: Configured root does not exist or is not a directory: {root_path}")
        manifest_json = get_manifest_path(root_path)
        if not manifest_json.exists():
            print(f"WARNING: .aa/manifest.json not found at {manifest_json}")
        else:
            manifest_root = ""
            try:
                import json as _json
                with open(manifest_json, "r", encoding="utf-8") as handle:
                    manifest_payload = _json.load(handle)
                if isinstance(manifest_payload, dict):
                    manifest_root = str(manifest_payload.get("drive_root") or "").strip()
            except Exception:
                manifest_root = ""
            if manifest_root and not paths_equivalent(manifest_root, root_path):
                print(f"WARNING: manifest drive_root ({manifest_root}) does not match configured root ({root_path})")

    # Invariant presence checks (string match)
    required_invariants = [
        "AA_DRIVE_ROOT must exist and be validated before any route registration.",
        "Gateway performs no direct file I/O; all writes proxy to FastAPI /config/*.",
        "All writes follow Preview  Apply  Restore.",
        "When /.aa/manifest.json has sanctioned_paths=[], all writes are rejected (read-only mode).",
        "CORS with credentials must enumerate origins (no '*'); allow headers: x-device-id, x-scope, content-type, authorization.",
        "Missing/disabled AI keys return 501 NOT_CONFIGURED (never 500).",
        "Structured logs include request_id, x-device-id, x-panel, and backup_path when applicable.",
        "Threads/tasks are joined/cancelled on shutdown; no orphaned workers.",
        "Frontend panels are isolated with ErrorBoundaries; errors log to /logs/frontend_errors.jsonl.",
    ]
    if isinstance(data.get("global_invariants"), list):
        inv = set(data["global_invariants"])
        for req in required_invariants:
            if req not in inv:
                errors.append(f"Missing required invariant: {req}")

    return errors


def _bootstrap_manifest_if_allowed(errors: List[str]) -> bool:
    """Create or repair <AA_DRIVE_ROOT>/.aa/manifest.json when AA_DEV_ALLOW_BOOTSTRAP=1.

    Returns True if a bootstrap/repair occurred and errors can be ignored.
    """
    import os
    from pathlib import Path

    allow = str(os.getenv("AA_DEV_ALLOW_BOOTSTRAP", "0")).lower() in {"1", "true", "yes"}
    if not allow:
        return False

    root = get_drive_root_or_none()
    if root is None:
        # Cannot bootstrap if AA_DRIVE_ROOT is not configured.
        return False
    target = root / ".aa" / "manifest.json"

    # Missing AA_DRIVE_ROOT entirely? Nothing to bootstrap.
    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    # Bootstrap when manifest is missing
    if not target.exists():
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            payload: Dict[str, Any] = {
                "version": 1,
                "drive_root": str(root),
                "launchbox_dir": str(root / "LaunchBox"),
                "configs_dir": str(root / "configs"),
                "overrides_dir": str(root / "configs" / "overrides"),
                "tmp_dir": str(root / "ArcadeAssistant" / "_tmp"),
                "created_at": datetime.now(timezone.utc).isoformat(),
                # Minimal sanctioned_paths to satisfy downstream checks
                "sanctioned_paths": DEFAULT_SANCTIONED_PATHS,
            }
            with open(target, "w", encoding="utf-8") as f:
                import json as _json
                _json.dump(payload, f)
            print("manifest: bootstrapped")
            return True
        except Exception as e:
            print(f"CONFIG ERROR: bootstrap failed: {e}")
            return False

    # Repair invalid JSON by backup and rewrite
    try:
        import json as _json
        with open(target, "r", encoding="utf-8") as f:
            _json.load(f)
        return False  # valid JSON; no repair
    except Exception:
        try:
            bak = target.with_suffix(".json.bak")
            try:
                target.replace(bak)
            except Exception:
                pass
            payload: Dict[str, Any] = {
                "version": 1,
                "drive_root": str(root),
                "launchbox_dir": str(root / "LaunchBox"),
                "configs_dir": str(root / "configs"),
                "overrides_dir": str(root / "configs" / "overrides"),
                "tmp_dir": str(root / "ArcadeAssistant" / "_tmp"),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "sanctioned_paths": DEFAULT_SANCTIONED_PATHS,
            }
            with open(target, "w", encoding="utf-8") as f:
                import json as _json
                _json.dump(payload, f)
            print("manifest: repaired")
            return True
        except Exception as e:
            print(f"CONFIG ERROR: repair failed: {e}")
            return False


def validate_on_startup(app: Any = None) -> None:
    try:
        data = load_manifest()
        errors = validate_manifest(data)
        if errors:
            # Try bootstrap path
            if _bootstrap_manifest_if_allowed(errors):
                return
            for msg in errors:
                print(f"CONFIG ERROR: {msg}")
            sys.exit(78)
    except SystemExit:
        raise
    except Exception as e:
        # When load fails entirely, try bootstrap
        if _bootstrap_manifest_if_allowed([str(e)]):
            return
        print(f"CONFIG ERROR: {e}")
        sys.exit(78)
