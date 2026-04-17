import os
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException

from backend.constants.drive_root import (
    DriveRootNotSetError,
    get_drive_root,
    get_drive_root_or_none,
    paths_equivalent,
    resolve_drive_root_input,
)
from backend.constants.sanctioned_paths import DEFAULT_SANCTIONED_PATHS
from backend.services import audit_log
from backend.services.cabinet_identity import ensure_local_identity, load_cabinet_identity, provision_device_id


async def validate_environment():
    """Validate required environment variables and drive structure"""
    required_envs = ["AA_BACKUP_ON_WRITE", "AA_DRY_RUN_DEFAULT"]

    missing = [env for env in required_envs if not os.getenv(env)]
    if missing:
        print(f"ERROR: Missing required environment variable(s): {', '.join(missing)}")
        return

    drive_root = get_drive_root_or_none()
    if drive_root is None:
        print("INFO: AA_DRIVE_ROOT is not set; backend will continue in read-only/mock-safe mode until configured")
        return

    if not drive_root.exists():
        os.environ.setdefault("AA_USE_MOCK_DATA", "1")
        print(f"INFO: Configured root missing ({drive_root}); continuing in development mode using mock LaunchBox data")
        return

    manifest_path = drive_root / ".aa" / "manifest.json"
    if not manifest_path.exists():
        print(f"WARNING: Drive manifest missing at {manifest_path} - system will start in READ-ONLY mode")
        return

    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        if "sanctioned_paths" not in manifest:
            raise RuntimeError("manifest.json missing 'sanctioned_paths'")

        if not isinstance(manifest["sanctioned_paths"], list):
            raise RuntimeError("manifest.json 'sanctioned_paths' must be a list")

    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON in manifest.json: {e}")


def _bootstrap_manifest(drive_root: Path, drive_root_raw: str) -> dict:
    """Create a starter manifest when none exists."""
    manifest_dir = drive_root / ".aa"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "manifest.json"

    manifest_template = {
        "manifest_version": "1.0",
        "drive_root": drive_root_raw or str(drive_root),
        "sanctioned_paths": DEFAULT_SANCTIONED_PATHS,
        "notes": "Configured cabinet assets are expected to resolve under AA_DRIVE_ROOT. Keep sanctioned_paths aligned to that root contract.",
    }

    try:
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest_template, handle, indent=2)
        audit_log.append(
            {
                "scope": "manifest",
                "action": "manifest_bootstrapped",
                "drive_root": str(drive_root),
                "sanctioned_paths": DEFAULT_SANCTIONED_PATHS,
                "manifest_path": str(manifest_path),
            }
        )
        print(f"INFO: Bootstrapped manifest template at {manifest_path}")
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: Failed to bootstrap manifest template: {exc}")

    return manifest_template


def _sync_manifest_drive_root(manifest_path: Path, manifest: dict, drive_root_raw: str) -> dict:
    """Backfill or refresh manifest drive_root to match the active runtime."""
    desired_drive_root = (drive_root_raw or "").strip()
    current_drive_root = (manifest.get("drive_root") or "").strip()

    if not desired_drive_root:
        return manifest

    needs_update = (
        not current_drive_root
        or current_drive_root.upper() == "<SET AA_DRIVE_ROOT>"
        or not paths_equivalent(current_drive_root, desired_drive_root)
    )

    if not needs_update:
        return manifest

    manifest["drive_root"] = desired_drive_root
    if "manifest_version" not in manifest and "version" in manifest:
        manifest["manifest_version"] = str(manifest["version"])

    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
        print(f"INFO: Updated manifest drive_root to {desired_drive_root}")
    except Exception as exc:
        print(f"WARNING: Failed to update manifest drive_root at {manifest_path}: {exc}")

    return manifest


