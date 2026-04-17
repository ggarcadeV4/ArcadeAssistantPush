"""Game Lifecycle Router - The Nervous System.

Handles Playnite game start/stop events, triggers LEDBlinky
Cinema Logic profiles, and bridges to GameLifecycleService
for score capture on game exit.

Endpoints:
    POST /api/game/start  - Game launched (LED + score tracking)
    POST /api/game/stop   - Game exited (LED reset + hiscore sync)
    GET  /api/game/status  - Health check + active game list
"""

from __future__ import annotations

import asyncio
import logging
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Request
from backend.constants.drive_root import get_drive_root
from backend.services.score_tracking import CanonicalGameEvent, get_score_tracking_service
from backend.services.led_blinky_translator import resolve_animation_code, resolve_genre_key
from pydantic import BaseModel, Field

logger = logging.getLogger("game_lifecycle")

router = APIRouter(
    prefix="/api/game",
    tags=["game-lifecycle"],
)


# ============================================================================
# Models
# ============================================================================


class GameStartRequest(BaseModel):
    """Payload sent by Playnite or LaunchBox when a game starts."""
    game_name: str = Field(..., description="Name of the game being launched")
    game_id: Optional[str] = Field(None, description="LaunchBox or local game identifier")
    tags: List[str] = Field(default_factory=list, description="List of tags including LED:* Cinema Logic tags")
    rom_name: Optional[str] = Field(None, description="ROM filename without extension (for direct blinky lookup)")
    platform: Optional[str] = Field(None, description="Platform name (e.g., Arcade, SNES)")
    emulator: Optional[str] = Field(None, description="Emulator or launcher name")
    pid: Optional[int] = Field(None, description="Running process id when known")
    source: str = Field(default="launchbox_plugin", description="Origin of the launch event")
    launch_method: str = Field(default="plugin_event", description="How the launch was initiated")
    player: Optional[str] = Field(None, description="Known player identity for the session")

class GameLifecycleResponse(BaseModel):
    """Standard response for game lifecycle events."""
    success: bool
    event: str
    game_name: Optional[str] = None
    cinema_tag: Optional[str] = None
    ledblinky_status: str = "skipped"
    score_tracking: str = "skipped"
    message: str = ""


# ============================================================================
# LEDBlinky Integration
# ============================================================================

# Dynamically resolve LEDBlinky path from drive root
_DRIVE_ROOT = get_drive_root()
LEDBLINKY_EXE = _DRIVE_ROOT / "LEDBlinky" / "LEDBlinky.exe"


def _extract_cinema_tag(tags: List[str]) -> Optional[str]:
    """Extract the first LED:* Cinema Logic tag from a tags list."""
    for tag in tags:
        if tag.upper().startswith("LED:"):
            return tag.upper()
    return None


# Map Cinema tags to color themes from configs/ledblinky/colors.json.
# These provide a genre-appropriate color wash on the Python HID stack
# (separate from LEDBlinky's per-button ROM-specific layouts).
CINEMA_TAG_TO_THEME = {
    "LED:FIGHTING":    "FighterClassic",
    "LED:BEATEMUP":    "FighterClassic",
    "LED:SHOOTER":     "SciFiShooter",
    "LED:RACING":      "NitroRush",
    "LED:SPORTS":      "Vibrant",
    "LED:LIGHTGUN":    "TargetLock",
    "LED:PLATFORMER":  "RetroArcade",
    "LED:PUZZLE":      "PurpleRain",
    "LED:MAZE":        "PurpleRain",
    "LED:TRACKBALL":   "RetroArcade",
    "LED:STANDARD":    "RetroArcade",
}

# Default idle LED color (warm amber) when no game is running
_IDLE_COLOR: Tuple[int, int, int] = (0xFF, 0xBF, 0x00)


