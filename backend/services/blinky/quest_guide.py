"""Quest Guide Mode for LED Blinky - Interactive story-driven coaching sequences.

This module implements wizard-style presets and gamified coaching sequences
designed for kids and families. It extends the tutor sequencer with narrative
elements, rewards, and adaptive difficulty scaling.

Architecture:
- Quest presets: Story-themed sequences (e.g., "Climb Quest", "Hero Journey")
- Adaptive branching: Easy retries with encouraging hints for kids
- Reward system: Bus integration with ScoreKeeper for badges and points
- Progress tracking: Save/resume support for multi-session quests

Design Philosophy:
- Make learning controls fun and engaging
- Reduce frustration with gentle guidance
- Celebrate small wins to build confidence
- Family-friendly language and pacing
"""
import asyncio
import logging
from typing import AsyncGenerator, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.services.blinky.models import (
    GamePattern,
    LEDAction,
    SequenceStep,
    TutorMode
)
from backend.services.bus_events import publish_tts_speak, get_event_bus

logger = logging.getLogger(__name__)


# ============================================================================
# Quest Models
# ============================================================================

class QuestTheme(BaseModel):
    """Theme configuration for a quest."""
    id: str = Field(..., description="Unique quest ID (e.g., 'climb_quest', 'hero_journey')")
    name: str = Field(..., description="Display name (e.g., 'The Climb Quest')")
    description: str = Field(..., description="Quest description for kids")
    intro_message: str = Field(..., description="Welcome message spoken by Voice Vicky")
    success_message: str = Field(..., description="Completion message")
    encouragement: List[str] = Field(
        default_factory=list,
        description="Random encouraging phrases for retries"
    )
    reward_points: int = Field(default=10, description="Points awarded on completion")


class QuestStep(BaseModel):
    """Extended sequence step with quest narrative."""
    led_id: int
    action: LEDAction
    duration_ms: int
    color: str
    story_hint: str = Field(..., description="Story-driven hint (e.g., 'Jump to the next platform!')")
    retry_hint: str = Field(..., description="Encouraging retry hint")
    reward_message: Optional[str] = Field(None, description="Message on successful completion")


# ============================================================================
# Quest Presets
# ============================================================================

QUEST_PRESETS: Dict[str, QuestTheme] = {
    "climb_quest": QuestTheme(
        id="climb_quest",
        name="The Climb Quest",
        description="Help the hero climb to the top! Press the glowing buttons to jump up.",
        intro_message="Let's help our hero climb! Watch for the glowing button, then press it to jump up!",
        success_message="Amazing! You reached the top! You're a climbing champion!",
        encouragement=[
            "Almost! Try again!",
            "You're getting better!",
            "One more time, you've got this!",
            "Great effort! Let's try that jump again!"
        ],
        reward_points=15
    ),
    "hero_journey": QuestTheme(
        id="hero_journey",
        name="Hero's Journey",
        description="Guide the hero through their adventure by pressing the magic buttons!",
        intro_message="Welcome, brave adventurer! Follow the lights to complete your quest!",
        success_message="Victory! You've completed the hero's journey! What an amazing adventure!",
        encouragement=[
            "The hero believes in you!",
            "Magic takes practice!",
            "Try again, hero!",
            "You're doing great!"
        ],
        reward_points=20
    ),
    "light_catcher": QuestTheme(
        id="light_catcher",
        name="Light Catcher",
        description="Catch all the lights before they disappear!",
        intro_message="Let's catch the lights! Press each glowing button as fast as you can!",
        success_message="You caught all the lights! You're a Light Catcher Master!",
        encouragement=[
            "So close!",
            "Catch it this time!",
            "You're quick!",
            "Try again!"
        ],
        reward_points=10
    ),
    "button_explorer": QuestTheme(
        id="button_explorer",
        name="Button Explorer",
        description="Explore the arcade by pressing each special button!",
        intro_message="Time to explore! Each button is a new discovery. Press them all!",
        success_message="Explorer's Badge earned! You found all the buttons!",
        encouragement=[
            "Keep exploring!",
            "Almost there!",
            "Try that one again!",
            "You're a great explorer!"
        ],
        reward_points=12
    ),
    "rainbow_painter": QuestTheme(
        id="rainbow_painter",
        name="Rainbow Painter",
        description="Paint a rainbow by pressing the colorful buttons in order!",
        intro_message="Let's paint a rainbow! Press each color button when it glows!",
        success_message="Beautiful rainbow! You're an amazing artist!",
        encouragement=[
            "Keep painting!",
            "Try that color again!",
            "Beautiful work!",
            "Almost finished!"
        ],
        reward_points=15
    )
}


