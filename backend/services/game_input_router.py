"""
Game Input Router

Determines whether a game should use ENCODER input (arcade panel) or
GAMEPAD input (Xbox/PS controller) based on platform, emulator, and game metadata.

This enables Controller Chuck's encoder config to automatically disseminate
to all arcade emulators, while Console Wizard's gamepad config goes to console emulators.

Architecture:
- Platform-based routing (fast, simple)
- Game metadata override (per-game control)
- RetroArch core awareness (arcade vs console cores)

Usage:
    from backend.services.game_input_router import get_input_type, InputType
    
    input_type = get_input_type(game_title="Initial D 8", platform="teknoparrot")
    if input_type == InputType.ENCODER:
        # Use Chuck's controls.json
    else:
        # Use Console Wizard's gamepad profile
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Input Type Enum
# -----------------------------------------------------------------------------

class InputType(str, Enum):
    """Primary input type for a game."""
    ENCODER = "encoder"      # Arcade panel (joystick + buttons wired to encoder)
    GAMEPAD = "gamepad"      # Console controller (Xbox, PS, Switch)
    KEYBOARD = "keyboard"    # PC keyboard (for PC games)
    WHEEL = "wheel"          # Racing wheel (specialized)
    LIGHTGUN = "lightgun"    # Light gun (Sinden, GunCon, etc.)
    HYBRID = "hybrid"        # Accepts multiple input types
    UNKNOWN = "unknown"      # Couldn't determine


# -----------------------------------------------------------------------------
# Platform Classification
# -----------------------------------------------------------------------------

# Platforms that ALWAYS use encoder input (arcade hardware)
ENCODER_PLATFORMS: Set[str] = {
    # Arcade systems
    "mame",
    "arcade",
    "cps1", "cps2", "cps3",
    "neogeo",
    "naomi", "naomi2",
    "atomiswave",
    "hikaru",
    "triforce",
    "chihiro",
    "lindbergh",
    "ringedge", "ringwide",
    "system16", "system18", "system24", "system32",
    "model1", "model2", "model3",
    "stv", "sega_st-v",
    "taito_type_x", "taito_type_x2",
    "namco_system_256", "namco_system_357",
    "examu",
    "cave",
    "pgm", "pgm2",
    
    # TeknoParrot (always arcade)
    "teknoparrot",
    "tp",
    
    # Standalone arcade emulators
    "demul",
    "supermodel",
    "m2emulator",
    "flycast_arcade",
}

# Platforms that ALWAYS use gamepad input (console hardware)
GAMEPAD_PLATFORMS: Set[str] = {
    # Nintendo
    "nes", "snes", "n64", "gamecube", "wii", "wiiu", "switch",
    "gameboy", "gba", "gbc", "ds", "3ds",
    
    # Sony
    "psx", "ps1", "ps2", "ps3", "ps4", "ps5",
    "psp", "vita",
    
    # Microsoft
    "xbox", "xbox360", "xboxone",
    
    # Sega consoles (not arcade)
    "genesis", "megadrive", "segacd", "32x",
    "saturn", "dreamcast",
    "mastersystem", "gamegear",
    
    # Other
    "turbografx", "pcengine",
    "neogeopocket",
    "wonderswan",
    "3do",
    "jaguar",
}

# Platforms that use wheel input
WHEEL_PLATFORMS: Set[str] = {
    "racing",
}

# Platforms that use lightgun input
LIGHTGUN_PLATFORMS: Set[str] = {
    "lightgun",
}


# -----------------------------------------------------------------------------
# RetroArch Core Classification
# -----------------------------------------------------------------------------

# RetroArch cores that run ARCADE content (use encoder)
ARCADE_RA_CORES: Set[str] = {
    # MAME/FBNeo
    "mame", "mame2003", "mame2003_plus", "mame2010", "mame2016",
    "fbneo", "fbalpha", "fbalpha2012",
    
    # Sega arcade
    "flycast",           # Naomi, Atomiswave
    "kronos", "yabause", # ST-V (Saturn-based arcade)
    "supermodel",        # Model 3
    
    # Other arcade
    "same_cdi",
}

# RetroArch cores that run CONSOLE content (use gamepad)
CONSOLE_RA_CORES: Set[str] = {
    # Nintendo
    "nestopia", "fceumm", "quicknes", "mesen",
    "snes9x", "bsnes", "bsnes_mercury",
    "mupen64plus", "parallel_n64",
    "dolphin", "ishiiruka",
    "mgba", "vbam", "gambatte",
    "melonds", "desmume",
    "citra",
    
    # Sony
    "pcsx_rearmed", "beetle_psx", "beetle_psx_hw", "duckstation",
    "pcsx2",
    "ppsspp",
    
    # Sega consoles
    "genesis_plus_gx", "picodrive", "blastem",
    "beetle_saturn", "mednafen_saturn",
    "redream", "flycast",  # Note: Flycast is ALSO console (Dreamcast)
    
    # Other
    "beetle_pce", "beetle_supergrafx",
    "beetle_ngp",
    "beetle_wswan",
}

# Note: Some cores like Flycast handle both Dreamcast (console) AND Naomi (arcade)
# We'll need game-level detection for those cases


# -----------------------------------------------------------------------------
# Game-Level Detection Heuristics
# -----------------------------------------------------------------------------

# Keywords in game titles that suggest arcade
ARCADE_TITLE_KEYWORDS: Set[str] = {
    "arcade", "jamma", "pcb",
    "vs.", "versus",  # Fighting games
    "deluxe",  # Often arcade versions
}

# Keywords that suggest console
CONSOLE_TITLE_KEYWORDS: Set[str] = {
    "home", "console", "port",
}


# -----------------------------------------------------------------------------
# Input Type Result
# -----------------------------------------------------------------------------

@dataclass
class InputTypeResult:
    """Result of input type detection."""
    input_type: InputType
    confidence: float  # 0.0 to 1.0
    reason: str
    platform: str
    emulator: Optional[str] = None
    core: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_type": self.input_type.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "platform": self.platform,
            "emulator": self.emulator,
            "core": self.core,
        }


# -----------------------------------------------------------------------------
# Core Detection Functions
# -----------------------------------------------------------------------------

def normalize_platform(platform: str) -> str:
    """Normalize platform string for matching."""
    if not platform:
        return ""
    return platform.lower().strip().replace(" ", "_").replace("-", "_")


def get_input_type(
    game_title: Optional[str] = None,
    platform: Optional[str] = None,
    emulator: Optional[str] = None,
    core: Optional[str] = None,
    game_metadata: Optional[Dict[str, Any]] = None,
) -> InputTypeResult:
    """Determine the input type for a game.
    
    Priority order:
    1. Explicit game metadata override
    2. Platform classification
    3. Emulator/core classification
    4. Title heuristics
    5. Default to encoder (arcade cabinet assumption)
    
    Args:
        game_title: Name of the game
        platform: Platform/system (e.g., "naomi", "ps2", "mame")
        emulator: Emulator being used (e.g., "teknoparrot", "retroarch")
        core: RetroArch core if applicable (e.g., "flycast", "fbneo")
        game_metadata: Optional dict with explicit input_type field
    
    Returns:
        InputTypeResult with type, confidence, and reason
    """
    norm_platform = normalize_platform(platform or "")
    norm_emulator = normalize_platform(emulator or "")
    norm_core = normalize_platform(core or "")
    
    # Priority 1: Explicit metadata override
    if game_metadata and "input_type" in game_metadata:
        explicit_type = game_metadata["input_type"]
        try:
            return InputTypeResult(
                input_type=InputType(explicit_type),
                confidence=1.0,
                reason="Explicit game metadata override",
                platform=platform or "",
                emulator=emulator,
                core=core,
            )
        except ValueError:
            logger.warning(f"Invalid input_type in metadata: {explicit_type}")
    
    # Priority 2: TeknoParrot is ALWAYS arcade
    if norm_emulator in ("teknoparrot", "tp") or norm_platform in ("teknoparrot", "tp"):
        return InputTypeResult(
            input_type=InputType.ENCODER,
            confidence=1.0,
            reason="TeknoParrot is always arcade encoder input",
            platform=platform or "teknoparrot",
            emulator="teknoparrot",
            core=core,
        )
    
    # Priority 3: Platform in encoder list
    if norm_platform in ENCODER_PLATFORMS:
        return InputTypeResult(
            input_type=InputType.ENCODER,
            confidence=0.95,
            reason=f"Platform '{platform}' is classified as arcade",
            platform=platform or "",
            emulator=emulator,
            core=core,
        )
    
    # Priority 4: Platform in gamepad list
    if norm_platform in GAMEPAD_PLATFORMS:
        return InputTypeResult(
            input_type=InputType.GAMEPAD,
            confidence=0.95,
            reason=f"Platform '{platform}' is classified as console",
            platform=platform or "",
            emulator=emulator,
            core=core,
        )
    
    # Priority 5: RetroArch core classification
    if norm_emulator == "retroarch" and norm_core:
        if norm_core in ARCADE_RA_CORES:
            return InputTypeResult(
                input_type=InputType.ENCODER,
                confidence=0.85,
                reason=f"RetroArch core '{core}' runs arcade content",
                platform=platform or "",
                emulator="retroarch",
                core=core,
            )
        if norm_core in CONSOLE_RA_CORES:
            return InputTypeResult(
                input_type=InputType.GAMEPAD,
                confidence=0.85,
                reason=f"RetroArch core '{core}' runs console content",
                platform=platform or "",
                emulator="retroarch",
                core=core,
            )
    
    # Priority 6: MAME is always arcade
    if norm_emulator == "mame" or norm_platform == "mame":
        return InputTypeResult(
            input_type=InputType.ENCODER,
            confidence=0.95,
            reason="MAME is arcade emulator",
            platform=platform or "mame",
            emulator="mame",
            core=core,
        )
    
    # Priority 7: Title heuristics (low confidence)
    if game_title:
        title_lower = game_title.lower()
        for keyword in ARCADE_TITLE_KEYWORDS:
            if keyword in title_lower:
                return InputTypeResult(
                    input_type=InputType.ENCODER,
                    confidence=0.6,
                    reason=f"Title contains arcade keyword '{keyword}'",
                    platform=platform or "",
                    emulator=emulator,
                    core=core,
                )
        for keyword in CONSOLE_TITLE_KEYWORDS:
            if keyword in title_lower:
                return InputTypeResult(
                    input_type=InputType.GAMEPAD,
                    confidence=0.6,
                    reason=f"Title contains console keyword '{keyword}'",
                    platform=platform or "",
                    emulator=emulator,
                    core=core,
                )
    
    # Priority 8: Default to encoder (we're an arcade cabinet after all!)
    return InputTypeResult(
        input_type=InputType.ENCODER,
        confidence=0.5,
        reason="Default: Assuming arcade cabinet input (no match found)",
        platform=platform or "",
        emulator=emulator,
        core=core,
    )


def is_arcade_game(
    platform: Optional[str] = None,
    emulator: Optional[str] = None,
    core: Optional[str] = None,
) -> bool:
    """Quick check if a game should use arcade encoder input.
    
    Convenience wrapper around get_input_type().
    """
    result = get_input_type(platform=platform, emulator=emulator, core=core)
    return result.input_type == InputType.ENCODER


def get_input_config_source(
    platform: Optional[str] = None,
    emulator: Optional[str] = None,
    core: Optional[str] = None,
) -> str:
    """Determine which config source to use for a game.
    
    Returns:
        "chuck" for arcade games (encoder)
        "wizard" for console games (gamepad)
    """
    if is_arcade_game(platform=platform, emulator=emulator, core=core):
        return "chuck"
    return "wizard"


# -----------------------------------------------------------------------------
# Platform Registry (for UI/API)
# -----------------------------------------------------------------------------

def get_all_platforms() -> Dict[str, List[str]]:
    """Return all classified platforms for UI/debugging."""
    return {
        "encoder_platforms": sorted(ENCODER_PLATFORMS),
        "gamepad_platforms": sorted(GAMEPAD_PLATFORMS),
        "arcade_ra_cores": sorted(ARCADE_RA_CORES),
        "console_ra_cores": sorted(CONSOLE_RA_CORES),
    }


def classify_platform(platform: str) -> str:
    """Classify a single platform. Returns 'encoder', 'gamepad', or 'unknown'."""
    norm = normalize_platform(platform)
    if norm in ENCODER_PLATFORMS:
        return "encoder"
    if norm in GAMEPAD_PLATFORMS:
        return "gamepad"
    return "unknown"
