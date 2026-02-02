from fastapi import APIRouter
import subprocess
import sys
from pathlib import Path

from backend.services import launchbox_cache as lb
from backend.services.launchbox_json_cache import json_cache

router = APIRouter(prefix="/api/launchbox/cache", tags=["launchbox-cache"])


@router.get("/status")
def cache_status():
    """Get combined cache status from both parser and JSON cache."""
    parser_status = lb.status()
    json_status = json_cache.get_cache_stats()
    return {
        "parser": parser_status,
        "json_cache": json_status,
    }


@router.post("/revalidate")
def cache_revalidate():
    return lb.revalidate()


@router.post("/reload")
def cache_reload():
    return lb.force_reload()


@router.post("/rebuild")
def cache_rebuild():
    """
    Rebuild the JSON cache from LaunchBox XML files.
    
    This runs the cache builder script and reloads the in-memory cache.
    Use this after adding new games to LaunchBox.
    """
    try:
        # Find the cache builder script
        project_root = Path(__file__).parent.parent.parent
        script_path = project_root / "scripts" / "build_launchbox_cache.py"
        
        if not script_path.exists():
            return {
                "success": False,
                "error": f"Cache builder script not found at {script_path}"
            }
        
        # Run the cache builder
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )
        
        if result.returncode != 0:
            return {
                "success": False,
                "error": "Cache builder failed",
                "stderr": result.stderr[-500:] if result.stderr else None
            }
        
        # Reload the JSON cache in memory
        json_cache.reload()
        stats = json_cache.get_cache_stats()
        
        return {
            "success": True,
            "message": "JSON cache rebuilt and reloaded",
            "stats": stats
        }
        
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Cache builder timed out after 120 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
