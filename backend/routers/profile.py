from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import httpx

from ..services.backup import create_backup
from ..services.diffs import compute_diff, has_changes
from ..services.policies import require_scope, is_allowed_file

router = APIRouter()


# Models
class SessionPlayer(BaseModel):
    """Controller assignment for saved session presets."""

    user: str = Field(..., min_length=1, max_length=80)
    controller: str = Field(..., min_length=1, max_length=80)


class ProfilePreferences(BaseModel):
    """Additional profile preferences shared across panels."""

    voiceAssignments: Dict[str, str] = Field(default_factory=dict)
    vocabulary: Optional[str] = Field(default=None, max_length=5000)
    players: List[SessionPlayer] = Field(default_factory=list)
    playerPosition: Optional[str] = Field(default=None, max_length=4)


class UserProfile(BaseModel):
    displayName: str = Field(..., min_length=1, max_length=80)
    initials: Optional[str] = Field(None, max_length=8)
    avatar: Optional[str] = Field(None, max_length=256)
    favoriteColor: Optional[str] = Field(None, max_length=32)
    userId: Optional[str] = Field(None, max_length=64)
    consent: Optional[bool] = None
    preferences: ProfilePreferences = Field(default_factory=ProfilePreferences)


class ConsentPayload(BaseModel):
    accepted: bool
    consentVersion: str = Field(..., max_length=16)
    scopes: Optional[list[str]] = Field(default_factory=list)
    userId: Optional[str] = Field(None, max_length=64)


class PrimaryProfilePayload(BaseModel):
    """Payload for setting the primary user profile and broadcasting to all agents."""

    user_id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=80)
    initials: str = Field(..., min_length=1, max_length=8)
    voice_prefs: Dict[str, str] = Field(default_factory=dict)
    vocabulary: List[str] = Field(default_factory=list)
    training_phrases: List[str] = Field(default_factory=list)
    player_position: Optional[str] = None
    controller_assignment: Optional[str] = None
    custom_vocabulary: Optional[List[str]] = None
    consent: Optional[bool] = None
    consent_active: Optional[bool] = None


# Paths (Golden Drive: all state under .aa)
def _profile_dir(drive_root: Path) -> Path:
    return drive_root / ".aa" / "state" / "profile"


def _profile_file(drive_root: Path) -> Path:
    return _profile_dir(drive_root) / "user.json"


def _consent_file(drive_root: Path) -> Path:
    return _profile_dir(drive_root) / "consent.json"


def _primary_profile_file(drive_root: Path) -> Path:
    return _profile_dir(drive_root) / "primary_user.json"


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_primary_profile_object(path: Path, payload: PrimaryProfilePayload) -> Dict[str, Any]:
    profile_obj = {
        "user_id": payload.user_id,
        "display_name": payload.display_name,
        "initials": payload.initials,
        "voice_prefs": payload.voice_prefs,
        "vocabulary": payload.vocabulary,
        "training_phrases": payload.training_phrases,
        "player_position": payload.player_position,
        "controller_assignment": payload.controller_assignment,
        "custom_vocabulary": payload.custom_vocabulary,
        "consent": payload.consent,
        "consent_active": payload.consent_active,
        "last_updated": datetime.now().isoformat(),
    }

    existing = _read_json(path) or {}
    if existing.get("created_at"):
        profile_obj["created_at"] = existing["created_at"]
    else:
        profile_obj["created_at"] = datetime.now().isoformat()
    return profile_obj


