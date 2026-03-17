"""
Content Manager Router
======================
Backend endpoints for Content & Display Manager panel.
Handles ROM/Asset path management, RetroFE collections, and marquee configuration.

@linked: frontend/src/panels/launchbox/ContentDisplayManager.jsx
"""

import json
import logging
import os
import re
import subprocess
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel

from backend.models.marquee_config import MarqueeConfig as SharedMarqueeConfig
# Import path utilities from existing modules
try:
    from backend.constants.a_drive_paths import AA_DRIVE_ROOT, STATE_DIR
except ImportError:
    from backend.constants.drive_root import get_drive_root

AA_DRIVE_ROOT = get_drive_root(allow_cwd_fallback=True)
STATE_DIR = AA_DRIVE_ROOT / ".aa" / "state"
from backend.constants.paths import Paths

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/content", tags=["content-manager"])
registry_router = APIRouter(prefix="/api/local/registry", tags=["content-registry"])

# State file paths (legacy .aa/state for existing content paths; new registries live under drive_root/state)
CONTENT_PATHS_FILE = STATE_DIR / "content_paths.json"
# Legacy fallback for marquee; primary path is drive_root/config/marquee.json via helper below
MARQUEE_CONFIG_FILE = STATE_DIR / "marquee.json"

MARQUEE_DEFAULT = {
    "targetDisplay": "Display 2 Marquee",
    "resolution": "1920x360",
    "safeArea": {"x": 0, "y": 0, "width": 1920, "height": 360},
    "useVideo": True,
    "useFallback": True,
    "imagePath": "",
    "videoPath": "",
}

MARQUEE_DEFAULT = {
    "targetDisplay": "Display 2 Marquee",
    "resolution": "1920x360",
    "safeArea": {"x": 0, "y": 0, "width": 1920, "height": 360},
    "useVideo": True,
    "useFallback": True,
    "imagePath": "",
    "videoPath": "",
}

# ============================================================================
# Pydantic Models
# ============================================================================

class CorePaths(BaseModel):
    launchboxRoot: str = ""
    retrofeRoot: str = ""
    romRoot: str = ""


class SystemPath(BaseModel):
    id: int
    system: str
    path: str


class ArtworkPaths(BaseModel):
    splashScreens: str = ""
    marqueeImages: str = ""
    marqueeVideos: str = ""
    bezels: str = ""
    manuals: str = ""


class ContentPathsRequest(BaseModel):
    core: CorePaths
    systems: List[SystemPath]
    artwork: ArtworkPaths


class PathStatus(BaseModel):
    launchboxRoot: str = "unknown"
    retrofeRoot: str = "unknown"
    romRoot: str = "unknown"


class SafeArea(BaseModel):
    x: int = 0
    y: int = 0
    width: int = 1920
    height: int = 360


MarqueeConfig = SharedMarqueeConfig


class RetroFECollection(BaseModel):
    system: str
    launchboxSource: str = "Not Detected"
    retrofeStatus: str = "Missing"


class GenerateRequest(BaseModel):
    system: str
class RefreshRegistryRequest(BaseModel):
    save: bool = True


class MarqueeTestRequest(BaseModel):
    title: Optional[str] = None
    platform: Optional[str] = None


class MarqueeBrowseRequest(BaseModel):
    platform: Optional[str] = None


# ============================================================================
# Helper Functions
# ============================================================================

