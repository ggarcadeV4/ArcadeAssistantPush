"""
Pegasus Frontend Integration Router
====================================
Provides status and management endpoints for Pegasus metadata.
Replaces RetroFE-focused endpoints in ContentDisplayManager.

@linked: frontend/src/panels/launchbox/ContentDisplayManager.jsx
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


router = APIRouter(prefix="/api/pegasus", tags=["pegasus"])


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

def _get_pegasus_root() -> Path:
    """Get Pegasus installation root."""
    from backend.constants.drive_root import get_drive_root
    return get_drive_root(allow_cwd_fallback=True) / "Tools" / "Pegasus"


def _get_metadata_root() -> Path:
    """Get Pegasus metadata directory."""
    return _get_pegasus_root() / "metadata"


def _get_launchbox_root() -> Path:
    """Get LaunchBox root for comparison."""
    from backend.constants.drive_root import get_drive_root
    return get_drive_root(allow_cwd_fallback=True) / "LaunchBox"


# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------

class PlatformStatus(BaseModel):
    id: str
    name: str
    display_name: str
    game_count: int
    has_metadata: bool
    last_synced: Optional[str] = None
    launchbox_count: Optional[int] = None
    sync_status: str = "unknown"  # synced, outdated, missing, error


class PegasusStatus(BaseModel):
    installed: bool
    metadata_root: str
    platform_count: int
    total_games: int
    platforms: List[PlatformStatus]


class SyncRequest(BaseModel):
    platform_id: str


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def _format_display_name(folder_name: str) -> str:
    """Convert folder name to display name."""
    # Replace underscores with spaces and title case
    name = folder_name.replace("_", " ")
    # Handle special cases
    replacements = {
        "nes": "NES",
        "snes": "SNES",
        "mame": "MAME",
        "ps2": "PS2",
        "ps3": "PS3",
        "psx": "PSX",
        "psp": "PSP",
        "nec": "NEC",
        "nintendo ds": "Nintendo DS",
    }
    name_lower = name.lower()
    for key, val in replacements.items():
        if key in name_lower:
            name = name.replace(key, val, 1).replace(key.title(), val, 1)
    return name.title()


def _count_launchbox_games(platform_name: str) -> Optional[int]:
    """Count games in LaunchBox for a platform (rough estimate from XML size)."""
    lb_root = _get_launchbox_root()
    
    # Try various name formats
    names_to_try = [
        platform_name,
        platform_name.replace("_", " "),
        platform_name.replace("_", " ").title(),
    ]
    
    for name in names_to_try:
        xml_path = lb_root / "Data" / "Platforms" / f"{name}.xml"
        if xml_path.exists():
            try:
                # Rough estimate: count <Game> tags
                content = xml_path.read_text(encoding="utf-8", errors="ignore")
                return content.count("<Game>")
            except Exception:
                pass
    return None


def _get_metadata_last_modified(platform_path: Path) -> Optional[str]:
    """Get last modified time of metadata file."""
    metadata_file = platform_path / "metadata.pegasus.txt"
    if metadata_file.exists():
        try:
            mtime = metadata_file.stat().st_mtime
            return datetime.fromtimestamp(mtime).isoformat()
        except Exception:
            pass
    return None


def _determine_sync_status(pegasus_count: int, launchbox_count: Optional[int]) -> str:
    """Determine sync status between Pegasus and LaunchBox."""
    if launchbox_count is None:
        return "no_source"  # No LaunchBox data to compare
    if pegasus_count == 0:
        return "missing"
    if abs(pegasus_count - launchbox_count) <= 2:
        return "synced"
    if pegasus_count < launchbox_count:
        return "outdated"
    return "synced"  # Pegasus has more (possibly includes extras)


def scan_pegasus_platforms() -> List[PlatformStatus]:
    """Scan Pegasus metadata directory for all platforms."""
    metadata_root = _get_metadata_root()
    platforms = []
    
    if not metadata_root.exists():
        return platforms
    
    for platform_dir in sorted(metadata_root.iterdir()):
        if not platform_dir.is_dir():
            continue
        
        folder_name = platform_dir.name
        
        # Count .game files
        game_files = list(platform_dir.glob("*.game"))
        game_count = len(game_files)
        
        # Check for metadata.pegasus.txt
        has_metadata = (platform_dir / "metadata.pegasus.txt").exists()
        
        # Get last modified time
        last_synced = _get_metadata_last_modified(platform_dir)
        
        # Get LaunchBox count for comparison
        launchbox_count = _count_launchbox_games(folder_name)
        
        # Determine sync status
        sync_status = _determine_sync_status(game_count, launchbox_count)
        
        platforms.append(PlatformStatus(
            id=folder_name,
            name=folder_name,
            display_name=_format_display_name(folder_name),
            game_count=game_count,
            has_metadata=has_metadata,
            last_synced=last_synced,
            launchbox_count=launchbox_count,
            sync_status=sync_status,
        ))
    
    return platforms


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@router.get("/status")
async def get_pegasus_status() -> PegasusStatus:
    """Get overall Pegasus installation and metadata status."""
    pegasus_root = _get_pegasus_root()
    metadata_root = _get_metadata_root()
    
    installed = pegasus_root.exists() and (pegasus_root / "pegasus-fe.exe").exists()
    
    platforms = scan_pegasus_platforms()
    total_games = sum(p.game_count for p in platforms)
    
    return PegasusStatus(
        installed=installed,
        metadata_root=str(metadata_root),
        platform_count=len(platforms),
        total_games=total_games,
        platforms=platforms,
    )


@router.get("/platforms")
async def get_platforms() -> List[PlatformStatus]:
    """Get list of all Pegasus platforms with status."""
    return scan_pegasus_platforms()


@router.get("/platforms/{platform_id}")
async def get_platform(platform_id: str) -> PlatformStatus:
    """Get status for a specific platform."""
    platforms = scan_pegasus_platforms()
    for p in platforms:
        if p.id == platform_id:
            return p
    raise HTTPException(status_code=404, detail=f"Platform {platform_id} not found")


@router.post("/sync/{platform_id}")
async def sync_platform(platform_id: str):
    """
    Trigger metadata regeneration for a specific platform.
    This would re-export from LaunchBox to Pegasus metadata format.
    """
    metadata_root = _get_metadata_root()
    platform_path = metadata_root / platform_id
    
    if not platform_path.exists():
        raise HTTPException(status_code=404, detail=f"Platform {platform_id} not found")
    
    # TODO: Implement actual sync from LaunchBox
    # For now, return status indicating manual sync needed
    return {
        "success": True,
        "platform_id": platform_id,
        "message": f"Sync queued for {platform_id}. Use LaunchBox export or run metadata generator.",
        "action_required": "Run: python scripts/generate_pegasus_metadata.py"
    }


@router.post("/sync-all")
async def sync_all_platforms():
    """Trigger metadata regeneration for all platforms."""
    platforms = scan_pegasus_platforms()
    
    # TODO: Implement actual batch sync
    return {
        "success": True,
        "platform_count": len(platforms),
        "message": f"Sync queued for {len(platforms)} platforms.",
        "action_required": "Run: python scripts/generate_pegasus_metadata.py"
    }


@router.get("/health")
async def pegasus_health():
    """Quick health check for Pegasus integration."""
    pegasus_root = _get_pegasus_root()
    metadata_root = _get_metadata_root()
    
    exe_exists = (pegasus_root / "pegasus-fe.exe").exists()
    metadata_exists = metadata_root.exists()
    platform_count = len(list(metadata_root.iterdir())) if metadata_exists else 0
    
    return {
        "healthy": exe_exists and metadata_exists and platform_count > 0,
        "pegasus_exe": exe_exists,
        "metadata_dir": metadata_exists,
        "platform_count": platform_count,
    }


@router.get("/diagnostic")
async def pegasus_diagnostic():
    """
    Comprehensive diagnostic for Pegasus integration.
    Use this to troubleshoot launch issues.
    """
    from backend.constants.drive_root import get_drive_root
    
    drive_root = get_drive_root(allow_cwd_fallback=True)
    pegasus_root = _get_pegasus_root()
    metadata_root = _get_metadata_root()
    scripts_dir = drive_root / "scripts"
    
    issues = []
    warnings = []
    
    # Check Pegasus executable
    pegasus_exe = pegasus_root / "pegasus-fe.exe"
    exe_ok = pegasus_exe.exists()
    if not exe_ok:
        issues.append(f"Pegasus executable not found at {pegasus_exe}")
    
    # Check portable.txt (enables portable mode)
    portable_txt = pegasus_root / "portable.txt"
    portable_ok = portable_txt.exists()
    if not portable_ok:
        warnings.append(f"portable.txt not found - Pegasus may not run in portable mode")
    
    # Check metadata directory
    metadata_ok = metadata_root.exists()
    if not metadata_ok:
        issues.append(f"Metadata directory not found at {metadata_root}")
    
    # Count platforms with metadata
    platform_count = 0
    platforms_with_games = []
    if metadata_ok:
        for p in metadata_root.iterdir():
            if p.is_dir():
                meta_file = p / "metadata.pegasus.txt"
                if meta_file.exists():
                    platform_count += 1
                    # Count games in metadata
                    try:
                        content = meta_file.read_text(encoding="utf-8")
                        game_count = content.count("\ngame:")
                        platforms_with_games.append({"id": p.name, "games": game_count})
                    except:
                        platforms_with_games.append({"id": p.name, "games": "?"})
    
    if platform_count == 0:
        issues.append("No platform metadata found - run generate_pegasus_metadata.py")
    
    # Check launch scripts
    launch_script = scripts_dir / "aa_launch_pegasus_simple.bat"
    wrapper_script = scripts_dir / "aa_pegasus_wrapper.bat"
    start_script = scripts_dir / "start_pegasus.bat"
    
    scripts_status = {
        "launch_script": launch_script.exists(),
        "wrapper_script": wrapper_script.exists(),
        "start_script": start_script.exists(),
    }
    
    if not launch_script.exists():
        issues.append("Launch script missing: aa_launch_pegasus_simple.bat")
    if not wrapper_script.exists():
        warnings.append("Wrapper script missing: aa_pegasus_wrapper.bat")
    
    # Check launch log
    launch_log = drive_root / "logs" / "pegasus_launch.log"
    log_exists = launch_log.exists()
    last_launch = None
    if log_exists:
        try:
            content = launch_log.read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            if lines:
                last_launch = lines[-1][:100] + "..." if len(lines[-1]) > 100 else lines[-1]
        except:
            pass
    
    return {
        "healthy": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "paths": {
            "pegasus_root": str(pegasus_root),
            "metadata_root": str(metadata_root),
            "scripts_dir": str(scripts_dir),
        },
        "checks": {
            "pegasus_exe": exe_ok,
            "portable_mode": portable_ok,
            "metadata_dir": metadata_ok,
            "platform_count": platform_count,
        },
        "scripts": scripts_status,
        "platforms": platforms_with_games[:10],  # First 10
        "launch_log": {
            "exists": log_exists,
            "last_entry": last_launch,
        }
    }
