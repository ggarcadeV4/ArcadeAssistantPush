"""LED tutor sequence generator with adaptive state machine.

This module generates interactive LED tutorial sequences that guide players
through game controls with pulsing, fading, and branching retry logic. It
adapts to player skill level and provides hints on missed inputs.

Architecture:
- State machine: Tracks progress with branching for retries
- Adaptive difficulty: Adjusts durations and hints based on mode (kid/standard/pro)
- Input polling: Simulates button press detection (mock for now, hardware later)
- Async generators: Streams sequence steps for real-time visualization
"""
import asyncio
import logging
import os
from typing import AsyncGenerator, Dict, List, Optional

from backend.services.blinky.models import (
    GamePattern,
    LEDAction,
    SequenceState,
    SequenceStep,
    StepUpdate,
    TutorMode
)
from backend.services.blinky.resolver import get_resolver
from backend.services.led_hardware import write_port

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

# Duration multipliers for different modes
MODE_DURATION_FACTORS = {
    TutorMode.KID: 2.0,       # Slow - 2x duration
    TutorMode.STANDARD: 1.0,  # Normal - 1x duration
    TutorMode.PRO: 0.7        # Fast - 0.7x duration
}

# Max steps per mode (to avoid overwhelming players)
MODE_MAX_STEPS = {
    TutorMode.KID: 4,
    TutorMode.STANDARD: 6,
    TutorMode.PRO: 8
}

# Input poll timeout (how long to wait for button press)
INPUT_POLL_TIMEOUT_MS = int(os.getenv('TUTOR_POLL_TIMEOUT_MS', '3000'))


# ============================================================================
# Input Polling (Mock for now, hardware integration later)
# ============================================================================

class InputPoller:
    """Base class for input polling during tutor sequences."""

    async def check_press(self, led_id: int, timeout_ms: int) -> bool:
        """Check if button corresponding to LED was pressed.

        Args:
            led_id: LED port number
            timeout_ms: Max time to wait for input

        Returns:
            True if button pressed within timeout, False otherwise
        """
        raise NotImplementedError


class MockInputPoller(InputPoller):
    """Mock input poller for testing (simulates random presses)."""

    async def check_press(self, led_id: int, timeout_ms: int) -> bool:
        """Simulate input check with 70% success rate."""
        await asyncio.sleep(timeout_ms / 1000 * 0.5)  # Wait half the timeout
        # 70% success rate for testing
        import random
        return random.random() < 0.7


class HardwareInputPoller(InputPoller):
    """Real hardware input poller (to be implemented with pyusb/HID)."""

    async def check_press(self, led_id: int, timeout_ms: int) -> bool:
        """Poll hardware for button press.

        TODO: Implement with pyusb/HID device polling
        For now, falls back to mock behavior
        """
        logger.warning("Hardware polling not implemented - using mock")
        mock = MockInputPoller()
        return await mock.check_press(led_id, timeout_ms)


# ============================================================================
# Sequence Builder
# ============================================================================

def build_tutor_sequence(pattern: GamePattern, mode: TutorMode) -> SequenceState:
    """Build tutor sequence from game pattern.

    Creates a step-by-step LED tutorial that pulses each active button
    in sequence, with duration/complexity adjusted for difficulty mode.

    Args:
        pattern: Game LED pattern
        mode: Difficulty mode (kid/standard/pro)

    Returns:
        SequenceState with steps and retry branches

    Heuristics:
        - Kid mode: Slow durations, max 4 buttons, simple hints
        - Standard mode: Normal speed, up to 6 buttons
        - Pro mode: Fast, can show all buttons, minimal hints
    """
    duration_factor = MODE_DURATION_FACTORS[mode]
    max_steps = MODE_MAX_STEPS[mode]

    # Sort active LEDs by port number for consistent sequence
    active_leds = sorted(pattern.active_leds.items())

    # Limit steps based on mode
    if len(active_leds) > max_steps:
        active_leds = active_leds[:max_steps]
        logger.debug(f"Limited sequence to {max_steps} steps for {mode} mode")

    steps = []
    branches = {}

    for idx, (led_id, color) in enumerate(active_leds):
        # Base duration: 1500ms, adjusted by mode
        base_duration = 1500
        duration = int(base_duration * duration_factor)

        # Generate hint based on button position and game
        hint = _generate_hint(led_id, idx, pattern.game_name, mode)

        step = SequenceStep(
            led_id=led_id,
            action=LEDAction.PULSE,
            duration_ms=duration,
            color=color,
            hint=hint
        )
        steps.append(step)

        # Create retry branch with adjusted parameters
        retry_steps = _create_retry_branch(step, mode)
        if retry_steps:
            branches[idx] = retry_steps

    # Build state
    state = SequenceState(
        rom=pattern.rom,
        mode=mode,
        steps=steps,
        branches=branches,
        max_retries=3 if mode == TutorMode.KID else 2
    )

    return state


