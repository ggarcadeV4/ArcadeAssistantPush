from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from pathlib import Path
from typing import Any, Dict
import json

from ..services.diffs import compute_diff, has_changes
from ..services.backup import create_backup
from ..services.policies import require_scope, is_allowed_file


router = APIRouter(prefix="/api/teknoparrot/aliases", tags=["teknoparrot-aliases"])


class AliasBody(BaseModel):
    aliases: Dict[str, str]


def _target_file(drive_root: Path) -> Path:
    return drive_root / "configs" / "teknoparrot-aliases.json"


@router.get("")
async def get_aliases(request: Request):
    try:
        drive_root = request.app.state.drive_root
        target = _target_file(drive_root)
        if not target.exists():
            return {"exists": False, "aliases": {}}
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"exists": True, "aliases": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preview")
async def preview_aliases(request: Request, body: AliasBody):
    try:
        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        target = _target_file(drive_root)

        if not is_allowed_file(target, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(status_code=403, detail=f"Target not sanctioned: {target}")

        new_content = json.dumps(body.aliases, indent=2, ensure_ascii=False)
        current_content = ""
        if target.exists():
            with open(target, "r", encoding="utf-8") as f:
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
async def apply_aliases(request: Request, body: AliasBody):
    try:
        require_scope(request, "config")
        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        target = _target_file(drive_root)

        if not is_allowed_file(target, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(status_code=403, detail=f"Target not sanctioned: {target}")

        target.parent.mkdir(parents=True, exist_ok=True)
        new_content = json.dumps(body.aliases, indent=2, ensure_ascii=False)
        current_content = ""
        if target.exists():
            with open(target, "r", encoding="utf-8") as f:
                current_content = f.read()

        if not has_changes(current_content, new_content):
            return {"status": "no_changes", "target_file": f"configs/{target.name}", "backup_path": None}

        backup_path = None
        if target.exists() and request.app.state.backup_on_write:
            backup_path = create_backup(target, drive_root)

        with open(target, "w", encoding="utf-8") as f:
            f.write(new_content)

        # Log change
        try:
            from .config_ops import log_change
            log_change(request, drive_root, f"configs/{target.name}", "teknoparrot_aliases", body.aliases, backup_path)
        except Exception:
            pass

        return {
            "status": "applied",
            "target_file": f"configs/{target.name}",
            "backup_path": str(backup_path) if backup_path else None,
            "entries": len(body.aliases or {}),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

