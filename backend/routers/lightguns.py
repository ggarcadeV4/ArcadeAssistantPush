from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import shutil

from ..services.diffs import compute_diff, has_changes
from ..services.policies import is_allowed_file

router = APIRouter()


class CalibrationPoint(BaseModel):
    x: float = Field(..., ge=0.0, le=1.0, description="Horizontal position normalized 0-1")
    y: float = Field(..., ge=0.0, le=1.0, description="Vertical position normalized 0-1")


class CalibrationPayload(BaseModel):
    device_id: str = Field(..., description="Logical identifier for the gun")
    points: List[CalibrationPoint]
    capture_mode: str = Field(default="nine-point", description="Calibration pattern descriptor")
    dry_run: Optional[bool] = Field(default=None, description="Override backend dry-run default")


class ProfilePayload(BaseModel):
    profile_name: str = Field(..., description="Friendly profile name (e.g., 'Time Crisis')")
    device_id: Optional[str] = Field(default=None, description="Device to bind profile to")
    sensitivity: Optional[float] = Field(default=1.0, ge=0.1, le=5.0)
    smoothing: Optional[float] = Field(default=0.0, ge=0.0, le=1.0)
    offsets: Dict[str, float] = Field(default_factory=dict, description="Axis offsets (x/y)")
    dry_run: Optional[bool] = None


class ProfileRestorePayload(BaseModel):
    backup_path: str
    dry_run: Optional[bool] = None


class TestPayload(BaseModel):
    device_id: str
    scenario: str = Field(default="targets", description="Test scenario (targets|tracking|offset)")
    duration_seconds: int = Field(default=30, ge=5, le=300)
    dry_run: Optional[bool] = None


def _sanitize_segment(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    return cleaned or "lightgun"


def _calibration_file(drive_root: Path, device_id: str) -> Path:
    return drive_root / ".aa" / "state" / "lightguns" / "calibration" / f"{_sanitize_segment(device_id)}.json"


def _profiles_dir(drive_root: Path) -> Path:
    return drive_root / "configs" / "lightguns" / "profiles"


def _profile_file(drive_root: Path, profile_name: str) -> Path:
    return _profiles_dir(drive_root) / f"{_sanitize_segment(profile_name)}.json"


def _tests_dir(drive_root: Path) -> Path:
    return drive_root / ".aa" / "state" / "lightguns" / "tests"


def _lightgun_backup_root(drive_root: Path) -> Path:
    return drive_root / ".aa" / "backups" / "lightguns"


def _create_lightgun_backup(target_path: Path, drive_root: Path, reason: str) -> Optional[Path]:
    if not target_path.exists():
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = _lightgun_backup_root(drive_root) / f"{timestamp}_{reason}"
    backup_path = backup_dir / target_path.relative_to(drive_root)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target_path, backup_path)
    return backup_path


def _resolve_backup_target(drive_root: Path, backup_path: Path) -> Path:
    backup_path = backup_path.resolve()
    backup_root = _lightgun_backup_root(drive_root).resolve()
    try:
        rel = backup_path.relative_to(backup_root)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="backup_path must be inside backups/lightguns"
        )

    if len(rel.parts) < 2:
        raise HTTPException(status_code=400, detail="backup path missing relative target information")

    # Drop timestamp folder
    target_rel = Path(*rel.parts[1:])
    return (drive_root / target_rel).resolve()


def _rel_path(path: Path, drive_root: Path) -> str:
    try:
        return str(path.relative_to(drive_root)).replace("\\", "/")
    except ValueError:
        return str(path)


def _require_lightgun_scope(request: Request, allowed_scopes: List[str]) -> str:
    scope = request.headers.get("x-scope")
    if not scope:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required x-scope header. Allowed scopes: {allowed_scopes}"
        )
    if scope not in allowed_scopes:
        raise HTTPException(
            status_code=400,
            detail=f"x-scope '{scope}' not permitted. Allowed: {allowed_scopes}"
        )
    return scope


def _log_lightgun_change(
    request: Request,
    drive_root: Path,
    action: str,
    details: Dict[str, Any],
    backup_path: Optional[Path] = None
) -> None:
    log_file = drive_root / ".aa" / "logs" / "changes.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "scope": "lightguns",
        "action": action,
        "details": details,
        "backup_path": str(backup_path) if backup_path else None,
        "device": request.headers.get("x-device-id", "unknown"),
        "panel": request.headers.get("x-panel", "lightguns"),
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


@router.get("/devices")
async def list_lightgun_devices(request: Request):
    inventory = getattr(request.app.state, "hardware_inventory", None)
    devices = []
    if isinstance(inventory, dict):
        devices = inventory.get("lightguns") or []

    if not devices:
        devices = [{
            "id": "gunner-p1",
            "name": "Sinden Light Gun (stub)",
            "type": "usb",
            "vid": "0x16c0",
            "pid": "0x27db",
            "connected": True,
            "last_seen": datetime.now().isoformat(),
            "profiles": []
        }]

    return {
        "devices": devices,
        "count": len(devices)
    }


