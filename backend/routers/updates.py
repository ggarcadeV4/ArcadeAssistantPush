"""
Update Plumbing Router (Phase 0 - Local-First, Inert by Default)

Provides safe local update framework that can be "fed" later via Supabase or USB.
Does NOT auto-update and cannot brick the cabinet.

Storage:
- .aa/updates/inbox/      - Drop zone for update bundles
- .aa/updates/staging/    - Validated bundles ready to apply
- .aa/updates/backups/    - Snapshot backups before apply
- .aa/logs/updates/events.jsonl - Audit log

Requires AA_UPDATES_ENABLED=1 to do anything besides status.
"""

from __future__ import annotations

import json
import os
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/local/updates", tags=["updates"])

# Import AI assistant for intelligent updates
from backend.services.update_assistant import get_update_assistant, UpdateAnalysis


# -----------------------------------------------------------------------------
# Path Helpers (Drive-letter agnostic)
# -----------------------------------------------------------------------------

def _get_drive_root(request: Optional[Request] = None) -> Path:
    """Get drive root from app state (set during startup validation).
    
    🚫 No os.getcwd() fallback - per Slice 2 contract.
    """
    if request:
        root = getattr(request.app.state, "drive_root", None)
        if root:
            return Path(root)
    # Fallback to env for non-request contexts (logging, status checks)
    drive_root = os.environ.get("AA_DRIVE_ROOT", "").strip()
    if drive_root:
        return Path(drive_root)
    raise RuntimeError("AA_DRIVE_ROOT is not set; cannot resolve path")


def _get_aa_root() -> Path:
    """Get .aa directory path."""
    return _get_drive_root() / ".aa"


def _updates_inbox_dir() -> Path:
    path = _get_aa_root() / "updates" / "inbox"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _updates_staging_dir() -> Path:
    path = _get_aa_root() / "updates" / "staging"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _updates_backups_dir() -> Path:
    path = _get_aa_root() / "updates" / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _updates_log_path() -> Path:
    path = _get_aa_root() / "logs" / "updates" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _manifest_path() -> Path:
    return _get_aa_root() / "cabinet_manifest.json"


def _version_file_path() -> Path:
    return _get_aa_root() / "version.json"


# -----------------------------------------------------------------------------
# Identity & Version Helpers
# -----------------------------------------------------------------------------

def _load_cabinet_identity() -> Dict[str, Any]:
    """Load cabinet identity from manifest."""
    manifest = _manifest_path()
    if manifest.exists():
        try:
            return json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _load_version_info() -> Dict[str, Any]:
    """Load current version info."""
    version_file = _version_file_path()
    if version_file.exists():
        try:
            return json.loads(version_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Default version
    return {
        "version": os.environ.get("AA_VERSION", "1.0.0"),
        "build": os.environ.get("AA_BUILD", "local"),
        "updated_at": None
    }


def _is_updates_enabled() -> bool:
    """Check if updates are enabled via env flag."""
    val = os.environ.get("AA_UPDATES_ENABLED", "0").lower()
    return val in ("1", "true", "yes", "on")


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

def _log_update_event(
    event: str,
    ok: bool,
    details: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None
) -> None:
    """Append event to updates log with identity fields."""
    try:
        identity = _load_cabinet_identity()
        
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "ok": ok,
            "device_id": identity.get("device_id", os.environ.get("AA_DEVICE_ID", "")),
            "cabinet_serial": identity.get("serial", ""),
            "cabinet_name": identity.get("name", ""),
            "frontend_source": request.headers.get("x-panel", "") if request else "",
            "details": details or {}
        }
        
        log_path = _updates_log_path()
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Best-effort logging


# -----------------------------------------------------------------------------
# Request/Response Models
# -----------------------------------------------------------------------------

class StagePayload(BaseModel):
    """Payload for staging an update bundle."""
    bundle_path: Optional[str] = Field(None, description="Path to bundle in inbox")
    bundle_id: Optional[str] = Field(None, description="Bundle ID (filename in inbox)")


