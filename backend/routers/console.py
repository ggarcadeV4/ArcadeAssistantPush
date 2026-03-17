"""Console Controller Router

REST endpoints for console controller detection and profile management.
Supports Xbox, PlayStation, and Nintendo Switch controllers.
"""

from fastapi import APIRouter, HTTPException, Query, Request, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import json
import logging

from ..services.gamepad_detector import (
    detect_controllers,
    get_controller_by_profile_id,
    get_available_profiles,
    get_profile_details,
    invalidate_cache,
    GamepadDetectionError,
    ProfileLoadError
)
from ..services.usb_detector import (
    USBBackendError,
    USBPermissionError,
    USBDetectionError,
    get_connection_troubleshooting_hints
)
from ..services.retroarch_config_generator import (
    generate_retroarch_config,
    validate_retroarch_config,
    get_retroarch_config_summary,
    RetroArchConfigError
)
from ..services.backup import create_backup, restore_from_backup
from ..services.diffs import compute_diff, has_changes
from ..services.policies import require_scope, is_allowed_file
from ..services.controller_cascade import enqueue_cascade_job, run_cascade_job
from ..services.controller_baseline import get_cascade_preference

logger = logging.getLogger(__name__)
router = APIRouter()


class ControllerDetectionResponse(BaseModel):
    """Response model for controller detection"""
    controllers: List[Dict[str, Any]]
    count: int
    cache_used: bool = True


class ProfileListResponse(BaseModel):
    """Response model for profile listing"""
    profiles: List[Dict[str, Any]]
    count: int


class ProfileDetailResponse(BaseModel):
    """Response model for single profile details"""
    profile: Dict[str, Any]
    detected: bool = False


class RetroArchConfigRequest(BaseModel):
    """Request model for RetroArch config generation"""
    profile_id: str
    player: int = 1
    system: Optional[str] = None
    include_hotkeys: bool = True
    include_deadzones: bool = True
    mappings: Optional[Dict[str, Any]] = None  # Custom button mappings from wizard
    deadzone: Optional[float] = None  # Custom deadzone from calibration


class RetroArchRestoreRequest(BaseModel):
    """Request model for RetroArch restore operations"""
    backup_path: str
    target_file: Optional[str] = None
    dry_run: Optional[bool] = None


# Utility functions
def log_console_wizard_change(
    request: Request,
    drive_root: Path,
    action: str,
    details: Dict[str, Any],
    backup_path: Optional[Path] = None
):
    """Log Console Wizard changes to changes.jsonl"""
    log_file = drive_root / ".aa" / "logs" / "changes.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    device = request.headers.get('x-device-id', 'unknown') if hasattr(request, 'headers') else 'unknown'
    panel = request.headers.get('x-panel', 'console_wizard') if hasattr(request, 'headers') else 'console_wizard'

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "scope": "console_wizard",
        "action": action,
        "details": details,
        "backup_path": str(backup_path) if backup_path else None,
        "device": device,
        "panel": panel,
    }

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry) + "\n")


def infer_target_from_backup(drive_root: Path, backup_file: Path) -> Optional[Path]:
    """Best-effort reconstruction of original config path from backup filename."""
    name = backup_file.name
    parts = name.split('_', 1)
    if len(parts) < 2:
        return None
    remainder = parts[1]
    prefix = "config_retroarch_"
    if remainder.startswith(prefix):
        relative = Path("config") / "retroarch" / remainder[len(prefix):]
        return (drive_root / relative).resolve()
    return None