def ensure_state_dir():
    """Ensure state directory exists."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _get_drive_root(request: Optional[Request] = None) -> Path:
    """Resolve drive root from app state with AA_DRIVE_ROOT fallback."""
    try:
        if request and getattr(request.app, "state", None):
            root = getattr(request.app.state, "drive_root", None)
            if root:
                return Path(root)
    except Exception:
        pass
    return Path(AA_DRIVE_ROOT)


def _get_state_dir(request: Optional[Request] = None) -> Path:
    """Drive-rooted state directory under .aa (Golden Drive compliant)."""
    return _get_drive_root(request) / ".aa" / "state"


def _get_config_dir(request: Optional[Request] = None) -> Path:
    """Drive-rooted config directory (e.g., A:/Arcade Assistant/config)."""
    return _get_drive_root(request) / "config"


def _marquee_config_path(request: Optional[Request] = None) -> Path:
    """Primary marquee config location."""
    return _get_config_dir(request) / "marquee.json"


def load_json_file(filepath: Path, default: Any = None) -> Any:
    """Load JSON file with fallback to default."""
    try:
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error("[ContentManager] Error loading %s: %s", filepath, e)
    return default if default is not None else {}


def _load_content_paths(drive_root: Path) -> Dict[str, Any]:
    """
    Load content paths from legacy (.aa/state) or drive_root/state locations.
    Preference order:
      1) CONTENT_PATHS_FILE (legacy)
      2) drive_root/state/content_paths.json
    """
    data = load_json_file(CONTENT_PATHS_FILE, None)
    if data is not None:
        return data
    alt = drive_root / ".aa" / "state" / "content_paths.json"
    data = load_json_file(alt, None)
    if data is not None:
        return data
    # Fallback default shape (unknown values as empty strings)
    return {
        "core": {"launchboxRoot": "", "retrofeRoot": "", "romRoot": ""},
        "systems": [
            {"id": 1, "system": "Arcade / MAME", "path": ""},
            {"id": 2, "system": "SNES", "path": ""},
        ],
        "artwork": {
            "splashScreens": "",
            "marqueeImages": "",
            "marqueeVideos": "",
            "bezels": "",
            "manuals": "",
        },
        "status": {
            "launchboxRoot": "unknown",
            "retrofeRoot": "unknown",
            "romRoot": "unknown",
        },
    }


def save_json_file(filepath: Path, data: Any, create_backup: bool = True) -> bool:
    """Save data to JSON file with optional backup.
    
    Following AA pattern: Preview → Apply → Backup → Log
    """
    try:
        ensure_state_dir()
        
        # Create backup if file exists
        if create_backup and filepath.exists():
            backup_dir = STATE_DIR / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"{filepath.stem}_{timestamp}.json"
            shutil.copy2(filepath, backup_path)
            logger.info("[ContentManager] Backup created: %s", backup_path)
        
        # Write the file
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        # Audit log
        log_content_change(filepath.name, "save", True)
        return True
    except Exception as e:
        logger.error("[ContentManager] Error saving %s: %s", filepath, e)
        log_content_change(filepath.name, "save", False, str(e))
        return False


def log_content_change(filename: str, action: str, success: bool, error: str = "") -> None:
    """Log content manager actions to audit log (Golden Drive compliant)."""
    log_dir = AA_DRIVE_ROOT / ".aa" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "content_manager.jsonl"
    
    entry = {
        "ts": datetime.now().isoformat(),
        "file": filename,
        "action": action,
        "success": success,
    }
    if error:
        entry["error"] = error
    
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.error("[ContentManager] Failed to write audit log: %s", e)


# Script paths
SCRIPTS_DIR = AA_DRIVE_ROOT / "Arcade Assistant Local" / "scripts"
RETROFE_GENERATE_SCRIPT = SCRIPTS_DIR / "generate_retrofe_collections.py"


def validate_path(path_str: str) -> str:
    """Validate if a path exists and return status."""
    if not path_str or not path_str.strip():
        return "unknown"
    try:
        p = Path(path_str)
        if p.exists():
            return "valid"
        return "invalid"
    except Exception:
        return "invalid"


def detect_retrofe_collections(drive_root: Optional[Path] = None) -> List[Dict[str, str]]:
    """Detect RetroFE collections by scanning LaunchBox platforms.
    
    Scans actual LaunchBox Data/Platforms folder for all platforms,
    then checks if RetroFE collection exists for each.
    """
    drive_root = drive_root or _get_drive_root()
    collections = []
    
    # Load saved paths
    paths_data = _load_content_paths(drive_root)
    retrofe_root = paths_data.get("core", {}).get("retrofeRoot", "") or str(Paths.RetroFE.ROOT)
    launchbox_root = paths_data.get("core", {}).get("launchboxRoot", "") or str(drive_root / "LaunchBox")
    
    lb_platforms_dir = Path(launchbox_root) / "Data" / "Platforms"
    rfe_collections_dir = Path(retrofe_root) / "collections"
    
    # Scan all LaunchBox platform XMLs
    detected_platforms = set()
    if lb_platforms_dir.exists():
        for xml_file in lb_platforms_dir.glob("*.xml"):
            platform_name = xml_file.stem
            if platform_name and not platform_name.startswith("_"):
                detected_platforms.add(platform_name)
    
    # Also include any existing RetroFE collections not in LaunchBox
    if rfe_collections_dir.exists():
        for collection_dir in rfe_collections_dir.iterdir():
            if collection_dir.is_dir() and collection_dir.name != "Main":
                # Convert underscore names back to spaces for display
                platform_name = collection_dir.name.replace("_", " ")
                detected_platforms.add(platform_name)
    
    # Build collection status for each platform
    for platform in sorted(detected_platforms):
        collection = {
            "system": platform, 
            "launchboxSource": "Not Detected", 
            "retrofeStatus": "Missing",
            "gameCount": 0
        }
        
        # Check LaunchBox platform XML
        lb_platform_file = lb_platforms_dir / f"{platform}.xml"
        if lb_platform_file.exists():
            collection["launchboxSource"] = "Detected"
            # Try to count games (rough estimate from file size)
            try:
                size = lb_platform_file.stat().st_size
                # Rough estimate: ~500 bytes per game entry
                collection["gameCount"] = max(1, size // 500)
            except:
                pass
        
        # Check RetroFE collection (handle both space and underscore names)
        safe_name = platform.replace(" ", "_")
        rfe_collection_path = rfe_collections_dir / safe_name
        if rfe_collection_path.exists():
            collection["retrofeStatus"] = "Generated"
            # Count actual games from menu.txt if it exists
            menu_file = rfe_collection_path / "menu.txt"
            if menu_file.exists():
                try:
                    with open(menu_file, "r", encoding="utf-8") as f:
                        collection["gameCount"] = sum(1 for line in f if line.strip())
                except:
                    pass
        
        collections.append(collection)
    
    # If no platforms found, return default list
    if not collections:
        default_systems = ["Arcade", "Nintendo Entertainment System", "Super Nintendo", "Sony PlayStation 2", "Sega Genesis", "Nintendo 64"]
        for system in default_systems:
            collections.append({
                "system": system,
                "launchboxSource": "Not Detected",
                "retrofeStatus": "Missing",
                "gameCount": 0
            })
    
    return collections


def _sanitize_id(value: str) -> str:
    """Create a stable identifier from a label."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return cleaned or "system"


