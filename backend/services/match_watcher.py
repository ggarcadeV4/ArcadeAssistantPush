"""
Match Result Watcher for ScoreKeeper Sam

Watches match_results.json written by MAME Tournament Mode plugin
and integrates results into Sam's tournament bracket system.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Callable
from threading import Thread, Event
import structlog

logger = structlog.get_logger(__name__)


class MatchResultWatcher:
    """
    Watches for match results from MAME Tournament Mode plugin.
    
    When a match ends (health = 0 detected, or manual confirmation),
    the Lua plugin writes to match_results.json. This watcher picks
    up the result and can notify ScoreKeeper Sam to update the bracket.
    """
    
    def __init__(self, drive_root: str = "A:"):
        self.drive_root = Path(drive_root)
        self.results_path = self.drive_root / ".aa" / "state" / "scorekeeper" / "match_results.json"
        self.current_match_path = self.drive_root / ".aa" / "state" / "scorekeeper" / "current_match.json"
        
        self.running = False
        self.stop_event = Event()
        self.watcher_thread: Optional[Thread] = None
        
        self.poll_interval = 2  # seconds
        self.last_result_time: Optional[str] = None
        self.callbacks: list[Callable[[Dict], None]] = []
        
        # Ensure paths exist
        self.results_path.parent.mkdir(parents=True, exist_ok=True)
    
    def register_callback(self, callback: Callable[[Dict], None]):
        """Register a callback to be called when a match result is detected."""
        self.callbacks.append(callback)
    
    def set_current_match(self, p1_name: str, p2_name: str, 
                          tournament_id: str = None, match_id: str = None):
        """
        Set the current match for MAME to display.
        
        This writes to current_match.json which the Lua plugin reads
        to show the matchup in the Tab menu.
        """
        match_data = {
            "p1_name": p1_name,
            "p2_name": p2_name,
            "tournament_id": tournament_id or "manual",
            "match_id": match_id or f"match_{datetime.now().strftime('%H%M%S')}",
            "started_at": datetime.now().isoformat(),
            "status": "active"
        }
        
        with open(self.current_match_path, 'w') as f:
            json.dump(match_data, f, indent=2)
        
        logger.info("current_match_set", p1=p1_name, p2=p2_name)
        return match_data
    
    def get_current_match(self) -> Optional[Dict]:
        """Get the current match info."""
        if not self.current_match_path.exists():
            return None
        
        try:
            with open(self.current_match_path, 'r') as f:
                return json.load(f)
        except:
            return None
    
    def clear_current_match(self):
        """Clear the current match."""
        if self.current_match_path.exists():
            self.current_match_path.unlink()
        logger.info("current_match_cleared")
    
    def _check_for_result(self) -> Optional[Dict]:
        """Check if there's a new match result."""
        if not self.results_path.exists():
            return None
        
        try:
            with open(self.results_path, 'r') as f:
                result = json.load(f)
            
            # Check if this is a new result
            result_time = result.get("timestamp")
            if result_time and result_time != self.last_result_time:
                self.last_result_time = result_time
                logger.info("match_result_detected",
                           winner=result.get("winner_name"),
                           game=result.get("game"))
                return result
            
        except Exception as e:
            logger.debug("result_check_error", error=str(e))
        
        return None
    
    def _watch_loop(self):
        """Main watch loop - runs in background thread."""
        logger.info("match_watcher_started", path=str(self.results_path))
        
        while not self.stop_event.is_set():
            try:
                result = self._check_for_result()
                if result:
                    # Notify all callbacks
                    for callback in self.callbacks:
                        try:
                            callback(result)
                        except Exception as e:
                            logger.error("callback_error", error=str(e))
            except Exception as e:
                logger.error("watch_error", error=str(e))
            
            self.stop_event.wait(self.poll_interval)
        
        logger.info("match_watcher_stopped")
    
    def start(self):
        """Start the watcher in a background thread."""
        if self.running:
            return
        
        self.running = True
        self.stop_event.clear()
        self.watcher_thread = Thread(target=self._watch_loop, daemon=True)
        self.watcher_thread.start()
    
    def stop(self):
        """Stop the watcher."""
        if not self.running:
            return
        
        self.running = False
        self.stop_event.set()
        if self.watcher_thread:
            self.watcher_thread.join(timeout=10)
    
    def get_status(self) -> Dict:
        """Get watcher status."""
        return {
            "running": self.running,
            "results_path": str(self.results_path),
            "current_match_path": str(self.current_match_path),
            "last_result_time": self.last_result_time,
            "poll_interval": self.poll_interval
        }


# Global instance
_match_watcher: Optional[MatchResultWatcher] = None


def get_match_watcher(drive_root: str = "A:") -> MatchResultWatcher:
    """Get or create the match watcher instance."""
    global _match_watcher
    if _match_watcher is None:
        _match_watcher = MatchResultWatcher(drive_root)
    return _match_watcher


def start_match_watcher(drive_root: str = "A:") -> MatchResultWatcher:
    """Start the match watcher."""
    watcher = get_match_watcher(drive_root)
    watcher.start()
    return watcher


def stop_match_watcher():
    """Stop the match watcher."""
    global _match_watcher
    if _match_watcher:
        _match_watcher.stop()
