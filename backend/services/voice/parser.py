"""Voice lighting command parser with regex patterns."""

import re
from typing import Optional
from datetime import datetime
import structlog

from .models import LightingIntent, ColorMapping

logger = structlog.get_logger(__name__)


class LightingCommandParser:
    """
    Parse voice transcripts into lighting intents.

    Uses regex patterns for common commands with fallback to fuzzy matching.
    """

    def __init__(self):
        # Compile regex patterns for performance
        self.patterns = [
            # "Light P1 red" or "Light player 1 red"
            (
                re.compile(r'\b(?:light|set)\s+(?:player\s*)?([p]?[1-4]|all)\s+(\w+)', re.IGNORECASE),
                self._parse_light_color
            ),
            # "Dim all lights"
            (
                re.compile(r'\b(?:dim|lower)\s+(?:player\s*)?([p]?[1-4]|all)?\s*(?:lights?)?', re.IGNORECASE),
                self._parse_dim
            ),
            # "Flash target 5" or "Flash P2 green"
            (
                re.compile(r'\bflash\s+(?:target\s+)?([p]?[1-4]|\d+|all)\s*(\w+)?', re.IGNORECASE),
                self._parse_flash
            ),
            # "Turn off lights"
            (
                re.compile(r'\b(?:turn\s*off|off|disable)\s+(?:player\s*)?([p]?[1-4]|all)?\s*(?:lights?)?', re.IGNORECASE),
                self._parse_off
            ),
            # "Rainbow mode" or "Pulse pattern"
            (
                re.compile(r'\b(\w+)\s+(?:mode|pattern)', re.IGNORECASE),
                self._parse_pattern
            ),
            # "Blue player 2" (alternative order)
            (
                re.compile(r'\b(\w+)\s+player\s*([1-4])', re.IGNORECASE),
                self._parse_color_player
            ),
        ]

    async def parse(self, transcript: str) -> Optional[LightingIntent]:
        """
        Parse transcript into LightingIntent.

        Args:
            transcript: Voice transcript text

        Returns:
            LightingIntent if successfully parsed, None otherwise
        """
        transcript = transcript.strip()

        if not transcript:
            return None

        logger.info("parsing_lighting_command", transcript=transcript)

        # Try each pattern
        for pattern, handler in self.patterns:
            match = pattern.search(transcript)
            if match:
                try:
                    intent = handler(match, transcript)
                    if intent:
                        logger.info("parsed_intent",
                                  action=intent.action,
                                  target=intent.target,
                                  color=intent.color)
                        return intent
                except Exception as e:
                    logger.error("parse_handler_failed", error=str(e), pattern=pattern.pattern)
                    continue

        # No pattern matched
        logger.warning("no_pattern_matched", transcript=transcript)
        return None

    def _parse_light_color(self, match, transcript: str) -> Optional[LightingIntent]:
        """Parse 'light P1 red' pattern."""
        target = self._normalize_target(match.group(1))
        color_name = match.group(2)
        color_hex = self._resolve_color(color_name)

        if not color_hex:
            logger.warning("unknown_color", color_name=color_name)
            return None

        return LightingIntent(
            action='color',
            target=target,
            color=color_hex,
            confidence=0.9
        )

    def _parse_dim(self, match, transcript: str) -> Optional[LightingIntent]:
        """Parse 'dim all lights' pattern."""
        target = match.group(1) if match.group(1) else 'all'
        target = self._normalize_target(target)

        return LightingIntent(
            action='dim',
            target=target,
            color='#222222',  # Dim = dark gray
            confidence=0.85
        )

    def _parse_flash(self, match, transcript: str) -> Optional[LightingIntent]:
        """Parse 'flash target 5' pattern."""
        target = self._normalize_target(match.group(1))
        color_name = match.group(2) if match.group(2) else 'white'
        color_hex = self._resolve_color(color_name)

        return LightingIntent(
            action='flash',
            target=target,
            color=color_hex or '#FFFFFF',
            duration_ms=500,
            confidence=0.9
        )

    def _parse_off(self, match, transcript: str) -> Optional[LightingIntent]:
        """Parse 'turn off lights' pattern."""
        target = match.group(1) if match.group(1) else 'all'
        target = self._normalize_target(target)

        return LightingIntent(
            action='off',
            target=target,
            color='#000000',
            confidence=1.0
        )

    def _parse_pattern(self, match, transcript: str) -> Optional[LightingIntent]:
        """Parse 'rainbow mode' pattern."""
        pattern_name = match.group(1).lower()

        # Validate pattern name
        valid_patterns = ['rainbow', 'pulse', 'wave', 'chase', 'breathe']
        if pattern_name not in valid_patterns:
            logger.warning("unknown_pattern", pattern=pattern_name)
            return None

        return LightingIntent(
            action='pattern',
            target='all',
            pattern=pattern_name,
            confidence=0.85
        )

    def _parse_color_player(self, match, transcript: str) -> Optional[LightingIntent]:
        """Parse 'blue player 2' pattern."""
        color_name = match.group(1)
        player_num = match.group(2)
        color_hex = self._resolve_color(color_name)

        if not color_hex:
            return None

        return LightingIntent(
            action='color',
            target=f'p{player_num}',
            color=color_hex,
            confidence=0.85
        )

    def _normalize_target(self, target: str) -> str:
        """Normalize target to consistent format."""
        target = target.lower().strip()

        # Handle "all" special case
        if target == 'all':
            return 'all'

        # Convert "player 1" or "player1" → "p1"
        if target.startswith('player'):
            # Extract just the number
            num = target.replace('player', '').strip()
            if num.isdigit():
                target = 'p' + num
        # Convert standalone digit "1" → "p1"
        elif target.isdigit() and len(target) == 1:
            target = 'p' + target
        # Handle "1p" → "p1"
        elif target.endswith('p') and target[0].isdigit():
            target = 'p' + target[0]
        # Handle "p1", "p2", etc. (already correct)
        elif target.startswith('p') and len(target) == 2 and target[1].isdigit():
            return target

        return target

    def _resolve_color(self, color_name: str) -> Optional[str]:
        """Resolve color name to hex code."""
        # Try exact match from color mapping
        hex_code = ColorMapping.get_hex(color_name)
        if hex_code:
            return hex_code

        # Try fuzzy matching (common misspellings)
        fuzzy_map = {
            'rd': 'red',
            'blu': 'blue',
            'grn': 'green',
            'yel': 'yellow',
            'yllw': 'yellow',
            'prpl': 'purple',
            'purpl': 'purple',
            'ornge': 'orange',
            'pnk': 'pink',
        }

        normalized = color_name.lower().strip()
        if normalized in fuzzy_map:
            return ColorMapping.get_hex(fuzzy_map[normalized])

        # No match
        return None


# Singleton parser instance
_parser = None

def get_parser() -> LightingCommandParser:
    """Get singleton parser instance."""
    global _parser
    if _parser is None:
        _parser = LightingCommandParser()
    return _parser
