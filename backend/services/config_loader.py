"""
Centralized configuration service for Arcade Assistant.

Loads configuration from multiple sources with priority order:
1. Environment variables (highest priority)
2. config/launchers.json
3. Hardcoded defaults (fallback)

Provides caching and graceful error handling.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

# Default config location
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "launchers.json"


@lru_cache(maxsize=1)
def load_launchers_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load launchers configuration from JSON file with caching.

    Args:
        config_path: Path to launchers.json (defaults to config/launchers.json)

    Returns:
        Dictionary containing configuration, or empty dict on error

    Example structure:
        {
            "global": {
                "allow_direct_retroarch": true,
                "allow_direct_pcsx2": true
            }
        }
    """
    path = config_path or DEFAULT_CONFIG_PATH

    try:
        if not path.exists():
            logger.warning(f"Config file not found at {path}, using defaults")
            return {}

        with open(path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            logger.info(f"Loaded launcher config from {path}")
            return config

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {path}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Failed to load config from {path}: {e}")
        return {}


def get_global_config(key: str, default: Any = None) -> Any:
    """
    Get a value from the global configuration section.

    Args:
        key: Configuration key (e.g., 'allow_direct_retroarch')
        default: Default value if key not found

    Returns:
        Configuration value or default
    """
    config = load_launchers_config()
    return config.get('global', {}).get(key, default)


def clear_config_cache():
    """Clear the configuration cache (useful for testing or hot reload)."""
    load_launchers_config.cache_clear()
