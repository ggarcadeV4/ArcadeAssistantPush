import os
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException

from backend.services import audit_log


DEFAULT_SANCTIONED_PATHS = [
    ".aa",
    ".aa/logs",
    ".aa/state",
    "config/mappings",
    "config/retroarch",
    "config/controllers/autoconfig/staging",
    "state/controller",
    "Emulators/RetroArch",
    "Emulators/MAME",
    "Emulators/Dolphin Tri-Force",
    "LaunchBox/Emulators/PPSSPPGold",
]


def _resolve_drive_root(raw: str) -> Path:
    """Resolve AA_DRIVE_ROOT allowing relative paths from project root."""
    import platform

    # Only convert Windows paths to WSL format if we're actually running on WSL
    is_wsl = platform.system() == 'Linux' and 'microsoft' in platform.release().lower()

    # Handle WSL: Convert Windows paths like "A:\" to "/mnt/a"
    if is_wsl and raw and len(raw) >= 2 and raw[1] == ':':
        drive_letter = raw[0].lower()
        # Convert A:\ to /mnt/a, C:\foo to /mnt/c/foo, etc.
        rest = raw[2:].replace('\\', '/').lstrip('/')
        wsl_path = f"/mnt/{drive_letter}"
        if rest:
            wsl_path = f"{wsl_path}/{rest}"
        return Path(wsl_path)

    p = Path(raw)
    if p.is_absolute():
        return p
    # backend/ -> project root is parent of this file's directory
    project_root = Path(__file__).resolve().parents[1]
    return (project_root / p).resolve()


def _normalize_drive_like(p: Path) -> Path:
    """Attempt to swap between Windows A:\\ and WSL /mnt/a path styles.

    This helps when AA_DRIVE_ROOT was set for the other runtime (WSL vs Windows).
    """
    s = str(p)
    if not s:
        return p
    # Windows -> WSL (Generic X: -> /mnt/x)
    if len(s) > 1 and s[1] == ':' and s[0].isalpha():
        drive = s[0].lower()
        s2 = s.replace('\\', '/').replace(f"{s[0]}:", f"/mnt/{drive}", 1)
        return Path(s2)
    # WSL -> Windows (Generic /mnt/x -> X:)
    if s.lower().startswith('/mnt/') and len(s) > 6 and s[6] == '/':
        drive = s[5].upper()
        s2 = s.replace(f"/mnt/{s[5]}", f"{drive}:", 1).replace('/', '\\')
        return Path(s2)
    return p


