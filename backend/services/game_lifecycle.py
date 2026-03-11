"""
Game Lifecycle Service
Tracks running game processes and triggers score capture on exit.

@service: game_lifecycle
@role: Process monitoring and game exit detection
@owner: Arcade Assistant / ScoreKeeper Sam
@status: active

Architecture:
  1. Game launches via aa_launch.py or launchbox.py
  2. This service tracks the process (PID)
  3. Background task monitors for exit
  4. On exit, triggers Vision score extraction (non-MAME) OR AI commentary (MAME)
"""

import asyncio
import logging
import os
import psutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import httpx

from backend.services.led_priority_arbiter import get_led_arbiter, LEDPriority
from backend.services.score_tracking import CanonicalGameEvent, get_score_tracking_service

logger = logging.getLogger(__name__)


# ── B5 FIX: Genre-Aware LED Animation Codes for LEDBlinky ────────────
# Each genre tag maps to a distinct animation code that makes the cabinet
# "feel" different per game type. Code "1" is the fallback (static ON).
GENRE_ANIMATION_MAP = {
    "LED:FIGHTING":   "3",    # Aggressive strobing
    "LED:RACING":     "4",    # Circular chase
    "LED:SHOOTER":    "5",    # Rapid pulse
    "LED:SPORTS":     "6",    # Slow sweep
    "LED:LIGHTGUN":   "7",    # Target flash
    "LED:PLATFORMER": "8",    # Color cycle
    "LED:PUZZLE":     "9",    # Breathing
    "LED:STANDARD":   "1",    # Static ON (default)
}


def get_animation_for_game(tags: list) -> str:
    """Select the best LEDBlinky animation code based on a game's genre tags.

    Args:
        tags: List of cinema/genre tags from the game metadata
              (e.g., ["LED:FIGHTING", "CABINET:VEWLIX"])

    Returns:
        Animation code string (e.g. "3" for fighting games)
    """
    for tag in tags:
        if tag in GENRE_ANIMATION_MAP:
            return GENRE_ANIMATION_MAP[tag]
    return GENRE_ANIMATION_MAP["LED:STANDARD"]


@dataclass
class TrackedGame:
    """Represents a game being monitored for exit."""
    game_id: str
    game_title: str
    platform: str
    pid: int
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    emulator: Optional[str] = None
    rom_name: Optional[str] = None
    source: str = "arcade_assistant"
    launch_method: str = "pid_monitor"
    player: Optional[str] = None
    session_id: Optional[str] = None
    is_mame: bool = False