def _sanitize_collection_name(value: str) -> str:
    """Match RetroFE folder naming."""
    safe = re.sub(r'[<>:"/\\|?*]', '', value)
    safe = re.sub(r'\s+', '_', safe)
    return safe.strip() or "collection"


def build_aa_registry(drive_root: Path, save: bool = True) -> Dict[str, Any]:
    """Build AA registry (systems + frontends) and optionally persist under drive_root/state."""
    paths_data = _load_content_paths(drive_root)

    launchbox_root = Path(paths_data.get("core", {}).get("launchboxRoot", "") or Paths.LaunchBox.ROOT)
    retrofe_root = Path(paths_data.get("core", {}).get("retrofeRoot", "") or Paths.RetroFE.ROOT)

    frontends = {
        "launchbox": {
            "enabled": launchbox_root.exists(),
            "root": str(launchbox_root),
        },
        "retrofe": {
            "enabled": retrofe_root.exists(),
            "root": str(retrofe_root),
        },
    }

    systems: List[Dict[str, Any]] = []
    for sys_entry in paths_data.get("systems", []):
        label = (sys_entry.get("system") or "").strip() or "Unknown"
        rom_path_val = (sys_entry.get("path") or "").strip()
        sys_id = _sanitize_id(label)
        system_obj = {
            "id": sys_id,
            "label": label,
            "rom_path": rom_path_val or None,
            "frontends": {
                "launchbox": {"platform": label},
                "retrofe": {"collection": _sanitize_collection_name(label)},
            },
        }
        systems.append(system_obj)

    registry = {
        "version": 1,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "frontends": frontends,
        "systems": systems,
    }

    if save:
        target = drive_root / ".aa" / "state" / "aa_registry.json"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(registry, f, indent=2)
            log_content_change(target.name, "save_registry", True)
        except Exception as e:
            log_content_change(target.name, "save_registry", False, str(e))

    return registry


