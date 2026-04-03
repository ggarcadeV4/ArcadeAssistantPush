"""
Adapter registry for game launchers.

ARCHITECTURE (2025-12-11): Direct-to-Emulator Model
====================================================
Pegasus (or any frontend) → Arcade Assistant → Emulator

LaunchBox is NOT part of the runtime launch chain.
RetroArch adapter is ALWAYS registered (no config gating).
This ensures 100% reliable direct launches.

Configuration sources (priority order):
1. Environment variables (AA_ENABLE_ADAPTER_*, AA_ALLOW_DIRECT_*)
2. config/launchers.json (global.allow_direct_*)
3. Hardcoded defaults (False for most adapters)

See: backend/utils/adapter_config.py for enablement logic
"""

import logging
from backend.utils.adapter_config import is_adapter_enabled

logger = logging.getLogger(__name__)

# Registered direct-launch adapters
REGISTERED = []
ADAPTER_STATUS = {}


def _register_adapter(adapter_name: str, module_path: str, enabled: bool = None):
    """
    Conditionally import and register an adapter.

    Args:
        adapter_name: Display name for logging (e.g., 'duckstation')
        module_path: Import path (e.g., 'backend.services.adapters.duckstation_adapter')
        enabled: Override enablement check (defaults to is_adapter_enabled)
    """
    if enabled is None:
        enabled = is_adapter_enabled(adapter_name)

    if not enabled:
        logger.info(f"Adapter '{adapter_name}' disabled (not registered)")
        return

    try:
        # Dynamic import
        parts = module_path.rsplit('.', 1)
        if len(parts) == 2:
            module_name, attr_name = parts
            module = __import__(module_name, fromlist=[attr_name])
            adapter = getattr(module, attr_name)
        else:
            adapter = __import__(module_path)

        REGISTERED.append(adapter)
        ADAPTER_STATUS[adapter_name] = 'ok'
        logger.info(f"Registered adapter: {adapter_name}")

    except Exception as e:
        logger.error(f"Failed to load adapter '{adapter_name}': {e}")
        ADAPTER_STATUS[adapter_name] = f'error: {e}'


# Register feature-flagged adapters
_register_adapter('duckstation', 'backend.services.adapters.duckstation_adapter')
_register_adapter('dolphin', 'backend.services.adapters.dolphin_adapter', enabled=True)  # Always: handles Wii + GameCube
_register_adapter('flycast', 'backend.services.adapters.flycast_adapter')
_register_adapter('model2', 'backend.services.adapters.model2_adapter')
_register_adapter('supermodel', 'backend.services.adapters.supermodel_adapter')
# RetroArch: ALWAYS enabled (direct-to-emulator model - no config gating)
_register_adapter('retroarch', 'backend.services.adapters.retroarch_adapter', enabled=True)
_register_adapter('redream', 'backend.services.adapters.redream_adapter')
_register_adapter('pcsx2', 'backend.services.adapters.pcsx2_adapter')
_register_adapter('rpcs3', 'backend.services.adapters.rpcs3_adapter', enabled=True)
_register_adapter('ppsspp', 'backend.services.adapters.ppsspp_adapter', enabled=True)
_register_adapter('teknoparrot', 'backend.services.adapters.teknoparrot_adapter', enabled=True)
_register_adapter('cemu', 'backend.services.adapters.cemu_adapter')

# Yuzu adapter for Nintendo Switch (always enabled)
_register_adapter('yuzu', 'backend.services.adapters.yuzu_adapter', enabled=True)

# Hypseus adapter for laserdisc games (always enabled for Dragon's Lair, Batman, etc.)
_register_adapter('hypseus', 'backend.services.adapters.hypseus_adapter', enabled=True)
# Daphne is an alias for Hypseus (modern fork)
_register_adapter('daphne', 'backend.services.adapters.hypseus_adapter', enabled=True)

# Direct app adapter (always enabled for Daphne/AHK scripts)
_register_adapter('direct_app', 'backend.services.adapters.direct_app_adapter', enabled=True)

logger.info(f"Adapter registry initialized: {len(REGISTERED)} adapters registered")