# ============================================================================
# Quest Builder
# ============================================================================

def build_quest_sequence(
    pattern: GamePattern,
    quest_id: str = "climb_quest",
    difficulty: str = "kid"
) -> tuple[QuestTheme, List[QuestStep]]:
    """Build a quest sequence from a game pattern.

    Args:
        pattern: Base game pattern
        quest_id: Quest preset ID
        difficulty: Difficulty level ('easy', 'kid', 'standard')

    Returns:
        (quest_theme, quest_steps) tuple

    Raises:
        ValueError: If quest_id not found in presets
    """
    if quest_id not in QUEST_PRESETS:
        raise ValueError(f"Unknown quest ID: {quest_id}. Available: {list(QUEST_PRESETS.keys())}")

    theme = QUEST_PRESETS[quest_id]

    # Sort active LEDs
    active_leds = sorted(pattern.active_leds.items())

    # Limit steps for kids (max 4 for easy quests)
    max_steps = 4 if difficulty == "easy" else 5 if difficulty == "kid" else 6
    if len(active_leds) > max_steps:
        active_leds = active_leds[:max_steps]

    # Build quest steps with story elements
    steps = []
    for idx, (led_id, color) in enumerate(active_leds):
        # Duration: slower for kids
        base_duration = 2500 if difficulty == "easy" else 2000 if difficulty == "kid" else 1500

        # Story-driven hints based on quest theme
        story_hint = _generate_story_hint(theme, idx, len(active_leds), pattern.game_name)

        step = QuestStep(
            led_id=led_id,
            action=LEDAction.PULSE,
            duration_ms=base_duration,
            color=color,
            story_hint=story_hint,
            retry_hint=theme.encouragement[idx % len(theme.encouragement)],
            reward_message=f"Step {idx + 1} complete! {len(active_leds) - idx - 1} more to go!" if idx < len(active_leds) - 1 else "Final step! You did it!"
        )
        steps.append(step)

    logger.info(f"Built quest '{theme.name}' with {len(steps)} steps for {pattern.rom}")
    return theme, steps


def _generate_story_hint(
    theme: QuestTheme,
    step_idx: int,
    total_steps: int,
    game_name: Optional[str]
) -> str:
    """Generate contextual story hint for a quest step.

    Args:
        theme: Quest theme
        step_idx: Current step index
        total_steps: Total steps in quest
        game_name: Optional game name for context

    Returns:
        Story-driven hint string
    """
    # Theme-specific hints
    if theme.id == "climb_quest":
        hints = [
            "Press the button to jump to the first platform!",
            "Great! Now jump to the next platform!",
            "You're climbing higher! Keep going!",
            "Almost at the top! One more jump!",
            "Final jump to reach the summit!"
        ]
        return hints[min(step_idx, len(hints) - 1)]

    elif theme.id == "hero_journey":
        hints = [
            "Start your journey by pressing the glowing button!",
            "The path continues! Follow the light!",
            "Keep going, hero! The quest awaits!",
            "You're getting close to your goal!",
            "The final challenge! Press to complete your quest!"
        ]
        return hints[min(step_idx, len(hints) - 1)]

    elif theme.id == "light_catcher":
        return f"Catch light {step_idx + 1} of {total_steps}! Press the glowing button!"

    elif theme.id == "button_explorer":
        return f"Discover button {step_idx + 1}! Press it to explore!"

    elif theme.id == "rainbow_painter":
        colors = ["red", "orange", "yellow", "green", "blue", "purple"]
        color = colors[step_idx % len(colors)]
        return f"Paint with {color}! Press the glowing {color} button!"

    else:
        return f"Press button {step_idx + 1} of {total_steps}!"


# ============================================================================
# Quest Runner
# ============================================================================