def _default_aa_registry(drive_root: Path) -> Dict[str, Any]:
    """Safe default AA registry."""
    return {
        "version": 1,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "frontends": {
            "launchbox": {"enabled": False, "root": str(Paths.LaunchBox.ROOT)},
            "retrofe": {"enabled": False, "root": str(Paths.RetroFE.ROOT)},
        },
        "systems": [],
    }


def build_retrofe_collections_registry(drive_root: Path, save: bool = True) -> Dict[str, Any]:
    """Build RetroFE collections registry from existing directories/status."""
    collections_dir = Paths.RetroFE.COLLECTIONS

    # Map system ids by sanitized collection name from content paths
    paths_data = _load_content_paths(drive_root)
    system_map: Dict[str, List[str]] = {}
    for sys_entry in paths_data.get("systems", []):
        label = (sys_entry.get("system") or "").strip() or "Unknown"
        sys_id = _sanitize_id(label)
        coll_name = _sanitize_collection_name(label)
        system_map.setdefault(coll_name, []).append(sys_id)

    entries: List[Dict[str, Any]] = []

    if collections_dir.exists():
        for coll_dir in collections_dir.iterdir():
            if not coll_dir.is_dir():
                continue
            if coll_dir.name.lower() == "main":
                continue
            name = coll_dir.name
            settings_path = coll_dir / "settings.conf"
            meta_dir = coll_dir / "meta"
            status = "generated" if settings_path.exists() and meta_dir.exists() else "unknown"

            game_count = None
            menu_file = coll_dir / "menu.txt"
            if menu_file.exists():
                try:
                    with open(menu_file, "r", encoding="utf-8") as f:
                        game_count = sum(1 for line in f if line.strip())
                except Exception:
                    game_count = None

            entries.append({
                "name": name,
                "systems": system_map.get(name, []),
                "path": str(coll_dir),
                "settings_conf": str(settings_path),
                "meta_dir": str(meta_dir),
                "status": status,
                "game_count": game_count,
            })
    # Add missing entries for mapped systems without a collection directory
    for mapped_name in sorted(system_map.keys()):
        if any(e["name"] == mapped_name for e in entries):
            continue
        coll_dir = collections_dir / mapped_name
        entries.append({
            "name": mapped_name,
            "systems": system_map.get(mapped_name, []),
            "path": str(coll_dir),
            "settings_conf": str(coll_dir / "settings.conf"),
            "meta_dir": str(coll_dir / "meta"),
            "status": "missing" if collections_dir.exists() else "unknown",
            "game_count": None,
        })

    registry = {
        "version": 1,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "collections": entries,
    }

    if save:
        target = drive_root / ".aa" / "state" / "retrofe_collections.json"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(registry, f, indent=2)
            log_content_change(target.name, "save_registry", True)
        except Exception as e:
            log_content_change(target.name, "save_registry", False, str(e))

    return registry


def _default_retrofe_registry() -> Dict[str, Any]:
    """Safe default RetroFE collections registry."""
    return {
        "version": 1,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "collections": [],
    }


# ============================================================================
# Path Management Endpoints
# ============================================================================

@router.get("/paths")
async def get_content_paths():
    """Get current content path configuration."""
    data = load_json_file(CONTENT_PATHS_FILE, {
        "core": {"launchboxRoot": "", "retrofeRoot": "", "romRoot": ""},
        "systems": [
            {"id": 1, "system": "Arcade / MAME", "path": ""},
            {"id": 2, "system": "SNES", "path": ""},
        ],
        "artwork": {
            "splashScreens": "",
            "marqueeImages": "",
            "marqueeVideos": "",
            "bezels": "",
            "manuals": "",
        },
        "status": {
            "launchboxRoot": "unknown",
            "retrofeRoot": "unknown",
            "romRoot": "unknown",
        }
    })
    
    # Auto-detect A: drive paths if not set
    if not data.get("core", {}).get("launchboxRoot"):
        lb_default = AA_DRIVE_ROOT / "LaunchBox"
        if lb_default.exists():
            data.setdefault("core", {})["launchboxRoot"] = str(lb_default)
            data.setdefault("status", {})["launchboxRoot"] = "valid"
    
    if not data.get("core", {}).get("retrofeRoot"):
        rfe_default = Paths.RetroFE.ROOT
        if rfe_default.exists():
            data.setdefault("core", {})["retrofeRoot"] = str(rfe_default)
            data.setdefault("status", {})["retrofeRoot"] = "valid"
    
    return data


