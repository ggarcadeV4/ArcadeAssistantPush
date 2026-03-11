from fastapi import APIRouter, HTTPException, Request, Query, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal
import os
import httpx
import asyncio
import base64
import json
from datetime import datetime
import uuid
import structlog
import re

from ..services.backup import create_backup
from ..services.diffs import compute_diff, has_changes
from ..services.policies import require_scope, is_allowed_file
from ..services.scorekeeper import TournamentService, TournamentConfig, TournamentData
from ..services.supabase_client import get_client as get_supabase_client
from ..services.supabase_client import insert_score as sb_insert_score
from ..services.leaderboard import get_leaderboard_service
from ..services.runtime_state import update_runtime_state, load_runtime_state
from ..services.player_tendencies import (
    PlayerTendencyService,
    get_active_player,
    set_active_player,
    extend_session,
    end_session,
    get_active_session
)
from ..services.score_tracking import (
    CanonicalGameEvent,
    ScoreReviewDecision,
    get_score_tracking_service,
)

# Initialize structured logger
logger = structlog.get_logger(__name__)

router = APIRouter()

# Gateway broadcast URL for real-time WebSocket push
GATEWAY_BROADCAST_URL = "http://localhost:8787/api/scorekeeper/broadcast"


def _broadcast_score_update(game: str, entry: dict, source: str = "scorekeeper_submit"):
    """Non-blocking broadcast to Gateway WebSocket for instantaneous leaderboard updates."""
    try:
        httpx.post(
            GATEWAY_BROADCAST_URL,
            json={
                "type": "score_updated",
                "game": game,
                "entry": entry,
                "source": source
            },
            timeout=2.0
        )
        logger.debug("broadcast_score_sent", game=game, source=source)
    except Exception as e:
        logger.warning("broadcast_score_failed", error=str(e))

# Pydantic models
class ScoreSubmit(BaseModel):
    game: str
    player: str
    score: int
    game_id: Optional[str] = None
    system: Optional[str] = None
    platform: Optional[str] = None
    player_userId: Optional[str] = None
    player_source: Optional[str] = None  # 'profile' | 'guest'
    publicLeaderboardEligible: Optional[bool] = None

class TournamentCreate(BaseModel):
    name: str
    game: str
    player_count: int  # 4, 8, 16, or 32

class LegacyTournamentCreate(BaseModel):
    """Backward-compatible payload for legacy acceptance scripts."""
    name: str
    size: int = Field(..., description="Bracket size (4, 8, 16, or 32)")
    game: Optional[str] = Field(default="Arcade", description="Optional game label")

class TournamentReport(BaseModel):
    tournament_id: str
    match_index: int
    winner_player: str

class TournamentGenerateRequest(BaseModel):
    """Request model for advanced tournament generation."""
    name: str
    players: List[str]
    mode: str = "casual"  # casual, tournament, fair_play, random
    game_id: Optional[str] = None
    enable_kid_shield: bool = False
    handicap_enabled: bool = False

class MatchSubmitRequest(BaseModel):
    """Request model for match result submission."""
    tournament_id: str
    match_id: str
    round_number: int
    winner: str
    score1: Optional[int] = None
    score2: Optional[int] = None

class ScorekeeperRestoreRequest(BaseModel):
    """Payload for scorekeeper restore operations."""
    backup_path: Optional[str] = None
    strategy: Optional[str] = Field(
        default=None,
        description="Optional restore strategy. Currently supports 'last' to use the newest snapshot."
    )
    dry_run: Optional[bool] = None

    @model_validator(mode="after")
    def validate_target(self) -> "ScorekeeperRestoreRequest":
        if not self.backup_path and not self.strategy:
            raise ValueError("Provide either backup_path or strategy.")
        if self.backup_path and self.strategy:
            raise ValueError("Specify backup_path or strategy, not both.")
        if self.strategy and self.strategy != "last":
            raise ValueError("Unsupported strategy. Allowed: 'last'.")
        return self

class ScorekeeperUndoRequest(BaseModel):
    """Optional payload for undo (allows forcing dry-run)."""
    dry_run: Optional[bool] = None

# Utility functions
def get_scorekeeper_dir(drive_root: Path) -> Path:
    """Get the scorekeeper state directory"""
    return drive_root / ".aa" / "state" / "scorekeeper"

def get_scores_file(drive_root: Path) -> Path:
    """Get the scores.jsonl file path"""
    return get_scorekeeper_dir(drive_root) / "scores.jsonl"

def get_tournament_file(drive_root: Path, tournament_id: str) -> Path:
    """Get tournament JSON file path"""
    return get_scorekeeper_dir(drive_root) / "tournaments" / f"{tournament_id}.json"


# ========================================
# IDENTITY HELPERS (Golden Drive support)
# ========================================
# Freshness: runtime_state is considered fresh if mode=="in_game" and updated within FRESHNESS_SECONDS

RUNTIME_STATE_FRESHNESS_SECONDS = 300  # 5 minutes

def _is_runtime_state_fresh(runtime_state: Dict[str, Any]) -> bool:
    """Check if runtime_state is fresh enough for hydration.
    
    Fresh = mode is 'in_game' AND last_updated within FRESHNESS_SECONDS.
    """
    if not runtime_state:
        return False
    if runtime_state.get("mode") != "in_game":
        return False
    last_updated = runtime_state.get("last_updated")
    if not last_updated:
        return False
    try:
        from datetime import timezone
        updated_dt = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = (now - updated_dt).total_seconds()
        return delta <= RUNTIME_STATE_FRESHNESS_SECONDS
    except Exception:
        return False


def _resolve_device_id(request: Request) -> str:
    """Resolve device_id from headers, state, or env. Returns 'unknown' if unavailable."""
    device_id = request.headers.get('x-device-id') or ''
    if not device_id:
        device_id = getattr(request.state, 'device_id', '') or ''
    if not device_id:
        device_id = os.getenv('AA_DEVICE_ID', '')
    return device_id.strip() or 'unknown'


def _resolve_frontend_source(request: Request, runtime_state: Dict[str, Any], is_fresh: bool) -> str:
    """Resolve frontend_source from header or runtime_state. Returns 'unknown' if unavailable."""
    # Prefer x-panel header
    panel = (request.headers.get('x-panel') or '').strip().lower()
    if panel:
        # Normalize known values
        if panel in ('retrofe', 'launchbox', 'pegasus', 'bigbox'):
            return panel
        return panel
    # Fallback to runtime_state if fresh
    if is_fresh and runtime_state:
        frontend = runtime_state.get('frontend')
        if frontend:
            return frontend
    return 'unknown'

def _consent_file(drive_root: Path) -> Path:
    return drive_root / ".aa" / "state" / "profile" / "consent.json"


def _load_consent(drive_root: Path) -> Dict[str, Any]:
    path = _consent_file(drive_root)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _consent_scopes(consent: Dict[str, Any]) -> set[str]:
    raw = consent.get("scopes")
    if not isinstance(raw, list):
        return set()
    return {str(scope).strip().lower() for scope in raw if str(scope).strip()}


def _is_tracking_opted_in(drive_root: Path) -> bool:
    """
    User activity tracking gate.
    Backward compatible: allows either legacy `network_participation`
    or explicit `activity_tracking`.
    """
    consent = _load_consent(drive_root)
    if not bool(consent.get("accepted")):
        return False
    scopes = _consent_scopes(consent)
    return ("network_participation" in scopes) or ("activity_tracking" in scopes)


def _is_public_leaderboard_opted_in(drive_root: Path) -> bool:
    consent = _load_consent(drive_root)
    if not bool(consent.get("accepted")):
        return False
    scopes = _consent_scopes(consent)
    return "leaderboard_public" in scopes

async def list_tournaments(drive_root: Path) -> List[Dict[str, Any]]:
    def _do_list():
        tdir = get_scorekeeper_dir(drive_root) / "tournaments"
        if not tdir.exists():
            return []
        items: List[Dict[str, Any]] = []
        for p in tdir.glob("*.json"):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    items.append({
                        "id": data.get("id") or p.stem,
                        "name": data.get("name", p.stem),
                        "status": data.get("status", "unknown"),
                        "player_count": data.get("player_count"),
                        "created_at": data.get("created_at"),
                        "path": str(p.relative_to(drive_root))
                    })
            except Exception:
                continue
        # Sort newest first by created_at
        def _ts(x):
            try:
                return datetime.fromisoformat(x.get("created_at") or "1970-01-01T00:00:00")
            except Exception:
                return datetime(1970, 1, 1)
        items.sort(key=_ts, reverse=True)
        return items
    return await asyncio.to_thread(_do_list)

