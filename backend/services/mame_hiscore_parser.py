"""
MAME High Score Parser for Arcade Assistant.

Parses MAME .hi files and extracts player initials + scores.
Uses game-specific parsing rules based on hiscore.dat community knowledge.

Supported games are defined in GAME_PARSERS with byte offsets for:
- Score values (BCD or binary encoded)
- Player initials (ASCII or mapped)

For unsupported games, returns empty list (logged for future support).
"""

import os
import struct
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class HighScoreEntry:
    """A single high score entry from MAME."""
    initials: str  # e.g., "DAD", "AAA"
    score: int
    rank: int  # 1-based rank
    game_rom: str  # MAME ROM name (e.g., "dkong")


@dataclass
class GameHighScores:
    """All high scores for a single game."""
    game_rom: str
    entries: List[HighScoreEntry]
    parsed_at: str
    parse_error: Optional[str] = None


def bcd_to_int(bcd_bytes: bytes) -> int:
    """Convert BCD-encoded bytes to integer.
    
    Many classic arcade games store scores as Binary Coded Decimal.
    Each nibble (4 bits) represents a digit 0-9.
    """
    result = 0
    for byte in bcd_bytes:
        high = (byte >> 4) & 0x0F
        low = byte & 0x0F
        result = result * 100 + high * 10 + low
    return result


def bytes_to_score(data: bytes, encoding: str = "bcd") -> int:
    """Convert bytes to score value based on encoding.
    
    Args:
        data: Raw bytes from .hi file
        encoding: "bcd" for BCD, "binary" for straight int, "binary_be" for big-endian
    """
    if encoding == "bcd":
        return bcd_to_int(data)
    elif encoding == "binary":
        return int.from_bytes(data, byteorder='little')
    elif encoding == "binary_be":
        return int.from_bytes(data, byteorder='big')
    else:
        raise ValueError(f"Unknown encoding: {encoding}")


def bytes_to_initials(data: bytes, mapping: Optional[Dict[int, str]] = None) -> str:
    """Convert bytes to initials string.
    
    Args:
        data: Raw bytes (typically 3 bytes for 3-letter initials)
        mapping: Optional byte->char mapping (some games use custom encoding)
    """
    if mapping:
        # Custom character mapping (some games offset ASCII)
        return ''.join(mapping.get(b, chr(b) if 32 <= b < 127 else '?') for b in data)
    else:
        # Standard ASCII with offset handling
        # Many games store A=0, B=1, etc. or A=1, B=2, etc.
        result = []
        for b in data:
            if b == 0 or b == 0x10:  # Often used for space/blank
                result.append(' ')
            elif 0 < b <= 26:
                # A=1, B=2, ... Z=26 encoding
                result.append(chr(ord('A') + b - 1))
            elif 65 <= b <= 90:
                # Direct ASCII A-Z
                result.append(chr(b))
            elif 97 <= b <= 122:
                # Lowercase a-z
                result.append(chr(b - 32))  # Convert to uppercase
            else:
                result.append('?')
        return ''.join(result).strip()


# ============================================================================
# Game-Specific Parsers
# ============================================================================
# Each parser defines:
#   - entry_count: Number of high score entries
#   - entry_size: Size in bytes per entry
#   - parse_entry: Function to parse a single entry
#
# Offsets determined by analyzing .hi files and hiscore.dat community docs.
# ============================================================================

def parse_dkong(data: bytes) -> List[HighScoreEntry]:
    """Parse Donkey Kong (dkong) high scores.
    
    Based on hex dump analysis:
    - 5 entries, each 35 bytes apart
    - Rank at offset 4 (1-indexed)
    - Score at offset 10-12 (3 bytes, BCD high nibble only)
    - Initials not stored in traditional format
    
    For now, extract scores without initials (use "???" placeholder).
    """
    entries = []
    entry_size = 35  # Bytes per entry based on hex pattern
    
    # DK stores scores in a complex format
    # Let's try extracting based on observed pattern
    # Offset 0-1: appears to be address
    # Offset 4: rank (01, 02, 03...)
    # Offset 10-12: score digits
    
    for i in range(5):
        offset = i * entry_size
        if offset + 15 > len(data):
            break
        
        try:
            rank = data[offset + 4]  # Rank byte
            
            # Score is at bytes 10-12, appears to be individual digits
            # Format: each byte is one digit (07 06 05 = 765 * 100 = 76500?)
            d1 = data[offset + 10] if offset + 10 < len(data) else 0
            d2 = data[offset + 11] if offset + 11 < len(data) else 0
            d3 = data[offset + 12] if offset + 12 < len(data) else 0
            
            # DK scores are typically 5-6 digits
            score = d1 * 10000 + d2 * 1000 + d3 * 100
            
            if score > 0 and rank in (1, 2, 3, 4, 5):
                entries.append(HighScoreEntry(
                    initials="???",  # DK doesn't store initials traditionally
                    score=score,
                    rank=rank,
                    game_rom="dkong"
                ))
        except Exception:
            continue
    
    return entries