async def initialize_app_state(app: FastAPI):
    """Initialize application state and create required directories"""
    drive_root_raw = os.getenv("AA_DRIVE_ROOT", "").strip()
    startup_errors = []
    writes_allowed = True
    write_block_reason = None

    if not drive_root_raw:
        write_block_reason = "AA_DRIVE_ROOT is not set; writes are disabled until it is configured."
        writes_allowed = False
        startup_errors.append(write_block_reason)

    try:
        drive_root = get_drive_root(context="startup_manager.initialize_app_state")
    except DriveRootNotSetError:
        drive_root = Path("<AA_DRIVE_ROOT_UNSET>")
    except Exception:
        drive_root = resolve_drive_root_input(drive_root_raw) or Path("<AA_DRIVE_ROOT_UNSET>")

    if drive_root_raw and not drive_root.exists():
        if not write_block_reason:
            write_block_reason = f"AA_DRIVE_ROOT path does not exist: {drive_root}"
        writes_allowed = False
        startup_errors.append(f"AA_DRIVE_ROOT path does not exist: {drive_root}")

    manifest = {"sanctioned_paths": []}
    policies = {}
    app.state.manifest_missing = True
    early_device_id = ""

    if not drive_root.exists():
        print(f"INFO: Development mode - using empty manifest (configured root unavailable: {drive_root})")
    else:
        try:
            early_device_id = provision_device_id(drive_root)
            os.environ["AA_DEVICE_ID"] = early_device_id
            print(f"INFO: Device UUID ready before startup services: {early_device_id}")
        except Exception as exc:
            startup_errors.append(f"device ID provisioning failed: {exc}")
            print(f"WARNING: Device ID provisioning failed: {exc}")

        print(f"INFO: Configured root resolved to {drive_root} - attempting to load .aa/manifest.json")
        manifest_path = drive_root / ".aa" / "manifest.json"
        policies_path = drive_root / ".aa" / "policies.json"

        if manifest_path.exists():
            try:
                with open(manifest_path, encoding="utf-8") as f:
                    manifest = json.load(f)
                manifest = _sync_manifest_drive_root(manifest_path, manifest, drive_root_raw)
                app.state.manifest_missing = False
            except Exception as e:
                print(f"ERROR: Failed to load manifest.json: {e}")
        else:
            print(f"WARNING: manifest.json not found at {manifest_path}; bootstrapping template with default guardrails")
            manifest = _bootstrap_manifest(drive_root, drive_root_raw)
            app.state.manifest_missing = False

        if policies_path.exists():
            try:
                with open(policies_path, encoding="utf-8") as f:
                    policies = json.load(f)
            except Exception as e:
                print(f"ERROR: Failed to load policies.json: {e}")

    sanctioned_paths = manifest.get("sanctioned_paths") or []
    manifest_drive = (manifest.get("drive_root") or "").strip()

    if not sanctioned_paths:
        writes_allowed = False
        if not write_block_reason:
            write_block_reason = "sanctioned_paths is empty; update .aa/manifest.json with allowed paths."
        startup_errors.append("sanctioned_paths is empty; update .aa/manifest.json with allowed paths.")

    aa_drive_root_error = "AA_DRIVE_ROOT is not set; writes are disabled until it is configured."
    if not manifest_drive or manifest_drive.upper() == "<SET AA_DRIVE_ROOT>".upper():
        if write_block_reason != aa_drive_root_error:
            writes_allowed = False
            if not write_block_reason:
                write_block_reason = "manifest drive_root is not set; set AA_DRIVE_ROOT or edit .aa/manifest.json drive_root."
            startup_errors.append("manifest drive_root is not set; set AA_DRIVE_ROOT or edit .aa/manifest.json drive_root.")
    elif drive_root_raw and manifest_drive:
        if not paths_equivalent(manifest_drive, drive_root_raw):
            writes_allowed = False
            if not write_block_reason:
                write_block_reason = f"manifest drive_root ({manifest_drive}) does not match AA_DRIVE_ROOT ({drive_root_raw})."
            startup_errors.append(f"manifest drive_root ({manifest_drive}) does not match AA_DRIVE_ROOT ({drive_root_raw}).")

    identity = load_cabinet_identity(drive_root if drive_root.exists() else None)

    if drive_root.exists():
        aa_root = drive_root / ".aa"
        aa_root.mkdir(exist_ok=True)
        for dir_name in ["state", "logs", "backups"]:
            (aa_root / dir_name).mkdir(exist_ok=True)
        (drive_root / "configs").mkdir(exist_ok=True)

        try:
            identity = ensure_local_identity(drive_root)
            print(f"INFO: Cabinet identity ready ({identity.source}): {identity.device_id}")
        except Exception as exc:
            startup_errors.append(f"cabinet identity bootstrap failed: {exc}")
            print(f"WARNING: Cabinet identity bootstrap failed: {exc}")

    if early_device_id:
        os.environ["AA_DEVICE_ID"] = early_device_id

    app.state.drive_root = drive_root
    app.state.manifest = manifest
    app.state.policies = policies
    app.state.backup_on_write = os.getenv("AA_BACKUP_ON_WRITE", "true").lower() == "true"
    app.state.dry_run_default = os.getenv("AA_DRY_RUN_DEFAULT", "true").lower() == "true"
    app.state.startup_errors = startup_errors
    app.state.writes_allowed = writes_allowed
    app.state.write_block_reason = write_block_reason
    app.state.cabinet_identity = identity.to_dict()

    print(f"Initialized with configured root: {drive_root}")
    if startup_errors:
        print(f"STARTUP ERRORS: {startup_errors}")
    print(f"Sanctioned paths: {manifest['sanctioned_paths']}")
    print(f"Backup on write: {app.state.backup_on_write}")
    print(f"Dry run default: {app.state.dry_run_default}")
