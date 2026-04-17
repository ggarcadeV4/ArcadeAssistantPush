"""
Deterministic path constants for Arcade Assistant (Playnite focus).

Authoritative cabinet wiring (paths derived from AA_DRIVE_ROOT):
- Playnite root: <DRIVE_LETTER>/Playnite
- Emulators:     <DRIVE_LETTER>/Emulators/{name}
- Arcade ROMs:   <DRIVE_LETTER>/Roms/{platform}
- Console ROMs:  <DRIVE_LETTER>/Console ROMs/{platform}
- BIOS:          <DRIVE_LETTER>/Bios/system
- Logs:          <AA_DRIVE_ROOT>/.aa/logs/
- Backups:       <AA_DRIVE_ROOT>/.aa/backups/

We intentionally avoid runtime discovery here so every component references
the exact same filesystem targets without guessing.

IMPORTANT: No hardcoded drive letters allowed. Use AA_DRIVE_ROOT.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from backend.constants.drive_root import (
    get_bios_root,
    get_console_roms_root,
    get_drive_root,
    get_emulators_root,
    get_launchbox_root,
    get_ledblinky_root,
    get_roms_root,
    get_tools_root,
)


def _get_drive_root() -> Path:
    """Get drive root. No CWD fallback per Slice 2 contract."""
    return get_drive_root(allow_cwd_fallback=False)


def _launchbox_root() -> Path:
    return get_launchbox_root(_get_drive_root())


def _playnite_root() -> Path:
    return _get_drive_root() / "Playnite"


def _tools_root() -> Path:
    return get_tools_root(_get_drive_root())


def _logs_root() -> Path:
    return _get_drive_root() / ".aa" / "logs"


def _backups_configs() -> Path:
    return _get_drive_root() / ".aa" / "backups" / "configs"


def _roms_root() -> Path:
    return get_roms_root(_get_drive_root())


def _console_roms_root() -> Path:
    return get_console_roms_root(_get_drive_root())


def _emulators_root() -> Path:
    return get_emulators_root(_get_drive_root())


def _bios_root() -> Path:
    return get_bios_root(_get_drive_root())


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

    # ----------------------------------------------------------------
    # Playnite (primary frontend — replaced LaunchBox)
    # ----------------------------------------------------------------

    class Playnite:
        """Playnite portable installation paths."""
        
        @classmethod
        def root(cls) -> Path:
            return _playnite_root()
        
        @classmethod
        def desktop_exe(cls) -> Path:
            return cls.root() / "Playnite.DesktopApp.exe"
        
        @classmethod
        def fullscreen_exe(cls) -> Path:
            return cls.root() / "Playnite.FullscreenApp.exe"
        
        @classmethod
        def library(cls) -> Path:
            return cls.root() / "library"
        
        @classmethod
        def emulators_db(cls) -> Path:
            return cls.library() / "emulators.db"
        
        @classmethod
        def games_db(cls) -> Path:
            return cls.library() / "games.db"
        
        @classmethod
        def extensions(cls) -> Path:
            return cls.root() / "Extensions"
        
        @classmethod
        def config_json(cls) -> Path:
            return cls.root() / "config.json"

    # ----------------------------------------------------------------
    # Emulators (all at drive-letter root)
    # ----------------------------------------------------------------

    class Emulators:
        """Emulator executable paths under <DRIVE>/Emulators/."""
        
        @classmethod
        def root(cls) -> Path:
            return _emulators_root()
        
        # --- MAME (two variants: joystick + gamepad) ---
        
        @classmethod
        def mame(cls) -> Path:
            """Default MAME (joystick cabinet config)."""
            return cls.root() / "MAME" / "mame.exe"
        
        @classmethod
        def mame_gamepad(cls) -> Path:
            """MAME configured for gamepad input."""
            return cls.root() / "MAME Gamepad" / "mame.exe"
        
        @classmethod
        def mame_dir(cls) -> Path:
            return cls.root() / "MAME"
        
        # --- RetroArch (two variants: joystick + gamepad) ---
        
        @classmethod
        def retroarch(cls) -> Path:
            """Default RetroArch (joystick cabinet config)."""
            return cls.root() / "RetroArch" / "retroarch.exe"
        
        @classmethod
        def retroarch_gamepad(cls) -> Path:
            """RetroArch configured for gamepad input."""
            return cls.root() / "RetroArch Gamepad" / "retroarch.exe"
        
        @classmethod
        def retroarch_dir(cls) -> Path:
            return cls.root() / "RetroArch"
        
        @classmethod
        def retroarch_cores(cls) -> Path:
            return cls.retroarch_dir() / "cores"
        
        # --- Dolphin Tri-Force (GameCube Triforce arcade board) ---
        
        @classmethod
        def dolphin_triforce(cls) -> Path:
            return cls.root() / "Dolphin Tri-Force" / "Dolphin.exe"
        
        # --- Sega Model 2 Emulator ---
        
        @classmethod
        def model2(cls) -> Path:
            return cls.root() / "Sega Model 2" / "EMULATOR.EXE"
        
        @classmethod
        def model2_multicpu(cls) -> Path:
            return cls.root() / "Sega Model 2" / "emulator_multicpu.exe"
        
        # --- SuperModel (Sega Model 3) ---
        
        @classmethod
        def supermodel(cls) -> Path:
            return cls.root() / "Super Model" / "Supermodel.exe"
        
        # --- TeknoParrot (three variants) ---
        
        @classmethod
        def teknoparrot(cls) -> Path:
            """Default TeknoParrot (joystick)."""
            return cls.root() / "TeknoParrot" / "TeknoParrotUi.exe"
        
        @classmethod
        def teknoparrot_gamepad(cls) -> Path:
            """TeknoParrot configured for gamepad input."""
            return cls.root() / "TeknoParrot Gamepad" / "TeknoParrotUi.exe"
        
        @classmethod
        def teknoparrot_latest(cls) -> Path:
            """Bleeding-edge TeknoParrot build."""
            return cls.root() / "TeknoParrot Latest" / "TeknoParrotUi.exe"
        
        # --- Convenience: list all emulators for health checks ---
        
        @classmethod
        def all_executables(cls) -> dict:
            """Return dict of {name: Path} for all known emulator executables."""
            return {
                "mame": cls.mame(),
                "mame_gamepad": cls.mame_gamepad(),
                "retroarch": cls.retroarch(),
                "retroarch_gamepad": cls.retroarch_gamepad(),
                "dolphin_triforce": cls.dolphin_triforce(),
                "model2": cls.model2(),
                "supermodel": cls.supermodel(),
                "teknoparrot": cls.teknoparrot(),
                "teknoparrot_gamepad": cls.teknoparrot_gamepad(),
                "teknoparrot_latest": cls.teknoparrot_latest(),
            }

    # ----------------------------------------------------------------
    # ROMs — Arcade (A:\Roms\{PLATFORM})
    # ----------------------------------------------------------------

    class ROMs:
        """Arcade ROM directories under <DRIVE>/Roms/."""
        
        @classmethod
        def root(cls) -> Path:
            return _roms_root()
        
        @classmethod
        def mame(cls) -> Path:
            return cls.root() / "MAME"
        
        @classmethod
        def atomiswave(cls) -> Path:
            return cls.root() / "ATOMISWAVE"
        
        @classmethod
        def daphne(cls) -> Path:
            return cls.root() / "DAPHNE"
        
        @classmethod
        def hikaru(cls) -> Path:
            return cls.root() / "HIKARU"
        
        @classmethod
        def model2(cls) -> Path:
            return cls.root() / "MODEL2"
        
        @classmethod
        def model3(cls) -> Path:
            return cls.root() / "MODEL3"
        
        @classmethod
        def naomi(cls) -> Path:
            return cls.root() / "NAOMI"
        
        @classmethod
        def pinball_fx2(cls) -> Path:
            return cls.root() / "PINBALL-FX2"
        
        @classmethod
        def pinball_fx3(cls) -> Path:
            return cls.root() / "PINBALL-FX3"
        
        @classmethod
        def singe_hypseus(cls) -> Path:
            return cls.root() / "SINGE-HYPSEUS"
        
        @classmethod
        def singe2(cls) -> Path:
            return cls.root() / "SINGE2"
        
        @classmethod
        def teknoparrot(cls) -> Path:
            return cls.root() / "TEKNOPARROT"
        
        @classmethod
        def triforce(cls) -> Path:
            return cls.root() / "TRI-FORCE"
        
        @classmethod
        def ttx(cls) -> Path:
            return cls.root() / "TTX"
        
        # Backward compat
        @classmethod
        def arcade(cls) -> Path:
            return cls.root() / "Arcade"
        
        @classmethod
        def all_platforms(cls) -> dict:
            """Return dict of {name: Path} for all arcade ROM directories."""
            return {
                "MAME": cls.mame(),
                "ATOMISWAVE": cls.atomiswave(),
                "DAPHNE": cls.daphne(),
                "HIKARU": cls.hikaru(),
                "MODEL2": cls.model2(),
                "MODEL3": cls.model3(),
                "NAOMI": cls.naomi(),
                "PINBALL-FX2": cls.pinball_fx2(),
                "PINBALL-FX3": cls.pinball_fx3(),
                "SINGE-HYPSEUS": cls.singe_hypseus(),
                "SINGE2": cls.singe2(),
                "TEKNOPARROT": cls.teknoparrot(),
                "TRI-FORCE": cls.triforce(),
                "TTX": cls.ttx(),
            }

    # ----------------------------------------------------------------
    # Console ROMs (A:\Console ROMs\{Platform Name})
    # ----------------------------------------------------------------

    class ConsoleROMs:
        """Console ROM directories under <DRIVE>/Console ROMs/."""
        
        @classmethod
        def root(cls) -> Path:
            return _console_roms_root()
        
        @classmethod
        def get(cls, platform: str) -> Path:
            """Get ROM directory for a specific console platform by name."""
            return cls.root() / platform
        
        # Convenience accessors for common platforms
        @classmethod
        def nes(cls) -> Path:
            return cls.root() / "Nintendo Entertainment System"
        
        @classmethod
        def snes(cls) -> Path:
            return cls.root() / "snes"
        
        @classmethod
        def n64(cls) -> Path:
            return cls.root() / "Nintendo 64"
        
        @classmethod
        def gamecube(cls) -> Path:
            return cls.root() / "Nintendo Games Cube"
        
        @classmethod
        def gba(cls) -> Path:
            return cls.root() / "Nintendo Game Boy Advance"
        
        @classmethod
        def gb(cls) -> Path:
            return cls.root() / "Nintendo Game Boy"
        
        @classmethod
        def nds(cls) -> Path:
            return cls.root() / "nds"
        
        @classmethod
        def genesis(cls) -> Path:
            return cls.root() / "Sega Genesis"
        
        @classmethod
        def dreamcast(cls) -> Path:
            return cls.root() / "Sega Dreamcast"
        
        @classmethod
        def psx(cls) -> Path:
            return cls.root() / "playstation"
        
        @classmethod
        def ps2(cls) -> Path:
            return cls.root() / "playstation 2"
        
        @classmethod
        def psp(cls) -> Path:
            return cls.root() / "psp"
        
        @classmethod
        def atari_2600(cls) -> Path:
            return cls.root() / "Atari 2600"
        
        @classmethod
        def tg16(cls) -> Path:
            return cls.root() / "NEC Turbografx-16"

    # ----------------------------------------------------------------
    # BIOS
    # ----------------------------------------------------------------

    class BIOS:
        """BIOS files for emulators under <DRIVE>/Bios/."""
        
        @classmethod
        def root(cls) -> Path:
            return _bios_root()
        
        @classmethod
        def system(cls) -> Path:
            """Primary system BIOS directory (RetroArch system dir)."""
            return cls.root() / "system"

    # ----------------------------------------------------------------
    # Tools (LEDBlinky, RetroFE, Pegasus, etc.)
    # ----------------------------------------------------------------

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
                return get_ledblinky_root(_get_drive_root())
            
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

    # ----------------------------------------------------------------
    # LaunchBox (legacy — kept for backward compatibility)
    # ----------------------------------------------------------------

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

    # ----------------------------------------------------------------
    # Logs & Backups
    # ----------------------------------------------------------------

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

    # ----------------------------------------------------------------
    # Back-compat aliases (methods now)
    # ----------------------------------------------------------------

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