async def read_scores(scores_file: Path) -> List[Dict[str, Any]]:
    """Read all scores from scores.jsonl"""
    def _do_read():
        if not scores_file.exists():
            return []

        scores = []
        with open(scores_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    scores.append(json.loads(line))
        return scores
    return await asyncio.to_thread(_do_read)


def _normalize_game_name(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


# ========================================
# HIGH SCORE AGGREGATION SERVICE (v1)
# ========================================
# Aggregates scores.jsonl into high_scores_index.json
# Groups by game_title with optional game_id support
# Does NOT modify scores.jsonl - read-only aggregation

def get_high_scores_index_file(drive_root: Path) -> Path:
    """Get the high_scores_index.json file path (same directory as scores.jsonl)"""
    return get_scorekeeper_dir(drive_root) / "high_scores_index.json"


async def build_high_scores_index(drive_root: Path, top_n: int = 10) -> Dict[str, Any]:
    """
    Build the high scores index from scores.jsonl.
    
    Groups scores by game title, sorts by score DESC, keeps top N per game.
    Returns the complete index structure ready to be saved.
    
    Args:
        drive_root: The drive root path
        top_n: Maximum number of top scores to keep per game (default 10)
    
    Returns:
        The high scores index dictionary
    """
    scores_file = get_scores_file(drive_root)
    all_scores = await read_scores(scores_file)
    
    # Group scores by game title
    # Key: game_title (string), Value: list of score entries
    games_map: Dict[str, Dict[str, Any]] = {}
    
    for entry in all_scores:
        # Get game title - this is the primary grouping key
        game_title = entry.get("game") or entry.get("game_title") or "Unknown"
        # Optional game_id if present (for future compatibility)
        game_id = entry.get("game_id") or entry.get("gameId")
        system = entry.get("platform") or entry.get("system")
        
        if game_title not in games_map:
            games_map[game_title] = {
                "game_title": game_title,
                "game_id": game_id,  # Will be None if not present
                "system": system or None,
                "scores": []
            }
        
        # If we didn't have a game_id before but this entry has one, use it
        if game_id and not games_map[game_title]["game_id"]:
            games_map[game_title]["game_id"] = game_id
        # Carry first non-null system if missing
        if system and not games_map[game_title]["system"]:
            games_map[game_title]["system"] = system
        
        # Add the score entry (preserving identity fields for traceability)
        games_map[game_title]["scores"].append({
            "player": entry.get("player") or entry.get("player_name") or "Unknown",
            "score": entry.get("score", 0),
            "timestamp": entry.get("timestamp") or entry.get("achieved_at"),
            # Identity fields (Golden Drive)
            "device_id": entry.get("device_id"),
            "frontend_source": entry.get("frontend_source"),
        })
    
    # Sort each game's scores DESC and keep top N
    games_list = []
    for game_title, game_data in games_map.items():
        sorted_scores = sorted(
            game_data["scores"],
            key=lambda x: x.get("score", 0),
            reverse=True
        )[:top_n]
        
        games_list.append({
            "game_title": game_data["game_title"],
            "game_id": game_data["game_id"],
            "system": game_data.get("system"),
            "top_scores": sorted_scores
        })
    
    # Sort games alphabetically by title
    games_list.sort(key=lambda x: x["game_title"].lower())
    
    return {
        "version": 1,
        "last_updated": datetime.now().isoformat(),
        "games": games_list
    }


async def save_high_scores_index(drive_root: Path, index: Dict[str, Any]) -> Path:
    """
    Save the high scores index to disk.
    
    Args:
        drive_root: The drive root path
        index: The index dictionary to save
    
    Returns:
        The path where the index was saved
    """
    def _do_save():
        index_file = get_high_scores_index_file(drive_root)
        index_file.parent.mkdir(parents=True, exist_ok=True)

        tmp = index_file.with_suffix(".tmp")
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2)
        tmp.replace(index_file)
        return index_file

    index_file = await asyncio.to_thread(_do_save)
    logger.info("high_scores_index_saved", path=str(index_file), game_count=len(index.get("games", [])))
    return index_file


async def regenerate_high_scores_index(drive_root: Path) -> Dict[str, Any]:
    """Helper to rebuild and save the index."""
    index = await build_high_scores_index(drive_root)
    await save_high_scores_index(drive_root, index)
    return index


async def load_high_scores_index(drive_root: Path, regenerate_if_stale: bool = True) -> Dict[str, Any]:
    """
    Load the high scores index, optionally regenerating if stale.
    
    The index is considered stale if:
    - It doesn't exist
    - scores.jsonl has been modified more recently than the index
    
    Args:
        drive_root: The drive root path
        regenerate_if_stale: If True, rebuild index when stale (default True)
    
    Returns:
        The high scores index dictionary
    """
    index_file = get_high_scores_index_file(drive_root)
    scores_file = get_scores_file(drive_root)
    
    needs_rebuild = False
    
    # Check if index exists
    if not index_file.exists():
        needs_rebuild = True
        logger.info("high_scores_index_missing", action="will_rebuild")
    elif regenerate_if_stale and scores_file.exists():
        # Check if scores.jsonl is newer than the index
        scores_mtime = scores_file.stat().st_mtime
        index_mtime = index_file.stat().st_mtime
        if scores_mtime > index_mtime:
            needs_rebuild = True
            logger.info("high_scores_index_stale", action="will_rebuild")
    
    if needs_rebuild and regenerate_if_stale:
        index = await build_high_scores_index(drive_root)
        await save_high_scores_index(drive_root, index)
        return index
    
    # Load existing index
    if index_file.exists():
        try:
            def _do_load():
                with open(index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return await asyncio.to_thread(_do_load)
        except Exception as e:
            logger.warning("high_scores_index_load_failed", error=str(e))
            # Fall back to rebuilding
            index = await build_high_scores_index(drive_root)
            await save_high_scores_index(drive_root, index)
            return index
    
    # No scores at all - return empty index
    return {
        "version": 1,
        "last_updated": datetime.now().isoformat(),
        "games": []
    }

def create_bracket(player_count: int, players: List[str] = None) -> List[Dict[str, Any]]:
    """Create a tournament bracket structure

    Args:
        player_count: Number of players (4, 8, 16, or 32)
        players: Optional list of player names (will use placeholders if not provided)

    Returns:
        List of match dictionaries
    """
    if player_count not in [4, 8, 16, 32]:
        raise ValueError("Player count must be 4, 8, 16, or 32")

    # Generate placeholder players if not provided
    if not players:
        players = [f"Player {i+1}" for i in range(player_count)]
    elif len(players) < player_count:
        # Pad with placeholders
        players.extend([f"Player {i+1}" for i in range(len(players), player_count)])

    matches = []
    num_matches = player_count - 1  # Total matches in single elimination

    # First round
    first_round_matches = player_count // 2
    for i in range(first_round_matches):
        matches.append({
            "match_index": i,
            "round": 1,
            "player1": players[i * 2],
            "player2": players[i * 2 + 1],
            "winner": None,
            "status": "pending"
        })

    # Remaining rounds (placeholders)
    match_index = first_round_matches
    current_round = 2
    matches_in_round = first_round_matches // 2

    while matches_in_round > 0:
        for i in range(matches_in_round):
            matches.append({
                "match_index": match_index,
                "round": current_round,
                "player1": "TBD",
                "player2": "TBD",
                "winner": None,
                "status": "locked"
            })
            match_index += 1

        matches_in_round //= 2
        current_round += 1

    return matches

def log_scorekeeper_change(request: Request, drive_root: Path, action: str, details: Dict[str, Any], backup_path: Optional[Path] = None):
    """Log scorekeeper action to .aa/logs/scorekeeper_changes.jsonl (Golden Drive contract)."""
    # Use .aa\logs per Golden Drive contract (not drive_root\logs)
    aa_log_root = Path(os.getenv("AA_DRIVE_ROOT", str(drive_root))) / ".aa" / "logs"
    try:
        aa_log_root.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        # No silent fallback - if .aa/logs fails, raise explicit error
        raise RuntimeError(f"Cannot create .aa/logs directory at {aa_log_root}: {e}")
    log_file = aa_log_root / "scorekeeper_changes.jsonl"

    device = request.headers.get('x-device-id', 'unknown') if hasattr(request, 'headers') else 'unknown'
    panel = request.headers.get('x-panel', 'unknown') if hasattr(request, 'headers') else 'unknown'

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "scope": "scorekeeper",
        "action": action,
        "details": details,
        "backup_path": str(backup_path) if backup_path else None,
        "device": device,
        "panel": panel,
    }

    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception:
        # Best-effort logging; do not block scoring on log failure
        pass

def require_scorekeeper_scope(request: Request, allowed_scopes: List[str]) -> str:
    scope = request.headers.get("x-scope")
    if not scope:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required x-scope header. Allowed: {allowed_scopes}"
        )
    if scope not in allowed_scopes:
        raise HTTPException(
            status_code=400,
            detail=f"x-scope '{scope}' not permitted. Allowed: {allowed_scopes}"
        )
    return scope

def _scorekeeper_backup_root(drive_root: Path) -> Path:
    return drive_root / ".aa" / "backups" / "scorekeeper"

def _latest_scorekeeper_snapshot(drive_root: Path) -> Path:
    """Locate the newest scorekeeper snapshot.json."""
    backup_root = _scorekeeper_backup_root(drive_root)
    if not backup_root.exists():
        raise HTTPException(status_code=404, detail="No scorekeeper backups found.")

    snapshot_dirs = sorted([path for path in backup_root.iterdir() if path.is_dir()])
    if not snapshot_dirs:
        raise HTTPException(status_code=404, detail="No scorekeeper snapshots available.")

    latest_snapshot = snapshot_dirs[-1] / "snapshot.json"
    if not latest_snapshot.exists():
        raise HTTPException(status_code=404, detail="Latest snapshot is missing snapshot.json.")
    return latest_snapshot

def _list_scorekeeper_files(drive_root: Path) -> List[Path]:
    base_dir = get_scorekeeper_dir(drive_root)
    if not base_dir.exists():
        return []
    return [path for path in base_dir.rglob("*") if path.is_file()]

def _rel_str(path: Path, drive_root: Path) -> str:
    return str(path.relative_to(drive_root)).replace("\\", "/")

def _bytes_to_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")