@router.get("/controllers", response_model=ControllerDetectionResponse)
async def get_connected_controllers(
    use_cache: bool = Query(default=True, description="Use cached results if available")
):
    """Get all connected console controllers

    Detects Xbox, PlayStation, and Switch controllers via USB.
    Matches detected devices to controller profiles for button/axis mappings.

    Query Parameters:
        - use_cache: Use cached results (5-second TTL) for performance

    Returns:
        List of detected controllers with profile information

    Example Response:
    ```json
    {
        "controllers": [
            {
                "vid": "0x045e",
                "pid": "0x028e",
                "vid_pid": "045e:028e",
                "profile_id": "xbox_360",
                "name": "Xbox 360 Controller",
                "manufacturer": "Microsoft",
                "type": "console_gamepad",
                "detected": true,
                "has_profile": true,
                "button_count": 11,
                "axis_count": 6,
                "features": {"xinput": true}
            }
        ],
        "count": 1,
        "cache_used": true
    }
    ```
    """
    try:
        logger.info("Controller detection endpoint called")
        controllers = detect_controllers(use_cache=use_cache)
        logger.info(f"Controller detection successful: found {len(controllers)} controllers")

        return ControllerDetectionResponse(
            controllers=controllers,
            count=len(controllers),
            cache_used=use_cache
        )

    except USBBackendError as e:
        logger.warning(f"USB backend unavailable: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "usb_backend_unavailable",
                "message": str(e),
                "hints": get_connection_troubleshooting_hints("gamepad")[:3]
            }
        )
    except USBPermissionError as e:
        logger.warning(f"USB permission denied: {e}")
        raise HTTPException(
            status_code=403,
            detail={
                "error": "usb_permission_denied",
                "message": str(e),
                "hints": ["Run as administrator/root", "Add user to plugdev group (Linux)"]
            }
        )
    except GamepadDetectionError as e:
        logger.error(f"Controller detection failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "controller_detection_failed",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error in controller detection: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "unexpected_error",
                "message": f"{type(e).__name__}: {str(e)}",
                "hint": "Check backend logs for full traceback"
            }
        )


@router.get("/profiles", response_model=ProfileListResponse)
async def list_controller_profiles():
    """Get list of all available controller profiles

    Returns all supported controller profiles with basic metadata.
    Profiles contain button/axis mappings and RetroArch configurations.

    Returns:
        List of available profiles (Xbox, PlayStation, Switch, etc.)

    Example Response:
    ```json
    {
        "profiles": [
            {
                "profile_id": "xbox_360",
                "name": "Xbox 360 Controller",
                "manufacturer": "Microsoft",
                "type": "console_gamepad",
                "button_count": 11,
                "axis_count": 6,
                "features": {"xinput": true},
                "notes": "Standard Xbox 360 controller layout...",
                "version": "1.0"
            }
        ],
        "count": 3
    }
    ```
    """
    try:
        profiles = get_available_profiles()

        return ProfileListResponse(
            profiles=profiles,
            count=len(profiles)
        )

    except ProfileLoadError as e:
        logger.error(f"Profile loading failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "profile_load_failed",
                "message": str(e),
                "hint": "Check that profile JSON files exist in backend/data/controller_profiles/"
            }
        )
    except Exception as e:
        logger.error(f"Failed to list profiles: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve profiles: {str(e)}"
        )


@router.get("/profiles/{profile_id}", response_model=ProfileDetailResponse)
async def get_profile(profile_id: str):
    """Get detailed information for a specific controller profile

    Returns full profile details including button mappings, axis configurations,
    RetroArch defaults, and feature flags.

    Args:
        profile_id: Profile identifier (e.g., 'xbox_360', 'ps4_dualshock', 'switch_pro')

    Returns:
        Complete profile data with button/axis details

    Example Response:
    ```json
    {
        "profile": {
            "profile_id": "xbox_360",
            "name": "Xbox 360 Controller",
            "manufacturer": "Microsoft",
            "type": "console_gamepad",
            "usb_identifiers": [
                {"vid": "045e", "pid": "028e", "description": "Xbox 360 Wired Controller"}
            ],
            "buttons": {
                "a": {"index": 0, "label": "A", "color": "green"},
                "b": {"index": 1, "label": "B", "color": "red"}
            },
            "dpad": {
                "up": {"index": 12, "label": "D-Pad Up"}
            },
            "axes": {
                "left_stick_x": {"index": 0, "label": "Left Stick X", "deadzone": 0.15}
            },
            "retroarch_defaults": {
                "input_device": "Xbox 360 Controller",
                "input_a_btn": "1"
            },
            "features": {"xinput": true},
            "notes": "Standard Xbox 360 controller layout...",
            "version": "1.0"
        },
        "detected": true
    }
    ```
    """
    try:
        profile = get_profile_details(profile_id)

        if profile is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "profile_not_found",
                    "message": f"Profile '{profile_id}' not found",
                    "profile_id": profile_id,
                    "hint": "Use GET /api/local/console/profiles to see available profiles"
                }
            )

        # Check if a controller with this profile is currently connected
        controller = get_controller_by_profile_id(profile_id)
        detected = controller is not None

        return ProfileDetailResponse(
            profile=profile,
            detected=detected
        )

    except HTTPException:
        raise
    except ProfileLoadError as e:
        logger.error(f"Profile loading failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "profile_load_failed",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Failed to get profile details: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve profile: {str(e)}"
        )


