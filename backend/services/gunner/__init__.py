"""Gunner multi-light gun calibration package.

Provides universal light gun support with:
- Multi-vendor hardware detection (Sinden, Gun4IR, AIMTRAK, Ultimarc, Wiimote, etc.)
- Pluggable registry pattern for extensibility
- Retro shooter mode handlers (Time Crisis, House of the Dead, etc.)
- Feature-based adaptive calibration
"""

from .hardware import (
    GunModel,
    MultiGunRegistry,
    MultiGunDetector,
    get_gun_registry
)

from .modes import (
    RetroMode,
    ModeData,
    ModeHandler,
    TimeCrisisHandler,
    HouseOfTheDeadHandler,
    PointBlankHandler,
    MODE_HANDLERS
)

__all__ = [
    'GunModel',
    'MultiGunRegistry',
    'MultiGunDetector',
    'get_gun_registry',
    'RetroMode',
    'ModeData',
    'ModeHandler',
    'TimeCrisisHandler',
    'HouseOfTheDeadHandler',
    'PointBlankHandler',
    'MODE_HANDLERS'
]