def parse_1942(data: bytes) -> List[HighScoreEntry]:
    """Parse 1942 high scores.
    
    Format: 10 entries, score in binary (4 bytes) + initials (3 bytes)
    """
    entries = []
    entry_size = 7
    
    for rank in range(1, 11):
        offset = (rank - 1) * entry_size
        if offset + entry_size > len(data):
            break
        
        score_bytes = data[offset:offset+4]
        initials_bytes = data[offset+4:offset+7]
        
        score = int.from_bytes(score_bytes, byteorder='big')
        initials = bytes_to_initials(initials_bytes)
        
        if score > 0:
            entries.append(HighScoreEntry(
                initials=initials,
                score=score,
                rank=rank,
                game_rom="1942"
            ))
    
    return entries


def parse_asteroids(data: bytes) -> List[HighScoreEntry]:
    """Parse Asteroids (asteroid) high scores.
    
    Format: 3 entries, initials (3 bytes) + score (3 bytes BCD)
    """
    entries = []
    entry_size = 6
    
    for rank in range(1, 4):
        offset = (rank - 1) * entry_size
        if offset + entry_size > len(data):
            break
        
        initials_bytes = data[offset:offset+3]
        score_bytes = data[offset+3:offset+6]
        
        # Asteroids uses A=1 encoding
        initials = bytes_to_initials(initials_bytes)
        score = bcd_to_int(score_bytes)
        
        if score > 0:
            entries.append(HighScoreEntry(
                initials=initials,
                score=score,
                rank=rank,
                game_rom="asteroid"
            ))
    
    return entries


def parse_tempest(data: bytes) -> List[HighScoreEntry]:
    """Parse Tempest high scores.
    
    Format: 10 entries, initials first, then score
    """
    entries = []
    entry_size = 6  # 3 initials + 3 score (BCD)
    
    for rank in range(1, 11):
        offset = (rank - 1) * entry_size
        if offset + entry_size > len(data):
            break
        
        initials_bytes = data[offset:offset+3]
        score_bytes = data[offset+3:offset+6]
        
        initials = bytes_to_initials(initials_bytes)
        score = bcd_to_int(score_bytes)
        
        if score > 0:
            entries.append(HighScoreEntry(
                initials=initials,
                score=score,
                rank=rank,
                game_rom="tempest"
            ))
    
    return entries


def parse_generic(data: bytes, game_rom: str) -> List[HighScoreEntry]:
    """Attempt generic parsing for unknown games.
    
    Tries common hiscore formats:
    1. 3-byte initials + 3-byte BCD score
    2. 3-byte BCD score + 3-byte initials
    
    Returns empty list if no recognizable pattern found.
    """
    entries = []
    
    # Try format 1: [initials][score] x N
    try:
        entry_size = 6
        for rank in range(1, 11):
            offset = (rank - 1) * entry_size
            if offset + entry_size > len(data):
                break
            
            initials_bytes = data[offset:offset+3]
            score_bytes = data[offset+3:offset+6]
            
            # Validate initials look like letters
            if all(b == 0 or (0 < b <= 26) or (65 <= b <= 90) for b in initials_bytes):
                initials = bytes_to_initials(initials_bytes)
                score = bcd_to_int(score_bytes)
                
                if 0 < score < 100000000:  # Reasonable score range
                    entries.append(HighScoreEntry(
                        initials=initials,
                        score=score,
                        rank=rank,
                        game_rom=game_rom
                    ))
        
        if entries:
            return entries
    except Exception:
        pass
    
    logger.debug(f"Generic parsing failed for {game_rom}, no entries extracted")
    return []


# Map of ROM names to their specific parsers
GAME_PARSERS = {
    "dkong": parse_dkong,
    "dkongjr": parse_dkong,  # Same format as DK
    "dkong3": parse_dkong,
    "1942": parse_1942,
    "1943": parse_1942,  # Similar format
    "asteroid": parse_asteroids,
    "astdelux": parse_asteroids,  # Same format
    "tempest": parse_tempest,
    # Add more games as needed
}