def _load_theme_colors(theme_name: str) -> List[Tuple[int, int, int]]:
    """Load an RGB color list from configs/ledblinky/colors.json."""
    try:
        config_path = Path(_DRIVE_ROOT) / "Arcade Assistant Local" / "configs" / "ledblinky" / "colors.json"
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        theme = data.get("themes", {}).get(theme_name)
        if not theme:
            logger.warning(f"[ColorTheme] Theme '{theme_name}' not found in colors.json")
            return []
        rgbs = []
        for hex_color in theme.get("colors", []):
            h = hex_color.lstrip("#")
            rgbs.append((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))
        return rgbs
    except Exception as e:
        logger.warning(f"[ColorTheme] Failed to load theme '{theme_name}': {e}")
        return []


async def _apply_genre_theme(cinema_tag: Optional[str]) -> str:
    """Apply a genre-specific color theme to LEDs via the Python HID stack.

    This is a cosmetic overlay *on top of* LEDBlinky's per-button ROM
    layouts.  If the HID stack is not available, this is silently skipped.

    Returns: 'applied', 'no_theme', or 'hid_unavailable'
    """
    theme_name = CINEMA_TAG_TO_THEME.get(cinema_tag or "", "RetroArcade")
    colors = _load_theme_colors(theme_name)
    if not colors:
        return "no_theme"

    try:
        from backend.services.led_hardware import LEDHardwareService
        hw = LEDHardwareService()  # Singleton
        for port_idx, rgb in enumerate(colors):
            hw.write_port(0, port_idx, rgb)
        logger.info(f"[ColorTheme] Applied '{theme_name}' ({len(colors)} ports)")
        return "applied"
    except Exception as e:
        logger.debug(f"[ColorTheme] HID unavailable (non-fatal): {e}")
        return "hid_unavailable"


async def _reset_leds_to_idle() -> str:
    """Reset all LED ports to the warm idle amber color.

    Called on game stop to return LEDs to attract mode on the HID
    side (LEDBlinky separately handles its own quit animation).

    Returns: 'reset', or 'hid_unavailable'
    """
    try:
        from backend.services.led_hardware import LEDHardwareService
        hw = LEDHardwareService()
        for port_idx in range(16):
            hw.write_port(0, port_idx, _IDLE_COLOR)
        logger.info("[ColorTheme] LEDs reset to idle amber")
        return "reset"
    except Exception as e:
        logger.debug(f"[ColorTheme] HID unavailable on reset (non-fatal): {e}")
        return "hid_unavailable"


async def _call_ledblinky(
    animation_code: Optional[str] = None,
    rom_name: Optional[str] = None,
    cinema_tag: Optional[str] = None,
    genre: Optional[str] = None,
) -> str:
    """Call LEDBlinky.exe with the given animation code.
    
    If the subprocess fails for any reason, falls back to the Python HID
    stack via _apply_genre_theme() so LEDs still respond.
    
    Args:
        animation_code: Optional LEDBlinky animation code override
        rom_name: Optional ROM name for game-specific lighting
        cinema_tag: Optional cinema tag for HID fallback (e.g., "LED:FIGHTING")
        genre: Optional normalized or raw genre hint used to resolve animation code
        
    Returns:
        Status string: "ok", "not_found", "fallback_hid", or "error: <message>"
    """
    if not LEDBLINKY_EXE.exists():
        logger.warning(f"LEDBlinky not found at {LEDBLINKY_EXE} - falling back to HID")
        if cinema_tag:
            fb = await _apply_genre_theme(cinema_tag)
            return f"not_found|fallback_{fb}"
        return "not_found"
    
    try:
        resolved_animation = animation_code or resolve_animation_code(genre=genre, cinema_tag=cinema_tag)
        cmd = [str(LEDBLINKY_EXE), resolved_animation]
        if rom_name:
            cmd.append(rom_name)
            
        logger.info(f"[LEDBlinky] Calling: {' '.join(cmd)}")
        
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(LEDBLINKY_EXE.parent),
        )
        
        if result.returncode == 0:
            logger.info(f"[LEDBlinky] Success: animation={resolved_animation} rom={rom_name}")
            return "ok"
        else:
            logger.warning(f"[LEDBlinky] Non-zero exit: {result.returncode} - {result.stderr}")
            if cinema_tag:
                fb = await _apply_genre_theme(cinema_tag)
                logger.info(f"[LEDBlinky] Fallback to HID: {fb}")
                return f"error_exit_{result.returncode}|fallback_{fb}"
            return f"error: exit code {result.returncode}"
            
    except subprocess.TimeoutExpired:
        logger.error("[LEDBlinky] Timed out after 5s")
        if cinema_tag:
            fb = await _apply_genre_theme(cinema_tag)
            return f"error_timeout|fallback_{fb}"
        return "error: timeout"
    except FileNotFoundError:
        logger.error(f"[LEDBlinky] Executable not found: {LEDBLINKY_EXE}")
        if cinema_tag:
            fb = await _apply_genre_theme(cinema_tag)
            return f"not_found|fallback_{fb}"
        return "not_found"
    except Exception as e:
        logger.error(f"[LEDBlinky] Unexpected error: {e}")
        if cinema_tag:
            fb = await _apply_genre_theme(cinema_tag)
            return f"error_{e}|fallback_{fb}"
        return f"error: {e}"


