"""
LaunchBox Integration Router - UPDATED 2025-10-06
Handles game library management, launching, and metadata queries.

@router: launchbox
@role: Game library integration with LaunchBox XML parsing
@owner: LoRa
@linked: frontend/src/panels/launchbox/LaunchBoxPanel.jsx
@status: active (refactored to use new services)

CHANGES:
- Uses backend/constants/a_drive_paths.py for path management
- Uses backend/services/launchbox_parser.py for XML parsing
- Uses backend/services/launcher.py for game launching
- Parses platform XMLs (not missing master XML)
- Implements launcher fallback chain (no CLI_Launcher dependency)
"""

from typing import List, Optional, Dict, Any, Tuple, Literal
from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    Depends,
    Body,
    Header,
)
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
import logging
import os
import time
import json
from datetime import datetime, timezone, timedelta
import math
import asyncio
import random
import shlex
import subprocess
from pathlib import Path
from functools import wraps
from difflib import SequenceMatcher
import re

from backend.models.game import Game, LaunchRequest, LaunchResponse, GameCacheStats
from backend.services.launchbox_parser import parser, get_platform_games
from backend.services import launchbox_cache as lb_cache
from backend.services.launchbox_json_cache import json_cache
from backend.services.platform_names import normalize_platform
from backend.routers import marquee as marquee_router
from backend.services.launcher import launcher
from backend.services.launcher import GameLauncher
from backend.services.adapters.adapter_utils import dry_run_enabled
from backend.services.launchbox_plugin_client import (
    get_plugin_client,
    LaunchBoxPluginError,
)
from backend.services.image_scanner import scanner as image_scanner
from backend.services.backup import create_backup
from backend.services.policies import require_scope, is_allowed_file
from backend.services.led_game_profiles import LEDGameProfileStore
from backend.services.led_mapping_service import LEDMappingService
from backend.constants.paths import Paths
from backend.services.runtime_state import update_runtime_state
import requests
from pydantic import BaseModel, Field
import shutil
from starlette.datastructures import MutableHeaders

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/launchbox", tags=["launchbox"])


# =============================================================================
# PERFORMANCE OPTIMIZATION: Timeout Wrappers
# =============================================================================


