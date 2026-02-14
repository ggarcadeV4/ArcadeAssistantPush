"""Emulator adapter interfaces and helpers."""

from .retroarch_adapter import (
    RAConfig,
    can_handle as retroarch_can_handle,
    resolve_config as retroarch_resolve_config,
    build_command as retroarch_build_command,
    to_command as retroarch_to_command,
)

__all__ = [
    "RAConfig",
    "retroarch_can_handle",
    "retroarch_resolve_config",
    "retroarch_build_command",
    "retroarch_to_command",
]