@router.post("/invalidate-cache")
async def invalidate_controller_cache():
    """Invalidate the controller detection cache

    Forces the next controller detection call to re-enumerate USB devices.
    Use this when you know a controller has been plugged/unplugged.

    Returns:
        Success confirmation
    """
    try:
        invalidate_cache()
        return {
            "status": "cache_invalidated",
            "message": "Controller cache cleared. Next detection will re-enumerate."
        }
    except Exception as e:
        logger.error(f"Failed to invalidate cache: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Cache invalidation failed: {str(e)}"
        )


@router.get("/health")
async def console_health_check():
    """Health check for console controller subsystem

    Verifies that:
    - Controller profiles can be loaded
    - USB backend is available for detection
    - Detection subsystem is operational

    Returns:
        System status and any error messages
    """
    import platform

    status_info = {
        "status": "healthy",
        "platform": platform.system(),
        "profile_status": "unknown",
        "usb_backend": "unknown",
        "error": None
    }

    # Check profile loading
    try:
        profiles = get_available_profiles()
        status_info["profile_status"] = "loaded"
        status_info["profile_count"] = len(profiles)
    except ProfileLoadError as e:
        status_info["status"] = "degraded"
        status_info["profile_status"] = "failed"
        status_info["error"] = f"Profile loading failed: {str(e)}"
        return status_info
    except Exception as e:
        status_info["status"] = "degraded"
        status_info["profile_status"] = "error"
        status_info["error"] = str(e)
        return status_info

    # Check USB detection
    try:
        controllers = detect_controllers(use_cache=False)
        status_info["usb_backend"] = "available"
        status_info["detected_controllers"] = len(controllers)
    except USBBackendError as e:
        status_info["status"] = "degraded"
        status_info["usb_backend"] = "backend_unavailable"
        status_info["error"] = str(e)
    except USBPermissionError as e:
        status_info["status"] = "degraded"
        status_info["usb_backend"] = "permission_denied"
        status_info["error"] = str(e)
    except GamepadDetectionError as e:
        status_info["status"] = "degraded"
        status_info["usb_backend"] = "detection_error"
        status_info["error"] = str(e)

    return status_info


# ========== RetroArch Config Generation Endpoints ==========

@router.post("/retroarch/config/preview")
@router.post("/retroarch/preview")
async def preview_retroarch_config(request: Request, config_request: RetroArchConfigRequest):
    """Preview RetroArch config generated from controller profile

    Generates RetroArch .cfg file content from the specified controller profile
    without writing to disk. Returns config content, validation results,
    and summary statistics.

    Args:
        config_request: RetroArch config generation parameters

    Returns:
        Preview with config content, validation, and summary
    """
    try:
        # Get the profile
        profile = get_profile_details(config_request.profile_id)

        if profile is None:
            raise HTTPException(
                status_code=404,
                detail=f"Profile '{config_request.profile_id}' not found"
            )

        # Generate RetroArch config
        cfg_content = generate_retroarch_config(
            profile=profile,
            player=config_request.player,
            system=config_request.system,
            include_hotkeys=config_request.include_hotkeys,
            include_deadzones=config_request.include_deadzones,
            custom_mappings=config_request.mappings,
            deadzone_override=config_request.deadzone,
        )

        # Validate generated config
        validation_errors = validate_retroarch_config(cfg_content)

        # Get summary statistics
        summary = get_retroarch_config_summary(cfg_content)

        # Determine target file path
        system_part = f"_{config_request.system}" if config_request.system else ""
        target_file = f"config/retroarch/{config_request.profile_id}{system_part}_p{config_request.player}.cfg"

        return {
            "cfg_content": cfg_content,
            "validation": {
                "valid": len(validation_errors) == 0,
                "errors": validation_errors
            },
            "summary": summary,
            "source_profile": config_request.profile_id,
            "target_file": target_file,
            "player": config_request.player,
            "system": config_request.system
        }

    except RetroArchConfigError as e:
        raise HTTPException(
            status_code=400,
            detail=f"RetroArch config generation failed: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RetroArch config preview error: {e}")
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")