def with_timeout(timeout_seconds: float = 10.0):
    """Decorator to add timeout protection to async endpoint handlers.

    Prevents long-running operations from blocking the event loop.
    Particularly important for XML parsing and plugin calls.

    Args:
        timeout_seconds: Maximum execution time before TimeoutError

    Usage:
        @router.get("/games")
        @with_timeout(5.0)
        async def get_games(...):
            ...
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                logger.error(
                    f"{func.__name__} exceeded timeout ({timeout_seconds}s) - "
                    "check XML cache, plugin connection, or threadpool contention"
                )
                raise HTTPException(
                    status_code=504,
                    detail=f"Operation timeout after {timeout_seconds}s. "
                    "This may indicate XML parsing delay or plugin unavailability.",
                )

        return wrapper

    return decorator


# =============================================================================
# DEPENDENCY INJECTION: Service Providers
# =============================================================================


class LaunchBoxServices:
    """Injectable service container for LaunchBox operations.

    Provides centralized access to parser, cache, launcher, and plugin client.
    Enables mocking in tests via FastAPI Depends override.
    """

    def __init__(self):
        self.parser = parser
        self.cache = lb_cache
        self.launcher = launcher
        self.plugin_client = get_plugin_client()
        self.image_scanner = image_scanner

    def invalidate_caches(self) -> None:
        """Invalidate all caches for fresh data."""
        # Parser cache is managed internally
        logger.info("LaunchBox service caches invalidated")


def get_launchbox_services() -> LaunchBoxServices:
    """FastAPI dependency for LaunchBox services (injectable for tests).

    Usage:
        @router.get("/games")
        async def get_games(services: LaunchBoxServices = Depends(get_launchbox_services)):
            games = await run_in_threadpool(services.cache.get_games)
            ...
    """
    return LaunchBoxServices()


# =============================================================================
# MODELS & HELPERS
# =============================================================================


class ShaderChangeRequest(BaseModel):
    """Request to change shader for a specific game."""
    game_id: str
    shader_name: str
    emulator: Literal["mame", "retroarch"]
    parameters: Optional[Dict[str, Any]] = None


class ShaderConfig(BaseModel):
    """Stored shader configuration for a game."""
    game_id: str
    shader_name: str
    emulator: str
    shader_path: str
    parameters: Dict[str, Any] = {}
    applied_at: str


class ResolveRequest(BaseModel):
    game_name: str = Field(..., alias="title", description="Game title to resolve")
    platform: Optional[str] = Field(None, description="Optional platform filter")
    year: Optional[int] = Field(None, description="Optional release year")
    limit: int = Field(5, ge=1, le=25, description="Maximum number of results to return")
    fuzzy_threshold: float = Field(0.82, ge=0.0, le=1.0, description="Minimum similarity ratio for fuzzy matches")

    class Config:
        allow_population_by_field_name = True


class LaunchByTitleRequest(BaseModel):
    """Request to launch a game by title (RetroFE bridge)."""
    title: str
    collection: Optional[str] = None

# Common gaming abbreviation expansions for fuzzy matching
# All values should map TO the shorter/canonical form found in LaunchBox
ABBREVIATION_MAP = {
    "brothers": "bros",
    "brother": "bro",
    "versus": "vs",
    "street": "st",
    "doctor": "dr",
    "mister": "mr",
    "junior": "jr",
    "senior": "sr",
    "edition": "ed",
    "deluxe": "dx",
    "tournament": "te",
    "championship": "champ",
    "international": "intl",
    "volume": "vol",
    "number": "no",
    "part": "pt",
    "episode": "ep",
}

# Roman numeral normalization (both directions for flexibility)
NUMERAL_MAP = {
    "1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v",
    "6": "vi", "7": "vii", "8": "viii", "9": "ix", "10": "x",
    # Also map spelled-out to roman
    "one": "i", "two": "ii", "three": "iii", "four": "iv", "five": "v",
}

NOISE_TOKENS = {
    "the", "a", "an",
    "arcade", "mame",
    "game", "games",
    "version", "ver",
}

# Tokens that typically signal sequels/variants rather than base releases.
VARIANT_TOKENS = {
    "jr", "super", "plus", "dx",
    "special", "champ", "championship",
    "ultimate", "deluxe", "remix", "redux",
    "remastered", "collection", "gold", "platinum",
    "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
}

ARCADE_HINT_TOKENS = {"arcade", "mame", "cabinet"}


def _tokenize_title(value: Optional[str], *, drop_variant_tokens: bool = False) -> List[str]:
    """Normalize a title into stable matching tokens."""
    if not value:
        return []

    text = value.lower()
    # Strip bracketed region/manufacturer tags: "(Midway)", "[USA]", etc.
    text = re.sub(r"[\(\[].*?[\)\]]", " ", text)

    for full, abbrev in ABBREVIATION_MAP.items():
        text = re.sub(rf"\b{full}\b", abbrev, text)

    for arabic, roman in NUMERAL_MAP.items():
        text = re.sub(rf"\b{arabic}\b", roman, text)

    tokens = re.findall(r"[a-z0-9]+", text)
    if not tokens:
        return []

    out: List[str] = []
    for token in tokens:
        if token in NOISE_TOKENS:
            continue
        if drop_variant_tokens and token in VARIANT_TOKENS:
            continue
        out.append(token)
    return out


def _normalize_title(value: Optional[str]) -> str:
    """Normalize a game title for comparison.

    Applies abbreviation expansion and roman numeral normalization
    to improve matching between user input and LaunchBox titles.
    Example: 'Super Mario Brothers 2' -> 'supermariobroii'
    """
    return "".join(_tokenize_title(value, drop_variant_tokens=False))


def _normalize_title_base(value: Optional[str]) -> str:
    """Variant-insensitive normalization for selecting a base/default title."""
    return "".join(_tokenize_title(value, drop_variant_tokens=True))


def _is_arcade_platform(platform: Optional[str]) -> bool:
    p = (platform or "").lower()
    return "arcade" in p or "mame" in p


def _pick_default_candidate(
    requested_title: str,
    matches: List[Tuple[float, Game]],
    platform_filter: Optional[str],
) -> Optional[Tuple[float, Game, str]]:
    """Pick a safe default when fuzzy matching returns multiple close variants."""
    if not matches:
        return None

    candidates = matches[:12]
    if not candidates:
        return None

    request_norm = _normalize_title(requested_title)
    request_base = _normalize_title_base(requested_title)
    if not request_base:
        return None

    top_score, top_game = candidates[0]
    second_score = candidates[1][0] if len(candidates) > 1 else -1.0
    # Strong score lead is safe to auto-pick.
    if top_score >= 0.96 and (len(candidates) == 1 or (top_score - second_score) >= 0.08):
        return top_score, top_game, "score_leader"

    strict_same = [(s, g) for s, g in candidates if _normalize_title(g.title) == request_norm]
    if len(strict_same) == 1:
        score, game = strict_same[0]
        return score, game, "strict_title"

    base_same = [(s, g) for s, g in candidates if _normalize_title_base(g.title) == request_base]
    if not base_same:
        return None

    platform_norm = (platform_filter or "").lower().strip()
    if platform_norm:
        platform_filtered = [
            (s, g) for s, g in base_same
            if platform_norm in (g.platform or "").lower()
        ]
        if platform_filtered:
            base_same = platform_filtered

    request_mentions_arcade = (
        bool(platform_norm and _is_arcade_platform(platform_norm))
        or any(tok in (requested_title or "").lower() for tok in ARCADE_HINT_TOKENS)
    )

    def rank(item: Tuple[float, Game]) -> Tuple[int, int, int, int, str]:
        _score, game = item
        title_norm = _normalize_title(game.title)
        title_base = _normalize_title_base(game.title)
        has_variant = int(title_norm != title_base)
        arcade_penalty = 0 if (request_mentions_arcade and _is_arcade_platform(game.platform)) else 1
        year = game.year if isinstance(game.year, int) else 9999
        return (arcade_penalty, has_variant, len(title_norm), year, (game.title or "").lower())

    ranked = sorted(base_same, key=rank)
    best_score, best_game = ranked[0]
    if best_score < 0.82:
        return None

    # If best two candidates tie exactly, force disambiguation for safety.
    if len(ranked) > 1 and rank(ranked[0]) == rank(ranked[1]):
        return None

    return best_score, best_game, "canonical_default"





# -----------------------------------------------------------------------------
# Shader discovery and binding store helpers
# -----------------------------------------------------------------------------


def get_available_shaders() -> Dict[str, list]:
    """Scan A: drive for installed shader presets."""
    from backend.constants.a_drive_paths import AA_DRIVE_ROOT

    shaders: Dict[str, list] = {"mame": [], "retroarch": []}

    root = Path(AA_DRIVE_ROOT)

    # MAME shaders (scan recursively; support .fx in common HLSL folders and BGFX chains)
    mame_shader_dir = root / "Emulators" / "MAME" / "shaders"
    mame_hlsl_dir = root / "Emulators" / "MAME" / "hlsl"
    mame_bgfx_chains_dir = root / "Emulators" / "MAME" / "bgfx" / "chains"
    for d in (mame_shader_dir, mame_hlsl_dir):
        if d.exists():
            for shader_file in d.rglob("*.fx"):
                shaders["mame"].append({
                    "name": shader_file.stem,
                    "path": str(shader_file),
                    "type": "hlsl",
                })
    if mame_bgfx_chains_dir.exists():
        for chain in mame_bgfx_chains_dir.rglob("*.json"):
            shaders["mame"].append({
                "name": chain.stem,  # chain name to be used in bgfx_screen_chains
                "path": str(chain),
                "type": "bgfx",
            })

    # RetroArch shaders (scan recursively; support .slangp and .glslp)
    retroarch_shader_dir = root / "Emulators" / "RetroArch" / "shaders"
    if retroarch_shader_dir.exists():
        for pattern, stype in (("*.slangp", "slang"), ("*.glslp", "glsl")):
            for shader_file in retroarch_shader_dir.rglob(pattern):
                shaders["retroarch"].append({
                    "name": shader_file.stem,
                    "path": str(shader_file),
                    "type": stype,
                })

    return shaders


# (Note) Per-game shader configs are stored under configs/shaders/games/<game_id>.json


def _serialize_game(game: Game) -> Dict[str, Any]:
    return {
        "id": game.id,
        "title": game.title,
        "platform": game.platform,
        "year": game.year,
        "genre": game.genre,
    }


def _filter_games(games: List[Game], platform: Optional[str], year: Optional[int]) -> List[Game]:
    if not platform and year is None:
        return list(games)
    platform_norm = platform.lower().strip() if platform else None
    filtered: List[Game] = []
    for game in games:
        if platform_norm:
            gp = (game.platform or "").lower()
            if gp != platform_norm and platform_norm not in gp:
                continue
        if year is not None and game.year != year:
            continue
        filtered.append(game)
    return filtered


def _find_exact_match(games: List[Game], title: str) -> Optional[Game]:
    matches = _find_exact_matches(games, title)
    return matches[0] if matches else None


def _find_exact_matches(games: List[Game], title: str) -> List[Game]:
    target = _normalize_title(title)
    if not target:
        return []
    matches: List[Game] = []
    for game in games:
        if _normalize_title(game.title) == target:
            matches.append(game)
    return matches


def _find_fuzzy_matches(games: List[Game], title: str, threshold: float) -> List[Tuple[float, Game]]:
    """Find games matching title using fuzzy string matching.
    
    RELIABILITY GUARANTEES:
    1. Graceful Degradation: Uses rapidfuzz if available, falls back to difflib
    2. Dirty Data Protection: Filters out games with None/empty titles
    3. Type Safety: Clamps threshold between 0.0 and 1.0
    
    Args:
        games: List of Game objects to search
        title: Search query string
        threshold: Minimum similarity score (0.0 to 1.0)
    
    Returns:
        List of (score, Game) tuples sorted by score descending
    """
    # === TYPE SAFETY: Clamp threshold (default 0.65 for lenient partial matching) ===
    threshold = max(0.0, min(1.0, float(threshold) if threshold is not None else 0.65))
    
    # === INPUT VALIDATION ===
    target = _normalize_title(title)
    target_tokens = set(_tokenize_title(title, drop_variant_tokens=True))
    if not target:
        return []
    
    # === DIRTY DATA PROTECTION: Filter invalid games ===
    valid_games: List[Tuple[str, set, Game]] = []
    for game in games:
        try:
            if game is None:
                continue
            game_title = getattr(game, 'title', None) if not isinstance(game, dict) else game.get('title')
            if not game_title or not isinstance(game_title, str) or not game_title.strip():
                continue
            normalized = _normalize_title(game_title)
            base_tokens = set(_tokenize_title(game_title, drop_variant_tokens=True))
            if normalized and base_tokens:
                # Prevent unrelated token collisions (e.g., "Pac-Man" matching "Narc").
                if target_tokens and not (target_tokens & base_tokens):
                    continue
                valid_games.append((normalized, base_tokens, game))
        except Exception:
            # Skip any game that causes an error during normalization
            continue
    
    if not valid_games:
        return []
    
    # === GRACEFUL DEGRADATION: Try rapidfuzz, fallback to difflib ===
    scored: List[Tuple[float, Game]] = []
    
    try:
        # Attempt rapidfuzz (10x faster, better fuzzy matching)
        from rapidfuzz import fuzz
        _USE_RAPIDFUZZ = True
    except ImportError:
        _USE_RAPIDFUZZ = False
        logger.info("[Librarian] rapidfuzz not available, using difflib (slower)")
    
    if _USE_RAPIDFUZZ:
        # Use partial_ratio for lenient matching (allows "Mario" -> "Super Mario Bros.")
        # Use partial_ratio for lenient matching (allows "Mario" -> "Super Mario Bros.")
        threshold_100 = threshold * 100
        for normalized, _base_tokens, game in valid_games:
            try:
                score = fuzz.partial_ratio(target, normalized) / 100.0
                if score >= threshold:
                    scored.append((score, game))
            except Exception:
                # Skip games that cause rapidfuzz errors
                continue
    else:
        # Fallback to stdlib difflib.SequenceMatcher
        for normalized, _base_tokens, game in valid_games:
            try:
                score = SequenceMatcher(None, target, normalized).ratio()
                if score >= threshold:
                    scored.append((score, game))
            except Exception:
                # Skip games that cause SequenceMatcher errors
                continue
    
    # Sort by score descending
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored



def _normalize_plugin_candidate(raw: Dict[str, Any]) -> Dict[str, Any]:
    def _first(keys: List[str]) -> Optional[Any]:
        for key in keys:
            if key in raw and raw[key]:
                return raw[key]
        return None

    year_val = _first(["year", "Year", "releaseDate", "ReleaseDate"])
    try:
        if isinstance(year_val, str) and len(year_val) >= 4:
            year_val = int(year_val[:4])
        elif year_val is not None:
            year_val = int(year_val)
    except Exception:
        year_val = None

    return {
        "id": _first(["id", "gameId", "ID", "GameId"]),
        "title": _first(["title", "Title"]) or "",
        "platform": _first(["platform", "Platform"]) or "",
        "year": year_val,
        "genre": _first(["genre", "Genre"]),
    }


async def _resolve_via_plugin(
    game_name: str,
    platform: Optional[str],
    year: Optional[int],
    limit: int,
    services: LaunchBoxServices,
) -> Tuple[List[Dict[str, Any]], bool]:
    client = services.plugin_client
    if not client:
        return [], False

    try:
        plugin_available = client.is_available()
    except Exception as exc:
        logger.warning(f"Plugin availability check failed: {exc}")
        plugin_available = False

    if not plugin_available:
        return [], False

    try:
        raw_results = await run_in_threadpool(
            client.search_games,
            game_name,
            max(limit, 10),
        )
    except LaunchBoxPluginError as exc:
        logger.warning(f"Plugin resolve failed for '{game_name}': {exc}")
        return [], True
    except Exception as exc:
        logger.error(f"Unexpected plugin resolve error for '{game_name}': {exc}", exc_info=True)
        return [], True

    normalized: List[Dict[str, Any]] = []
    platform_norm = platform.lower().strip() if platform else None
    for raw in raw_results or []:
        candidate = _normalize_plugin_candidate(raw)
        if not candidate.get("id"):
            continue
        if platform_norm and (candidate.get("platform") or "").lower() != platform_norm:
            continue
        if year is not None and candidate.get("year") != year:
            continue
        normalized.append(candidate)
    return normalized[:limit], True


def _with_launchbox_panel(http_request: Request) -> Request:
    """
    Clone the incoming request scope and force x-panel=launchbox so downstream
    launch routing (launch_game) accepts RetroFE bridge requests.
    """
    headers = MutableHeaders(raw=list(http_request.headers.raw))
    headers["x-panel"] = "launchbox"
    scope = dict(http_request.scope)
    scope["headers"] = headers.raw
    return Request(scope, http_request.receive)


# =============================================================================
# INITIALIZATION (Called from backend/app.py startup event)
# =============================================================================


def initialize_cache():
    """
    Initialize game cache on startup with performance logging.
    This is called from backend/app.py @app.on_event("startup").
    Note: Parser now uses lazy loading, so this just triggers initialization.
    """
    start_time = time.time()
    logger.info("LaunchBox parser initializing (lazy loading enabled)")

    # Prefetch critical data to avoid first-request delay
    try:
        # Trigger lazy load in background
        _ = parser.get_cache_stats()
        init_time = (time.time() - start_time) * 1000
        logger.info(f"LaunchBox parser ready ({init_time:.1f}ms)")
    except Exception as exc:
        logger.warning(f"LaunchBox parser initialization warning: {exc}")
        # Non-fatal: cache will load on first request


# -----------------------------------------------------------------------------
# LoRa Chat Compatibility Proxy
# -----------------------------------------------------------------------------
@router.post("/chat")
async def lora_chat_proxy(req: Request):
    """Compatibility proxy so frontends posting chat to backend still work.

    Forwards payload to the Gateway's `/api/launchbox/chat` and returns its JSON.
    This keeps demo flows working even if the panel points at the backend URL.
    """
    try:
        payload = await req.json()
    except Exception:
        payload = {}

    gateway_url = os.getenv("GATEWAY_URL", "http://localhost:8787")
    url = f"{gateway_url.rstrip('/')}/api/launchbox/chat"
    try:
        resp = await run_in_threadpool(requests.post, url, json=payload, timeout=20)
        # Try to return JSON content transparently
        try:
            data = resp.json()
        except Exception:
            data = {"success": False, "error": "gateway returned non-JSON"}
        if resp.status_code != 404:
            return JSONResponse(status_code=resp.status_code, content=data)
        # Fallback alias: /api/launchbox/ai/chat
        alias = f"{gateway_url.rstrip('/')}/api/launchbox/ai/chat"
        resp2 = await run_in_threadpool(requests.post, alias, json=payload, timeout=20)
        try:
            data2 = resp2.json()
        except Exception:
            data2 = {"success": False, "error": "gateway returned non-JSON"}
        return JSONResponse(status_code=resp2.status_code, content=data2)
    except Exception as e:
        return JSONResponse(status_code=502, content={"success": False, "error": f"gateway proxy failed: {e}"})


# -----------------------------------------------------------------------------
# RetroFE Launch Endpoint
# -----------------------------------------------------------------------------
@router.post("/retrofe/launch")
async def launch_retrofe(req: Request):
    """Launch RetroFE fullscreen frontend.
    
    Executes RetroFE as a detached process so the user can browse their
    game library in a beautiful fullscreen interface. Games launched from
    RetroFE will still route through Arcade Assistant's backend.
    """
    retrofe_exe = Paths.RetroFE.executable()
    retrofe_cwd = Paths.RetroFE.root()
    
    if not retrofe_exe.exists():
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": f"RetroFE not found at {retrofe_exe}. Run generate_retrofe_collections.py first."
            }
        )
    
    try:
        # Launch RetroFE as detached process
        if os.name == 'nt':
            # Windows: use CREATE_NEW_PROCESS_GROUP and DETACHED_PROCESS
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008
            subprocess.Popen(
                [str(retrofe_exe)],
                cwd=str(retrofe_cwd),
                creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            # Linux/Mac
            subprocess.Popen(
                [str(retrofe_exe)],
                cwd=str(retrofe_cwd),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        
        logger.info("RetroFE launched successfully")
        # Update runtime state to browsing in RetroFE
        try:
            drive_root = getattr(req.app.state, "drive_root", None)
            update_runtime_state({
                "frontend": "retrofe",
                "mode": "browse",
                "system_id": None,
                "game_title": None,
                "game_id": None,
                "player": None,
                "elapsed_seconds": None,
            }, drive_root)
        except Exception:
            pass
        return JSONResponse(content={
            "success": True,
            "message": "RetroFE launched. Press ESC to exit."
        })
    except Exception as e:
        logger.error(f"Failed to launch RetroFE: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Failed to launch RetroFE: {e}"}
        )



def _start_dewey_overlay_sidecar() -> tuple[bool, str]:
    """Best-effort start for Dewey F9 overlay companion process."""
    enabled = os.getenv("AA_AUTO_START_DEWEY_OVERLAY", "true").lower() in {"1", "true", "yes"}
    if not enabled:
        return False, "disabled by AA_AUTO_START_DEWEY_OVERLAY"

    if os.name != "nt":
        return False, "unsupported on non-Windows host"

    repo_root = Path(__file__).resolve().parents[2]
    overlay_entry = repo_root / "frontend" / "electron" / "main.cjs"
    if not overlay_entry.exists():
        return False, f"overlay entry missing: {overlay_entry}"

    candidates = [
        [str(repo_root / "frontend" / "node_modules" / ".bin" / "electron.cmd"), str(overlay_entry)],
        ["electron", str(overlay_entry)],
    ]

    CREATE_NEW_PROCESS_GROUP = 0x00000200
    DETACHED_PROCESS = 0x00000008

    last_error = None
    for cmd in candidates:
        exe = cmd[0]
        if exe.lower().endswith("electron.cmd") and not Path(exe).exists():
            continue
        try:
            subprocess.Popen(
                cmd,
                cwd=str(repo_root),
                creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True, f"started via: {exe}"
        except Exception as e:
            last_error = e

    return False, f"failed to start overlay: {last_error}"


# -----------------------------------------------------------------------------
# LaunchBox App Launch Endpoint
# -----------------------------------------------------------------------------
@router.post("/frontend/launchbox/launch")
async def launch_launchbox_app(req: Request):
    """Launch LaunchBox.exe as a detached process."""
    drive_root = getattr(req.app.state, "drive_root", None)
    drive_letter_root: Optional[Path] = None
    try:
        if isinstance(drive_root, Path) and drive_root.drive:
            drive_letter_root = Path(f"{drive_root.drive}\\")
        elif isinstance(drive_root, str):
            p = Path(drive_root)
            if p.drive:
                drive_letter_root = Path(f"{p.drive}\\")
    except Exception:
        drive_letter_root = None

    candidates: List[Path] = []
    if drive_letter_root:
        candidates.extend([
            drive_letter_root / "LaunchBox" / "LaunchBox.exe",
            drive_letter_root / "LaunchBox" / "Core" / "LaunchBox.exe",
        ])
    candidates.append(Paths.LaunchBox.executable())

    # Preserve order and remove duplicates.
    deduped: List[Path] = []
    seen = set()
    for cand in candidates:
        key = str(cand).lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cand)

    launchbox_exe = next((cand for cand in deduped if cand.exists()), None)
    if not launchbox_exe:
        searched = "; ".join(str(c) for c in deduped)
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": f"LaunchBox not found. Searched: {searched}"
            }
        )
    launchbox_cwd = launchbox_exe.parent

    try:
        if os.name == 'nt':
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008
            subprocess.Popen(
                [str(launchbox_exe)],
                cwd=str(launchbox_cwd),
                creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            subprocess.Popen(
                [str(launchbox_exe)],
                cwd=str(launchbox_cwd),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        logger.info("LaunchBox launched successfully: %s", launchbox_exe)

        # Direct LaunchBox launch should stay focused on LaunchBox itself.
        # Dewey remains an explicit F9 action rather than auto-activating here.
        overlay_started = False
        overlay_note = "not triggered for direct LaunchBox launch"
        try:
            drive_root = getattr(req.app.state, "drive_root", None)
            update_runtime_state({
                "frontend": "launchbox",
                "mode": "browse",
                "system_id": None,
                "game_title": None,
                "game_id": None,
                "player": None,
                "elapsed_seconds": None,
            }, drive_root)
        except Exception:
            pass

        return JSONResponse(content={
            "success": True,
            "message": f"LaunchBox launched from {launchbox_exe}.",
            "overlay_started": overlay_started,
            "overlay_note": overlay_note,
        })
    except Exception as e:
        logger.error(f"Failed to launch LaunchBox: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Failed to launch LaunchBox: {e}"}
        )

# -----------------------------------------------------------------------------
# Pegasus Launch Endpoint
# -----------------------------------------------------------------------------
@router.post("/pegasus/launch")
async def launch_pegasus(req: Request):
    """Launch Pegasus fullscreen frontend.
    
    Executes Pegasus as a detached process so the user can browse their
    game library in a beautiful fullscreen interface. Games launched from
    Pegasus will still route through Arcade Assistant's backend.
    """
    pegasus_exe = Paths.Pegasus.executable()
    pegasus_cwd = Paths.Pegasus.root()
    
    if not pegasus_exe.exists():
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": f"Pegasus not found at {pegasus_exe}. Install Pegasus to <drive>\\Tools\\Pegasus first."
            }
        )
    
    try:
        # Launch Pegasus as detached process
        if os.name == 'nt':
            # Windows: use CREATE_NEW_PROCESS_GROUP and DETACHED_PROCESS
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008
            subprocess.Popen(
                [str(pegasus_exe)],
                cwd=str(pegasus_cwd),
                creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            # Linux/Mac
            subprocess.Popen(
                [str(pegasus_exe)],
                cwd=str(pegasus_cwd),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        
        logger.info("Pegasus launched successfully")
        # Update runtime state to browsing in Pegasus
        try:
            drive_root = getattr(req.app.state, "drive_root", None)
            update_runtime_state({
                "frontend": "pegasus",
                "mode": "browse",
                "system_id": None,
                "game_title": None,
                "game_id": None,
                "player": None,
                "elapsed_seconds": None,
            }, drive_root)
        except Exception:
            pass
        return JSONResponse(content={
            "success": True,
            "message": "Pegasus launched. Press ESC to exit."
        })
    except Exception as e:
        logger.error(f"Failed to launch Pegasus: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Failed to launch Pegasus: {e}"}
        )


# =============================================================================
# ROUTING DECISIONS LOGGING
# =============================================================================

ROUTING_LOG = os.path.join("logs", "routing-decisions.jsonl")


def _ensure_logs_dir() -> None:
    try:
        os.makedirs(os.path.dirname(ROUTING_LOG) or ".", exist_ok=True)
    except Exception:
        pass


def _read_routing_policy() -> Dict[str, Any]:
    """Best-effort read of <drive>/configs/routing-policy.json for policy flags."""
    try:
        from backend.constants.a_drive_paths import AA_DRIVE_ROOT
        p = os.path.join(str(AA_DRIVE_ROOT), "configs", "routing-policy.json")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def _parse_command_info(command: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract (exe_path, emulator_name, profile_used) from a command string, if available."""
    if not command or not isinstance(command, str) or not command.strip():
        return None, None, None
    cmd = command.strip()
    # exe path: first token, possibly quoted
    exe_path = None
    try:
        if cmd.startswith("\""):
            end = cmd.find("\"", 1)
            if end > 0:
                exe_path = cmd[1:end]
        if not exe_path:
            exe_path = cmd.split()[0]
    except Exception:
        exe_path = None

    emulator = None
    exe_lower = (exe_path or "").lower()
    if "retroarch.exe" in exe_lower:
        emulator = "RetroArch"
    elif "mame.exe" in exe_lower:
        emulator = "MAME"
    elif "pcsx2.exe" in exe_lower:
        emulator = "PCSX2"
    elif "rpcs3.exe" in exe_lower:
        emulator = "RPCS3"
    elif "teknoparrotui.exe" in exe_lower or "teknoparrot.exe" in exe_lower or "cmd.exe" in exe_lower:
        # cmd.exe wrapper might be used for TeknoParrot + AHK
        emulator = "TeknoParrot"

    # profile: look for --profile=VALUE
    profile = None
    try:
        # simple scan for --profile=
        idx = cmd.lower().find("--profile=")
        if idx >= 0:
            tail = cmd[idx + len("--profile="):]
            # stop at first space
            stop = tail.find(" ")
            val = tail if stop < 0 else tail[:stop]
            # Strip surrounding quotes if present
            v = val.strip()
            if v.startswith('"') and v.endswith('"') and len(v) >= 2:
                v = v[1:-1]
            elif v.startswith("'") and v.endswith("'") and len(v) >= 2:
                v = v[1:-1]
            profile = v
    except Exception:
        profile = None

    return exe_path, emulator, profile


def _best_effort_find_pid(exe_path: Optional[str], window_seconds: int = 15) -> Optional[int]:
    """Best-effort PID resolution for a launched process.

    Used for direct-to-emulator launches where we only have the command string.
    Returns the most recently created process matching exe_path within the time window.
    """
    if not exe_path:
        return None
    try:
        import psutil
        now = time.time()
        exe_norm = os.path.normcase(os.path.normpath(exe_path))
        best_pid = None
        best_ctime = 0.0
        for proc in psutil.process_iter(["pid", "exe", "create_time"]):
            try:
                pexe = proc.info.get("exe")
                ctime = float(proc.info.get("create_time") or 0.0)
                if not pexe:
                    continue
                if (now - ctime) > float(window_seconds):
                    continue
                pexe_norm = os.path.normcase(os.path.normpath(str(pexe)))
                if pexe_norm != exe_norm:
                    continue
                if ctime >= best_ctime:
                    best_ctime = ctime
                    best_pid = int(proc.info["pid"])
            except Exception:
                continue
        return best_pid
    except Exception:
        return None


