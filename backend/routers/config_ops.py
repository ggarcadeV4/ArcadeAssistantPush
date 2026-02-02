from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from pathlib import Path
from typing import Dict, Any, Optional
import json
from datetime import datetime

from ..services.backup import create_backup, restore_from_backup
from ..services.diffs import compute_diff, has_changes
from ..services.policies import require_scope, is_allowed_file, filter_allowed_keys, validate_file_extension

router = APIRouter()

class PreviewRequest(BaseModel):
    target_file: str
    patch: Dict[str, Any]
    emulator: Optional[str] = None

class ApplyRequest(BaseModel):
    target_file: str
    patch: Dict[str, Any]
    emulator: str
    dry_run: Optional[bool] = None

class RestoreRequest(BaseModel):
    backup_path: str
    target_file: str

@router.post("/preview")
async def preview_config_changes(request: Request, preview_req: PreviewRequest):
    """Preview config changes without applying them"""

    try:
        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        policies = request.app.state.policies

        # Resolve target file path
        target_path = drive_root / preview_req.target_file

        # Validate path is in sanctioned areas
        if not is_allowed_file(target_path, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(
                status_code=403,
                detail=f"File not in sanctioned areas: {preview_req.target_file}"
            )

        # Validate file extension if emulator specified
        if preview_req.emulator:
            validate_file_extension(target_path, preview_req.emulator, policies)

        # Read current content
        if target_path.exists():
            with open(target_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
        else:
            current_content = ""

        # Apply patch to create new content
        if preview_req.emulator:
            # For emulator configs, filter allowed keys
            filtered_patch = filter_allowed_keys(preview_req.patch, preview_req.emulator, policies)
        else:
            filtered_patch = preview_req.patch

        # Simple key=value format for config files
        new_lines = []
        if current_content:
            new_lines = current_content.splitlines()

        # Apply patch (basic implementation)
        for key, value in filtered_patch.items():
            # Find existing key
            found = False
            for i, line in enumerate(new_lines):
                if line.strip().startswith(f"{key}="):
                    new_lines[i] = f"{key}={value}"
                    found = True
                    break

            # Add new key if not found
            if not found:
                new_lines.append(f"{key}={value}")

        new_content = "\n".join(new_lines)

        # Generate diff
        diff = compute_diff(current_content, new_content, preview_req.target_file)

        return {
            "target_file": preview_req.target_file,
            "has_changes": has_changes(current_content, new_content),
            "diff": diff,
            "patch_applied": filtered_patch,
            "file_exists": target_path.exists()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/apply")
async def apply_config_changes(request: Request, apply_req: ApplyRequest):
    """Apply config changes with backup"""

    try:
        # Validate scope header
        require_scope(request, "config")

        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        policies = request.app.state.policies

        # Resolve target file path
        target_path = drive_root / apply_req.target_file

        # Validate path is in sanctioned areas
        if not is_allowed_file(target_path, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(
                status_code=403,
                detail=f"File not in sanctioned areas: {apply_req.target_file}"
            )

        # Validate file extension
        validate_file_extension(target_path, apply_req.emulator, policies)

        # Filter allowed keys
        filtered_patch = filter_allowed_keys(apply_req.patch, apply_req.emulator, policies)

        # Read current content
        if target_path.exists():
            with open(target_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
        else:
            current_content = ""
            # Ensure parent directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)

        # Apply patch
        new_lines = current_content.splitlines() if current_content else []

        for key, value in filtered_patch.items():
            # Find existing key
            found = False
            for i, line in enumerate(new_lines):
                if line.strip().startswith(f"{key}="):
                    new_lines[i] = f"{key}={value}"
                    found = True
                    break

            # Add new key if not found
            if not found:
                new_lines.append(f"{key}={value}")

        new_content = "\n".join(new_lines)

        # Check if changes exist
        if not has_changes(current_content, new_content):
            return {
                "status": "no_changes",
                "target_file": apply_req.target_file,
                "backup_path": None
            }

        backup_path = None

        # Determine effective dry-run default
        dry_default = getattr(request.app.state, "dry_run_default", True)
        effective_dry = apply_req.dry_run if apply_req.dry_run is not None else dry_default

        # Create backup and write only when not in dry-run
        if not effective_dry:
            if target_path.exists() and request.app.state.backup_on_write:
                backup_path = create_backup(target_path, drive_root)

            # Write new content
            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            # Log change (enriched)
            log_change(request, drive_root, apply_req.target_file, "config", filtered_patch, backup_path, result="applied", ops_count=len(filtered_patch))

        return {
            "status": "applied" if not effective_dry else "preview",
            "target_file": apply_req.target_file,
            "backup_path": str(backup_path) if backup_path else None,
            "patch_applied": filtered_patch,
            "changes_count": len(filtered_patch)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/backups")
async def list_backups(request: Request, target_file: str):
    """List available backups for a target file"""

    try:
        # Validate scope header
        require_scope(request, "config")

        drive_root = request.app.state.drive_root
        backups_dir = drive_root / ".aa" / "backups"

        if not backups_dir.exists():
            return {"backups": []}

        # Find all backups matching the target file
        target_name = Path(target_file).name
        backups = []

        # Search through dated backup directories (YYYYMMDD format)
        for dated_dir in sorted(backups_dir.iterdir(), reverse=True):
            if not dated_dir.is_dir():
                continue

            # Look for backups of this target file
            for backup_file in dated_dir.glob(f"*{target_name}*"):
                backups.append({
                    "path": str(backup_file.relative_to(drive_root)),
                    "date": dated_dir.name,
                    "timestamp": backup_file.stat().st_mtime
                })

        return {"backups": backups[:10]}  # Limit to 10 most recent

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/restore")
async def restore_config(request: Request, restore_req: RestoreRequest):
    """Restore config from backup"""

    try:
        # Validate scope header
        require_scope(request, "backup")

        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest

        # Resolve paths
        backup_path = Path(restore_req.backup_path)
        target_path = drive_root / restore_req.target_file

        # Validate target is in sanctioned areas
        if not is_allowed_file(target_path, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(
                status_code=403,
                detail=f"Target not in sanctioned areas: {restore_req.target_file}"
            )

        # Validate backup path is within .aa/backups directory
        if not str(backup_path).startswith(str(drive_root / ".aa" / "backups")):
            raise HTTPException(
                status_code=403,
                detail="Backup path must be within .aa/backups directory"
            )

        # Perform restore
        restore_from_backup(backup_path, target_path)

        # Log restore
        log_change(request, drive_root, restore_req.target_file, "restore",
                  {"backup_path": str(backup_path)}, None, result="restored")

        return {
            "status": "restored",
            "target_file": restore_req.target_file,
            "backup_path": str(backup_path)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def log_change(request: Request, drive_root: Path, target_file: str, scope: str, patch: Dict[str, Any], backup_path: Optional[Path], result: Optional[str] = None, duration_ms: Optional[float] = None, ops_count: Optional[int] = None):
    """Log change to changes.jsonl with enriched metadata"""

    log_file = drive_root / ".aa" / "logs" / "changes.jsonl"
    device = request.headers.get('x-device-id', '') if hasattr(request, 'headers') else ''
    panel = request.headers.get('x-panel', '') if hasattr(request, 'headers') else ''
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "target_file": target_file,
        "scope": scope,
        "patch_keys": list(patch.keys()) if isinstance(patch, dict) else [],
        "backup_path": str(backup_path) if backup_path else None,
        "device": device,
        "panel": panel,
        "result": result,
        "duration_ms": duration_ms,
        "ops_count": ops_count,
    }

    # Append to log file
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry) + "\n")
