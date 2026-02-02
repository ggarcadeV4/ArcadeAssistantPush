"""
Controller Auto-Configuration Router

Endpoints:
    GET  /api/controllers/autoconfig/detect - Detect connected devices
    GET  /api/controllers/autoconfig/profiles - List existing profiles
    POST /api/controllers/autoconfig/mirror - Mirror staged config to emulators

Note: Staging configs via /config/apply (not this router) to ensure proper backup/logging.

Feature Flag: CONTROLLER_AUTOCONFIG_ENABLED (default: false)
Set environment variable CONTROLLER_AUTOCONFIG_ENABLED=true to enable these endpoints.
"""

import os
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path

from ..capabilities.autoconfig_manager import (
    mirror_staged_config,
    get_existing_profiles,
    AutoConfigError,
    MirrorError
)
from ..capabilities.input_probe import (
    detect_devices,
    detect_unconfigured_devices,
    get_device_by_vidpid
)

router = APIRouter(prefix="/api/controllers/autoconfig", tags=["autoconfig"])

# Feature flag (default: disabled)
AUTOCONFIG_ENABLED = os.getenv('CONTROLLER_AUTOCONFIG_ENABLED', 'false').lower() == 'true'


def _check_feature_enabled():
    """
    Check if controller auto-configuration is enabled.

    Raises:
        HTTPException: 501 Not Implemented if feature is disabled
    """
    if not AUTOCONFIG_ENABLED:
        raise HTTPException(
            status_code=501,
            detail="Controller auto-configuration is disabled. Set CONTROLLER_AUTOCONFIG_ENABLED=true to enable."
        )


class MirrorRequest(BaseModel):
    """Request to mirror a staged config"""
    profile_name: str
    device_class: str  # controller | encoder | lightgun
    vendor_id: Optional[str] = None
    product_id: Optional[str] = None


@router.get("/detect")
async def detect_controllers(
    request: Request,
    force_refresh: bool = Query(False, description="Force USB device refresh")
):
    """
    Detect connected input devices.

    Returns:
        List of detected devices with profile status

    Performance: <50ms (cached)
    """
    _check_feature_enabled()
    try:
        drive_root = request.app.state.drive_root

        # Detect all devices
        devices = detect_devices(force_refresh=force_refresh)

        # Check profile existence for each
        from ..capabilities.input_probe import check_profile_exists
        for device in devices:
            device.profile_exists = check_profile_exists(device, drive_root)
            if device.profile_exists:
                if device.manufacturer and device.model:
                    device.profile_name = f"{device.manufacturer}_{device.model}"
                else:
                    from ..capabilities.autoconfig_manager import normalize_profile_name
                    device.profile_name = normalize_profile_name(device.name)

        return {
            "devices": [d.to_dict() for d in devices],
            "count": len(devices),
            "unconfigured_count": sum(1 for d in devices if not d.profile_exists)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/unconfigured")
async def detect_unconfigured(request: Request):
    """
    Detect devices that need auto-configuration.

    Returns:
        List of devices without existing profiles
    """
    _check_feature_enabled()
    try:
        drive_root = request.app.state.drive_root
        unconfigured = detect_unconfigured_devices(drive_root)

        return {
            "devices": [d.to_dict() for d in unconfigured],
            "count": len(unconfigured)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles")
async def list_profiles(
    request: Request,
    device_class: Optional[str] = Query(None, description="Filter by device class")
):
    """
    List existing controller profiles.

    Args:
        device_class: Optional filter (controller | encoder | lightgun)

    Returns:
        List of profile names
    """
    _check_feature_enabled()
    try:
        drive_root = request.app.state.drive_root
        profiles = get_existing_profiles(device_class or "controller", drive_root)

        return {
            "profiles": profiles,
            "count": len(profiles),
            "device_class": device_class
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mirror")
async def mirror_config(request: Request, mirror_req: MirrorRequest):
    """
    Mirror a staged controller config to emulator trees.

    This endpoint ONLY mirrors validated configs from staging.
    To stage a new config, use POST /config/apply with target_file in staging area.

    Args:
        mirror_req: Profile name and device info

    Returns:
        Mirror status with paths

    Raises:
        404: If staged config not found
        400: If validation fails
        500: If mirror operation fails
    """
    _check_feature_enabled()
    try:
        drive_root = request.app.state.drive_root

        # Get request headers for logging
        device_id = request.headers.get('x-device-id', '')
        panel = request.headers.get('x-panel', 'controller_chuck')

        # Mirror the config
        result = mirror_staged_config(
            profile_name=mirror_req.profile_name,
            device_class=mirror_req.device_class,
            vendor_id=mirror_req.vendor_id,
            product_id=mirror_req.product_id,
            drive_root=drive_root,
            device_id=device_id,
            panel=panel
        )

        return result

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=f"Staged config not found: {mirror_req.profile_name}"
        )
    except MirrorError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except AutoConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def autoconfig_status(request: Request):
    """
    Get auto-configuration system status.

    Returns:
        Path validation, device count, profile count
    """
    try:
        from ..constants.a_drive_paths import AutoConfigPaths

        drive_root = request.app.state.drive_root

        enabled = AUTOCONFIG_ENABLED

        # Validate paths
        path_status = AutoConfigPaths.validate()

        if not enabled:
            return {
                "enabled": False,
                "reason": "Controller auto-configuration is disabled. Set CONTROLLER_AUTOCONFIG_ENABLED=true to enable.",
                "paths": path_status,
                "staging_root": str(AutoConfigPaths.STAGING_ROOT),
                "status": "disabled",
            }

        # Count devices and profiles only when enabled
        devices = detect_devices()
        profiles = get_existing_profiles("controller", drive_root)

        return {
            "enabled": True,
            "paths": path_status,
            "devices_detected": len(devices),
            "profiles_available": len(profiles),
            "staging_root": str(AutoConfigPaths.STAGING_ROOT),
            "status": "operational" if path_status["staging_root"] else "degraded"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