def log_decision(entry: Dict[str, Any]) -> None:
    _ensure_logs_dir()
    try:
        with open(ROUTING_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # Logging must never break the launch path
        pass


# -----------------------------------------------------------------------------
# ScoreKeeper Sam - launch event logging (JSONL under state/scorekeeper)
# -----------------------------------------------------------------------------

def _extract_emulator_from_result(result: Any, command: Optional[str]) -> tuple:
    """
    Extract emulator and adapter names from launch result.
    
    Returns:
        (emulator_name, adapter_name) - Either can be None if not determinable
    """
    emulator = None
    adapter = None
    
    # Try to get from result object first (explicit attribution)
    if hasattr(result, 'adapter'):
        adapter = getattr(result, 'adapter', None)
    if hasattr(result, 'emulator'):
        emulator = getattr(result, 'emulator', None)
    
    # If result is a dict (from adapter)
    if isinstance(result, dict):
        adapter = result.get('adapter') or adapter
        emulator = result.get('emulator') or emulator
    
    # Infer from command string if not explicit
    if not emulator and command:
        cmd_lower = command.lower()
        if 'retroarch' in cmd_lower:
            emulator = 'RetroArch'
        elif 'mame' in cmd_lower:
            emulator = 'MAME'
        elif 'teknoparrot' in cmd_lower:
            emulator = 'TeknoParrot'
            adapter = adapter or 'teknoparrot'
        elif 'pcsx2' in cmd_lower:
            emulator = 'PCSX2'
        elif 'rpcs3' in cmd_lower:
            emulator = 'RPCS3'
        elif 'dolphin' in cmd_lower:
            emulator = 'Dolphin'
        elif 'duckstation' in cmd_lower:
            emulator = 'DuckStation'
        elif 'redream' in cmd_lower:
            emulator = 'Redream'
        elif 'flycast' in cmd_lower:
            emulator = 'Flycast'
        elif 'supermodel' in cmd_lower:
            emulator = 'Supermodel'
    
    return emulator, adapter


def _map_panel_to_frontend(panel: Optional[str]) -> str:
    """Map x-panel header to frontend name for ScoreKeeper Sam."""
    if not panel:
        return "unknown"
    panel_lower = panel.lower().strip()
    if panel_lower in {"pegasus", "pegasus-fe"}:
        return "pegasus"
    elif panel_lower in {"retrofe", "retro-fe"}:
        return "retrofe"
    elif panel_lower in {"launchbox", "launchbox-bigbox", "bigbox"}:
        return "launchbox"
    return panel_lower


def _log_launch_event(
    http_request: Request,
    game: Any,
    result: Any,
    event_type: str = "launch_start"
) -> None:
    """
    Log a launch event for ScoreKeeper Sam.
    
    Args:
        http_request: The HTTP request with headers
        game: The game object being launched
        result: The launch result
        event_type: "launch_start" or "launch_end"
    """
    try:
        drive_root = http_request.app.state.drive_root if hasattr(http_request, 'app') else None
        if not drive_root:
            return
        # Respect sanctioned paths - write under state/scorekeeper
        target_dir = drive_root / 'state' / 'scorekeeper'
        target_dir.mkdir(parents=True, exist_ok=True)
        log_file = target_dir / 'launches.jsonl'
        
        # Extract player/session info from headers for ScoreKeeper Sam integration
        headers = http_request.headers if hasattr(http_request, 'headers') else {}
        player_id = headers.get('x-user-profile') or headers.get('x-profile-id')
        player_name = headers.get('x-user-name')
        session_owner = headers.get('x-session-owner')
        
        # Get panel and map to frontend
        panel = headers.get('x-panel')
        frontend = _map_panel_to_frontend(panel)
        
        # Extract emulator/adapter attribution
        command = getattr(result, 'command', None)
        emulator, adapter = _extract_emulator_from_result(result, command)
        
        # Get profile if available (e.g., TeknoParrot profile)
        profile = None
        if hasattr(result, 'profile'):
            profile = getattr(result, 'profile', None)
        elif isinstance(result, dict):
            profile = result.get('profile')
        
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "game_id": getattr(game, 'id', None),
            "title": getattr(game, 'title', None),
            "platform": getattr(game, 'platform', None),
            "method": getattr(result, 'method_used', None) or getattr(result, 'method', None),
            "success": bool(getattr(result, 'success', False)),
            "command": command,
            # Explicit attribution for ScoreKeeper Sam
            "panel": panel,
            "frontend": frontend,
            "emulator": emulator,
            "adapter": adapter,
            "profile": profile,
            "corr": headers.get('x-corr-id'),
            # Player/session tracking for ScoreKeeper Sam
            "player_id": player_id,
            "player_name": player_name,
            "session_owner": session_owner,
        }
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # Never break the launch flow for logging issues
        pass


def _log_led_launch_binding(
    http_request: Request,
    game: Any,
    profile_name: str,
    apply_result: Dict[str, Any],
    preview: Dict[str, Any],
    binding: Dict[str, Any],
) -> None:
    """Append a record showing which LED profile was auto-applied for a launch."""
    try:
        drive_root = http_request.app.state.drive_root if hasattr(http_request, "app") else None
        if not drive_root:
            return
        log_file = drive_root / ".aa" / "logs" / "changes.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "scope": "led_game_profile",
            "action": "launch_auto_apply",
            "game_id": getattr(game, "id", None),
            "game_title": getattr(game, "title", None),
            "platform": getattr(game, "platform", None),
            "profile_name": profile_name,
            "binding_updated_at": binding.get("updated_at"),
            "target_file": apply_result.get("target_file"),
            "led_status": apply_result.get("status"),
            "total_channels": (preview or {}).get("total_channels"),
            "missing_buttons": (preview or {}).get("missing_buttons"),
            "device": (http_request.headers.get("x-device-id") if hasattr(http_request, "headers") else None),
            "panel": (http_request.headers.get("x-panel") if hasattr(http_request, "headers") else None),
        }
        with open(log_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # LED logging must not impact the launch flow
        pass


async def _apply_led_profile_binding_for_launch(http_request: Request, game: Any) -> Optional[Dict[str, Any]]:
    """Best-effort helper to apply the bound LED profile before launching a game.
    
    Resolution order:
    1. Explicit game -> LED profile binding (from game_profiles.json)
    2. Genre-based LED profile from GenreProfileService (auto-detect by genre)
    3. No LED change if neither found
    """
    game_id = getattr(game, "id", None)
    game_title = getattr(game, "title", None)
    game_genre = getattr(game, "genre", None)
    game_platform = getattr(game, "platform", None)
    
    if not game_id:
        return None
    app_state = getattr(getattr(http_request, "app", None), "state", None)
    if not app_state:
        return None
    drive_root = getattr(app_state, "drive_root", None)
    manifest = getattr(app_state, "manifest", {}) or {}
    if not drive_root:
        return None

    def _worker() -> Optional[Dict[str, Any]]:
        # 1. Check for explicit game binding first
        store = LEDGameProfileStore(drive_root, manifest)
        binding = store.get_binding(game_id)
        
        if binding:
            profile_name = binding.get("profile_name")
            if profile_name:
                service = LEDMappingService(drive_root, manifest)
                profile_doc = service.load_profile_document(profile_name)
                preview_result = service.preview(profile_doc["document"])
                apply_result = service.apply(
                    profile_doc["document"],
                    dry_run=False,
                    backup_on_write=False,
                    preview=preview_result,
                )
                return {
                    "binding": binding,
                    "profile_name": profile_name,
                    "source": "explicit_binding",
                    "preview": preview_result.response,
                    "apply_result": apply_result,
                }
        
        # 2. Fall back to genre-based LED profile
        try:
            from ..services.genre_profile_service import GenreProfileService
            genre_service = GenreProfileService()
            profile = genre_service.get_profile_for_game(
                game_id=game_id,
                title=game_title,
                genre=game_genre,
                platform=game_platform
            )
            
            if profile and profile.get("led_profile"):
                led_profile = profile["led_profile"]
                profile_key = profile.get("profile_key", "genre")
                
                # Apply LED colors directly from genre profile
                service = LEDMappingService(drive_root, manifest)
                
                # Convert genre LED profile format to LEDMappingService format
                buttons_payload = {}
                for button_key, button_data in led_profile.items():
                    if isinstance(button_data, dict) and "color" in button_data:
                        buttons_payload[button_key] = {"color": button_data["color"]}
                
                if buttons_payload:
                    # Create a synthetic profile document
                    profile_doc = {
                        "version": 1,
                        "profile_name": f"genre_{profile_key}",
                        "buttons": buttons_payload
                    }
                    preview_result = service.preview(profile_doc)
                    apply_result = service.apply(
                        profile_doc,
                        dry_run=False,
                        backup_on_write=False,
                        preview=preview_result,
                    )
                    
                    logger.info(
                        "Applied genre-based LED profile '%s' for game '%s' (genre=%s)",
                        profile_key, game_title, game_genre
                    )
                    
                    return {
                        "binding": {
                            "game_id": game_id,
                            "profile_name": f"genre_{profile_key}",
                            "source": "genre_auto",
                        },
                        "profile_name": f"genre_{profile_key}",
                        "source": "genre_profile",
                        "genre_key": profile_key,
                        "preview": preview_result.response,
                        "apply_result": apply_result,
                    }
        except Exception as genre_exc:
            logger.debug("Genre profile LED fallback failed: %s", genre_exc)
        
        return None

    try:
        result = await run_in_threadpool(_worker)
    except HTTPException as exc:
        logger.warning(
            "LED profile apply failed for game_id=%s: %s",
            game_id,
            getattr(exc, "detail", exc),
        )
        return None
    except Exception as exc:
        logger.warning("LED profile apply failed for game_id=%s: %s", game_id, exc)
        return None

    if result:
        _log_led_launch_binding(
            http_request,
            game,
            result["profile_name"],
            result["apply_result"],
            result["preview"],
            result["binding"],
        )
    return result


async def _ensure_controller_config_for_game(http_request: Request, game: Any) -> Optional[Dict[str, Any]]:
    """Best-effort helper to generate controller config files before launching a game.
    
    Uses GenreProfileService to get genre-appropriate button mappings, then
    generates emulator-specific config files:
    - MAME: default.cfg with JOYCODE_* entries
    - TeknoParrot: XInput bindings based on genre profile
    
    This ensures the emulator has correct button mappings based on game genre.
    """
    game_platform = getattr(game, "platform", None)
    game_title = getattr(game, "title", None)
    game_genre = getattr(game, "genre", None)
    game_id = getattr(game, "id", None)
    
    if not game_platform:
        return None
    
    app_state = getattr(getattr(http_request, "app", None), "state", None)
    if not app_state:
        return None
    drive_root = getattr(app_state, "drive_root", None)
    if not drive_root:
        return None

    def _worker() -> Optional[Dict[str, Any]]:
        from pathlib import Path
        import json
        
        platform_lower = (game_platform or "").lower()
        result = {
            "platform": game_platform,
            "game_title": game_title,
            "genre": game_genre,
            "configs_generated": [],
            "profile_used": None
        }
        
        # Determine which emulators need config
        is_mame_platform = any(p in platform_lower for p in [
            "mame", "arcade", "cps", "neo geo", "neogeo", "atomiswave",
            "naomi", "model 2", "model 3", "cave", "namco", "taito", "sega"
        ])
        
        is_tp_platform = any(p in platform_lower for p in [
            "teknoparrot", "taito type x", "lindbergh", "ringedge", "ringwide",
            "nu", "es1", "es2", "es3"
        ])
        
        # Get genre profile for this game
        try:
            from ..services.genre_profile_service import get_genre_profile_service
            genre_service = get_genre_profile_service(Path(drive_root))
            
            # Get the profile for this game's genre
            profile_data = genre_service.get_profile_for_game(
                game_id=game_id,
                game_title=game_title,
                genre=game_genre,
                platform=game_platform
            )
            
            if profile_data:
                profile_key = profile_data.get("profile_key", "default")
                result["profile_used"] = profile_key
                logger.info("Using genre profile '%s' for '%s' (genre=%s)", 
                           profile_key, game_title, game_genre)
        except Exception as e:
            logger.debug("Genre profile lookup failed: %s", e)
            profile_data = None
            profile_key = "default"
        
        # Load base controls.json
        controls_path = Path(drive_root) / "Arcade Assistant Local" / "config" / "mappings" / "controls.json"
        if not controls_path.exists():
            controls_path = Path(drive_root) / "config" / "mappings" / "controls.json"
        if not controls_path.exists():
            logger.debug("controls.json not found, skipping controller config generation")
            return None
        
        try:
            with open(controls_path, "r", encoding="utf-8") as f:
                controls_data = json.load(f)
        except Exception as e:
            logger.debug("Failed to load controls.json: %s", e)
            return None
        
        mappings = controls_data.get("mappings", {})
        
        # Generate MAME config
        if is_mame_platform:
            try:
                from ..services.mame_config_generator import generate_mame_config_xml
                from ..services.emulator_registry import default_registry
                
                mame_cfg_path = Path(drive_root) / "Emulators" / "MAME" / "cfg" / "default.cfg"
                
                # Get MAME-specific key mapping rules
                mame_pattern = default_registry.get_pattern("mame")
                key_rules = mame_pattern.key_mapping_rules if mame_pattern else {}
                
                # Generate the config XML with controls.json mappings
                xml_content = generate_mame_config_xml(mappings)
                
                # Ensure directory exists
                mame_cfg_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Write the config
                with open(mame_cfg_path, "w", encoding="utf-8") as f:
                    f.write(xml_content)
                
                logger.info("Generated MAME config for '%s' (profile=%s) at %s", 
                           game_title, profile_key, mame_cfg_path)
                result["configs_generated"].append({
                    "emulator": "mame",
                    "path": str(mame_cfg_path),
                    "profile": profile_key
                })
            except Exception as e:
                logger.warning("MAME config generation failed: %s", e)
        
        # Generate TeknoParrot config
        if is_tp_platform:
            try:
                # Get TeknoParrot-specific mappings from genre profile
                if profile_data:
                    emulator_mappings = profile_data.get("emulator_mappings", {}).get("teknoparrot", {})
                    button_map = emulator_mappings.get("button_map", {})
                    category = emulator_mappings.get("category", "generic")
                    
                    if button_map:
                        logger.info("TeknoParrot mappings for '%s' (category=%s): %s", 
                                   game_title, category, list(button_map.keys()))
                        result["configs_generated"].append({
                            "emulator": "teknoparrot",
                            "category": category,
                            "profile": profile_key,
                            "button_map": button_map,
                            "status": "ready"
                        })
                    else:
                        result["configs_generated"].append({
                            "emulator": "teknoparrot",
                            "status": "using_defaults"
                        })
                else:
                    result["configs_generated"].append({
                        "emulator": "teknoparrot",
                        "status": "no_profile"
                    })
            except Exception as e:
                logger.debug("TeknoParrot config generation failed: %s", e)
        
        return result if result["configs_generated"] else None

    try:
        result = await run_in_threadpool(_worker)
        if result:
            logger.info("Controller config generated: %s", result)
    except Exception as exc:
        logger.debug("Controller config generation failed: %s", exc)
        return None
    
    return result


@router.post("/diagnostics/autofix/retroarch")
async def autofix_retroarch(request: Request) -> Dict[str, Any]:
    """
    Auto-fix RetroArch configuration for direct launches.

    - Scans typical locations for retroarch.exe
      A:\\LaunchBox\\Emulators\\**\\retroarch.exe and A:\\Emulators\\RetroArch\\retroarch.exe
    - Chooses the first/best candidate
    - Verifies an Atari 2600 core exists (stella*libretro.dll)
    - Updates config/launchers.json with the discovered exe path
      and preserves existing core mapping unless missing
    - Backs up the original file under backups/YYYYMMDD
    """
    from pathlib import Path
    from backend.constants.a_drive_paths import LaunchBoxPaths

    def _to_windows_forward(p: Path) -> str:
        s = str(p)
        low = s.lower()
        if low.startswith('/mnt/') and len(s) > 6:
            # /mnt/x/... -> X:/...
            drive = s[5].upper()
            rest = s[7:].replace('\\', '/').replace('\\', '/')
            if rest.startswith('/'):
                rest = rest[1:]
            return f"{drive}:/{rest}"
        return s.replace('\\', '/')

    # 1) Locate retroarch.exe
    candidates: list[Path] = []
    try:
        lb_emus = LaunchBoxPaths.LAUNCHBOX_ROOT / 'Emulators'
        if lb_emus.exists():
            candidates.extend(lb_emus.rglob('retroarch.exe'))
    except Exception:
        pass
    try:
        # Generic A:/Emulators
        generic = LaunchBoxPaths.EMULATORS_ROOT
        if generic.exists():
            candidates.extend(generic.rglob('retroarch.exe'))
    except Exception:
        pass

    if not candidates:
        return {"success": False, "message": "retroarch.exe not found in typical locations"}

    # Prefer a path under LaunchBox/Emulators if present
    chosen = None
    for c in candidates:
        try:
            if str(c).lower().replace('\\', '/').find('/launchbox/emulators/') != -1:
                chosen = c
                break
        except Exception:
            continue
    if chosen is None:
        chosen = candidates[0]

    # 2) Verify core exists (stella or stella2014)
    core_rel = None
    for rel in ('cores/stella_libretro.dll', 'cores/stella2014_libretro.dll'):
        cp = chosen.parent / rel.replace('/', LaunchBoxPaths.LAUNCHBOX_ROOT.anchor or '/')  # just normalize slashes later
        # Use simple join instead of replace hack
        cp = chosen.parent / rel.replace('/', LaunchBoxPaths.LAUNCHBOX_ROOT.anchor if False else 'cores/').split('cores/')[1]
        cp = chosen.parent / 'cores' / (rel.split('/')[-1])
        try:
            if cp.exists():
                core_rel = rel
                break
        except Exception:
            continue

    # 3) Load config/launchers.json
    cfg_paths = [
        Path.cwd() / 'config' / 'launchers.json',
        Path(__file__).resolve().parents[2] / 'config' / 'launchers.json',
    ]
    cfg_path = next((p for p in cfg_paths if p.exists()), None)
    if not cfg_path:
        return {"success": False, "message": "config/launchers.json not found"}

    # 4) Backup
    drive_root = request.app.state.drive_root if hasattr(request, 'app') else Path.cwd()
    try:
        backup_path = create_backup(cfg_path, drive_root)
    except Exception:
        backup_path = None

    # 5) Update
    try:
        data = json.loads(cfg_path.read_text(encoding='utf-8'))
    except Exception as e:
        return {"success": False, "message": f"failed to read launchers.json: {e}"}

    # Ensure blocks exist
    if 'emulators' not in data or not isinstance(data['emulators'], dict):
        data['emulators'] = {}
    if 'retroarch' not in data['emulators'] or not isinstance(data['emulators']['retroarch'], dict):
        data['emulators']['retroarch'] = {}

    ra = data['emulators']['retroarch']
    ra['exe'] = _to_windows_forward(chosen)
    # Preserve cores map; add stella if missing and we verified it
    cores = ra.get('cores') or {}
    if core_rel and 'atari2600' not in cores:
        cores['atari2600'] = core_rel
    ra['cores'] = cores
    data['emulators']['retroarch'] = ra

    try:
        cfg_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
    except Exception as e:
        return {"success": False, "message": f"failed to write launchers.json: {e}"}

    return {
        "success": True,
        "retroarch_exe": ra['exe'],
        "atari2600_core": cores.get('atari2600'),
        "backup_path": str(backup_path) if backup_path else None,
    }

# =============================================================================
# API ENDPOINTS
# =============================================================================


@router.api_route("/resolve", methods=["GET", "POST"])
@with_timeout(8.0)
async def resolve_game_endpoint(
    payload: Optional[ResolveRequest] = Body(None),
    title: Optional[str] = Query(None, description="Game title (GET compatibility)"),
    platform: Optional[str] = Query(None, description="Optional platform filter"),
    year: Optional[int] = Query(None, description="Optional release year"),
    limit: int = Query(5, ge=1, le=25, description="Maximum number of candidates to return"),
    fuzzy_threshold: float = Query(0.70, ge=0.0, le=1.0, description="Minimum similarity for fuzzy matches"),
    services: LaunchBoxServices = Depends(get_launchbox_services),
):
    """
    Resolve a spoken or typed game request to a LaunchBox game entry.

    Resolution order:
      1. Exact cache match (case-insensitive)
      2. Fuzzy cache matches (SequenceMatcher, configurable threshold)
      3. Plugin search fallback (source-of-truth IDs)
      4. Return not_found with helpful context
    """
    data = payload
    if data is None:
        if not title:
            raise HTTPException(status_code=400, detail="title or game_name is required")
        data = ResolveRequest(
            game_name=title,
            platform=platform,
            year=year,
            limit=limit,
            fuzzy_threshold=fuzzy_threshold,
        )

    game_name = (data.game_name or "").strip()
    if not game_name:
        raise HTTPException(status_code=400, detail="game_name is required")

    platform_filter = data.platform if data.platform is not None else platform
    year_filter = data.year if data.year is not None else year
    limit_value = max(1, min(25, data.limit or limit))
    threshold_value = max(0.0, min(1.0, data.fuzzy_threshold if data.fuzzy_threshold is not None else fuzzy_threshold))

    games = services.parser.get_all_games() or []
    filtered_games = _filter_games(games, platform_filter, year_filter)
    
    # If platform filter was specified but returned no games, check if game exists on OTHER platforms
    # This enables the "Did you mean X on GBA or Y on Genesis?" disambiguation flow
    if platform_filter and not filtered_games:
        # Search all games (without platform filter) for potential matches
        all_matches = _find_fuzzy_matches(games, game_name, threshold_value)
        if all_matches:
            # Group matches by platform to show disambiguation options
            platforms_found = {}
            for score, game in all_matches[:10]:  # Limit to top 10
                plat = game.platform or "Unknown"
                if plat not in platforms_found:
                    platforms_found[plat] = []
                platforms_found[plat].append({
                    **_serialize_game(game),
                    "confidence": round(score, 3)
                })
            
            # Return disambiguation response for LoRa to ask clarifying question
            return {
                "status": "platform_disambiguation",
                "message": f"'{game_name}' was not found on {platform_filter}, but similar games exist on other platforms.",
                "requested_platform": platform_filter,
                "available_on": list(platforms_found.keys()),
                "suggestions": [
                    {"platform": plat, "games": games_list[:3]}  # Top 3 per platform
                    for plat, games_list in platforms_found.items()
                ],
            }
        # No matches anywhere - just return not_found
        return {
            "status": "not_found",
            "message": f"Could not find game: {game_name}",
            "plugin_available": False,
        }
    
    search_pool = filtered_games if filtered_games else games

    exact_matches = _find_exact_matches(search_pool, game_name)
    if len(exact_matches) == 1:
        exact = exact_matches[0]
        return {
            "status": "resolved",
            "source": "cache_exact",
            "game": _serialize_game(exact),
        }
    if len(exact_matches) > 1:
        suggestions: List[Dict[str, Any]] = []
        for game in exact_matches[:limit_value]:
            suggestions.append(_serialize_game(game))
        return {
            "status": "multiple_matches",
            "source": "cache_exact",
            "suggestions": suggestions,
            "count": len(exact_matches),
        }

    fuzzy_matches = _find_fuzzy_matches(search_pool, game_name, threshold_value)
    if len(fuzzy_matches) == 1:
        score, game = fuzzy_matches[0]
        candidate = _serialize_game(game)
        candidate["confidence"] = round(score, 3)
        return {
            "status": "resolved",
            "source": "cache_fuzzy",
            "game": candidate,
        }

    if len(fuzzy_matches) > 1:
        default_candidate = _pick_default_candidate(game_name, fuzzy_matches, platform_filter)
        if default_candidate is not None:
            score, game, reason = default_candidate
            candidate = _serialize_game(game)
            candidate["confidence"] = round(score, 3)
            return {
                "status": "resolved",
                "source": f"cache_fuzzy_{reason}",
                "game": candidate,
            }

        suggestions: List[Dict[str, Any]] = []
        for score, game in fuzzy_matches[:limit_value]:
            entry = _serialize_game(game)
            entry["confidence"] = round(score, 3)
            suggestions.append(entry)
        return {
            "status": "multiple_matches",
            "source": "cache_fuzzy",
            "suggestions": suggestions,
            "count": len(fuzzy_matches),
        }

    plugin_matches, plugin_available = await _resolve_via_plugin(
        game_name,
        platform_filter,
        year_filter,
        limit_value,
        services,
    )
    if plugin_matches:
        if len(plugin_matches) == 1:
            return {
                "status": "resolved",
                "source": "plugin",
                "game": plugin_matches[0],
            }
        return {
            "status": "multiple_matches",
            "source": "plugin",
            "suggestions": plugin_matches,
            "count": len(plugin_matches),
        }

    return {
        "status": "not_found",
        "message": f"Could not find game: {game_name}",
        "plugin_available": plugin_available,
    }


# =============================================================================
# Game List Endpoints (for /api/launchbox/games LoRa panel compatibility)
# =============================================================================


def _serialize_cache_game_main(game: Game) -> Dict[str, Any]:
    """Serialize Game model for JSON response."""
    return {
        "id": getattr(game, "id", ""),
        "title": getattr(game, "title", ""),
        "platform": getattr(game, "platform", ""),
        "applicationPath": getattr(game, "application_path", "") or getattr(game, "rom_path", "") or "",
        "commandLine": "",
        "genre": getattr(game, "genre", None),
        "year": getattr(game, "year", None),
    }


@router.get("/games/list")
@with_timeout(15.0)
async def list_games_legacy(
    platform: Optional[str] = Query(None),
    search: Optional[str] = Query(None),  # Accept "search" param directly
    q: Optional[str] = Query(None),        # Also accept "q" for legacy compatibility
    limit: int = Query(100, ge=1, le=20000),
):
    """
    (Legacy) List games from LaunchBox JSON cache with optional filtering.
    
    Uses pre-built JSON cache for fast response (<1s vs 10-30s XML parsing).
    Falls back to XML parser if cache unavailable.
    
    Deprecated in favor of GET /api/launchbox/games which returns a paginated object.
    """
    # Merge q and search params (q takes precedence for legacy)
    effective_search = q or search
    
    try:
        # Use JSON cache (fast) with parser fallback
        games = await run_in_threadpool(
            json_cache.filter_games,
            platform=platform,
            genre=None,
            search=effective_search,
            limit=limit
        )
        return games if games else []
    except Exception as e:
        logger.error(f"LaunchBox game list error: {e}")
        raise HTTPException(status_code=503, detail="Unable to load games from LaunchBox")


@router.get("/random")
@with_timeout(10.0)
async def random_game(platform: Optional[str] = Query(None)):
    """
    Get a random game, optionally filtered by platform.
    
    Uses JSON cache for fast access.
    Used by LoRa panel for random game selection.
    """
    try:
        # Get filtered games from JSON cache
        games = await run_in_threadpool(
            json_cache.filter_games,
            platform=platform,
            genre=None,
            search=None,
            limit=20000  # Get all matching games for random selection
        )
        
        if not games:
            raise HTTPException(status_code=503, detail="No games available")
        
        return random.choice(games)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"LaunchBox random game error: {e}")
        raise HTTPException(status_code=503, detail="Unable to load games from LaunchBox")


