"""
Deterministic path constants for Arcade Assistant (LaunchBox focus).

Authoritative cabinet wiring (paths derived from AA_DRIVE_ROOT):
- LaunchBox root: <AA_DRIVE_ROOT>/LaunchBox
- Platform XMLs: <AA_DRIVE_ROOT>/LaunchBox/Data/Platforms/<Platform>.xml
- Logs: <AA_DRIVE_ROOT>/.aa/logs/
- Backups: <AA_DRIVE_ROOT>/.aa/backups/

We intentionally avoid runtime discovery here so every component references
the exact same filesystem targets without guessing.

IMPORTANT: No hardcoded drive letters allowed. Use AA_DRIVE_ROOT.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from backend.constants.drive_root import get_drive_root


def _get_drive_root() -> Path:
    """Get drive root. No CWD fallback per Slice 2 contract."""
    return get_drive_root(allow_cwd_fallback=False)


# Dynamic path resolution - no hardcoded drive letters
def _drive_letter_root() -> Path:
    """Get the drive letter root (e.g., A:\) from AA_DRIVE_ROOT.
    
    Tools, Emulators, Roms, LaunchBox are at drive letter root,
    not under the project folder.
    """
    drive_root = _get_drive_root()
    # Extract drive letter (e.g., "A:" from "A:\Arcade Assistant Local")
    if drive_root.drive:
        return Path(drive_root.drive + "\\")
    # Fallback for non-Windows or edge cases
    return drive_root


def _launchbox_root() -> Path:
    return _drive_letter_root() / "LaunchBox"


def _tools_root() -> Path:
    return _drive_letter_root() / "Tools"


def _logs_root() -> Path:
    return _get_drive_root() / ".aa" / "logs"


def _backups_configs() -> Path:
    return _get_drive_root() / ".aa" / "backups" / "configs"


def _roms_root() -> Path:
    return _drive_letter_root() / "Roms"


def _emulators_root() -> Path:
    return _drive_letter_root() / "Emulators"


class Paths:
    """Centralized, deterministic filesystem paths.
    
    All paths are derived dynamically from AA_DRIVE_ROOT.
    No hardcoded drive letters.
    """

    @classmethod
    def drive_root(cls) -> Path:
        return _get_drive_root()
    
    # Keep DRIVE_ROOT as property for compatibility
    @property
    def DRIVE_ROOT(self) -> Path:
        return _get_drive_root()

    class RetroFE:
        @classmethod
        def root(cls) -> Path:
            return _tools_root() / "RetroFE" / "RetroFE"
        
        ROOT: ClassVar[Path] = property(lambda self: self.root())
        
        @classmethod
        def executable(cls) -> Path:
            return cls.root() / "core" / "retrofe.exe"
        
        @classmethod
        def collections(cls) -> Path:
            return cls.root() / "collections"
        
        @classmethod
        def launchers(cls) -> Path:
            return cls.root() / "launchers.windows"
        
        @classmethod
        def meta(cls) -> Path:
            return cls.root() / "meta"

    class Pegasus:
        @classmethod
        def root(cls) -> Path:
            return _tools_root() / "Pegasus"
        
        @classmethod
        def executable(cls) -> Path:
            return cls.root() / "pegasus-fe.exe"
        
        @classmethod
        def config(cls) -> Path:
            return cls.root() / "config"
        
        @classmethod
        def themes(cls) -> Path:
            return cls.root() / "themes"
        
        @classmethod
        def metadata(cls) -> Path:
            return cls.root() / "metadata"

    class Tools:
        """Tool paths at drive letter root / Tools."""
        
        @classmethod
        def root(cls) -> Path:
            return _tools_root()
        
        class LEDBlinky:
            """LEDBlinky LED control software paths."""
            
            @classmethod
            def root(cls) -> Path:
                return _tools_root() / "LEDBlinky"
            
            @classmethod
            def executable(cls) -> Path:
                """Main LEDBlinky.exe for CLI control."""
                return cls.root() / "LEDBlinky.exe"
            
            @classmethod
            def config_wizard(cls) -> Path:
                return cls.root() / "LEDBlinkyConfigWizard.exe"
            
            @classmethod
            def output_test(cls) -> Path:
                return cls.root() / "LEDBlinkyOutputTest.exe"
            
            @classmethod
            def simple_test(cls) -> Path:
                return cls.root() / "SimpleLEDTest.exe"
            
            @classmethod
            def settings_ini(cls) -> Path:
                return cls.root() / "Settings.ini"
            
            @classmethod
            def controls_xml(cls) -> Path:
                return cls.root() / "LEDBlinkyControls.xml"

    class LaunchBox:
        @classmethod
        def root(cls) -> Path:
            return _launchbox_root()
        
        ROOT: ClassVar[Path] = property(lambda self: self.root())
        
        @classmethod
        def data(cls) -> Path:
            return cls.root() / "Data"
        
        @classmethod
        def platforms(cls) -> Path:
            return cls.data() / "Platforms"
        
        @classmethod
        def xml_glob(cls) -> str:
            return str(cls.platforms() / "*.xml")
        
        @classmethod
        def images(cls) -> Path:
            return cls.root() / "Images"
        
        @classmethod
        def executable(cls) -> Path:
            return cls.root() / "LaunchBox.exe"
        
        @classmethod
        def bigbox_executable(cls) -> Path:
            return cls.root() / "BigBox.exe"

        @staticmethod
        def platform_xml(platform_name: str) -> Path:
            sanitized = platform_name.replace("/", "-").replace("\\", "-").strip()
            if not sanitized:
                raise ValueError("platform_name is required")
            return Paths.LaunchBox.platforms() / f"{sanitized}.xml"

    class Logs:
        @classmethod
        def root(cls) -> Path:
            return _logs_root()
        
        @classmethod
        def changes(cls) -> Path:
            return cls.root() / "changes.jsonl"

    class Backups:
        @classmethod
        def configs(cls) -> Path:
            return _backups_configs()

    class ROMs:
        @classmethod
        def root(cls) -> Path:
            return _roms_root()
        
        @classmethod
        def arcade(cls) -> Path:
            return cls.root() / "Arcade"
        
        @classmethod
        def mame(cls) -> Path:
            return cls.root() / "MAME"

    class Emulators:
        @classmethod
        def root(cls) -> Path:
            return _emulators_root()
        
        @classmethod
        def mame(cls) -> Path:
            return cls.root() / "MAME" / "mame.exe"
        
        @classmethod
        def retroarch(cls) -> Path:
            return cls.root() / "RetroArch" / "retroarch.exe"

    # Back-compat aliases (methods now)
    @classmethod
    def launchbox_root(cls) -> Path:
        return cls.LaunchBox.root()
    
    @classmethod
    def platforms_dir(cls) -> Path:
        return cls.LaunchBox.platforms()
    
    @classmethod
    def platform_xml_glob(cls) -> str:
        return cls.LaunchBox.xml_glob()
    
    @classmethod
    def logs_dir(cls) -> Path:
        return cls.Logs.root()
    
    @classmethod
    def changes_log(cls) -> Path:
        return cls.Logs.changes()
    
    @classmethod
    def backups_dir(cls) -> Path:
        return cls.Backups.configs()

    @classmethod
    def platform_xml(cls, platform_name: str) -> Path:
        """Compatibility shim; prefer Paths.LaunchBox.platform_xml."""
        return cls.LaunchBox.platform_xml(platform_name)

