"""
MAME Hiscore Watcher Service

Watches MAME hiscore directories for .hi file changes and automatically
syncs them to mame_scores.json for ScoreKeeper Sam awareness.

This runs as a background service - start it once and forget about it.
The AI will always know the latest high scores.
"""

import os
import time
import json
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Set, Optional, List
from threading import Thread, Event
import structlog
import httpx
from .player_tendencies import get_active_session

logger = structlog.get_logger(__name__)


class HiscoreWatcher:
    """
    Watches MAME hiscore directories and auto-syncs to JSON.
    
    When any .hi file changes, it:
    1. Detects the change via file modification time
    2. Runs hi2txt to parse the score
    3. Updates mame_scores.json
    4. ScoreKeeper Sam can read the updated data
    """
    
    def __init__(self, drive_root: Optional[str] = None):
        if not drive_root:
            drive_root = os.getenv("AA_DRIVE_ROOT", r"A:\\")
        self.drive_root = Path(drive_root)
        self.running = False
        self.stop_event = Event()
        self.watcher_thread: Optional[Thread] = None
        
        # Paths to watch
        self.hiscore_dirs = [
            self.drive_root / "Emulators" / "MAME" / "hiscore",
            self.drive_root / "Emulators" / "MAME" / "hi",
            self.drive_root / "Emulators" / "MAME Gamepad" / "hiscore",
            self.drive_root / "Emulators" / "MAME Gamepad" / "hi",
        ]
        
        # Tools
        self.hi2txt_path = self.drive_root / "LaunchBox" / "ThirdParty" / "hi2txt" / "hi2txt.exe"
        self.output_path = self.drive_root / ".aa" / "state" / "scorekeeper" / "mame_scores.json"
        self.high_scores_index_file = self.output_path.parent / "high_scores_index.json"
        
        # State tracking
        self.last_modified: Dict[str, float] = {}
        self.poll_interval = 5  # seconds between checks
        
        # Ensure output directory exists
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._scores_jsonl_name = "scores.jsonl"
        self._lua_scores_path: Optional[Path] = None
        self._lua_last_mtime: Optional[float] = None
        self._lua_last_scores: Optional[dict] = None
        self._lua_initialized = False
        self._lua_poll_interval = 3
        self._lua_thread: Optional[Thread] = None
        self._rom_mapping: Optional[Dict[str, Dict[str, str]]] = None
        self._rom_mapping_loaded_at: Optional[float] = None
        self._rom_mapping_ttl_seconds = 300
        # Compatibility: older API expected a dat_parser attribute
        self.dat_parser = None

    def _normalize_rom_key(self, rom_name: Optional[str]) -> str:
        if not rom_name:
            return ""
        return str(rom_name).strip().lower()

    def get_scores_snapshot(self) -> Dict[str, list]:
        """Return current mame_scores.json contents (rom -> entries)."""
        scores = self._load_current_scores()
        return scores if isinstance(scores, dict) else {}

    def get_rom_mapping(self) -> Dict[str, Dict[str, str]]:
        """Public wrapper for ROM -> LaunchBox mapping."""
        return self._get_rom_mapping()

    def save_scores(self, scores: dict) -> None:
        """Public wrapper to persist scores and refresh scores.jsonl."""
        self._save_scores(scores)

    def get_game_scores(self, rom_name: str) -> List[dict]:
        """Return scores for a single ROM (case-insensitive)."""
        scores = self.get_scores_snapshot()
        rom_key = self._normalize_rom_key(rom_name)
        if not rom_key:
            return []
        direct = scores.get(rom_key)
        if isinstance(direct, list):
            return direct
        # Fallback: try case-insensitive search
        for key, entries in scores.items():
            if self._normalize_rom_key(key) == rom_key and isinstance(entries, list):
                return entries
        return []

    def scan_all_hiscores(self) -> Dict[str, list]:
        """Compatibility wrapper returning all parsed hi scores."""
        return self.get_scores_snapshot()
    
    def _parse_hi_file(self, hi_file: Path) -> Optional[dict]:
        """Parse a .hi file using hi2txt and return structured data."""
        if not self.hi2txt_path.exists():
            logger.error("hi2txt_not_found", path=str(self.hi2txt_path))
            return None
        
        try:
            result = subprocess.run(
                [str(self.hi2txt_path), "-r", str(hi_file)],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return None
            
            # Parse output: RANK|SCORE|NAME (NAME optional)
            entries = []
            for idx, line in enumerate(result.stdout.strip().split('\n')):
                if not line or line.startswith("RANK|"):
                    continue
                parts = [part.strip() for part in line.split('|')]
                if len(parts) >= 2:
                    try:
                        rank_text = parts[0]
                        rank_digits = ''.join(ch for ch in rank_text if ch.isdigit())
                        rank = int(rank_digits) if rank_digits else (idx + 1)
                        name = parts[2] if len(parts) >= 3 else "???"
                        entries.append({
                            "rank": rank,
                            "score": int(parts[1]),
                            "name": name or "???",
                            "rom": hi_file.stem,
                            "game_name": hi_file.stem,  # Could look up friendly name
                            "timestamp": datetime.now().isoformat(),
                            "source": "hi2txt"
                        })
                    except ValueError:
                        continue
            
            return {"entries": entries, "parsed_at": datetime.now().isoformat()}
            
        except Exception as e:
            logger.error("hi2txt_error", file=str(hi_file), error=str(e))
            return None
    
    def _get_all_hi_files(self) -> Dict[str, Path]:
        """Get all .hi files from all watched directories."""
        files = {}
        for hiscore_dir in self.hiscore_dirs:
            if not hiscore_dir.exists():
                continue
            for hi_file in hiscore_dir.glob("*.hi"):
                rom = hi_file.stem
                # Later file wins (more recent MAME installation)
                if rom not in files or hi_file.stat().st_mtime > files[rom].stat().st_mtime:
                    files[rom] = hi_file
        return files
    
    def _load_current_scores(self) -> dict:
        """Load current scores from JSON file."""
        if self.output_path.exists():
            try:
                with open(self.output_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}
    
    def _save_scores(self, scores: dict):
        """Save scores to JSON file."""
        with open(self.output_path, 'w') as f:
            json.dump(scores, f, indent=2)
        self._refresh_scores_jsonl(scores)

    def _is_mame_score_entry(self, entry: dict) -> bool:
        """Return True if the scores.jsonl entry is from MAME."""
        if not isinstance(entry, dict):
            return False
        game_id = (entry.get("game_id") or "").lower()
        if game_id.startswith("mame_"):
            return True
        if (entry.get("frontend_source") or "").lower() == "mame":
            return True
        if entry.get("game_rom"):
            return True
        return False

    def _is_persistent_entry(self, entry: dict) -> bool:
        """Filter out live-only entries that don't represent saved highscores."""
        if not isinstance(entry, dict):
            return False
        source = (entry.get("source") or "").lower()
        if source in {"mame_lua", "arcade_assistant_scores"} and not entry.get("name"):
            score = entry.get("score", 0)
            try:
                score = int(score)
            except Exception:
                score = 0
            return score > 0
        return True

    def _refresh_scores_jsonl(self, scores: dict) -> None:
        """Update scores.jsonl with the latest MAME highscores, preserving non-MAME entries."""
        if not isinstance(scores, dict):
            return

        scores_dir = self.output_path.parent
        scores_dir.mkdir(parents=True, exist_ok=True)
        scores_file = scores_dir / self._scores_jsonl_name

        # Keep non-MAME entries
        preserved = []
        if scores_file.exists():
            try:
                with open(scores_file, "r", encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except Exception:
                            continue
                        if not self._is_mame_score_entry(entry):
                            preserved.append(entry)
            except Exception:
                preserved = []

        # Build fresh MAME entries from mame_scores.json
        rom_mapping = self._get_rom_mapping()
        mame_entries = []
        for rom, entries in scores.items():
            if not isinstance(entries, list):
                continue
            rom_key = str(rom).lower()
            lb_info = rom_mapping.get(rom_key, {})
            game_title = lb_info.get("game_title") or rom
            game_id = lb_info.get("game_id") or f"mame_{rom}"
            for entry in entries:
                if not self._is_persistent_entry(entry):
                    continue
                player_name = entry.get("name") or entry.get("player") or "???"
                player_user_id = None
                player_source = None
                entry_source = (entry.get("source") or "").lower()
                game_initials = None
                normalized_player = str(player_name).strip().lower()
                if normalized_player and normalized_player not in {"??", "???", "unknown"}:
                    game_initials = str(player_name).strip()

                # Only hydrate from session if player_name is unknown/empty
                # This preserves game initials (AAA, JON, etc.) for historical entries
                # and only attributes new unknown scores to the active player
                should_hydrate_from_session = normalized_player in {"", "??", "???", "unknown"}
                
                if should_hydrate_from_session:
                    active_session = get_active_session()
                    if not active_session:
                        # Fallback: try primary profile
                        primary = self._load_primary_profile()
                        if primary and primary.get("display_name"):
                            player_name = primary.get("display_name")
                            player_user_id = primary.get("user_id")
                            player_source = "profile"
                    else:
                        player_name = active_session.get("player_name") or player_name
                        player_user_id = active_session.get("player_id")
                        player_source = "profile"
                mame_entries.append({
                    "timestamp": entry.get("timestamp") or datetime.now().isoformat(),
                    "game": game_title,
                    "game_id": game_id,
                    "game_rom": rom,
                    "player": player_name,
                    "score": entry.get("score", 0),
                    "rank": entry.get("rank", 0),
                    "source": entry.get("source") or "hi2txt",
                    "device_id": os.getenv("AA_DEVICE_ID", "unknown"),
                    "frontend_source": "mame"
                })
                if game_initials:
                    mame_entries[-1]["game_initials"] = game_initials
                if player_user_id:
                    mame_entries[-1]["player_userId"] = player_user_id
                if player_source:
                    mame_entries[-1]["player_source"] = player_source

        # Backup existing scores.jsonl before overwriting
        if scores_file.exists():
            backup_dir = self.drive_root / ".aa" / "backups" / "scores"
            try:
                backup_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = backup_dir / f"scores_backup_{timestamp}.jsonl"
                shutil.copy2(scores_file, backup_path)
            except Exception:
                pass

        # Write merged scores.jsonl (non-MAME + fresh MAME)
        tmp_path = scores_file.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as handle:
            for entry in preserved + mame_entries:
                handle.write(json.dumps(entry) + "\n")
        tmp_path.replace(scores_file)

    def _load_primary_profile(self) -> Optional[dict]:
        """Load primary profile if available (fallback when no active session)."""
        try:
            profile_path = self.drive_root / ".aa" / "state" / "profile" / "primary_user.json"
            if not profile_path.exists():
                return None
            with open(profile_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                return None
            return {
                "user_id": data.get("user_id"),
                "display_name": data.get("display_name"),
                "initials": data.get("initials")
            }
        except Exception:
            return None

    def _get_rom_mapping(self) -> Dict[str, Dict[str, str]]:
        """Map ROM name -> LaunchBox game_id/title if available."""
        now = time.time()
        if (
            self._rom_mapping is not None
            and self._rom_mapping_loaded_at is not None
            and now - self._rom_mapping_loaded_at < self._rom_mapping_ttl_seconds
        ):
            return self._rom_mapping

        mapping: Dict[str, Dict[str, str]] = {}
        try:
            from .launchbox_cache import get_games
            games = get_games()
            for game in games:
                app_path = game.get("ApplicationPath", "")
                if not app_path:
                    continue
                rom_name = Path(app_path).stem.lower()
                if not rom_name:
                    continue
                mapping[rom_name] = {
                    "game_id": game.get("Id") or game.get("id") or f"mame_{rom_name}",
                    "game_title": game.get("Title") or game.get("title") or rom_name
                }
        except Exception:
            mapping = {}

        self._rom_mapping = mapping
        self._rom_mapping_loaded_at = now
        return mapping

    def _sync_lua_scores(self, broadcast: bool = True) -> None:
        """Refresh scores.jsonl from the Lua plugin's mame_scores.json."""
        if not self._lua_scores_path:
            return
        if not self._lua_scores_path.exists():
            return
        try:
            with open(self._lua_scores_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as e:
            logger.warning("lua_score_watcher_read_failed", error=str(e))
            return
        if not isinstance(data, dict):
            return

        record_events = []
        previous_scores = self._lua_last_scores or {}
        if broadcast and self._lua_initialized:
            for rom, entries in data.items():
                if not isinstance(entries, list):
                    continue
                old_entries = previous_scores.get(rom)
                if not isinstance(old_entries, list):
                    old_entries = []
                event = self._build_record_event(rom, old_entries, entries)
                if event:
                    record_events.append(event)

        self._lua_last_scores = data
        self._lua_initialized = True
        self._refresh_scores_jsonl(data)
        self._broadcast_record_events(record_events)

    def _lua_watch_loop(self) -> None:
        """Watch the Lua scores file for changes and refresh scores.jsonl."""
        if not self._lua_scores_path:
            return
        logger.info(
            "lua_score_watcher_started",
            path=str(self._lua_scores_path),
            interval=self._lua_poll_interval
        )
        while not self.stop_event.is_set():
            try:
                if self._lua_scores_path.exists():
                    mtime = self._lua_scores_path.stat().st_mtime
                    if self._lua_last_mtime is None or mtime > self._lua_last_mtime:
                        self._lua_last_mtime = mtime
                        self._sync_lua_scores(broadcast=self._lua_initialized)
            except Exception as e:
                logger.warning("lua_score_watcher_error", error=str(e))
            self.stop_event.wait(self._lua_poll_interval)
        logger.info("lua_score_watcher_stopped")

    def start_lua_watcher(self, lua_scores_path: Path, poll_interval: int = 3) -> None:
        """Start a background watcher for the Lua plugin scores file."""
        self._lua_scores_path = Path(lua_scores_path)
        self._lua_poll_interval = poll_interval
        if self._lua_thread and self._lua_thread.is_alive():
            return
        self._lua_last_mtime = None
        self._lua_last_scores = None
        self._lua_initialized = False
        self._lua_thread = Thread(target=self._lua_watch_loop, daemon=True)
        self._lua_thread.start()
    
    def sync_all(self) -> dict:
        """
        Sync all .hi files to JSON.
        
        This does a full scan and update.
        """
        hi_files = self._get_all_hi_files()
        scores = {}
        
        for rom, hi_file in hi_files.items():
            result = self._parse_hi_file(hi_file)
            if result and result["entries"]:
                scores[rom] = result["entries"]
                logger.info("synced_game", rom=rom, entries=len(result["entries"]))
        
        self._save_scores(scores)
        logger.info("sync_complete", games=len(scores))
        return scores

    def _build_record_event(self, rom: str, old_entries: list, new_entries: list) -> Optional[dict]:
        """Return a score_record payload when the top score is beaten."""
        old_top = max(
            (
                (entry.get("score", 0) if isinstance(entry, dict) else 0)
                for entry in old_entries
            ),
            default=0
        )
        if not isinstance(new_entries, list) or not new_entries:
            return None
        top = max(
            (
                entry for entry in new_entries
                if isinstance(entry, dict)
            ),
            key=lambda x: x.get("score", 0),
            default=None
        )
        if not top:
            return None
        new_top = top.get("score", 0)
        if isinstance(new_top, str):
            try:
                new_top = int(new_top)
            except Exception:
                new_top = 0
        if new_top <= old_top:
            return None
        return {
            "rom": rom,
            "score": new_top,
            "player": top.get("name", "???"),
            "previous_top": old_top,
            "source": "watcher",
            "timestamp": datetime.now().isoformat()
        }

    def _broadcast_record_events(self, record_events: list) -> None:
        """Send score_record events to the ScoreKeeper WS bridge and Supabase."""
        if not record_events:
            return
        try:
            httpx.post(
                "http://localhost:8787/api/scorekeeper/broadcast",
                json={
                    "type": "score_record",
                    "records": record_events,
                    "source": "watcher"
                },
                timeout=2.0
            )
        except Exception as e:
            logger.warning("broadcast_failed", error=str(e))

        # Also push each record to Supabase scores table via gateway
        for record in record_events:
            try:
                httpx.post(
                    "http://localhost:8787/api/scorekeeper/supabase-sync",
                    json={
                        "game_id": record.get("rom", "unknown"),
                        "player": record.get("player", "???"),
                        "score": record.get("score", 0),
                        "meta": {
                            "source": "hiscore_watcher",
                            "previous_top": record.get("previous_top", 0),
                            "timestamp": record.get("timestamp")
                        }
                    },
                    timeout=3.0
                )
            except Exception as e:
                logger.debug("supabase_sync_failed", rom=record.get("rom"), error=str(e))
    
    def _check_for_changes(self) -> Set[str]:
        """Check which .hi files have changed since last check."""
        changed = set()
        hi_files = self._get_all_hi_files()
        
        for rom, hi_file in hi_files.items():
            try:
                mtime = hi_file.stat().st_mtime
                key = str(hi_file)
                
                if key not in self.last_modified:
                    # First time seeing this file
                    self.last_modified[key] = mtime
                elif mtime > self.last_modified[key]:
                    # File was modified
                    changed.add(rom)
                    self.last_modified[key] = mtime
                    logger.info("detected_change", rom=rom, file=str(hi_file))
            except:
                continue
        
        return changed
    
    def _update_changed_games(self, changed_roms: Set[str]):
        """Update just the games that changed."""
        if not changed_roms:
            return
        
        hi_files = self._get_all_hi_files()
        current_scores = self._load_current_scores()
        record_events = []
        
        for rom in changed_roms:
            if rom in hi_files:
                old_entries = current_scores.get(rom)
                if not isinstance(old_entries, list):
                    old_entries = []
                result = self._parse_hi_file(hi_files[rom])
                if result and result["entries"]:
                    event = self._build_record_event(rom, old_entries, result["entries"])
                    if event:
                        record_events.append(event)
                    current_scores[rom] = result["entries"]
                    # Get top score for logging
                    top_entry = max(result["entries"], key=lambda x: x.get("score", 0))
                    logger.info(
                        "updated_score",
                        rom=rom,
                        top_score=top_entry.get("score", 0),
                        top_player=top_entry.get("name")
                    )
        
        self._save_scores(current_scores)
        
        # Broadcast score update to frontend via Gateway Event Bus
        try:
            httpx.post(
                "http://localhost:8787/api/scorekeeper/broadcast",
                json={
                    "type": "score_updated",
                    "games": list(changed_roms),
                    "source": "watcher"
                },
                timeout=2.0
            )
            logger.info("broadcast_sent", games=list(changed_roms))
        except Exception as e:
            logger.warning("broadcast_failed", error=str(e))

        self._broadcast_record_events(record_events)

        # Trigger AI commentary for new high scores (fire-and-forget)
        for event in record_events:
            try:
                from .score_announcer import announce_high_score
                import asyncio
                rom = event.get("rom", "")
                rom_mapping = self._get_rom_mapping()
                game_name = rom_mapping.get(rom, {}).get("game_title", rom)
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(announce_high_score(
                        game_name=game_name,
                        score=event.get("score", 0),
                        initials=event.get("player", "???"),
                        rank=1,
                        speak=True
                    ))
                else:
                    asyncio.run(announce_high_score(
                        game_name=game_name,
                        score=event.get("score", 0),
                        initials=event.get("player", "???"),
                        rank=1,
                        speak=True
                    ))
            except Exception as e:
                logger.debug("score_announcer_failed", rom=event.get("rom"), error=str(e))
    
    def _watch_loop(self):
        """Main watch loop - runs in background thread."""
        logger.info("watcher_started", 
                   dirs=[str(d) for d in self.hiscore_dirs],
                   interval=self.poll_interval)
        
        # Initial sync
        self.sync_all()
        
        while not self.stop_event.is_set():
            try:
                changed = self._check_for_changes()
                if changed:
                    self._update_changed_games(changed)
            except Exception as e:
                logger.error("watch_error", error=str(e))
            
            # Wait for next check (interruptible)
            self.stop_event.wait(self.poll_interval)
        
        logger.info("watcher_stopped")
    
    def start(self):
        """Start the watcher in a background thread."""
        if self.running:
            return
        
        self.running = True
        self.stop_event.clear()
        self.watcher_thread = Thread(target=self._watch_loop, daemon=True)
        self.watcher_thread.start()
        logger.info("hiscore_watcher_started")
    
    def stop(self):
        """Stop the watcher."""
        if not self.running:
            return
        
        self.running = False
        self.stop_event.set()
        if self.watcher_thread:
            self.watcher_thread.join(timeout=10)
        if self._lua_thread:
            self._lua_thread.join(timeout=10)
        logger.info("hiscore_watcher_stopped")
    
    def get_status(self) -> dict:
        """Get current watcher status."""
        hi_files = self._get_all_hi_files()
        return {
            "running": self.running,
            "dirs_watched": [str(d) for d in self.hiscore_dirs if d.exists()],
            "games_tracked": list(hi_files.keys()),
            "poll_interval": self.poll_interval,
            "output_file": str(self.output_path)
        }


# Global watcher instance
_watcher: Optional[HiscoreWatcher] = None


def get_watcher(drive_root: Optional[str] = None) -> HiscoreWatcher:
    """Get or create the watcher instance."""
    global _watcher
    if _watcher is None:
        _watcher = HiscoreWatcher(drive_root)
    return _watcher


def start_watcher(drive_root: Optional[str] = None):
    """Start the hiscore watcher (call on app startup)."""
    watcher = get_watcher(drive_root)
    watcher.start()
    return watcher


def stop_watcher():
    """Stop the hiscore watcher (call on app shutdown)."""
    global _watcher
    if _watcher:
        _watcher.stop()


# Async initialization functions (for app.py compatibility)
async def initialize_hiscore_watcher(mame_root, scores_file, high_scores_index):
    """
    Initialize hiscore watcher for a specific MAME directory.
    Called by app.py on startup.
    
    Note: This now uses the unified hi2txt-based watcher instead of
    the old per-directory approach.
    """
    global _watcher
    if _watcher is None:
        _watcher = HiscoreWatcher()
    
    # Just start the watcher if not already running
    if not _watcher.running:
        _watcher.start()
    
    return _watcher


async def initialize_lua_score_watcher(lua_scores_json):
    """
    Initialize watcher for Lua plugin scores.
    
    Note: The hi2txt watcher now handles this automatically by
    scanning .hi files directly. This function is kept for
    backwards compatibility but just ensures the main watcher
    is running.
    """
    global _watcher
    if _watcher is None:
        _watcher = HiscoreWatcher()
    
    if not _watcher.running:
        _watcher.start()

    try:
        _watcher.start_lua_watcher(Path(lua_scores_json))
    except Exception as e:
        logger.warning("lua_score_watcher_start_failed", error=str(e))
    
    return _watcher


# Backward compatibility alias for hiscore.py router
def get_hiscore_watcher(drive_root: Optional[str] = None) -> HiscoreWatcher:
    """Alias for get_watcher - backward compatibility with hiscore.py."""
    return get_watcher(drive_root)