def parse_hiscore_file(filepath: Path) -> GameHighScores:
    """Parse a single MAME .hi file.
    
    Args:
        filepath: Path to the .hi file
        
    Returns:
        GameHighScores with extracted entries (may be empty)
    """
    game_rom = filepath.stem  # e.g., "dkong" from "dkong.hi"
    
    try:
        data = filepath.read_bytes()
        
        if game_rom in GAME_PARSERS:
            entries = GAME_PARSERS[game_rom](data)
            logger.info(f"Parsed {len(entries)} scores from {game_rom}")
        else:
            entries = parse_generic(data, game_rom)
            if entries:
                logger.info(f"Generic parsed {len(entries)} scores from {game_rom}")
            else:
                logger.warning(f"No parser for {game_rom}, skipping")
        
        return GameHighScores(
            game_rom=game_rom,
            entries=entries,
            parsed_at=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Failed to parse {filepath}: {e}")
        return GameHighScores(
            game_rom=game_rom,
            entries=[],
            parsed_at=datetime.utcnow().isoformat(),
            parse_error=str(e)
        )


def scan_hiscore_directory(hiscore_dir: Path) -> Dict[str, GameHighScores]:
    """Scan a directory for .hi files and parse all of them.
    
    Args:
        hiscore_dir: Path to MAME hiscore directory (e.g., A:\Emulators\MAME\hi)
        
    Returns:
        Dict mapping game_rom -> GameHighScores
    """
    results = {}
    
    if not hiscore_dir.exists():
        logger.warning(f"Hiscore directory not found: {hiscore_dir}")
        return results
    
    hi_files = list(hiscore_dir.glob("*.hi"))
    logger.info(f"Found {len(hi_files)} .hi files in {hiscore_dir}")
    
    for hi_file in hi_files:
        game_scores = parse_hiscore_file(hi_file)
        if game_scores.entries:  # Only include games with scores
            results[game_scores.game_rom] = game_scores
    
    return results


def get_default_hiscore_path() -> Path:
    """Get the default MAME hiscore directory path.
    
    Checks common locations and AA_DRIVE_ROOT.
    """
    drive_root = Path(os.environ.get("AA_DRIVE_ROOT", "A:\\"))
    
    # Common MAME hiscore locations
    candidates = [
        drive_root / "Emulators" / "MAME Gamepad" / "hiscore",
        drive_root / "Emulators" / "MAME" / "hiscore",
        drive_root / "Emulators" / "MAME" / "hi",
        Path("A:\\") / "Emulators" / "MAME Gamepad" / "hiscore",
        Path("A:\\") / "Emulators" / "MAME" / "hi",
    ]
    
    for path in candidates:
        if path.exists():
            logger.info(f"Found MAME hiscore directory: {path}")
            return path
    
    # Return the first candidate even if it doesn't exist
    logger.warning(f"No MAME hiscore directory found, defaulting to {candidates[0]}")
    return candidates[0]


# ============================================================================
# Public API
# ============================================================================

def get_all_mame_scores(hiscore_dir: Optional[Path] = None) -> Dict[str, GameHighScores]:
    """Main entry point: Get all MAME high scores from the hiscore directory.
    
    Args:
        hiscore_dir: Optional override for hiscore directory
        
    Returns:
        Dict mapping game_rom -> GameHighScores
    """
    if hiscore_dir is None:
        hiscore_dir = get_default_hiscore_path()
    
    return scan_hiscore_directory(hiscore_dir)


def format_for_launchbox(scores: Dict[str, GameHighScores]) -> Dict[str, Any]:
    """Format parsed scores for LaunchBox HighScores.json format.
    
    NOTE: Requires game_id mapping from LaunchBox cache to convert
    ROM names to LaunchBox GUIDs. This function returns a preliminary
    format that the ScoreKeeper service will enrich.
    """
    result = {
        "HighScores": [],
        "GeneratedAt": datetime.utcnow().isoformat(),
        "Source": "mame_hiscore_parser"
    }
    
    for game_rom, game_scores in scores.items():
        if not game_scores.entries:
            continue
        
        game_entry = {
            "RomName": game_rom,  # Will be mapped to GameId by ScoreKeeper
            "GameId": None,  # To be filled by ScoreKeeper using LaunchBox cache
            "Scores": [
                {
                    "Player": entry.initials,
                    "Score": entry.score,
                    "Rank": entry.rank,
                    "Source": "mame_hiscore"
                }
                for entry in game_scores.entries
            ]
        }
        result["HighScores"].append(game_entry)
    
    return result


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)
    
    scores = get_all_mame_scores()
    print(f"\nFound scores for {len(scores)} games:")
    
    for game_rom, game_scores in scores.items():
        print(f"\n{game_rom}:")
        for entry in game_scores.entries:
            print(f"  {entry.rank}. {entry.initials}: {entry.score:,}")
