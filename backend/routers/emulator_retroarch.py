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
from ..services.audit_log import append_pause_event

logger = logging.getLogger(__name__)
router = APIRouter()


def log_retroarch_change(drive_root: Path, action: str, details: Dict[str, Any], backup_path=None):
    """Log RetroArch config changes to changes.jsonl"""
    log_file = drive_root / ".aa" / "logs" / "changes.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "scope": "emulator",
        "panel": "retroarch",
        "action": action,
        "details": details,
        "backup_path": str(backup_path) if backup_path else None,
    }
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as exc:
        logger.warning(f"Failed to log change: {exc}")

class RetroArchConfigRequest(BaseModel):
    patch: Dict[str, Any]
    dry_run: bool = False

@router.post("/config/patch")
async def patch_retroarch_config(request: Request, config_req: RetroArchConfigRequest):
    """Apply structured patch to retroarch.cfg"""

    try:
        # Validate scope header
        require_scope(request, "config")

        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        policies = request.app.state.policies

        # Get RetroArch config path from manifest
        retroarch_config = manifest.get("emulators", {}).get("retroarch", {})
        if not retroarch_config:
            raise HTTPException(
                status_code=400,
                detail="RetroArch not configured in manifest.json"
            )

        config_path = retroarch_config.get("cfg", "emulators/retroarch/config/retroarch.cfg")
        target_path = drive_root / config_path

        # Validate path is in sanctioned areas
        if not is_allowed_file(target_path, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(
                status_code=403,
                detail=f"File not in sanctioned areas: {target_path}"
            )

        # Validate file extension
        validate_file_extension(target_path, "retroarch", policies)

        # Filter allowed keys
        filtered_patch = filter_allowed_keys(config_req.patch, "retroarch", policies)

        # Read current content
        if target_path.exists():
            with open(target_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
        else:
            current_content = ""
            # Ensure parent directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)

        # Apply patch to RetroArch config format
        new_lines = current_content.splitlines() if current_content else []

        for key, value in filtered_patch.items():
            # RetroArch config format: key = "value"
            found = False
            for i, line in enumerate(new_lines):
                # Skip comments and empty lines
                if line.strip().startswith('#') or not line.strip():
                    continue

                # Check if line contains our key
                if '=' in line:
                    config_key = line.split('=')[0].strip()
                    if config_key == key:
                        # Format value based on type
                        if isinstance(value, str):
                            new_lines[i] = f'{key} = "{value}"'
                        elif isinstance(value, bool):
                            new_lines[i] = f'{key} = "{str(value).lower()}"'
                        else:
                            new_lines[i] = f'{key} = "{value}"'
                        found = True
                        break

            # Add new key if not found
            if not found:
                if isinstance(value, str):
                    new_lines.append(f'{key} = "{value}"')
                elif isinstance(value, bool):
                    new_lines.append(f'{key} = "{str(value).lower()}"')
                else:
                    new_lines.append(f'{key} = "{value}"')

        new_content = "\n".join(new_lines)

        # Check if changes exist
        if not has_changes(current_content, new_content):
            return {
                "status": "no_changes",
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
            log_retroarch_change(
                drive_root,
                "config_patch",
                {
                    "config_path": config_path,
                    "changes_count": len(filtered_patch),
                    "keys_changed": list(filtered_patch.keys()),
                },
                backup_path,
            )

        return {
            "status": "applied" if not config_req.dry_run else "dry_run",
            "config_path": config_path,
            "target_path": str(target_path),
            "backup_path": str(backup_path) if backup_path else None,
            "patch_applied": filtered_patch,
            "changes_count": len(filtered_patch)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/network/enable")
async def enable_network_cmd(request: Request):
    """Enable RetroArch UDP network commands with defaults (idempotent).

    Returns: { changed:boolean, diff:string, backup_path:string, file:string }
    """
    try:
        # Validate scope header
        require_scope(request, "config")

        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        policies = request.app.state.policies

        retroarch_config = manifest.get("emulators", {}).get("retroarch", {})
        if not retroarch_config:
            raise HTTPException(status_code=400, detail="RetroArch not configured in manifest.json")

        config_path = retroarch_config.get("cfg", "emulators/retroarch/config/retroarch.cfg")
        target_path = drive_root / config_path

        if not is_allowed_file(target_path, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(status_code=403, detail=f"File not in sanctioned areas: {target_path}")
        validate_file_extension(target_path, "retroarch", policies)

        before = ""
        if target_path.exists():
            with open(target_path, "r", encoding="utf-8") as f:
                before = f.read()
        else:
            target_path.parent.mkdir(parents=True, exist_ok=True)

        desired = {
            "network_cmd_enable": "true",
            "network_cmd_port": "55355",
        }

        # Merge
        existing_lines = before.splitlines() if before else []
        new_lines = []
        seen = set()
        for line in existing_lines:
            s = line.strip()
            if not s or s.startswith("#"):
                new_lines.append(line)
                continue
            if "=" in s:
                k = s.split("=", 1)[0].strip()
                lk = k.lower()
                if lk in desired:
                    new_lines.append(f"{k} = \"{desired[lk]}\"")
                    seen.add(lk)
                    continue
            new_lines.append(line)

        for k, v in desired.items():
            if k not in seen:
                new_lines.append(f"{k} = \"{v}\"")

        after = "\n".join(new_lines) + ("\n" if new_lines else "")
        diff = compute_diff(before, after, "retroarch.cfg")
        changed = (before != after)

        backup_path = None
        if changed:
            if target_path.exists() and request.app.state.backup_on_write:
                backup_path = create_backup(target_path, drive_root)
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(after)

        append_pause_event("retroarch", "preflight", "ok", "network_cmd_enable=true")
        
        # Log the change
        if changed:
            log_retroarch_change(
                drive_root,
                "network_enable",
                {
                    "config_path": config_path,
                    "network_cmd_enable": True,
                    "network_cmd_port": 55355,
                },
                backup_path,
            )
        
        return {
            "changed": bool(changed),
            "diff": diff,
            "backup_path": str(backup_path) if backup_path else None,
            "file": str(target_path),
        }
    except HTTPException:
        raise
    except Exception as e:
        append_pause_event("retroarch", "preflight", "error", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/config/preview")
async def preview_retroarch_config(request: Request, config_req: RetroArchConfigRequest):
    """Preview RetroArch config changes"""

    try:
        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        policies = request.app.state.policies

        # Get RetroArch config path from manifest
        retroarch_config = manifest.get("emulators", {}).get("retroarch", {})
        if not retroarch_config:
            raise HTTPException(
                status_code=400,
                detail="RetroArch not configured in manifest.json"
            )

        config_path = retroarch_config.get("cfg", "emulators/retroarch/config/retroarch.cfg")
        target_path = drive_root / config_path

        # Validate path is in sanctioned areas
        if not is_allowed_file(target_path, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(
                status_code=403,
                detail=f"File not in sanctioned areas: {target_path}"
            )

        # Filter allowed keys
        filtered_patch = filter_allowed_keys(config_req.patch, "retroarch", policies)

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

                if '=' in line:
                    config_key = line.split('=')[0].strip()
                    if config_key == key:
                        if isinstance(value, str):
                            new_lines[i] = f'{key} = "{value}"'
                        elif isinstance(value, bool):
                            new_lines[i] = f'{key} = "{str(value).lower()}"'
                        else:
                            new_lines[i] = f'{key} = "{value}"'
                        found = True
                        break

            if not found:
                if isinstance(value, str):
                    new_lines.append(f'{key} = "{value}"')
                elif isinstance(value, bool):
                    new_lines.append(f'{key} = "{str(value).lower()}"')
                else:
                    new_lines.append(f'{key} = "{value}"')

        new_content = "\n".join(new_lines)

        # Generate diff
        diff = compute_diff(current_content, new_content, "retroarch.cfg")

        return {
            "config_path": config_path,
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
