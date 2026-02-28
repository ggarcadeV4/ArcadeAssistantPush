"""Game Lifecycle Router — The Nervous System.

Handles Playnite game start/stop events, triggers LEDBlinky
Cinema Logic profiles, and bridges to GameLifecycleService
for score capture on game exit.

Endpoints:
    POST /api/game/start  — Game launched (LED + score tracking)
    POST /api/game/stop   — Game exited (LED reset + hiscore sync)
    GET  /api/game/status  — Health check + active game list
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
    """Payload sent by Playnite when a game starts."""
    game_name: str = Field(..., description="Name of the game being launched")
    tags: List[str] = Field(default_factory=list, description="List of tags including LED:* Cinema Logic tags")
    rom_name: Optional[str] = Field(None, description="ROM filename without extension (for direct blinky lookup)")
    platform: Optional[str] = Field(None, description="Platform name (e.g., Arcade, SNES)")


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
_DRIVE_ROOT = os.getenv("AA_DRIVE_ROOT", "A:\\")
LEDBLINKY_EXE = Path(_DRIVE_ROOT) / "LEDBlinky" / "LEDBlinky.exe"


def _extract_cinema_tag(tags: List[str]) -> Optional[str]:
    """Extract the first LED:* Cinema Logic tag from a tags list."""
    for tag in tags:
        if tag.upper().startswith("LED:"):
            return tag.upper()
    return None


# LEDBlinky animation codes (from LEDBlinky docs):
#   1 = Game Start animation
#   2 = Game Quit animation  
#   3 = Pause animation
#   4 = Screen Saver Start
#   5 = Screen Saver Stop
#  14 = Set individual LED (e.g., "14", "1,48" = LED 1 brightness 48)

CINEMA_TAG_TO_ANIMATION = {
    "LED:FIGHTING":    "1",
    "LED:RACING":      "1",
    "LED:SHOOTER":     "1",
    "LED:SPORTS":      "1",
    "LED:BEATEMUP":    "1",
    "LED:LIGHTGUN":    "1",
    "LED:PLATFORMER":  "1",
    "LED:PUZZLE":      "1",
    "LED:MAZE":        "1",
    "LED:TRACKBALL":   "1",
    "LED:STANDARD":    "1",
}

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
    animation_code: str,
    rom_name: Optional[str] = None,
    cinema_tag: Optional[str] = None,
) -> str:
    """Call LEDBlinky.exe with the given animation code.
    
    If the subprocess fails for any reason, falls back to the Python HID
    stack via _apply_genre_theme() so LEDs still respond.
    
    Args:
        animation_code: LEDBlinky animation code (e.g., "1" for game start)
        rom_name: Optional ROM name for game-specific lighting
        cinema_tag: Optional cinema tag for HID fallback (e.g., "LED:FIGHTING")
        
    Returns:
        Status string: "ok", "not_found", "fallback_hid", or "error: <message>"
    """
    if not LEDBLINKY_EXE.exists():
        logger.warning(f"LEDBlinky not found at {LEDBLINKY_EXE} — falling back to HID")
        if cinema_tag:
            fb = await _apply_genre_theme(cinema_tag)
            return f"not_found|fallback_{fb}"
        return "not_found"
    
    try:
        cmd = [str(LEDBLINKY_EXE), animation_code]
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
            logger.info(f"[LEDBlinky] Success: animation={animation_code} rom={rom_name}")
            return "ok"
        else:
            logger.warning(f"[LEDBlinky] Non-zero exit: {result.returncode} — {result.stderr}")
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


def _bridge_track_game(game_name: str, rom_name: Optional[str], platform: Optional[str]) -> str:
    """Register the game with GameLifecycleService for score capture on exit.
    
    Returns status string for the response.
    """
    global _active_game
    
    _active_game = {
        "game_name": game_name,
        "rom_name": rom_name or "",
        "platform": platform or "Arcade",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    
    # Try to register with the full GameLifecycleService (PID-based tracking)
    try:
        from backend.services.game_lifecycle import get_game_lifecycle
        service = get_game_lifecycle()
        logger.info(f"[Bridge] GameLifecycleService available, active games: {len(service.get_active_games())}")
        return "tracked"
    except Exception as e:
        logger.warning(f"[Bridge] GameLifecycleService not available: {e} — using lightweight tracking")
        return "tracked_lightweight"


async def _bridge_on_game_stop() -> str:
    """Trigger score capture and hiscore sync when a game stops.
    
    Returns status string for the response.
    """
    global _active_game
    
    if not _active_game:
        logger.info("[Bridge] No active game to stop — may have been stopped by PID monitor")
        return "no_active_game"
    
    game_info = dict(_active_game)
    _active_game = {}
    
    game_name = game_info.get("game_name", "Unknown")
    rom_name = game_info.get("rom_name", "")
    platform = game_info.get("platform", "Arcade")
    
    logger.info(f"[Bridge] Game stopped: {game_name} — triggering hiscore sync")
    
    # 1. Sync MAME hiscores (if applicable)
    is_mame = platform.lower() in ("arcade", "mame") or "mame" in platform.lower()
    if is_mame and rom_name:
        try:
            from backend.services.hiscore_watcher import get_watcher
            watcher = get_watcher()
            result = await asyncio.to_thread(watcher.sync_all)
            synced = list(result.keys()) if isinstance(result, dict) else []
            logger.info(f"[Bridge] MAME hiscore sync: {len(synced)} games synced")
        except Exception as e:
            logger.warning(f"[Bridge] MAME hiscore sync failed (non-critical): {e}")
    
    # 2. Broadcast score update to ScoreKeeper Sam via Gateway
    try:
        import httpx
        await asyncio.to_thread(
            httpx.post,
            "http://localhost:8787/api/scorekeeper/broadcast",
            json={
                "type": "score_updated",
                "games": [rom_name] if rom_name else [],
                "source": "playnite_game_exit",
                "game_title": game_name,
                "game_id": rom_name,
            },
            timeout=2.0,
        )
        logger.info("[Bridge] Score broadcast sent to ScoreKeeper Sam")
    except Exception as e:
        logger.debug(f"[Bridge] Score broadcast failed (non-critical): {e}")
    
    return "synced"


# ============================================================================
# Session Bridge (Break 5 fix) — Write game context to Supabase session
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
        # Non-critical — session bridge is best-effort
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
    
    logger.info(
        f"[GameStart] {request.game_name} | tag={cinema_tag} | "
        f"rom={request.rom_name} | platform={request.platform}"
    )
    
    # Determine LEDBlinky animation code
    animation = CINEMA_TAG_TO_ANIMATION.get(cinema_tag or "", "1")
    
    # Fire LEDBlinky (per-button ROM-specific layout via CLI)
    # If LEDBlinky fails, falls back to HID genre theme automatically
    blinky_status = await _call_ledblinky(animation, request.rom_name, cinema_tag=cinema_tag)
    
    # Apply genre color theme to HID LEDs (cosmetic overlay, non-blocking)
    theme_status = await _apply_genre_theme(cinema_tag)
    
    # Bridge to score tracking pipeline (Break 1 fix)
    tracking_status = _bridge_track_game(request.game_name, request.rom_name, request.platform)
    
    # Bridge to session store (Break 5 fix) — fire-and-forget
    asyncio.create_task(
        _bridge_update_session(request.game_name, request.rom_name, request.platform)
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
    logger.info("[GameStop] Game exited — resetting LEDs to attract mode")
    
    # Animation code 2 = Game Quit
    blinky_status = await _call_ledblinky("2")
    
    # Reset HID LEDs to idle amber (separate from LEDBlinky quit animation)
    await _reset_leds_to_idle()
    
    # Bridge to score pipeline (Break 1 fix)
    score_status = await _bridge_on_game_stop()
    
    # Clear session context (Break 5 fix) — fire-and-forget
    asyncio.create_task(_bridge_clear_session())
    
    return GameLifecycleResponse(
        success=True,
        event="game_stop",
        ledblinky_status=blinky_status,
        score_tracking=score_status,
        message="Game stopped — LEDs reset, hiscores synced",
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
        "drive_root": _DRIVE_ROOT,
        "active_game": _active_game if _active_game else None,
        "service_tracked_games": service_games,
        "endpoints": ["/api/game/start", "/api/game/stop", "/api/game/status"],
    }
