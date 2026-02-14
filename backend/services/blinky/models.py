"""Pydantic models for LED Blinky service.

This module defines the data models for LED lighting patterns, tutor sequences,
and state management. All models include comprehensive validation to ensure
data integrity and prevent invalid configurations.
"""
from enum import Enum
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class LEDAction(str, Enum):
    """Actions that can be performed on an LED."""
    PULSE = "pulse"
    HOLD = "hold"
    FADE = "fade"
    OFF = "off"


class TutorMode(str, Enum):
    """Tutor sequence difficulty modes."""
    KID = "kid"  # Slower, simpler sequences
    STANDARD = "standard"  # Normal speed
    PRO = "pro"  # Fast, advanced sequences


class GamePattern(BaseModel):
    """LED lighting pattern for a specific game/ROM.

    Defines which LEDs should be active (lit) and which should be inactive (dark)
    for a particular game. For example:
    - Donkey Kong: 1 red button active, all others dark
    - Street Fighter 2: 6 buttons with multi-colors, joystick dark
    """
    rom: str = Field(..., description="ROM name identifier (e.g., 'dkong', 'sf2')")
    active_leds: Dict[int, str] = Field(
        default_factory=dict,
        description="Map of LED port number to hex color (e.g., {1: '#FF0000', 2: '#00FF00'})"
    )
    inactive_leds: List[int] = Field(
        default_factory=list,
        description="List of LED port numbers that should be dark (#000000)"
    )
    inactive_color: str = Field(
        default="#000000",
        description="Color for inactive LEDs (default black/off)"
    )
    brightness: int = Field(
        default=100,
        ge=0,
        le=100,
        description="Global brightness percentage (0-100)"
    )
    game_name: Optional[str] = Field(None, description="Human-readable game name")
    platform: Optional[str] = Field(None, description="Platform/system name")
    control_count: Optional[int] = Field(None, description="Total button count from controls.dat")

    @field_validator('active_leds')
    @classmethod
    def validate_active_colors(cls, v):
        """Ensure all colors are valid hex format."""
        for port, color in v.items():
            if not isinstance(color, str) or not color.startswith('#'):
                raise ValueError(f"Port {port} color must be hex format (e.g., '#FF0000'), got: {color}")
            if len(color) != 7:
                raise ValueError(f"Port {port} color must be 7 chars (#RRGGBB), got: {color}")
            # Validate hex digits
            try:
                int(color[1:], 16)
            except ValueError:
                raise ValueError(f"Port {port} color contains invalid hex digits: {color}")
        return v

    @field_validator('inactive_color')
    @classmethod
    def validate_inactive_color(cls, v):
        """Ensure inactive color is valid hex format."""
        if not v.startswith('#') or len(v) != 7:
            raise ValueError(f"Inactive color must be hex format (#RRGGBB), got: {v}")
        try:
            int(v[1:], 16)
        except ValueError:
            raise ValueError(f"Inactive color contains invalid hex digits: {v}")
        return v

    @model_validator(mode='after')
    def validate_no_overlap(self):
        """Ensure no LED is both active and inactive."""
        active = set(self.active_leds.keys())
        inactive = set(self.inactive_leds)
        overlap = active & inactive
        if overlap:
            raise ValueError(f"LEDs cannot be both active and inactive: {overlap}")
        return self

    def get_combined_updates(self, total_leds: int = 32) -> Dict[int, str]:
        """Get complete LED state with active colored and inactive dark.

        Args:
            total_leds: Total number of LED ports available (default 32)

        Returns:
            Dict mapping all LED port numbers to hex colors
        """
        updates = {}

        # Set active LEDs to their specified colors
        for port, color in self.active_leds.items():
            if 1 <= port <= total_leds:
                updates[port] = color

        # Set inactive LEDs to dark
        for port in self.inactive_leds:
            if 1 <= port <= total_leds:
                updates[port] = self.inactive_color

        # Fill remaining LEDs with inactive color if not specified
        all_specified = set(self.active_leds.keys()) | set(self.inactive_leds)
        for port in range(1, total_leds + 1):
            if port not in all_specified:
                updates[port] = self.inactive_color

        return updates

    def __hash__(self):
        """Make hashable for LRU cache."""
        return hash((self.rom, tuple(sorted(self.active_leds.items()))))


class SequenceStep(BaseModel):
    """Single step in a tutor sequence.

    Represents one action in a guided LED tutorial sequence, such as pulsing
    a specific button to teach the player which control to use.
    """
    led_id: int = Field(..., ge=1, le=96, description="LED port number (1-96)")
    action: LEDAction = Field(default=LEDAction.PULSE, description="Action to perform")
    duration_ms: int = Field(
        default=1500,
        ge=500,
        le=5000,
        description="Duration in milliseconds (500-5000ms)"
    )
    color: str = Field(..., description="Hex color for this step (e.g., '#FF0000')")
    hint: Optional[str] = Field(None, description="Optional text hint for player")

    @field_validator('color')
    @classmethod
    def validate_color(cls, v):
        """Ensure color is valid hex format."""
        if not v.startswith('#') or len(v) != 7:
            raise ValueError(f"Color must be hex format (#RRGGBB), got: {v}")
        try:
            int(v[1:], 16)
        except ValueError:
            raise ValueError(f"Color contains invalid hex digits: {v}")
        return v

    @model_validator(mode='after')
    def validate_duration(self):
        """Adjust duration based on action type."""
        if self.action == LEDAction.PULSE and self.duration_ms < 1000:
            raise ValueError("PULSE action requires minimum 1000ms duration")
        return self


