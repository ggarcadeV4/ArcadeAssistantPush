"""Lazy exports for LED Blinky services.

This package must stay cheap to import during backend startup. Heavy modules such as
resolver/service/hardware orchestration are imported on first attribute access.
"""

from __future__ import annotations

from importlib import import_module
from typing import Dict, Tuple

_EXPORTS: Dict[str, Tuple[str, str]] = {
    'BlinkyService': ('backend.services.blinky.service', 'BlinkyService'),
    'get_service': ('backend.services.blinky.service', 'get_service'),
    'PatternResolver': ('backend.services.blinky.resolver', 'PatternResolver'),
    'get_resolver': ('backend.services.blinky.resolver', 'get_resolver'),
    'MockResolver': ('backend.services.blinky.resolver', 'MockResolver'),
    'get_mock_patterns': ('backend.services.blinky.resolver', 'get_mock_patterns'),
    'GamePattern': ('backend.services.blinky.models', 'GamePattern'),
    'SequenceStep': ('backend.services.blinky.models', 'SequenceStep'),
    'SequenceState': ('backend.services.blinky.models', 'SequenceState'),
    'StepUpdate': ('backend.services.blinky.models', 'StepUpdate'),
    'LEDAction': ('backend.services.blinky.models', 'LEDAction'),
    'TutorMode': ('backend.services.blinky.models', 'TutorMode'),
    'PatternPreview': ('backend.services.blinky.models', 'PatternPreview'),
    'run_tutor_sequence': ('backend.services.blinky.sequencer', 'run_tutor_sequence'),
    'generate_tutor_sequence': ('backend.services.blinky.sequencer', 'generate_tutor_sequence'),
    'build_tutor_sequence': ('backend.services.blinky.sequencer', 'build_tutor_sequence'),
    'get_input_poller': ('backend.services.blinky.sequencer', 'get_input_poller'),
    'InputPoller': ('backend.services.blinky.sequencer', 'InputPoller'),
    'MockInputPoller': ('backend.services.blinky.sequencer', 'MockInputPoller'),
    'run_quest_sequence': ('backend.services.blinky.quest_guide', 'run_quest_sequence'),
    'get_available_quests': ('backend.services.blinky.quest_guide', 'get_available_quests'),
    'get_quest_for_game': ('backend.services.blinky.quest_guide', 'get_quest_for_game'),
    'QUEST_PRESETS': ('backend.services.blinky.quest_guide', 'QUEST_PRESETS'),
    'get_fallback_pattern': ('backend.services.blinky.edge_cases', 'get_fallback_pattern'),
    'adapt_pattern_to_hardware': ('backend.services.blinky.edge_cases', 'adapt_pattern_to_hardware'),
    'safe_hardware_write': ('backend.services.blinky.edge_cases', 'safe_hardware_write'),
    'get_device_lock': ('backend.services.blinky.edge_cases', 'get_device_lock'),
    'rate_limit': ('backend.services.blinky.edge_cases', 'rate_limit'),
    'with_retry': ('backend.services.blinky.edge_cases', 'with_retry'),
}

__all__ = list(_EXPORTS.keys())


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
