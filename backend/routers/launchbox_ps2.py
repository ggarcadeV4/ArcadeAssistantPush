from __future__ import annotations

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path
import logging

from backend.services.ps2_resolver import (
    build_ps2_report,
    write_overrides_from_report,
    load_overrides,
    reload_overrides
)
from backend.constants.runtime_paths import ps2_overrides_path
from backend.services.launcher import launcher
from backend.services.launchbox_parser import parser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/launchbox/ps2", tags=["ps2"])


def _games_as_dicts() -> List[Dict[str, Any]]:
    """Convert game objects to dictionaries for PS2 resolver.

    Returns:
        List of game dictionaries with id, title, platform, and path
    """
    games = []
    try:
        for game in parser.get_all_games():
            # Use getattr with defaults for safer attribute access
            rom_path = getattr(game, "rom_path", None)
            app_path = getattr(game, "application_path", None)

            games.append({
                "id": getattr(game, "id", ""),
                "title": getattr(game, "title", ""),
                "platform": getattr(game, "platform", ""),
                "path": rom_path or app_path or "",
            })
    except Exception as e:
        logger.error(f"Failed to convert games to dicts: {e}")

    return games


@router.get("/resolve-report")
def ps2_resolve_report() -> Dict[str, Any]:
    """Generate PS2 game path resolution report.

    Returns:
        Report dict with summary and item details

    Raises:
        HTTPException: If report generation fails
    """
    try:
        games = _games_as_dicts()
        report = build_ps2_report(games)
        return report
    except Exception as e:
        logger.error(f"Failed to generate PS2 resolve report: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate PS2 resolve report")


@router.post("/resolve-apply")
def ps2_resolve_apply() -> Dict[str, Any]:
    """Generate and apply PS2 path resolutions.

    Returns:
        Status dict with overrides path and summary

    Raises:
        HTTPException: If resolution or writing fails
    """
    try:
        games = _games_as_dicts()
        report = build_ps2_report(games)
        path = write_overrides_from_report(report)

        return {
            "status": "ok",
            "overrides_path": str(path),
            "summary": report.get("summary", {})
        }
    except Exception as e:
        logger.error(f"Failed to apply PS2 resolutions: {e}")
        raise HTTPException(status_code=500, detail="Failed to apply PS2 resolutions")


@router.get("/overrides-stats")
def ps2_overrides_stats() -> Dict[str, Any]:
    """Return statistics about the PS2 overrides file.

    Returns:
        Dict with file stats including existence, counts, size, and modification time
    """
    path = ps2_overrides_path()
    exists = path.exists()

    # Load data only if file exists
    if exists:
        data = load_overrides()
    else:
        data = {"version": 1, "by_game_id": {}, "by_request_path": {}}

    # Use dict.get() for safe access
    by_id = data.get("by_game_id", {})
    by_req = data.get("by_request_path", {})

    # Get file stats if available
    size_bytes = 0
    modified = None

    if exists:
        try:
            stat = path.stat()
            size_bytes = stat.st_size
            modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
        except (OSError, IOError) as e:
            logger.debug(f"Failed to get file stats for {path}: {e}")

    return {
        "path": str(path),
        "exists": exists,
        "version": data.get("version", 1),
        "by_game_id_count": len(by_id),
        "by_request_path_count": len(by_req),
        "size_bytes": size_bytes,
        "modified": modified,
    }


@router.post("/overrides/reload")
def ps2_overrides_reload() -> Dict[str, Any]:
    """Reload PS2 overrides in launcher without restarting.

    This endpoint triggers a reload of the PS2 overrides cache in the launcher
    service, which uses proper thread locking for safety.

    Returns:
        Status dict with counts and path

    Raises:
        HTTPException: If reload fails
    """
    try:
        # This calls launcher.reload_ps2_overrides() which has thread locking
        counts = launcher.reload_ps2_overrides()

        return {
            "status": "ok",
            "counts": counts,
            "path": str(ps2_overrides_path()),
        }
    except Exception as e:
        logger.error(f"Failed to reload PS2 overrides: {e}")
        raise HTTPException(status_code=500, detail="Failed to reload PS2 overrides")