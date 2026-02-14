"""LED Blinky service - Per-game lighting patterns with tutor sequences.

This module provides game-specific LED lighting control with:
- Pattern resolution from LaunchBox metadata
- Real-time pattern application with streaming
- Interactive tutor sequences for control guidance
- Adaptive difficulty modes (kid/standard/pro)

Main exports:
    - get_service(): Get BlinkyService singleton
    - get_resolver(): Get PatternResolver singleton
    - PatternResolver.initialize(): Async initialization at startup

Usage in FastAPI router:
    from backend.services.blinky import get_service

    @router.post("/game-lights/{rom}")
    async def apply_game_lights(rom: str, service: BlinkyService = Depends(get_service)):
        async for update in service.process_game_lights(rom):
            yield update
"""

# Service exports
from backend.services.blinky.service import BlinkyService, get_service

# Resolver exports
from backend.services.blinky.resolver import (
    PatternResolver,
    get_resolver,
    MockResolver,
    get_mock_patterns
)

# Model exports
from backend.services.blinky.models import (
    GamePattern,
    SequenceStep,
    SequenceState,
    StepUpdate,
    LEDAction,
    TutorMode,
    PatternPreview
)

# Sequencer exports
from backend.services.blinky.sequencer import (
    run_tutor_sequence,
    generate_tutor_sequence,
    build_tutor_sequence,
    get_input_poller,
    InputPoller,
    MockInputPoller
)

# Quest Guide exports (NEW - 2025-10-31)
from backend.services.blinky.quest_guide import (
    run_quest_sequence,
    get_available_quests,
    get_quest_for_game,
    QUEST_PRESETS
)

# Edge Case Handler exports (NEW - 2025-10-31)
from backend.services.blinky.edge_cases import (
    get_fallback_pattern,
    adapt_pattern_to_hardware,
    safe_hardware_write,
    get_device_lock,
    rate_limit,
    with_retry
)


__all__ = [
    # Services
    "BlinkyService",
    "get_service",

    # Resolver
    "PatternResolver",
    "get_resolver",
    "MockResolver",
    "get_mock_patterns",

    # Models
    "GamePattern",
    "SequenceStep",
    "SequenceState",
    "StepUpdate",
    "LEDAction",
    "TutorMode",
    "PatternPreview",

    # Sequencer
    "run_tutor_sequence",
    "generate_tutor_sequence",
    "build_tutor_sequence",
    "get_input_poller",
    "InputPoller",
    "MockInputPoller",

    # Quest Guide (NEW)
    "run_quest_sequence",
    "get_available_quests",
    "get_quest_for_game",
    "QUEST_PRESETS",

    # Edge Cases (NEW)
    "get_fallback_pattern",
    "adapt_pattern_to_hardware",
    "safe_hardware_write",
    "get_device_lock",
    "rate_limit",
    "with_retry",
]
