"""
Emulator configuration models.
Supports auto-detection from multiple frontend sources (LaunchBox, EmulationStation, etc.)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from functools import lru_cache
import re


@dataclass(frozen=False)
class EmulatorDefinition:
    """
    Represents a single emulator installation.

    Attributes:
        id: Unique identifier (GUID from LaunchBox or generated)
        title: Human-readable name (e.g., "MAME", "RetroArch-Controller")
        executable_path: Full path to emulator executable
        command_line: Optional emulator-level command-line parameters
        working_directory: Optional working directory for execution
        source: Where this config was detected from ("launchbox" | "manual" | etc.)
    """
    id: str
    title: str
    executable_path: str
    command_line: str = ""
    working_directory: Optional[str] = None
    source: str = "launchbox"

    def __hash__(self) -> int:
        """Make hashable for caching purposes."""
        return hash((self.id, self.title, self.executable_path))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "executable_path": self.executable_path,
            "command_line": self.command_line,
            "working_directory": self.working_directory,
            "source": self.source
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EmulatorDefinition:
        """Create from dictionary (for loading from config file)."""
        return cls(
            id=data["id"],
            title=data["title"],
            executable_path=data["executable_path"],
            command_line=data.get("command_line", ""),
            working_directory=data.get("working_directory"),
            source=data.get("source", "manual")
        )

    @lru_cache(maxsize=128)
    def resolve_path(self, launchbox_root: Path) -> Path:
        """
        Resolve executable path relative to LaunchBox root if needed.

        LaunchBox stores paths relative to its root directory with Windows separators.
        E.g., "Emulators\\MAME\\mame.exe" -> "<DRIVE>\\LaunchBox\\Emulators\\MAME\\mame.exe"
        Or "..\\Gun Build\\Emulators\\retroarch.exe" -> "<DRIVE>\\Gun Build\\Emulators\\retroarch.exe"

        Handles WSL/Windows cross-platform paths properly:
        - Input: Windows-style path from LaunchBox XML
        - Processing: Resolves using WSL paths if in WSL environment
        - Output: Windows-style path for subprocess execution

        Args:
            launchbox_root: Root path of LaunchBox installation (can be WSL or Windows format)

        Returns:
            Resolved absolute path to executable in Windows format
        """
        import platform

        # Normalize path separators (LaunchBox uses Windows backslashes)
        exe_path_str = self.executable_path.replace('\\', '/')
        exe_path = Path(exe_path_str)

        # Resolve the path
        if exe_path.is_absolute():
            resolved = exe_path
        else:
            # If relative, resolve from LaunchBox root
            # Path.resolve() properly handles .. (parent directory) references
            resolved = (launchbox_root / exe_path).resolve()

        # Always normalize any WSL-style mount path to Windows format
        # Some configurations may store '/mnt/x/...' paths even on Windows.
        # _wsl_to_windows_path() is a no-op for non-/mnt/ paths.
        resolved = self._wsl_to_windows_path(resolved)

        # Fix common mis-conversion: 'C:\\mnt\\a\\...' -> 'A:\\...'
        s = str(resolved)
        m = re.match(r"^[A-Za-z]:\\mnt\\([A-Za-z])\\(.*)$", s)
        if m:
            drive = m.group(1).upper()
            rest = m.group(2)
            return Path(f"{drive}:\\{rest}")

        return resolved

    @staticmethod
    def _wsl_to_windows_path(wsl_path: Path) -> Path:
        """
        Convert WSL path to Windows path format.

        Examples:
            /mnt/a/LaunchBox/mame.exe -> A:\\LaunchBox\\mame.exe (on A: drive)
            /mnt/c/Program Files/... -> C:\\Program Files\\... (on C: drive)

        Args:
            wsl_path: Path in WSL format

        Returns:
            Path in Windows format
        """
        path_str = str(wsl_path)

        # Check if it's a WSL mount path
        if path_str.startswith('/mnt/'):
            # Extract drive letter and path
            parts = path_str[5:].split('/', 1)
            if len(parts) >= 1:
                drive_letter = parts[0].upper()
                path_remainder = parts[1] if len(parts) > 1 else ''

                # Convert to Windows format
                windows_path = f"{drive_letter}:\\"
                if path_remainder:
                    # Replace forward slashes with backslashes
                    windows_path += path_remainder.replace('/', '\\')

                return Path(windows_path)

        # If not a WSL mount path, return as-is
        return wsl_path


@dataclass(frozen=False)
class PlatformEmulatorMapping:
    """
    Maps a platform to its emulator with launch parameters.

    Attributes:
        platform: Platform name (e.g., "Arcade", "Nintendo Entertainment System")
        emulator_id: Reference to EmulatorDefinition.id
        command_line: Command-line parameters for this platform
        is_default: Whether this is the default emulator for this platform
    """
    platform: str
    emulator_id: str
    command_line: str = ""
    is_default: bool = True

    def __hash__(self) -> int:
        """Make hashable for caching purposes."""
        return hash((self.platform, self.emulator_id, self.is_default))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "platform": self.platform,
            "emulator_id": self.emulator_id,
            "command_line": self.command_line,
            "is_default": self.is_default
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PlatformEmulatorMapping:
        """Create from dictionary."""
        return cls(
            platform=data["platform"],
            emulator_id=data["emulator_id"],
            command_line=data.get("command_line", ""),
            is_default=data.get("is_default", True)
        )


@dataclass
class EmulatorConfig:
    """
    Complete emulator configuration for the system.

    This combines emulator definitions with platform mappings,
    providing everything needed to launch games.
    """
    emulators: Dict[str, EmulatorDefinition] = field(default_factory=dict)
    platform_mappings: List[PlatformEmulatorMapping] = field(default_factory=list)
    launchbox_root: Optional[str] = None
    detection_timestamp: Optional[str] = None

    # Cache for platform lookups
    _platform_cache: Dict[str, Optional[Tuple[EmulatorDefinition, PlatformEmulatorMapping]]] = field(
        default_factory=dict, init=False, repr=False
    )

    def get_emulator_for_platform(
        self, platform: str
    ) -> Optional[Tuple[EmulatorDefinition, PlatformEmulatorMapping]]:
        """
        Get the default emulator for a given platform with caching.

        Args:
            platform: Name of the platform

        Returns:
            Tuple of (EmulatorDefinition, PlatformEmulatorMapping) or None if not found
        """
        # Check cache first
        if platform in self._platform_cache:
            return self._platform_cache[platform]

        # Find default mapping for platform using more efficient approach
        mapping = None
        for m in self.platform_mappings:
            if m.platform == platform and m.is_default:
                mapping = m
                break

        if not mapping:
            self._platform_cache[platform] = None
            return None

        # Get emulator definition
        emulator = self.emulators.get(mapping.emulator_id)

        if not emulator:
            self._platform_cache[platform] = None
            return None

        result = (emulator, mapping)
        self._platform_cache[platform] = result
        return result

    def clear_cache(self) -> None:
        """Clear the platform lookup cache."""
        self._platform_cache.clear()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "emulators": {
                emu_id: emu.to_dict()
                for emu_id, emu in self.emulators.items()
            },
            "platform_mappings": [
                mapping.to_dict()
                for mapping in self.platform_mappings
            ],
            "launchbox_root": self.launchbox_root,
            "detection_timestamp": self.detection_timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EmulatorConfig:
        """Create from dictionary (for loading from config file)."""
        emulators = {
            emu_id: EmulatorDefinition.from_dict(emu_data)
            for emu_id, emu_data in data.get("emulators", {}).items()
        }

        platform_mappings = [
            PlatformEmulatorMapping.from_dict(m)
            for m in data.get("platform_mappings", [])
        ]

        return cls(
            emulators=emulators,
            platform_mappings=platform_mappings,
            launchbox_root=data.get("launchbox_root"),
            detection_timestamp=data.get("detection_timestamp")
        )