@router.post("/retroarch/config/apply")
@router.post("/retroarch/apply")
async def apply_retroarch_config(request: Request, config_request: RetroArchConfigRequest, background_tasks: BackgroundTasks):
    """Generate and write RetroArch config from controller profile

    Creates RetroArch .cfg file from the specified controller profile,
    validates it, and writes to config/retroarch/ with backup.

    Args:
        config_request: RetroArch config generation parameters

    Returns:
        Apply status with backup path and summary
    """
    try:
        # Validate scope header
        require_scope(request, "config")

        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest

        # Get the profile
        profile = get_profile_details(config_request.profile_id)

        if profile is None:
            raise HTTPException(
                status_code=404,
                detail=f"Profile '{config_request.profile_id}' not found"
            )

        # Determine config file path
        system_part = f"_{config_request.system}" if config_request.system else ""
        filename = f"{config_request.profile_id}{system_part}_p{config_request.player}.cfg"
        config_file = drive_root / "config" / "retroarch" / filename

        # Validate path is in sanctioned areas
        if not is_allowed_file(config_file, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(
                status_code=403,
                detail=f"RetroArch config path not in sanctioned areas: {config_file}"
            )

        # Generate RetroArch config
        cfg_content = generate_retroarch_config(
            profile=profile,
            player=config_request.player,
            system=config_request.system,
            include_hotkeys=config_request.include_hotkeys,
            include_deadzones=config_request.include_deadzones,
            custom_mappings=config_request.mappings,
            deadzone_override=config_request.deadzone,
        )

        # Validate generated config
        validation_errors = validate_retroarch_config(cfg_content)
        if validation_errors:
            raise HTTPException(
                status_code=400,
                detail=f"Generated RetroArch config failed validation: {', '.join(validation_errors)}"
            )

        # Ensure directory exists
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # Create backup if file exists
        backup_path = None
        if config_file.exists() and request.app.state.backup_on_write:
            backup_path = create_backup(config_file, drive_root)

        # Write RetroArch config
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(cfg_content)

        # Get summary for response
        summary = get_retroarch_config_summary(cfg_content)

        # Log the change
        log_console_wizard_change(
            request, drive_root, "retroarch_config_apply",
            {
                "action": "generate_retroarch_config",
                "profile_id": config_request.profile_id,
                "player": config_request.player,
                "system": config_request.system,
                "button_count": summary["button_count"],
                "axis_count": summary["axis_count"],
                "has_deadzones": summary["has_deadzones"],
                "has_hotkeys": summary["has_hotkeys"]
            },
            backup_path
        )

        # Trigger cascade to propagate gamepad config to all emulators
        device_id = request.headers.get("x-device-id", "console-wizard")
        cascade_pref = get_cascade_preference(drive_root)
        
        if cascade_pref == "auto":
            # Auto-trigger cascade in background
            job_record = enqueue_cascade_job(
                drive_root,
                requested_by=device_id,
                metadata={"source": "console_wizard", "profile_id": config_request.profile_id, "player": config_request.player},
                backup=request.app.state.backup_on_write,
            )
            background_tasks.add_task(
                run_cascade_job,
                drive_root,
                manifest,
                job_record["job_id"],
                backup=request.app.state.backup_on_write,
            )
            logger.info(f"[Console Wizard] Auto-cascade triggered: job_id={job_record['job_id']}")

        return {
            "status": "applied",
            "target_file": f"config/retroarch/{filename}",
            "backup_path": str(backup_path) if backup_path else None,
            "summary": summary,
            "validation": {
                "valid": True,
                "errors": []
            },
            "profile_id": config_request.profile_id,
            "player": config_request.player,
            "cascade_triggered": cascade_pref == "auto"
        }

    except RetroArchConfigError as e:
        raise HTTPException(
            status_code=400,
            detail=f"RetroArch config generation failed: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RetroArch config apply error: {e}")
        raise HTTPException(status_code=500, detail=f"Apply failed: {str(e)}")


@router.post("/retroarch/restore")
async def restore_retroarch_config(request: Request, restore_request: RetroArchRestoreRequest):
    """Restore RetroArch configs from a recorded backup snapshot."""
    try:
        require_scope(request, "config")

        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest

        backup_path = Path(restore_request.backup_path)
        if not backup_path.is_absolute():
            backup_path = (drive_root / backup_path).resolve()
        else:
            backup_path = backup_path.resolve()

        backup_root = (drive_root / ".aa" / "backups").resolve()
        try:
            backup_path.relative_to(backup_root)
        except ValueError:
            raise HTTPException(
                status_code=403,
                detail="Backup path must live under drive_root/.aa/backups"
            )

        if not backup_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Backup not found: {backup_path}"
            )

        target_file = restore_request.target_file
        target_path: Optional[Path] = None
        if target_file:
            temp_path = Path(target_file)
            if not temp_path.is_absolute():
                temp_path = drive_root / temp_path
            target_path = temp_path.resolve()
            target_file = str(target_path.relative_to(drive_root))
        else:
            target_path = infer_target_from_backup(drive_root, backup_path)
            if target_path is None:
                raise HTTPException(
                    status_code=400,
                    detail="target_file is required for this backup"
                )
            target_file = str(target_path.relative_to(drive_root))

        if not is_allowed_file(target_path, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(
                status_code=403,
                detail=f"Target path not sanctioned: {target_file}"
            )

        if target_path.exists():
            current_content = target_path.read_text(encoding='utf-8')
        else:
            current_content = ""

        backup_content = backup_path.read_text(encoding='utf-8')
        diff_text = compute_diff(current_content, backup_content, target_file)
        has_diff = has_changes(current_content, backup_content)
        diff_line_count = diff_text.count("\n")

        dry_default = getattr(request.app.state, "dry_run_default", True)
        effective_dry = (
            restore_request.dry_run
            if restore_request.dry_run is not None
            else dry_default
        )

        pre_restore_backup = None
        if not effective_dry:
            if target_path.exists() and request.app.state.backup_on_write:
                pre_restore_backup = create_backup(target_path, drive_root)

            restore_from_backup(backup_path, target_path)

            summary = get_retroarch_config_summary(backup_content)
            log_console_wizard_change(
                request,
                drive_root,
                "retroarch_config_restore",
                {
                    "restored_from": str(backup_path),
                    "target_file": target_file,
                    "lines_changed": diff_line_count,
                    "button_count": summary["button_count"],
                    "axis_count": summary["axis_count"],
                },
                pre_restore_backup,
            )
        else:
            summary = get_retroarch_config_summary(backup_content)

        message = (
            "Preview restore diff generated (dry-run)"
            if effective_dry
            else f"RetroArch config restored from {backup_path.name}"
        )

        return {
            "restored": bool(has_diff and not effective_dry),
            "dry_run": effective_dry,
            "backup_path": str(backup_path),
            "target_file": target_file,
            "diff": diff_text,
            "summary": summary,
            "pre_restore_backup": str(pre_restore_backup) if pre_restore_backup else None,
            "message": message,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RetroArch config restore error: {e}")
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")


@router.get("/retroarch/config/validate")
async def validate_existing_retroarch_config(
    request: Request,
    profile_id: str = Query(..., description="Profile ID (e.g., 'xbox_360')"),
    player: int = Query(default=1, description="Player number (1-4)"),
    system: Optional[str] = Query(default=None, description="Optional system override")
):
    """Validate existing RetroArch config file

    Reads the existing config/retroarch/...cfg file (if it exists)
    and validates it for well-formed structure and correctness.

    Args:
        profile_id: Profile identifier (e.g., 'xbox_360', 'ps4_dualshock')
        player: Player number (1-4)
        system: Optional system override (e.g., 'snes', 'genesis')

    Returns:
        Validation results and summary
    """
    try:
        drive_root = request.app.state.drive_root

        # Determine config file path
        system_part = f"_{system}" if system else ""
        filename = f"{profile_id}{system_part}_p{player}.cfg"
        config_file = drive_root / "config" / "retroarch" / filename

        if not config_file.exists():
            return {
                "exists": False,
                "file_path": f"config/retroarch/{filename}",
                "validation": {
                    "valid": False,
                    "errors": ["File does not exist"]
                },
                "summary": None,
                "profile_id": profile_id,
                "player": player,
                "system": system
            }

        # Read existing RetroArch config
        with open(config_file, 'r', encoding='utf-8') as f:
            cfg_content = f.read()

        # Validate
        validation_errors = validate_retroarch_config(cfg_content)

        # Get summary
        summary = get_retroarch_config_summary(cfg_content)

        return {
            "exists": True,
            "file_path": f"config/retroarch/{filename}",
            "validation": {
                "valid": len(validation_errors) == 0,
                "errors": validation_errors
            },
            "summary": summary,
            "profile_id": profile_id,
            "player": player,
            "system": system
        }

    except Exception as e:
        logger.error(f"RetroArch config validation error: {e}")
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


# ========== TeknoParrot Config Generation Endpoints ==========

class TeknoParrotConfigRequest(BaseModel):
    """Request model for TeknoParrot config generation"""
    profile_name: str  # e.g., "InitialD8", "HOTD4"
    game_category: Optional[str] = None  # "racing", "lightgun", "generic"
    player: int = 1


@router.post("/teknoparrot/config/preview")
@router.post("/teknoparrot/preview")
async def preview_teknoparrot_config(request: Request, config_request: TeknoParrotConfigRequest):
    """Preview TeknoParrot config generated from current mappings

    Generates TeknoParrot input binding mapping from the current arcade
    panel controls without writing to disk. Returns binding preview,
    category detection, and summary statistics.

    Args:
        config_request: TeknoParrot config generation parameters

    Returns:
        Preview with bindings, validation, and summary
    """
    try:
        from ..services.console_wizard_manager import ConsoleWizardManager
        from ..services.teknoparrot_config_generator import (
            get_schema_for_game,
            build_canonical_mapping,
            preview_tp_config,
            TPGameCategory,
        )

        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest or {}
        
        manager = ConsoleWizardManager(drive_root, manifest)
        
        # Load current panel mappings
        controls_blob = manager.mapping_service.load_current()
        controls = controls_blob.get("mappings") or {}
        
        if not controls:
            raise HTTPException(
                status_code=404,
                detail="controls.json is empty - run Controller Chuck first."
            )
        
        # Get game schema
        schema = get_schema_for_game(config_request.profile_name)
        category = config_request.game_category or (schema.category.value if schema else "generic")
        
        # Build canonical mapping
        canonical = build_canonical_mapping(
            config_request.profile_name,
            controls,
            player=config_request.player,
        )
        
        if canonical is None:
            # Use generic mapping from wizard
            tp_mapping = manager._teknoparrot_mapping(controls)
            return {
                "profile": config_request.profile_name,
                "category": "generic",
                "supported": False,
                "bindings": tp_mapping.get("bindings", {}),
                "summary": {
                    "controls_mapped": len(tp_mapping.get("bindings", {})),
                    "required_controls": [],
                    "optional_controls": [],
                },
                "message": f"Game '{config_request.profile_name}' not in known database; using generic mapping."
            }
        
        # Check for existing profile path
        profiles_dir = drive_root / "Emulators" / "TeknoParrot" / "UserProfiles"
        profile_path = profiles_dir / canonical.profile
        
        preview = preview_tp_config(profile_path, canonical)
        
        return {
            "profile": canonical.profile,
            "profile_path": preview.profile_path,
            "category": category,
            "supported": True,
            "has_changes": preview.has_changes,
            "changes_count": preview.changes_count,
            "file_exists": preview.file_exists,
            "bindings": canonical.to_dict()["controls"],
            "diffs": preview.to_dict()["diffs"],
            "summary": {
                "controls_mapped": len(canonical.controls),
                "required_controls": canonical.metadata.get("required_controls", []),
                "optional_controls": canonical.metadata.get("optional_controls", []),
            },
            "message": preview.summary,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TeknoParrot config preview error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")


@router.post("/teknoparrot/config/apply")
@router.post("/teknoparrot/apply")
async def apply_teknoparrot_config(
    request: Request,
    config_request: TeknoParrotConfigRequest,
    background_tasks: BackgroundTasks,
):
    """Generate and apply TeknoParrot config from current mappings

    Creates TeknoParrot input bindings from the current arcade panel controls
    and updates the UserProfile XML with backup.

    Flow:
    1. Build canonical mapping from Chuck's controls.json
    2. Preview diff against current TP profile
    3. Create backup of original XML
    4. Write updated bindings to XML
    5. Log changes to changes.jsonl with before/after values
    6. Update controller baseline

    Args:
        config_request: TeknoParrot config generation parameters

    Returns:
        Apply status with detailed changes
    """
    try:
        require_scope(request, "config")

        from ..services.console_wizard_manager import ConsoleWizardManager
        from ..services.teknoparrot_config_generator import (
            build_canonical_mapping,
            apply_tp_config,
            create_sample_profile,
            TPGameCategory,
        )
        from ..services.controller_baseline import update_controller_baseline

        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest or {}

        manager = ConsoleWizardManager(drive_root, manifest)

        # Load current panel mappings
        controls_blob = manager.mapping_service.load_current()
        controls = controls_blob.get("mappings") or {}

        if not controls:
            raise HTTPException(
                status_code=404,
                detail="controls.json is empty - run Controller Chuck first."
            )

        # Build canonical mapping
        canonical = build_canonical_mapping(
            config_request.profile_name,
            controls,
            player=config_request.player,
        )

        if canonical is None:
            raise HTTPException(
                status_code=400,
                detail=f"Game '{config_request.profile_name}' is not in the known games database. Supported categories: racing, lightgun, fighting, generic"
            )

        # Determine TeknoParrot profile path
        # Try multiple possible locations
        tp_candidates = [
            drive_root / "Emulators" / "TeknoParrot" / "UserProfiles" / canonical.profile,
            drive_root / "Emulators" / "TeknoParrot Latest" / "UserProfiles" / canonical.profile,
        ]
        
        profile_path = None
        for candidate in tp_candidates:
            if candidate.exists():
                profile_path = candidate
                break
        
        # If no profile exists, create a sample one for testing
        if profile_path is None:
            # Use the first candidate location
            profile_path = tp_candidates[0]
            
            # Create sample profile for testing
            created = create_sample_profile(
                profile_path,
                profile_name=config_request.profile_name,
                category=canonical.category,
            )
            
            if not created:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to create TeknoParrot profile at {profile_path}"
                )
            
            logger.info(f"Created sample TeknoParrot profile for testing: {profile_path}")

        # Apply the config (backup → write XML → log)
        result = apply_tp_config(
            profile_path=profile_path,
            canonical=canonical,
            drive_root=drive_root,
            backup=request.app.state.backup_on_write,
        )

        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to apply TeknoParrot config: {result.error}"
            )

        # Update controller baseline for cascade awareness
        update_controller_baseline(
            drive_root,
            {
                "emulators": {
                    "teknoparrot": {
                        "status": "configured",
                        "last_game": config_request.profile_name,
                        "last_profile_path": str(profile_path),
                        "last_applied": result.log_entry,
                        "changes_count": result.changes_applied,
                        "message": f"Applied {result.changes_applied} binding changes to {canonical.profile}",
                    }
                }
            },
            backup=False,  # Already backed up the XML
        )

        return {
            "status": "applied",
            "success": True,
            "profile": canonical.profile,
            "profile_path": str(profile_path),
            "category": canonical.category.value,
            "player": config_request.player,
            "changes_applied": result.changes_applied,
            "changes_detail": result.changes_detail,
            "backup_path": result.backup_path,
            "log_entry": result.log_entry,
            "baseline_updated": True,
            "xml_written": True,
            "message": f"Applied {result.changes_applied} binding changes to {canonical.profile}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TeknoParrot config apply error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Apply failed: {str(e)}")


@router.get("/teknoparrot/games")
async def list_teknoparrot_games():
    """List supported TeknoParrot games with category info

    Returns all games that have canonical control schemas defined.
    """
    try:
        from ..services.teknoparrot_config_generator import get_supported_games

        games = get_supported_games()
        return {
            "games": games,
            "count": len(games),
            "categories": ["racing", "lightgun", "fighting", "generic"],
        }
    except Exception as e:
        logger.error(f"TeknoParrot games list error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list games: {str(e)}")


@router.get("/teknoparrot/schema/{category}")
async def get_teknoparrot_schema(category: str):
    """Get canonical control schema for a TeknoParrot game category

    Args:
        category: Game category (racing, lightgun, fighting, generic)

    Returns:
        Schema definition with control names and types
    """
    try:
        from ..services.teknoparrot_config_generator import get_schema

        schema = get_schema(category)
        if schema is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown category: {category}. Valid: racing, lightgun, fighting, generic"
            )
        return schema
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TeknoParrot schema error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get schema: {str(e)}")