class GameLifecycleService:
    """
    Monitors game processes and triggers actions on exit.
    
    For MAME: Score is captured by Lua plugin, this just logs the exit
    For Non-MAME: Triggers AI Vision to capture final score from screenshot
    """
    
    def __init__(self):
        self._tracked_games: Dict[int, TrackedGame] = {}  # pid -> TrackedGame
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False
        self._poll_interval = 2.0  # seconds
    
    async def start(self) -> None:
        """Start the background monitor."""
        if self._running:
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("GameLifecycleService started")
    
    async def stop(self) -> None:
        """Stop the background monitor."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("GameLifecycleService stopped")
    
    def track_game(
        self,
        game_id: str,
        game_title: str,
        platform: str,
        pid: int,
        emulator: Optional[str] = None,
        rom_name: Optional[str] = None,
        source: str = "arcade_assistant",
        launch_method: str = "pid_monitor",
        player: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> None:
        """
        Start tracking a game launch.
        
        Args:
            game_id: LaunchBox GUID
            game_title: Display name
            platform: Platform/system name
            pid: Process ID to monitor
            emulator: Emulator name (for determining if MAME)
        """
        is_mame = self._is_mame_emulator(emulator, platform)
        
        tracked = TrackedGame(
            game_id=game_id,
            game_title=game_title,
            platform=platform,
            pid=pid,
            emulator=emulator,
            rom_name=rom_name,
            source=source,
            launch_method=launch_method,
            player=player,
            session_id=session_id,
            is_mame=is_mame
        )
        
        self._tracked_games[pid] = tracked
        logger.info(
            f"Tracking game: {game_title} (pid={pid}, mame={is_mame})"
        )

        try:
            tracking_service = get_score_tracking_service(Path(os.getenv("AA_DRIVE_ROOT", "A:\\")))
            session = tracking_service.record_launch(
                CanonicalGameEvent(
                    session_id=session_id,
                    source=source,
                    game_id=game_id,
                    title=game_title,
                    platform=platform,
                    emulator=emulator,
                    pid=pid,
                    launch_method=launch_method,
                    player=player,
                    rom_name=rom_name,
                )
            )
            tracked.session_id = session.get("session_id")
        except Exception as tracking_error:
            logger.warning(f"Score tracking launch record failed: {tracking_error}")

        try:
            tags = getattr(tracked, "tags", []) or []
            animation = get_animation_for_game(tags)
            arbiter = get_led_arbiter()
            asyncio.create_task(
                arbiter.claim(
                    LEDPriority.GAME,
                    animation_code=animation,
                    label=f"Game: {game_title}",
                )
            )
        except Exception as e:
            logger.warning(f"LED arbiter claim failed (non-fatal): {e}")

    def untrack_game(self, pid: int) -> Optional[TrackedGame]:
        """Stop tracking a game and return its info."""
        return self._tracked_games.pop(pid, None)

    def _is_mame_emulator(self, emulator: Optional[str], platform: str) -> bool:
        """Determine if the emulator is MAME (scores handled by Lua plugin)."""
        if not emulator:
            emulator = ""

        emulator_lower = emulator.lower()
        platform_lower = platform.lower()
        mame_indicators = ["mame", "arcade"]
        return any(ind in emulator_lower or ind in platform_lower for ind in mame_indicators)

    async def _monitor_loop(self) -> None:
        """Background loop that checks for exited processes."""
        while self._running:
            try:
                await self._check_processes()
            except Exception as e:
                logger.error(f"Error in game monitor loop: {e}")

            await asyncio.sleep(self._poll_interval)

    async def _check_processes(self) -> None:
        """Check tracked processes and handle exits."""
        exited = []

        for pid, tracked in list(self._tracked_games.items()):
            if not psutil.pid_exists(pid):
                exited.append((pid, tracked))
            else:
                try:
                    proc = psutil.Process(pid)
                    if proc.status() in [psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD]:
                        exited.append((pid, tracked))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    exited.append((pid, tracked))

        for pid, tracked in exited:
            self.untrack_game(pid)
            await self._on_game_exit(tracked)

    async def _on_game_exit(self, tracked: TrackedGame) -> None:
        """Handle game exit - detect crashes, trigger remediation, or score capture."""
        play_duration = (datetime.now(timezone.utc) - tracked.started_at).total_seconds()

        try:
            arbiter = get_led_arbiter()
            await arbiter.release(LEDPriority.GAME)
        except Exception as e:
            logger.warning(f"LED arbiter release failed (non-fatal): {e}")

        logger.info(
            f"Game exited: {tracked.game_title} after {play_duration:.0f}s "
            f"(mame={tracked.is_mame})"
        )

        try:
            from backend.services.launch_remediation import is_probable_crash, attempt_remediation
            if is_probable_crash(play_duration):
                logger.warning(
                    f"Probable crash detected for {tracked.game_title} "
                    f"(exited in {play_duration:.1f}s < 10s threshold)"
                )
                error_context = (
                    f"Game '{tracked.game_title}' on platform '{tracked.platform}' "
                    f"exited in {play_duration:.1f}s using emulator '{tracked.emulator}'. "
                    f"PID {tracked.pid} is no longer running."
                )
                result = await attempt_remediation(
                    game_title=tracked.game_title,
                    platform=tracked.platform,
                    emulator=tracked.emulator,
                    error_context=error_context,
                )
                try:
                    from backend.routers.doc_diagnostics import broadcast_health_event
                    await broadcast_health_event({
                        "type": "remediation",
                        "game": tracked.game_title,
                        "platform": tracked.platform,
                        "emulator": tracked.emulator,
                        "play_duration": play_duration,
                        "result": result.to_dict(),
                    })
                except Exception as ws_err:
                    logger.debug(f"Doc WS broadcast skipped: {ws_err}")
                await self._log_game_session(tracked, play_duration)
                return
        except ImportError:
            logger.debug("launch_remediation not available - skipping crash detection")
        except Exception as exc:
            logger.error(f"Remediation check failed: {exc}")

        tracking_service = None
        session = None
        try:
            tracking_service = get_score_tracking_service(Path(os.getenv("AA_DRIVE_ROOT", "A:\\")))
            session = tracking_service.close_session(
                session_id=tracked.session_id,
                game_id=tracked.game_id,
                title=tracked.game_title,
                pid=tracked.pid,
                rom_name=tracked.rom_name,
            )
        except Exception as tracking_error:
            logger.warning(f"Score tracking close session failed: {tracking_error}")

        if tracked.is_mame:
            logger.debug("MAME game - score handled by Lua plugin")
            mame_result = await self._sync_mame_hiscores(tracked)
            if tracking_service and session:
                if mame_result and mame_result.get("score") is not None:
                    tracking_service.record_auto_capture(
                        session,
                        strategy_name="mame_hiscore",
                        score=int(mame_result.get("score")),
                        confidence=1.0,
                        player=tracked.player or mame_result.get("name"),
                        metadata={
                            "rom_name": tracked.rom_name,
                            "source": "mame_hiscore",
                            "rank": mame_result.get("rank"),
                        },
                    )
                else:
                    tracking_service.record_pending_review(
                        session,
                        strategy_name="mame_hiscore",
                        reason="mame_sync_no_score",
                        metadata={
                            "rom_name": tracked.rom_name,
                            "play_duration": play_duration,
                        },
                    )
            await self._log_game_session(tracked, play_duration)
        else:
            logger.info(f"Non-MAME game exit - triggering Vision capture for {tracked.game_title}")
            vision_result = await self._trigger_vision_capture(tracked)
            if tracking_service and session:
                if vision_result and vision_result.get("score") is not None:
                    confidence = float(vision_result.get("confidence") or 0.0)
                    evidence_path = vision_result.get("image_path") or vision_result.get("screenshot_path")
                    if confidence >= 0.85:
                        tracking_service.record_auto_capture(
                            session,
                            strategy_name="vision",
                            score=int(vision_result.get("score")),
                            confidence=confidence,
                            evidence_path=evidence_path,
                            player=tracked.player,
                            metadata={
                                "screen_type": vision_result.get("screen_type"),
                                "source": vision_result.get("source"),
                            },
                        )
                    else:
                        tracking_service.record_pending_review(
                            session,
                            strategy_name="vision",
                            confidence=confidence,
                            raw_score=int(vision_result.get("score")),
                            evidence_path=evidence_path,
                            reason="vision_low_confidence",
                            metadata={
                                "screen_type": vision_result.get("screen_type"),
                            },
                        )
                else:
                    strategy_name = (session.get("strategy") or {}).get("primary") or "vision"
                    tracking_service.record_pending_review(
                        session,
                        strategy_name=strategy_name,
                        reason="vision_no_score",
                        metadata={
                            "play_duration": play_duration,
                            "rom_name": tracked.rom_name,
                        },
                    )
            await self._log_game_session(tracked, play_duration)

    async def _sync_mame_hiscores(self, tracked: TrackedGame) -> Optional[Dict[str, Any]]:
        """Trigger an immediate MAME hiscore sync on game exit."""
        try:
            from backend.services.hiscore_watcher import get_watcher

            watcher = get_watcher()
            result = watcher.sync_all()
            games = list(result.keys()) if isinstance(result, dict) else []
            top_entry = None
            if tracked.rom_name:
                entries = watcher.get_game_scores(tracked.rom_name)
                if entries:
                    top_entry = entries[0]

            try:
                await asyncio.to_thread(
                    httpx.post,
                    "http://localhost:8787/api/scorekeeper/broadcast",
                    json={
                        "type": "score_updated",
                        "games": games,
                        "source": "game_exit",
                        "game_title": tracked.game_title,
                        "game_id": tracked.game_id,
                    },
                    timeout=2.0,
                )
            except Exception as e:
                logger.debug(f"Score broadcast failed (non-critical): {e}")
            return top_entry
        except Exception as e:
            logger.warning(f"MAME hiscore sync on exit failed: {e}")
            return None

    async def _trigger_vision_capture(self, tracked: TrackedGame) -> Optional[Dict[str, Any]]:
        """Trigger AI Vision score extraction for non-MAME games."""
        try:
            from backend.services.vision_score_service import get_vision_score_service

            vision_service = get_vision_score_service()
            if not vision_service:
                logger.warning("Vision score service not available")
                return None

            await asyncio.sleep(0.5)

            result = await vision_service.process_game_exit(
                game_rom=tracked.rom_name or tracked.game_id,
                player_name=tracked.player,
            )

            if result:
                logger.info(
                    f"Vision captured score for {tracked.game_title}: "
                    f"{result.get('score')}"
                )
                await self._submit_score_to_scorekeeper(tracked, result)
                await self._announce_score(tracked, result)
            else:
                logger.debug(f"No score captured for {tracked.game_title}")
            return result
        except Exception as e:
            logger.error(f"Vision capture failed: {e}")
            return None

    async def _submit_score_to_scorekeeper(
        self,
        tracked: TrackedGame,
        score_data: Dict[str, Any]
    ) -> None:
        """Submit a captured score into ScoreKeeper (best-effort)."""
        try:
            score = score_data.get("score")
            if score is None:
                return

            player_name = None
            player_user_id = None
            player_source = None

            try:
                from backend.services.player_tendencies import get_active_session

                active = get_active_session()
                if active:
                    player_name = active.get("player_name")
                    player_user_id = active.get("player_id")
                    player_source = "profile"
            except Exception:
                pass

            if not player_name:
                try:
                    from backend.services.hiscore_watcher import get_watcher

                    watcher = get_watcher()
                    primary = watcher._load_primary_profile()  # best-effort
                    if primary:
                        player_name = primary.get("display_name")
                        player_user_id = primary.get("user_id")
                        player_source = "profile"
                except Exception:
                    pass

            if not player_name:
                player_name = "unknown"

            payload = {
                "game": tracked.game_title,
                "game_id": tracked.game_id,
                "system": tracked.platform,
                "player": player_name,
                "score": int(score),
                "player_userId": player_user_id,
                "player_source": player_source,
            }

            headers = {
                "x-scope": "state",
                "x-panel": "playnite",
                "Content-Type": "application/json",
            }

            await asyncio.to_thread(
                httpx.post,
                "http://localhost:8787/api/scorekeeper/submit/apply",
                json=payload,
                headers=headers,
                timeout=5.0
            )
        except Exception as e:
            logger.debug(f"Score submit failed (non-critical): {e}")
    
    async def _announce_score(
        self, 
        tracked: TrackedGame, 
        score_data: Dict[str, Any]
    ) -> None:
        """Generate AI commentary for captured score."""
        try:
            from backend.services.score_announcer import announce_high_score
            
            await announce_high_score(
                game_name=tracked.game_title,
                score=score_data.get("score", 0),
                initials=score_data.get("initials", "???"),
                rank=1,  # Assume #1 for non-MAME single captures
                previous_scores=None,
                speak=True
            )
        except Exception as e:
            logger.debug(f"Score announcement failed: {e}")
    
    async def _log_game_session(
        self, 
        tracked: TrackedGame, 
        duration_seconds: float
    ) -> None:
        """Log game session for analytics."""
        try:
            # Could write to a sessions log file or send to Supabase
            logger.debug(
                f"Session logged: {tracked.game_title}, "
                f"platform={tracked.platform}, duration={duration_seconds:.0f}s"
            )
        except Exception:
            pass
    
    def get_active_games(self) -> List[Dict[str, Any]]:
        """Get list of currently tracked games."""
        return [
            {
                "game_id": t.game_id,
                "game_title": t.game_title,
                "platform": t.platform,
                "pid": t.pid,
                "started_at": t.started_at.isoformat(),
                "is_mame": t.is_mame
            }
            for t in self._tracked_games.values()
        ]


# Global instance
_game_lifecycle: Optional[GameLifecycleService] = None


def get_game_lifecycle() -> GameLifecycleService:
    """Get or create the global GameLifecycleService instance."""
    global _game_lifecycle
    if _game_lifecycle is None:
        _game_lifecycle = GameLifecycleService()
    return _game_lifecycle


async def initialize_game_lifecycle() -> GameLifecycleService:
    """Initialize and start the game lifecycle service."""
    service = get_game_lifecycle()
    await service.start()
    return service


async def shutdown_game_lifecycle() -> None:
    """Shutdown the game lifecycle service."""
    global _game_lifecycle
    if _game_lifecycle:
        await _game_lifecycle.stop()
        _game_lifecycle = None


def track_game_launch(
    game_id: str,
    game_title: str,
    platform: str,
    pid: int,
    emulator: Optional[str] = None,
    rom_name: Optional[str] = None,
    source: str = "arcade_assistant",
    launch_method: str = "pid_monitor",
    player: Optional[str] = None,
    session_id: Optional[str] = None,
) -> None:
    """Convenience function to track a game launch."""
    service = get_game_lifecycle()
    service.track_game(
        game_id,
        game_title,
        platform,
        pid,
        emulator,
        rom_name,
        source,
        launch_method,
        player,
        session_id,
    )



