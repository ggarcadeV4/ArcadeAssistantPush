"""
Adapter enablement utilities.

Provides unified logic for determining if an adapter should be enabled
based on environment variables and configuration files.
"""

import os
import logging
from typing import Optional
from backend.services.config_loader import get_global_config

logger = logging.getLogger(__name__)

# Mapping of adapter names to environment variable names
ADAPTER_ENV_VARS = {
    'duckstation': 'AA_ENABLE_ADAPTER_DUCKSTATION',
    'dolphin': 'AA_ENABLE_ADAPTER_DOLPHIN',
    'flycast': 'AA_ENABLE_ADAPTER_FLYCAST',
    'model2': 'AA_ENABLE_ADAPTER_MODEL2',
    'supermodel': 'AA_ENABLE_ADAPTER_SUPERMODEL',
    'retroarch': 'AA_ALLOW_DIRECT_RETROARCH',
    'redream': 'AA_ALLOW_DIRECT_REDREAM',
    'pcsx2': 'AA_ALLOW_DIRECT_PCSX2',
    'rpcs3': 'AA_ALLOW_DIRECT_RPCS3',
    'teknoparrot': 'AA_ALLOW_DIRECT_TEKNOPARROT',
    'cemu': 'AA_ALLOW_DIRECT_CEMU',
}

# Mapping of adapter names to config file keys
ADAPTER_CONFIG_KEYS = {
    'retroarch': 'allow_direct_retroarch',
    'pcsx2': 'allow_direct_pcsx2',
    'teknoparrot': 'allow_direct_teknoparrot',
    'redream': 'allow_direct_redream',
    'rpcs3': 'allow_direct_rpcs3',
    'cemu': 'allow_direct_cemu',
    'model2': 'allow_direct_model2',
    'supermodel': 'allow_direct_supermodel',
}


def _normalize_bool(value: Optional[str]) -> bool:
    """
    Convert string values to boolean.

    Args:
        value: String value from environment or config

    Returns:
        True if value is truthy ('1', 'true', 'yes'), False otherwise
    """
    if value is None:
        return False
    return str(value).lower() in {'1', 'true', 'yes'}


def is_adapter_enabled(
    adapter_name: str,
    env_var: Optional[str] = None,
    config_key: Optional[str] = None,
    default: bool = False
) -> bool:
    """
    Check if an adapter should be enabled.

    Priority order:
    1. Environment variable (if set)
    2. config/launchers.json (if key exists)
    3. Default value

    Args:
        adapter_name: Name of adapter (e.g., 'retroarch', 'pcsx2')
        env_var: Environment variable name (auto-detected if None)
        config_key: Config file key (auto-detected if None)
        default: Default value if not found in env or config

    Returns:
        True if adapter should be enabled, False otherwise

    Example:
        >>> is_adapter_enabled('retroarch')
        True  # if AA_ALLOW_DIRECT_RETROARCH=true or allow_direct_retroarch: true
    """
    # Auto-detect env var and config key
    env_var = env_var or ADAPTER_ENV_VARS.get(adapter_name)
    config_key = config_key or ADAPTER_CONFIG_KEYS.get(adapter_name)

    # Check environment variable first (highest priority)
    if env_var:
        env_value = os.getenv(env_var)
        if env_value is not None:
            result = _normalize_bool(env_value)
            logger.debug(f"Adapter '{adapter_name}' enabled via env {env_var}={env_value} -> {result}")
            return result

    # Check config file second
    if config_key:
        config_value = get_global_config(config_key)
        if config_value is not None:
            result = _normalize_bool(config_value)
            logger.debug(f"Adapter '{adapter_name}' enabled via config {config_key}={config_value} -> {result}")
            return result

    # Use default
    logger.debug(f"Adapter '{adapter_name}' using default={default}")
    return default