# ========== Game Input Router Endpoints ==========

class InputTypeRequest(BaseModel):
    """Request for input type classification."""
    game_title: Optional[str] = None
    platform: Optional[str] = None
    emulator: Optional[str] = None
    core: Optional[str] = None


@router.post("/input-type")
@router.post("/input_type")
async def get_game_input_type(request_data: InputTypeRequest):
    """Classify a game's input type (encoder vs gamepad)

    This determines whether a game should use Controller Chuck's
    arcade encoder mappings or Console Wizard's gamepad profiles.

    Args:
        game_title: Name of the game (optional)
        platform: Platform/system (e.g., "naomi", "ps2", "mame")
        emulator: Emulator being used (e.g., "teknoparrot", "retroarch")
        core: RetroArch core if applicable (e.g., "flycast", "fbneo")

    Returns:
        Input type classification with confidence and reason
    """
    try:
        from ..services.game_input_router import get_input_type

        result = get_input_type(
            game_title=request_data.game_title,
            platform=request_data.platform,
            emulator=request_data.emulator,
            core=request_data.core,
        )
        
        return {
            **result.to_dict(),
            "config_source": "chuck" if result.input_type.value == "encoder" else "wizard",
        }
    except Exception as e:
        logger.error(f"Input type classification error: {e}")
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")