class SequenceState(BaseModel):
    """State machine for tutor sequences.

    Tracks progress through a multi-step LED tutorial sequence with support
    for branching (retries on missed inputs) and adaptive difficulty.
    """
    rom: str = Field(..., description="ROM identifier")
    mode: TutorMode = Field(default=TutorMode.STANDARD, description="Difficulty mode")
    current_step: int = Field(default=0, ge=0, description="Current step index")
    steps: List[SequenceStep] = Field(default_factory=list, description="Sequence steps")
    branches: Dict[int, List[SequenceStep]] = Field(
        default_factory=dict,
        description="Branch steps for retries (step_index -> retry_steps)"
    )
    retry_count: int = Field(default=0, ge=0, le=3, description="Current retry count")
    max_retries: int = Field(default=3, ge=1, le=5, description="Max retries per step")
    total_duration: int = Field(
        default=0,
        ge=0,
        le=60000,
        description="Total sequence duration in ms (max 60s)"
    )
    completed_steps: List[int] = Field(
        default_factory=list,
        description="List of successfully completed step indices"
    )

    @field_validator('steps')
    @classmethod
    def validate_steps(cls, v):
        """Ensure reasonable step count."""
        if len(v) > 20:
            raise ValueError("Sequence cannot exceed 20 steps")
        return v

    @model_validator(mode='after')
    def validate_branches_and_duration(self):
        """Ensure branch depth doesn't exceed max_retries and calculate duration."""
        # Validate branches
        for step_idx, retry_steps in self.branches.items():
            if len(retry_steps) > self.max_retries:
                raise ValueError(f"Branch at step {step_idx} exceeds max retries ({self.max_retries})")

        # Calculate total duration
        total = sum(step.duration_ms for step in self.steps)
        self.total_duration = total

        # Warn if exceeding recommended duration
        if total > 30000:  # 30 seconds
            import logging
            logging.getLogger(__name__).warning(
                f"Sequence duration {total}ms exceeds recommended 30s"
            )

        return self

    def get_current_step(self) -> Optional[SequenceStep]:
        """Get the current step or None if completed."""
        if self.current_step >= len(self.steps):
            return None
        return self.steps[self.current_step]

    def advance(self) -> bool:
        """Advance to next step. Returns False if sequence complete."""
        if self.current_step < len(self.steps):
            self.completed_steps.append(self.current_step)
            self.current_step += 1
            self.retry_count = 0  # Reset retry counter
            return self.current_step < len(self.steps)
        return False

    def branch_to_retry(self) -> Optional[List[SequenceStep]]:
        """Get retry branch steps if available and under max retries."""
        if self.retry_count >= self.max_retries:
            return None

        self.retry_count += 1
        return self.branches.get(self.current_step)

    def is_complete(self) -> bool:
        """Check if sequence is fully completed."""
        return self.current_step >= len(self.steps)

    def get_progress(self) -> float:
        """Get completion progress (0.0 - 1.0)."""
        if not self.steps:
            return 1.0
        return len(self.completed_steps) / len(self.steps)


class StepUpdate(BaseModel):
    """Real-time update during sequence execution.

    Sent as streaming updates to clients during tutor sequence playback.
    """
    led_id: int = Field(..., description="LED port being updated")
    action: LEDAction = Field(..., description="Action being performed")
    color: str = Field(..., description="Current color")
    status: Literal["executing", "completed", "retry", "skipped"] = Field(
        ...,
        description="Step execution status"
    )
    step_index: int = Field(..., ge=0, description="Current step index")
    total_steps: int = Field(..., ge=1, description="Total steps in sequence")
    progress: float = Field(..., ge=0.0, le=1.0, description="Completion progress")
    hint: Optional[str] = Field(None, description="Player hint text")
    retry_count: Optional[int] = Field(None, description="Current retry count")


class PatternPreview(BaseModel):
    """Preview of LED pattern before applying to hardware.

    Used for frontend visualization and user confirmation before committing
    pattern changes to physical LEDs.
    """
    rom: str = Field(..., description="ROM identifier")
    pattern: GamePattern = Field(..., description="Complete pattern definition")
    preview_updates: Dict[int, str] = Field(
        ...,
        description="All LED updates that will be applied (port -> color)"
    )
    active_count: int = Field(..., ge=0, description="Number of active LEDs")
    inactive_count: int = Field(..., ge=0, description="Number of inactive LEDs")
    estimated_apply_time_ms: int = Field(
        default=100,
        description="Estimated time to apply pattern"
    )
