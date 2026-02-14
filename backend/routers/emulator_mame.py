from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
import json
import logging

from ..services.backup import create_backup
from ..services.diffs import compute_diff, has_changes
from ..services.policies import require_scope, is_allowed_file, filter_allowed_keys, validate_file_extension

logger = logging.getLogger(__name__)
router = APIRouter()


def log_mame_change(drive_root: Path, action: str, details: Dict[str, Any], backup_path=None):
    """Log MAME config changes to changes.jsonl"""
    log_file = drive_root / ".aa" / "logs" / "changes.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "scope": "emulator",
        "panel": "mame",
        "action": action,
        "details": details,
        "backup_path": str(backup_path) if backup_path else None,
    }
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as exc:
        logger.warning(f"Failed to log change: {exc}")

class MAMEConfigRequest(BaseModel):
    config_file: str  # relative path like "cfg/mame.cfg" or "ini/mame.ini"
    patch: Dict[str, Any]
    dry_run: bool = False

@router.post("/config/apply")
async def apply_mame_config(request: Request, config_req: MAMEConfigRequest):
    """Apply structured patch to MAME config files"""

    try:
        # Validate scope header
        require_scope(request, "config")

        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        policies = request.app.state.policies

        # Get MAME paths from manifest
        mame_config = manifest.get("emulators", {}).get("mame", {})
        if not mame_config:
            raise HTTPException(
                status_code=400,
                detail="MAME not configured in manifest.json"
            )

        # Determine full path
        if config_req.config_file.endswith('.cfg'):
            base_dir = mame_config.get("cfg_dir", "emulators/mame/cfg")
        elif config_req.config_file.endswith('.ini'):
            base_dir = mame_config.get("ini_dir", "emulators/mame/ini")
        else:
            raise HTTPException(
                status_code=400,
                detail="Config file must be .cfg or .ini"
            )

        target_path = drive_root / base_dir / Path(config_req.config_file).name

        # Validate path is in sanctioned areas
        if not is_allowed_file(target_path, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(
                status_code=403,
                detail=f"File not in sanctioned areas: {target_path}"
            )

        # Validate file extension
        validate_file_extension(target_path, "mame", policies)

        # Filter allowed keys
        filtered_patch = filter_allowed_keys(config_req.patch, "mame", policies)

        # Read current content
        if target_path.exists():
            with open(target_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
        else:
            current_content = ""
            # Ensure parent directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)

        # Apply patch to MAME config format
        new_lines = current_content.splitlines() if current_content else []

        for key, value in filtered_patch.items():
            # MAME config format: key    value
            found = False
            for i, line in enumerate(new_lines):
                # Skip comments and empty lines
                if line.strip().startswith('#') or not line.strip():
                    continue

                # Check if line starts with our key
                parts = line.strip().split(None, 1)
                if parts and parts[0] == key:
                    new_lines[i] = f"{key}    {value}"
                    found = True
                    break

            # Add new key if not found
            if not found:
                new_lines.append(f"{key}    {value}")

        new_content = "\n".join(new_lines)

        # Check if changes exist
        if not has_changes(current_content, new_content):
            return {
                "status": "no_changes",
                "config_file": config_req.config_file,
                "backup_path": None
            }

        backup_path = None

        # Create backup if not dry run and backup is enabled
        if not config_req.dry_run:
            if target_path.exists() and request.app.state.backup_on_write:
                backup_path = create_backup(target_path, drive_root)

            # Write new content
            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

        # Log the change
        if not config_req.dry_run:
            log_mame_change(
                drive_root,
                "config_apply",
                {
                    "config_file": config_req.config_file,
                    "changes_count": len(filtered_patch),
                    "keys_changed": list(filtered_patch.keys()),
                },
                backup_path,
            )

        return {
            "status": "applied" if not config_req.dry_run else "dry_run",
            "config_file": config_req.config_file,
            "target_path": str(target_path),
            "backup_path": str(backup_path) if backup_path else None,
            "patch_applied": filtered_patch,
            "changes_count": len(filtered_patch)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/preview")
async def preview_mame_config(request: Request, config_req: MAMEConfigRequest):
    """Preview MAME config changes"""

    try:
        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        policies = request.app.state.policies

        # Get MAME paths from manifest
        mame_config = manifest.get("emulators", {}).get("mame", {})
        if not mame_config:
            raise HTTPException(
                status_code=400,
                detail="MAME not configured in manifest.json"
            )

        # Determine full path
        if config_req.config_file.endswith('.cfg'):
            base_dir = mame_config.get("cfg_dir", "emulators/mame/cfg")
        elif config_req.config_file.endswith('.ini'):
            base_dir = mame_config.get("ini_dir", "emulators/mame/ini")
        else:
            raise HTTPException(
                status_code=400,
                detail="Config file must be .cfg or .ini"
            )

        target_path = drive_root / base_dir / Path(config_req.config_file).name

        # Validate path is in sanctioned areas
        if not is_allowed_file(target_path, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(
                status_code=403,
                detail=f"File not in sanctioned areas: {target_path}"
            )

        # Filter allowed keys
        filtered_patch = filter_allowed_keys(config_req.patch, "mame", policies)

        # Read current content
        if target_path.exists():
            with open(target_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
        else:
            current_content = ""

        # Apply patch preview
        new_lines = current_content.splitlines() if current_content else []

        for key, value in filtered_patch.items():
            found = False
            for i, line in enumerate(new_lines):
                if line.strip().startswith('#') or not line.strip():
                    continue

                parts = line.strip().split(None, 1)
                if parts and parts[0] == key:
                    new_lines[i] = f"{key}    {value}"
                    found = True
                    break

            if not found:
                new_lines.append(f"{key}    {value}")

        new_content = "\n".join(new_lines)

        # Generate diff
        diff = compute_diff(current_content, new_content, config_req.config_file)

        return {
            "config_file": config_req.config_file,
            "target_path": str(target_path),
            "has_changes": has_changes(current_content, new_content),
            "diff": diff,
            "patch_applied": filtered_patch,
            "file_exists": target_path.exists()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
