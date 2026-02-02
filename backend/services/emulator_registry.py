"""Registry of emulator configuration patterns used by Controller Chuck cascade."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmulatorPattern:
    """Describes how to identify and update a specific emulator."""

    type: str
    display_name: str
    executable_patterns: List[str] = field(default_factory=list)
    config_path_pattern: str = ""
    config_format: str = ""
    priority: int = 50
    key_mapping_rules: Dict[str, str] = field(default_factory=dict)
    quote_strings: bool = False
    section_based: bool = False


def _mame_mapping_rules() -> Dict[str, str]:
    return {
        "p1.up": "P1_UP",
        "p1.down": "P1_DOWN",
        "p1.left": "P1_LEFT",
        "p1.right": "P1_RIGHT",
        "p1.button1": "P1_BUTTON1",
        "p1.button2": "P1_BUTTON2",
        "p1.button3": "P1_BUTTON3",
        "p1.button4": "P1_BUTTON4",
        "p1.button5": "P1_BUTTON5",
        "p1.button6": "P1_BUTTON6",
        "p1.start": "P1_START",
        "p1.select": "P1_SELECT",
    }


def _retroarch_mapping_rules() -> Dict[str, str]:
    return {
        "p1.up": "input_player1_up",
        "p1.down": "input_player1_down",
        "p1.left": "input_player1_left",
        "p1.right": "input_player1_right",
        "p1.button1": "input_player1_b",
        "p1.button2": "input_player1_a",
        "p1.button3": "input_player1_y",
        "p1.button4": "input_player1_x",
        "p1.button5": "input_player1_l",
        "p1.button6": "input_player1_r",
        "p1.start": "input_player1_start",
        "p1.select": "input_player1_select",
    }


def _dolphin_mapping_rules() -> Dict[str, str]:
    return {
        "p1.up": "GCPad1/DPad/Up",
        "p1.down": "GCPad1/DPad/Down",
        "p1.left": "GCPad1/DPad/Left",
        "p1.right": "GCPad1/DPad/Right",
        "p1.button1": "GCPad1/Buttons/A",
        "p1.button2": "GCPad1/Buttons/B",
        "p1.button3": "GCPad1/Buttons/X",
        "p1.button4": "GCPad1/Buttons/Y",
        "p1.button5": "GCPad1/Buttons/L",
        "p1.button6": "GCPad1/Buttons/R",
        "p1.start": "GCPad1/Buttons/Start",
        "p1.select": "GCPad1/Buttons/Z",
    }


def _pcsx2_mapping_rules() -> Dict[str, str]:
    return {
        "p1.up": "Pad1/Up",
        "p1.down": "Pad1/Down",
        "p1.left": "Pad1/Left",
        "p1.right": "Pad1/Right",
        "p1.button1": "Pad1/Cross",
        "p1.button2": "Pad1/Circle",
        "p1.button3": "Pad1/Square",
        "p1.button4": "Pad1/Triangle",
        "p1.button5": "Pad1/L1",
        "p1.button6": "Pad1/R1",
        "p1.start": "Pad1/Start",
        "p1.select": "Pad1/Select",
    }


def _rpcs3_mapping_rules() -> Dict[str, str]:
    return {
        "p1.up": "Input/Player1/Up",
        "p1.down": "Input/Player1/Down",
        "p1.left": "Input/Player1/Left",
        "p1.right": "Input/Player1/Right",
        "p1.button1": "Input/Player1/Cross",
        "p1.button2": "Input/Player1/Circle",
        "p1.button3": "Input/Player1/Square",
        "p1.button4": "Input/Player1/Triangle",
        "p1.button5": "Input/Player1/L1",
        "p1.button6": "Input/Player1/R1",
        "p1.start": "Input/Player1/Start",
        "p1.select": "Input/Player1/Select",
    }


def _cemu_mapping_rules() -> Dict[str, str]:
    return {
        "p1.up": "Controller/Player1/DPad/Up",
        "p1.down": "Controller/Player1/DPad/Down",
        "p1.left": "Controller/Player1/DPad/Left",
        "p1.right": "Controller/Player1/DPad/Right",
        "p1.button1": "Controller/Player1/Buttons/A",
        "p1.button2": "Controller/Player1/Buttons/B",
        "p1.button3": "Controller/Player1/Buttons/X",
        "p1.button4": "Controller/Player1/Buttons/Y",
        "p1.button5": "Controller/Player1/Buttons/L",
        "p1.button6": "Controller/Player1/Buttons/R",
        "p1.start": "Controller/Player1/Buttons/Start",
        "p1.select": "Controller/Player1/Buttons/Select",
    }


def _qt_mapping_rules(prefix: str) -> Dict[str, str]:
    # Used by Citra and Yuzu which share the qt-config.ini structure.
    return {
        "p1.up": f"{prefix}/DPadUp",
        "p1.down": f"{prefix}/DPadDown",
        "p1.left": f"{prefix}/DPadLeft",
        "p1.right": f"{prefix}/DPadRight",
        "p1.button1": f"{prefix}/ButtonA",
        "p1.button2": f"{prefix}/ButtonB",
        "p1.button3": f"{prefix}/ButtonX",
        "p1.button4": f"{prefix}/ButtonY",
        "p1.button5": f"{prefix}/ButtonL",
        "p1.button6": f"{prefix}/ButtonR",
        "p1.start": f"{prefix}/Start",
        "p1.select": f"{prefix}/Select",
    }


def _ppsspp_mapping_rules() -> Dict[str, str]:
    return {
        "p1.up": "ControlMapping/Up",
        "p1.down": "ControlMapping/Down",
        "p1.left": "ControlMapping/Left",
        "p1.right": "ControlMapping/Right",
        "p1.button1": "ControlMapping/Cross",
        "p1.button2": "ControlMapping/Circle",
        "p1.button3": "ControlMapping/Square",
        "p1.button4": "ControlMapping/Triangle",
        "p1.button5": "ControlMapping/L",
        "p1.button6": "ControlMapping/R",
        "p1.start": "ControlMapping/Start",
        "p1.select": "ControlMapping/Select",
    }


def _duckstation_mapping_rules() -> Dict[str, str]:
    return {
        "p1.up": "Controller1/DPadUp",
        "p1.down": "Controller1/DPadDown",
        "p1.left": "Controller1/DPadLeft",
        "p1.right": "Controller1/DPadRight",
        "p1.button1": "Controller1/Cross",
        "p1.button2": "Controller1/Circle",
        "p1.button3": "Controller1/Square",
        "p1.button4": "Controller1/Triangle",
        "p1.button5": "Controller1/L1",
        "p1.button6": "Controller1/R1",
        "p1.start": "Controller1/Start",
        "p1.select": "Controller1/Select",
    }


def _xenia_mapping_rules() -> Dict[str, str]:
    return {
        "p1.up": "Controller1/DPadUp",
        "p1.down": "Controller1/DPadDown",
        "p1.left": "Controller1/DPadLeft",
        "p1.right": "Controller1/DPadRight",
        "p1.button1": "Controller1/ButtonA",
        "p1.button2": "Controller1/ButtonB",
        "p1.button3": "Controller1/ButtonX",
        "p1.button4": "Controller1/ButtonY",
        "p1.button5": "Controller1/LeftBumper",
        "p1.button6": "Controller1/RightBumper",
        "p1.start": "Controller1/Start",
        "p1.select": "Controller1/Back",
    }


def _teknoparrot_mapping_rules() -> Dict[str, str]:
    return {
        "p1.up": "InputUp",
        "p1.down": "InputDown",
        "p1.left": "InputLeft",
        "p1.right": "InputRight",
        "p1.button1": "InputButton1",
        "p1.button2": "InputButton2",
        "p1.button3": "InputButton3",
        "p1.button4": "InputButton4",
        "p1.button5": "InputButton5",
        "p1.button6": "InputButton6",
        "p1.start": "InputStart",
        "p1.select": "InputCoin",
    }


def _model2_mapping_rules() -> Dict[str, str]:
    return {
        "p1.up": "JoyUp",
        "p1.down": "JoyDown",
        "p1.left": "JoyLeft",
        "p1.right": "JoyRight",
        "p1.button1": "JoyButton1",
        "p1.button2": "JoyButton2",
        "p1.button3": "JoyButton3",
        "p1.button4": "JoyButton4",
        "p1.start": "JoyStart",
        "p1.select": "JoyCoin",
    }


def _supermodel_mapping_rules() -> Dict[str, str]:
    return {
        "p1.up": "InputJoy1Up",
        "p1.down": "InputJoy1Down",
        "p1.left": "InputJoy1Left",
        "p1.right": "InputJoy1Right",
        "p1.button1": "InputJoy1Button1",
        "p1.button2": "InputJoy1Button2",
        "p1.button3": "InputJoy1Button3",
        "p1.button4": "InputJoy1Button4",
        "p1.button5": "InputJoy1Button5",
        "p1.button6": "InputJoy1Button6",
        "p1.start": "InputStart1",
        "p1.select": "InputCoin1",
    }


def _demul_mapping_rules() -> Dict[str, str]:
    return {
        "p1.up": "Up",
        "p1.down": "Down",
        "p1.left": "Left",
        "p1.right": "Right",
        "p1.button1": "A",
        "p1.button2": "B",
        "p1.button3": "X",
        "p1.button4": "Y",
        "p1.button5": "LTrigger",
        "p1.button6": "RTrigger",
        "p1.start": "Start",
        "p1.select": "Coin",
    }


def _redream_mapping_rules() -> Dict[str, str]:
    return {
        "p1.up": "port0_dpad_up",
        "p1.down": "port0_dpad_down",
        "p1.left": "port0_dpad_left",
        "p1.right": "port0_dpad_right",
        "p1.button1": "port0_a",
        "p1.button2": "port0_b",
        "p1.button3": "port0_x",
        "p1.button4": "port0_y",
        "p1.button5": "port0_ltrig",
        "p1.button6": "port0_rtrig",
        "p1.start": "port0_start",
        "p1.select": "menu",
    }


def _vita3k_mapping_rules() -> Dict[str, str]:
    return {
        "p1.up": "up",
        "p1.down": "down",
        "p1.left": "left",
        "p1.right": "right",
        "p1.button1": "cross",
        "p1.button2": "circle",
        "p1.button3": "square",
        "p1.button4": "triangle",
        "p1.button5": "l",
        "p1.button6": "r",
        "p1.start": "start",
        "p1.select": "select",
    }


def _built_in_patterns() -> List[EmulatorPattern]:
    """Return the list of stock emulator pattern definitions."""
    return [
        EmulatorPattern(
            type="mame",
            display_name="MAME",
            executable_patterns=["mame.exe", "mame64.exe"],
            config_path_pattern="mame.ini",
            config_format="ini",
            priority=10,
            key_mapping_rules=_mame_mapping_rules(),
            quote_strings=False,
            section_based=True,
        ),
        EmulatorPattern(
            type="retroarch",
            display_name="RetroArch",
            executable_patterns=["retroarch.exe"],
            config_path_pattern="config/retroarch.cfg",
            config_format="cfg",
            priority=20,
            key_mapping_rules=_retroarch_mapping_rules(),
            quote_strings=True,
            section_based=False,
        ),
        EmulatorPattern(
            type="dolphin",
            display_name="Dolphin",
            executable_patterns=["Dolphin.exe"],
            config_path_pattern="User/Config/Dolphin.ini",
            config_format="ini",
            priority=30,
            key_mapping_rules=_dolphin_mapping_rules(),
            quote_strings=False,
            section_based=True,
        ),
        EmulatorPattern(
            type="pcsx2",
            display_name="PCSX2",
            executable_patterns=["pcsx2.exe", "pcsx2-qt.exe"],
            config_path_pattern="~/Documents/PCSX2/inis/PCSX2.ini",  # PCSX2-qt uses user Documents
            config_format="ini",
            priority=40,
            key_mapping_rules=_pcsx2_mapping_rules(),
            quote_strings=False,
            section_based=True,
        ),
        EmulatorPattern(
            type="rpcs3",
            display_name="RPCS3",
            executable_patterns=["rpcs3.exe"],
            config_path_pattern="config.yml",
            config_format="yaml",
            priority=50,
            key_mapping_rules=_rpcs3_mapping_rules(),
            quote_strings=False,
            section_based=False,
        ),
        EmulatorPattern(
            type="cemu",
            display_name="Cemu",
            executable_patterns=["Cemu.exe"],
            config_path_pattern="settings.xml",
            config_format="xml",
            priority=50,
            key_mapping_rules=_cemu_mapping_rules(),
            quote_strings=False,
            section_based=False,
        ),
        EmulatorPattern(
            type="citra",
            display_name="Citra",
            executable_patterns=["citra.exe", "citra-qt.exe"],
            config_path_pattern="qt-config.ini",
            config_format="ini",
            priority=50,
            key_mapping_rules=_qt_mapping_rules("Controls/Player1"),
            quote_strings=False,
            section_based=True,
        ),
        EmulatorPattern(
            type="yuzu",
            display_name="Yuzu",
            executable_patterns=["yuzu.exe"],
            config_path_pattern="qt-config.ini",
            config_format="ini",
            priority=50,
            key_mapping_rules=_qt_mapping_rules("Controls/Player1"),
            quote_strings=False,
            section_based=True,
        ),
        EmulatorPattern(
            type="ppsspp",
            display_name="PPSSPP",
            executable_patterns=["PPSSPPWindows.exe", "PPSSPP.exe"],
            config_path_pattern="ppsspp.ini",
            config_format="ini",
            priority=50,
            key_mapping_rules=_ppsspp_mapping_rules(),
            quote_strings=False,
            section_based=True,
        ),
        EmulatorPattern(
            type="duckstation",
            display_name="Duckstation",
            executable_patterns=[
                "duckstation-qt-x64-ReleaseLTCG.exe",
                "duckstation.exe",
            ],
            config_path_pattern="settings.ini",
            config_format="ini",
            priority=50,
            key_mapping_rules=_duckstation_mapping_rules(),
            quote_strings=False,
            section_based=True,
        ),
        EmulatorPattern(
            type="xenia",
            display_name="Xenia",
            executable_patterns=["xenia.exe", "xenia_canary.exe"],
            config_path_pattern="xenia.config.toml",
            config_format="toml",
            priority=50,
            key_mapping_rules=_xenia_mapping_rules(),
            quote_strings=False,
            section_based=False,
        ),
        EmulatorPattern(
            type="teknoparrot",
            display_name="TeknoParrot",
            executable_patterns=["TeknoParrotUi.exe"],
            config_path_pattern="UserProfiles",
            config_format="xml",
            priority=60,
            key_mapping_rules=_teknoparrot_mapping_rules(),
            quote_strings=False,
            section_based=False,
        ),
        EmulatorPattern(
            type="model2",
            display_name="Sega Model 2",
            executable_patterns=["EMULATOR.EXE", "emulator_multicpu.exe"],
            config_path_pattern="EMULATOR.INI",
            config_format="ini",
            priority=65,
            key_mapping_rules=_model2_mapping_rules(),
            quote_strings=False,
            section_based=True,
        ),
        EmulatorPattern(
            type="supermodel",
            display_name="Super Model",
            executable_patterns=["Supermodel.exe"],
            config_path_pattern="Config/Supermodel.ini",
            config_format="ini",
            priority=70,
            key_mapping_rules=_supermodel_mapping_rules(),
            quote_strings=False,
            section_based=True,
        ),
        EmulatorPattern(
            type="flycast",
            display_name="Flycast",
            executable_patterns=["flycast.exe"],
            config_path_pattern="emu.cfg",
            config_format="cfg",
            priority=75,
            key_mapping_rules=_demul_mapping_rules(),  # Flycast uses similar Dreamcast mapping
            quote_strings=False,
            section_based=False,
        ),
        EmulatorPattern(
            type="demul",
            display_name="Demul",
            executable_patterns=["demul.exe"],
            config_path_pattern="Demul.ini",
            config_format="ini",
            priority=75,
            key_mapping_rules=_demul_mapping_rules(),
            quote_strings=False,
            section_based=True,
        ),
        EmulatorPattern(
            type="redream",
            display_name="Redream",
            executable_patterns=["redream.exe"],
            config_path_pattern="redream.cfg",
            config_format="cfg",
            priority=75,
            key_mapping_rules=_redream_mapping_rules(),
            quote_strings=False,
            section_based=False,
        ),
        EmulatorPattern(
            type="epsxe",
            display_name="ePSXe",
            executable_patterns=["ePSXe.exe"],
            config_path_pattern="ePSXe.ini",
            config_format="ini",
            priority=75,
            key_mapping_rules=_duckstation_mapping_rules(),  # Similar PS1 mapping
            quote_strings=False,
            section_based=True,
        ),
        EmulatorPattern(
            type="mesen",
            display_name="Mesen",
            executable_patterns=["Mesen.exe"],
            config_path_pattern="settings.xml",
            config_format="xml",
            priority=75,
            key_mapping_rules=_retroarch_mapping_rules(),  # Similar NES mapping
            quote_strings=False,
            section_based=False,
        ),
        EmulatorPattern(
            type="snes9x",
            display_name="Snes9x",
            executable_patterns=["snes9x.exe", "snes9x-x64.exe"],
            config_path_pattern="snes9x.conf",
            config_format="conf",
            priority=75,
            key_mapping_rules=_retroarch_mapping_rules(),  # Similar SNES mapping
            quote_strings=False,
            section_based=False,
        ),
        EmulatorPattern(
            type="vita3k",
            display_name="Vita3K",
            executable_patterns=["Vita3K.exe"],
            config_path_pattern="config.yml",
            config_format="yaml",
            priority=75,
            key_mapping_rules=_vita3k_mapping_rules(),
            quote_strings=False,
            section_based=False,
        ),
        EmulatorPattern(
            type="cxbx",
            display_name="CXBX-Reloaded",
            executable_patterns=["cxbx.exe", "cxbxr-ldr.exe"],
            config_path_pattern="settings.ini",
            config_format="ini",
            priority=75,
            key_mapping_rules=_xenia_mapping_rules(),  # Similar Xbox mapping
            quote_strings=False,
            section_based=False,
        ),
        EmulatorPattern(
            type="hypseus",
            display_name="Hypseus Singe",
            executable_patterns=["hypseus.exe", "daphne.exe"],
            config_path_pattern="hypinput.ini",
            config_format="ini",
            priority=80,
            key_mapping_rules=_mame_mapping_rules(),  # Similar arcade mapping
            quote_strings=False,
            section_based=False,
        ),
    ]


class EmulatorRegistry:
    """Registry containing the known emulator patterns."""

    def __init__(self, patterns: Optional[Sequence[EmulatorPattern]] = None) -> None:
        self._patterns: Dict[str, EmulatorPattern] = {}
        source = patterns or _built_in_patterns()
        for pattern in source:
            self.add_pattern(pattern)

    def get_pattern(self, emulator_type: str) -> Optional[EmulatorPattern]:
        """Return the pattern for the requested emulator type."""
        if not emulator_type:
            return None
        return self._patterns.get(emulator_type.lower())

    def identify_by_executable(self, executable_name: str) -> Optional[str]:
        """Infer an emulator type based on an executable filename."""
        if not executable_name:
            return None

        candidate_name = Path(executable_name).name.lower()
        candidate_stub = candidate_name.split(".", 1)[0]

        for pattern in sorted(self._patterns.values(), key=lambda info: info.priority):
            for raw in pattern.executable_patterns:
                normalized = Path(raw).name.lower()
                normalized_stub = normalized.split(".", 1)[0]
                if candidate_name == normalized or candidate_stub == normalized_stub:
                    return pattern.type
        return None

    def add_pattern(self, pattern: EmulatorPattern) -> None:
        """Add or replace a pattern definition."""
        key = pattern.type.lower()
        if key in self._patterns:
            logger.debug("Replacing emulator pattern for type: %s", key)
        else:
            logger.debug("Registering emulator pattern for type: %s", key)
        self._patterns[key] = pattern

    def get_all_patterns(self) -> Dict[str, EmulatorPattern]:
        """Return a copy of all registered patterns keyed by emulator type."""
        return dict(self._patterns)


# Expose a ready-to-use registry for callers that do not need custom wiring.
default_registry = EmulatorRegistry()