def _log_change(request: Request, scope: str, action: str, details: Dict[str, Any], backup_path: Optional[Path] = None):
    log_file = request.app.state.drive_root / ".aa" / "logs" / "changes.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    device = request.headers.get("x-device-id", "unknown") if hasattr(request, "headers") else "unknown"
    panel = request.headers.get("x-panel", "unknown") if hasattr(request, "headers") else "unknown"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "scope": scope,
        "action": action,
        "details": details,
        "backup_path": str(backup_path) if backup_path else None,
        "device": device,
        "panel": panel,
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# Profile routes
@router.get("/profile")
async def get_profile(request: Request):
    try:
        drive_root = request.app.state.drive_root
        data = _read_json(_profile_file(drive_root)) or {}
        return {"profile": data, "exists": bool(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/profile/preview")
async def preview_profile(request: Request, payload: UserProfile):
    try:
        drive_root = request.app.state.drive_root
        path = _profile_file(drive_root)

        current = ""
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                current = f.read()

        new_obj = {
            **payload.model_dump(),
            "userId": payload.userId or (payload.initials or payload.displayName)[:8],
            "lastUpdated": datetime.now().isoformat(),
        }
        # Preserve createdAt if exists
        existing = _read_json(path) or {}
        if existing.get("createdAt"):
            new_obj["createdAt"] = existing["createdAt"]
        else:
            new_obj["createdAt"] = datetime.now().isoformat()

        new_content = json.dumps(new_obj, indent=2)
        diff = compute_diff(current, new_content, "profile/user.json")
        return {
            "target_file": "state/profile/user.json",
            "has_changes": has_changes(current, new_content),
            "diff": diff,
            "profile": new_obj,
            "file_exists": path.exists(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/profile/apply")
async def apply_profile(request: Request, payload: UserProfile):
    try:
        require_scope(request, "state")
        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        path = _profile_file(drive_root)

        if not is_allowed_file(path, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(status_code=403, detail=f"File not in sanctioned areas: {path}")

        path.parent.mkdir(parents=True, exist_ok=True)

        backup_path = None
        if path.exists() and request.app.state.backup_on_write:
            backup_path = create_backup(path, drive_root)

        new_obj = {
            **payload.model_dump(),
            "userId": payload.userId or (payload.initials or payload.displayName)[:8],
            "lastUpdated": datetime.now().isoformat(),
        }
        existing = _read_json(path) or {}
        if existing.get("createdAt"):
            new_obj["createdAt"] = existing["createdAt"]
        else:
            new_obj["createdAt"] = datetime.now().isoformat()

        with open(path, "w", encoding="utf-8") as f:
            json.dump(new_obj, f, indent=2)

        _log_change(request, "profile", "profile_apply", {"target_file": "state/profile/user.json"}, backup_path)

        return {"status": "applied", "target_file": "state/profile/user.json", "backup_path": str(backup_path) if backup_path else None, "profile": new_obj}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Consent routes
@router.get("/consent")
async def get_consent(request: Request):
    try:
        drive_root = request.app.state.drive_root
        data = _read_json(_consent_file(drive_root)) or {}
        return {"consent": data, "accepted": bool(data.get("accepted")), "exists": bool(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/consent/preview")
async def preview_consent(request: Request, payload: ConsentPayload):
    try:
        drive_root = request.app.state.drive_root
        path = _consent_file(drive_root)

        current = ""
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                current = f.read()

        new_obj = {
            **payload.model_dump(),
            "timestamp": datetime.now().isoformat(),
            "deviceId": request.headers.get("x-device-id", "unknown"),
        }
        new_content = json.dumps(new_obj, indent=2)
        diff = compute_diff(current, new_content, "profile/consent.json")
        return {
            "target_file": "state/profile/consent.json",
            "has_changes": has_changes(current, new_content),
            "diff": diff,
            "consent": new_obj,
            "file_exists": path.exists(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/consent/apply")
async def apply_consent(request: Request, payload: ConsentPayload):
    try:
        require_scope(request, "state")
        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        path = _consent_file(drive_root)

        if not is_allowed_file(path, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(status_code=403, detail=f"File not in sanctioned areas: {path}")

        path.parent.mkdir(parents=True, exist_ok=True)

        backup_path = None
        if path.exists() and request.app.state.backup_on_write:
            backup_path = create_backup(path, drive_root)

        new_obj = {
            **payload.model_dump(),
            "timestamp": datetime.now().isoformat(),
            "deviceId": request.headers.get("x-device-id", "unknown"),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(new_obj, f, indent=2)

        _log_change(request, "profile", "consent_apply", {"target_file": "state/profile/consent.json"}, backup_path)

        return {"status": "applied", "target_file": "state/profile/consent.json", "backup_path": str(backup_path) if backup_path else None, "consent": new_obj}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Primary Profile Route (for broadcasting)
@router.post("/profile/primary/preview")
async def preview_primary_profile(request: Request, payload: PrimaryProfilePayload):
    """Preview primary profile changes without writing or broadcasting."""
    try:
        drive_root = request.app.state.drive_root
        path = _primary_profile_file(drive_root)

        current = ""
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                current = f.read()

        profile_obj = _build_primary_profile_object(path, payload)
        new_content = json.dumps(profile_obj, indent=2)
        diff = compute_diff(current, new_content, "profile/primary_user.json")
        return {
            "target_file": "state/profile/primary_user.json",
            "has_changes": has_changes(current, new_content),
            "diff": diff,
            "profile": profile_obj,
            "file_exists": path.exists(),
            "dry_run": True,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/profile/primary")
async def update_primary_profile(request: Request, payload: PrimaryProfilePayload):
    """
    Update the primary user profile and broadcast to all agents.

    This endpoint saves the primary user's profile information to a canonical location
    that all other agents can read from. This implements the "broadcast" pattern where
    we write once to a central location instead of pushing to each agent individually.
    """
    try:
        require_scope(request, "state")
        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        path = _primary_profile_file(drive_root)

        if not is_allowed_file(path, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(status_code=403, detail=f"File not in sanctioned areas: {path}")

        path.parent.mkdir(parents=True, exist_ok=True)

        # Create backup if file exists
        backup_path = None
        if path.exists() and request.app.state.backup_on_write:
            backup_path = create_backup(path, drive_root)

        profile_obj = _build_primary_profile_object(path, payload)

        # Write to file
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profile_obj, f, indent=2)

        # Log the change
        _log_change(
            request,
            "profile",
            "primary_profile_update",
            {
                "target_file": "state/profile/primary_user.json",
                "user_id": payload.user_id,
                "display_name": payload.display_name,
            },
            backup_path,
        )

        # Broadcast profile update to frontend via Gateway Event Bus
        try:
            httpx.post(
                "http://localhost:8787/api/session/broadcast",
                json={
                    "type": "profile_updated",
                    "user_id": payload.user_id,
                    "display_name": payload.display_name,
                    "initials": payload.initials,
                    "profile": profile_obj,
                    "source": "profile_router"
                },
                timeout=2.0
            )
        except Exception as e:
            pass  # Don't fail profile save if broadcast fails

        return {
            "status": "saved",
            "message": "Primary user profile saved and broadcast to Arcade Assistant",
            "target_file": "state/profile/primary_user.json",
            "backup_path": str(backup_path) if backup_path else None,
            "profile": profile_obj,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile/primary")
async def get_primary_profile(request: Request):
    """Get the primary user profile."""
    try:
        drive_root = request.app.state.drive_root
        data = _read_json(_primary_profile_file(drive_root)) or {}
        return {"profile": data, "exists": bool(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