# =============================================================================
# Shader Management Endpoints (V2)
# =============================================================================


@router.get("/shaders/available")
async def get_shaders_available():
    """List all installed shader presets."""
    try:
        shaders = get_available_shaders()
        logger.info(
            f"[Shaders] Found {len(shaders['mame'])} MAME + {len(shaders['retroarch'])} RetroArch shaders"
        )
        return shaders
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"[Shaders] Failed to scan: {e}")
        return {"mame": [], "retroarch": [], "error": str(e)}


@router.get("/shaders/game/{game_id}")
async def get_game_shader(game_id: str, request: Request):
    """Get current shader config for specific game."""
    drive_root = request.app.state.drive_root if hasattr(request, "app") else Path.cwd()
    manifest = getattr(request.app.state, "manifest", {}) if hasattr(request, "app") else {}
    config_path = drive_root / "configs" / "shaders" / "games" / f"{game_id}.json"

    # Sanctioned path check
    sanctioned = manifest.get("sanctioned_paths", [])
    if sanctioned and not is_allowed_file(config_path, drive_root, sanctioned):
        rel = str(config_path.relative_to(drive_root)).replace("\\", "/")
        raise HTTPException(status_code=403, detail=f"Path not sanctioned: {rel}")

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        logger.info(f"[Shaders] Loaded config for {game_id}")
        return config
    else:
        return {"game_id": game_id, "shader": None}


@router.post("/shaders/preview")
async def preview_shader_change(payload: ShaderChangeRequest):
    """Preview shader config change with diff."""
    config_path = Path("configs") / "shaders" / "games" / f"{payload.game_id}.json"

    # Get current config
    old_config = None
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            old_config = json.load(f)

    # Build new config
    shaders = get_available_shaders()
    shader_list = shaders.get(payload.emulator, [])
    shader_obj = next((s for s in shader_list if s["name"] == payload.shader_name), None)

    if not shader_obj:
        return {
            "error": f"Shader '{payload.shader_name}' not found",
            "available": [s["name"] for s in shader_list],
        }

    new_config = {
        "game_id": payload.game_id,
        "shader_name": payload.shader_name,
        "emulator": payload.emulator,
        "shader_path": shader_obj["path"],
        "parameters": payload.parameters or {},
        "applied_at": datetime.utcnow().isoformat(),
    }

    # Generate diff
    if old_config:
        diff = f"Change shader from '{old_config.get('shader_name')}' to '{new_config['shader_name']}'"
    else:
        diff = f"Add new shader '{new_config['shader_name']}'"

    return {"old": old_config, "new": new_config, "diff": diff}