@router.post("/calibrate/preview")
async def preview_calibration(request: Request, payload: CalibrationPayload):
    _require_lightgun_scope(request, ["state", "local"])
    drive_root = request.app.state.drive_root
    manifest = getattr(request.app.state, "manifest", {}) or {}
    target_file = _calibration_file(drive_root, payload.device_id)
    if not is_allowed_file(target_file, drive_root, manifest.get("sanctioned_paths", [])):
        raise HTTPException(status_code=403, detail=f"Target path not sanctioned: {_rel_path(target_file, drive_root)}")

    current_content = ""
    if target_file.exists():
        current_content = target_file.read_text(encoding="utf-8")

    new_data = {
        "device_id": payload.device_id,
        "capture_mode": payload.capture_mode,
        "point_count": len(payload.points),
        "points": [point.dict() for point in payload.points],
        "updated_at": datetime.now().isoformat()
    }
    new_content = json.dumps(new_data, indent=2)
    rel_path = _rel_path(target_file, drive_root)
    diff = compute_diff(current_content, new_content, rel_path)

    return {
        "target_file": rel_path,
        "has_changes": has_changes(current_content, new_content),
        "diff": diff,
        "device_id": payload.device_id,
        "points_captured": len(payload.points)
    }


@router.post("/calibrate/apply")
async def apply_calibration(request: Request, payload: CalibrationPayload):
    _require_lightgun_scope(request, ["state"])
    drive_root = request.app.state.drive_root
    manifest = getattr(request.app.state, "manifest", {}) or {}
    target_file = _calibration_file(drive_root, payload.device_id)
    if not is_allowed_file(target_file, drive_root, manifest.get("sanctioned_paths", [])):
        raise HTTPException(status_code=403, detail=f"Target path not sanctioned: {_rel_path(target_file, drive_root)}")

    current_content = ""
    if target_file.exists():
        current_content = target_file.read_text(encoding="utf-8")

    new_data = {
        "device_id": payload.device_id,
        "capture_mode": payload.capture_mode,
        "point_count": len(payload.points),
        "points": [point.dict() for point in payload.points],
        "updated_at": datetime.now().isoformat()
    }
    new_content = json.dumps(new_data, indent=2)
    rel_path = _rel_path(target_file, drive_root)
    diff = compute_diff(current_content, new_content, rel_path)
    changed = has_changes(current_content, new_content)

    dry_default = getattr(request.app.state, "dry_run_default", False)
    dry_run = payload.dry_run if payload.dry_run is not None else dry_default

    backup_path = None
    if changed and not dry_run and target_file.exists() and getattr(request.app.state, "backup_on_write", True):
        backup_path = _create_lightgun_backup(target_file, drive_root, reason="calibration")

    if changed and not dry_run:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(new_content, encoding="utf-8")

    _log_lightgun_change(
        request,
        drive_root,
        "calibration_apply",
        {
            "device_id": payload.device_id,
            "points_captured": len(payload.points),
            "capture_mode": payload.capture_mode,
            "dry_run": dry_run,
            "has_changes": changed
        },
        backup_path
    )

    return {
        "target_file": rel_path,
        "has_changes": changed,
        "diff": diff,
        "dry_run": dry_run,
        "backup_path": str(backup_path) if backup_path else None
    }


@router.post("/profile/preview")
async def preview_profile(request: Request, payload: ProfilePayload):
    _require_lightgun_scope(request, ["config", "state", "local"])
    drive_root = request.app.state.drive_root
    manifest = getattr(request.app.state, "manifest", {}) or {}
    target_file = _profile_file(drive_root, payload.profile_name)
    if not is_allowed_file(target_file, drive_root, manifest.get("sanctioned_paths", [])):
        raise HTTPException(status_code=403, detail=f"Target path not sanctioned: {_rel_path(target_file, drive_root)}")

    current_content = ""
    if target_file.exists():
        current_content = target_file.read_text(encoding="utf-8")

    new_data = {
        "profile_name": payload.profile_name,
        "device_id": payload.device_id,
        "sensitivity": payload.sensitivity,
        "smoothing": payload.smoothing,
        "offsets": payload.offsets,
        "updated_at": datetime.now().isoformat()
    }
    new_content = json.dumps(new_data, indent=2)
    rel_path = _rel_path(target_file, drive_root)
    diff = compute_diff(current_content, new_content, rel_path)

    return {
        "target_file": rel_path,
        "has_changes": has_changes(current_content, new_content),
        "diff": diff,
        "profile": payload.profile_name
    }


