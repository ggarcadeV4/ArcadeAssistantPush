"""
Score Service
Handles score reset operations with backup and AI state management.

@service: score_service
@role: Score reset, backup, and state management
@owner: Arcade Assistant / ScoreKeeper Sam
"""

import os
import shutil
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Request

from backend.constants.drive_root import get_drive_root
logger = logging.getLogger(__name__)

def _get_drive_root() -> Path:
    return get_drive_root(context="score_service")


def get_hiscore_dir() -> Path:
    return _get_drive_root() / "Emulators" / "MAME Gamepad" / "hiscore"


def get_backup_dir() -> Path:
    return _get_drive_root() / ".aa" / "backups" / "scores"


def get_ai_state_file() -> Path:
    return _get_drive_root() / ".aa" / "state" / "scorekeeper" / "mame_scores.json"


def get_live_score_file() -> Path:
    return _get_drive_root() / ".aa" / "state" / "scorekeeper" / "mame_live_score.json"


class ScoreService:
    """Manages high score files and AI state."""

    def _resolve_drive_root(self, request: Optional[Request] = None) -> Path:
        if request is not None and hasattr(request.app.state, "drive_root"):
            return Path(request.app.state.drive_root)
        return _get_drive_root()

    def _log_change(
        self,
        request: Optional[Request],
        drive_root: Path,
        action: str,
        details: dict,
        backup_path: Optional[Path] = None,
    ) -> None:
        log_file = drive_root / ".aa" / "logs" / "changes.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "scope": "scores",
            "action": action,
            "details": details,
            "backup_path": str(backup_path) if backup_path else None,
            "device": request.headers.get("x-device-id", "unknown") if request is not None else "unknown",
            "panel": request.headers.get("x-panel", "unknown") if request is not None else "unknown",
        }
        with open(log_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    
    def reset_score(self, rom_name: str, *, request: Optional[Request] = None, dry_run: bool = False) -> dict:
        """
        Safely resets a game's high score:
        1. Archives the existing .hi file to /backups/
        2. Deletes the active .hi file (forcing MAME to use factory defaults)
        3. Clears the game from the AI's awareness (mame_scores.json)
        
        Args:
            rom_name: The MAME ROM name (e.g., galaga, pacman)
            
        Returns:
            Dict with backup_created, file_deleted, ai_state_cleared, message
        """
        drive_root = self._resolve_drive_root(request)
        rom_name = rom_name.lower().strip()
        hi_file = drive_root / "Emulators" / "MAME Gamepad" / "hiscore" / f"{rom_name}.hi"
        ai_state_file = drive_root / ".aa" / "state" / "scorekeeper" / "mame_scores.json"
        
        result = {
            "game": rom_name,
            "backup_created": False,
            "backup_path": None,
            "file_deleted": False,
            "ai_state_cleared": False,
            "message": "",
            "dry_run": dry_run,
        }

        ai_state_present = False
        try:
            if ai_state_file.exists():
                with open(ai_state_file, 'r') as f:
                    ai_data = json.load(f)
                ai_state_present = rom_name in ai_data
        except Exception:
            ai_state_present = False

        if dry_run:
            result["file_exists"] = hi_file.exists()
            result["would_backup"] = hi_file.exists()
            result["ai_state_present"] = ai_state_present
            if hi_file.exists():
                result["message"] = "Preview: reset would back up and delete the active .hi file."
            elif ai_state_present:
                result["message"] = "Preview: no .hi file exists, but AI state would be cleared."
            else:
                result["message"] = "Preview: no score artifacts found for this game."
            self._log_change(
                request,
                drive_root,
                "score_reset_preview",
                {
                    "game": rom_name,
                    "file_exists": hi_file.exists(),
                    "ai_state_present": ai_state_present,
                },
            )
            return result

        # STEP 1: BACKUP AND DELETE .HI FILE
        if hi_file.exists():
            try:
                # Create timestamped backup folder
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                target_backup_dir = drive_root / ".aa" / "backups" / "scores" / rom_name
                target_backup_dir.mkdir(parents=True, exist_ok=True)
                
                backup_path = target_backup_dir / f"{timestamp}_{rom_name}.hi"
                shutil.copy2(hi_file, backup_path)
                result["backup_created"] = True
                result["backup_path"] = str(backup_path)
                
                # Delete the active file
                hi_file.unlink()
                result["file_deleted"] = True
                logger.info(f"Reset {rom_name}: Backed up to {backup_path} and deleted active file.")
                
            except Exception as e:
                logger.error(f"Failed to reset .hi file for {rom_name}: {e}")
                raise e
        else:
            logger.warning(f"Reset requested for {rom_name}, but no .hi file found.")

        # STEP 2: CLEAR AI STATE (JSON)
        result["ai_state_cleared"] = self._clear_json_entry(rom_name, drive_root=drive_root)
        
        if result["file_deleted"]:
            result["message"] = "Score reset successfully. Restart MAME for changes to take effect."
        elif result["ai_state_cleared"]:
            result["message"] = "No high score file existed, but AI state cleared."
        else:
            result["message"] = "No scores found for this game."

        self._log_change(
            request,
            drive_root,
            "score_reset_apply",
            {
                "game": rom_name,
                "file_deleted": result["file_deleted"],
                "ai_state_cleared": result["ai_state_cleared"],
            },
            Path(result["backup_path"]) if result.get("backup_path") else None,
        )
            
        return result

    def _clear_json_entry(self, rom_name: str, *, drive_root: Optional[Path] = None) -> bool:
        """
        Updates mame_scores.json to remove scores for this game.
        
        Our schema: {"galaga": [{score entries...}], "pacman": [...]}
        """
        try:
            root = drive_root or _get_drive_root()
            ai_state_file = root / ".aa" / "state" / "scorekeeper" / "mame_scores.json"

            if not ai_state_file.exists():
                logger.debug("AI state file doesn't exist, nothing to clear")
                return False

            with open(ai_state_file, 'r') as f:
                data = json.load(f)

            # Check if this game has entries
            if rom_name in data:
                del data[rom_name]
                
                with open(ai_state_file, 'w') as f:
                    json.dump(data, f, indent=2)
                    
                logger.info(f"Cleared AI state for {rom_name}")
                return True
            else:
                logger.debug(f"No AI state found for {rom_name}")
                return False
            
        except Exception as e:
            logger.error(f"Error clearing AI state: {e}")
            return False
    
    def reset_all_scores(self) -> dict:
        """
        Factory reset ALL high scores.
        
        Returns:
            Dict with list of reset games and backup location
        """
        result = {
            "games_reset": [],
            "backup_dir": str(get_backup_dir()),
            "ai_state_cleared": False,
            "message": ""
        }
        
        # Get all .hi files
        hiscore_dir = get_hiscore_dir()
        backup_dir = get_backup_dir()
        ai_state_file = get_ai_state_file()

        if hiscore_dir.exists():
            hi_files = list(hiscore_dir.glob("*.hi"))
            
            for hi_file in hi_files:
                rom_name = hi_file.stem
                try:
                    single_result = self.reset_score(rom_name)
                    if single_result["file_deleted"]:
                        result["games_reset"].append(rom_name)
                except Exception as e:
                    logger.error(f"Failed to reset {rom_name}: {e}")
        
        # Clear entire AI state file
        if ai_state_file.exists():
            try:
                # Backup the JSON too
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_json = backup_dir / f"{timestamp}_mame_scores.json"
                shutil.copy2(ai_state_file, backup_json)
                
                # Reset to empty
                with open(ai_state_file, 'w') as f:
                    json.dump({}, f)
                result["ai_state_cleared"] = True
            except Exception as e:
                logger.error(f"Failed to clear AI state: {e}")
        
        count = len(result["games_reset"])
        result["message"] = f"Factory reset complete. {count} games cleared. Restart MAME for changes to take effect."
        
        return result
    
    def get_backups(self, rom_name: str = None) -> list:
        """
        List available backups, optionally filtered by game.
        """
        backups = []
        
        backup_dir = get_backup_dir()
        if not backup_dir.exists():
            return backups
        
        if rom_name:
            game_dir = backup_dir / rom_name.lower()
            if game_dir.exists():
                for backup_file in game_dir.glob("*.hi"):
                    backups.append({
                        "game": rom_name,
                        "file": backup_file.name,
                        "path": str(backup_file),
                        "timestamp": backup_file.stat().st_mtime
                    })
        else:
            for game_dir in backup_dir.iterdir():
                if game_dir.is_dir():
                    for backup_file in game_dir.glob("*.hi"):
                        backups.append({
                            "game": game_dir.name,
                            "file": backup_file.name,
                            "path": str(backup_file),
                            "timestamp": backup_file.stat().st_mtime
                        })
        
        # Sort by timestamp descending
        backups.sort(key=lambda x: x["timestamp"], reverse=True)
        return backups
    
    def restore_backup(self, backup_path: str) -> dict:
        """
        Restore a specific backup.
        """
        backup_file = Path(backup_path)
        
        if not backup_file.exists():
            return {"success": False, "message": "Backup file not found"}
        
        # Extract game name from path
        rom_name = backup_file.parent.name
        target_file = get_hiscore_dir() / f"{rom_name}.hi"
        
        try:
            shutil.copy2(backup_file, target_file)
            return {
                "success": True,
                "game": rom_name,
                "message": f"Restored {rom_name} from backup. Restart MAME for changes to take effect."
            }
        except Exception as e:
            return {"success": False, "message": f"Restore failed: {e}"}


# Export Singleton
score_service = ScoreService()
