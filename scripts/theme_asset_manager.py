#!/usr/bin/env python3
"""
Theme Asset Manager for Pegasus Frontend

Manages custom collection assets across all Pegasus themes.
Allows defining custom categories (like "NES Gun Games") and deploying
artwork to all themes at once.

Usage:
    # List all collections
    python theme_asset_manager.py list
    
    # Show asset status for a collection
    python theme_asset_manager.py status "NES Gun Games"
    
    # Deploy an asset to a collection across all themes
    python theme_asset_manager.py deploy "NES Gun Games" --logo path/to/logo.png
    python theme_asset_manager.py deploy "NES Gun Games" --art path/to/background.jpg
    
    # Create a new custom collection
    python theme_asset_manager.py create "NES Gun Games" --shortname "nes-gun"
    
    # API mode (for integration with chat/AI)
    python theme_asset_manager.py api --action deploy --collection "NES Gun Games" --asset-type logo --file path/to/logo.png
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime

# Configuration
PEGASUS_ROOT = Path(os.environ.get("PEGASUS_ROOT", "A:/Tools/Pegasus"))
THEMES_DIR = PEGASUS_ROOT / "themes"
CUSTOM_ASSETS_DIR = PEGASUS_ROOT / "custom_assets"
COLLECTION_ARTWORK_DIR = PEGASUS_ROOT / "collection_artwork"
CONFIG_FILE = CUSTOM_ASSETS_DIR / "asset_config.json"

# Asset types and their expected filenames in themes
ASSET_TYPES = {
    "logo": ["logo_color.svg", "logo_color.png", "logo.svg", "logo.png"],
    "logo_mono": ["logo_mono.svg", "logo_mono.png"],
    "art": ["art.jpg", "art.png", "background.jpg", "background.png"],
    "banner": ["banner.png", "banner.jpg"],
    "poster": ["poster.png", "poster.jpg"],
}

# Standard collection name mappings (Pegasus shortnames)
STANDARD_COLLECTIONS = {
    "nes": ["nes", "nintendo entertainment system", "famicom"],
    "snes": ["snes", "super nintendo", "super famicom", "sfc"],
    "genesis": ["genesis", "megadrive", "mega drive", "sega genesis"],
    "n64": ["n64", "nintendo 64"],
    "gb": ["gb", "game boy", "gameboy"],
    "gba": ["gba", "game boy advance", "gameboy advance"],
    "gbc": ["gbc", "game boy color", "gameboy color"],
    "psx": ["psx", "playstation", "ps1", "psone"],
    "ps2": ["ps2", "playstation 2"],
    "dreamcast": ["dreamcast", "dc"],
    "saturn": ["saturn", "sega saturn"],
    "arcade": ["arcade", "mame", "fba", "fbneo"],
    "atari2600": ["atari2600", "atari 2600", "2600"],
}


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


def get_theme_collection_dirs() -> Dict[str, Path]:
    """Get all theme collection asset directories."""
    theme_dirs = {}
    for theme_path in THEMES_DIR.iterdir():
        if theme_path.is_dir():
            # Check common asset locations
            for asset_subdir in ["assets/collections", "assets/platforms", "collections"]:
                collections_path = theme_path / asset_subdir
                if collections_path.exists():
                    theme_dirs[theme_path.name] = collections_path
                    break
    return theme_dirs


def normalize_collection_name(name: str) -> str:
    """Normalize a collection name to a shortname format."""
    # Convert to lowercase, replace spaces with hyphens
    shortname = name.lower().strip()
    shortname = shortname.replace(" ", "-")
    shortname = shortname.replace("_", "-")
    # Remove special characters
    shortname = "".join(c for c in shortname if c.isalnum() or c == "-")
    return shortname


def find_collection_in_themes(collection_name: str) -> Dict[str, Optional[Path]]:
    """Find where a collection exists across all themes."""
    shortname = normalize_collection_name(collection_name)
    theme_dirs = get_theme_collection_dirs()
    results = {}
    
    for theme_name, collections_path in theme_dirs.items():
        collection_path = collections_path / shortname
        if collection_path.exists():
            results[theme_name] = collection_path
        else:
            results[theme_name] = None
    
    return results


def list_collections():
    """List all available collections across themes."""
    theme_dirs = get_theme_collection_dirs()
    all_collections = set()
    
    for theme_name, collections_path in theme_dirs.items():
        if collections_path.exists():
            for item in collections_path.iterdir():
                if item.is_dir():
                    all_collections.add(item.name)
    
    # Also include custom collections
    config = load_config()
    for custom_name, custom_data in config.get("custom_collections", {}).items():
        all_collections.add(custom_data.get("shortname", normalize_collection_name(custom_name)))
    
    print(f"Found {len(all_collections)} collections across {len(theme_dirs)} themes:\n")
    for collection in sorted(all_collections):
        print(f"  - {collection}")
    
    return sorted(all_collections)


def show_status(collection_name: str):
    """Show asset status for a collection across all themes."""
    shortname = normalize_collection_name(collection_name)
    theme_locations = find_collection_in_themes(collection_name)
    
    print(f"Collection: {collection_name} (shortname: {shortname})")
    print("=" * 60)
    
    for theme_name, collection_path in theme_locations.items():
        print(f"\n{theme_name}:")
        if collection_path is None:
            print("  ❌ Collection folder not found")
        else:
            print(f"  📁 {collection_path}")
            # List assets
            assets_found = []
            for asset_type, filenames in ASSET_TYPES.items():
                for filename in filenames:
                    asset_path = collection_path / filename
                    if asset_path.exists():
                        size = asset_path.stat().st_size
                        assets_found.append(f"    ✓ {filename} ({size:,} bytes)")
                        break
            
            if assets_found:
                print("  Assets:")
                for asset in assets_found:
                    print(asset)
            else:
                print("  ⚠ No assets found")


def create_collection(collection_name: str, shortname: Optional[str] = None):
    """Create a new custom collection definition."""
    if shortname is None:
        shortname = normalize_collection_name(collection_name)
    
    config = load_config()
    config["custom_collections"][collection_name] = {
        "shortname": shortname,
        "created": datetime.now().isoformat(),
        "assets": {}
    }
    save_config(config)
    
    # Create folders in all themes
    theme_dirs = get_theme_collection_dirs()
    created_count = 0
    
    for theme_name, collections_path in theme_dirs.items():
        collection_path = collections_path / shortname
        if not collection_path.exists():
            collection_path.mkdir(parents=True, exist_ok=True)
            created_count += 1
            print(f"  ✓ Created: {collection_path}")
    
    print(f"\nCreated collection '{collection_name}' (shortname: {shortname})")
    print(f"Created {created_count} folders across {len(theme_dirs)} themes")
    
    return shortname


def deploy_asset(collection_name: str, asset_type: str, source_file: str, 
                 themes: Optional[List[str]] = None) -> Dict[str, Any]:
    """Deploy an asset to a collection across themes."""
    source_path = Path(source_file)
    if not source_path.exists():
        return {"success": False, "error": f"Source file not found: {source_file}"}
    
    shortname = normalize_collection_name(collection_name)
    theme_dirs = get_theme_collection_dirs()
    
    # Filter themes if specified
    if themes:
        theme_dirs = {k: v for k, v in theme_dirs.items() if k in themes}
    
    # Determine target filename based on asset type and source extension
    source_ext = source_path.suffix.lower()
    if asset_type == "logo":
        if source_ext == ".svg":
            target_filename = "logo_color.svg"
        else:
            target_filename = "logo_color.png"
    elif asset_type == "logo_mono":
        if source_ext == ".svg":
            target_filename = "logo_mono.svg"
        else:
            target_filename = "logo_mono.png"
    elif asset_type == "art":
        target_filename = f"art{source_ext}"
    elif asset_type == "banner":
        target_filename = f"banner{source_ext}"
    elif asset_type == "poster":
        target_filename = f"poster{source_ext}"
    else:
        return {"success": False, "error": f"Unknown asset type: {asset_type}"}
    
    results = {"success": True, "deployed": [], "failed": [], "created_dirs": []}
    
    for theme_name, collections_path in theme_dirs.items():
        collection_path = collections_path / shortname
        
        # Create collection folder if it doesn't exist
        if not collection_path.exists():
            collection_path.mkdir(parents=True, exist_ok=True)
            results["created_dirs"].append(str(collection_path))
        
        target_path = collection_path / target_filename
        
        try:
            shutil.copy2(source_path, target_path)
            results["deployed"].append({
                "theme": theme_name,
                "path": str(target_path)
            })
            print(f"  ✓ {theme_name}: {target_path}")
        except Exception as e:
            results["failed"].append({
                "theme": theme_name,
                "error": str(e)
            })
            print(f"  ✗ {theme_name}: {e}")
    
    # Log deployment
    config = load_config()
    config["deployments"].append({
        "timestamp": datetime.now().isoformat(),
        "collection": collection_name,
        "shortname": shortname,
        "asset_type": asset_type,
        "source": str(source_path),
        "target_filename": target_filename,
        "themes_deployed": len(results["deployed"]),
        "themes_failed": len(results["failed"])
    })
    save_config(config)
    
    return results


def api_handler(args) -> Dict[str, Any]:
    """Handle API-style requests (for AI/chat integration)."""
    action = args.action
    
    if action == "list":
        collections = list_collections()
        return {"success": True, "collections": collections}
    
    elif action == "status":
        if not args.collection:
            return {"success": False, "error": "Collection name required"}
        show_status(args.collection)
        return {"success": True}
    
    elif action == "create":
        if not args.collection:
            return {"success": False, "error": "Collection name required"}
        shortname = create_collection(args.collection, args.shortname)
        return {"success": True, "shortname": shortname}
    
    elif action == "deploy":
        if not args.collection or not args.asset_type or not args.file:
            return {"success": False, "error": "Collection, asset-type, and file required"}
        themes = args.themes.split(",") if args.themes else None
        return deploy_asset(args.collection, args.asset_type, args.file, themes)
    
    else:
        return {"success": False, "error": f"Unknown action: {action}"}


def main():
    parser = argparse.ArgumentParser(description="Pegasus Theme Asset Manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all collections")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show status for a collection")
    status_parser.add_argument("collection", help="Collection name")
    
    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new custom collection")
    create_parser.add_argument("collection", help="Collection name (e.g., 'NES Gun Games')")
    create_parser.add_argument("--shortname", help="Short name for folder (e.g., 'nes-gun')")
    
    # Deploy command
    deploy_parser = subparsers.add_parser("deploy", help="Deploy asset to collection")
    deploy_parser.add_argument("collection", help="Collection name")
    deploy_parser.add_argument("--logo", help="Path to logo image")
    deploy_parser.add_argument("--logo-mono", help="Path to monochrome logo")
    deploy_parser.add_argument("--art", help="Path to background art")
    deploy_parser.add_argument("--banner", help="Path to banner image")
    deploy_parser.add_argument("--poster", help="Path to poster image")
    deploy_parser.add_argument("--themes", help="Comma-separated list of themes (default: all)")
    
    # API command (for programmatic use)
    api_parser = subparsers.add_parser("api", help="API mode for integration")
    api_parser.add_argument("--action", required=True, 
                           choices=["list", "status", "create", "deploy"])
    api_parser.add_argument("--collection", help="Collection name")
    api_parser.add_argument("--shortname", help="Short name for collection")
    api_parser.add_argument("--asset-type", dest="asset_type",
                           choices=["logo", "logo_mono", "art", "banner", "poster"])
    api_parser.add_argument("--file", help="Path to asset file")
    api_parser.add_argument("--themes", help="Comma-separated list of themes")
    api_parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    if args.command == "list":
        list_collections()
    
    elif args.command == "status":
        show_status(args.collection)
    
    elif args.command == "create":
        create_collection(args.collection, args.shortname)
    
    elif args.command == "deploy":
        print(f"Deploying assets to '{args.collection}'...")
        print("-" * 40)
        
        if args.logo:
            print(f"\nDeploying logo: {args.logo}")
            deploy_asset(args.collection, "logo", args.logo, 
                        args.themes.split(",") if args.themes else None)
        
        if args.logo_mono:
            print(f"\nDeploying mono logo: {args.logo_mono}")
            deploy_asset(args.collection, "logo_mono", args.logo_mono,
                        args.themes.split(",") if args.themes else None)
        
        if args.art:
            print(f"\nDeploying art: {args.art}")
            deploy_asset(args.collection, "art", args.art,
                        args.themes.split(",") if args.themes else None)
        
        if args.banner:
            print(f"\nDeploying banner: {args.banner}")
            deploy_asset(args.collection, "banner", args.banner,
                        args.themes.split(",") if args.themes else None)
        
        if args.poster:
            print(f"\nDeploying poster: {args.poster}")
            deploy_asset(args.collection, "poster", args.poster,
                        args.themes.split(",") if args.themes else None)
        
        print("\n✓ Deployment complete!")
    
    elif args.command == "api":
        result = api_handler(args)
        if hasattr(args, 'json') and args.json:
            print(json.dumps(result, indent=2))
        else:
            if not result.get("success"):
                print(f"Error: {result.get('error')}")
                sys.exit(1)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
