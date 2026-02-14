from __future__ import annotations

import re
from typing import Dict


def normalize_platform(name: str) -> str:
    """Historical helper: normalize PS2 synonyms.

    Kept for backward compatibility; prefer normalize_key for adapter matching.
    """
    if not isinstance(name, str):
        return name
    n = name.strip().lower()
    ps2 = {
        "playstation 2",
        "sony playstation 2",
        "ps2",
        "playstation2",
    }
    if n in ps2:
        return "Sony PlayStation 2"
    return name


_PLATFORM_SYNONYMS: Dict[str, str] = {
    # PS1
    "sony playstation": "sony playstation",
    "playstation": "sony playstation",
    "ps1": "sony playstation",
    "psx": "sony playstation",
    # GameCube
    "nintendo gamecube": "nintendo gamecube",
    "gamecube": "nintendo gamecube",
    # Wii
    "nintendo wii": "nintendo wii",
    "wii": "nintendo wii",
    # Naomi
    "sega naomi": "sega naomi",
    "naomi": "sega naomi",
    # Atomiswave
    "sammy atomiswave": "sammy atomiswave",
    "atomiswave": "sammy atomiswave",
    # Model 2
    "sega model 2": "sega model 2",
    "model 2": "sega model 2",
    # Model 3
    "sega model 3": "sega model 3",
    "model 3": "sega model 3",
    # Dreamcast
    "sega dreamcast": "sega dreamcast",
    "dreamcast": "sega dreamcast",
}


def normalize_key(name: str) -> str:
    """Normalize platform name into a lowercase canonical key for adapter matching.

    - Strips trailing qualifiers like 'Gun Games', '(Light Guns)'.
    - Applies known synonym folding (e.g., 'psx' -> 'sony playstation').
    - Returns the best-effort canonical key (lowercase string).
    """
    if not isinstance(name, str) or not name:
        return ""
    s = name.strip().lower()
    # Remove '(light guns)' and similar parentheticals
    s = re.sub(r"\(.*?light\s*guns.*?\)", "", s)
    # Remove 'light gun games' / 'gun games'
    s = s.replace("light gun games", "").replace("gun games", "")
    s = s.strip()
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s)
    # Apply synonyms
    return _PLATFORM_SYNONYMS.get(s, s)