class UpdateStatusResponse(BaseModel):
    """Response for update status."""
    enabled: bool
    current_version: str
    last_update: Optional[str] = None
    drive_root: str
    device_id: str
    error: Optional[str] = None


# -----------------------------------------------------------------------------
# Helper: Require scope header
# -----------------------------------------------------------------------------

def _require_scope(request: Request, allowed: List[str]) -> str:
    """Require x-scope header for mutating operations."""
    scope = request.headers.get("x-scope")
    if not scope:
        raise HTTPException(status_code=400, detail=f"Missing x-scope header. Allowed: {allowed}")
    if scope not in allowed:
        raise HTTPException(status_code=400, detail=f"x-scope '{scope}' not permitted. Allowed: {allowed}")
    return scope


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.get("/status")
async def get_update_status(request: Request):
    """
    Get update system status.
    
    Always returns status even if updates disabled.
    """
    enabled = _is_updates_enabled()
    version_info = _load_version_info()
    identity = _load_cabinet_identity()
    drive_root = _get_drive_root()
    
    return {
        "enabled": enabled,
        "current_version": version_info.get("version", "1.0.0"),
        "build": version_info.get("build", "local"),
        "last_update": version_info.get("updated_at"),
        "drive_root": str(drive_root),
        "device_id": identity.get("device_id", os.environ.get("AA_DEVICE_ID", "")),
        "cabinet_name": identity.get("name", ""),
        "cabinet_serial": identity.get("serial", ""),
        "inbox_path": str(_updates_inbox_dir()),
        "staging_path": str(_updates_staging_dir()),
        "backups_path": str(_updates_backups_dir())
    }


@router.post("/stage")
async def stage_update(request: Request, payload: StagePayload):
    """
    Stage an update bundle for later application.
    
    Requires x-scope: state header.
    Requires AA_UPDATES_ENABLED=1.
    Bundle must be in .aa/updates/inbox/
    """
    _require_scope(request, ["state"])
    
    # Check if updates enabled
    if not _is_updates_enabled():
        _log_update_event("stage_rejected", False, {"reason": "UPDATES_DISABLED"}, request)
        return {"enabled": False, "error": "UPDATES_DISABLED", "message": "Updates are disabled. Set AA_UPDATES_ENABLED=1 to enable."}
    
    # Resolve bundle path
    inbox = _updates_inbox_dir()
    
    if payload.bundle_path:
        bundle = Path(payload.bundle_path)
    elif payload.bundle_id:
        bundle = inbox / payload.bundle_id
    else:
        raise HTTPException(status_code=400, detail="Must provide bundle_path or bundle_id")
    
    # Validate bundle is under inbox (security)
    try:
        bundle = bundle.resolve()
        inbox_resolved = inbox.resolve()
        if not str(bundle).startswith(str(inbox_resolved)):
            raise HTTPException(status_code=400, detail="Bundle must be under .aa/updates/inbox/")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid bundle path: {e}")
    
    if not bundle.exists():
        raise HTTPException(status_code=404, detail=f"Bundle not found: {bundle.name}")
    
    # TODO: Validate manifest, sha256, signature, allowlist paths
    # For now, just create staging record
    
    staging = _updates_staging_dir()
    stage_record = {
        "bundle": bundle.name,
        "bundle_path": str(bundle),
        "staged_at": datetime.now(timezone.utc).isoformat(),
        "validated": False,  # Will be True after full validation
        "applied": False
    }
    
    stage_file = staging / f"{bundle.stem}.json"
    stage_file.write_text(json.dumps(stage_record, indent=2), encoding="utf-8")
    
    _log_update_event("staged", True, {"bundle": bundle.name}, request)
    
    return {
        "ok": True,
        "staged": True,
        "bundle": bundle.name,
        "stage_record": str(stage_file),
        "message": "Bundle staged. Call /apply to apply update."
    }