async def run_quest_sequence(
    pattern: GamePattern,
    quest_id: str = "climb_quest",
    difficulty: str = "kid",
    tts_enabled: bool = True,
    device_id: int = 0
) -> AsyncGenerator[Dict, None]:
    """Run an interactive quest sequence with TTS narration.

    Args:
        pattern: Game pattern
        quest_id: Quest preset ID
        difficulty: Difficulty level
        tts_enabled: Enable Voice Vicky TTS narration
        device_id: LED device ID

    Yields:
        Quest progress updates

    Flow:
        1. Introduce quest with TTS
        2. For each step:
           - Pulse LED with story hint
           - Wait for input (simulated for now)
           - Encourage on miss, celebrate on success
        3. Completion with reward message
        4. Emit bus event for ScoreKeeper points
    """
    try:
        # Build quest
        theme, steps = build_quest_sequence(pattern, quest_id, difficulty)

        yield {
            "status": "quest_intro",
            "theme": theme.model_dump(),
            "total_steps": len(steps),
            "message": theme.intro_message
        }

        # TTS intro
        if tts_enabled:
            await publish_tts_speak(theme.intro_message, priority=1)
            await asyncio.sleep(3)  # Let intro finish

        # Execute quest steps
        for idx, step in enumerate(steps):
            yield {
                "status": "quest_step",
                "step_index": idx,
                "total_steps": len(steps),
                "led_id": step.led_id,
                "color": step.color,
                "hint": step.story_hint,
                "progress": idx / len(steps)
            }

            # TTS story hint
            if tts_enabled:
                await publish_tts_speak(step.story_hint)

            # Pulse LED (actual hardware integration would go here)
            await asyncio.sleep(step.duration_ms / 1000)

            # Simulate input check (70% success rate for demo)
            import random
            success = random.random() < 0.7

            if success:
                yield {
                    "status": "quest_step_success",
                    "step_index": idx,
                    "message": step.reward_message or "Great job!"
                }

                if tts_enabled and step.reward_message:
                    await publish_tts_speak(step.reward_message)

            else:
                # Encourage retry
                yield {
                    "status": "quest_step_retry",
                    "step_index": idx,
                    "message": step.retry_hint
                }

                if tts_enabled:
                    await publish_tts_speak(step.retry_hint)

                # Re-pulse for retry
                await asyncio.sleep(step.duration_ms / 1000)

        # Quest completion
        yield {
            "status": "quest_completed",
            "theme": theme.name,
            "reward_points": theme.reward_points,
            "message": theme.success_message
        }

        if tts_enabled:
            await publish_tts_speak(theme.success_message, priority=1)

        # Emit bus event for ScoreKeeper
        bus = get_event_bus()
        await bus.publish("quest_completed", {
            "quest_id": theme.id,
            "quest_name": theme.name,
            "rom": pattern.rom,
            "game_name": pattern.game_name,
            "reward_points": theme.reward_points,
            "difficulty": difficulty
        })

        logger.info(f"Quest '{theme.name}' completed for {pattern.rom}")

    except Exception as e:
        logger.error(f"Error running quest: {e}", exc_info=True)
        yield {
            "status": "quest_error",
            "error": str(e)
        }


# ============================================================================
# API Functions
# ============================================================================

def get_available_quests() -> List[Dict]:
    """Get list of available quest presets.

    Returns:
        List of quest theme metadata
    """
    return [
        {
            "id": theme.id,
            "name": theme.name,
            "description": theme.description,
            "reward_points": theme.reward_points
        }
        for theme in QUEST_PRESETS.values()
    ]


def get_quest_for_game(pattern: GamePattern, age: Optional[int] = None) -> str:
    """Recommend a quest based on game pattern and player age.

    Args:
        pattern: Game pattern
        age: Optional player age

    Returns:
        Recommended quest ID

    Heuristics:
        - Age < 6: Simple quests (light_catcher, button_explorer)
        - Age 6-10: Story quests (climb_quest, hero_journey)
        - Age > 10: Skill quests (rainbow_painter)
        - Fighting games: hero_journey
        - Platformers: climb_quest
        - Shooters: light_catcher
    """
    # Age-based
    if age and age < 6:
        return "button_explorer"
    elif age and age <= 10:
        return "climb_quest"

    # Game-based
    game_lower = pattern.game_name.lower() if pattern.game_name else ""
    if any(kw in game_lower for kw in ['street fighter', 'mortal kombat', 'tekken']):
        return "hero_journey"
    elif any(kw in game_lower for kw in ['donkey kong', 'mario', 'sonic']):
        return "climb_quest"
    elif any(kw in game_lower for kw in ['galaga', '1942', 'raiden']):
        return "light_catcher"

    # Default
    return "button_explorer"