@router.post("/paths")
async def save_content_paths(request: ContentPathsRequest):
    """Save content path configuration."""
    data = {
        "core": request.core.model_dump(),
        "systems": [s.model_dump() for s in request.systems],
        "artwork": request.artwork.model_dump(),
    }
    
    if save_json_file(CONTENT_PATHS_FILE, data):
        return {"success": True, "message": "Paths saved"}
    else:
        raise HTTPException(status_code=500, detail="Failed to save paths")


@router.post("/paths/validate")
async def validate_content_paths(request: ContentPathsRequest):
    """Validate all content paths."""
    status = {
        "launchboxRoot": validate_path(request.core.launchboxRoot),
        "retrofeRoot": validate_path(request.core.retrofeRoot),
        "romRoot": validate_path(request.core.romRoot),
    }
    
    all_valid = all(s == "valid" for s in status.values() if s != "unknown")
    
    return {
        "valid": all_valid,
        "status": status,
    }


# ============================================================================
# RetroFE Collection Endpoints
# ============================================================================

@router.get("/retrofe/collections")
async def get_retrofe_collections(request: Request):
    """Get RetroFE collection status."""
    drive_root = _get_drive_root(request)
    collections = detect_retrofe_collections(drive_root)
    return {"collections": collections}


@router.post("/retrofe/generate")
async def generate_retrofe_collection(request: GenerateRequest, background_tasks: BackgroundTasks):
    """Generate RetroFE collection for a specific system.
    
    Runs the generation script for a single platform.
    Note: Current script generates ALL at once, so this triggers full regeneration.
    """
    system = request.system
    drive_root = _get_drive_root()
    
    # Load paths - use auto-detection fallback (same as detect_retrofe_collections)
    paths_data = _load_content_paths(drive_root)
    retrofe_root = paths_data.get("core", {}).get("retrofeRoot", "") or str(Paths.RetroFE.ROOT)
    
    # Validate that the path actually exists
    if not retrofe_root or not Path(retrofe_root).exists():
        raise HTTPException(status_code=400, detail="RetroFE root path not configured or does not exist")
    
    # Check if script exists
    if not RETROFE_GENERATE_SCRIPT.exists():
        raise HTTPException(status_code=500, detail=f"Generation script not found: {RETROFE_GENERATE_SCRIPT}")
    
    # Run the script (fires generation for all platforms)
    try:
        result = subprocess.run(
            ["python", str(RETROFE_GENERATE_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(SCRIPTS_DIR)
        )
        
        if result.returncode != 0:
            log_content_change("retrofe_generate", f"generate_{system}", False, result.stderr[:500])
            raise HTTPException(status_code=500, detail=f"Generation failed: {result.stderr[:200]}")
        
        log_content_change("retrofe_generate", f"generate_{system}", True)
        
        # Count generated games from output
        output = result.stdout
        game_count = 0
        if "Total games:" in output:
            try:
                game_count = int(output.split("Total games:")[1].split()[0])
            except:
                pass
        
        return {
            "success": True,
            "system": system,
            "message": f"Collection for {system} generated successfully",
            "gameCount": game_count
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Generation timed out")
    except Exception as e:
        log_content_change("retrofe_generate", f"generate_{system}", False, str(e))
        raise HTTPException(status_code=500, detail=f"Generation error: {str(e)}")


@router.get("/retrofe/preview/{system}")
async def preview_retrofe_settings(system: str):
    """Preview settings.conf for a RetroFE collection."""
    drive_root = _get_drive_root()
    paths_data = _load_content_paths(drive_root)
    # Use auto-detection fallback (same as detect_retrofe_collections)
    retrofe_root = paths_data.get("core", {}).get("retrofeRoot", "") or str(Paths.RetroFE.ROOT)
    
    if not retrofe_root:
        return {"content": "# RetroFE root path not configured"}
    
    # Handle both space and underscore naming (RetroFE uses underscores for folder names)
    safe_system = system.replace(" ", "_")
    
    # Try the exact name first, then the underscore version
    for try_name in [system, safe_system]:
        settings_path = Path(retrofe_root) / "collections" / try_name / "settings.conf"
        if settings_path.exists():
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    return {"content": f.read()}
            except Exception as e:
                return {"content": f"# Error reading settings: {e}"}
    
    return {"content": f"# settings.conf for {system} does not exist yet\n# Generate the collection first to create this file."}


@router.post("/retrofe/generate-all")
async def generate_all_retrofe_collections():
    """Generate all RetroFE collections from LaunchBox game library.
    
    Runs the full generation script which:
    1. Loads game library from A:\.aa\launchbox_games.json
    2. Creates RetroFE collections for all platforms
    3. Sets up media paths pointing to LaunchBox Images
    4. Creates launcher configuration
    """
    # Check if script exists
    if not RETROFE_GENERATE_SCRIPT.exists():
        raise HTTPException(status_code=500, detail=f"Generation script not found: {RETROFE_GENERATE_SCRIPT}")
    
    try:
        result = subprocess.run(
            ["python", str(RETROFE_GENERATE_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=180,  # 3 minute timeout for full generation
            cwd=str(SCRIPTS_DIR)
        )
        
        if result.returncode != 0:
            log_content_change("retrofe_generate", "generate_all", False, result.stderr[:500])
            raise HTTPException(status_code=500, detail=f"Generation failed: {result.stderr[:200]}")
        
        log_content_change("retrofe_generate", "generate_all", True)
        
        # Parse counts from output
        output = result.stdout
        platform_count = 0
        game_count = 0
        
        if "Total platforms:" in output:
            try:
                platform_count = int(output.split("Total platforms:")[1].split()[0])
            except:
                pass
        if "Total games:" in output:
            try:
                game_count = int(output.split("Total games:")[1].split()[0])
            except:
                pass
        
        return {
            "success": True,
            "count": platform_count,
            "gameCount": game_count,
            "message": f"Generated {platform_count} collections with {game_count} total games"
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Generation timed out (>3 minutes)")
    except Exception as e:
        log_content_change("retrofe_generate", "generate_all", False, str(e))
        raise HTTPException(status_code=500, detail=f"Generation error: {str(e)}")


@router.post("/retrofe/rebuild-meta")
async def rebuild_retrofe_meta():
    """Rebuild RetroFE meta.db database.
    
    RetroFE's meta.db is typically rebuilt by RetroFE itself on startup.
    This endpoint triggers a regeneration of collections which updates metadata.
    """
    # For now, just regenerate all collections (which updates all metadata)
    # In the future, we could call RetroFE's meta tool directly
    try:
        result = subprocess.run(
            ["python", str(RETROFE_GENERATE_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(SCRIPTS_DIR)
        )
        
        if result.returncode != 0:
            log_content_change("retrofe_meta", "rebuild", False, result.stderr[:500])
            raise HTTPException(status_code=500, detail=f"Rebuild failed: {result.stderr[:200]}")
        
        log_content_change("retrofe_meta", "rebuild", True)
        
        return {
            "success": True,
            "message": "meta.db and all collections rebuilt successfully"
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Rebuild timed out")
    except Exception as e:
        log_content_change("retrofe_meta", "rebuild", False, str(e))
        raise HTTPException(status_code=500, detail=f"Rebuild error: {str(e)}")


# ============================================================================
# Marquee Configuration Endpoints
# ============================================================================

@router.get("/marquee")
async def get_marquee_config(request: Request):
    """Get marquee configuration."""
    config_path = _marquee_config_path(request)
    data = load_json_file(config_path, None)
    if data is None:
        data = load_json_file(MARQUEE_CONFIG_FILE, None)
    if data is None:
        data = dict(MARQUEE_DEFAULT)

    cfg = MarqueeConfig.model_validate(data)
    payload = cfg.model_dump()
    payload["displays"] = [
        "Display 1 - Main",
        "Display 2 - Marquee",
        "Display 3 - Auxiliary",
    ]

    return payload


@router.post("/marquee")
async def save_marquee_config(config: MarqueeConfig, request: Request):
    """Save marquee configuration."""
    config_path = _marquee_config_path(request)
    data = config.model_dump()
    
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Backup if file exists (store under .aa/backups)
        backup_dir = _get_drive_root(request) / ".aa" / "backups"
        if config_path.exists():
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(config_path, backup_dir / f"marquee_{timestamp}.json")
        
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        log_content_change(config_path.name, "save_marquee", True)
        return {"success": True, "message": "Marquee configuration saved"}
    except Exception as e:
        log_content_change(config_path.name, "save_marquee", False, str(e))
        raise HTTPException(status_code=500, detail="Failed to save marquee configuration")


def _match_platform(game_platform: Optional[str], platform_filter: Optional[str]) -> bool:
    if not platform_filter:
        return True
    return (game_platform or "").strip().lower() == platform_filter.strip().lower()


def _iter_marquee_candidates(platform_filter: Optional[str] = None):
    from backend.services.launchbox_parser import parser as launchbox_parser

    try:
        for game in launchbox_parser.get_all_games() or []:
            if _match_platform(getattr(game, "platform", None), platform_filter):
                yield game
    except Exception:
        return


@router.post("/marquee/test/image")
async def test_marquee_image(request: Request, payload: Optional[MarqueeTestRequest] = None):
    """Display test image on marquee monitor."""
    try:
        from backend.routers import marquee as marquee_router

        selected_title = payload.title if payload else None
        selected_platform = payload.platform if payload else None
        resolved = None

        if selected_title:
            resolved = marquee_router._resolve_media_assets(  # type: ignore[attr-defined]
                request,
                title=selected_title,
                platform=selected_platform,
                prefer_video=False,
            )
        else:
            for game in _iter_marquee_candidates(selected_platform):
                resolved = marquee_router._resolve_media_assets(  # type: ignore[attr-defined]
                    request,
                    game_id=getattr(game, "id", None),
                    title=getattr(game, "title", None),
                    platform=getattr(game, "platform", None),
                    prefer_video=False,
                )
                if resolved.get("game_image_file"):
                    break

        if not resolved or not resolved.get("game_image_file"):
            title_label = selected_title or "the requested game"
            return {"status": "no_media", "message": f"No marquee image found for {title_label}"}

        marquee_router.persist_current_game({
            "game_id": resolved.get("game_id"),
            "title": resolved.get("game_title"),
            "platform": resolved.get("platform"),
            "mode": "image",
            "event_type": "GAME",
            "source": "content_manager_test_image",
        })
        return {
            "status": "ok",
            "image_path": str(resolved["game_image_file"]),
            "game": resolved.get("game_title"),
        }
    except Exception as e:
        logger.warning("[ContentManager] test marquee image failed: %s", e)
        return {"status": "no_media", "message": f"Unable to display marquee image: {e}"}


@router.post("/marquee/test/video")
async def test_marquee_video(request: Request, payload: Optional[MarqueeTestRequest] = None):
    """Display test video on marquee monitor."""
    try:
        from backend.routers import marquee as marquee_router

        selected_title = payload.title if payload else None
        selected_platform = payload.platform if payload else None
        resolved = None

        if selected_title:
            resolved = marquee_router._resolve_media_assets(  # type: ignore[attr-defined]
                request,
                title=selected_title,
                platform=selected_platform,
                prefer_video=True,
            )
        else:
            for game in _iter_marquee_candidates(selected_platform):
                resolved = marquee_router._resolve_media_assets(  # type: ignore[attr-defined]
                    request,
                    game_id=getattr(game, "id", None),
                    title=getattr(game, "title", None),
                    platform=getattr(game, "platform", None),
                    prefer_video=True,
                )
                if resolved.get("game_video_file"):
                    break

        if not resolved or not resolved.get("game_video_file"):
            title_label = selected_title or "the requested game"
            return {"status": "no_media", "message": f"No video snap found for {title_label}"}

        marquee_router.persist_current_game({
            "game_id": resolved.get("game_id"),
            "title": resolved.get("game_title"),
            "platform": resolved.get("platform"),
            "mode": "video",
            "event_type": "GAME",
            "source": "content_manager_test_video",
        })
        return {
            "status": "ok",
            "video_path": str(resolved["game_video_file"]),
            "game": resolved.get("game_title"),
        }
    except Exception as e:
        logger.warning("[ContentManager] test marquee video failed: %s", e)
        return {"status": "no_media", "message": f"Unable to display marquee video: {e}"}


@router.post("/marquee/test/browse")
async def test_marquee_browse(request: Request, payload: Optional[MarqueeBrowseRequest] = None):
    """Simulate game browsing with marquee updates."""
    try:
        from backend.routers import marquee as marquee_router

        platform_filter = payload.platform if payload else None
        previews: List[Dict[str, Any]] = []

        for game in _iter_marquee_candidates(platform_filter):
            resolved = marquee_router._resolve_media_assets(  # type: ignore[attr-defined]
                request,
                game_id=getattr(game, "id", None),
                title=getattr(game, "title", None),
                platform=getattr(game, "platform", None),
                prefer_video=False,
            )
            if resolved.get("game_image_file"):
                previews.append({
                    "game_id": resolved.get("game_id"),
                    "title": resolved.get("game_title"),
                    "platform": resolved.get("platform"),
                })
            if len(previews) >= 10:
                break

        if not previews:
            return {"status": "no_media", "message": "No marquee images found"}

        first_preview = previews[0]
        marquee_router.persist_preview_game(
            {
                "game_id": first_preview.get("game_id"),
                "title": first_preview.get("title"),
                "platform": first_preview.get("platform"),
                "event_type": "GAME",
                "source": "content_manager_test_browse",
            },
            mode="image",
        )
        return {
            "status": "ok",
            "preview_count": len(previews),
            "first_preview": first_preview.get("title"),
        }
    except Exception as e:
        logger.warning("[ContentManager] test marquee browse failed: %s", e)
        return {"status": "no_media", "message": f"Unable to start marquee browse preview: {e}"}


# ============================================================================
# Registry (Read-only snapshots for other panels / AI helpers)
# ============================================================================

def _load_aa_registry(drive_root: Path) -> Dict[str, Any]:
    path = drive_root / ".aa" / "state" / "aa_registry.json"
    data = load_json_file(path, None)
    if isinstance(data, dict) and data.get("version"):
        return data
    try:
        return build_aa_registry(drive_root, save=True)
    except Exception:
        return _default_aa_registry(drive_root)


def _load_retrofe_registry(drive_root: Path) -> Dict[str, Any]:
    path = drive_root / ".aa" / "state" / "retrofe_collections.json"
    data = load_json_file(path, None)
    if isinstance(data, dict) and data.get("version"):
        return data
    try:
        return build_retrofe_collections_registry(drive_root, save=True)
    except Exception:
        return _default_retrofe_registry()


@router.get("/registry")
async def get_content_registry(request: Request):
    """Return registry snapshots for AA systems and RetroFE collections."""
    drive_root = _get_drive_root(request)
    aa_reg = _load_aa_registry(drive_root)
    retrofe_reg = _load_retrofe_registry(drive_root)
    return {"aa_registry": aa_reg, "retrofe_collections": retrofe_reg}


@router.get("/registry/aa")
async def get_aa_registry(request: Request):
    drive_root = _get_drive_root(request)
    return _load_aa_registry(drive_root)


@router.get("/registry/retrofe")
async def get_retrofe_registry(request: Request):
    drive_root = _get_drive_root(request)
    return _load_retrofe_registry(drive_root)


@router.post("/registry/refresh")
async def refresh_content_registry(request: Request, payload: RefreshRegistryRequest):
    """Rebuild registries from current paths and RetroFE collections."""
    drive_root = _get_drive_root(request)
    aa_reg = build_aa_registry(drive_root, save=payload.save)
    retrofe_reg = build_retrofe_collections_registry(drive_root, save=payload.save)
    return {"aa_registry": aa_reg, "retrofe_collections": retrofe_reg, "saved": payload.save}


# ============================================================================
# Local registry (read-only) under /api/local/registry/*
# ============================================================================


@registry_router.get("/aa")
async def get_local_aa_registry(request: Request):
    drive_root = _get_drive_root(request)
    return _load_aa_registry(drive_root)


@registry_router.get("/retrofe")
async def get_local_retrofe_registry(request: Request):
    drive_root = _get_drive_root(request)
    return _load_retrofe_registry(drive_root)
