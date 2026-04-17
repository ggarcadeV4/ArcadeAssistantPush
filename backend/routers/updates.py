"""
Update router with staged apply and rollback support.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.constants.drive_root import get_drive_root
from backend.services.update_assistant import get_update_assistant

router = APIRouter(prefix="/api/local/updates", tags=["updates"])

LOCAL_MANIFEST_CANDIDATES = (
    Path(".aa/updates/inbox/update_manifest.json"),
    Path(".aa/updates/inbox/manifest.json"),
    Path(".aa/updates/manifest.json"),
)
MANIFEST_FILENAMES = ("manifest.json", "update_manifest.json")


def _get_drive_root(request: Optional[Request] = None) -> Path:
    if request:
        root = getattr(request.app.state, "drive_root", None)
        if root:
            return Path(root)
    return get_drive_root(context="updates router")


def _get_aa_root(request: Optional[Request] = None) -> Path:
    return _get_drive_root(request) / ".aa"


def _updates_root(request: Optional[Request] = None) -> Path:
    path = _get_aa_root(request) / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _updates_inbox_dir(request: Optional[Request] = None) -> Path:
    path = _updates_root(request) / "inbox"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _updates_staging_dir(request: Optional[Request] = None) -> Path:
    path = _updates_root(request) / "staging"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _updates_rollback_dir(request: Optional[Request] = None) -> Path:
    path = _updates_root(request) / "rollback"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _updates_log_path(request: Optional[Request] = None) -> Path:
    path = _get_aa_root(request) / "logs" / "updates.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _cabinet_manifest_path(request: Optional[Request] = None) -> Path:
    return _get_aa_root(request) / "cabinet_manifest.json"


def _version_file_path(request: Optional[Request] = None) -> Path:
    return _get_aa_root(request) / "version.json"


def _load_json_file(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _load_cabinet_identity(request: Optional[Request] = None) -> Dict[str, Any]:
    return _load_json_file(_cabinet_manifest_path(request)) or {}


def _load_version_info(request: Optional[Request] = None) -> Dict[str, Any]:
    payload = _load_json_file(_version_file_path(request))
    if payload:
        return payload
    return {
        "version": os.environ.get("AA_VERSION", "1.0.0"),
        "build": os.environ.get("AA_BUILD", "local"),
        "updated_at": None,
        "release_notes": "",
    }


def _write_version_info(version: str, release_notes: str, request: Optional[Request] = None) -> None:
    payload = {
        "version": version,
        "build": os.environ.get("AA_BUILD", "local"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "release_notes": release_notes,
    }
    _version_file_path(request).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _is_updates_enabled() -> bool:
    val = os.environ.get("AA_UPDATES_ENABLED", "0").strip().lower()
    return val in {"1", "true", "yes", "on"}


def _disabled_response(operation: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "enabled": False,
        "operation": operation,
        "error": "UPDATES_DISABLED",
        "message": "Updates disabled. Set AA_UPDATES_ENABLED=1 to enable update operations.",
    }


def _log_update_event(
    event: str,
    ok: bool,
    details: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> None:
    try:
        identity = _load_cabinet_identity(request)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "ok": ok,
            "device_id": identity.get("device_id", os.environ.get("AA_DEVICE_ID", "")),
            "cabinet_serial": identity.get("device_serial") or identity.get("serial", ""),
            "cabinet_name": identity.get("device_name") or identity.get("name", ""),
            "panel": request.headers.get("x-panel", "") if request else "",
            "details": details or {},
        }
        with open(_updates_log_path(request), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    except Exception:
        pass


class StagePayload(BaseModel):
    bundle_path: Optional[str] = Field(None, description="Path to bundle in inbox")
    bundle_id: Optional[str] = Field(None, description="Bundle filename in inbox")


class DownloadPayload(BaseModel):
    source_url: Optional[str] = Field(None, description="Override source manifest or bundle URL")


class ApplyPayload(BaseModel):
    stage_id: Optional[str] = Field(None, description="Specific stage record id to apply")


class RollbackPayload(BaseModel):
    snapshot_id: Optional[str] = Field(None, description="Specific rollback snapshot id to restore")


def _require_scope(request: Request, allowed: Iterable[str]) -> str:
    allowed_values = list(allowed)
    scope = request.headers.get("x-scope")
    if not scope:
        raise HTTPException(status_code=400, detail=f"Missing x-scope header. Allowed: {allowed_values}")
    if scope not in allowed_values:
        raise HTTPException(status_code=400, detail=f"x-scope '{scope}' not permitted. Allowed: {allowed_values}")
    return scope


def _version_key(version: str) -> Tuple[int, ...]:
    parts: List[int] = []
    for token in str(version).replace("-", ".").split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts or [0])


def _safe_relative_path(rel_path: str) -> Path:
    path = Path(rel_path)
    if path.is_absolute() or ".." in path.parts:
        raise HTTPException(status_code=400, detail=f"Unsafe path in update bundle: {rel_path}")
    return path


def _is_remote_source(source: str) -> bool:
    parsed = urlparse(source)
    return parsed.scheme in {"http", "https"}


def _resolve_source_path(source: str, base: Optional[str] = None) -> str:
    if not source:
        raise HTTPException(status_code=400, detail="Update source is empty")
    if _is_remote_source(source):
        return source
    if base and _is_remote_source(base):
        return urljoin(base, source)
    candidate = Path(source)
    if not candidate.is_absolute() and base and not _is_remote_source(base):
        candidate = Path(base).parent / candidate
    return str(candidate)


def _read_source_bytes(source: str, base: Optional[str] = None) -> bytes:
    resolved = _resolve_source_path(source, base)
    if _is_remote_source(resolved):
        with urlopen(resolved, timeout=15) as response:
            return response.read()
    return Path(resolved).read_bytes()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_bundle(bundle_path: Path, manifest: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    errors: List[str] = []
    if not bundle_path.exists():
        errors.append("bundle missing")
    elif not bundle_path.is_file():
        errors.append("bundle is not a file")
    elif bundle_path.stat().st_size <= 0:
        errors.append("bundle is empty")

    computed_hash = _sha256_file(bundle_path) if bundle_path.exists() and bundle_path.is_file() else None
    expected_hash = str((manifest or {}).get("sha256") or (manifest or {}).get("bundle_sha256") or "").strip().lower()
    if expected_hash and computed_hash and computed_hash.lower() != expected_hash:
        errors.append("bundle sha256 mismatch")

    return {
        "exists": bundle_path.exists(),
        "size_bytes": bundle_path.stat().st_size if bundle_path.exists() and bundle_path.is_file() else 0,
        "sha256": computed_hash,
        "verified": not errors,
        "errors": errors,
    }


def _bundle_manifest_from_zip(bundle_path: Path) -> Optional[Dict[str, Any]]:
    with zipfile.ZipFile(bundle_path, "r") as archive:
        for name in archive.namelist():
            if Path(name).name.lower() in MANIFEST_FILENAMES:
                with archive.open(name) as manifest_file:
                    return json.loads(manifest_file.read().decode("utf-8"))
    return None


def _load_bundle_manifest(bundle_path: Path) -> Dict[str, Any]:
    if not bundle_path.exists():
        return {}
    if bundle_path.is_dir():
        for candidate in MANIFEST_FILENAMES:
            manifest_path = bundle_path / candidate
            payload = _load_json_file(manifest_path)
            if payload:
                return payload
        return {}
    if bundle_path.suffix.lower() == ".json":
        return _load_json_file(bundle_path) or {}
    if bundle_path.suffix.lower() == ".zip":
        try:
            return _bundle_manifest_from_zip(bundle_path) or {}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Failed to read update zip manifest: {exc}") from exc
    return {}


def _normalize_manifest(manifest: Dict[str, Any], request: Optional[Request] = None) -> Dict[str, Any]:
    current = _load_version_info(request)
    return {
        "version": str(manifest.get("version") or current.get("version") or "1.0.0"),
        "previous_version": str(manifest.get("previous_version") or current.get("version") or "1.0.0"),
        "release_notes": str(manifest.get("release_notes") or ""),
        "files": list(manifest.get("files") or []),
        "bundle_url": manifest.get("bundle_url") or manifest.get("download_url") or manifest.get("bundle_path"),
        "sha256": manifest.get("sha256") or manifest.get("bundle_sha256"),
    }


def _resolve_manifest_source(request: Optional[Request] = None, override: Optional[str] = None) -> Optional[str]:
    if override:
        return override
    env_source = os.environ.get("AA_UPDATE_URL", "").strip()
    if env_source:
        return env_source
    drive_root = _get_drive_root(request)
    for relative in LOCAL_MANIFEST_CANDIDATES:
        candidate = drive_root / relative
        if candidate.exists():
            return str(candidate)
    return None


def _load_available_manifest(request: Optional[Request] = None, override: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    source = _resolve_manifest_source(request, override)
    if not source:
        return None, None

    resolved = _resolve_source_path(source)
    if resolved.lower().endswith(".zip"):
        bundle_path = Path(resolved)
        return _normalize_manifest(_load_bundle_manifest(bundle_path), request), resolved

    try:
        raw = _read_source_bytes(resolved)
        manifest = json.loads(raw.decode("utf-8"))
        return _normalize_manifest(manifest, request), resolved
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to load update manifest from {resolved}: {exc}") from exc


def _resolve_bundle_source(manifest: Dict[str, Any], manifest_source: Optional[str]) -> Optional[str]:
    bundle_source = manifest.get("bundle_url")
    if not bundle_source:
        return None
    return _resolve_source_path(str(bundle_source), manifest_source)


def _latest_stage_record(request: Optional[Request] = None) -> Optional[Tuple[Path, Dict[str, Any]]]:
    stage_records: List[Tuple[Path, Dict[str, Any]]] = []
    for stage_dir in _updates_staging_dir(request).iterdir():
        if not stage_dir.is_dir():
            continue
        record_path = stage_dir / "stage_record.json"
        payload = _load_json_file(record_path)
        if payload:
            stage_records.append((record_path, payload))
    if not stage_records:
        return None
    stage_records.sort(key=lambda entry: entry[0].stat().st_mtime, reverse=True)
    return stage_records[0]


def _stage_record_for_id(stage_id: str, request: Optional[Request] = None) -> Tuple[Path, Dict[str, Any]]:
    record_path = _updates_staging_dir(request) / stage_id / "stage_record.json"
    payload = _load_json_file(record_path)
    if not payload:
        raise HTTPException(status_code=404, detail=f"Stage record not found: {stage_id}")
    return record_path, payload


def _resolve_stage_record(stage_id: Optional[str], request: Optional[Request] = None) -> Tuple[Path, Dict[str, Any]]:
    if stage_id:
        return _stage_record_for_id(stage_id, request)
    latest = _latest_stage_record(request)
    if not latest:
        raise HTTPException(status_code=404, detail="No staged updates found")
    return latest


def _safe_extract_zip(bundle_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(bundle_path, "r") as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            _safe_relative_path(member.filename)
            rel_path = Path(member.filename)
            target = destination / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as source_handle, open(target, "wb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle)


def _copy_bundle_to_payload(bundle_path: Path, payload_root: Path) -> None:
    payload_root.mkdir(parents=True, exist_ok=True)
    if bundle_path.suffix.lower() == ".zip":
        _safe_extract_zip(bundle_path, payload_root)
        return
    if bundle_path.is_dir():
        shutil.copytree(bundle_path, payload_root, dirs_exist_ok=True)
        return
    if bundle_path.suffix.lower() == ".json":
        shutil.copy2(bundle_path, payload_root / bundle_path.name)
        return
    raise HTTPException(status_code=400, detail=f"Unsupported update bundle format: {bundle_path.suffix}")


def _collect_stage_files(payload_root: Path, manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    files = manifest.get("files") or []
    collected: List[Dict[str, Any]] = []

    if files:
        for entry in files:
            rel_path = str(entry.get("path") or "").replace("\\", "/").strip()
            if not rel_path:
                continue
            _safe_relative_path(rel_path)
            collected.append({"path": rel_path, "action": str(entry.get("action") or "replace")})
        return collected

    for path in payload_root.rglob("*"):
        if not path.is_file():
            continue
        if path.name.lower() in MANIFEST_FILENAMES:
            continue
        rel_path = str(path.relative_to(payload_root)).replace("\\", "/")
        _safe_relative_path(rel_path)
        collected.append({"path": rel_path, "action": "replace"})
    return collected


def _snapshot_targets(entries: List[Dict[str, Any]], request: Optional[Request] = None) -> Tuple[str, Path]:
    drive_root = _get_drive_root(request).resolve()
    snapshot_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_root = _updates_rollback_dir(request) / snapshot_id
    files_root = snapshot_root / "files"
    files_root.mkdir(parents=True, exist_ok=True)

    metadata_entries: List[Dict[str, Any]] = []
    tracked_paths = {entry["path"] for entry in entries}
    tracked_paths.add(".aa/version.json")

    for rel_path in sorted(tracked_paths):
        rel = _safe_relative_path(rel_path)
        target = (drive_root / rel).resolve()
        if drive_root not in [target, *target.parents]:
            raise HTTPException(status_code=400, detail=f"Update target escapes drive root: {rel_path}")

        existed = target.exists()
        entry = {
            "path": str(rel).replace("\\", "/"),
            "existed": existed,
            "type": "dir" if target.is_dir() else "file" if target.is_file() else "missing",
        }
        if existed:
            backup_target = files_root / rel
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_dir():
                shutil.copytree(target, backup_target, dirs_exist_ok=True)
            else:
                shutil.copy2(target, backup_target)
        metadata_entries.append(entry)

    metadata = {
        "snapshot_id": snapshot_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "entries": metadata_entries,
    }
    (snapshot_root / "snapshot.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return snapshot_id, snapshot_root


def _apply_stage_record(record_path: Path, stage_record: Dict[str, Any], request: Request) -> Dict[str, Any]:
    if stage_record.get("applied"):
        return {
            "ok": False,
            "error": "ALREADY_APPLIED",
            "message": "This staged update was already applied.",
        }

    payload_root = Path(stage_record.get("payload_root") or "")
    if not payload_root.exists():
        raise HTTPException(status_code=400, detail="Staged payload is missing; stage the bundle again")

    manifest = stage_record.get("manifest") or {}
    files = list(stage_record.get("files") or [])
    if not files:
        files = _collect_stage_files(payload_root, manifest)
        stage_record["files"] = files

    snapshot_id, _snapshot_root = _snapshot_targets(files, request)
    drive_root = _get_drive_root(request)

    for entry in files:
        rel = _safe_relative_path(entry["path"])
        action = str(entry.get("action") or "replace").lower()
        source = payload_root / rel
        target = drive_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)

        if action == "delete":
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            continue

        if not source.exists():
            raise HTTPException(status_code=400, detail=f"Staged payload missing file: {rel}")

        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()

        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)

    version = str(manifest.get("version") or _load_version_info(request).get("version") or "1.0.0")
    release_notes = str(manifest.get("release_notes") or "")
    _write_version_info(version, release_notes, request)

    stage_record["applied"] = True
    stage_record["applied_at"] = datetime.now(timezone.utc).isoformat()
    stage_record["snapshot_id"] = snapshot_id
    record_path.write_text(json.dumps(stage_record, indent=2) + "\n", encoding="utf-8")

    return {
        "ok": True,
        "applied": True,
        "bundle": stage_record.get("bundle"),
        "stage_id": stage_record.get("stage_id"),
        "snapshot_id": snapshot_id,
        "version": version,
        "message": "Update applied successfully.",
    }


def _restore_snapshot(snapshot_id: str, request: Optional[Request] = None) -> Dict[str, Any]:
    snapshot_root = _updates_rollback_dir(request) / snapshot_id
    metadata = _load_json_file(snapshot_root / "snapshot.json")
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Rollback snapshot not found: {snapshot_id}")

    drive_root = _get_drive_root(request)
    files_root = snapshot_root / "files"
    restored = 0

    for entry in metadata.get("entries", []):
        rel = _safe_relative_path(entry["path"])
        target = drive_root / rel
        backup_source = files_root / rel

        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()

        if entry.get("existed"):
            target.parent.mkdir(parents=True, exist_ok=True)
            if backup_source.is_dir():
                shutil.copytree(backup_source, target, dirs_exist_ok=True)
            elif backup_source.exists():
                shutil.copy2(backup_source, target)
            restored += 1

    return {
        "ok": True,
        "rolled_back": True,
        "snapshot_id": snapshot_id,
        "restored_count": restored,
        "message": "Rollback completed successfully.",
    }


@router.get("/status")
async def get_update_status(request: Request) -> Dict[str, Any]:
    enabled = _is_updates_enabled()
    version_info = _load_version_info(request)
    identity = _load_cabinet_identity(request)
    drive_root = _get_drive_root(request)

    return {
        "enabled": enabled,
        "current_version": version_info.get("version", "1.0.0"),
        "build": version_info.get("build", "local"),
        "last_update": version_info.get("updated_at"),
        "drive_root": str(drive_root),
        "device_id": identity.get("device_id", os.environ.get("AA_DEVICE_ID", "")),
        "cabinet_name": identity.get("device_name") or identity.get("name", ""),
        "cabinet_serial": identity.get("device_serial") or identity.get("serial", ""),
        "inbox_path": str(_updates_inbox_dir(request)),
        "staging_path": str(_updates_staging_dir(request)),
        "rollback_path": str(_updates_rollback_dir(request)),
        "backups_path": str(_updates_rollback_dir(request)),
        "log_path": str(_updates_log_path(request)),
    }


@router.get("/check")
async def check_for_updates(request: Request, source_url: Optional[str] = None) -> Dict[str, Any]:
    if not _is_updates_enabled():
        _log_update_event("check_rejected", False, {"reason": "UPDATES_DISABLED"}, request)
        return _disabled_response("check")

    manifest, source = _load_available_manifest(request, source_url)
    current_version = _load_version_info(request).get("version", "1.0.0")
    if not manifest or not source:
        response = {
            "ok": True,
            "available": False,
            "current_version": current_version,
            "source": None,
            "message": "No update manifest available.",
        }
        _log_update_event("check", True, response, request)
        return response

    target_version = str(manifest.get("version") or current_version)
    available = _version_key(target_version) > _version_key(current_version)
    response = {
        "ok": True,
        "available": available,
        "current_version": current_version,
        "target_version": target_version,
        "source": source,
        "bundle_source": _resolve_bundle_source(manifest, source),
        "manifest": manifest,
        "message": "Update available." if available else "Cabinet already up to date.",
    }
    _log_update_event("check", True, response, request)
    return response


@router.post("/download")
async def download_update(request: Request, payload: DownloadPayload = DownloadPayload()) -> Dict[str, Any]:
    _require_scope(request, ["state"])
    if not _is_updates_enabled():
        _log_update_event("download_rejected", False, {"reason": "UPDATES_DISABLED"}, request)
        return _disabled_response("download")

    manifest, source = _load_available_manifest(request, payload.source_url)
    if not manifest or not source:
        raise HTTPException(status_code=404, detail="No update manifest available for download")

    bundle_source = _resolve_bundle_source(manifest, source)
    if not bundle_source:
        raise HTTPException(status_code=400, detail="Update manifest does not include a bundle_url")

    inbox = _updates_inbox_dir(request)
    filename = Path(urlparse(bundle_source).path).name or "update_bundle.zip"
    destination = inbox / filename

    if _is_remote_source(bundle_source):
        with urlopen(bundle_source, timeout=30) as response, open(destination, "wb") as handle:
            shutil.copyfileobj(response, handle)
    else:
        source_path = Path(bundle_source)
        if not source_path.exists():
            raise HTTPException(status_code=404, detail=f"Bundle source not found: {bundle_source}")
        shutil.copy2(source_path, destination)

    verification = _verify_bundle(destination, manifest)
    if not verification["verified"]:
        raise HTTPException(status_code=400, detail=f"Downloaded bundle failed verification: {verification['errors']}")

    result = {
        "ok": True,
        "downloaded": True,
        "bundle": destination.name,
        "bundle_path": str(destination),
        "size_bytes": verification["size_bytes"],
        "sha256": verification["sha256"],
        "manifest": manifest,
    }
    _log_update_event("download", True, result, request)
    return result


@router.post("/stage")
async def stage_update(request: Request, payload: StagePayload) -> Dict[str, Any]:
    _require_scope(request, ["state"])
    if not _is_updates_enabled():
        _log_update_event("stage_rejected", False, {"reason": "UPDATES_DISABLED"}, request)
        return _disabled_response("stage")

    inbox = _updates_inbox_dir(request)
    if payload.bundle_path:
        bundle = Path(payload.bundle_path)
    elif payload.bundle_id:
        bundle = inbox / payload.bundle_id
    else:
        raise HTTPException(status_code=400, detail="Must provide bundle_path or bundle_id")

    bundle = bundle.resolve()
    if inbox.resolve() not in [bundle, *bundle.parents]:
        raise HTTPException(status_code=400, detail="Bundle must be located under .aa/updates/inbox/")
    if not bundle.exists():
        raise HTTPException(status_code=404, detail=f"Bundle not found: {bundle.name}")

    manifest = _normalize_manifest(_load_bundle_manifest(bundle), request)
    verification = _verify_bundle(bundle, manifest)
    if not verification["verified"]:
        raise HTTPException(status_code=400, detail=f"Bundle verification failed: {verification['errors']}")

    stage_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{bundle.stem}"
    stage_dir = _updates_staging_dir(request) / stage_id
    payload_root = stage_dir / "payload"
    payload_root.mkdir(parents=True, exist_ok=True)
    _copy_bundle_to_payload(bundle, payload_root)

    files = _collect_stage_files(payload_root, manifest)
    stage_record = {
        "stage_id": stage_id,
        "bundle": bundle.name,
        "bundle_path": str(bundle),
        "payload_root": str(payload_root),
        "staged_at": datetime.now(timezone.utc).isoformat(),
        "manifest": manifest,
        "files": files,
        "validated": True,
        "verification": verification,
        "applied": False,
    }
    record_path = stage_dir / "stage_record.json"
    record_path.write_text(json.dumps(stage_record, indent=2) + "\n", encoding="utf-8")

    result = {
        "ok": True,
        "staged": True,
        "stage_id": stage_id,
        "bundle": bundle.name,
        "stage_record": str(record_path),
        "file_count": len(files),
        "version": manifest.get("version"),
        "message": "Bundle staged successfully. Call /apply to commit it.",
    }
    _log_update_event("stage", True, result, request)
    return result


@router.post("/apply")
async def apply_update(request: Request, payload: ApplyPayload = ApplyPayload()) -> Dict[str, Any]:
    _require_scope(request, ["state"])
    if not _is_updates_enabled():
        _log_update_event("apply_rejected", False, {"reason": "UPDATES_DISABLED"}, request)
        return _disabled_response("apply")

    record_path, stage_record = _resolve_stage_record(payload.stage_id, request)
    result = _apply_stage_record(record_path, stage_record, request)
    _log_update_event("apply", bool(result.get("ok")), result, request)
    return result


@router.post("/rollback")
async def rollback_update(request: Request, payload: RollbackPayload = RollbackPayload()) -> Dict[str, Any]:
    _require_scope(request, ["state"])
    if not _is_updates_enabled():
        _log_update_event("rollback_rejected", False, {"reason": "UPDATES_DISABLED"}, request)
        return _disabled_response("rollback")

    snapshot_id = payload.snapshot_id
    if not snapshot_id:
        snapshots = [path for path in _updates_rollback_dir(request).iterdir() if path.is_dir()]
        if not snapshots:
            return {"ok": False, "error": "NO_BACKUPS", "message": "No rollback snapshots available."}
        snapshots.sort(key=lambda path: path.name, reverse=True)
        snapshot_id = snapshots[0].name

    result = _restore_snapshot(snapshot_id, request)
    _log_update_event("rollback", True, result, request)
    return result


@router.post("/ai/analyze")
async def ai_analyze_update(request: Request) -> Dict[str, Any]:
    if not _is_updates_enabled():
        _log_update_event("ai_analyze_rejected", False, {"reason": "UPDATES_DISABLED"}, request)
        return _disabled_response("ai_analyze")

    _record_path, stage_record = _resolve_stage_record(None, request)
    manifest = stage_record.get("manifest") or {}
    assistant = get_update_assistant()
    analysis = await assistant.analyze_update(manifest)

    result = {
        "ok": True,
        "analysis": {
            "safe_to_apply": analysis.safe_to_apply,
            "confidence": analysis.confidence,
            "summary": analysis.summary,
            "changes": analysis.changes,
            "risks": analysis.risks,
            "conflicts": analysis.conflicts,
            "recommendations": analysis.recommendations,
            "requires_user_approval": analysis.requires_user_approval,
            "estimated_downtime_seconds": analysis.estimated_downtime_seconds,
        },
    }
    _log_update_event("ai_analysis", True, result["analysis"], request)
    return result


@router.post("/ai/apply")
async def ai_apply_update(request: Request, user_approved: bool = False) -> Dict[str, Any]:
    _require_scope(request, ["state"])
    if not _is_updates_enabled():
        _log_update_event("ai_apply_rejected", False, {"reason": "UPDATES_DISABLED"}, request)
        return _disabled_response("ai_apply")

    record_path, stage_record = _resolve_stage_record(None, request)
    manifest = stage_record.get("manifest") or {}
    assistant = get_update_assistant()
    analysis = await assistant.analyze_update(manifest)
    if not analysis.safe_to_apply and not user_approved:
        result = {
            "ok": False,
            "error": "AI_REJECTED_UPDATE",
            "message": analysis.summary,
            "analysis": {
                "safe_to_apply": analysis.safe_to_apply,
                "confidence": analysis.confidence,
                "conflicts": analysis.conflicts,
                "recommendations": analysis.recommendations,
            },
        }
        _log_update_event("ai_apply", False, result, request)
        return result

    version_before = str(manifest.get("previous_version") or _load_version_info(request).get("version") or "1.0.0")
    apply_result = _apply_stage_record(record_path, stage_record, request)
    version_after = str(manifest.get("version") or version_before)
    ai_summary = analysis.summary if apply_result.get("ok") else "AI-assisted apply failed."
    result = {
        "ok": bool(apply_result.get("ok")),
        "result": {
            "success": bool(apply_result.get("ok")),
            "version_before": version_before,
            "version_after": version_after,
            "changes_applied": [entry["path"] for entry in stage_record.get("files", [])],
            "errors": [] if apply_result.get("ok") else [apply_result.get("message") or "Apply failed"],
            "rollback_available": bool(apply_result.get("snapshot_id")),
            "ai_summary": ai_summary,
            "snapshot_id": apply_result.get("snapshot_id"),
        },
    }
    _log_update_event("ai_apply", bool(result["ok"]), result["result"], request)
    return result


@router.get("/ai/status")
async def ai_update_status() -> Dict[str, Any]:
    ai_available = True
    try:
        from backend.services.model_router import get_model_router

        router_service = get_model_router()
        budget = router_service.get_usage_stats()
        ai_available = budget["budget_remaining_cents"] > 0
    except Exception:
        ai_available = False

    recent_updates: List[Dict[str, Any]] = []
    ai_log = _get_aa_root() / "logs" / "updates" / "ai_assisted_updates.jsonl"
    if ai_log.exists():
        try:
            with open(ai_log, encoding="utf-8") as handle:
                for line in handle.readlines()[-10:]:
                    recent_updates.append(json.loads(line))
        except Exception:
            pass

    return {
        "ai_available": ai_available,
        "updates_enabled": _is_updates_enabled(),
        "current_version": _load_version_info().get("version", "unknown"),
        "recent_ai_updates": recent_updates,
        "capabilities": [
            "Pre-update safety analysis",
            "Conflict detection with local state",
            "Operator-confirmed staged apply",
            "Rollback snapshot restore",
            "Human-readable summaries",
        ],
    }