@router.post("/profile/apply")
async def apply_profile(request: Request, payload: ProfilePayload):
    _require_lightgun_scope(request, ["config", "state"])
    drive_root = request.app.state.drive_root
    manifest = getattr(request.app.state, "manifest", {}) or {}
    target_file = _profile_file(drive_root, payload.profile_name)
    if not is_allowed_file(target_file, drive_root, manifest.get("sanctioned_paths", [])):
        raise HTTPException(status_code=403, detail=f"Target path not sanctioned: {_rel_path(target_file, drive_root)}")

    current_content = ""
    if target_file.exists():
        current_content = target_file.read_text(encoding="utf-8")

    new_data = {
        "profile_name": payload.profile_name,
        "device_id": payload.device_id,
        "sensitivity": payload.sensitivity,
        "smoothing": payload.smoothing,
        "offsets": payload.offsets,
        "updated_at": datetime.now().isoformat()
    }
    new_content = json.dumps(new_data, indent=2)
    rel_path = _rel_path(target_file, drive_root)
    diff = compute_diff(current_content, new_content, rel_path)
    changed = has_changes(current_content, new_content)

    dry_default = getattr(request.app.state, "dry_run_default", False)
    dry_run = payload.dry_run if payload.dry_run is not None else dry_default

    backup_path = None
    if changed and not dry_run and target_file.exists() and getattr(request.app.state, "backup_on_write", True):
        backup_path = _create_lightgun_backup(target_file, drive_root, reason="profile")

    if changed and not dry_run:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(new_content, encoding="utf-8")

    _log_lightgun_change(
        request,
        drive_root,
        "profile_apply",
        {
            "profile": payload.profile_name,
            "device_id": payload.device_id,
            "offset_keys": list(payload.offsets.keys()),
            "dry_run": dry_run,
            "has_changes": changed
        },
        backup_path
    )

    return {
        "target_file": rel_path,
        "has_changes": changed,
        "diff": diff,
        "dry_run": dry_run,
        "backup_path": str(backup_path) if backup_path else None
    }


@router.post("/profile/restore")
async def restore_profile(request: Request, payload: ProfileRestorePayload):
    _require_lightgun_scope(request, ["state", "backup", "config"])
    drive_root = request.app.state.drive_root
    backup_path = Path(payload.backup_path)
    if not backup_path.is_absolute():
        backup_path = (drive_root / backup_path).resolve()
    else:
        backup_path = backup_path.resolve()

    if not backup_path.exists():
        raise HTTPException(status_code=404, detail=f"Backup not found: {backup_path}")

    target_path = _resolve_backup_target(drive_root, backup_path)
    rel_path = _rel_path(target_path, drive_root)

    current_content = ""
    if target_path.exists():
        current_content = target_path.read_text(encoding="utf-8")
    backup_content = backup_path.read_text(encoding="utf-8")
    diff = compute_diff(current_content, backup_content, rel_path)
    changed = has_changes(current_content, backup_content)

    dry_default = getattr(request.app.state, "dry_run_default", False)
    dry_run = payload.dry_run if payload.dry_run is not None else dry_default

    if changed and not dry_run:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, target_path)

    _log_lightgun_change(
        request,
        drive_root,
        "profile_restore",
        {
            "target_file": rel_path,
            "dry_run": dry_run,
            "has_changes": changed
        },
        backup_path
    )

    return {
        "target_file": rel_path,
        "backup_path": str(backup_path),
        "dry_run": dry_run,
        "has_changes": changed,
        "diff": diff
    }


@router.post("/test/preview")
async def preview_test(request: Request, payload: TestPayload):
    _require_lightgun_scope(request, ["state", "local"])
    return {
        "device_id": payload.device_id,
        "scenario": payload.scenario,
        "duration_seconds": payload.duration_seconds,
        "message": f"Would run {payload.scenario} diagnostics for {payload.duration_seconds}s"
    }


@router.post("/test/apply")
async def apply_test(request: Request, payload: TestPayload):
    _require_lightgun_scope(request, ["state"])
    drive_root = request.app.state.drive_root
    manifest = getattr(request.app.state, "manifest", {}) or {}
    tests_dir = _tests_dir(drive_root)
    target_file = tests_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_sanitize_segment(payload.device_id)}.json"

    if not is_allowed_file(target_file, drive_root, manifest.get("sanctioned_paths", [])):
        raise HTTPException(status_code=403, detail=f"Target path not sanctioned: {_rel_path(target_file, drive_root)}")

    payload_data = {
        "device_id": payload.device_id,
        "scenario": payload.scenario,
        "duration_seconds": payload.duration_seconds,
        "requested_at": datetime.now().isoformat()
    }
    new_content = json.dumps(payload_data, indent=2)
    rel_path = _rel_path(target_file, drive_root)
    diff = compute_diff("", new_content, rel_path)

    dry_default = getattr(request.app.state, "dry_run_default", False)
    dry_run = payload.dry_run if payload.dry_run is not None else dry_default

    if not dry_run:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(new_content, encoding="utf-8")

    _log_lightgun_change(
        request,
        drive_root,
        "test_apply",
        {
            "device_id": payload.device_id,
            "scenario": payload.scenario,
            "duration_seconds": payload.duration_seconds,
            "dry_run": dry_run
        }
    )

    return {
        "target_file": rel_path,
        "diff": diff,
        "dry_run": dry_run,
        "has_changes": True,
        "payload": payload_data
    }