@router.post("/shaders/apply")
async def apply_shader_change(request: Request, payload: ShaderChangeRequest):
    """Apply shader config with automatic backup."""
    require_scope(request, "config")
    drive_root = request.app.state.drive_root
    manifest = request.app.state.manifest

    config_path = drive_root / "configs" / "shaders" / "games" / f"{payload.game_id}.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Sanctioned path check
    sanctioned = manifest.get("sanctioned_paths", [])
    if sanctioned and not is_allowed_file(config_path, drive_root, sanctioned):
        rel = str(config_path.relative_to(drive_root)).replace("\\", "/")
        raise HTTPException(status_code=403, detail=f"Path not sanctioned: {rel}")

    # Backup existing
    backup_path = None
    if config_path.exists() and getattr(request.app.state, "backup_on_write", True):
        backup = create_backup(config_path, drive_root)
        backup_path = str(backup.relative_to(drive_root)).replace("\\", "/")

    # Get shader info
    shaders = get_available_shaders()
    shader_list = shaders.get(payload.emulator, [])
    shader_obj = next((s for s in shader_list if s["name"] == payload.shader_name), None)

    if not shader_obj:
        return {"success": False, "error": f"Shader '{payload.shader_name}' not found"}

    # Write new config
    new_config = {
        "game_id": payload.game_id,
        "shader_name": payload.shader_name,
        "emulator": payload.emulator,
        "shader_path": shader_obj["path"],
        "parameters": payload.parameters or {},
        "applied_at": datetime.utcnow().isoformat(),
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(new_config, f, indent=2)

    logger.info(f"[Shaders] Applied {payload.shader_name} to {payload.game_id}")

    # Best-effort: if applying for MAME, try wiring BGFX chain in mame.ini
    try:
      if payload.emulator == "mame":
        # Determine MAME ini path (common defaults)
        # Prefer emulators/mame/mame.ini; fallback to emulators/mame/ini/mame.ini
        mame_ini_primary = request.app.state.drive_root / "emulators" / "mame" / "mame.ini"
        mame_ini_alt = request.app.state.drive_root / "emulators" / "mame" / "ini" / "mame.ini"
        mame_ini = mame_ini_primary if mame_ini_primary.exists() else mame_ini_alt
        mame_ini.parent.mkdir(parents=True, exist_ok=True)

        # Compute a reasonable BGFX chain name from shader_name when path indicates a BGFX/JSON chain
        chain_name = None
        if new_config.get("shader_path", "").lower().endswith(".json"):
            chain_name = Path(new_config["shader_path"]).stem
        # Heuristic mapping for common CRT presets requested for MAME
        if not chain_name:
            name_l = (payload.shader_name or "").lower()
            if "crt" in name_l:
                chain_name = "crt-geom"  # widely available in MAME bgfx chains

        if chain_name:
            # Read current mame.ini (text)
            current = mame_ini.read_text(encoding="utf-8") if mame_ini.exists() else ""
            lines = current.splitlines() if current else []
            def upsert(key: str, value: str):
                nonlocal lines
                found = False
                for i, line in enumerate(lines):
                    s = line.strip()
                    if not s or s.startswith("#"):  # skip comments/blank
                        continue
                    parts = s.split(None, 1)
                    if parts and parts[0] == key:
                        lines[i] = f"{key}    {value}"
                        found = True
                        break
                if not found:
                    lines.append(f"{key}    {value}")

            # Enable BGFX with our chain; bgfx_path kept relative to MAME exe (bgfx folder next to it)
            upsert("video", "bgfx")
            upsert("bgfx_path", "bgfx")
            upsert("bgfx_screen_chains", chain_name)

            mame_ini.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            logger.info(f"[Shaders:MAME] Set bgfx_screen_chains={chain_name} in {mame_ini}")
    except Exception as e:
      logger.warning(f"[Shaders:MAME] Failed to patch mame.ini: {e}")

    try:
        audit_log_append({
            "scope": "shader",
            "action": "apply",
            "game_id": payload.game_id,
            "emulator": payload.emulator,
            "shader_name": payload.shader_name,
            "target_file": str(config_path.relative_to(drive_root)).replace("\\", "/"),
            "backup_path": backup_path,
            "panel": request.headers.get("x-panel"),
            "device": request.headers.get("x-device-id"),
        })
    except Exception:
        pass

    return {
        "success": True,
        "backup_path": backup_path,
        "config_path": str(config_path.relative_to(drive_root)).replace("\\", "/"),
    }


@router.post("/shaders/revert")
async def revert_shader_change(request: Request, backup_path: str):
    """Rollback to previous shader config."""
    require_scope(request, "config")
    drive_root = request.app.state.drive_root
    manifest = request.app.state.manifest

    # Resolve backup path (allow relative to drive_root or absolute)
    backup = Path(backup_path)
    if not backup.is_absolute():
        backup = drive_root / backup

    if not backup.exists():
        return {"success": False, "error": f"Backup not found: {backup_path}"}

    # Determine game_id from file contents if possible
    game_id = None
    try:
        with open(backup, "r", encoding="utf-8") as f:
            doc = json.load(f)
            game_id = doc.get("game_id")
    except Exception:
        pass
    if not game_id:
        # Fallback to filename convention
        game_id = backup.stem.split("_shader_")[0]

    config_path = drive_root / "configs" / "shaders" / "games" / f"{game_id}.json"
    sanctioned = manifest.get("sanctioned_paths", [])
    if sanctioned and not is_allowed_file(config_path, drive_root, sanctioned):
        rel = str(config_path.relative_to(drive_root)).replace("\\", "/")
        raise HTTPException(status_code=403, detail=f"Path not sanctioned: {rel}")

    shutil.copy(backup, config_path)
    logger.info(f"[Shaders] Reverted {game_id} from {backup}")
    try:
        audit_log_append({
            "scope": "shader",
            "action": "revert",
            "game_id": game_id,
            "target_file": str(config_path.relative_to(drive_root)).replace("\\", "/"),
            "restored_from": str(backup.relative_to(drive_root)).replace("\\", "/") if drive_root in backup.parents else str(backup),
            "panel": request.headers.get("x-panel"),
            "device": request.headers.get("x-device-id"),
        })
    except Exception:
        pass
    return {"success": True, "restored_from": str(backup)}


@router.delete("/shaders/game/{game_id}")
async def delete_game_shader(
    request: Request,
    game_id: str,
    emulator: Optional[str] = Query(
        None, description="Optional emulator filter (mame/retroarch)"
    ),
    x_scope: Optional[str] = Header(None, alias="x-scope"),
):
    """Remove shader binding for a game.

    Supports two storage layouts:
      1) Per-game file: configs/shaders/games/{game_id}.json
      2) Central store: configs/shaders/game_shaders.json with bindings[]

    Returns consistent JSON with removed_count and backup_path.
    """
    # Enforce config scope
    if x_scope != "config":
        return JSONResponse(
            status_code=403,
            content={
                "error": "x-scope: config required for shader deletion",
            },
        )
    drive_root = request.app.state.drive_root
    manifest = request.app.state.manifest

    # Paths we may operate on
    config_path = drive_root / "configs" / "shaders" / "games" / f"{game_id}.json"
    store_path = drive_root / "configs" / "shaders" / "game_shaders.json"

    sanctioned = manifest.get("sanctioned_paths", [])

    # If central store exists, operate on it
    if store_path.exists():
        if sanctioned and not is_allowed_file(store_path, drive_root, sanctioned):
            rel = str(store_path.relative_to(drive_root)).replace("\\", "/")
            raise HTTPException(status_code=403, detail=f"Path not sanctioned: {rel}")

        # Load bindings
        try:
            with open(store_path, "r", encoding="utf-8") as f:
                document = json.load(f)
        except Exception as e:
            logger.error(f"[Shaders] Failed to read store: {e}")
            return {"success": False, "error": str(e), "removed_count": 0}

        bindings = document.get("bindings", [])
        original_count = len(bindings)

        if emulator:
            bindings = [
                b for b in bindings if not (b.get("game_id") == game_id and b.get("emulator") == emulator)
            ]
        else:
            bindings = [b for b in bindings if b.get("game_id") != game_id]

        removed_count = original_count - len(bindings)
        if removed_count == 0:
            return {
                "success": False,
                "error": "No shader binding found",
                "removed_count": 0,
            }

        # Backup store file
        backup_path = None
        if getattr(request.app.state, "backup_on_write", True):
            try:
                backup = create_backup(store_path, drive_root)
                backup_path = str(backup.relative_to(drive_root)).replace("\\", "/")
            except Exception:
                backup_path = None

        # Write updated store
        document["bindings"] = bindings
        with open(store_path, "w", encoding="utf-8") as f:
            json.dump(document, f, indent=2)

        try:
            audit_log_append(
                {
                    "scope": "shader",
                    "action": "delete",
                    "game_id": game_id,
                    "target_file": str(store_path.relative_to(drive_root)).replace("\\", "/"),
                    "backup_path": backup_path,
                    "panel": request.headers.get("x-panel"),
                    "device": request.headers.get("x-device-id"),
                    "emulator": emulator,
                    "removed_count": removed_count,
                }
            )
        except Exception:
            pass

        logger.info(
            f"[Shaders] Removed {removed_count} binding(s) for {game_id}{' ('+emulator+')' if emulator else ''} from store"
        )
        return {
            "success": True,
            "removed_count": removed_count,
            "game_id": game_id,
            "emulator": emulator,
            "backup_path": backup_path,
        }

    # Otherwise, operate on per-game file
    if sanctioned and not is_allowed_file(config_path, drive_root, sanctioned):
        rel = str(config_path.relative_to(drive_root)).replace("\\", "/")
        raise HTTPException(status_code=403, detail=f"Path not sanctioned: {rel}")
    if not config_path.exists():
        return {"success": False, "error": "not_found", "removed_count": 0}

    backup_path = None
    try:
        # If emulator filter provided, validate before deletion
        if emulator:
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    current = json.load(f)
                current_emulator = current.get("emulator")
                if current_emulator and current_emulator != emulator:
                    return {
                        "success": False,
                        "error": "emulator_mismatch",
                        "current_emulator": current_emulator,
                        "removed_count": 0,
                    }
            except Exception:
                # If we can't parse, proceed with deletion (defensive)
                pass

        # Backup existing config if configured
        if getattr(request.app.state, "backup_on_write", True):
            try:
                backup = create_backup(config_path, drive_root)
                backup_path = str(backup.relative_to(drive_root)).replace("\\", "/")
            except Exception:
                backup_path = None

        # Delete the config file
        try:
            config_path.unlink(missing_ok=False)
        except TypeError:
            # Python <3.8 compatibility (missing_ok not available)
            if config_path.exists():
                config_path.unlink()

        logger.info(f"[Shaders] Deleted shader binding for {game_id}")

        try:
            audit_log_append(
                {
                    "scope": "shader",
                    "action": "delete",
                    "game_id": game_id,
                    "target_file": str(config_path.relative_to(drive_root)).replace(
                        "\\", "/"
                    ),
                    "backup_path": backup_path,
                    "panel": request.headers.get("x-panel"),
                    "device": request.headers.get("x-device-id"),
                }
            )
        except Exception:
            pass

        return {
            "success": True,
            "removed_count": 1,
            "game_id": game_id,
            "emulator": emulator,
            "backup_path": backup_path,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Shaders] Failed to delete binding for {game_id}: {e}")
        return {"success": False, "error": str(e), "removed_count": 0}

@router.get("/games", response_model=Dict[str, Any])
@with_timeout(10.0)  # Timeout protection for XML parsing delays
async def get_games(
    platform: Optional[str] = Query(None, description="Filter by platform name (e.g., 'Arcade')"),
    genre: Optional[str] = Query(None, description="Filter by genre (e.g., 'Fighting')"),
    search: Optional[str] = Query(None, description="Search term for title, developer, or publisher"),
    year_min: Optional[int] = Query(None, description="Minimum release year (inclusive)"),
    year_max: Optional[int] = Query(None, description="Maximum release year (inclusive)"),
    sort_by: str = Query('title', description="Field to sort by (e.g., 'title', 'year')"),
    sort_order: str = Query('asc', description="Sort order ('asc' or 'desc')"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(50, ge=1, le=500, description="Number of games per page"),
    services: LaunchBoxServices = Depends(get_launchbox_services),
):
    """
    Get a paginated, filtered, and sorted list of games from the LaunchBox library.
    This endpoint is optimized for UI performance by handling all heavy lifting on the server side.
    """
    request_start = time.time()

    # Normalize platform synonyms
    if platform:
        try:
            platform = normalize_platform(platform)
        except Exception:
            pass

    # Use the new paginated method in the parser
    result = await run_in_threadpool(
        services.parser.get_paginated_games,
        platform=platform,
        genre=genre,
        search=search,
        year_min=year_min,
        year_max=year_max,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        limit=limit,
    )

    request_duration = (time.time() - request_start) * 1000
    logger.info(
        f"GET /games: Sent page {page} with {len(result['games'])}/{result['total']} games in {request_duration:.1f}ms "
        f"(platform={platform}, genre={genre}, search={search}, page={page})"
    )

    # Warn if slow (indicates XML cache miss or parser issue)
    if request_duration > 1000:
        logger.warning(
            f"Slow /games request ({request_duration:.0f}ms) - "
            "check XML cache initialization."
        )

    return result


@router.get("/games/{game_id}", response_model=Game)
async def get_game(game_id: str):
    """Get details for a specific game by ID."""
    # Offload potential first-use initialization to threadpool
    game = await run_in_threadpool(parser.get_game_by_id, game_id)

    if not game:
        # Return structured error response (not FastAPI default)
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": f"Game not found: {game_id}"
            }
        )

    return game


@router.get("/image/{game_id}")
async def get_game_image(game_id: str):
    """
    Serve game image with intelligent fallback.

    Priority order:
    1. Clear logo (best coverage, smaller files, consistent dimensions)
    2. Box front artwork
    3. Gameplay screenshot

    Also checks region subfolders for localized artwork.
    """
    from fastapi.responses import FileResponse
    from pathlib import Path
    import os

    # Fetch game data (cached, fast lookup)
    game = await run_in_threadpool(parser.get_game_by_id, game_id)

    if not game:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": f"Game not found: {game_id}"
            }
        )

    # Image priority (optimized: filter None values upfront)
    image_paths = [p for p in [
        game.clear_logo_path,
        game.box_front_path,
        game.screenshot_path
    ] if p]

    if not image_paths:
        logger.debug(f"No image paths configured for '{game.title}'")
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": f"No images configured for: {game.title}"
            }
        )

    # Region priority for international releases
    REGION_PRIORITIES = ["World", "North America", "USA", "Europe", "Japan", "Asia", "Australia"]

    # Efficient image search with early return
    import mimetypes
    for image_path in image_paths:
        # Check primary path
        if await run_in_threadpool(os.path.exists, image_path):
            logger.debug(f"Image found for '{game.title}': {image_path}")
            mt, _ = mimetypes.guess_type(str(image_path))
            return FileResponse(
                image_path,
                media_type=mt or "application/octet-stream",
                headers={
                    "Cache-Control": "public, max-age=86400",  # 24hr cache
                    "X-Game-Title": game.title  # Debug header
                }
            )

        # Check region variants (optimized path construction)
        path_obj = Path(image_path)
        parent = path_obj.parent
        filename = path_obj.name

        for region in REGION_PRIORITIES:
            region_path = parent / region / filename
            if await run_in_threadpool(region_path.exists):
                logger.debug(f"Regional image found for '{game.title}': {region_path}")
                mt, _ = mimetypes.guess_type(str(region_path))
                return FileResponse(
                    str(region_path),
                    media_type=mt or "application/octet-stream",
                    headers={
                        "Cache-Control": "public, max-age=86400",
                        "X-Game-Title": game.title,
                        "X-Region": region
                    }
                )

    # No image found after exhaustive search
    logger.debug(f"No image found for '{game.title}' after checking {len(image_paths)} paths with regions")
    return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "message": f"No image available for: {game.title}",
            "paths_checked": len(image_paths) * (1 + len(REGION_PRIORITIES))
        }
    )


@router.get("/platforms", response_model=List[str])
async def get_platforms():
    """Get list of all available platforms (cached)."""
    platforms = await run_in_threadpool(parser.get_platforms)
    logger.debug(f"Returning {len(platforms)} platforms")
    return platforms


@router.get("/platform-aliases", response_model=Dict[str, List[str]])
async def get_platform_aliases() -> Dict[str, List[str]]:
    platforms = await run_in_threadpool(parser.get_platforms)
    platform_set = {p for p in platforms if isinstance(p, str) and p.strip()}

    arcade_platforms = {
        "Arcade",
        "MAME",
        "Arcade MAME",
        "MAME Gun Games",
        "TeknoParrot Arcade",
        "TeknoParrot Gun Games",
        "Sega Model 2",
        "Sega Model 3",
        "Sega Naomi",
        "Model 2 Gun Games",
        "Model 3 Gun Games",
        "Naomi Gun Games",
        "Sammy Atomiswave",
        "Atomiswave Gun Games",
        "Taito Type X",
        "Daphne",
        "American Laser Games",
    }

    arcade_platforms_existing = {p for p in platform_set if p in arcade_platforms}

    def _take(pred):
        return sorted([p for p in platform_set if pred(p)])

    aliases: Dict[str, List[str]] = {
        "arcade": sorted(
            list(
                set(
                    _take(lambda p: p.lower() in {"arcade", "mame", "arcade mame"} or "arcade" in p.lower() or "mame" in p.lower())
                )
                | arcade_platforms_existing
            )
        ),
        "nintendo": _take(lambda p: any(k in p.lower() for k in ["nes", "snes", "nintendo", "game boy", "gba", "gbc", "gamecube", "wii", "switch", "n64"])),
        "playstation": _take(lambda p: any(k in p.lower() for k in ["playstation", "ps1", "ps2", "ps3", "ps4", "ps5", "psp", "vita"])),
        "sega": _take(lambda p: any(k in p.lower() for k in ["sega", "genesis", "mega drive", "saturn", "dreamcast", "game gear", "32x", "master system"])),
        "atari": _take(lambda p: any(k in p.lower() for k in ["atari", "2600", "5200", "7800", "lynx", "jaguar"])),
        "xbox": _take(lambda p: any(k in p.lower() for k in ["xbox"])),
        "pc": _take(lambda p: any(k in p.lower() for k in ["pc", "windows", "dos", "steam"])),
    }

    # Remove empty groups to keep response clean
    return {k: v for k, v in aliases.items() if v}


@router.get("/genres", response_model=List[str])
async def get_genres():
    """Get list of all available genres (cached)."""
    genres = await run_in_threadpool(parser.get_genres)
    logger.debug(f"Returning {len(genres)} genres")
    return genres


@router.get("/random", response_model=Game)
async def get_random_game(
    platform: Optional[str] = Query(None),
    genre: Optional[str] = Query(None),
    decade: Optional[int] = Query(None),
):
    """
    Get random game with optional filters.

    Use Case: "Surprise Me" button, random game night selector.
    """

    # Use threadpool for consistency and performance
    random_game = await run_in_threadpool(
        parser.get_random_game,
        platform=platform,
        genre=genre,
        decade=decade
    )

    if not random_game:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": f"No games match criteria (platform={platform}, genre={genre}, decade={decade})"
            }
        )

    logger.info(f"Random game selected: '{random_game.title}' (platform={platform}, genre={genre}, decade={decade})")

    return random_game


