"""Voice Vicky intent models with validation."""

from typing import Optional, Literal, List
from pydantic import BaseModel, Field, validator
import re
import structlog

logger = structlog.get_logger(__name__)


class LightingIntent(BaseModel):
    """
    Parsed lighting command intent.

    Attributes:
        action: What to do with lights (dim, flash, color, off, pattern)
        target: What to affect (all, player1-4, specific LED ID)
        color: Hex color code (optional for dim/off actions)
        duration_ms: How long to apply effect (default 0 = permanent)
        confidence: Parser confidence score (0.0-1.0)
    """
    action: Literal['dim', 'flash', 'color', 'off', 'pattern'] = Field(
        ...,
        description="Lighting action to perform"
    )
    target: str = Field(
        ...,
        description="Target LEDs (all, p1-p4, or LED ID)"
    )
    color: Optional[str] = Field(
        None,
        description="Hex color code (e.g., #FF0000)"
    )
    duration_ms: int = Field(
        default=0,
        ge=0,
        le=60000,
        description="Duration in milliseconds (0=permanent)"
    )
    pattern: Optional[str] = Field(
        None,
        description="Pattern name for pattern action (pulse, wave, etc.)"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Parser confidence score"
    )

    @validator('color')
    def validate_color(cls, v):
        """Validate hex color format."""
        if v is None:
            return v

        if not v.startswith('#'):
            v = '#' + v

        if len(v) != 7:
            raise ValueError(f"Invalid hex color: {v}. Must be #RRGGBB format.")

        # Validate hex digits
        try:
            int(v[1:], 16)
        except ValueError:
            raise ValueError(f"Invalid hex color: {v}")

        return v.upper()

    @validator('target')
    def validate_target(cls, v):
        """Validate target format."""
        v = v.lower()

        # Valid targets: all, p1-p4, player1-4, or numeric LED ID
        if v in ['all', 'p1', 'p2', 'p3', 'p4', 'player1', 'player2', 'player3', 'player4']:
            return v

        # Try parsing as LED ID
        try:
            led_id = int(v)
            if led_id < 0:
                raise ValueError(f"LED ID must be positive: {led_id}")
            return str(led_id)
        except ValueError:
            raise ValueError(f"Invalid target: {v}. Must be 'all', 'p1-p4', or LED ID.")

        return v

    @validator('action', always=True)
    def validate_action_color(cls, v, values):
        """Ensure color is provided for color/flash actions."""
        # Skip validation if we're still building the model
        if 'color' not in values:
            return v
        if v in ['color', 'flash'] and not values.get('color'):
            raise ValueError(f"Action '{v}' requires a color parameter.")
        return v


class LightingCommand(BaseModel):
    """
    Complete lighting command with metadata.

    Used for logging and history tracking.
    """
    transcript: str = Field(..., description="Original voice transcript")
    intent: LightingIntent = Field(..., description="Parsed intent")
    user_id: Optional[str] = Field(None, description="User ID for logging")
    timestamp: str = Field(..., description="ISO timestamp")
    applied: bool = Field(default=False, description="Whether command was applied")
    error: Optional[str] = Field(None, description="Error message if failed")


class ColorMapping:
    """Common color name to hex mappings."""
    RED = "#FF0000"
    GREEN = "#00FF00"
    BLUE = "#0000FF"
    YELLOW = "#FFFF00"
    CYAN = "#00FFFF"
    MAGENTA = "#FF00FF"
    WHITE = "#FFFFFF"
    ORANGE = "#FF8800"
    PURPLE = "#8800FF"
    PINK = "#FF00AA"

    @classmethod
    def get_hex(cls, color_name: str) -> Optional[str]:
        """Get hex code for color name."""
        return getattr(cls, color_name.upper(), None)
