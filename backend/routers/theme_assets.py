"""
Theme Asset Management API

Provides endpoints for managing Pegasus theme assets, allowing custom
collection artwork to be deployed across all themes.
"""

import os
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

router = APIRouter()

# Configuration
PEGASUS_ROOT = Path(os.environ.get("PEGASUS_ROOT", "A:/Tools/Pegasus"))
THEMES_DIR = PEGASUS_ROOT / "themes"
CUSTOM_ASSETS_DIR = PEGASUS_ROOT / "custom_assets"
CONFIG_FILE = CUSTOM_ASSETS_DIR / "asset_config.json"

# Asset types
ASSET_TYPES = ["logo", "logo_mono", "art", "banner", "poster"]


class CollectionCreate(BaseModel):
    name: str
    shortname: Optional[str] = None


class AssetDeploy(BaseModel):
    collection: str
    asset_type: str
    source_path: str
    themes: Optional[List[str]] = None


class DeployResult(BaseModel):
    success: bool
    collection: str
    shortname: str
    asset_type: str
    deployed: List[Dict[str, str]]
    failed: List[Dict[str, str]]
    created_dirs: List[str]


def load_config() -> Dict[str, Any]:
    """Load the asset configuration file."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {"custom_collections": {}, "deployments": []}


def save_config(config: Dict[str, Any]):
    """Save the asset configuration file."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def normalize_collection_name(name: str) -> str:
    """Normalize a collection name to a shortname format."""
    shortname = name.lower().strip()
    shortname = shortname.replace(" ", "-")
    shortname = shortname.replace("_", "-")
    shortname = "".join(c for c in shortname if c.isalnum() or c == "-")
    return shortname


def get_theme_collection_dirs() -> Dict[str, Path]:
    """Get all theme collection asset directories."""
    theme_dirs = {}
    for theme_path in THEMES_DIR.iterdir():
        if theme_path.is_dir():
            for asset_subdir in ["assets/collections", "assets/platforms", "collections"]:
                collections_path = theme_path / asset_subdir
                if collections_path.exists():
                    theme_dirs[theme_path.name] = collections_path
                    break
    return theme_dirs


@router.get("/collections")
async def list_collections():
    """List all available collections across themes."""
    theme_dirs = get_theme_collection_dirs()
    all_collections = set()
    
    for theme_name, collections_path in theme_dirs.items():
        if collections_path.exists():
            for item in collections_path.iterdir():
                if item.is_dir():
                    all_collections.add(item.name)
    
    # Include custom collections
    config = load_config()
    custom = []
    for custom_name, custom_data in config.get("custom_collections", {}).items():
        shortname = custom_data.get("shortname", normalize_collection_name(custom_name))
        all_collections.add(shortname)
        custom.append({"name": custom_name, "shortname": shortname})
    
    return {
        "collections": sorted(all_collections),
        "custom_collections": custom,
        "theme_count": len(theme_dirs),
        "total_count": len(all_collections)
    }


@router.get("/collections/{collection_name}/status")
async def get_collection_status(collection_name: str):
    """Get asset status for a collection across all themes."""
    shortname = normalize_collection_name(collection_name)
    theme_dirs = get_theme_collection_dirs()
    
    status = {
        "collection": collection_name,
        "shortname": shortname,
        "themes": {}
    }
    
    for theme_name, collections_path in theme_dirs.items():
        collection_path = collections_path / shortname
        theme_status = {"exists": False, "assets": []}
        
        if collection_path.exists():
            theme_status["exists"] = True
            theme_status["path"] = str(collection_path)
            
            # Check for assets
            for item in collection_path.iterdir():
                if item.is_file():
                    theme_status["assets"].append({
                        "name": item.name,
                        "size": item.stat().st_size
                    })
        
        status["themes"][theme_name] = theme_status
    
    return status


