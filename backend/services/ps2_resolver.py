from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Optional
import json
import time
import os
import logging

from backend.services.archive_utils import resolve_rom_path
from backend.constants.runtime_paths import ps2_overrides_path
from backend.constants.a_drive_paths import LaunchBoxPaths
try:
    from backend.services.platform_names import normalize_platform
except Exception:
    def normalize_platform(name: str) -> str:
        return name

logger = logging.getLogger(__name__)


@dataclass
class PS2Item:
    game_id: str
    title: str
    requested_path: str
    exists: bool
    resolved_path: Optional[str] = None
    status: str = "exact"  # exact|resolved|missing
    bytes: Optional[int] = None


def _norm(p: str) -> str:
    return str(Path(p)).lower().replace("/", "\\")


def _game_to_dict(g) -> Dict:
    # Convert Game (pydantic/dataclass-like) to dict safely
    try:
        return {
            "id": getattr(g, "id", ""),
            "title": getattr(g, "title", ""),
            "platform": getattr(g, "platform", ""),
            "path": getattr(g, "rom_path", None) or getattr(g, "application_path", None) or "",
        }
    except Exception:
        return {}


def build_ps2_report(games: List[dict]) -> Dict:
    """
    Input: list of game dicts ({id,title,platform,path}).
    Filter to PS2 via normalize_platform, then resolve missing file paths.
    Output: dict with summary + items.
    """
    items: List[PS2Item] = []
    total = exact = resolved = missing = 0

    for g in games:
        platform = normalize_platform(g.get("platform", ""))
        if platform != "Sony PlayStation 2":
            continue
        gid = str(g.get("id", ""))
        title = g.get("title", "")
        requested = g.get("path") or g.get("rom_path") or ""
        if not requested:
            items.append(PS2Item(gid, title, requested, False, None, "missing"))
            missing += 1; total += 1; continue

        # ApplicationPath in LaunchBox XML is relative to LaunchBox root
        # Resolve it properly like direct_app_adapter does
        req_path = Path(requested)
        if not req_path.is_absolute():
            resolved = (LaunchBoxPaths.LAUNCHBOX_ROOT / requested).resolve()
            logger.info(f"PS2 path resolution: '{requested}' → '{resolved}' (exists: {resolved.exists()})")
            req_path = resolved

        if req_path.exists():
            size = None
            try:
                size = req_path.stat().st_size
            except Exception:
                pass
            items.append(PS2Item(gid, title, str(req_path), True, None, "exact", size))
            exact += 1; total += 1; continue

        alt, how = resolve_rom_path(req_path)
        if alt and alt.exists():
            size = None
            try:
                size = alt.stat().st_size
            except Exception:
                pass
            items.append(PS2Item(gid, title, str(req_path), False, str(alt), "resolved", size))
            resolved += 1; total += 1
        else:
            items.append(PS2Item(gid, title, str(req_path), False, None, "missing"))
            missing += 1; total += 1

    return {
        "version": 1,
        "generated_at": int(time.time()),
        "summary": {"total": total, "exact": exact, "resolved": resolved, "missing": missing},
        "items": [asdict(i) for i in items]
    }


def write_overrides_from_report(report: Dict) -> Path:
    """
    Write overrides map for fast lookup at launch time.
    Schema:
    {
      "version": 1,
      "by_game_id": { "<game_id>": "<resolved_path>", ... },
      "by_request_path": { "<norm(requested_path)>": "<resolved_path>", ... }
    }
    Include items with status 'exact' or 'resolved' (both mean file was found).
    """
    overrides = {"version": 1, "by_game_id": {}, "by_request_path": {}}
    for it in report.get("items", []):
        status = it.get("status")
        # Include both 'exact' (file found at requested path) and 'resolved' (file found at alt path)
        if status in ("exact", "resolved"):
            # For 'exact', use requested_path as the resolved path
            # For 'resolved', use the resolved_path field
            resolved_path = it.get("resolved_path") if status == "resolved" else it.get("requested_path")
            if resolved_path:
                gid = str(it.get("game_id", ""))
                if gid:
                    overrides["by_game_id"][gid] = resolved_path
                rp = it.get("requested_path") or ""
                if rp:
                    overrides["by_request_path"][_norm(rp)] = resolved_path

    path = ps2_overrides_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(overrides, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def load_overrides() -> Dict:
    p = ps2_overrides_path()
    if not p.exists():
        return {"version": 1, "by_game_id": {}, "by_request_path": {}}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("by_game_id", {})
        data.setdefault("by_request_path", {})
        return data
    except Exception:
        return {"version": 1, "by_game_id": {}, "by_request_path": {}}


def reload_overrides() -> Dict[str, int]:
    """Re-read overrides file and return counts (does not mutate launcher cache)."""
    data = load_overrides()
    by_id = (data.get("by_game_id", {}) or {})
    by_req = (data.get("by_request_path", {}) or {})
    return {
        "by_game_id": len(by_id),
        "by_request_path": len(by_req),
    }