async def validate_environment():
    """Validate required environment variables and drive structure"""
    required_envs = ["AA_DRIVE_ROOT", "AA_BACKUP_ON_WRITE", "AA_DRY_RUN_DEFAULT"]

    missing = [env for env in required_envs if not os.getenv(env)]
    if missing:
        # Surface error but do not crash; downstream will gate writes
        print(f"ERROR: Missing required environment variable(s): {', '.join(missing)}")
        return

    drive_root = _resolve_drive_root(os.getenv("AA_DRIVE_ROOT"))

    # --- Universal Drive Validation ---
    # Treats any detected AA_DRIVE_ROOT as the source of truth.
    # If the drive exists but lacks a manifest, we allow it (Read-Only mode) rather than crashing.

    if not drive_root.exists():
        # Optional hint for downstream services; harmless if unused.
        os.environ.setdefault("AA_USE_MOCK_DATA", "1")
        print(f"INFO: Drive root missing ({drive_root}); continuing in development mode using mock LaunchBox data")
        return

    # If drive exists, check for manifest
    manifest_path = drive_root / ".aa" / "manifest.json"
    if not manifest_path.exists():
        # Do not crash; allow booting in restricted mode (handled in initialize_app_state)
        print(f"WARNING: Manifest missing at {manifest_path} - System will start in READ-ONLY mode")
        return

    # Validate manifest structure if it exists
    try:
        with open(manifest_path) as f:
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
        "drive_root": drive_root_raw or "<SET AA_DRIVE_ROOT>",
        "sanctioned_paths": DEFAULT_SANCTIONED_PATHS,
        "notes": "Update drive_root to the actual arcade drive and expand sanctioned_paths only as needed.",
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

    # Do not silently fall back to repo folder; use a sentinel when unset
    drive_root = _resolve_drive_root(drive_root_raw or "AA_DRIVE_ROOT_NOT_SET")
    if not drive_root.exists():
        alt = _normalize_drive_like(drive_root)
        if alt != drive_root and alt.exists():
            print(f"WARNING: AA_DRIVE_ROOT missing: {drive_root} — using normalized {alt}")
            drive_root = alt
        else:
            # Only overwrite if this isn't the AA_DRIVE_ROOT-not-set case
            if not write_block_reason:
                write_block_reason = f"AA_DRIVE_ROOT path does not exist: {drive_root}"
            writes_allowed = False
            startup_errors.append(f"AA_DRIVE_ROOT path does not exist: {drive_root}")

    # Default to missing/read-only state
    manifest = {"sanctioned_paths": []}
    policies = {}
    app.state.manifest_missing = True

    if not drive_root.exists():
        print(f"INFO: Development mode - using empty manifest (drive root missing: {drive_root})")
    else:
        # Drive exists - attempt to load configs
        print(f"INFO: Drive detected at {drive_root} - attempting to load manifest.json")
        manifest_path = drive_root / ".aa" / "manifest.json"
        policies_path = drive_root / ".aa" / "policies.json"

        if manifest_path.exists():
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
                app.state.manifest_missing = False
            except Exception as e:
                print(f"ERROR: Failed to load manifest.json: {e}")
        else:
            print(f"WARNING: manifest.json not found at {manifest_path}; bootstrapping template with default guardrails")
            manifest = _bootstrap_manifest(drive_root, drive_root_raw)

        if policies_path.exists():
            try:
                with open(policies_path) as f:
                    policies = json.load(f)
            except Exception as e:
                print(f"ERROR: Failed to load policies.json: {e}")

    # Apply manifest-driven safety checks
    sanctioned_paths = manifest.get("sanctioned_paths") or []
    manifest_drive = (manifest.get("drive_root") or "").strip()

    if not sanctioned_paths:
        writes_allowed = False
        if not write_block_reason:
            write_block_reason = "sanctioned_paths is empty; update .aa/manifest.json with allowed paths."
        startup_errors.append("sanctioned_paths is empty; update .aa/manifest.json with allowed paths.")

    # Ensure manifest drive_root matches runtime
    # Skip this check if AA_DRIVE_ROOT was already the blocking reason (preserve that error)
    aa_drive_root_error = "AA_DRIVE_ROOT is not set; writes are disabled until it is configured."
    if not manifest_drive or manifest_drive.upper() == "<SET AA_DRIVE_ROOT>".upper():
        if write_block_reason != aa_drive_root_error:
            writes_allowed = False
            if not write_block_reason:
                write_block_reason = "manifest drive_root is not set; set AA_DRIVE_ROOT or edit .aa/manifest.json drive_root."
            startup_errors.append("manifest drive_root is not set; set AA_DRIVE_ROOT or edit .aa/manifest.json drive_root.")
    elif drive_root_raw and manifest_drive:
        # Normalize slashes for comparison
        if str(Path(manifest_drive)).replace("\\", "/").lower() != str(drive_root).replace("\\", "/").lower():
            writes_allowed = False
            if not write_block_reason:
                write_block_reason = f"manifest drive_root ({manifest_drive}) does not match AA_DRIVE_ROOT ({drive_root_raw})."
            startup_errors.append(f"manifest drive_root ({manifest_drive}) does not match AA_DRIVE_ROOT ({drive_root_raw}).")

    # Create required directories under .aa (only if drive root exists)
    if drive_root.exists():
        aa_root = drive_root / ".aa"
        aa_root.mkdir(exist_ok=True)
        for dir_name in ["state", "logs", "backups"]:
            (aa_root / dir_name).mkdir(exist_ok=True)
        # Legacy configs at root level (read-only source, not state)
        (drive_root / "configs").mkdir(exist_ok=True)

    # Store in app state
    app.state.drive_root = drive_root
    app.state.manifest = manifest
    app.state.policies = policies
    app.state.backup_on_write = os.getenv("AA_BACKUP_ON_WRITE", "true").lower() == "true"
    app.state.dry_run_default = os.getenv("AA_DRY_RUN_DEFAULT", "true").lower() == "true"
    app.state.startup_errors = startup_errors
    app.state.writes_allowed = writes_allowed
    app.state.write_block_reason = write_block_reason

    print(f"Initialized with drive root: {drive_root}")
    if startup_errors:
        print(f"STARTUP ERRORS: {startup_errors}")
    print(f"Sanctioned paths: {manifest['sanctioned_paths']}")
    print(f"Backup on write: {app.state.backup_on_write}")
    print(f"Dry run default: {app.state.dry_run_default}")