@router.post("/collections")
async def create_collection(data: CollectionCreate):
    """Create a new custom collection."""
    shortname = data.shortname or normalize_collection_name(data.name)
    
    config = load_config()
    config["custom_collections"][data.name] = {
        "shortname": shortname,
        "created": datetime.now().isoformat(),
        "assets": {}
    }
    save_config(config)
    
    # Create folders in all themes
    theme_dirs = get_theme_collection_dirs()
    created = []
    
    for theme_name, collections_path in theme_dirs.items():
        collection_path = collections_path / shortname
        if not collection_path.exists():
            collection_path.mkdir(parents=True, exist_ok=True)
            created.append(str(collection_path))
    
    return {
        "success": True,
        "name": data.name,
        "shortname": shortname,
        "created_dirs": created,
        "theme_count": len(theme_dirs)
    }


@router.post("/deploy")
async def deploy_asset(data: AssetDeploy) -> DeployResult:
    """Deploy an asset to a collection across themes."""
    source_path = Path(data.source_path)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail=f"Source file not found: {data.source_path}")
    
    if data.asset_type not in ASSET_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid asset type. Must be one of: {ASSET_TYPES}")
    
    shortname = normalize_collection_name(data.collection)
    theme_dirs = get_theme_collection_dirs()
    
    # Filter themes if specified
    if data.themes:
        theme_dirs = {k: v for k, v in theme_dirs.items() if k in data.themes}
    
    # Determine target filename
    source_ext = source_path.suffix.lower()
    if data.asset_type == "logo":
        target_filename = "logo_color.svg" if source_ext == ".svg" else "logo_color.png"
    elif data.asset_type == "logo_mono":
        target_filename = "logo_mono.svg" if source_ext == ".svg" else "logo_mono.png"
    else:
        target_filename = f"{data.asset_type}{source_ext}"
    
    result = DeployResult(
        success=True,
        collection=data.collection,
        shortname=shortname,
        asset_type=data.asset_type,
        deployed=[],
        failed=[],
        created_dirs=[]
    )
    
    for theme_name, collections_path in theme_dirs.items():
        collection_path = collections_path / shortname
        
        if not collection_path.exists():
            collection_path.mkdir(parents=True, exist_ok=True)
            result.created_dirs.append(str(collection_path))
        
        target_path = collection_path / target_filename
        
        try:
            shutil.copy2(source_path, target_path)
            result.deployed.append({"theme": theme_name, "path": str(target_path)})
        except Exception as e:
            result.failed.append({"theme": theme_name, "error": str(e)})
    
    # Log deployment
    config = load_config()
    config["deployments"].append({
        "timestamp": datetime.now().isoformat(),
        "collection": data.collection,
        "shortname": shortname,
        "asset_type": data.asset_type,
        "source": str(source_path),
        "target_filename": target_filename,
        "themes_deployed": len(result.deployed),
        "themes_failed": len(result.failed)
    })
    save_config(config)
    
    return result


@router.post("/deploy/upload")
async def deploy_asset_upload(
    collection: str = Form(...),
    asset_type: str = Form(...),
    file: UploadFile = File(...),
    themes: Optional[str] = Form(None)
):
    """Deploy an uploaded asset to a collection across themes."""
    if asset_type not in ASSET_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid asset type. Must be one of: {ASSET_TYPES}")
    
    # Save uploaded file temporarily
    temp_dir = CUSTOM_ASSETS_DIR / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / file.filename
    
    try:
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Deploy using the saved file
        themes_list = themes.split(",") if themes else None
        data = AssetDeploy(
            collection=collection,
            asset_type=asset_type,
            source_path=str(temp_path),
            themes=themes_list
        )
        result = await deploy_asset(data)
        
        return result
    finally:
        # Clean up temp file
        if temp_path.exists():
            temp_path.unlink()


@router.get("/themes")
async def list_themes():
    """List all available themes."""
    theme_dirs = get_theme_collection_dirs()
    themes = []
    
    for theme_name, collections_path in theme_dirs.items():
        collection_count = sum(1 for item in collections_path.iterdir() if item.is_dir())
        themes.append({
            "name": theme_name,
            "collections_path": str(collections_path),
            "collection_count": collection_count
        })
    
    return {"themes": themes}


@router.get("/deployments")
async def get_deployment_history():
    """Get deployment history."""
    config = load_config()
    return {"deployments": config.get("deployments", [])}