@router.post("/apply")
async def apply_update(request: Request):
    """
    Apply staged update.
    
    Requires x-scope: state header.
    Requires AA_UPDATES_ENABLED=1.
    """
    _require_scope(request, ["state"])
    
    if not _is_updates_enabled():
        _log_update_event("apply_rejected", False, {"reason": "UPDATES_DISABLED"}, request)
        return {"enabled": False, "error": "UPDATES_DISABLED", "message": "Updates are disabled. Set AA_UPDATES_ENABLED=1 to enable."}
    
    # Find staged updates
    staging = _updates_staging_dir()
    staged_files = list(staging.glob("*.json"))
    
    if not staged_files:
        return {"ok": False, "error": "NO_STAGED_UPDATES", "message": "No updates staged. Stage a bundle first."}
    
    # Get most recent staged update
    staged_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    stage_file = staged_files[0]
    
    try:
        stage_record = json.loads(stage_file.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read stage record: {e}")
    
    if stage_record.get("applied"):
        return {"ok": False, "error": "ALREADY_APPLIED", "message": "This update was already applied."}
    
    # TODO: Create backup snapshot
    backups = _updates_backups_dir()
    backup_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = backups / backup_id
    
    # TODO: Apply update (atomic file replacement)
    # For Phase 0, just mark as applied and log
    
    stage_record["applied"] = True
    stage_record["applied_at"] = datetime.now(timezone.utc).isoformat()
    stage_record["backup_id"] = backup_id
    stage_file.write_text(json.dumps(stage_record, indent=2), encoding="utf-8")
    
    _log_update_event("applied", True, {
        "bundle": stage_record.get("bundle"),
        "backup_id": backup_id
    }, request)
    
    return {
        "ok": True,
        "applied": True,
        "bundle": stage_record.get("bundle"),
        "backup_id": backup_id,
        "message": "Update applied successfully. (Phase 0: no-op implementation)"
    }


@router.post("/rollback")
async def rollback_update(request: Request):
    """
    Rollback to last backup snapshot.
    
    Requires x-scope: state header.
    Requires AA_UPDATES_ENABLED=1.
    """
    _require_scope(request, ["state"])
    
    if not _is_updates_enabled():
        _log_update_event("rollback_rejected", False, {"reason": "UPDATES_DISABLED"}, request)
        return {"enabled": False, "error": "UPDATES_DISABLED", "message": "Updates are disabled. Set AA_UPDATES_ENABLED=1 to enable."}
    
    # Find backups
    backups = _updates_backups_dir()
    backup_dirs = [d for d in backups.iterdir() if d.is_dir()]
    
    if not backup_dirs:
        return {"ok": False, "error": "NO_BACKUPS", "message": "No backup snapshots available."}
    
    # Get most recent backup
    backup_dirs.sort(key=lambda d: d.name, reverse=True)
    latest_backup = backup_dirs[0]
    
    # TODO: Restore backup (atomic file replacement)
    # For Phase 0, just log the attempt
    
    _log_update_event("rollback", True, {"backup_id": latest_backup.name}, request)
    
    return {
        "ok": True,
        "rolled_back": True,
        "backup_id": latest_backup.name,
        "message": "Rollback completed. (Phase 0: no-op implementation)"
    }


# =============================================================================
# AI-ASSISTED UPDATE ENDPOINTS
# =============================================================================

@router.post("/ai/analyze")
async def ai_analyze_update(request: Request):
    """
    AI analyzes a staged update before applying.
    
    Returns AI's assessment of:
    - Safety to apply
    - Potential conflicts with local state
    - Recommendations
    - Estimated downtime
    
    This provides consistent, intelligent analysis across all fleet cabinets.
    """
    # Find staged update
    staging = _updates_staging_dir()
    staged_files = list(staging.glob("*.json"))
    
    if not staged_files:
        return {"ok": False, "error": "NO_STAGED_UPDATE", "message": "No update staged for analysis."}
    
    # Load manifest from most recent staged update
    staged_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    stage_record = json.loads(staged_files[0].read_text())
    
    # Load actual manifest from bundle (simplified - would extract from zip)
    manifest = {
        "version": stage_record.get("version", "unknown"),
        "previous_version": _load_version_info().get("version", "unknown"),
        "files": [],
        "release_notes": stage_record.get("release_notes", "")
    }
    
    # Get AI analysis
    assistant = get_update_assistant()
    analysis = await assistant.analyze_update(manifest)
    
    _log_update_event("ai_analysis", True, {
        "safe_to_apply": analysis.safe_to_apply,
        "confidence": analysis.confidence,
        "conflicts": len(analysis.conflicts)
    }, request)
    
    return {
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
            "estimated_downtime_seconds": analysis.estimated_downtime_seconds
        }
    }