@router.post("/launch-by-title", response_model=LaunchResponse)
@with_timeout(30.0)
async def launch_by_title(
    payload: LaunchByTitleRequest,
    http_request: Request,
    services: LaunchBoxServices = Depends(get_launchbox_services),
):
    """
    Resolve a LaunchBox game by title (and optional collection/platform) then launch it.
    Intended for RetroFE bridge calls (aa_launch.bat).
    """
    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    normalized_title = _normalize_title(title)
    platform_filter = (payload.collection or "").strip().lower()

    caller_panel = (http_request.headers.get("x-panel") or "").strip().lower()
    if caller_panel not in {"launchbox", "retrofe", "pegasus"}:
        raise HTTPException(status_code=403, detail="Forbidden: launch-by-title allowed only from LaunchBox, RetroFE, or Pegasus")

    games = services.parser.get_all_games() or []
    if not games:
        raise HTTPException(status_code=404, detail="No games available in LaunchBox cache")

    # Diagnostic logging for launch-by-title debugging
    logger.info(f"[launch-by-title] Received: title='{title}', collection='{payload.collection}', panel='{caller_panel}'")
    logger.info(f"[launch-by-title] Normalized title: '{normalized_title}', platform_filter: '{platform_filter}'")
    logger.info(f"[launch-by-title] Total games in cache: {len(games)}")

    def _matches_platform(game: Game) -> bool:
        return bool(platform_filter) and isinstance(getattr(game, "platform", ""), str) and game.platform.lower() == platform_filter

    exact_in_platform = [g for g in games if _normalize_title(getattr(g, "title", "")) == normalized_title and (not platform_filter or _matches_platform(g))]
    
    # Log match results
    logger.info(f"[launch-by-title] Exact matches (with platform filter): {len(exact_in_platform)}")

    chosen: Optional[Game] = None
    if platform_filter:
        if len(exact_in_platform) == 1:
            chosen = exact_in_platform[0]
        elif len(exact_in_platform) > 1:
            raise HTTPException(
                status_code=400,
                detail=f"Multiple exact matches for '{title}' in platform '{payload.collection}'. Specify a unique title.",
            )

    if chosen is None:
        exact_all = [g for g in games if _normalize_title(getattr(g, "title", "")) == normalized_title]
        if len(exact_all) == 1:
            chosen = exact_all[0]
        elif len(exact_all) > 1:
            raise HTTPException(
                status_code=400,
                detail=f"Multiple exact matches for '{title}' across platforms; provide collection/platform to disambiguate.",
            )

    if chosen is None:
        # Best-effort fuzzy fallback to avoid hard failure
        fuzzy_matches = _find_fuzzy_matches(games, title, 0.9)
        if len(fuzzy_matches) == 1:
            chosen = fuzzy_matches[0][1]
        elif len(fuzzy_matches) > 1:
            raise HTTPException(
                status_code=400,
                detail=f"Title '{title}' is ambiguous; refine your request with collection/platform.",
            )

    if chosen is None:
        # Log diagnostic info to help debug why no match was found
        logger.warning(f"[launch-by-title] NO MATCH FOUND for title='{title}' (normalized='{normalized_title}')")
        logger.warning(f"[launch-by-title] Platform filter was: '{platform_filter}'")
        
        # Show some sample titles from the library for debugging
        sample_titles = [getattr(g, "title", "?") for g in games[:10]]
        logger.warning(f"[launch-by-title] Sample titles in library: {sample_titles}")
        
        # Check if there's a close match with different normalization
        close_matches = [g for g in games if title.lower() in getattr(g, "title", "").lower() or getattr(g, "title", "").lower() in title.lower()]
        if close_matches:
            close_titles = [getattr(g, "title", "?") for g in close_matches[:5]]
            logger.warning(f"[launch-by-title] Possible close matches: {close_titles}")
        
        raise HTTPException(status_code=404, detail=f"Game not found for title '{title}'")

    launch_req = LaunchRequest()
    # Pass original request to preserve x-panel header (pegasus, retrofe, launchbox)
    return await launch_game(chosen.id, http_request, launch_req, services)


@router.post("/launch/{game_id}", response_model=LaunchResponse)
@with_timeout(30.0)  # Longer timeout for launch operations (plugin + emulator startup)
async def launch_game(
    game_id: str,
    http_request: Request,
    request: Optional[LaunchRequest] = None,
    services: LaunchBoxServices = Depends(get_launchbox_services),
):
    # Guardrail: only LaunchBox, RetroFE, or Pegasus panels are allowed to launch games
    panel = (http_request.headers.get("x-panel") or "").lower()
    if panel not in {"launchbox", "retrofe", "pegasus"}:
        logger.warning(f"Forbidden launch attempt for game_id={game_id} from panel='{panel or 'unknown'}'")
        resp = LaunchResponse(
            success=False,
            message="Forbidden: game launches are allowed only from LaunchBox, RetroFE, or Pegasus panels",
            method_used="forbidden",
            game_id=game_id,
            game_title=""
        )
        # Log forbidden attempt
        try:
            decision = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "game_id": game_id,
                "game_title": None,
                "platform": None,
                "categories": [],
                "panel": panel,
                "requested_by": "manual",
                "launch_method": resp.method_used,
                "reason": resp.message,
            }
            log_decision(decision)
        except Exception:
            pass
        return resp

    # Optional throttle to avoid duplicate rapid launches
    # BYPASS: Pegasus panel never throttled (direct-to-emulator model requires 100% reliability)
    try:
        throttle_sec = int(os.getenv("AA_LAUNCH_THROTTLE_SEC", "5"))
    except Exception:
        throttle_sec = 5
    if throttle_sec > 0 and panel != "pegasus":
        THROTTLE_WINDOW = timedelta(seconds=throttle_sec)
        now = datetime.now(timezone.utc)
        key = f"{game_id}"
        last_map = getattr(launch_game, "_last_launch", {})
        last = last_map.get(key)  # Expect timezone-aware datetime
        # Only throttle when a prior launch occurred within the window
        if isinstance(last, datetime) and (now - last) < THROTTLE_WINDOW:
            remaining_td = THROTTLE_WINDOW - (now - last)
            remaining = int(math.ceil(max(0.0, remaining_td.total_seconds())))
            # Record attempt timestamp even when throttled
            if not hasattr(launch_game, "_last_launch"):
                launch_game._last_launch = {}
            launch_game._last_launch[key] = now
            resp = LaunchResponse(
                success=False,
                message=f"Please wait {remaining}s before launching again",
                method_used="throttled",
                game_id=game_id,
                game_title=""
            )
            try:
                decision = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "game_id": game_id,
                    "game_title": None,
                    "platform": None,
                    "categories": [],
                    "panel": panel,
                    "requested_by": "manual",
                    "launch_method": resp.method_used,
                    "reason": resp.message,
                }
                log_decision(decision)
            except Exception:
                pass
            return resp
        # Record timestamp for this launch attempt when not throttled
        if not hasattr(launch_game, "_last_launch"):
            launch_game._last_launch = {}
        launch_game._last_launch[key] = now

    # Correlation ID for tracing (optional header)
    corr = http_request.headers.get("x-corr-id") or ""
    if corr:
        logger.info(f"corr={corr} requested launch for game_id={game_id}")
    """
    Launch game by ID using plugin-first architecture.

    Architecture:
    1. Check for mock mode and return error if true
    2. Try C# Plugin Bridge (primary method - uses LaunchBox's native launch)
    3. Fallback to launcher service methods if plugin unavailable

    Returns: LaunchResponse with success status and method used.
    """

    # Check if in mock mode (optimized: single cache stat call)
    stats = await run_in_threadpool(parser.get_cache_stats)
    if stats.get("is_mock_data", False):
        logger.warning(f"Launch rejected in mock mode for game_id: {game_id}")
        resp = LaunchResponse(
            success=False,
            game_id=game_id,
            method_used="none",
            message="Cannot launch in mock mode. Set AA_DRIVE_ROOT to A:\\ in .env file",
            game_title=None
        )
        try:
            decision = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "game_id": game_id,
                "game_title": None,
                "platform": None,
                "categories": [],
                "panel": panel,
                "requested_by": "manual",
                "launch_method": resp.method_used,
                "reason": resp.message,
            }
            log_decision(decision)
        except Exception:
            pass
        return resp

    # Fetch game (with threadpool for potential lazy initialization)
    game = await run_in_threadpool(parser.get_game_by_id, game_id)
    if not game:
        logger.error(f"Game not found for launch: {game_id}")
        resp = LaunchResponse(
            success=False,
            game_id=game_id,
            method_used="none",
            message=f"Game not found: {game_id}",
            game_title=None
        )
        try:
            decision = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "game_id": game_id,
                "game_title": None,
                "platform": None,
                "categories": [],
                "panel": panel,
                "requested_by": "manual",
                "launch_method": resp.method_used,
                "reason": resp.message,
            }
            log_decision(decision)
        except Exception:
            pass
        return resp
    # AHK script safety guard:
    # Some LaunchBox entries use ApplicationPath .ahk launchers.
    # A second launch while the first script is active can trigger AutoHotkey's
    # "older instance already running" prompt. Apply a short per-game cooldown
    # specifically for .ahk-backed launches.
    try:
        ahk_cooldown_sec = int(os.getenv("AA_AHK_LAUNCH_COOLDOWN_SEC", "20"))
    except Exception:
        ahk_cooldown_sec = 20

    app_path_raw = str(getattr(game, "application_path", "") or "").strip().lower()
    is_ahk_launcher = app_path_raw.endswith(".ahk")
    if ahk_cooldown_sec > 0 and panel != "pegasus" and is_ahk_launcher:
        AHK_COOLDOWN = timedelta(seconds=ahk_cooldown_sec)
        now = datetime.now(timezone.utc)
        if not hasattr(launch_game, "_last_ahk_launch"):
            launch_game._last_ahk_launch = {}
        ahk_map = getattr(launch_game, "_last_ahk_launch", {})
        last_ahk = ahk_map.get(game_id)
        if isinstance(last_ahk, datetime) and (now - last_ahk) < AHK_COOLDOWN:
            remaining_td = AHK_COOLDOWN - (now - last_ahk)
            remaining = int(math.ceil(max(0.0, remaining_td.total_seconds())))
            resp = LaunchResponse(
                success=False,
                message=f"Launch script already active. Please wait {remaining}s before relaunching.",
                method_used="ahk_cooldown",
                game_id=game_id,
                game_title=game.title
            )
            try:
                decision = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "game_id": game.id,
                    "game_title": game.title,
                    "platform": game.platform,
                    "categories": game.categories or [],
                    "panel": panel,
                    "requested_by": "manual",
                    "launch_method": resp.method_used,
                    "reason": resp.message,
                }
                log_decision(decision)
            except Exception:
                pass
            return resp
        launch_game._last_ahk_launch[game_id] = now


    # In-flight single-flight guard (prevents concurrent duplicate launches)
    # BYPASS: Pegasus panel never blocked by inflight (direct-to-emulator model)
    try:
        inflight_ttl = int(os.getenv("AA_LAUNCH_INFLIGHT_TTL_SEC", "5"))
    except Exception:
        inflight_ttl = 5
    now = datetime.now(timezone.utc)
    if not hasattr(launch_game, "_inflight"):
        launch_game._inflight = {}
    # Cleanup stale
    try:
        stale_keys = []
        for k, ts in getattr(launch_game, "_inflight", {}).items():
            if isinstance(ts, datetime) and (now - ts) > timedelta(seconds=inflight_ttl):
                stale_keys.append(k)
        for k in stale_keys:
            del launch_game._inflight[k]
    except Exception:
        pass
    # Only apply inflight guard for non-Pegasus panels
    if panel != "pegasus" and getattr(launch_game, "_inflight", {}).get(game_id):
        resp = LaunchResponse(
            success=False,
            message="Launch already in progress",
            method_used="inflight",
            game_id=game_id,
            game_title=game.title
        )
        try:
            decision = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "game_id": game.id,
                "game_title": game.title,
                "platform": game.platform,
                "categories": game.categories or [],
                "panel": (http_request.headers.get("x-panel") or ""),
                "requested_by": "lora_direct",
                "launch_method": resp.method_used,
                "emulator_detected": None,
                "profile_used": None,
                "adapter_path": None,
                "ahk_wrapper_applied": False,
                "policy_flags": {},
                "reason": resp.message,
            }
            log_decision(decision)
        except Exception:
            pass
        return resp
    # Mark inflight for this game id
    try:
        launch_game._inflight[game_id] = now
    except Exception:
        pass

    # Apply any bound LED profile before the emulator launches (best-effort)
    try:
        await _apply_led_profile_binding_for_launch(http_request, game)
    except Exception:
        # LED preparation errors should never block a launch
        logger.debug("LED launch hook skipped for %s", game_id, exc_info=True)

    # Generate controller config for this game's platform (best-effort)
    # This ensures MAME/TeknoParrot have correct button mappings before launch
    try:
        await _ensure_controller_config_for_game(http_request, game)
    except Exception:
        # Controller config errors should never block a launch
        logger.debug("Controller config hook skipped for %s", game_id, exc_info=True)


    # Update marquee display with current game (for MarqueeDisplayV2 polling)
    # Use persist_preview_game with mode="video" to trigger video playback
    try:
        region = getattr(game, "region", None) or "North America"
        marquee_router.persist_preview_game({
            "game_id": game.id,
            "title": game.title,
            "platform": game.platform or "Arcade",
            "region": region,
        }, mode="video")
        # Also update current_game for legacy compatibility
        marquee_router.persist_current_game({
            "game_id": game.id,
            "title": game.title,
            "platform": game.platform or "Arcade",
            "region": region,
        })
        logger.debug("Marquee state updated for %s (video mode)", game.title)
    except Exception:
        logger.debug("Marquee hook skipped for %s", game_id, exc_info=True)

    # Determine effective profile hint
    profile_hint: Optional[str] = None
    try:
        if request and getattr(request, 'profile_hint', None):
            profile_hint = request.profile_hint
        # Panel-level implication: Light Guns panel implies lightgun profile
        if not profile_hint:
            panel_name = (http_request.headers.get("x-panel") or "").strip().lower()
            if panel_name in {"light guns", "lightguns", "light-guns"}:
                profile_hint = "lightgun"
        # Category-level implication: Category contains 'Light Gun'
        if not profile_hint and getattr(game, 'categories', None):
            cats = [c.lower() for c in (game.categories or [])]
            if any("light gun" in c or "lightgun" in c for c in cats):
                profile_hint = "lightgun"
    except Exception:
        profile_hint = profile_hint or None

    # Launch policy: default to direct-only per project decision
    # Values: direct_only | plugin_first
    # 
    # ARCHITECTURE (2025-12-11): Direct-to-Emulator Model
    # ====================================================
    # Pegasus (or any frontend) -> Arcade Assistant -> Emulator
    # LaunchBox is NOT part of the runtime launch chain.
    # Pegasus ALWAYS uses direct_only with NO LaunchBox fallback.
    try:
        policy_mode = (os.getenv("AA_LAUNCH_POLICY", "direct_only") or "").strip().lower()
    except Exception:
        policy_mode = "direct_only"
    
    # Pegasus: FORCE direct_only - never use LaunchBox plugin
    if panel == "pegasus":
        policy_mode = "direct_only"
        logger.info(f"[PEGASUS] Direct-to-emulator launch for '{game.title}' (platform={game.platform})")
    # LaunchBox LoRa should behave like native LaunchBox whenever plugin is available.
    elif panel == "launchbox":
        policy_mode = "plugin_first"

    # Policy-based forced launch method (per-game/platform/title overrides)
    try:
        policy = _read_routing_policy() or {}
        force = (policy.get("force_launch_method") or {}) if isinstance(policy, dict) else {}
        forced_method: Optional[str] = None
        # by_game_id (exact)
        by_id = (force.get("by_game_id") or {}) if isinstance(force, dict) else {}
        if isinstance(by_id, dict) and game_id in by_id:
            forced_method = str(by_id.get(game_id) or "").strip().lower() or None
        # by_platform (exact string match)
        if not forced_method:
            by_plat = (force.get("by_platform") or {}) if isinstance(force, dict) else {}
            plat = getattr(game, 'platform', None)
            if isinstance(by_plat, dict) and isinstance(plat, str) and plat in by_plat:
                forced_method = str(by_plat.get(plat) or "").strip().lower() or None
        # by_title (case-insensitive exact)
        if not forced_method:
            by_title = (force.get("by_title") or {}) if isinstance(force, dict) else {}
            title = getattr(game, 'title', None)
            if isinstance(by_title, dict) and isinstance(title, str):
                # Normalize keys once for a tolerant lookup
                tnorm = title.strip().lower()
                for k, v in by_title.items():
                    try:
                        if isinstance(k, str) and tnorm == k.strip().lower():
                            forced_method = str(v or "").strip().lower() or None
                            break
                    except Exception:
                        continue
        if forced_method in {"plugin", "detected_emulator", "direct", "launchbox"}:
            result = await run_in_threadpool(launcher.launch, game, forced_method, profile_hint)
            result.game_title = game.title
            try:
                exe_path, emulator_name, profile_used = _parse_command_info(getattr(result, 'command', None))
                decision = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "game_id": game.id,
                    "game_title": game.title,
                    "platform": game.platform,
                    "categories": game.categories or [],
                    "panel": panel,
                    "requested_by": "policy_forced",
                    "launch_method": result.method_used,
                    "emulator_detected": emulator_name,
                    "profile_used": profile_used or ("lightgun" if (profile_hint == "lightgun") else None),
                    "adapter_path": exe_path,
                    "ahk_wrapper_applied": False,
                    "policy_flags": {"force_method": forced_method},
                    "reason": f"Forced by routing-policy for game/platform/title",
                }
                log_decision(decision)
            except Exception:
                pass
            try:
                _log_launch_event(http_request, game, result)
            except Exception:
                pass

            # Best-effort PID tracking for non-plugin launches (enables vision capture on exit)
            try:
                exe_path, emulator_name, _ = _parse_command_info(getattr(result, 'command', None))
                pid = _best_effort_find_pid(exe_path)
                if pid:
                    from backend.services.game_lifecycle import track_game_launch

                    track_game_launch(
                        game_id=game.id,
                        game_title=game.title,
                        platform=game.platform,
                        pid=pid,
                        emulator=emulator_name,
                    )
            except Exception:
                pass
            return result
    except Exception:
        # Ignore policy errors and continue with normal flow
        pass
    if policy_mode == "direct_only":
        try:
            direct_result = await run_in_threadpool(launcher.launch, game, 'direct', profile_hint)
            if direct_result and getattr(direct_result, 'success', False):
                direct_result.game_title = game.title
                logger.info(f"Direct-only launch succeeded for '{game.title}'")
                try:
                    _log_launch_event(http_request, game, direct_result)
                except Exception:
                    pass

                # Best-effort PID tracking (enables vision capture on exit for non-MAME)
                try:
                    exe_path, emulator_name, _ = _parse_command_info(getattr(direct_result, 'command', None))
                    pid = _best_effort_find_pid(exe_path)
                    if pid:
                        from backend.services.game_lifecycle import track_game_launch

                        track_game_launch(
                            game_id=game.id,
                            game_title=game.title,
                            platform=game.platform,
                            pid=pid,
                            emulator=emulator_name,
                        )
                except Exception:
                    pass
                return direct_result
            else:
                # PEGASUS: Never fall back to LaunchBox - return explicit failure
                if panel == "pegasus":
                    failure_msg = getattr(direct_result, 'message', 'Unknown error') if direct_result else 'No adapter claimed this platform'
                    logger.error(f"[PEGASUS] Direct launch FAILED for '{game.title}': {failure_msg}")
                    logger.error(f"[PEGASUS] Diagnostics - platform={game.platform}, rom_path={getattr(game, 'rom_path', None)}, app_path={getattr(game, 'application_path', None)}")
                    resp = LaunchResponse(
                        success=False,
                        game_id=game.id,
                        game_title=game.title,
                        method_used="direct_failed",
                        message=f"Direct launch failed: {failure_msg}. Platform: {game.platform}",
                        error=failure_msg
                    )
                    try:
                        log_decision({
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "game_id": game.id,
                            "game_title": game.title,
                            "platform": game.platform,
                            "categories": game.categories or [],
                            "panel": panel,
                            "requested_by": "pegasus_direct",
                            "launch_method": "direct_failed",
                            "reason": failure_msg,
                        })
                    except Exception:
                        pass
                    return resp
                # Non-Pegasus: try detected_emulator fallback
                logger.info(f"Direct-only path did not claim '{game.title}', trying detected_emulator")
                result = await run_in_threadpool(launcher.launch, game, 'detected_emulator', profile_hint)
                result.game_title = game.title
                try:
                    _log_launch_event(http_request, game, result)
                except Exception:
                    pass
                if getattr(result, "success", False):
                    return result
                logger.warning(
                    "Detected emulator fallback failed for '%s' (%s), continuing to plugin/fallback chain",
                    game.title,
                    getattr(result, "message", "no message"),
                )
        except Exception as e:
            logger.warning(f"Direct-only failed for '{game.title}': {e}")
            # PEGASUS: Return explicit failure, never fall through to LaunchBox
            if panel == "pegasus":
                logger.error(f"[PEGASUS] Exception during direct launch for '{game.title}': {e}")
                resp = LaunchResponse(
                    success=False,
                    game_id=game.id,
                    game_title=game.title,
                    method_used="direct_exception",
                    message=f"Direct launch exception: {str(e)}",
                    error=str(e)
                )
                return resp

    # Try plugin method first (primary launch strategy)
    plugin_client = get_plugin_client()
    try:
        if plugin_client.is_available():
            logger.info(f"Launching '{game.title}' via plugin bridge...")
            result = await run_in_threadpool(plugin_client.launch_game, game_id)

            if result.get("success"):
                resp = LaunchResponse(
                    success=True,
                    message=result.get("message", "Game launched successfully"),
                    method_used="plugin_bridge",
                    game_id=game_id,
                    game_title=game.title,
                    command=None  # No command for plugin method
                )
                # Log success via plugin bridge
                try:
                    policy = _read_routing_policy()
                    decision = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "game_id": game.id,
                        "game_title": game.title,
                        "platform": game.platform,
                        "categories": game.categories or [],
                        "panel": panel,
                        "requested_by": "launchbox_plugin",
                        "launch_method": resp.method_used,
                        "emulator_detected": None,
                        "profile_used": None,
                        "adapter_path": None,
                        "ahk_wrapper_applied": False,
                        "policy_flags": {
                            "AA_ALLOW_DIRECT_TEKNOPARROT": os.getenv("AA_ALLOW_DIRECT_TEKNOPARROT", "false"),
                            "lightgun.ahk_wrapper": ((policy.get("profiles", {}) or {}).get("lightgun", {}) or {}).get("ahk_wrapper", None),
                        },
                        "reason": result.get("message") or "plugin bridge",
                    }
                    log_decision(decision)
                except Exception:
                    pass
                try:
                    _log_launch_event(http_request, game, resp)
                except Exception:
                    pass

                # Update runtime state (in-game)
                try:
                    drive_root = getattr(http_request.app.state, "drive_root", None)
                    update_runtime_state({
                        "frontend": panel or "launchbox",
                        "mode": "in_game",
                        "system_id": game.platform,
                        "game_title": game.title,
                        "game_id": game.id,
                        "player": None,
                        "elapsed_seconds": None,
                    }, drive_root)
                except Exception:
                    pass
                return resp
            else:
                logger.warning(f"Plugin launch failed for '{game.title}': {result.get('message')}")
                # Continue to fallback
        else:
            logger.info("Plugin not available, using fallback launcher...")
    except LaunchBoxPluginError as e:
        logger.error(f"Plugin error for '{game.title}': {e}")
        # Continue to fallback
    except Exception as e:
        logger.error(f"Unexpected plugin error for '{game.title}': {e}", exc_info=True)
        # Continue to fallback

    # Fallback to launcher service
    try:
        force_method = request.force_method if request else None
        result = await run_in_threadpool(
            launcher.launch,
            game,
            force_method,
            profile_hint
        )

        logger.info(
            f"Launch result for '{game.title}': {result.method_used} "
            f"({'SUCCESS' if result.success else 'FAILED'})"
        )

        # Update result with game title for consistency
        result.game_title = game.title

        # Log routing decision with best-effort metadata
        try:
            exe_path, emulator_name, profile_used = _parse_command_info(result.command)
            policy = _read_routing_policy()
            # Infer wrapper from command for TeknoParrot direct
            ahk_applied = bool(result.command and (".ahk" in result.command.lower() or "&&" in result.command))
            decision = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "game_id": game.id,
                "game_title": game.title,
                "platform": game.platform,
                "categories": game.categories or [],
                "panel": panel,
                "requested_by": ("launchbox_plugin" if result.method_used == "plugin_bridge" else "lora_direct"),
                "launch_method": result.method_used,
                "emulator_detected": emulator_name,
                "profile_used": profile_used or ("lightgun" if (profile_hint == "lightgun") else None),
                "adapter_path": exe_path,
                "ahk_wrapper_applied": ahk_applied,
                "policy_flags": {
                    "AA_ALLOW_DIRECT_TEKNOPARROT": os.getenv("AA_ALLOW_DIRECT_TEKNOPARROT", "false"),
                    "lightgun.ahk_wrapper": ((policy.get("profiles", {}) or {}).get("lightgun", {}) or {}).get("ahk_wrapper", None),
                },
                "reason": result.message,
            }
            log_decision(decision)
        except Exception:
            pass

        try:
            _log_launch_event(http_request, game, result)
        except Exception:
            pass

        # Update runtime state on success
        try:
            if getattr(result, "success", False):
                drive_root = getattr(http_request.app.state, "drive_root", None)
                update_runtime_state({
                    "frontend": panel or "launchbox",
                    "mode": "in_game",
                    "system_id": game.platform,
                    "game_title": game.title,
                    "game_id": game.id,
                    "player": None,
                    "elapsed_seconds": None,
                }, drive_root)
        except Exception:
            pass
        return result

    except Exception as e:
        logger.error(f"Launch failed for '{game.title}': {e}", exc_info=True)
        resp = LaunchResponse(
            success=False,
            game_id=game_id,
            method_used="none",
            message=f"Launch failed: {str(e)}",
            game_title=game.title
        )
        try:
            policy = _read_routing_policy()
            decision = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "game_id": game.id,
                "game_title": game.title,
                "platform": game.platform,
                "categories": game.categories or [],
                "panel": panel,
                "requested_by": "lora_direct",
                "launch_method": resp.method_used,
                "emulator_detected": None,
                "profile_used": None,
                "adapter_path": None,
                "ahk_wrapper_applied": False,
                "policy_flags": {
                    "AA_ALLOW_DIRECT_TEKNOPARROT": os.getenv("AA_ALLOW_DIRECT_TEKNOPARROT", "false"),
                    "lightgun.ahk_wrapper": ((policy.get("profiles", {}) or {}).get("lightgun", {}) or {}).get("ahk_wrapper", None),
                },
                "reason": resp.message,
            }
            log_decision(decision)
        except Exception:
            pass
        return resp
    finally:
        # Clear inflight marker
        try:
            if hasattr(launch_game, "_inflight") and game_id in launch_game._inflight:
                del launch_game._inflight[game_id]
        except Exception:
            pass

