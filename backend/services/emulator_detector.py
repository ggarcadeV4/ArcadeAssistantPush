"""
Emulator auto-detection service.
Reads emulator configurations from LaunchBox and other frontends.

Performance optimizations:
- Singleton pattern to avoid repeated file I/O
- In-memory caching of loaded configurations
- Lazy loading with iterparse for large XML files
- Efficient path validation with early returns
"""
import xml.etree.ElementTree as ET
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from contextlib import contextmanager

from backend.models.emulator_config import (
    EmulatorConfig,
    EmulatorDefinition,
    PlatformEmulatorMapping
)
from backend.constants.a_drive_paths import LaunchBoxPaths, is_on_a_drive

logger = logging.getLogger(__name__)


class EmulatorDetector:
    """
    Detects and parses emulator configurations from various sources.

    Priority:
    1. LaunchBox Data/Emulators.xml (if available)
    2. User config file (manual overrides)
    3. Fallback to hardcoded paths

    This class follows a singleton pattern for efficiency.
    """

    CONFIG_FILE = Path("configs/emulator_paths.json")
    _instance: Optional['EmulatorDetector'] = None
    _config_cache: Optional[EmulatorConfig] = None

    def __new__(cls) -> 'EmulatorDetector':
        """Implement singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def detect_launchbox_emulators(cls) -> Optional[EmulatorConfig]:
        """
        Parse LaunchBox's Emulators.xml to extract all emulator configurations.

        Returns:
            EmulatorConfig with all detected emulators and platform mappings,
            or None if LaunchBox is not found or parsing fails.
        """
        emulators_xml = LaunchBoxPaths.DATA_DIR / "Emulators.xml"

        if not emulators_xml.exists():
            logger.warning(f"LaunchBox Emulators.xml not found at {emulators_xml}")
            return None

        try:
            logger.info(f"Parsing LaunchBox emulator configs from {emulators_xml}...")

            config = EmulatorConfig(
                launchbox_root=str(LaunchBoxPaths.LAUNCHBOX_ROOT),
                detection_timestamp=datetime.now().isoformat()
            )

            # Use iterparse for better memory efficiency with large XML files
            emulator_count = 0
            mapping_count = 0

            for event, elem in ET.iterparse(emulators_xml, events=('end',)):
                # Only process and clear top-level elements to avoid clearing children
                # before their parent is processed
                if elem.tag == "Emulator" and elem.findtext("ID"):
                    # This is a full emulator definition (has ID child), not just a UUID reference
                    emu_def = cls._parse_emulator_definition(elem)
                    if emu_def:
                        config.emulators[emu_def.id] = emu_def
                        emulator_count += 1
                    elem.clear()  # Free memory

                elif elem.tag == "EmulatorPlatform":
                    mapping = cls._parse_platform_mapping(elem)
                    if mapping:
                        config.platform_mappings.append(mapping)
                        mapping_count += 1
                    elem.clear()  # Free memory

            logger.info(
                f"Detected {emulator_count} emulators "
                f"with {mapping_count} platform mappings"
            )

            return config

        except ET.ParseError as e:
            logger.error(f"XML parsing failed: {e}")
            return None
        except IOError as e:
            logger.error(f"File I/O error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing LaunchBox emulators: {e}", exc_info=True)
            return None

    @staticmethod
    def _parse_emulator_definition(elem: ET.Element) -> Optional[EmulatorDefinition]:
        """
        Parse a single <Emulator> XML element.

        Args:
            elem: XML element to parse

        Returns:
            EmulatorDefinition or None if parsing fails
        """
        try:
            emu_id = elem.findtext("ID", "").strip()
            title = elem.findtext("Title", "").strip()
            app_path = elem.findtext("ApplicationPath", "").strip()
            command_line = elem.findtext("CommandLine", "").strip()

            if not all([emu_id, title, app_path]):
                return None

            return EmulatorDefinition(
                id=emu_id,
                title=title,
                executable_path=app_path,
                command_line=command_line,
                source="launchbox"
            )

        except (AttributeError, ValueError) as e:
            logger.debug(f"Failed to parse emulator definition: {e}")
            return None

    @staticmethod
    def _parse_platform_mapping(elem: ET.Element) -> Optional[PlatformEmulatorMapping]:
        """
        Parse a single <EmulatorPlatform> XML element.

        Args:
            elem: XML element to parse

        Returns:
            PlatformEmulatorMapping or None if parsing fails
        """
        try:
            platform = elem.findtext("Platform", "").strip()
            emulator_id = elem.findtext("Emulator", "").strip()
            command_line = elem.findtext("CommandLine", "").strip()
            is_default_str = elem.findtext("Default", "false").strip().lower()
            is_default = is_default_str == "true"

            if not all([platform, emulator_id]):
                return None

            return PlatformEmulatorMapping(
                platform=platform,
                emulator_id=emulator_id,
                command_line=command_line,
                is_default=is_default
            )

        except (AttributeError, ValueError) as e:
            logger.debug(f"Failed to parse platform mapping: {e}")
            return None

    @classmethod
    @contextmanager
    def _safe_file_operation(cls, file_path: Path, mode: str, operation: str):
        """
        Context manager for safe file operations with proper error handling.

        Args:
            file_path: Path to file
            mode: File open mode
            operation: Description of operation for logging

        Yields:
            File handle
        """
        file_handle = None
        try:
            if mode.startswith('w'):
                file_path.parent.mkdir(parents=True, exist_ok=True)

            file_handle = open(file_path, mode)
            yield file_handle

        except IOError as e:
            logger.error(f"I/O error during {operation}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during {operation}: {e}", exc_info=True)
            raise
        finally:
            if file_handle:
                file_handle.close()

    @classmethod
    def save_config(cls, config: EmulatorConfig) -> bool:
        """
        Save emulator config to JSON file.

        Args:
            config: EmulatorConfig to save

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            with cls._safe_file_operation(
                cls.CONFIG_FILE, 'w', 'config save'
            ) as f:
                json.dump(config.to_dict(), f, indent=2)

            logger.info(f"Saved emulator config to {cls.CONFIG_FILE}")
            cls._config_cache = config  # Update cache
            return True

        except Exception:
            return False

    @classmethod
    def load_config(cls) -> Optional[EmulatorConfig]:
        """
        Load emulator config from JSON file with caching.

        Returns:
            EmulatorConfig if file exists and is valid, None otherwise
        """
        # Return cached config if available
        if cls._config_cache is not None:
            return cls._config_cache

        if not cls.CONFIG_FILE.exists():
            logger.info("No saved emulator config found")
            return None

        try:
            with cls._safe_file_operation(
                cls.CONFIG_FILE, 'r', 'config load'
            ) as f:
                data = json.load(f)

            emulators = data.get("emulators", {})
            if isinstance(emulators, dict):
                missing_command_line = any(
                    isinstance(emu_data, dict) and "command_line" not in emu_data
                    for emu_data in emulators.values()
                )
                if missing_command_line:
                    logger.info(
                        "Saved emulator config is missing emulator command_line fields; forcing redetect"
                    )
                    return None

            config = EmulatorConfig.from_dict(data)
            cls._config_cache = config  # Cache the loaded config
            logger.info(f"Loaded emulator config from {cls.CONFIG_FILE}")
            return config

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            return None
        except Exception:
            return None

    @classmethod
    def get_or_detect_config(cls) -> EmulatorConfig:
        """
        Get emulator configuration using the following priority:
        1. Load from saved config file (with caching)
        2. Auto-detect from LaunchBox (on A: drive OR if Emulators.xml exists)
        3. Return empty config (will use hardcoded fallbacks)

        Returns:
            EmulatorConfig (never None, but may be empty)
        """
        # Try loading saved config (uses cache if available)
        config = cls.load_config()
        if config:
            logger.info("Using saved emulator configuration")
            return config

        # Try auto-detecting from LaunchBox
        # Check both: on A: drive OR if LaunchBox Emulators.xml exists (dev mode)
        emulators_xml = LaunchBoxPaths.DATA_DIR / "Emulators.xml"

        if is_on_a_drive() or emulators_xml.exists():
            if emulators_xml.exists():
                logger.info(f"Found LaunchBox Emulators.xml at {emulators_xml}")
                logger.info("Attempting auto-detection from LaunchBox...")
                config = cls.detect_launchbox_emulators()

                if config:
                    # Save for future use
                    cls.save_config(config)
                    return config
            elif is_on_a_drive():
                logger.warning(f"On A: drive but Emulators.xml not found at {emulators_xml}")

        # Return empty config (launcher will use hardcoded fallbacks)
        logger.warning("No emulator config found - using hardcoded fallbacks")
        empty_config = EmulatorConfig()
        cls._config_cache = empty_config  # Cache even empty config
        return empty_config

    @classmethod
    def force_redetect(cls) -> Optional[EmulatorConfig]:
        """
        Force re-detection of emulators, ignoring saved config and cache.

        Returns:
            Newly detected EmulatorConfig or None if detection fails
        """
        logger.info("Force re-detecting emulators...")

        # Clear cache
        cls._config_cache = None

        config = cls.detect_launchbox_emulators()

        if config:
            cls.save_config(config)

        return config

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the in-memory config cache."""
        cls._config_cache = None
        logger.debug("Cleared emulator config cache")


# Singleton instance for easy import
detector = EmulatorDetector()
