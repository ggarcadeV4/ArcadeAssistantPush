from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Any, Dict
import logging
import os
import json

from backend.services.launchbox_plugin_client import get_plugin_client, LaunchBoxPluginError
from backend.services import launchbox_cache as lb_cache
from backend.constants.drive_root import get_drive_root

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/launchbox/import", tags=["launchbox-import"])


class ImportApplyRequest(BaseModel):
    platform: str
    folder: str


@router.get("/missing")
def import_list_missing(platform: str = Query(...), folder: str = Query(...)) -> Dict[str, Any]:
    plugin = get_plugin_client()
    if not plugin.is_available():
        raise HTTPException(status_code=503, detail="LaunchBox plugin unavailable")
    if not os.path.isdir(folder):
        raise HTTPException(status_code=400, detail=f"Folder not found: {folder}")
    try:
        return plugin.list_missing(platform, folder)
    except LaunchBoxPluginError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply")
def import_apply(req: ImportApplyRequest) -> Dict[str, Any]:
    plugin = get_plugin_client()
    if not plugin.is_available():
        raise HTTPException(status_code=503, detail="LaunchBox plugin unavailable")
    if not os.path.isdir(req.folder):
        raise HTTPException(status_code=400, detail=f"Folder not found: {req.folder}")
    try:
        result = plugin.import_missing(req.platform, req.folder)

        # Operator-clear log line (Golden Drive: use .aa/logs)
        try:
            drive_root = get_drive_root(allow_cwd_fallback=True)
            log_dir = drive_root / ".aa" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "changes.jsonl"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "type": "import",
                    "platform": req.platform,
                    "folder": req.folder,
                    "added": result.get("added", 0),
                    "skipped": result.get("skipped", 0)
                }) + "\n")
        except Exception as le:
            logger.warning(f"Failed to write import log: {le}")

        # Trigger cache revalidation automatically
        try:
            lb_cache.revalidate()
        except Exception as ce:
            logger.warning(f"Cache revalidate failed: {ce}")

        return result
    except LaunchBoxPluginError as e:
        raise HTTPException(status_code=500, detail=str(e))