def _generate_hint(led_id: int, step_idx: int, game_name: Optional[str], mode: TutorMode) -> str:
    """Generate contextual hint for a sequence step.

    Args:
        led_id: LED port number
        step_idx: Step index in sequence
        game_name: Game name for context
        mode: Difficulty mode

    Returns:
        Hint string
    """
    # Button position hints
    position_hints = {
        1: "top-left button",
        2: "top-middle button",
        3: "top-right button",
        4: "bottom-left button",
        5: "bottom-middle button",
        6: "bottom-right button",
    }

    position = position_hints.get(led_id, f"button {led_id}")

    # Game-specific hints
    if game_name and "street fighter" in game_name.lower():
        sf_hints = ["Light Punch", "Medium Punch", "Heavy Punch",
                    "Light Kick", "Medium Kick", "Heavy Kick"]
        if step_idx < len(sf_hints):
            position = sf_hints[step_idx]

    elif game_name and "mortal kombat" in game_name.lower():
        mk_hints = ["High Punch", "Low Punch", "Block", "High Kick", "Low Kick"]
        if step_idx < len(mk_hints):
            position = mk_hints[step_idx]

    # Mode-specific hint detail
    if mode == TutorMode.KID:
        return f"Press the pulsing {position} button!"
    elif mode == TutorMode.PRO:
        return position
    else:
        return f"Press {position}"


def _create_retry_branch(step: SequenceStep, mode: TutorMode) -> List[SequenceStep]:
    """Create retry steps for missed input.

    Args:
        step: Original step that was missed
        mode: Difficulty mode

    Returns:
        List of retry steps with adjusted parameters
    """
    # Retry with brighter color and longer duration
    retry_step = SequenceStep(
        led_id=step.led_id,
        action=LEDAction.PULSE,
        duration_ms=step.duration_ms + 500,  # Add 500ms
        color=step.color,
        hint=f"Try again - {step.hint}" if step.hint else "Press the pulsing button!"
    )

    return [retry_step]


# ============================================================================
# Sequence Runner
# ============================================================================

async def run_tutor_sequence(
    pattern: GamePattern,
    mode: TutorMode = TutorMode.STANDARD,
    poller: Optional[InputPoller] = None,
    device_id: int = 0,
    preview_only: bool = False
) -> AsyncGenerator[StepUpdate, None]:
    """Run interactive tutor sequence with input polling.

    This is the main entry point for executing LED tutorial sequences.
    Streams updates as sequence progresses, handling retries on missed inputs.

    Args:
        pattern: Game LED pattern
        mode: Difficulty mode
        poller: Input poller (defaults to Mock for testing)
        device_id: LED device ID
        preview_only: If True, skip hardware writes

    Yields:
        StepUpdate with execution status and progress

    Flow:
        1. Build sequence from pattern
        2. For each step:
           a. Pulse LED
           b. Poll for input
           c. If pressed: advance to next step
           d. If missed: retry branch (up to max_retries)
        3. Complete or skip after max retries
    """
    # Default to mock poller for testing
    if poller is None:
        poller = MockInputPoller()

    # Build sequence
    state = build_tutor_sequence(pattern, mode)
    total_steps = len(state.steps)

    logger.info(f"Starting tutor sequence for {pattern.rom} ({mode}) - {total_steps} steps")

    while not state.is_complete():
        step = state.get_current_step()
        if step is None:
            break

        # Apply LED effect
        if not preview_only:
            await _apply_step_effect(step, device_id)

        # Yield step start
        yield StepUpdate(
            led_id=step.led_id,
            action=step.action,
            color=step.color,
            status="executing",
            step_index=state.current_step,
            total_steps=total_steps,
            progress=state.get_progress(),
            hint=step.hint
        )

        # Poll for input
        pressed = await poller.check_press(step.led_id, step.duration_ms)

        if pressed:
            # Success - advance to next step
            state.advance()

            yield StepUpdate(
                led_id=step.led_id,
                action=step.action,
                color=step.color,
                status="completed",
                step_index=state.current_step - 1,
                total_steps=total_steps,
                progress=state.get_progress(),
                hint="Great!"
            )

        else:
            # Miss - try retry branch
            retry_steps = state.branch_to_retry()

            if retry_steps:
                # Execute retry
                yield StepUpdate(
                    led_id=step.led_id,
                    action=step.action,
                    color=step.color,
                    status="retry",
                    step_index=state.current_step,
                    total_steps=total_steps,
                    progress=state.get_progress(),
                    hint=f"Try again (attempt {state.retry_count}/{state.max_retries})",
                    retry_count=state.retry_count
                )

                # Execute retry step
                for retry_step in retry_steps:
                    if not preview_only:
                        await _apply_step_effect(retry_step, device_id)

                    await asyncio.sleep(retry_step.duration_ms / 1000)

            else:
                # Max retries exceeded - skip this step
                logger.warning(f"Max retries exceeded for step {state.current_step}")
                state.advance()

                yield StepUpdate(
                    led_id=step.led_id,
                    action=step.action,
                    color=step.color,
                    status="skipped",
                    step_index=state.current_step - 1,
                    total_steps=total_steps,
                    progress=state.get_progress(),
                    hint="Skipping - let's try the next one!"
                )

    logger.info(f"Tutor sequence completed for {pattern.rom}")


