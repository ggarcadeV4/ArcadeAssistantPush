"""Pattern renderer utilities for LED animations."""
from __future__ import annotations

import math
from typing import List

MAX_BRIGHTNESS = 255


def color_to_brightness(color: str, max_value: int = MAX_BRIGHTNESS) -> int:
    """Convert hex color (#RRGGBB) to a LED-Wiz brightness value."""
    if not isinstance(color, str):
        return 0
    value = color.lstrip("#")
    if len(value) != 6:
        return 0
    try:
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
    except ValueError:
        return 0
    # Use perceived luminance weighting
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    scaled = int((luminance / 255.0) * max_value)
    return max(0, min(max_value, scaled))


class PatternRenderer:
    """Produce per-channel brightness frames for common patterns."""

    def __init__(self, channel_count: int = 32):
        self.channel_count = channel_count

    def solid(self, color: str) -> List[int]:
        value = color_to_brightness(color)
        return [value] * self.channel_count

    def pulse(self, color: str, time_ms: float) -> List[int]:
        base = color_to_brightness(color)
        phase = (math.sin(time_ms / 250.0) + 1.0) / 2.0
        value = max(0, min(MAX_BRIGHTNESS, int(base * phase)))
        return [value] * self.channel_count

    def chase(self, color: str, time_ms: float) -> List[int]:
        value = color_to_brightness(color)
        frame = [0] * self.channel_count
        if self.channel_count == 0:
            return frame
        position = int(time_ms / 80.0) % self.channel_count
        frame[position] = value
        trailing = (position - 1) % self.channel_count
        frame[trailing] = int(value * 0.4)
        return frame

    def rainbow(self, time_ms: float) -> List[int]:
        frame = [0] * self.channel_count
        for index in range(self.channel_count):
            hue = (time_ms / 500.0 + index / self.channel_count) % 1.0
            value = self._hue_to_brightness(hue)
            frame[index] = value
        return frame

    def _hue_to_brightness(self, hue: float) -> int:
        # Map hue angle to brightness using cosine wave
        value = (math.cos(hue * math.pi * 2) + 1.0) / 2.0
        scaled = int(value * MAX_BRIGHTNESS)
        return max(0, min(MAX_BRIGHTNESS, scaled))
