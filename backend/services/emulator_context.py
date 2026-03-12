"""
Emulator input-context resolver.
ARCHITECTURE: "Path IS the Signal"
==================================
We do NOT guess input types from process names or PIDs.
The folder path determines the input mode:
  - Gun Build\\        -> lightgun
  - Gamepad / Joystick / Controller  -> gamepad
  - Everything else   -> arcade_panel (default)
This resolver is the foundational switchboard for:
  - AI Knowledge Router (pick Chuck's troubleshooting context)
  - Gunner panel auto-activation
  - LED Blinky profile selection
"""

from __future__ import annotations

import logging
import re
from typing import Literal


logger = logging.getLogger(__name__)

InputContext = Literal["lightgun", "gamepad", "arcade_panel"]

# Patterns checked IN ORDER - first match wins
_GUN_PATTERN = re.compile(r"Gun[\s_]Build[/\\]", re.IGNORECASE)
_GAMEPAD_PATTERN = re.compile(
    r"(?:Gamepad|Joystick|Controller)(?:[/\\]|$)", re.IGNORECASE
)


def infer_input_context(emulator_path: str) -> InputContext:
    """
    Determine the input context from an emulator's executable path.

    Args:
        emulator_path: Full or relative path to the emulator executable.

    Returns:
        "lightgun"     if path contains 'Gun Build\\'
        "gamepad"      if path contains 'Gamepad', 'Joystick', or 'Controller'
        "arcade_panel" otherwise (default)
    """
    if not emulator_path:
        return "arcade_panel"

    # Normalize separators for consistent matching
    normalized = emulator_path.replace("/", "\\")

    if _GUN_PATTERN.search(normalized):
        return "lightgun"

    if _GAMEPAD_PATTERN.search(normalized):
        return "gamepad"

    return "arcade_panel"