# ============================================================================
# Score Pipeline Bridge (Break 1 fix)
# ============================================================================

# In-memory tracking of the currently running game so /stop can access it
_active_game: Dict[str, Any] = {}


def _bridge_track_game(
    game_name: str,
    rom_name: Optional[str],
    platform: Optional[str],
    *,
    game_id: Optional[str] = None,
    emulator: Optional[str] = None,
    pid: Optional[int] = None,
    source: str = "launchbox_plugin",
    launch_method: str = "plugin_event",
    player: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> str:
    """Register the game with score tracking and lifecycle monitoring."""
    global _active_game

    tracking_service = get_score_tracking_service(_DRIVE_ROOT)
    session = tracking_service.record_launch(
        CanonicalGameEvent(
            source=source,
            game_id=game_id,
            title=game_name,
            platform=platform or "Arcade",
            emulator=emulator,
            pid=pid,
            launch_method=launch_method,
            player=player,
            rom_name=rom_name,
        )
    )

    _active_game = {
        "session_id": session.get("session_id"),
        "game_name": game_name,
        "game_id": game_id,
        "rom_name": rom_name or "",
        "platform": platform or "Arcade",
        "emulator": emulator,
        "pid": pid,
        "player": player,
        "source": source,
        "launch_method": launch_method,
        "started_at": session.get("started_at") or datetime.now(timezone.utc).isoformat(),
    }

    if pid:
        try:
            from backend.services.game_lifecycle import track_game_launch

            track_game_launch(
                game_id=game_id or rom_name or game_name,
                game_title=game_name,
                platform=platform or "Arcade",
                pid=pid,
                emulator=emulator,
                rom_name=rom_name,
                source=source,
                launch_method=launch_method,
                player=player,
                session_id=session.get("session_id"),
                tags=tags,
            )
            return "tracked"
        except Exception as e:
            logger.warning(f"[Bridge] PID tracking unavailable: {e} - using lightweight tracking")
            return "tracked_lightweight"

    return "tracked_lightweight"


async def _bridge_on_game_stop() -> str:
    """Trigger score capture and attempt tracking when a game stops."""
    global _active_game

    if not _active_game:
        logger.info("[Bridge] No active game to stop - may have been stopped by PID monitor")
        return "no_active_game"

    game_info = dict(_active_game)
    _active_game = {}

    game_name = game_info.get("game_name", "Unknown")
    game_id = game_info.get("game_id")
    rom_name = game_info.get("rom_name", "")
    platform = game_info.get("platform", "Arcade")
    player = game_info.get("player")

    logger.info(f"[Bridge] Game stopped: {game_name} - evaluating score capture")

    tracking_service = get_score_tracking_service(_DRIVE_ROOT)
    session = tracking_service.close_session(
        session_id=game_info.get("session_id"),
        game_id=game_id,
        title=game_name,
        pid=game_info.get("pid"),
        rom_name=rom_name,
    )
    if not session:
        logger.info(f"[Bridge] Score session already closed for {game_name} - skipping duplicate stop handling")
        return "already_closed"

    is_mame = platform.lower() in ("arcade", "mame") or "mame" in platform.lower()
    status = "pending_review"

    if is_mame and rom_name:
        try:
            from backend.services.hiscore_watcher import get_watcher

            watcher = get_watcher()
            result = await asyncio.to_thread(watcher.sync_all)
            synced = list(result.keys()) if isinstance(result, dict) else []
            entries = watcher.get_game_scores(rom_name)
            top_entry = entries[0] if entries else None
            strategy_name = "mame_hiscore"
            if top_entry and str(top_entry.get("source", "")).lower() in {"mame_lua", "arcade_assistant_scores"}:
                strategy_name = "mame_lua"
            elif not top_entry and getattr(watcher, "_lua_scores_path", None):
                sync_lua_scores = getattr(watcher, "_sync_lua_scores", None)
                if callable(sync_lua_scores):
                    try:
                        sync_lua_scores(broadcast=False)
                        entries = watcher.get_game_scores(rom_name)
                        if entries:
                            top_entry = next(
                                (
                                    entry for entry in entries
                                    if str(entry.get("source", "")).lower() in {"mame_lua", "arcade_assistant_scores"}
                                ),
                                entries[0],
                            )
                            strategy_name = "mame_lua"
                    except Exception as lua_error:
                        logger.debug(f"[Bridge] MAME Lua fallback lookup failed: {lua_error}")
            if top_entry:
                tracking_service.record_auto_capture(
                    session,
                    strategy_name=strategy_name,
                    score=int(top_entry.get("score", 0)),
                    confidence=1.0,
                    player=player or top_entry.get("name"),
                    metadata={
                        "rom_name": rom_name,
                        "source": top_entry.get("source") or strategy_name,
                        "synced_games": synced,
                    },
                )
                status = "captured_auto"
            else:
                tracking_service.record_pending_review(
                    session,
                    strategy_name="mame_hiscore",
                    reason="mame_sync_no_score",
                    metadata={"rom_name": rom_name},
                )
        except Exception as e:
            logger.warning(f"[Bridge] MAME hiscore sync failed (non-critical): {e}")
            tracking_service.record_failure(session, strategy_name="mame_hiscore", reason=str(e))
            status = "failed"
    else:
        try:
            from backend.services.vision_score_service import get_vision_score_service

            vision_service = get_vision_score_service()
            result = None
            if vision_service:
                result = await vision_service.process_game_exit(
                    game_rom=rom_name or game_id or game_name,
                    player_name=player,
                )

            if result and result.get("score") is not None:
                confidence = float(result.get("confidence") or 0.0)
                evidence_path = result.get("image_path") or result.get("screenshot_path")
                if confidence >= 0.85:
                    tracking_service.record_auto_capture(
                        session,
                        strategy_name="vision",
                        score=int(result.get("score")),
                        confidence=confidence,
                        evidence_path=evidence_path,
                        player=player,
                        metadata={"screen_type": result.get("screen_type")},
                    )
                    status = "captured_auto"
                else:
                    tracking_service.record_pending_review(
                        session,
                        strategy_name="vision",
                        confidence=confidence,
                        raw_score=int(result.get("score")),
                        evidence_path=evidence_path,
                        reason="vision_low_confidence",
                        metadata={"screen_type": result.get("screen_type")},
                    )
            else:
                strategy_name = (session.get("strategy") or {}).get("primary") or "vision"
                tracking_service.record_pending_review(
                    session,
                    strategy_name=strategy_name,
                    reason="vision_no_score",
                    metadata={"rom_name": rom_name, "game_id": game_id},
                )
        except Exception as e:
            logger.warning(f"[Bridge] Vision capture failed (non-critical): {e}")
            tracking_service.record_failure(session, strategy_name="vision", reason=str(e))
            status = "failed"

    try:
        import httpx
        await asyncio.to_thread(
            httpx.post,
            "http://localhost:8787/api/scorekeeper/broadcast",
            json={
                "type": "score_updated",
                "games": [rom_name] if rom_name else [],
                "source": "launchbox_bridge_stop",
                "game_title": game_name,
                "game_id": game_id or rom_name,
            },
            timeout=2.0,
        )
    except Exception as e:
        logger.debug(f"[Bridge] Score broadcast failed (non-critical): {e}")

    return status


# ============================================================================
# Session Bridge (Break 5 fix) - Write game context to Supabase session
# ============================================================================


async def _bridge_update_session(game_name: str, rom_name: Optional[str], platform: Optional[str]) -> None:
    """Write current game context into aa_lora_sessions so Sam can hydrate the active player."""
    try:
        import httpx
        await asyncio.to_thread(
            httpx.post,
            "http://localhost:8787/api/lora/session/update-context",
            json={
                "game_name": game_name,
                "rom_name": rom_name or "",
                "platform": platform or "Arcade",
            },
            timeout=2.0,
        )
        logger.info(f"[SessionBridge] Context pushed to LoRa session: {game_name}")
    except Exception as e:
        # Non-critical - session bridge is best-effort
        logger.debug(f"[SessionBridge] Failed to update session (non-critical): {e}")


async def _bridge_clear_session() -> None:
    """Clear game context from session on game stop."""
    try:
        import httpx
        await asyncio.to_thread(
            httpx.post,
            "http://localhost:8787/api/lora/session/clear-context",
            json={},
            timeout=2.0,
        )
        logger.info("[SessionBridge] Game context cleared from LoRa session")
    except Exception as e:
        logger.debug(f"[SessionBridge] Failed to clear session (non-critical): {e}")


async def _push_marquee_game_state(
    *,
    game_name: str,
    game_id: Optional[str],
    platform: Optional[str],
    rom_name: Optional[str],
    source: str,
) -> None:
    """Write marquee state for a launched game without blocking launch flow."""
    try:
        from backend.routers import marquee as marquee_router

        await asyncio.to_thread(
            marquee_router.persist_current_game,
            {
                "game_id": game_id,
                "title": game_name,
                "platform": platform or "Arcade",
                "region": "North America",
                "rom_name": rom_name,
                "source": source,
                "mode": "video",
                "event_type": "GAME",
            },
        )
    except Exception as exc:
        logger.warning("[GameStart] Marquee switch failed: %s", exc)


async def _push_marquee_idle_state(source: str) -> None:
    """Return marquee state to idle without blocking stop flow."""
    try:
        from backend.routers import marquee as marquee_router

        await asyncio.to_thread(marquee_router.reset_marquee_to_idle, source)
    except Exception as exc:
        logger.warning("[GameStop] Marquee idle reset failed: %s", exc)


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/start", response_model=GameLifecycleResponse)
async def game_start(request: GameStartRequest):
    """Handle game start event from Playnite.
    
    Extracts the LED:* Cinema Logic tag from the game's tags,
    triggers LEDBlinky with the appropriate animation, and
    registers the game with the score tracking pipeline.
    
    Example payload:
        {
            "game_name": "Street Fighter II",
            "tags": ["LED:FIGHTING", "Arcade", "MAME"],
            "rom_name": "sf2",
            "platform": "Arcade"
        }
    """
    cinema_tag = _extract_cinema_tag(request.tags)
    launch_genre = resolve_genre_key(tags=request.tags, cinema_tag=cinema_tag)
    
    logger.info(
        f"[GameStart] {request.game_name} | genre={launch_genre or 'default'} | tag={cinema_tag} | "
        f"rom={request.rom_name} | platform={request.platform}"
    )
    
    animation = resolve_animation_code(genre=launch_genre, tags=request.tags, cinema_tag=cinema_tag)
    
    # Fire LEDBlinky (per-button ROM-specific layout via CLI)
    # If LEDBlinky fails, falls back to HID genre theme automatically
    blinky_status = await _call_ledblinky(
        animation,
        request.rom_name,
        cinema_tag=cinema_tag,
        genre=launch_genre,
    )
    
    # Apply genre color theme to HID LEDs (cosmetic overlay, non-blocking)
    theme_status = await _apply_genre_theme(cinema_tag)
    
    # Bridge to score tracking pipeline (Break 1 fix)
    tracking_status = _bridge_track_game(
        request.game_name,
        request.rom_name,
        request.platform,
        game_id=request.game_id,
        emulator=request.emulator,
        pid=request.pid,
        source=request.source,
        launch_method=request.launch_method,
        player=request.player,
        tags=request.tags,
    )
    
    # Bridge to session store (Break 5 fix) - fire-and-forget
    asyncio.create_task(
        _bridge_update_session(request.game_name, request.rom_name, request.platform)
    )
    asyncio.create_task(
        _push_marquee_game_state(
            game_name=request.game_name,
            game_id=request.game_id,
            platform=request.platform,
            rom_name=request.rom_name,
            source=request.source,
        )
    )
    
    return GameLifecycleResponse(
        success=True,
        event="game_start",
        game_name=request.game_name,
        cinema_tag=cinema_tag,
        ledblinky_status=blinky_status,
        score_tracking=tracking_status,
        message=f"Game started: {request.game_name} [{cinema_tag or 'no tag'}]",
    )


@router.post("/stop", response_model=GameLifecycleResponse)
async def game_stop():
    """Handle game stop event from Playnite.
    
    Triggers LEDBlinky quit animation (code 2) to reset LEDs
    to attract/idle mode, and triggers hiscore sync + score broadcast.
    """
    logger.info("[GameStop] Game exited - resetting LEDs to attract mode")
    
    # Animation code 2 = Game Quit
    blinky_status = await _call_ledblinky("2")
    
    # Reset HID LEDs to idle amber (separate from LEDBlinky quit animation)
    await _reset_leds_to_idle()
    
    # Bridge to score pipeline (Break 1 fix)
    score_status = await _bridge_on_game_stop()
    
    # Clear session context (Break 5 fix) - fire-and-forget
    asyncio.create_task(_bridge_clear_session())
    asyncio.create_task(_push_marquee_idle_state("game_lifecycle_stop"))
    
    return GameLifecycleResponse(
        success=True,
        event="game_stop",
        ledblinky_status=blinky_status,
        score_tracking=score_status,
        message="Game stopped - LEDs reset, hiscores synced",
    )


@router.get("/status")
async def game_lifecycle_status():
    """Health check for game lifecycle endpoints.
    
    Returns LEDBlinky availability, active games from both
    the lightweight tracker and GameLifecycleService.
    """
    ledblinky_found = LEDBLINKY_EXE.exists()
    
    # Get active games from GameLifecycleService (PID-based)
    service_games = []
    try:
        from backend.services.game_lifecycle import get_game_lifecycle
        service = get_game_lifecycle()
        service_games = service.get_active_games()
    except Exception:
        pass
    
    return {
        "status": "operational",
        "ledblinky_path": str(LEDBLINKY_EXE),
        "ledblinky_found": ledblinky_found,
        "drive_root": str(_DRIVE_ROOT),
        "active_game": _active_game if _active_game else None,
        "service_tracked_games": service_games,
        "endpoints": ["/api/game/start", "/api/game/stop", "/api/game/status"],
    }