@router.get("/platforms")
async def list_platform_classifications():
    """List all platform classifications

    Returns lists of platforms classified as encoder (arcade) or gamepad (console),
    plus RetroArch cores for each category.
    """
    try:
        from ..services.game_input_router import get_all_platforms

        return get_all_platforms()
    except Exception as e:
        logger.error(f"Platform list error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed: {str(e)}")


@router.get("/platforms/{platform}")
async def classify_single_platform(platform: str):
    """Classify a single platform as encoder or gamepad

    Args:
        platform: Platform name to classify

    Returns:
        Classification result
    """
    try:
        from ..services.game_input_router import classify_platform, get_input_type

        classification = classify_platform(platform)
        result = get_input_type(platform=platform)
        
        return {
            "platform": platform,
            "classification": classification,
            "input_type": result.input_type.value,
            "confidence": result.confidence,
            "reason": result.reason,
            "config_source": "chuck" if classification == "encoder" else "wizard",
        }
    except Exception as e:
        logger.error(f"Platform classification error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed: {str(e)}")


# ========== Gamepad Preference Persistence ==========


class GamepadPreferencesRequest(BaseModel):
    """Request model for saving gamepad wizard preferences"""
    profile_id: str
    gamepad_name: Optional[str] = None
    mappings: Dict[str, Any]          # { "up": 12, "down": 13, "a": 0, ... }
    deadzone: float = 0.15
    calibration: Optional[Dict[str, Any]] = None  # stick range data