def create_scorekeeper_snapshot(drive_root: Path, reason: str = "apply") -> Path:
    """Capture current state/scorekeeper files into a JSON snapshot."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_dir = _scorekeeper_backup_root(drive_root) / timestamp
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    files = []
    for file_path in _list_scorekeeper_files(drive_root):
        data = file_path.read_bytes()
        stat = file_path.stat()
        files.append({
            "path": _rel_str(file_path, drive_root),
            "encoding": "base64",
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "data": base64.b64encode(data).decode("ascii")
        })

    snapshot = {
        "version": 1,
        "created_at": datetime.now().isoformat(),
        "reason": reason,
        "file_count": len(files),
        "files": files
    }

    snapshot_path = snapshot_dir / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return snapshot_path

def _load_snapshot(snapshot_path: Path) -> Dict[str, Any]:
    with open(snapshot_path, "r", encoding="utf-8") as f:
        return json.load(f)

def restore_scorekeeper_snapshot(
    drive_root: Path,
    snapshot_path: Path,
    manifest: Dict[str, Any],
    dry_run: bool = False
) -> Dict[str, Any]:
    """Restore files described in snapshot.json; returns diff metadata."""
    snapshot = _load_snapshot(snapshot_path)
    files = snapshot.get("files", [])
    manifest_paths = manifest.get("sanctioned_paths", [])

    existing_files = {_rel_str(path, drive_root): path for path in _list_scorekeeper_files(drive_root)}
    snapshot_files = {entry["path"]: entry for entry in files}

    file_diffs: List[Dict[str, Any]] = []
    has_any_change = False

    # Restore or create files from snapshot
    for rel_path, entry in snapshot_files.items():
        target_path = (drive_root / rel_path).resolve()
        if not is_allowed_file(target_path, drive_root, manifest_paths):
            raise HTTPException(
                status_code=403,
                detail=f"Snapshot file outside sanctioned paths: {rel_path}"
            )

        new_bytes = base64.b64decode(entry.get("data", "").encode("ascii"))
        current_bytes = target_path.read_bytes() if target_path.exists() else b""

        current_text = _bytes_to_text(current_bytes)
        new_text = _bytes_to_text(new_bytes)
        diff_text = compute_diff(current_text, new_text, rel_path)
        changed = has_changes(current_text, new_text)
        if changed:
            has_any_change = True

        file_diffs.append({
            "path": rel_path,
            "diff": diff_text,
            "changed": changed
        })

        if not dry_run:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(new_bytes)

    # Remove files that are not present in snapshot
    removed_files = []
    for rel_path, existing_path in existing_files.items():
        if rel_path in snapshot_files:
            continue
        if not is_allowed_file(existing_path, drive_root, manifest_paths):
            continue

        current_bytes = existing_path.read_bytes()
        current_text = _bytes_to_text(current_bytes)
        diff_text = compute_diff(current_text, "", rel_path)
        has_any_change = has_any_change or bool(current_text)
        file_diffs.append({
            "path": rel_path,
            "diff": diff_text,
            "changed": bool(current_text),
            "removed": True
        })
        removed_files.append(rel_path)

        if not dry_run and existing_path.exists():
            existing_path.unlink()

    diff_output = "\n\n".join([entry["diff"] for entry in file_diffs if entry.get("diff")])

    return {
        "diff": diff_output,
        "files_changed": sum(1 for entry in file_diffs if entry.get("changed")),
        "removed_files": removed_files,
        "has_changes": has_any_change,
        "file_details": file_diffs
    }


# ========================================
# HIGH SCORE ENDPOINTS (v1 - Read-Only)
# ========================================
# These endpoints expose high_scores_index.json data
# They do NOT modify scores.jsonl or tournament data

@router.get("/highscores/cabinet")
async def get_cabinet_high_scores(request: Request):
    """
    Get the cabinet-wide high scores summary.
    
    Returns the contents of high_scores_index.json, regenerating if necessary.
    This is the main endpoint for the CabinetHighScoresPanel.
    
    Returns:
        The complete high scores index with all games and their top scores
    """
    try:
        drive_root = request.app.state.drive_root
        index = await load_high_scores_index(drive_root, regenerate_if_stale=True)
        
        return {
            "status": "ok",
            "version": index.get("version", 1),
            "last_updated": index.get("last_updated"),
            "game_count": len(index.get("games", [])),
            "games": index.get("games", [])
        }
    except Exception as e:
        logger.error("get_cabinet_high_scores_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/highscores/game")
async def get_game_high_scores(
    request: Request,
    title: Optional[str] = Query(None, description="Game title (case-insensitive exact)"),
    game_id: Optional[str] = Query(None, description="Optional game_id to match"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of scores to return")
):
    """
    Get top scores for a specific game by title or game_id.
    """
    try:
        drive_root = request.app.state.drive_root
        index = await load_high_scores_index(drive_root, regenerate_if_stale=True)
        games = index.get("games", []) or []

        def _match(g: Dict[str, Any]) -> bool:
            if game_id and g.get("game_id"):
                if str(g.get("game_id")).strip().lower() == game_id.strip().lower():
                    return True
            if title and g.get("game_title"):
                if g.get("game_title", "").strip().lower() == title.strip().lower():
                    return True
            return False

        game_data = next((g for g in games if _match(g)), None)

        if not game_data:
            raise HTTPException(status_code=404, detail="Game not found in high score index")

        return {
            "status": "ok",
            "game_title": game_data.get("game_title"),
            "game_id": game_data.get("game_id"),
            "system": game_data.get("system"),
            "top_scores": (game_data.get("top_scores") or [])[:limit]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_game_high_scores_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-game")
async def get_scores_by_game(request: Request):
    """
    Get all games with their top scores (frontend compatibility endpoint).
    
    This is the endpoint the frontend expects for the "By Game" view.
    Returns a simplified array format suitable for dropdowns and lists.
    
    Returns:
        Array of games, each with game_id, game_title, and top_scores
    """
    try:
        drive_root = request.app.state.drive_root
        index = await load_high_scores_index(drive_root, regenerate_if_stale=True)
        
        # Return the games array directly for frontend compatibility
        games = index.get("games", [])
        
        return {
            "status": "ok",
            "count": len(games),
            "games": games
        }
    except Exception as e:
        logger.error("get_scores_by_game_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/undo")
async def undo_last_change(request: Request, payload: Optional[ScorekeeperUndoRequest] = Body(default=None)):
    """Revert scorekeeper state using the most recent snapshot."""
    require_scorekeeper_scope(request, ["backup", "state", "local"])

    drive_root = request.app.state.drive_root
    manifest = getattr(request.app.state, "manifest", {}) or {}
    latest_snapshot = _latest_scorekeeper_snapshot(drive_root)

    dry_default = getattr(request.app.state, "dry_run_default", True)
    requested_dry = payload.dry_run if payload else None
    dry_run = requested_dry if requested_dry is not None else dry_default

    pre_restore_snapshot = None
    if not dry_run and getattr(request.app.state, "backup_on_write", True):
        pre_restore_snapshot = create_scorekeeper_snapshot(drive_root, reason="pre-undo")

    diff_result = restore_scorekeeper_snapshot(
        drive_root,
        latest_snapshot,
        manifest,
        dry_run=dry_run
    )

    log_scorekeeper_change(
        request,
        drive_root,
        "undo",
        {
            "files_changed": diff_result["files_changed"],
            "removed_files": diff_result["removed_files"],
            "dry_run": dry_run
        },
        Path(latest_snapshot)
    )

    message = "Dry-run preview generated" if dry_run else "Scorekeeper state restored from latest snapshot"

    return {
        "restored": bool(diff_result["has_changes"] and not dry_run),
        "dry_run": dry_run,
        "backup_path": str(latest_snapshot),
        "diff": diff_result["diff"],
        "files_changed": diff_result["files_changed"],
        "removed_files": diff_result["removed_files"],
        "pre_restore_backup": str(pre_restore_snapshot) if pre_restore_snapshot else None,
        "message": message
    }

@router.post("/restore")
async def restore_scorekeeper_state(request: Request, payload: ScorekeeperRestoreRequest):
    """Restore scorekeeper state from a specific snapshot file."""
    require_scorekeeper_scope(request, ["backup", "state", "local"])

    drive_root = request.app.state.drive_root
    manifest = getattr(request.app.state, "manifest", {}) or {}

    if payload.strategy == "last":
        snapshot_path = _latest_scorekeeper_snapshot(drive_root)
    else:
        backup_path_value = payload.backup_path
        if not backup_path_value:
            raise HTTPException(status_code=400, detail="backup_path is required when strategy is not used.")
        snapshot_path = Path(backup_path_value)
        if not snapshot_path.is_absolute():
            snapshot_path = (drive_root / snapshot_path).resolve()
        else:
            snapshot_path = snapshot_path.resolve()

        backup_root = _scorekeeper_backup_root(drive_root).resolve()
        try:
            snapshot_path.relative_to(backup_root)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="backup_path must live under drive_root/.aa/backups/scorekeeper"
            )

        if not snapshot_path.exists():
            raise HTTPException(status_code=404, detail=f"Snapshot not found: {snapshot_path}")

    dry_default = getattr(request.app.state, "dry_run_default", True)
    dry_run = payload.dry_run if payload.dry_run is not None else dry_default

    pre_restore_snapshot = None
    if not dry_run and getattr(request.app.state, "backup_on_write", True):
        pre_restore_snapshot = create_scorekeeper_snapshot(drive_root, reason="pre-restore")

    diff_result = restore_scorekeeper_snapshot(
        drive_root,
        snapshot_path,
        manifest,
        dry_run=dry_run
    )

    log_scorekeeper_change(
        request,
        drive_root,
        "restore",
        {
            "backup_path": str(snapshot_path),
            "files_changed": diff_result["files_changed"],
            "removed_files": diff_result["removed_files"],
            "dry_run": dry_run
        },
        snapshot_path
    )

    message = "Dry-run preview generated" if dry_run else f"Scorekeeper state restored from {snapshot_path.name}"

    return {
        "restored": bool(diff_result["has_changes"] and not dry_run),
        "dry_run": dry_run,
        "backup_path": str(snapshot_path),
        "diff": diff_result["diff"],
        "files_changed": diff_result["files_changed"],
        "removed_files": diff_result["removed_files"],
        "pre_restore_backup": str(pre_restore_snapshot) if pre_restore_snapshot else None,
        "message": message
    }

# Routes
@router.get("/tournaments")
async def list_tournaments_route(request: Request):
    try:
        drive_root = request.app.state.drive_root
        items = await list_tournaments(drive_root)
        return {"count": len(items), "tournaments": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/leaderboard")
async def get_leaderboard(
    request: Request,
    game: Optional[str] = Query(None, description="Filter by game name"),
    limit: int = Query(10, description="Number of top scores to return")
):
    """Get top scores (leaderboard)"""
    try:
        drive_root = request.app.state.drive_root
        scores_file = get_scores_file(drive_root)

        # Read all scores
        all_scores = await read_scores(scores_file)

        # Filter by game if specified (case/punctuation insensitive)
        if game:
            target = _normalize_game_name(game)
            all_scores = [
                s for s in all_scores
                if _normalize_game_name(s.get("game")) == target
            ]

        # Sort by score descending
        all_scores.sort(key=lambda x: x.get("score", 0), reverse=True)

        # Limit results
        top_scores = all_scores[:limit]

        return {
            "game": game or "all",
            "count": len(top_scores),
            "scores": top_scores
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/submit/preview")
async def preview_score_submit(request: Request, score_data: ScoreSubmit):
    """Preview score submission (no write)"""
    try:
        drive_root = request.app.state.drive_root
        scores_file = get_scores_file(drive_root)

        # Read current content
        current_content = ""
        if scores_file.exists():
            def _do_read():
                with open(scores_file, 'r', encoding='utf-8') as f:
                    return f.read()
            current_content = await asyncio.to_thread(_do_read)

        # Create new entry
        new_entry = {
            "timestamp": datetime.now().isoformat(),
            "game": score_data.game,
            "player": score_data.player,
            "score": score_data.score
        }
        # Optional metadata if provided
        if score_data.game_id:
            new_entry["game_id"] = score_data.game_id
        if score_data.system:
            new_entry["system"] = score_data.system
        if score_data.platform:
            new_entry["platform"] = score_data.platform
        if score_data.player_userId:
            new_entry["player_userId"] = score_data.player_userId
        if score_data.player_source:
            new_entry["player_source"] = score_data.player_source
        if score_data.publicLeaderboardEligible is not None:
            new_entry["publicLeaderboardEligible"] = score_data.publicLeaderboardEligible

        # Append to content
        new_content = current_content
        if new_content and not new_content.endswith('\n'):
            new_content += '\n'
        new_content += json.dumps(new_entry) + '\n'

        # Generate diff
        diff = compute_diff(current_content, new_content, "scores.jsonl")

        return {
            "target_file": "state/scorekeeper/scores.jsonl",
            "has_changes": True,
            "diff": diff,
            "entry": new_entry,
            "file_exists": scores_file.exists()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/submit/apply")
async def apply_score_submit(request: Request, score_data: ScoreSubmit):
    """Apply score submission (append to scores.jsonl)
    
    Golden Drive contract: Every score entry includes identity fields:
    - device_id (cabinet identity)
    - frontend_source (launchbox/retrofe/pegasus/etc)
    - game (title) + optional game_id/system/platform
    """
    try:
        # Validate scope header
        require_scope(request, "state")

        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        scores_file = get_scores_file(drive_root)

        snapshot_path: Optional[Path] = None
        if getattr(request.app.state, "backup_on_write", True):
            snapshot_path = create_scorekeeper_snapshot(drive_root, reason="score_submit")

        # Validate path is in sanctioned areas
        if not is_allowed_file(scores_file, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(
                status_code=403,
                detail=f"File not in sanctioned areas: {scores_file}"
            )

        # Ensure directory exists
        scores_file.parent.mkdir(parents=True, exist_ok=True)

        # Create backup if file exists
        file_backup_path = None
        if scores_file.exists() and request.app.state.backup_on_write:
            file_backup_path = create_backup(scores_file, drive_root)

        # ========================================
        # IDENTITY RESOLUTION (Golden Drive)
        # ========================================
        # Load runtime state for hydration fallback
        runtime_state = {}
        try:
            runtime_state = load_runtime_state(drive_root)
        except Exception:
            pass
        is_fresh = _is_runtime_state_fresh(runtime_state)

        # Resolve identity fields
        device_id = _resolve_device_id(request)
        frontend_source = _resolve_frontend_source(request, runtime_state, is_fresh)

        tracking_opted_in = _is_tracking_opted_in(drive_root)
        public_leaderboard_opted_in = _is_public_leaderboard_opted_in(drive_root)

        resolved_player_user_id = score_data.player_userId if tracking_opted_in else None
        resolved_player_source = score_data.player_source if tracking_opted_in else "guest"
        resolved_public_leaderboard_eligible = (
            bool(score_data.publicLeaderboardEligible)
            and tracking_opted_in
            and public_leaderboard_opted_in
        )

        if (not tracking_opted_in) and (score_data.player_userId or score_data.player_source == "profile"):
            logger.info(
                "score_submit_identity_redacted_no_opt_in",
                game=score_data.game,
                player=score_data.player,
            )

        # Game identifiers: use payload or hydrate from runtime_state if fresh
        game_title = score_data.game
        game_id = score_data.game_id
        system_platform = score_data.system or score_data.platform
        
        # Hydrate from runtime_state if fresh and payload has minimal info
        if is_fresh and runtime_state:
            if not game_id:
                game_id = runtime_state.get("game_id")
            if not system_platform:
                system_platform = runtime_state.get("system_id") or runtime_state.get("platform")
            # If game title is missing but runtime_state has it, use that (edge case)
            if not game_title and runtime_state.get("game_title"):
                game_title = runtime_state.get("game_title")
                logger.warning("score_submit_hydrated_game_title", 
                              source="runtime_state", 
                              game_title=game_title)

        # Ensure we have at least a game identifier
        if not game_title:
            game_title = "unknown"
            logger.warning("score_submit_missing_game", player=score_data.player)

        # ========================================
        # BUILD NORMALIZED ENTRY
        # ========================================
        entry = {
            "timestamp": datetime.now().isoformat(),
            # Core identity fields (Golden Drive contract)
            "device_id": device_id,
            "frontend_source": frontend_source,
            # Game identifiers
            "game": game_title,
            "game_id": game_id,
            "system": system_platform,
            # Score data
            "player": score_data.player,
            "score": score_data.score
        }
        # Optional metadata preserved
        if resolved_player_user_id:
            entry["player_userId"] = resolved_player_user_id
        if resolved_player_source:
            entry["player_source"] = resolved_player_source
        entry["publicLeaderboardEligible"] = resolved_public_leaderboard_eligible

        # Append to file
        def _do_append():
            with open(scores_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')
        await asyncio.to_thread(_do_append)

        # ========================================
        # SUPABASE MIRROR (best-effort, non-blocking)
        # ========================================
        try:
            if device_id and device_id != 'unknown':
                await asyncio.to_thread(
                    sb_insert_score,
                    device_id,
                    game_title,
                    score_data.player,
                    score_data.score,
                    {
                        'source': 'scorekeeper_submit',
                        'frontend_source': frontend_source,
                        'game_id': game_id,
                        'system': system_platform,
                        'player_userId': resolved_player_user_id,
                        'player_source': resolved_player_source,
                        'public_leaderboard_eligible': resolved_public_leaderboard_eligible,
                    }
                )
        except Exception:
            # Best-effort only; ignore failures
            pass

        # Broadcast to Gateway for real-time leaderboard push
        try:
            await asyncio.to_thread(_broadcast_score_update, game_title, entry, "scorekeeper_submit")
        except Exception:
            pass  # Best-effort; don't fail the request

        # Log change
        log_scorekeeper_change(
            request, drive_root, "score_submit",
            {
                "game": game_title,
                "game_id": game_id,
                "player": score_data.player,
                "score": score_data.score,
                "device_id": device_id,
                "frontend_source": frontend_source,
                "file_backup_path": str(file_backup_path) if file_backup_path else None
            },
            snapshot_path
        )

        return {
            "status": "applied",
            "target_file": "state/scorekeeper/scores.jsonl",
            "backup_path": str(snapshot_path) if snapshot_path else None,
            "file_backup_path": str(file_backup_path) if file_backup_path else None,
            "entry": entry
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/submit")
async def submit_score_alias(request: Request, score_data: ScoreSubmit):
    """Compatibility alias for score submission (routes to /submit/apply)."""
    return await apply_score_submit(request, score_data)

@router.get("/coverage")
async def get_score_tracking_coverage(request: Request):
    drive_root = request.app.state.drive_root
    service = get_score_tracking_service(drive_root)
    return service.coverage_summary()

@router.get("/attempts/review-queue")
async def get_score_attempt_review_queue(request: Request, limit: int = Query(default=25, ge=1, le=100)):
    drive_root = request.app.state.drive_root
    service = get_score_tracking_service(drive_root)
    items = service.list_review_queue(limit=limit)
    return {
        "items": items,
        "count": len(items),
    }


class ScoreAttemptReviewRequest(BaseModel):
    """Review action for a pending score attempt."""
    action: Literal["approve", "edit", "reject", "mark_unsupported"]
    score: Optional[int] = None
    player: Optional[str] = None
    note: Optional[str] = None

@router.post("/attempts/{attempt_id}/review")
async def review_score_attempt(request: Request, attempt_id: str, review: ScoreAttemptReviewRequest):
    require_scope(request, "state")
    drive_root = request.app.state.drive_root
    service = get_score_tracking_service(drive_root)
    decision = ScoreReviewDecision.model_validate(review.model_dump())
    attempt = service.review_attempt(attempt_id, decision)
    if not attempt:
        raise HTTPException(status_code=404, detail="Score attempt not found")

    score_result = None
    if attempt.status == "captured_manual" and attempt.final_score is not None:
        score_result = await apply_score_submit(
            request,
            ScoreSubmit(
                game=attempt.game_title,
                game_id=attempt.game_id,
                system=attempt.platform,
                platform=attempt.platform,
                player=attempt.player or "unknown",
                score=int(attempt.final_score),
            ),
        )

    return {
        "status": "ok",
        "attempt": attempt.model_dump(),
        "score_result": score_result,
    }


@router.post("/tournaments/create/preview")
async def preview_tournament_create(request: Request, tournament_data: TournamentCreate):
    """Preview tournament creation"""
    try:
        if tournament_data.player_count not in [4, 8, 16, 32]:
            raise HTTPException(
                status_code=400,
                detail="Player count must be 4, 8, 16, or 32"
            )

        drive_root = request.app.state.drive_root
        tournament_id = str(uuid.uuid4())[:8]
        tournament_file = get_tournament_file(drive_root, tournament_id)

        # Create tournament structure
        tournament = {
            "id": tournament_id,
            "name": tournament_data.name,
            "game": tournament_data.game,
            "player_count": tournament_data.player_count,
            "created_at": datetime.now().isoformat(),
            "status": "active",
            "current_round": 1,
            "matches": create_bracket(tournament_data.player_count)
        }

        new_content = json.dumps(tournament, indent=2)

        # Generate diff (no old content since it's a new file)
        diff = compute_diff("", new_content, f"tournaments/{tournament_id}.json")

        return {
            "target_file": f"state/scorekeeper/tournaments/{tournament_id}.json",
            "has_changes": True,
            "diff": diff,
            "tournament": tournament,
            "file_exists": False
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def _apply_tournament_create_impl(
    request: Request,
    tournament_data: TournamentCreate,
    *, source: str = "standard"
) -> Dict[str, Any]:
    """Shared implementation for tournament creation variants."""
    # Validate scope header
    require_scope(request, "state")

    if tournament_data.player_count not in [4, 8, 16, 32]:
        raise HTTPException(
            status_code=400,
            detail="Player count must be 4, 8, 16, or 32"
        )

    drive_root = request.app.state.drive_root
    manifest = request.app.state.manifest
    tournament_id = str(uuid.uuid4())[:8]
    tournament_file = get_tournament_file(drive_root, tournament_id)

    snapshot_path: Optional[Path] = None
    if getattr(request.app.state, "backup_on_write", True):
        snapshot_path = create_scorekeeper_snapshot(drive_root, reason="tournament_create")

    # Validate path is in sanctioned areas
    if not is_allowed_file(tournament_file, drive_root, manifest["sanctioned_paths"]):
        raise HTTPException(
            status_code=403,
            detail=f"File not in sanctioned areas: {tournament_file}"
        )

    # Ensure directory exists
    tournament_file.parent.mkdir(parents=True, exist_ok=True)

    # Create tournament structure
    tournament = {
        "id": tournament_id,
        "name": tournament_data.name,
        "game": tournament_data.game,
        "player_count": tournament_data.player_count,
        "created_at": datetime.now().isoformat(),
        "status": "active",
        "current_round": 1,
        "matches": create_bracket(tournament_data.player_count)
    }

    # Write tournament file
    def _do_write():
        with open(tournament_file, 'w', encoding='utf-8') as f:
            json.dump(tournament, f, indent=2)
    await asyncio.to_thread(_do_write)

    # Log change
    log_details = {
        "tournament_id": tournament_id,
        "name": tournament_data.name,
        "player_count": tournament_data.player_count,
        "source": source
    }
    log_scorekeeper_change(
        request, drive_root, "tournament_create",
        log_details,
        snapshot_path
    )

    return {
        "status": "applied",
        "target_file": f"state/scorekeeper/tournaments/{tournament_id}.json",
        "backup_path": str(snapshot_path) if snapshot_path else None,
        "tournament": tournament
    }

@router.post("/tournaments/create/apply")
async def apply_tournament_create(request: Request, tournament_data: TournamentCreate):
    """Apply tournament creation"""
    try:
        return await _apply_tournament_create_impl(request, tournament_data, source="standard")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tournament/create")
async def legacy_tournament_create(request: Request, payload: LegacyTournamentCreate):
    """Backward compatible create endpoint (name+size) used by legacy acceptance tests."""
    try:
        player_count = payload.size
        tournament_data = TournamentCreate(
            name=payload.name,
            game=payload.game or "Arcade",
            player_count=player_count
        )
        result = await _apply_tournament_create_impl(request, tournament_data, source="legacy")
        result["legacy_request"] = True
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tournaments/{tournament_id}")
async def get_tournament(request: Request, tournament_id: str):
    """Get tournament state"""
    try:
        drive_root = request.app.state.drive_root
        tournament_file = get_tournament_file(drive_root, tournament_id)

        def _do_get():
            if not tournament_file.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Tournament not found: {tournament_id}"
                )

            with open(tournament_file, 'r', encoding='utf-8') as f:
                return json.load(f)

        return await asyncio.to_thread(_do_get)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tournaments/report/preview")
async def preview_tournament_report(request: Request, report_data: TournamentReport):
    """Preview tournament match winner report"""
    try:
        drive_root = request.app.state.drive_root
        tournament_file = get_tournament_file(drive_root, report_data.tournament_id)

        def _do_read():
            if not tournament_file.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Tournament not found: {report_data.tournament_id}"
                )

            # Read current tournament
            with open(tournament_file, 'r', encoding='utf-8') as f:
                content = f.read()
                return content, json.loads(content)

        old_content, tournament = await asyncio.to_thread(_do_read)

        # Find and update match
        if report_data.match_index >= len(tournament["matches"]):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid match_index: {report_data.match_index}"
            )

        match = tournament["matches"][report_data.match_index]

        # Validate winner is one of the players
        if report_data.winner_player not in [match["player1"], match["player2"]]:
            raise HTTPException(
                status_code=400,
                detail=f"Winner must be one of the match players: {match['player1']} or {match['player2']}"
            )

        # Update match
        match["winner"] = report_data.winner_player
        match["status"] = "completed"

        # Advance winner to next round (if exists)
        current_round = match["round"]
        position_in_round = report_data.match_index % (2 ** (current_round - 1))
        next_match_index = (tournament["player_count"] // 2) + (report_data.match_index // 2)

        if next_match_index < len(tournament["matches"]):
            next_match = tournament["matches"][next_match_index]
            if position_in_round % 2 == 0:
                next_match["player1"] = report_data.winner_player
            else:
                next_match["player2"] = report_data.winner_player

            # Unlock next match if both players are set
            if next_match["player1"] != "TBD" and next_match["player2"] != "TBD":
                next_match["status"] = "pending"

        new_content = json.dumps(tournament, indent=2)
        diff = compute_diff(old_content, new_content, f"tournaments/{report_data.tournament_id}.json")

        return {
            "target_file": f"state/scorekeeper/tournaments/{report_data.tournament_id}.json",
            "has_changes": has_changes(old_content, new_content),
            "diff": diff,
            "tournament": tournament
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tournaments/report/apply")
async def apply_tournament_report(request: Request, report_data: TournamentReport):
    """Apply tournament match winner report"""
    try:
        # Validate scope header
        require_scope(request, "state")

        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        tournament_file = get_tournament_file(drive_root, report_data.tournament_id)

        # Validate path is in sanctioned areas
        if not is_allowed_file(tournament_file, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(
                status_code=403,
                detail=f"File not in sanctioned areas: {tournament_file}"
            )

        if not tournament_file.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Tournament not found: {report_data.tournament_id}"
            )

        snapshot_path: Optional[Path] = None
        if getattr(request.app.state, "backup_on_write", True):
            snapshot_path = create_scorekeeper_snapshot(drive_root, reason="tournament_report")

        # Create backup
        file_backup_path = None
        if request.app.state.backup_on_write:
            file_backup_path = create_backup(tournament_file, drive_root)

        # Read current tournament
        def _do_read():
            with open(tournament_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        tournament = await asyncio.to_thread(_do_read)

        # Find and update match
        if report_data.match_index >= len(tournament["matches"]):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid match_index: {report_data.match_index}"
            )

        match = tournament["matches"][report_data.match_index]

        # Validate winner
        if report_data.winner_player not in [match["player1"], match["player2"]]:
            raise HTTPException(
                status_code=400,
                detail=f"Winner must be one of the match players: {match['player1']} or {match['player2']}"
            )

        # Update match
        match["winner"] = report_data.winner_player
        match["status"] = "completed"

        # Advance winner to next round
        current_round = match["round"]
        position_in_round = report_data.match_index % (2 ** (current_round - 1))
        next_match_index = (tournament["player_count"] // 2) + (report_data.match_index // 2)

        if next_match_index < len(tournament["matches"]):
            next_match = tournament["matches"][next_match_index]
            if position_in_round % 2 == 0:
                next_match["player1"] = report_data.winner_player
            else:
                next_match["player2"] = report_data.winner_player

            # Unlock next match if both players are set
            if next_match["player1"] != "TBD" and next_match["player2"] != "TBD":
                next_match["status"] = "pending"

        # Write updated tournament
        def _do_write():
            with open(tournament_file, 'w', encoding='utf-8') as f:
                json.dump(tournament, f, indent=2)
        await asyncio.to_thread(_do_write)

        # Log change
        log_scorekeeper_change(
            request, drive_root, "tournament_report",
            {
                "tournament_id": report_data.tournament_id,
                "match_index": report_data.match_index,
                "winner": report_data.winner_player,
                "file_backup_path": str(file_backup_path) if file_backup_path else None
            },
            snapshot_path
        )

        return {
            "status": "applied",
            "target_file": f"state/scorekeeper/tournaments/{report_data.tournament_id}.json",
            "backup_path": str(snapshot_path) if snapshot_path else None,
            "file_backup_path": str(file_backup_path) if file_backup_path else None,
            "tournament": tournament
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Advanced Tournament System ====================

import threading

# Initialize services (lazy loading with thread safety)
_tournament_service: Optional[TournamentService] = None
_tournament_config: Optional[TournamentConfig] = None
_service_lock = threading.Lock()
_config_lock = threading.Lock()


def get_tournament_service() -> TournamentService:
    """Get or create tournament service instance (thread-safe)."""
    global _tournament_service
    if _tournament_service is None:
        with _service_lock:
            if _tournament_service is None:  # Double-check pattern
                supabase = get_supabase_client()
                _tournament_service = TournamentService(supabase_client=supabase)
    return _tournament_service


def get_tournament_config() -> TournamentConfig:
    """Get or create tournament config instance (thread-safe)."""
    global _tournament_config
    if _tournament_config is None:
        with _config_lock:
            if _tournament_config is None:  # Double-check pattern
                supabase = get_supabase_client()
                _tournament_config = TournamentConfig(supabase_client=supabase)
    return _tournament_config


@router.post("/tournament/generate")
async def generate_tournament_stream(request: Request, tournament_req: TournamentGenerateRequest):
    """
    Generate tournament bracket with streaming progress updates.
    Returns Server-Sent Events (SSE) stream with progress messages.

    Supports:
    - Profile-aware seeding (random, elo, balanced_family, fair_play)
    - Kid Shield for family-friendly tournaments
    - Fairness scoring
    - Large tournament batching (64+ players)
    """
    try:
        service = get_tournament_service()
        config = get_tournament_config()

        # Create tournament data
        tournament_data = TournamentData(
            name=tournament_req.name,
            players=tournament_req.players,
            mode=tournament_req.mode,
            game_id=tournament_req.game_id,
            enable_kid_shield=tournament_req.enable_kid_shield,
            handicap_enabled=tournament_req.handicap_enabled
        )

        # Stream generator
        async def event_stream():
            """Generate SSE events from bracket generation."""
            bracket_data = None

            async for event in service.generate_bracket_stream(tournament_data):
                # Convert to SSE format
                event_type = event.get("type", "progress")
                message = event.get("message", "")
                progress = event.get("progress", 0)

                # Store bracket data when complete
                if event_type == "complete":
                    bracket_data = event.get("data")

                # Send SSE event
                yield f"data: {json.dumps(event)}\n\n"

            # Persist tournament to Supabase after generation
            if bracket_data:
                try:
                    from ..services.scorekeeper.service import TournamentBracket
                    bracket = TournamentBracket(**bracket_data)
                    await config.upsert_tournament(tournament_data, bracket)

                    yield f"data: {json.dumps({'type': 'persisted', 'message': 'Tournament saved', 'tournament_id': tournament_data.id})}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'message': f'Failed to persist: {str(e)}'})}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resume/{tournament_id}")
async def resume_tournament(request: Request, tournament_id: str):
    """
    Resume an existing tournament by merging saved state.
    Returns full tournament state with current bracket.
    """
    try:
        config = get_tournament_config()

        state = await config.resume_tournament(tournament_id)

        if not state:
            raise HTTPException(
                status_code=404,
                detail=f"Tournament {tournament_id} not found or inactive"
            )

        return {
            "tournament_id": state.tournament_id,
            "name": state.name,
            "mode": state.mode,
            "players": state.players,
            "bracket": state.bracket_data,
            "current_round": state.current_round,
            "completed_matches": state.completed_matches,
            "fairness_score": state.fairness_score,
            "created_at": state.created_at.isoformat(),
            "updated_at": state.updated_at.isoformat(),
            "active": state.active
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/submit")
async def submit_match_result(request: Request, match_data: MatchSubmitRequest):
    """
    Submit match result with concurrent submission locking.
    Ensures only one match update happens at a time per tournament.

    Features:
    - Tournament-level locking for concurrent safety
    - Automatic round completion detection
    - Telemetry logging (structlog JSONL)
    - Tournament completion detection
    """
    try:
        config = get_tournament_config()

        result = await config.submit_match(
            tournament_id=match_data.tournament_id,
            match_id=match_data.match_id,
            round_number=match_data.round_number,
            winner=match_data.winner,
            score1=match_data.score1,
            score2=match_data.score2
        )

        return {
            "status": "success",
            "match_id": result["match_id"],
            "winner": result["winner"],
            "completed": result["completed"],
            "round_complete": result.get("round_complete", False),
            "tournament_complete": result.get("tournament_complete", False)
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plugin/health")
async def check_plugin_health(request: Request, cached: bool = Query(True, description="Use cached status")):
    """
    Check LaunchBox plugin health via proxy.

    Args:
        cached: If True, return cached status. If False, fetch fresh status.

    Returns:
        Plugin health status with LaunchBox connection info
    """
    try:
        # TODO: Implement LaunchBox plugin health check via proxy
        # For now, return basic Supabase health
        config = get_tournament_config()
        health = await config.health_check()

        return {
            "plugin_status": "not_implemented",
            "message": "LaunchBox plugin health check pending implementation",
            "supabase": health,
            "cached": cached,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Health check failed: {str(e)}")


@router.get("/tournaments/active")
async def get_active_tournaments(request: Request, limit: int = Query(10, ge=1, le=50)):
    """
    Get active tournaments for resume/display.

    Args:
        limit: Max number of tournaments to return (1-50)
    """
    try:
        config = get_tournament_config()

        tournaments = await config.get_active_tournaments(limit=limit)

        return {
            "count": len(tournaments),
            "tournaments": [
                {
                    "tournament_id": t.tournament_id,
                    "name": t.name,
                    "mode": t.mode,
                    "players": len(t.players),
                    "current_round": t.current_round,
                    "completed_matches": len(t.completed_matches),
                    "fairness_score": t.fairness_score,
                    "updated_at": t.updated_at.isoformat()
                }
                for t in tournaments
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tournaments/{tournament_id}/archive")
async def archive_tournament_route(request: Request, tournament_id: str):
    """
    Archive completed tournament (set active=False).
    """
    try:
        config = get_tournament_config()

        success = await config.archive_tournament(tournament_id)

        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to archive tournament {tournament_id}"
            )

        return {
            "status": "archived",
            "tournament_id": tournament_id,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/highscores/{game_id}")
async def get_game_highscores(
    request: Request,
    game_id: str,
    limit: int = Query(10, ge=1, le=100, description="Max scores to return")
):
    """
    Get high scores for a specific game.

    Reads from the ScoreKeeper JSONL file (scores.jsonl) and
    optionally from Supabase cabinet_game_score.
    Falls back to MAME nvram hiscore if available.

    Args:
        game_id: Game ID or ROM name
        limit: Maximum number of scores to return (default 10, max 100)

    Returns:
        {
            "game_id": str,
            "game_title": str,
            "scores": [{"player": str, "score": int, "timestamp": str}],
            "total_count": int
        }
    """
    import os

    try:
        drive_root = Path(
            getattr(request.app.state, "drive_root", os.getenv("AA_DRIVE_ROOT", "A:\\"))
        )
        scores_file = get_scores_file(drive_root)

        game_scores = []
        game_title = game_id

        # Read from ScoreKeeper JSONL
        if scores_file.exists():
            try:
                with open(scores_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            # Match by game_id or game title
                            if (
                                entry.get('game_id') == game_id
                                or entry.get('game', '').lower() == game_id.lower()
                            ):
                                game_scores.append(entry)
                                # Use the most recent title seen
                                if entry.get('game_title') or entry.get('game'):
                                    game_title = entry.get('game_title') or entry.get('game')
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.warning("scores_file_read_error", error=str(e))

        # Sort scores descending by value
        sorted_scores = sorted(
            game_scores,
            key=lambda s: s.get('score', 0),
            reverse=True
        )[:limit]

        # Format response
        formatted_scores = [
            {
                "player": score.get('player', 'Anonymous'),
                "score": score.get('score', 0),
                "timestamp": score.get('timestamp', 'Unknown'),
                "rank": idx + 1
            }
            for idx, score in enumerate(sorted_scores)
        ]

        logger.info("highscores_retrieved",
                   game_id=game_id,
                   game_title=game_title,
                   count=len(formatted_scores))

        return {
            "game_id": game_id,
            "game_title": game_title,
            "scores": formatted_scores,
            "total_count": len(game_scores)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("highscores_error", game_id=game_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve high scores: {str(e)}")


class GameAutoSubmit(BaseModel):
    """Auto-submit score from game end event (Playnite / bus event)."""
    game_id: str
    game_title: str
    player: str
    score: int
    session_id: Optional[str] = None
    tournament_id: Optional[str] = None


# Keep /autosubmit path for backwards compatibility
@router.post("/autosubmit")
async def game_autosubmit(request: Request, submit_data: GameAutoSubmit):
    """
    Auto-submit score on game end (bus event integration).

    This endpoint is called automatically when a game ends (Playnite or bus event).
    Scores are submitted to both local JSONL
    and Supabase (if tournament active).

    Args:
        submit_data: Game end event data with score

    Returns:
        {
            "status": "submitted",
            "game_id": str,
            "player": str,
            "score": int,
            "leaderboard_rank": int | null,
            "tournament_match_updated": bool
        }
    """
    try:
        drive_root = Path(
            getattr(request.app.state, "drive_root", os.getenv("AA_DRIVE_ROOT", "A:\\"))
        )
        manifest = getattr(request.app.state, "manifest", {"sanctioned_paths": []})

        scores_file = get_scores_file(drive_root)
        if not is_allowed_file(
            scores_file, drive_root, manifest.get("sanctioned_paths", [])
        ):
            raise HTTPException(
                status_code=403,
                detail="Scores file is not in sanctioned paths"
            )

        scores_file.parent.mkdir(parents=True, exist_ok=True)

        runtime_state = {}
        try:
            runtime_state = load_runtime_state(drive_root)
        except Exception:
            runtime_state = {}
        is_fresh = _is_runtime_state_fresh(runtime_state)

        device_id = _resolve_device_id(request)
        frontend_source = _resolve_frontend_source(request, runtime_state, is_fresh)

        tracking_opted_in = _is_tracking_opted_in(drive_root)
        if not tracking_opted_in:
            logger.info(
                "autosubmit_identity_redacted_no_opt_in",
                game_id=submit_data.game_id,
                player=submit_data.player,
            )
        game_title = (
            submit_data.game_title
            or runtime_state.get("game_title")
            or "unknown"
        )
        game_id = submit_data.game_id or (
            runtime_state.get("game_id") if is_fresh else None
        )
        system_platform = (
            (runtime_state.get("system_id") or runtime_state.get("platform"))
            if is_fresh else None
        )

        player_user_id = None
        player_source = "guest"

        if tracking_opted_in:
            active_session = get_active_session()
            if active_session:
                player_user_id = active_session.get("player_id")
                if player_user_id:
                    player_source = "profile"

            primary_profile = None
            if not player_user_id:
                try:
                    primary_path = (
                        drive_root / ".aa" / "state" / "profile" / "primary_user.json"
                    )
                    if primary_path.exists():
                        with open(primary_path, "r", encoding="utf-8") as handle:
                            primary_profile = json.load(handle)
                except Exception:
                    primary_profile = None
                if isinstance(primary_profile, dict):
                    player_user_id = primary_profile.get("user_id")
                    if player_user_id:
                        player_source = "profile"
        score_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "device_id": device_id,
            "frontend_source": frontend_source,
            "game": game_title,
            "game_title": game_title,
            "game_id": game_id,
            "system": system_platform,
            "player": submit_data.player,
            "score": submit_data.score,
            "session_id": submit_data.session_id,
            "tournament_id": submit_data.tournament_id,
            "source": "game_autosubmit"
        }
        if player_user_id:
            score_entry["player_userId"] = player_user_id
        if player_source:
            score_entry["player_source"] = player_source

        with open(scores_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(score_entry) + "\n")

        # Mirror to Supabase (best-effort; non-blocking)
        try:
            if device_id and device_id != "unknown":
                await asyncio.to_thread(
                    sb_insert_score,
                    device_id,
                    game_id or submit_data.game_id or game_title,
                    submit_data.player,
                    submit_data.score,
                    {
                        'source': 'game_autosubmit',
                        'session_id': submit_data.session_id,
                        'tournament_id': submit_data.tournament_id,
                    }
                )
        except Exception:
            pass

        logger.info("game_autosubmit",
                   game_id=game_id or submit_data.game_id,
                   player=submit_data.player,
                   score=submit_data.score,
                   tournament_id=submit_data.tournament_id)

        # Broadcast to Gateway for real-time leaderboard push
        try:
            await asyncio.to_thread(_broadcast_score_update, game_title, score_entry, "game_autosubmit")
        except Exception:
            pass  # Best-effort; don't fail the request

        # Calculate leaderboard rank
        leaderboard_rank = None
        try:
            # Read all scores for this game
            all_scores = []
            if scores_file.exists():
                with open(scores_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            if game_id and entry.get("game_id") == game_id:
                                all_scores.append(entry)
                            elif not game_id and entry.get("game") == game_title:
                                all_scores.append(entry)
                        except json.JSONDecodeError:
                            continue

            # Sort and find rank
            all_scores.sort(key=lambda s: s.get('score', 0), reverse=True)
            for idx, s in enumerate(all_scores):
                if (
                    s.get("player") == submit_data.player
                    and s.get("score") == submit_data.score
                    and s.get("timestamp") == score_entry["timestamp"]
                ):
                    leaderboard_rank = idx + 1
                    break
        except Exception as e:
            logger.warning("leaderboard_rank_calculation_failed", error=str(e))

        # Update tournament match if tournament_id provided
        tournament_match_updated = False
        if submit_data.tournament_id:
            try:
                config = get_tournament_config()
                # Check if this score affects active tournament
                tournament = await config.resume_tournament(submit_data.tournament_id)
                if tournament and tournament.active:
                    # TODO: Implement automatic match result update
                    # This would require knowing which match the player is in
                    tournament_match_updated = False
                    logger.info("tournament_score_detected",
                               tournament_id=submit_data.tournament_id,
                               player=submit_data.player,
                               score=submit_data.score,
                               note="Manual match submission still required")
            except Exception as e:
                logger.error("tournament_update_failed",
                           tournament_id=submit_data.tournament_id,
                           error=str(e))

        log_scorekeeper_change(
            request,
            drive_root,
            "game_autosubmit",
            {
                "game": game_title,
                "game_id": game_id,
                "player": submit_data.player,
                "score": submit_data.score,
                "device_id": device_id,
                "frontend_source": frontend_source
            }
        )

        return {
            "status": "submitted",
            "game_id": game_id or submit_data.game_id,
            "player": submit_data.player,
            "score": submit_data.score,
            "leaderboard_rank": leaderboard_rank,
            "tournament_match_updated": tournament_match_updated,
            "timestamp": score_entry['timestamp']
        }

    except Exception as e:
        logger.error("autosubmit_failed",
                   game_id=submit_data.game_id,
                   error=str(e))
        raise HTTPException(status_code=500, detail=f"Auto-submit failed: {str(e)}")


# =============================================================================
# LEADERBOARD ENDPOINTS (Phase 3: House Honesty)
# =============================================================================

@router.get("/leaderboard/player/{player_id}/top-games")
async def get_player_top_games(
    player_id: str,
    limit: int = Query(10, ge=1, le=50),
    platform: Optional[str] = Query(None)
):
    """
    Get a player's most played games.
    
    Example: "Show me Dad's top 10 games"
    """
    service = get_leaderboard_service()
    if not service:
        raise HTTPException(status_code=500, detail="Leaderboard service not initialized")
    
    top_games = service.get_player_top_games(player_id, limit, platform)
    return {
        "player_id": player_id,
        "top_games": top_games,
        "count": len(top_games)
    }


@router.get("/leaderboard/game/{game_id}")
async def get_game_leaderboard_by_id(
    game_id: str,
    limit: int = Query(10, ge=1, le=50)
):
    """
    Get leaderboard for a specific game by ID.
    
    Example: "Who's #1 at Street Fighter?"
    """
    service = get_leaderboard_service()
    if not service:
        raise HTTPException(status_code=500, detail="Leaderboard service not initialized")
    
    leaderboard = service.get_game_leaderboard(game_id=game_id, limit=limit)
    return {
        "game_id": game_id,
        "leaderboard": leaderboard,
        "count": len(leaderboard)
    }


@router.get("/leaderboard/game")
async def get_game_leaderboard_by_title(
    title: str = Query(..., description="Game title to search for"),
    limit: int = Query(10, ge=1, le=50)
):
    """
    Get leaderboard for a specific game by title (fuzzy match).
    
    Example: "Who's #1 at Street Fighter?"
    """
    service = get_leaderboard_service()
    if not service:
        raise HTTPException(status_code=500, detail="Leaderboard service not initialized")
    
    leaderboard = service.get_game_leaderboard(game_title=title, limit=limit)
    return {
        "game_title": title,
        "leaderboard": leaderboard,
        "count": len(leaderboard)
    }


@router.get("/leaderboard/house")
async def get_house_stats():
    """
    Get overall house statistics.
    
    Returns:
    - Most played games
    - Most active players
    - Platform breakdown
    - Total stats
    """
    service = get_leaderboard_service()
    if not service:
        raise HTTPException(status_code=500, detail="Leaderboard service not initialized")
    
    return service.get_house_stats()


@router.get("/leaderboard/versus/{player1_id}/{player2_id}")
async def get_player_vs_player(
    player1_id: str,
    player2_id: str,
    game_id: Optional[str] = Query(None)
):
    """
    Compare two players' play history.
    
    Example: "Who plays more - Dad or Mom?"
    """
    service = get_leaderboard_service()
    if not service:
        raise HTTPException(status_code=500, detail="Leaderboard service not initialized")
    
    return service.get_player_vs_player(player1_id, player2_id, game_id)


# =============================================================================
# PLAYER TRACKING ENDPOINTS (Voice-based session management)
# =============================================================================

class LaunchStartEvent(BaseModel):
    """Game launch event for player tendency tracking."""
    game_id: str
    game_title: str
    platform: str
    genre: Optional[str] = None
    player: Optional[str] = None  # Override active player


class LaunchEndEvent(BaseModel):
    """Game completion event for player tendency tracking."""
    game_id: str
    duration_seconds: int
    score: Optional[int] = None



# NOTE: ScoreAttemptReviewRequest moved above review_score_attempt route (near line 1258)


class PlayerSessionRequest(BaseModel):
    """Request to start a player session."""
    player_name: str
    voice_id: Optional[str] = None
    player_id: Optional[str] = None
    players: Optional[List[Dict[str, Any]]] = None


@router.post("/events/launch-start")
async def track_launch_start(request: Request, event: LaunchStartEvent):
    """
    Track game launch for player tendencies.

    Called when a game is launched through LoRa or LaunchBox.
    Attributes the launch to the active player session.
    """
    try:
        drive_root = request.app.state.drive_root
        tracking_opted_in = _is_tracking_opted_in(drive_root)
        player_name = event.player or get_active_player()
        panel = (request.headers.get("x-panel") or "launchbox").strip().lower()

        if tracking_opted_in:
            service = PlayerTendencyService(drive_root)
            service.track_launch(
                player_name=player_name,
                game_id=event.game_id,
                game_title=event.game_title,
                platform=event.platform,
                genre=event.genre
            )

            if get_active_session():
                extend_session()

            logger.info(
                "launch_tracked",
                player=player_name,
                game_id=event.game_id,
                game_title=event.game_title
            )
        else:
            logger.info(
                "launch_tracking_skipped_no_opt_in",
                player=player_name,
                game_id=event.game_id,
                game_title=event.game_title
            )

        try:
            tracking_service = get_score_tracking_service(drive_root)
            tracking_service.record_launch(
                CanonicalGameEvent(
                    source=panel,
                    game_id=event.game_id,
                    title=event.game_title,
                    platform=event.platform,
                    player=player_name if tracking_opted_in else None,
                    launch_method="frontend_event",
                    metadata={"genre": event.genre},
                )
            )
        except Exception as tracking_error:
            logger.warning("score_tracking_launch_record_failed", error=str(tracking_error), game_id=event.game_id)

        try:
            frontend = "retrofe" if panel == "retrofe" else "launchbox"
            update_runtime_state({
                "frontend": frontend,
                "mode": "in_game",
                "system_id": event.platform or None,
                "game_title": event.game_title,
                "game_id": event.game_id,
                "player": player_name if tracking_opted_in else None,
                "elapsed_seconds": None,
            }, drive_root)
        except Exception:
            pass

        response = {
            "status": "tracked" if tracking_opted_in else "skipped",
            "player": player_name,
            "game_id": event.game_id,
        }
        if not tracking_opted_in:
            response["reason"] = "tracking_not_opted_in"
        return response

    except Exception as e:
        logger.error("launch_track_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/events/launch-end")
async def track_launch_end(request: Request, event: LaunchEndEvent):
    """
    Track game completion for player tendencies.

    Called when a game exits. Updates play duration in tendency file.
    """
    try:
        drive_root = request.app.state.drive_root
        tracking_opted_in = _is_tracking_opted_in(drive_root)
        player_name = get_active_player()

        if tracking_opted_in:
            service = PlayerTendencyService(drive_root)
            service.track_completion(
                player_name=player_name,
                game_id=event.game_id,
                duration_seconds=event.duration_seconds,
                score=event.score
            )

            logger.info(
                "completion_tracked",
                player=player_name,
                game_id=event.game_id,
                duration=event.duration_seconds
            )
        else:
            logger.info(
                "completion_tracking_skipped_no_opt_in",
                player=player_name,
                game_id=event.game_id,
                duration=event.duration_seconds
            )

        try:
            tracking_service = get_score_tracking_service(drive_root)
            session = tracking_service.close_session(game_id=event.game_id)
            if event.score is not None:
                tracking_service.record_manual_submission(
                    game_id=session.get("game_id") or event.game_id,
                    game_title=session.get("title") or event.game_id,
                    platform=session.get("platform"),
                    player=player_name,
                    score=int(event.score),
                    metadata={
                        "duration_seconds": event.duration_seconds,
                        "submission_source": "launch_end_event",
                    },
                )
        except Exception as tracking_error:
            logger.warning("score_tracking_launch_end_failed", error=str(tracking_error), game_id=event.game_id)

        # Update runtime state to idle
        try:
            update_runtime_state({
                "mode": "idle",
                "game_title": None,
                "game_id": None,
                "system_id": None,
                "player": None,
                "elapsed_seconds": None,
            }, drive_root)
        except Exception:
            pass

        response = {
            "status": "tracked" if tracking_opted_in else "skipped",
            "player": player_name,
            "game_id": event.game_id,
            "duration_seconds": event.duration_seconds
        }
        if not tracking_opted_in:
            response["reason"] = "tracking_not_opted_in"
        return response

    except Exception as e:
        logger.error("completion_track_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/session/start")
async def start_player_session(request: Request, session_req: PlayerSessionRequest):
    """
    Start a new player session.
    
    Called by Vicky when a player is identified by voice.
    All subsequent game launches will be attributed to this player.
    """
    try:
        session = set_active_player(
            player_name=session_req.player_name,
            voice_id=session_req.voice_id,
            player_id=session_req.player_id,
            players=session_req.players
        )
        
        logger.info(
            "session_started",
            player=session_req.player_name,
            expires_at=session["expires_at"]
        )
        
        return {
            "status": "session_started",
            "player": session["player_name"],
            "player_id": session.get("player_id"),
            "players": session.get("players") or [],
            "expires_at": session["expires_at"]
        }
    
    except Exception as e:
        logger.error("session_start_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/end")
async def end_player_session(request: Request):
    """
    End the current player session.
    
    Called when player explicitly logs out or session expires.
    """
    try:
        session = get_active_session()
        if not session:
            return {"status": "no_active_session"}
        
        player_name = session["player_name"]
        end_session()
        
        logger.info("session_ended", player=player_name)
        
        return {
            "status": "session_ended",
            "player": player_name
        }
    
    except Exception as e:
        logger.error("session_end_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/current")
async def get_current_session(request: Request):
    """
    Get the current active player session.
    
    Returns session info or null if no active session.
    """
    try:
        session = get_active_session()
        
        if not session:
            return {
                "active": False,
                "player": "Guest"
            }
        
        return {
            "active": True,
            "player": session["player_name"],
            "player_id": session.get("player_id"),
            "players": session.get("players") or [],
            "started_at": session["started_at"],
            "expires_at": session["expires_at"],
            "games_launched": session.get("games_launched", 0)
        }
    
    except Exception as e:
        logger.error("session_get_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tendencies/{player_name}")
async def get_player_tendencies(request: Request, player_name: str):
    """
    Get a player's tendency file.
    
    Returns play history, favorite genres/platforms, and recommendations.
    """
    try:
        drive_root = request.app.state.drive_root
        service = PlayerTendencyService(drive_root)
        
        tendencies = service.load_tendencies(player_name)
        
        return tendencies
    
    except Exception as e:
        logger.error("tendencies_load_failed", player=player_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tendencies/current")
async def get_current_player_tendencies(request: Request):
    """
    Get the current active player's tendencies.
    
    Convenience endpoint for frontend to fetch active player's data.
    """
    try:
        player_name = get_active_player()
        drive_root = request.app.state.drive_root
        service = PlayerTendencyService(drive_root)
        
        tendencies = service.load_tendencies(player_name)
        
        return {
            "player": player_name,
            "tendencies": tendencies
        }
    
    except Exception as e:
        logger.error("current_tendencies_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# SAM ENHANCED FEATURES (Phase 4)
# ========================================
# Profile-to-Initials Mapping
# Hidden/Moderated Scores
# Household Player Registry

# Pydantic models for Sam enhanced features
class InitialsMappingCreate(BaseModel):
    """Request to create an initials mapping."""
    initials: str = Field(..., min_length=1, max_length=3)
    profile_id: str
    profile_name: str
    game_ids: Optional[List[str]] = None
    created_by: Optional[str] = None


class HideScoreRequest(BaseModel):
    """Request to hide a score."""
    score_id: str
    reason: str = "manual"
    hidden_by: Optional[str] = None
    note: Optional[str] = None


class HouseholdCreate(BaseModel):
    """Request to create a household."""
    name: str
    cabinet_id: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class HouseholdMemberAdd(BaseModel):
    """Request to add a member to a household."""
    profile_id: str
    profile_name: str
    role: str = "member"
    invited_by: Optional[str] = None


# ===== Initials Mapping Endpoints =====

@router.get("/sam/initials")
async def list_initials_mappings(
    request: Request,
    profile_id: Optional[str] = Query(None, description="Filter by profile ID")
):
    """
    List all initials-to-profile mappings.
    
    Optionally filter by profile_id to get all initials for one player.
    """
    try:
        from ..services.scorekeeper.sam_enhanced import InitialsMappingService
        
        drive_root = request.app.state.drive_root
        service = InitialsMappingService(drive_root)
        
        mappings = service.list_mappings(profile_id=profile_id)
        
        return {
            "status": "ok",
            "count": len(mappings),
            "mappings": [m.dict() for m in mappings]
        }
    except Exception as e:
        logger.error("list_initials_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sam/initials")
async def create_initials_mapping(request: Request, payload: InitialsMappingCreate):
    """
    Create a new initials-to-profile mapping.
    
    Links arcade initials (e.g., "DAD") to a player profile so Sam
    can recognize the same player across different games.
    """
    try:
        from ..services.scorekeeper.sam_enhanced import InitialsMappingService
        
        drive_root = request.app.state.drive_root
        service = InitialsMappingService(drive_root)
        
        mapping = service.create_mapping(
            initials=payload.initials,
            profile_id=payload.profile_id,
            profile_name=payload.profile_name,
            game_ids=payload.game_ids,
            created_by=payload.created_by,
        )
        
        log_scorekeeper_change(
            request,
            drive_root,
            "create_initials_mapping",
            {"initials": mapping.initials, "profile_name": mapping.profile_name}
        )
        
        return {
            "status": "created",
            "mapping": mapping.dict()
        }
    except Exception as e:
        logger.error("create_initials_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sam/initials/resolve/{initials}")
async def resolve_initials(
    request: Request,
    initials: str,
    game_id: Optional[str] = Query(None, description="Optional game ID for context")
):
    """
    Resolve arcade initials to a player profile.
    
    Returns the linked profile if found, or None if the initials
    are not mapped to any profile.
    """
    try:
        from ..services.scorekeeper.sam_enhanced import InitialsMappingService
        
        drive_root = request.app.state.drive_root
        service = InitialsMappingService(drive_root)
        
        mapping = service.resolve_initials(initials, game_id=game_id)
        
        if mapping:
            return {
                "status": "found",
                "initials": initials,
                "profile_id": mapping.profile_id,
                "profile_name": mapping.profile_name,
                "mapping": mapping.dict()
            }
        
        return {
            "status": "not_found",
            "initials": initials,
            "profile_id": None,
            "profile_name": None
        }
    except Exception as e:
        logger.error("resolve_initials_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sam/initials/{mapping_id}")
async def delete_initials_mapping(request: Request, mapping_id: str):
    """Delete an initials mapping."""
    try:
        from ..services.scorekeeper.sam_enhanced import InitialsMappingService
        
        drive_root = request.app.state.drive_root
        service = InitialsMappingService(drive_root)
        
        deleted = service.delete_mapping(mapping_id)
        
        if deleted:
            log_scorekeeper_change(
                request,
                drive_root,
                "delete_initials_mapping",
                {"mapping_id": mapping_id}
            )
            return {"status": "deleted", "mapping_id": mapping_id}
        
        raise HTTPException(status_code=404, detail="Mapping not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_initials_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ===== Hidden Scores Endpoints =====

@router.get("/sam/hidden-scores")
async def list_hidden_scores(request: Request):
    """
    List all hidden/moderated scores.
    
    Returns scores that have been excluded from the public leaderboard.
    """
    try:
        from ..services.scorekeeper.sam_enhanced import HiddenScoresService
        
        drive_root = request.app.state.drive_root
        service = HiddenScoresService(drive_root)
        
        hidden = service.list_hidden()
        
        return {
            "status": "ok",
            "count": len(hidden),
            "hidden_scores": [h.dict() for h in hidden]
        }
    except Exception as e:
        logger.error("list_hidden_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sam/hidden-scores")
async def hide_score(request: Request, payload: HideScoreRequest):
    """
    Hide a score from the public leaderboard.
    
    The score is not deleted, just marked as hidden with a reason.
    """
    try:
        from ..services.scorekeeper.sam_enhanced import HiddenScoresService
        
        drive_root = request.app.state.drive_root
        service = HiddenScoresService(drive_root)
        
        hidden = service.hide_score(
            score_id=payload.score_id,
            reason=payload.reason,
            hidden_by=payload.hidden_by,
            note=payload.note,
        )
        
        log_scorekeeper_change(
            request,
            drive_root,
            "hide_score",
            {"score_id": payload.score_id, "reason": payload.reason}
        )
        
        return {
            "status": "hidden",
            "hidden_score": hidden.dict()
        }
    except Exception as e:
        logger.error("hide_score_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sam/hidden-scores/{score_id}")
async def unhide_score(request: Request, score_id: str):
    """Unhide a previously hidden score."""
    try:
        from ..services.scorekeeper.sam_enhanced import HiddenScoresService
        
        drive_root = request.app.state.drive_root
        service = HiddenScoresService(drive_root)
        
        unhidden = service.unhide_score(score_id)
        
        if unhidden:
            log_scorekeeper_change(
                request,
                drive_root,
                "unhide_score",
                {"score_id": score_id}
            )
            return {"status": "unhidden", "score_id": score_id}
        
        raise HTTPException(status_code=404, detail="Hidden score not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("unhide_score_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ===== Household Endpoints =====

@router.get("/sam/households")
async def list_households(request: Request):
    """List all households."""
    try:
        from ..services.scorekeeper.sam_enhanced import load_sam_state
        
        drive_root = request.app.state.drive_root
        state = load_sam_state(drive_root)
        
        households = [h.dict() for h in state.households.values()]
        
        return {
            "status": "ok",
            "count": len(households),
            "households": households
        }
    except Exception as e:
        logger.error("list_households_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sam/households")
async def create_household(request: Request, payload: HouseholdCreate):
    """Create a new household."""
    try:
        from ..services.scorekeeper.sam_enhanced import HouseholdService
        
        drive_root = request.app.state.drive_root
        service = HouseholdService(drive_root)
        
        household = service.create_household(
            name=payload.name,
            cabinet_id=payload.cabinet_id,
            settings=payload.settings,
        )
        
        log_scorekeeper_change(
            request,
            drive_root,
            "create_household",
            {"name": payload.name, "household_id": household.id}
        )
        
        return {
            "status": "created",
            "household": household.dict()
        }
    except Exception as e:
        logger.error("create_household_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sam/households/{household_id}")
async def get_household(request: Request, household_id: str):
    """Get a household by ID."""
    try:
        from ..services.scorekeeper.sam_enhanced import HouseholdService
        
        drive_root = request.app.state.drive_root
        service = HouseholdService(drive_root)
        
        household = service.get_household(household_id)
        
        if not household:
            raise HTTPException(status_code=404, detail="Household not found")
        
        return {
            "status": "ok",
            "household": household.dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_household_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sam/households/{household_id}/members")
async def list_household_members(request: Request, household_id: str):
    """List all members of a household."""
    try:
        from ..services.scorekeeper.sam_enhanced import HouseholdService
        
        drive_root = request.app.state.drive_root
        service = HouseholdService(drive_root)
        
        members = service.list_members(household_id)
        
        return {
            "status": "ok",
            "household_id": household_id,
            "count": len(members),
            "members": [m.dict() for m in members]
        }
    except Exception as e:
        logger.error("list_members_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sam/households/{household_id}/members")
async def add_household_member(
    request: Request,
    household_id: str,
    payload: HouseholdMemberAdd
):
    """Add a member to a household."""
    try:
        from ..services.scorekeeper.sam_enhanced import HouseholdService
        
        drive_root = request.app.state.drive_root
        service = HouseholdService(drive_root)
        
        member = service.add_member(
            household_id=household_id,
            profile_id=payload.profile_id,
            profile_name=payload.profile_name,
            role=payload.role,
            invited_by=payload.invited_by,
        )
        
        if not member:
            raise HTTPException(status_code=404, detail="Household not found")
        
        log_scorekeeper_change(
            request,
            drive_root,
            "add_household_member",
            {"household_id": household_id, "profile_name": payload.profile_name}
        )
        
        return {
            "status": "added",
            "member": member.dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("add_member_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sam/households/{household_id}/members/{profile_id}")
async def remove_household_member(
    request: Request,
    household_id: str,
    profile_id: str
):
    """Remove a member from a household."""
    try:
        from ..services.scorekeeper.sam_enhanced import HouseholdService
        
        drive_root = request.app.state.drive_root
        service = HouseholdService(drive_root)
        
        removed = service.remove_member(household_id, profile_id)
        
        if removed:
            log_scorekeeper_change(
                request,
                drive_root,
                "remove_household_member",
                {"household_id": household_id, "profile_id": profile_id}
            )
            return {"status": "removed", "profile_id": profile_id}
        
        raise HTTPException(status_code=404, detail="Member not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("remove_member_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ===== Sam Stats Endpoint =====

@router.get("/sam/stats")
async def get_sam_stats(request: Request):
    """
    Get Sam enhanced features statistics.
    
    Returns counts of households, members, initials mappings, and hidden scores.
    """
    try:
        from ..services.scorekeeper.sam_enhanced import SamEnhancedService
        
        drive_root = request.app.state.drive_root
        service = SamEnhancedService(drive_root)
        
        return {
            "status": "ok",
            **service.get_stats()
        }
    except Exception as e:
        logger.error("sam_stats_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Tournament Champions & Top Dog ====================

@router.get("/champions")
async def get_tournament_champions(
    request: Request,
    limit: int = Query(20, description="Number of champions to return")
):
    """
    Get tournament champions - players ranked by tournament wins.
    
    This is the "Top Dog" leaderboard showing who has won the most tournaments.
    
    Returns:
        List of players with their tournament win counts, sorted by wins.
    """
    try:
        drive_root = request.app.state.drive_root
        tournaments_dir = get_scorekeeper_dir(drive_root) / "tournaments"
        
        if not tournaments_dir.exists():
            return {
                "champions": [],
                "total_tournaments": 0,
                "message": "No tournaments found"
            }
        
        # Scan all tournament files
        champion_counts = {}
        champion_details = {}
        total_tournaments = 0
        completed_tournaments = 0
        
        for tournament_file in tournaments_dir.glob("*.json"):
            try:
                with open(tournament_file, 'r', encoding='utf-8') as f:
                    tournament = json.load(f)
                
                total_tournaments += 1
                
                # Find the final match (last match in the bracket)
                matches = tournament.get("matches", [])
                if not matches:
                    continue
                
                # The final match is typically the last one with a winner
                final_match = None
                for match in reversed(matches):
                    if match.get("winner") and match.get("status") == "completed":
                        # Check if this is the final (highest round)
                        if final_match is None or match.get("round", 0) > final_match.get("round", 0):
                            final_match = match
                
                # Check if tournament is complete (final match has winner)
                if final_match and final_match.get("winner"):
                    completed_tournaments += 1
                    champion = final_match["winner"]
                    
                    if champion not in champion_counts:
                        champion_counts[champion] = 0
                        champion_details[champion] = {
                            "player": champion,
                            "wins": 0,
                            "tournaments_won": [],
                            "games": set()
                        }
                    
                    champion_counts[champion] += 1
                    champion_details[champion]["wins"] += 1
                    champion_details[champion]["tournaments_won"].append({
                        "tournament_id": tournament.get("id", tournament_file.stem),
                        "tournament_name": tournament.get("name", "Unknown"),
                        "game": tournament.get("game", "Unknown"),
                        "date": tournament.get("created_at", "Unknown")
                    })
                    if tournament.get("game"):
                        champion_details[champion]["games"].add(tournament.get("game"))
                        
            except Exception as e:
                logger.warning("tournament_parse_error", file=str(tournament_file), error=str(e))
                continue
        
        # Sort by wins and build result
        sorted_champions = sorted(
            champion_details.values(),
            key=lambda x: x["wins"],
            reverse=True
        )[:limit]
        
        # Convert sets to lists for JSON serialization
        for champ in sorted_champions:
            champ["games"] = list(champ["games"])
            champ["rank"] = sorted_champions.index(champ) + 1
        
        # Determine top dog
        top_dog = sorted_champions[0]["player"] if sorted_champions else None
        
        return {
            "top_dog": top_dog,
            "champions": sorted_champions,
            "total_tournaments": total_tournaments,
            "completed_tournaments": completed_tournaments,
            "last_updated": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error("get_champions_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/champions/{player_name}")
async def get_player_championship_history(
    request: Request,
    player_name: str
):
    """
    Get a specific player's tournament championship history.
    
    Shows all tournaments they've won and their overall ranking.
    """
    try:
        drive_root = request.app.state.drive_root
        tournaments_dir = get_scorekeeper_dir(drive_root) / "tournaments"
        
        if not tournaments_dir.exists():
            raise HTTPException(status_code=404, detail="No tournaments found")
        
        player_lower = player_name.lower()
        tournaments_won = []
        tournaments_participated = []
        total_matches_won = 0
        total_matches_played = 0
        
        for tournament_file in tournaments_dir.glob("*.json"):
            try:
                with open(tournament_file, 'r', encoding='utf-8') as f:
                    tournament = json.load(f)
                
                # Check if player participated
                players = tournament.get("players", [])
                player_in_tournament = any(p.lower() == player_lower for p in players)
                
                if not player_in_tournament:
                    continue
                
                tournaments_participated.append({
                    "tournament_id": tournament.get("id", tournament_file.stem),
                    "tournament_name": tournament.get("name", "Unknown"),
                    "game": tournament.get("game", "Unknown")
                })
                
                # Count matches
                for match in tournament.get("matches", []):
                    p1 = (match.get("player1") or "").lower()
                    p2 = (match.get("player2") or "").lower()
                    winner = (match.get("winner") or "").lower()
                    
                    if p1 == player_lower or p2 == player_lower:
                        total_matches_played += 1
                        if winner == player_lower:
                            total_matches_won += 1
                
                # Check if they won the tournament
                matches = tournament.get("matches", [])
                final_match = None
                for match in reversed(matches):
                    if match.get("winner") and match.get("status") == "completed":
                        if final_match is None or match.get("round", 0) > final_match.get("round", 0):
                            final_match = match
                
                if final_match and final_match.get("winner", "").lower() == player_lower:
                    tournaments_won.append({
                        "tournament_id": tournament.get("id", tournament_file.stem),
                        "tournament_name": tournament.get("name", "Unknown"),
                        "game": tournament.get("game", "Unknown"),
                        "date": tournament.get("created_at", "Unknown"),
                        "player_count": tournament.get("player_count", len(players))
                    })
                    
            except Exception:
                continue
        
        if not tournaments_participated:
            raise HTTPException(status_code=404, detail=f"Player '{player_name}' not found in any tournaments")
        
        win_rate = (total_matches_won / total_matches_played * 100) if total_matches_played > 0 else 0
        
        return {
            "player": player_name,
            "tournament_wins": len(tournaments_won),
            "tournaments_participated": len(tournaments_participated),
            "match_wins": total_matches_won,
            "matches_played": total_matches_played,
            "win_rate": round(win_rate, 1),
            "championships": tournaments_won,
            "all_tournaments": tournaments_participated
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_player_history_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/highscores/legacy/{game}")
async def get_game_highscores_legacy(
    request: Request,
    game: str,
    limit: int = Query(10, description="Number of scores to return")
):
    """
    Get high score leaderboard for a specific game.
    
    Returns actual game scores (not play counts), sorted highest to lowest.
    """
    try:
        drive_root = request.app.state.drive_root
        scores_file = get_scores_file(drive_root)
        
        def _do_read():
            if not scores_file.exists():
                return {
                    "game": game,
                    "highscores": [],
                    "total_scores": 0
                }

            # Load all scores for this game
            game_lower = game.lower()
            scores_list = []

            with open(scores_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("game", "").lower() == game_lower:
                            scores_list.append(entry)
                    except json.JSONDecodeError:
                        continue
            return scores_list

        scores_result = await asyncio.to_thread(_do_read)
        if isinstance(scores_result, dict):
            return scores_result
        scores = scores_result
        
        # Sort by score descending
        scores.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        # Add rank and limit
        highscores = []
        for i, score in enumerate(scores[:limit]):
            highscores.append({
                "rank": i + 1,
                "player": score.get("player", "???"),
                "score": score.get("score", 0),
                "timestamp": score.get("timestamp", "Unknown"),
                "player_userId": score.get("player_userId")
            })
        
        return {
            "game": game,
            "highscores": highscores,
            "total_scores": len(scores),
            "top_player": highscores[0]["player"] if highscores else None
        }
        
    except Exception as e:
        logger.error("get_highscores_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/topdog")
async def get_top_dog(request: Request):
    """
    Get the current "Top Dog" - the player with the most tournament wins.
    
    Quick endpoint for Sam to answer "Who's the top dog in the house?"
    """
    try:
        # Reuse champions endpoint logic
        result = await get_tournament_champions(request, limit=1)
        
        if not result.get("top_dog"):
            return {
                "top_dog": None,
                "message": "No tournaments completed yet. Play some tournaments to crown a Top Dog!",
                "total_tournaments": result.get("total_tournaments", 0)
            }
        
        champion = result["champions"][0] if result.get("champions") else {}
        
        return {
            "top_dog": result["top_dog"],
            "tournament_wins": champion.get("wins", 0),
            "games_dominated": champion.get("games", []),
            "message": f"{result['top_dog']} is the Top Dog with {champion.get('wins', 0)} tournament wins!",
            "total_tournaments": result.get("completed_tournaments", 0)
        }
        
    except Exception as e:
        logger.error("get_topdog_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# MAME HISCORE SYNC ENDPOINTS
# ========================================
# Parse MAME .hi files and ingest scores into ScoreKeeper

@router.post("/mame/sync")
async def sync_mame_hiscores(request: Request):
    """
    Sync MAME high scores from .hi files into ScoreKeeper.
    
    Parses MAME hiscore files, resolves ROM names to LaunchBox game IDs,
    and writes scores to scores.jsonl + Supabase.
    
    Returns:
        {
            "synced": int,  # Number of new scores added
            "games": list,  # Games processed
            "errors": list  # Any parsing errors
        }
    """
    try:
        from ..services.hiscore_watcher import get_watcher
        from ..services.mame_hiscore_parser import get_all_mame_scores

        drive_root = Path(
            getattr(request.app.state, "drive_root", os.getenv("AA_DRIVE_ROOT", "A:\\"))
        )
        watcher = get_watcher(str(drive_root))

        sync_result = watcher.sync_all()
        games_processed = []
        synced_count = 0
        errors = []

        if isinstance(sync_result, dict) and sync_result:
            rom_mapping = watcher.get_rom_mapping()
            for rom, entries in sync_result.items():
                if not isinstance(entries, list):
                    continue
                lb_info = rom_mapping.get(str(rom).lower(), {})
                game_id = lb_info.get("game_id") or f"mame_{rom}"
                game_title = lb_info.get("game_title") or str(rom).upper()
                games_processed.append({
                    "rom": rom,
                    "title": game_title,
                    "game_id": game_id,
                    "scores": len(entries)
                })
                synced_count += len(entries)

            try:
                await regenerate_high_scores_index(drive_root)
            except Exception:
                pass

            logger.info(
                "mame_hiscore_sync_complete",
                synced=synced_count,
                games=len(games_processed)
            )

            return {
                "synced": synced_count,
                "games": games_processed,
                "errors": errors if errors else None,
                "source": "hi2txt"
            }

        status = watcher.get_status()
        if status.get("games_tracked"):
            errors.append("hi2txt produced no entries; falling back to legacy parser")

        legacy_scores = get_all_mame_scores()
        if not legacy_scores:
            return {
                "synced": 0,
                "games": [],
                "errors": errors or ["No MAME hiscore files found or parseable"],
                "hiscore_dirs": status.get("dirs_watched", [])
            }

        fallback_scores = {}
        for game_rom, game_data in legacy_scores.items():
            if game_data.parse_error:
                errors.append(f"{game_rom}: {game_data.parse_error}")
                continue
            if not game_data.entries:
                continue
            entries = []
            for entry in game_data.entries:
                entries.append({
                    "rank": entry.rank,
                    "score": entry.score,
                    "name": entry.initials or "???",
                    "rom": game_rom,
                    "game_name": game_rom,
                    "timestamp": datetime.now().isoformat(),
                    "source": "mame_hiscore"
                })
            fallback_scores[game_rom] = entries

        if fallback_scores:
            watcher.save_scores(fallback_scores)
            try:
                await regenerate_high_scores_index(drive_root)
            except Exception:
                pass

        for rom, entries in fallback_scores.items():
            games_processed.append({
                "rom": rom,
                "title": rom.upper(),
                "game_id": f"mame_{rom}",
                "scores": len(entries)
            })
            synced_count += len(entries)

        logger.info(
            "mame_hiscore_sync_complete",
            synced=synced_count,
            games=len(games_processed),
            source="legacy_parser"
        )

        return {
            "synced": synced_count,
            "games": games_processed,
            "errors": errors if errors else None,
            "source": "legacy_parser"
        }

    except Exception as e:
        logger.error("mame_sync_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mame/status")
async def get_mame_sync_status(request: Request):
    """
    Get MAME hiscore sync status and available games.
    
    Returns info about which MAME games have parseable hiscores.
    """
    try:
        from ..services.hiscore_watcher import get_watcher

        watcher = get_watcher(str(getattr(request.app.state, "drive_root", "A:\\")))
        status = watcher.get_status()
        scores = watcher.get_scores_snapshot()

        games = []
        total_scores = 0

        for game_rom, entries in scores.items():
            if not isinstance(entries, list):
                continue
            top_entry = None
            if entries:
                top_entry = max(entries, key=lambda e: e.get("score", 0))
            games.append({
                "rom": game_rom,
                "score_count": len(entries),
                "top_score": top_entry.get("score") if top_entry else None,
                "top_player": top_entry.get("name") if top_entry else None,
                "parse_error": None
            })
            total_scores += len(entries)

        tracked_roms = status.get("games_tracked", [])
        unparsed = [rom for rom in tracked_roms if rom not in scores]

        return {
            "hiscore_dirs": status.get("dirs_watched", []),
            "hi2txt_path": str(watcher.hi2txt_path),
            "hi2txt_exists": watcher.hi2txt_path.exists(),
            "parsed_games": len(games),
            "total_scores": total_scores,
            "games": games,
            "unparsed_roms": unparsed,
            "poll_interval": status.get("poll_interval"),
            "output_file": status.get("output_file")
        }

    except Exception as e:
        logger.error("mame_status_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))








