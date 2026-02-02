"""
TeknoParrot diagnostics and health endpoint.
Provides structured status reporting for TeknoParrot adapter.

@router: teknoparrot
@role: Health checks and diagnostics for TeknoParrot launches
@owner: Arcade Assistant
@status: active
"""

from fastapi import APIRouter, Request
from pathlib import Path
from typing import Any, Dict, List, Optional
import os
import subprocess
import logging

from backend.constants.a_drive_paths import LaunchBoxPaths

router = APIRouter(prefix="/api/local/teknoparrot", tags=["teknoparrot"])
logger = logging.getLogger(__name__)


# Structured error codes for diagnostics
class TeknoParrotError:
    """Structured error codes for TeknoParrot adapter diagnostics."""
    EXE_NOT_FOUND = "exe_not_found"
    PROFILES_MISSING = "profiles_missing"
    UPDATER_STUCK = "updater_stuck"
    CONFIG_INVALID = "config_invalid"
    PROFILE_NOT_FOUND = "profile_not_found"


def _find_teknoparrot_exe() -> Optional[Path]:
    """Locate TeknoParrotUi.exe from known locations."""
    candidates = [
        LaunchBoxPaths.LAUNCHBOX_ROOT / "Emulators" / "TeknoParrot" / "TeknoParrotUi.exe",
        LaunchBoxPaths.EMULATORS_ROOT / "TeknoParrot" / "TeknoParrotUi.exe",
        LaunchBoxPaths.EMULATORS_ROOT / "TeknoParrot Latest" / "TeknoParrotUi.exe",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _check_updater_process() -> bool:
    """Check if TeknoParrot updater is running (blocks launches)."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq TeknoParrotUpdater.exe"],
            capture_output=True, text=True, timeout=5
        )
        return "TeknoParrotUpdater.exe" in result.stdout
    except Exception:
        return False


def _count_profiles(tp_root: Path) -> int:
    """Count available UserProfiles."""
    profiles_dir = tp_root / "UserProfiles"
    if not profiles_dir.exists():
        return 0
    return len(list(profiles_dir.glob("*.xml")))


def _list_profiles(tp_root: Path, limit: int = 50) -> List[str]:
    """List available UserProfile names (without .xml extension)."""
    profiles_dir = tp_root / "UserProfiles"
    if not profiles_dir.exists():
        return []
    profiles = [p.stem for p in profiles_dir.glob("*.xml")]
    return sorted(profiles)[:limit]


def _check_profile_exists(tp_root: Path, profile_name: str) -> bool:
    """Check if a specific profile exists."""
    profiles_dir = tp_root / "UserProfiles"
    # Try with and without .xml extension
    if not profile_name.endswith(".xml"):
        profile_name = f"{profile_name}.xml"
    return (profiles_dir / profile_name).exists()


@router.get("/health")
async def teknoparrot_health(request: Request) -> Dict[str, Any]:
    """
    TeknoParrot adapter health check with structured diagnostics.
    
    Returns:
        - status: "healthy" | "degraded" | "unhealthy"
        - exe_path: Path to TeknoParrotUi.exe or null
        - profiles_count: Number of UserProfiles found
        - errors: List of structured error codes
        - warnings: List of non-critical issues
    """
    errors: List[str] = []
    warnings: List[str] = []
    
    # Check executable
    exe_path = _find_teknoparrot_exe()
    if not exe_path:
        errors.append(TeknoParrotError.EXE_NOT_FOUND)
    
    # Check profiles
    profiles_count = 0
    tp_root = None
    if exe_path:
        tp_root = exe_path.parent
        profiles_count = _count_profiles(tp_root)
        if profiles_count == 0:
            errors.append(TeknoParrotError.PROFILES_MISSING)
    
    # Check updater (warning, not error)
    updater_running = _check_updater_process()
    if updater_running:
        warnings.append(TeknoParrotError.UPDATER_STUCK)
    
    # Determine overall status
    if errors:
        status = "unhealthy"
    elif warnings:
        status = "degraded"
    else:
        status = "healthy"
    
    return {
        "status": status,
        "adapter": "teknoparrot",
        "exe_path": str(exe_path) if exe_path else None,
        "exe_exists": exe_path is not None and exe_path.exists(),
        "profiles_count": profiles_count,
        "updater_running": updater_running,
        "errors": errors,
        "warnings": warnings,
    }


@router.get("/profiles")
async def list_teknoparrot_profiles(request: Request) -> Dict[str, Any]:
    """
    List available TeknoParrot UserProfiles.
    
    Returns:
        - profiles: List of profile names (without .xml)
        - count: Total number of profiles
        - profiles_dir: Path to UserProfiles directory
    """
    exe_path = _find_teknoparrot_exe()
    if not exe_path:
        return {
            "profiles": [],
            "count": 0,
            "profiles_dir": None,
            "error": TeknoParrotError.EXE_NOT_FOUND,
        }
    
    tp_root = exe_path.parent
    profiles_dir = tp_root / "UserProfiles"
    profiles = _list_profiles(tp_root)
    
    return {
        "profiles": profiles,
        "count": len(profiles),
        "profiles_dir": str(profiles_dir) if profiles_dir.exists() else None,
    }


@router.get("/profile/{profile_name}")
async def check_teknoparrot_profile(profile_name: str, request: Request) -> Dict[str, Any]:
    """
    Check if a specific TeknoParrot profile exists.
    
    Args:
        profile_name: Name of profile (with or without .xml extension)
    
    Returns:
        - exists: Whether the profile exists
        - profile_path: Full path to profile if it exists
        - error_code: Structured error code if not found
    """
    exe_path = _find_teknoparrot_exe()
    if not exe_path:
        return {
            "exists": False,
            "profile_name": profile_name,
            "profile_path": None,
            "error_code": TeknoParrotError.EXE_NOT_FOUND,
        }
    
    tp_root = exe_path.parent
    profiles_dir = tp_root / "UserProfiles"
    
    # Normalize profile name
    xml_name = profile_name if profile_name.endswith(".xml") else f"{profile_name}.xml"
    profile_path = profiles_dir / xml_name
    exists = profile_path.exists()
    
    return {
        "exists": exists,
        "profile_name": profile_name,
        "profile_path": str(profile_path) if exists else None,
        "error_code": None if exists else TeknoParrotError.PROFILE_NOT_FOUND,
    }
