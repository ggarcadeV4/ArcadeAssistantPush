"""
MAME Hi2txt Score Parser Service

Reads .hi files from MAME's hiscore folder using hi2txt.exe and
writes scores to mame_scores.json for ScoreKeeper Sam awareness.

This approach is more reliable than RAM reading because:
1. Works with any game supported by hiscore.dat
2. Uses MAME's proven hiscore plugin
3. No game-specific memory mapping needed
"""

import os
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class HiscoreEntry:
    """A single high score entry from a .hi file"""
    rank: int
    score: int
    name: str
    game_rom: str
    game_name: Optional[str] = None


@dataclass
class GameHiscores:
    """All high scores for a single game"""
    rom_name: str
    game_name: Optional[str]
    entries: List[HiscoreEntry]
    parsed_at: str
    parse_error: Optional[str] = None


class Hi2txtParser:
    """
    Parse MAME .hi files using hi2txt.exe
    
    hi2txt is bundled with LaunchBox and converts binary .hi files
    to human-readable text with scores, names, and ranks.
    """
    
    def __init__(self, drive_root: Optional[str] = None):
        if not drive_root:
            from backend.constants.drive_root import get_drive_root
            drive_root = str(get_drive_root(allow_cwd_fallback=True))
        self.drive_root = Path(drive_root)
        
        # Standard paths
        self.hi2txt_path = self.drive_root / "LaunchBox" / "ThirdParty" / "hi2txt" / "hi2txt.exe"
        self.hiscore_dirs = [
            self.drive_root / "Emulators" / "MAME Gamepad" / "hiscore",
            self.drive_root / "Emulators" / "MAME Gamepad" / "hi",
            self.drive_root / "Emulators" / "MAME" / "hiscore",
            self.drive_root / "Emulators" / "MAME" / "hi",
        ]
        self.output_path = self.drive_root / ".aa" / "state" / "scorekeeper" / "mame_scores.json"
        
        # Ensure output directory exists
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _find_hi2txt(self) -> Optional[Path]:
        """Find hi2txt.exe"""
        if self.hi2txt_path.exists():
            return self.hi2txt_path
        
        # Try alternate locations (all relative to drive root)
        alternates = [
            self.drive_root / "LaunchBox" / "Tools" / "hi2txt.exe",
        ]
        for alt in alternates:
            if alt.exists():
                return alt
        
        return None
    
    def _parse_hi_file(self, hi_file: Path) -> Optional[GameHiscores]:
        """Parse a single .hi file using hi2txt"""
        hi2txt = self._find_hi2txt()
        if not hi2txt:
            logger.error("hi2txt_not_found", searched=str(self.hi2txt_path))
            return None
        
        rom_name = hi_file.stem
        
        try:
            # Run hi2txt with -r flag (main high scores)
            result = subprocess.run(
                [str(hi2txt), "-r", str(hi_file)],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                logger.warning("hi2txt_failed", rom=rom_name, stderr=result.stderr)
                return GameHiscores(
                    rom_name=rom_name,
                    game_name=None,
                    entries=[],
                    parsed_at=datetime.now().isoformat(),
                    parse_error=result.stderr or "hi2txt returned non-zero"
                )
            
            # Parse output (pipe-separated: RANK|SCORE|NAME; NAME optional for some games)
            entries = []
            lines = result.stdout.strip().split('\n')
            
            for idx, line in enumerate(lines):
                line = line.strip()
                if not line or line.startswith("RANK|"):  # Skip header
                    continue
                
                parts = [part.strip() for part in line.split('|')]
                if len(parts) >= 2:
                    try:
                        rank_text = parts[0]
                        rank_digits = ''.join(ch for ch in rank_text if ch.isdigit())
                        rank = int(rank_digits) if rank_digits else (idx + 1)
                        score = int(parts[1])
                        name = parts[2] if len(parts) >= 3 else "???"
                        
                        entries.append(HiscoreEntry(
                            rank=rank,
                            score=score,
                            name=name or "???",
                            game_rom=rom_name
                        ))
                    except ValueError:
                        continue
            
            logger.info("hi_file_parsed", rom=rom_name, entries=len(entries))
            
            return GameHiscores(
                rom_name=rom_name,
                game_name=None,  # Could look up from LaunchBox cache
                entries=entries,
                parsed_at=datetime.now().isoformat()
            )
            
        except subprocess.TimeoutExpired:
            logger.error("hi2txt_timeout", rom=rom_name)
            return GameHiscores(
                rom_name=rom_name,
                game_name=None,
                entries=[],
                parsed_at=datetime.now().isoformat(),
                parse_error="hi2txt timed out"
            )
        except Exception as e:
            logger.error("hi2txt_exception", rom=rom_name, error=str(e))
            return GameHiscores(
                rom_name=rom_name,
                game_name=None,
                entries=[],
                parsed_at=datetime.now().isoformat(),
                parse_error=str(e)
            )
    
    def scan_all_hiscores(self) -> Dict[str, GameHiscores]:
        """Scan all hiscore directories and parse all .hi files"""
        all_scores = {}
        
        for hiscore_dir in self.hiscore_dirs:
            if not hiscore_dir.exists():
                logger.debug("hiscore_dir_missing", path=str(hiscore_dir))
                continue
            
            for hi_file in hiscore_dir.glob("*.hi"):
                rom_name = hi_file.stem
                
                # Skip if already parsed (first dir takes priority)
                if rom_name in all_scores:
                    continue
                
                result = self._parse_hi_file(hi_file)
                if result:
                    all_scores[rom_name] = result
        
        logger.info("hiscore_scan_complete", games=len(all_scores))
        return all_scores
    
    def update_scores_json(self) -> Dict:
        """
        Scan all .hi files and update mame_scores.json
        
        Returns the updated scores data
        """
        all_scores = self.scan_all_hiscores()
        
        # Convert to JSON-serializable format
        output_data = {}
        
        for rom_name, game_scores in all_scores.items():
            entries = []
            for entry in game_scores.entries:
                entries.append({
                    "rank": entry.rank,
                    "score": entry.score,
                    "name": entry.name,
                    "rom": rom_name,
                    "game_name": game_scores.game_name or rom_name,
                    "timestamp": game_scores.parsed_at,
                    "source": "hi2txt"
                })
            
            if entries:
                output_data[rom_name] = entries
        
        # Write to file
        with open(self.output_path, 'w') as f:
            json.dump(output_data, f, indent=2)
        
        logger.info("scores_json_updated", 
                   games=len(output_data),
                   path=str(self.output_path))
        
        return output_data
    
    def get_game_scores(self, rom_name: str) -> Optional[GameHiscores]:
        """Get scores for a specific game"""
        for hiscore_dir in self.hiscore_dirs:
            hi_file = hiscore_dir / f"{rom_name}.hi"
            if hi_file.exists():
                return self._parse_hi_file(hi_file)
        return None


# Singleton instance
_parser: Optional[Hi2txtParser] = None


def get_parser(drive_root: Optional[str] = None) -> Hi2txtParser:
    """Get or create the Hi2txt parser instance"""
    global _parser
    if _parser is None:
        _parser = Hi2txtParser(drive_root)
    return _parser


def sync_hiscores(drive_root: Optional[str] = None) -> Dict:
    """
    Main entry point: Sync all MAME high scores to mame_scores.json
    
    Call this on a schedule or when games exit.
    """
    parser = get_parser(drive_root)
    return parser.update_scores_json()