def _prefs_path(drive_root: Path) -> Path:
    """Canonical path for the gamepad preferences JSON file."""
    return drive_root / ".aa" / "state" / "controller" / "gamepad_preferences.json"


@router.get("/gamepad/preferences")
async def get_gamepad_preferences(request: Request):
    """Load previously saved gamepad preferences.

    Returns the JSON blob written by the wizard, or status='none' if no
    preferences have been saved yet.
    """
    try:
        drive_root = request.app.state.drive_root
        path = _prefs_path(drive_root)

        if not path.exists():
            return {"status": "none"}

        data = json.loads(path.read_text(encoding="utf-8"))
        return {"status": "ok", "preferences": data}

    except json.JSONDecodeError as e:
        logger.warning(f"Corrupt gamepad preferences file: {e}")
        return {"status": "corrupt", "error": str(e)}
    except Exception as e:
        logger.error(f"Failed to load gamepad preferences: {e}")
        raise HTTPException(status_code=500, detail=f"Load failed: {str(e)}")


@router.post("/gamepad/preferences")
async def save_gamepad_preferences(request: Request, prefs: GamepadPreferencesRequest):
    """Persist gamepad wizard preferences to disk.

    Writes to A:/.aa/state/controller/gamepad_preferences.json using
    the atomic temp-file + rename pattern.  This file becomes the single
    source of truth that emulator config generators read from.
    """
    try:
        drive_root = request.app.state.drive_root
        path = _prefs_path(drive_root)
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "version": 1,
            "saved_at": datetime.now().isoformat(),
            "profile_id": prefs.profile_id,
            "gamepad_name": prefs.gamepad_name,
            "mappings": prefs.mappings,
            "deadzone": prefs.deadzone,
            "calibration": prefs.calibration,
        }

        # Atomic write: temp file then rename
        import tempfile
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), suffix=".tmp", prefix="gamepad_prefs_"
        )
        try:
            import os as _os
            with _os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            Path(tmp_path).replace(path)
        except Exception:
            # Clean up temp file on failure
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
            raise

        # Log the change
        log_console_wizard_change(
            request, drive_root, "gamepad_preferences_save",
            {
                "profile_id": prefs.profile_id,
                "mapped_buttons": len(prefs.mappings),
                "deadzone": prefs.deadzone,
            },
        )

        logger.info(f"Gamepad preferences saved: profile={prefs.profile_id}, buttons={len(prefs.mappings)}")

        return {
            "status": "saved",
            "path": str(path.relative_to(drive_root)),
            "profile_id": prefs.profile_id,
            "mapped_buttons": len(prefs.mappings),
        }

    except Exception as e:
        logger.error(f"Failed to save gamepad preferences: {e}")
        raise HTTPException(status_code=500, detail=f"Save failed: {str(e)}")