@router.post("/ai/apply")
async def ai_apply_update(request: Request, user_approved: bool = False):
    """
    Apply update with AI assistance.
    
    The AI:
    1. Analyzes the update for safety
    2. Creates automatic backup
    3. Monitors the update process
    4. Handles edge cases intelligently
    5. Can auto-rollback if needed
    6. Generates human-readable summary
    
    Args:
        user_approved: If True, bypasses AI safety check (for known conflicts)
    
    Requires x-scope: state header and AA_UPDATES_ENABLED=1.
    """
    _require_scope(request, ["state"])
    
    if not _is_updates_enabled():
        _log_update_event("ai_apply_rejected", False, {"reason": "UPDATES_DISABLED"}, request)
        return {"enabled": False, "error": "UPDATES_DISABLED"}
    
    # Find staged update
    staging = _updates_staging_dir()
    staged_files = list(staging.glob("*.json"))
    
    if not staged_files:
        return {"ok": False, "error": "NO_STAGED_UPDATE"}
    
    staged_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    stage_record = json.loads(staged_files[0].read_text())
    
    # Build manifest
    manifest = {
        "version": stage_record.get("version", "unknown"),
        "previous_version": _load_version_info().get("version", "unknown"),
        "files": stage_record.get("files", []),
        "release_notes": stage_record.get("release_notes", "")
    }
    
    bundle_path = Path(stage_record.get("bundle_path", ""))
    
    # Apply with AI assistance
    assistant = get_update_assistant()
    result = await assistant.apply_update_with_ai(manifest, bundle_path, user_approved)
    
    _log_update_event("ai_apply", result.success, {
        "version_before": result.version_before,
        "version_after": result.version_after,
        "changes": len(result.changes_applied),
        "errors": len(result.errors),
        "ai_summary": result.ai_summary
    }, request)
    
    return {
        "ok": result.success,
        "result": {
            "success": result.success,
            "version_before": result.version_before,
            "version_after": result.version_after,
            "changes_applied": result.changes_applied,
            "errors": result.errors,
            "rollback_available": result.rollback_available,
            "ai_summary": result.ai_summary
        }
    }


@router.get("/ai/status")
async def ai_update_status():
    """
    Get AI-assisted update system status.
    
    Shows whether AI assistance is available and recent update history.
    """
    assistant = get_update_assistant()
    
    # Check if AI is available
    ai_available = True
    try:
        from backend.services.model_router import get_model_router
        router = get_model_router()
        budget = router.get_usage_stats()
        ai_available = budget["budget_remaining_cents"] > 0
    except:
        ai_available = False
    
    # Get recent AI-assisted updates
    logs_dir = _get_aa_root() / "logs" / "updates"
    recent_updates = []
    
    ai_log = logs_dir / "ai_assisted_updates.jsonl"
    if ai_log.exists():
        try:
            with open(ai_log) as f:
                lines = f.readlines()[-10:]  # Last 10 entries
                for line in lines:
                    recent_updates.append(json.loads(line))
        except:
            pass
    
    return {
        "ai_available": ai_available,
        "updates_enabled": _is_updates_enabled(),
        "current_version": _load_version_info().get("version", "unknown"),
        "recent_ai_updates": recent_updates,
        "capabilities": [
            "Pre-update safety analysis",
            "Conflict detection with local state",
            "Automatic backup creation",
            "Intelligent rollback decisions",
            "Human-readable summaries"
        ]
    }