@router.get("/plugin-status")
async def get_plugin_status():
    """
    Check C# plugin bridge availability.

    Returns plugin connectivity status for diagnostic purposes.
    """
    plugin_client = get_plugin_client()
    is_available = await run_in_threadpool(plugin_client.is_available)

    return {
        "available": is_available,
        "url": plugin_client.base_url,
        "message": "Plugin bridge operational" if is_available else "Plugin bridge offline - fallback methods will be used",
        "timeout": plugin_client.timeout
    }


@router.get("/diagnostics/dry-run")
async def get_dry_run_and_direct_status():
    """
    Quick diagnostics for adapter dry-run and direct launch readiness.

    Returns flags from environment and config/launchers.json so we can
    quickly see why console launches may not be executing.
    """
    # Dry-run status
    dry = dry_run_enabled()

    # Plugin availability (cached)
    plugin_client = get_plugin_client()
    plugin_ok = await run_in_threadpool(plugin_client.is_available)

    # Load manifest toggles
    manifest = GameLauncher._load_launchers_config() or {}
    gblock = (manifest.get("global") or {}) if isinstance(manifest, dict) else {}
    allow_cfg = {
        "allow_direct_emulator": bool(gblock.get("allow_direct_emulator")),
        "allow_direct_mame": bool(gblock.get("allow_direct_mame")),
        "allow_direct_retroarch": bool(gblock.get("allow_direct_retroarch")),
        "allow_direct_redream": bool(gblock.get("allow_direct_redream")),
        "allow_direct_pcsx2": bool(gblock.get("allow_direct_pcsx2")),
        "allow_direct_rpcs3": bool(gblock.get("allow_direct_rpcs3")),
        "allow_direct_teknoparrot": bool(gblock.get("allow_direct_teknoparrot")),
        "allow_direct_cemu": bool(gblock.get("allow_direct_cemu")),
        "allow_direct_model2": bool(gblock.get("allow_direct_model2")),
    }

    # Env toggles
    def _envb(name: str) -> bool:
        try:
            return str(os.getenv(name, "false")).lower() in {"1", "true", "yes"}
        except Exception:
            return False

    allow_env = {
        "AA_ALLOW_DIRECT_EMULATOR": _envb("AA_ALLOW_DIRECT_EMULATOR"),
        "AA_ALLOW_DIRECT_MAME": _envb("AA_ALLOW_DIRECT_MAME"),
        "AA_ALLOW_DIRECT_RETROARCH": _envb("AA_ALLOW_DIRECT_RETROARCH"),
        "AA_ALLOW_DIRECT_REDREAM": _envb("AA_ALLOW_DIRECT_REDREAM"),
        "AA_ALLOW_DIRECT_PCSX2": _envb("AA_ALLOW_DIRECT_PCSX2"),
        "AA_ALLOW_DIRECT_RPCS3": _envb("AA_ALLOW_DIRECT_RPCS3"),
        "AA_ALLOW_DIRECT_TEKNOPARROT": _envb("AA_ALLOW_DIRECT_TEKNOPARROT"),
        "AA_ALLOW_DIRECT_CEMU": _envb("AA_ALLOW_DIRECT_CEMU"),
        "AA_ALLOW_DIRECT_MODEL2": _envb("AA_ALLOW_DIRECT_MODEL2"),
    }

    # RetroArch presence + Atari 2600 mapping check
    retroarch = {"exe": None, "exe_exists": False, "core_key": None, "core": None, "core_exists": False}
    try:
        emu = None
        for key in ("emulators", "launchers"):
            block = manifest.get(key)
            if isinstance(block, dict) and isinstance(block.get("retroarch"), dict):
                emu = block.get("retroarch")
                break
        if not emu and isinstance(manifest.get("retroarch"), dict):
            emu = manifest.get("retroarch")
        if isinstance(emu, dict):
            exe = emu.get("exe")
            retroarch["exe"] = exe
            if isinstance(exe, str) and exe:
                from pathlib import Path
                p = Path(exe)
                if not p.exists() and exe.upper().startswith('A:') and os.name != 'nt':
                    p = Path(exe.replace('\\', '/').replace('A:', '/mnt/a'))
                retroarch["exe_exists"] = p.exists()
            plat_map = (emu.get("platform_map") or {})
            core_key = plat_map.get("Atari 2600")
            retroarch["core_key"] = core_key
            if isinstance(core_key, str):
                core_rel = (emu.get("cores") or {}).get(core_key)
                retroarch["core"] = core_rel
                if core_rel and isinstance(exe, str):
                    from pathlib import Path
                    exe_p = Path(exe)
                    core_path = Path(core_rel)
                    if not core_path.is_absolute():
                        cand = exe_p.parent / core_rel
                        if not cand.exists():
                            cand = exe_p.parent / "cores" / core_rel
                        core_path = cand
                    retroarch["core_exists"] = core_path.exists()
    except Exception:
        pass
    # Configured emulator executable presence map (clone-readiness visibility)
    emulator_paths: Dict[str, Dict[str, Any]] = {}
    try:
        emulators_block = {}
        for key in ("emulators", "launchers"):
            block = manifest.get(key)
            if isinstance(block, dict):
                emulators_block = block
                break
        if not emulators_block and isinstance(manifest, dict):
            emulators_block = manifest

        for emu_name, emu_cfg in emulators_block.items():
            if not isinstance(emu_cfg, dict):
                continue
            exe_val = emu_cfg.get("exe")
            exists = False
            resolved = None
            if isinstance(exe_val, str) and exe_val.strip():
                p = Path(exe_val)
                if not p.exists() and exe_val.upper().startswith("A:") and os.name != "nt":
                    p = Path(exe_val.replace("\\", "/").replace("A:", "/mnt/a"))
                exists = p.exists()
                resolved = str(p)
            emulator_paths[str(emu_name)] = {
                "exe": exe_val,
                "resolved_path": resolved,
                "exists": exists,
            }
    except Exception:
        pass
    # Direct health from launcher
    try:
        direct_ok = await run_in_threadpool(launcher._direct_is_healthy)
    except Exception:
        direct_ok = False

    return {
        "dry_run_enabled": dry,
        "plugin_available": plugin_ok,
        "allow_direct_env": allow_env,
        "allow_direct_config": allow_cfg,
        "allow_direct_effective": bool(any(allow_env.values()) or any(allow_cfg.values())),
        "emulator_paths": emulator_paths,
        "direct_is_healthy": direct_ok,
        "retroarch": retroarch,
    }

