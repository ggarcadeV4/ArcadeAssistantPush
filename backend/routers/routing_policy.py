from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime
import json

from ..services.diffs import compute_diff, has_changes
from ..services.backup import create_backup
from ..services.policies import require_scope, is_allowed_file


router = APIRouter(prefix="/api/routing-policy", tags=["routing-policy"])


class PolicyBody(BaseModel):
    # Accept arbitrary dict for now; validation below constrains top-level keys
    policy: Dict[str, Any]


ALLOWED_TOP_KEYS = {
    "policy_version",
    "order",
    "mame_protected",
    "platform_map",
    "profiles",
    "diagnostics",
}


def _target_file(drive_root: Path) -> Path:
    return drive_root / "configs" / "routing-policy.json"


def _validate_policy_shape(policy: Dict[str, Any]) -> None:
    if not isinstance(policy, dict):
        raise HTTPException(status_code=400, detail="Policy must be an object")
    unknown = set(policy.keys()) - ALLOWED_TOP_KEYS
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown keys: {sorted(list(unknown))}")
    # Minimal type checks (optional)
    if "order" in policy and not isinstance(policy["order"], list):
        raise HTTPException(status_code=400, detail="order must be a list")
    if "mame_protected" in policy and not isinstance(policy["mame_protected"], list):
        raise HTTPException(status_code=400, detail="mame_protected must be a list")
    if "platform_map" in policy and not isinstance(policy["platform_map"], dict):
        raise HTTPException(status_code=400, detail="platform_map must be an object")
    if "profiles" in policy and not isinstance(policy["profiles"], dict):
        raise HTTPException(status_code=400, detail="profiles must be an object")


@router.get("")
async def get_policy(request: Request):
    try:
        drive_root = request.app.state.drive_root
        target = _target_file(drive_root)
        if not target.exists():
            return {"exists": False, "policy": None}
        with open(target, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {"exists": True, "policy": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preview")
async def preview_policy(request: Request, body: PolicyBody):
    try:
        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        target = _target_file(drive_root)

        if not is_allowed_file(target, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(status_code=403, detail=f"Target not sanctioned: {target}")

        _validate_policy_shape(body.policy)

        new_content = json.dumps(body.policy, indent=2)
        current_content = ""
        if target.exists():
            with open(target, 'r', encoding='utf-8') as f:
                current_content = f.read()
        diff = compute_diff(current_content, new_content, target.name)
        return {
            "target_file": f"configs/{target.name}",
            "has_changes": has_changes(current_content, new_content),
            "diff": diff,
            "file_exists": target.exists(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply")
async def apply_policy(request: Request, body: PolicyBody):
    try:
        require_scope(request, "config")
        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        target = _target_file(drive_root)

        if not is_allowed_file(target, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(status_code=403, detail=f"Target not sanctioned: {target}")

        _validate_policy_shape(body.policy)

        target.parent.mkdir(parents=True, exist_ok=True)
        new_content = json.dumps(body.policy, indent=2)
        current_content = ""
        if target.exists():
            with open(target, 'r', encoding='utf-8') as f:
                current_content = f.read()

        if not has_changes(current_content, new_content):
            return {"status": "no_changes", "target_file": f"configs/{target.name}", "backup_path": None}

        backup_path = None
        if target.exists() and request.app.state.backup_on_write:
            backup_path = create_backup(target, drive_root)

        with open(target, 'w', encoding='utf-8') as f:
            f.write(new_content)

        # Log change
        try:
            from .config_ops import log_change  # reuse existing logger shape
            log_change(request, drive_root, f"configs/{target.name}", "routing_policy", body.policy, backup_path)
        except Exception:
            pass

        return {
            "status": "applied",
            "target_file": f"configs/{target.name}",
            "backup_path": str(backup_path) if backup_path else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

