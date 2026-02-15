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

logger = logging.getLogger(__name__)


@dataclass
class TrackedGame:
    """Represents a game being monitored for exit."""
    game_id: str
    game_title: str
    platform: str
    pid: int
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    emulator: Optional[str] = None
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
        emulator: Optional[str] = None
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
            is_mame=is_mame
        )
        
        self._tracked_games[pid] = tracked
        logger.info(
            f"Tracking game: {game_title} (pid={pid}, mame={is_mame})"
        )
    
    def untrack_game(self, pid: int) -> Optional[TrackedGame]:
        """Stop tracking a game and return its info."""
        return self._tracked_games.pop(pid, None)
    
    def _is_mame_emulator(self, emulator: Optional[str], platform: str) -> bool:
        """Determine if the emulator is MAME (scores handled by Lua plugin)."""
        if not emulator:
            emulator = ""
        
        emulator_lower = emulator.lower()
        platform_lower = platform.lower()
        
        # MAME variants
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
                    # Also check if process is a zombie or terminated
                    if proc.status() in [psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD]:
                        exited.append((pid, tracked))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    exited.append((pid, tracked))
        
        for pid, tracked in exited:
            self.untrack_game(pid)
            await self._on_game_exit(tracked)
    
    async def _on_game_exit(self, tracked: TrackedGame) -> None:
        """Handle game exit - trigger appropriate score capture."""
        play_duration = (datetime.now(timezone.utc) - tracked.started_at).total_seconds()
        
        logger.info(
            f"Game exited: {tracked.game_title} after {play_duration:.0f}s "
            f"(mame={tracked.is_mame})"
        )
        
        if tracked.is_mame:
            # MAME games: Lua plugin handles score capture
            # Just log the exit for telemetry
            logger.debug("MAME game - score handled by Lua plugin")
            await self._sync_mame_hiscores(tracked)
            await self._log_game_session(tracked, play_duration)
        else:
            # Non-MAME games: Trigger Vision score extraction
            logger.info(f"Non-MAME game exit - triggering Vision capture for {tracked.game_title}")
            await self._trigger_vision_capture(tracked)
            await self._log_game_session(tracked, play_duration)

    async def _sync_mame_hiscores(self, tracked: TrackedGame) -> None:
        """Trigger an immediate MAME hiscore sync on game exit."""
        try:
            from backend.services.hiscore_watcher import get_watcher

            watcher = get_watcher()
            result = watcher.sync_all()
            games = list(result.keys()) if isinstance(result, dict) else []

            # Broadcast update to ScoreKeeper Sam via Gateway
            try:
                await asyncio.to_thread(
                    httpx.post,
                    "http://localhost:8787/api/scorekeeper/broadcast",
                    json={
                        "type": "score_updated",
                        "games": games,
                        "source": "game_exit",
                        "game_title": tracked.game_title,
                        "game_id": tracked.game_id
                    },
                    timeout=2.0
                )
            except Exception as e:
                logger.debug(f"Score broadcast failed (non-critical): {e}")
        except Exception as e:
            logger.warning(f"MAME hiscore sync on exit failed: {e}")
    
    async def _trigger_vision_capture(self, tracked: TrackedGame) -> None:
        """Trigger AI Vision score extraction for non-MAME games."""
        try:
            from backend.services.vision_score_service import get_vision_score_service
            
            vision_service = get_vision_score_service()
            if not vision_service:
                logger.warning("Vision score service not available")
                return
            
            # Slight delay to ensure game window has closed
            await asyncio.sleep(0.5)
            
            # Capture and extract score
            result = await vision_service.process_game_exit(
                game_rom=tracked.game_id,
                player_name=None  # Could get from active profile
            )

            if result:
                logger.info(
                    f"Vision captured score for {tracked.game_title}: "
                    f"{result.get('score')}"
                )

                await self._submit_score_to_scorekeeper(tracked, result)

                # Generate AI commentary
                await self._announce_score(tracked, result)
            else:
                logger.debug(f"No score captured for {tracked.game_title}")
                
        except Exception as e:
            logger.error(f"Vision capture failed: {e}")

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
    emulator: Optional[str] = None
) -> None:
    """Convenience function to track a game launch."""
    service = get_game_lifecycle()
    service.track_game(game_id, game_title, platform, pid, emulator)