@router.post("/diagnostics/emulators/redetect")
async def redetect_emulators():
    """Force re-detection of emulator configs from LaunchBox Emulators.xml.

    Fixes stale configs (e.g., wrong paths like C:\\mnt\\a\\...).
    """
    from backend.services.emulator_detector import EmulatorDetector
    cfg = await run_in_threadpool(EmulatorDetector.force_redetect)
    if not cfg:
        return {"success": False, "message": "redetect failed"}
    try:
        launcher.emulator_config = cfg
        return {
            "success": True,
            "emulators": len(cfg.emulators or {}),
            "platform_mappings": len(cfg.platform_mappings or []),
            "launchbox_root": cfg.launchbox_root,
        }
    except Exception as e:
        return {"success": False, "message": str(e)}

@router.get("/stats", response_model=GameCacheStats)
async def get_cache_stats():
    """
    Get cache statistics for debugging.

    Returns: Total games, platforms, genres, last update time, mock data flag.
    """
    stats = parser.get_cache_stats()

    return GameCacheStats(
        total_games=stats["total_games"],
        platforms_count=stats["platforms_count"],
        genres_count=stats["genres_count"],
        xml_files_parsed=stats["xml_files_parsed"],
        last_updated=None,  # Will parse datetime if needed
        is_mock_data=stats["is_mock_data"],
        a_drive_status=stats["a_drive_status"],
    )


# -----------------------------------------------------------------------------
# Adapter diagnostics
# -----------------------------------------------------------------------------
@router.get("/diagnostics/adapters")
async def list_adapters() -> List[Dict[str, Any]]:
    from backend.services.launcher_registry import ADAPTER_STATUS
    from backend.services.adapters.adapter_utils import PREFS, find_emulator_exe

    def _get_emu_block(manifest_obj: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
        alias_map = {
            "daphne": ["daphne", "hypseus"],
            "hypseus": ["hypseus", "daphne"],
            "direct_app": [],
        }
        aliases = alias_map.get(key, [key])
        for root_key in ("emulators", "launchers"):
            block = manifest_obj.get(root_key)
            if not isinstance(block, dict):
                continue
            for alias in aliases:
                cfg = block.get(alias)
                if isinstance(cfg, dict):
                    return cfg
        if isinstance(manifest_obj, dict):
            for alias in aliases:
                cfg = manifest_obj.get(alias)
                if isinstance(cfg, dict):
                    return cfg
        return None

    def _resolve_cfg_exe(manifest_obj: Dict[str, Any], key: str) -> Tuple[Optional[str], bool]:
        cfg = _get_emu_block(manifest_obj, key)
        if not cfg:
            return None, False
        exe_raw = cfg.get("exe")
        if not isinstance(exe_raw, str) or not exe_raw.strip():
            return None, False
        p = Path(exe_raw)
        if not p.exists() and exe_raw.upper().startswith("A:") and os.name != "nt":
            p = Path(exe_raw.replace("\\", "/").replace("A:", "/mnt/a"))
        return exe_raw, p.exists()

    items: List[Dict[str, Any]] = []
    manifest = GameLauncher._load_launchers_config() or {}
    adapter_keys = list((ADAPTER_STATUS or {}).keys())

    for key in adapter_keys:
        exts = PREFS.get(key, [])
        exe_hint = {
            "duckstation": "duckstation",
            "dolphin": "dolphin",
            "flycast": "flycast",
            "model2": "model 2",
            "supermodel": "supermodel",
            "retroarch": "retroarch",
            "redream": "redream",
            "pcsx2": "pcsx2",
            "rpcs3": "rpcs3",
            "teknoparrot": "teknoparrot",
            "cemu": "cemu",
            "hypseus": "hypseus",
            "daphne": "daphne",
        }.get(key, key)

        configured_exe, configured_exists = _resolve_cfg_exe(manifest, key)
        discovered = find_emulator_exe(exe_hint)
        discovered_exists = bool(discovered and discovered.exists())
        emulator_required = key not in {"direct_app"}
        emulator_found = True if not emulator_required else bool(configured_exists or discovered_exists)

        items.append({
            "adapter": key,
            "enabled": True,
            "platform_keys": {
                "duckstation": ["sony playstation"],
                "dolphin": ["nintendo gamecube", "nintendo wii"],
                "flycast": ["sega naomi", "sammy atomiswave", "sega dreamcast (fallback)"],
                "model2": ["sega model 2"],
                "supermodel": ["sega model 3"],
                "rpcs3": ["sony playstation 3", "ps3"],
                "teknoparrot": ["teknoparrot arcade", "taito type x"],
                "daphne": ["daphne", "laserdisc"],
                "hypseus": ["daphne", "laserdisc"],
            }.get(key, []),
            "accepted_exts": exts,
            "configured_exe": configured_exe,
            "configured_exe_exists": configured_exists,
            "discovered_exe": str(discovered) if discovered else None,
            "discovered_exe_exists": discovered_exists,
            "emulator_required": emulator_required,
            "emulator_found": emulator_found,
        })

    return items


@router.get("/diagnostics/claim")
async def claim_adapter(game_id: str) -> Dict[str, Any]:
    from backend.services.launcher_registry import REGISTERED
    game = parser.get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "game not found"}
    manifest = GameLauncher._load_launchers_config() or {}
    claimants: List[Dict[str, Any]] = []
    selected = None
    for mod in REGISTERED:
        try:
            ok, reason = mod.can_handle(game, manifest, return_reason=True)
        except TypeError:
            ok = bool(mod.can_handle(game, manifest))
            reason = ""
        mod_name = getattr(mod, "__name__", "")
        leaf = mod_name.split(".")[-1]
        name = leaf[:-8] if leaf.endswith("_adapter") else leaf
        claimants.append({"adapter": name, "ok": bool(ok), "reason": reason})
        if ok and selected is None:
            selected = name
    # platform key
    from backend.services.platform_names import normalize_key
    platform_key = normalize_key(game.platform or "")
    direct_builtin = None
    if platform_key in {"arcade", "arcade mame", "mame"}:
        direct_builtin = "mame"
    return {
        "success": True,
        "platform_key": platform_key,
        "claimants": claimants,
        "selected_adapter": selected,
        "direct_builtin": direct_builtin,
    }


@router.get("/diagnostics/resolve")
async def resolve_adapter_config(game_id: str, adapter: str) -> Dict[str, Any]:
    """Return the adapter-provided config (exe|args|cwd) for a given game.

    This does not spawn processes; it just runs the adapter.resolve().
    """
    from backend.services.launcher_registry import REGISTERED
    game = parser.get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "game not found"}
    manifest = GameLauncher._load_launchers_config() or {}
    target = (adapter or '').strip().lower()
    mod = None
    for m in REGISTERED:
        mod_name = getattr(m, "__name__", "")
        leaf = mod_name.split(".")[-1]
        name = leaf[:-8] if leaf.endswith("_adapter") else leaf
        if name.lower() == target:
            mod = m
            break
    if not mod:
        return {"success": False, "message": f"adapter not found: {adapter}"}
    try:
        cfg = mod.resolve(game, manifest) or {}
        return {"success": bool(cfg.get('exe')), "cfg": cfg}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/images/stats")
async def get_image_scanner_stats():
    """
    Get image scanner statistics for monitoring and debugging.

    Returns detailed statistics about the image cache including:
    - Total images scanned
    - Images per platform
    - Scan duration
    - Memory usage
    - Fuzzy matching threshold
    - Cache source (disk or memory_scan)
    - Cache file information
    """
    stats = image_scanner.get_cache_stats()

    return {
        "platforms_scanned": stats.get("platforms_scanned", 0),
        "total_images": stats.get("images_found", 0),
        "scan_duration_seconds": stats.get("scan_duration", 0),
        "cache_memory_mb": stats.get("cache_memory_mb", 0),
        "cache_source": stats.get("cache_source", "unknown"),
        "loaded_from_disk": stats.get("loaded_from_disk", False),
        "cache_file_exists": stats.get("cache_file_exists", False),
        "cache_file_size_mb": stats.get("cache_file_size_mb", 0),
        "cache_max_age_days": stats.get("cache_max_age_days", 7),
        "fuzzy_threshold": stats.get("fuzzy_threshold", 0.85),
        "is_initialized": stats.get("is_initialized", False),
        "last_scan": stats.get("last_scan").isoformat() if stats.get("last_scan") else None,
        "top_platforms": sorted(
            [(platform, count) for platform, count in stats.get("platforms", {}).items()],
            key=lambda x: x[1],
            reverse=True
        )[:10] if stats.get("platforms") else []
    }


@router.post("/images/refresh")
async def refresh_image_cache():
    """
    Force a refresh of the image scanner cache and save to disk.

    Use this endpoint after adding new images to LaunchBox.
    This will rescan all image directories and update the disk cache.
    Warning: This operation may take 30-40 seconds for large libraries.
    """
    try:
        image_scanner.refresh_cache()
        stats = image_scanner.get_cache_stats()

        return {
            "success": True,
            "message": "Image cache refreshed and saved to disk",
            "images_found": stats.get("images_found", 0),
            "platforms_scanned": stats.get("platforms_scanned", 0),
            "scan_duration_seconds": stats.get("scan_duration", 0),
            "cache_file_exists": stats.get("cache_file_exists", False),
            "cache_file_size_mb": stats.get("cache_file_size_mb", 0)
        }
    except Exception as e:
        logger.error(f"Failed to refresh image cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Local LaunchBox endpoints (proxied via /api/local/*)
# =============================================================================

local_router = APIRouter(prefix="/launchbox", tags=["launchbox-local"])


def _normalize_application_path(raw_path: Optional[str]) -> Path:
    cleaned = (raw_path or "").strip().strip('"')
    if not cleaned:
        raise ValueError("ApplicationPath missing in XML")
    candidate = Path(cleaned)
    if not candidate.is_absolute():
        candidate = (Paths.LaunchBox.root() / cleaned).resolve()
    return candidate


def _build_launch_command(entry: Dict[str, str]) -> List[str]:
    exe_path = _normalize_application_path(entry.get("applicationPath"))
    if not exe_path.exists():
        raise FileNotFoundError(f"Executable not found: {exe_path}")
    cmd_line = (entry.get("commandLine") or "").strip()
    args: List[str] = shlex.split(cmd_line, posix=False) if cmd_line else []
    return [str(exe_path), *args]


def _serialize_cache_game(game: Game) -> Dict[str, Any]:
    return {
        "id": getattr(game, "id", ""),
        "title": getattr(game, "title", ""),
        "platform": getattr(game, "platform", ""),
        "applicationPath": getattr(game, "application_path", "") or getattr(game, "rom_path", "") or "",
        "commandLine": "",
        "genre": getattr(game, "genre", None),
        "year": getattr(game, "year", None),
    }


@local_router.get("/games")
async def local_list_games(
    platform: Optional[str] = Query(None),
    q: str = "",
    limit: int = 100
):
    platform_param = (platform or "").strip()

    try:
        if not platform_param or platform_param.lower() == "all":
            cache_games = await run_in_threadpool(parser.get_all_games)
            games = [_serialize_cache_game(g) for g in cache_games]
        else:
            games = await run_in_threadpool(get_platform_games, platform_param)
    except FileNotFoundError as e:
        logger.warning(f"LaunchBox data not found: {e}")
        raise HTTPException(status_code=503, detail="LaunchBox data not found or misconfigured")
    except Exception as e:
        logger.error(f"LaunchBox game list error: {e}")
        raise HTTPException(status_code=503, detail="Unable to load games from LaunchBox")

    if q:
        q_lower = q.lower()
        games = [g for g in games if q_lower in (g.get("title") or "").lower()]

    return games[:limit] if games else []


@local_router.post("/play")
async def local_play_game(payload: Dict[str, str]):
    payload = payload or {}
    platform = payload.get("platform")
    gid = payload.get("id")

    if not platform or not gid:
        raise HTTPException(status_code=422, detail="id and platform are required")

    games = await run_in_threadpool(get_platform_games, platform)
    match = next((g for g in games if g.get("id") == gid), None)
    if not match:
        raise HTTPException(status_code=404, detail="Game not found")
    if not match.get("applicationPath"):
        raise HTTPException(status_code=422, detail="ApplicationPath missing in XML")

    try:
        command = _build_launch_command(match)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    exec_path = Path(command[0])

    def _launch():
        subprocess.Popen(command, cwd=str(exec_path.parent))

    await run_in_threadpool(_launch)
    audit_log_append({
        "panel": "launchbox",
        "action": "play",
        "game_id": gid,
        "platform": platform,
        "title": match.get("title"),
    })

    return {"ok": True, "launched": match.get("title"), "id": gid}


@local_router.get("/random")
async def local_random_game(platform: Optional[str] = Query(None)):
    platform_param = (platform or "").strip()

    try:
        if not platform_param or platform_param.lower() == "all":
            cache_games = await run_in_threadpool(parser.get_all_games)
            games = [_serialize_cache_game(g) for g in cache_games]
        else:
            games = await run_in_threadpool(get_platform_games, platform_param)
    except FileNotFoundError as e:
        logger.warning(f"LaunchBox data not found: {e}")
        raise HTTPException(status_code=503, detail="LaunchBox data not found or misconfigured")
    except Exception as e:
        logger.error(f"LaunchBox random game error: {e}")
        raise HTTPException(status_code=503, detail="Unable to load games from LaunchBox")

    if not games:
        raise HTTPException(status_code=503, detail="No games available")

    pick = random.choice(games)
    audit_log_append({
        "panel": "launchbox",
        "action": "random_select",
        "game_id": pick.get("id"),
        "platform": platform,
        "title": pick.get("title"),
    })
    return pick


# =============================================================================
# Pegasus Exit Hook - State Cleanup on Game Exit
# =============================================================================


@router.post("/pegasus/exit")
async def pegasus_exit(request: Request):
    """
    Called by Pegasus launch script when emulator exits.
    
    Clears marquee preview state and resets runtime state to browse mode.
    This prevents LoRa from reading stale game state after returning to menu.
    """
    # Clear marquee preview
    try:
        await marquee_router.clear_preview()
    except Exception as e:
        logger.debug(f"Marquee clear failed (non-critical): {e}")
    
    # Reset runtime state to browse mode
    try:
        drive_root = getattr(request.app.state, "drive_root", None)
        update_runtime_state({
            "frontend": "pegasus",
            "mode": "browse",
            "system_id": None,
            "game_title": None,
            "game_id": None,
            "player": None,
            "elapsed_seconds": None,
        }, drive_root)
        logger.info("[PEGASUS] Exit hook: cleared marquee and reset runtime state to browse")
    except Exception as e:
        logger.warning(f"Runtime state reset failed: {e}")
    
    return {"ok": True, "cleared": True, "mode": "browse"}