async def _apply_step_effect(step: SequenceStep, device_id: int) -> None:
    """Apply LED effect for a sequence step.

    Args:
        step: Sequence step
        device_id: LED device ID

    Effects:
        - PULSE: Fade in/out using brightness modulation
        - HOLD: Solid color
        - FADE: Gradual fade out
    """
    # Convert color to RGB
    hex_color = step.color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    if step.action == LEDAction.PULSE:
        # Pulse effect: fade in, hold, fade out
        steps_in = 10
        steps_out = 10
        hold_time = step.duration_ms / 1000 * 0.5

        # Fade in
        for i in range(steps_in):
            brightness = i / steps_in
            rgb = (int(r * brightness), int(g * brightness), int(b * brightness))
            write_port(device_id, step.led_id, rgb)
            await asyncio.sleep(hold_time / steps_in)

        # Hold
        write_port(device_id, step.led_id, (r, g, b))
        await asyncio.sleep(hold_time)

        # Fade out
        for i in range(steps_out):
            brightness = 1.0 - (i / steps_out)
            rgb = (int(r * brightness), int(g * brightness), int(b * brightness))
            write_port(device_id, step.led_id, rgb)
            await asyncio.sleep(hold_time / steps_out)

        # Off
        write_port(device_id, step.led_id, (0, 0, 0))

    elif step.action == LEDAction.HOLD:
        # Solid color for duration
        write_port(device_id, step.led_id, (r, g, b))
        await asyncio.sleep(step.duration_ms / 1000)

    elif step.action == LEDAction.FADE:
        # Fade out from full brightness
        steps = 20
        for i in range(steps):
            brightness = 1.0 - (i / steps)
            rgb = (int(r * brightness), int(g * brightness), int(b * brightness))
            write_port(device_id, step.led_id, rgb)
            await asyncio.sleep(step.duration_ms / 1000 / steps)

        write_port(device_id, step.led_id, (0, 0, 0))

    else:  # OFF
        write_port(device_id, step.led_id, (0, 0, 0))


# ============================================================================
# Dependency Injection
# ============================================================================

def get_input_poller(test_mode: bool = False) -> InputPoller:
    """Get input poller based on environment.

    Args:
        test_mode: If True, always return MockInputPoller

    Returns:
        InputPoller instance

    Note:
        Set TEST_MODE=1 env var to force mock poller
    """
    if test_mode or os.getenv('TEST_MODE', '').lower() in ('1', 'true'):
        return MockInputPoller()

    # TODO: Return HardwareInputPoller when hardware integration ready
    logger.info("Using MockInputPoller (hardware not yet integrated)")
    return MockInputPoller()


async def generate_tutor_sequence(
    pattern: GamePattern,
    mode: str = 'standard'
) -> AsyncGenerator[SequenceStep, None]:
    """Generate simple tutor sequence without input polling.

    This is a simpler version of run_tutor_sequence that just streams
    the sequence steps without interactive polling. Useful for preview
    and visualization.

    Args:
        pattern: Game LED pattern
        mode: Difficulty mode string ('kid', 'standard', 'pro')

    Yields:
        SequenceStep for each step in sequence
    """
    try:
        tutor_mode = TutorMode(mode.lower())
    except ValueError:
        logger.warning(f"Invalid mode '{mode}', using standard")
        tutor_mode = TutorMode.STANDARD

    state = build_tutor_sequence(pattern, tutor_mode)

    for step in state.steps:
        yield step
        await asyncio.sleep(step.duration_ms / 1000)
