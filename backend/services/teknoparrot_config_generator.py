"""
TeknoParrot Config Generator for Controller Chuck.

Defines canonical control schemas for TeknoParrot games (racing, lightgun)
and provides preview/apply operations for TP UserProfile XML bindings.

Safety: Uses Preview → Apply → Backup → Log flow.
Chuck outputs "what correct looks like"; Wizard (or cascade) writes files.

Architecture:
- Canonical schema defines logical controls per game category (racing, lightgun)
- Maps arcade panel controls (from controls.json) to TP input binding names
- Generates diff-friendly patches for TP UserProfile XML
- Does NOT write files directly; returns structured payload for Wizard/cascade
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Enums & Constants
# -----------------------------------------------------------------------------

class TPGameCategory(str, Enum):
    """TeknoParrot game categories with distinct control layouts."""
    RACING = "racing"
    LIGHTGUN = "lightgun"
    FIGHTING = "fighting"
    GENERIC = "generic"


class TPInputType(str, Enum):
    """TeknoParrot input types."""
    BUTTON = "Button"
    AXIS = "Axis"
    AXIS_POSITIVE = "AxisPositive"
    AXIS_NEGATIVE = "AxisNegative"


class TPInputMode(str, Enum):
    """TeknoParrot input device mode (XInput vs DirectInput)."""
    XINPUT = "xinput"
    DINPUT = "dinput"


# XInput button mappings for TeknoParrot
# Maps arcade panel control to TeknoParrot XInput binding string
XINPUT_BUTTON_MAP = {
    # Player 1 buttons
    "p1.button1": "XInput/0/Button A",
    "p1.button2": "XInput/0/Button B",
    "p1.button3": "XInput/0/Button X",
    "p1.button4": "XInput/0/Button Y",
    "p1.button5": "XInput/0/Left Shoulder",
    "p1.button6": "XInput/0/Right Shoulder",
    "p1.button7": "XInput/0/Left Trigger",
    "p1.button8": "XInput/0/Right Trigger",
    "p1.start": "XInput/0/Start",
    "p1.coin": "XInput/0/Back",
    "p1.up": "XInput/0/DPad Up",
    "p1.down": "XInput/0/DPad Down",
    "p1.left": "XInput/0/DPad Left",
    "p1.right": "XInput/0/DPad Right",
    # Player 2 buttons (second controller)
    "p2.button1": "XInput/1/Button A",
    "p2.button2": "XInput/1/Button B",
    "p2.button3": "XInput/1/Button X",
    "p2.button4": "XInput/1/Button Y",
    "p2.button5": "XInput/1/Left Shoulder",
    "p2.button6": "XInput/1/Right Shoulder",
    "p2.button7": "XInput/1/Left Trigger",
    "p2.button8": "XInput/1/Right Trigger",
    "p2.start": "XInput/1/Start",
    "p2.coin": "XInput/1/Back",
    "p2.up": "XInput/1/DPad Up",
    "p2.down": "XInput/1/DPad Down",
    "p2.left": "XInput/1/DPad Left",
    "p2.right": "XInput/1/DPad Right",
    # Player 3 buttons (third controller)
    "p3.button1": "XInput/2/Button A",
    "p3.button2": "XInput/2/Button B",
    "p3.button3": "XInput/2/Button X",
    "p3.button4": "XInput/2/Button Y",
    "p3.start": "XInput/2/Start",
    "p3.coin": "XInput/2/Back",
    # Player 4 buttons (fourth controller)
    "p4.button1": "XInput/3/Button A",
    "p4.button2": "XInput/3/Button B",
    "p4.button3": "XInput/3/Button X",
    "p4.button4": "XInput/3/Button Y",
    "p4.start": "XInput/3/Start",
    "p4.coin": "XInput/3/Back",
}

# XInput axis mappings for steering/aiming
XINPUT_AXIS_MAP = {
    "p1.steering": "XInput/0/Left Stick X",
    "p1.gas": "XInput/0/Right Trigger",
    "p1.brake": "XInput/0/Left Trigger",
    "p1.aim_x": "XInput/0/Right Stick X",
    "p1.aim_y": "XInput/0/Right Stick Y",
    "p2.steering": "XInput/1/Left Stick X",
    "p2.gas": "XInput/1/Right Trigger",
    "p2.brake": "XInput/1/Left Trigger",
}


# -----------------------------------------------------------------------------
# Canonical Control Schemas
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class TPControlDefinition:
    """Definition of a single TeknoParrot control input."""
    tp_name: str               # TeknoParrot XML element name (e.g., "InputGas", "InputSteer")
    input_type: TPInputType    # Type of input
    description: str           # Human-readable description
    required: bool = True      # Whether this control is required for the game category
    default_binding: Optional[str] = None  # Default panel control to map to
    axis_range: Optional[Tuple[int, int]] = None  # For axis inputs: (min, max)


@dataclass
class TPCanonicalSchema:
    """Canonical control schema for a TeknoParrot game category."""
    category: TPGameCategory
    description: str
    controls: Dict[str, TPControlDefinition] = field(default_factory=dict)
    
    def get_required_controls(self) -> List[str]:
        """Return list of required control names."""
        return [name for name, ctrl in self.controls.items() if ctrl.required]
    
    def get_optional_controls(self) -> List[str]:
        """Return list of optional control names."""
        return [name for name, ctrl in self.controls.items() if not ctrl.required]


# Racing game canonical schema
RACING_SCHEMA = TPCanonicalSchema(
    category=TPGameCategory.RACING,
    description="Racing/driving games (wheel, pedals, gear)",
    controls={
        "wheel": TPControlDefinition(
            tp_name="InputSteer",
            input_type=TPInputType.AXIS,
            description="Steering wheel axis",
            required=True,
            axis_range=(-32768, 32767),
        ),
        "gas": TPControlDefinition(
            tp_name="InputGas",
            input_type=TPInputType.AXIS_POSITIVE,
            description="Gas/accelerator pedal",
            required=True,
            default_binding="p1.button2",
        ),
        "brake": TPControlDefinition(
            tp_name="InputBrake",
            input_type=TPInputType.AXIS_POSITIVE,
            description="Brake pedal",
            required=True,
            default_binding="p1.button3",
        ),
        "gear_up": TPControlDefinition(
            tp_name="InputGearUp",
            input_type=TPInputType.BUTTON,
            description="Gear shift up",
            required=False,
            default_binding="p1.button5",
        ),
        "gear_down": TPControlDefinition(
            tp_name="InputGearDown",
            input_type=TPInputType.BUTTON,
            description="Gear shift down",
            required=False,
            default_binding="p1.button6",
        ),
        "start": TPControlDefinition(
            tp_name="InputStart",
            input_type=TPInputType.BUTTON,
            description="Start button",
            required=True,
            default_binding="p1.start",
        ),
        "coin": TPControlDefinition(
            tp_name="InputCoin",
            input_type=TPInputType.BUTTON,
            description="Coin/credit button",
            required=True,
            default_binding="p1.coin",
        ),
        "service": TPControlDefinition(
            tp_name="InputService",
            input_type=TPInputType.BUTTON,
            description="Service button",
            required=False,
        ),
        "view": TPControlDefinition(
            tp_name="InputChangeView",
            input_type=TPInputType.BUTTON,
            description="Change camera/view",
            required=False,
            default_binding="p1.button4",
        ),
        "nitro": TPControlDefinition(
            tp_name="InputNitro",
            input_type=TPInputType.BUTTON,
            description="Nitro/boost button",
            required=False,
            default_binding="p1.button1",
        ),
    }
)

# Lightgun game canonical schema
LIGHTGUN_SCHEMA = TPCanonicalSchema(
    category=TPGameCategory.LIGHTGUN,
    description="Light gun shooting games",
    controls={
        "trigger": TPControlDefinition(
            tp_name="InputTrigger",
            input_type=TPInputType.BUTTON,
            description="Gun trigger",
            required=True,
        ),
        "reload": TPControlDefinition(
            tp_name="InputReload",
            input_type=TPInputType.BUTTON,
            description="Reload/pump action",
            required=True,
        ),
        "start": TPControlDefinition(
            tp_name="InputStart",
            input_type=TPInputType.BUTTON,
            description="Start button",
            required=True,
            default_binding="p1.start",
        ),
        "coin": TPControlDefinition(
            tp_name="InputCoin",
            input_type=TPInputType.BUTTON,
            description="Coin/credit button",
            required=True,
            default_binding="p1.coin",
        ),
        "service": TPControlDefinition(
            tp_name="InputService",
            input_type=TPInputType.BUTTON,
            description="Service button",
            required=False,
        ),
        "aim_x": TPControlDefinition(
            tp_name="InputAimX",
            input_type=TPInputType.AXIS,
            description="Gun aim X axis",
            required=True,
            axis_range=(0, 65535),
        ),
        "aim_y": TPControlDefinition(
            tp_name="InputAimY",
            input_type=TPInputType.AXIS,
            description="Gun aim Y axis",
            required=True,
            axis_range=(0, 65535),
        ),
        "grenade": TPControlDefinition(
            tp_name="InputGrenade",
            input_type=TPInputType.BUTTON,
            description="Grenade/special button",
            required=False,
        ),
        "cover": TPControlDefinition(
            tp_name="InputCover",
            input_type=TPInputType.BUTTON,
            description="Take cover button",
            required=False,
        ),
    }
)

# Fighting game schema (6-button layout: LP/MP/HP/LK/MK/HK)
FIGHTING_SCHEMA = TPCanonicalSchema(
    category=TPGameCategory.FIGHTING,
    description="Fighting games (6-button layout + joystick)",
    controls={
        # Joystick directions
        "up": TPControlDefinition(
            tp_name="InputUp",
            input_type=TPInputType.BUTTON,
            description="Joystick up",
            required=True,
            default_binding="p1.up",
        ),
        "down": TPControlDefinition(
            tp_name="InputDown",
            input_type=TPInputType.BUTTON,
            description="Joystick down",
            required=True,
            default_binding="p1.down",
        ),
        "left": TPControlDefinition(
            tp_name="InputLeft",
            input_type=TPInputType.BUTTON,
            description="Joystick left",
            required=True,
            default_binding="p1.left",
        ),
        "right": TPControlDefinition(
            tp_name="InputRight",
            input_type=TPInputType.BUTTON,
            description="Joystick right",
            required=True,
            default_binding="p1.right",
        ),
        # 6-button fighting layout (top row: punches, bottom row: kicks)
        "lp": TPControlDefinition(
            tp_name="InputButton1",
            input_type=TPInputType.BUTTON,
            description="Light Punch (LP)",
            required=True,
            default_binding="p1.button1",
        ),
        "mp": TPControlDefinition(
            tp_name="InputButton2",
            input_type=TPInputType.BUTTON,
            description="Medium Punch (MP)",
            required=True,
            default_binding="p1.button2",
        ),
        "hp": TPControlDefinition(
            tp_name="InputButton3",
            input_type=TPInputType.BUTTON,
            description="Heavy Punch (HP)",
            required=True,
            default_binding="p1.button3",
        ),
        "lk": TPControlDefinition(
            tp_name="InputButton4",
            input_type=TPInputType.BUTTON,
            description="Light Kick (LK)",
            required=True,
            default_binding="p1.button4",
        ),
        "mk": TPControlDefinition(
            tp_name="InputButton5",
            input_type=TPInputType.BUTTON,
            description="Medium Kick (MK)",
            required=True,
            default_binding="p1.button5",
        ),
        "hk": TPControlDefinition(
            tp_name="InputButton6",
            input_type=TPInputType.BUTTON,
            description="Heavy Kick (HK)",
            required=True,
            default_binding="p1.button6",
        ),
        # Standard buttons
        "start": TPControlDefinition(
            tp_name="InputStart",
            input_type=TPInputType.BUTTON,
            description="Start button",
            required=True,
            default_binding="p1.start",
        ),
        "coin": TPControlDefinition(
            tp_name="InputCoin",
            input_type=TPInputType.BUTTON,
            description="Coin/credit button",
            required=True,
            default_binding="p1.coin",
        ),
        "service": TPControlDefinition(
            tp_name="InputService",
            input_type=TPInputType.BUTTON,
            description="Service button",
            required=False,
        ),
    }
)

# Generic game schema (button-heavy, for unclassified games)
GENERIC_SCHEMA = TPCanonicalSchema(
    category=TPGameCategory.GENERIC,
    description="Generic arcade games (buttons + joystick)",
    controls={
        "up": TPControlDefinition(
            tp_name="InputUp",
            input_type=TPInputType.BUTTON,
            description="Joystick up",
            required=True,
            default_binding="p1.up",
        ),
        "down": TPControlDefinition(
            tp_name="InputDown",
            input_type=TPInputType.BUTTON,
            description="Joystick down",
            required=True,
            default_binding="p1.down",
        ),
        "left": TPControlDefinition(
            tp_name="InputLeft",
            input_type=TPInputType.BUTTON,
            description="Joystick left",
            required=True,
            default_binding="p1.left",
        ),
        "right": TPControlDefinition(
            tp_name="InputRight",
            input_type=TPInputType.BUTTON,
            description="Joystick right",
            required=True,
            default_binding="p1.right",
        ),
        "button1": TPControlDefinition(
            tp_name="InputButton1",
            input_type=TPInputType.BUTTON,
            description="Button 1",
            required=True,
            default_binding="p1.button1",
        ),
        "button2": TPControlDefinition(
            tp_name="InputButton2",
            input_type=TPInputType.BUTTON,
            description="Button 2",
            required=True,
            default_binding="p1.button2",
        ),
        "button3": TPControlDefinition(
            tp_name="InputButton3",
            input_type=TPInputType.BUTTON,
            description="Button 3",
            required=False,
            default_binding="p1.button3",
        ),
        "button4": TPControlDefinition(
            tp_name="InputButton4",
            input_type=TPInputType.BUTTON,
            description="Button 4",
            required=False,
            default_binding="p1.button4",
        ),
        "button5": TPControlDefinition(
            tp_name="InputButton5",
            input_type=TPInputType.BUTTON,
            description="Button 5",
            required=False,
            default_binding="p1.button5",
        ),
        "button6": TPControlDefinition(
            tp_name="InputButton6",
            input_type=TPInputType.BUTTON,
            description="Button 6",
            required=False,
            default_binding="p1.button6",
        ),
        "start": TPControlDefinition(
            tp_name="InputStart",
            input_type=TPInputType.BUTTON,
            description="Start button",
            required=True,
            default_binding="p1.start",
        ),
        "coin": TPControlDefinition(
            tp_name="InputCoin",
            input_type=TPInputType.BUTTON,
            description="Coin/credit button",
            required=True,
            default_binding="p1.coin",
        ),
        "service": TPControlDefinition(
            tp_name="InputService",
            input_type=TPInputType.BUTTON,
            description="Service button",
            required=False,
        ),
    }
)

# Registry of schemas by category
SCHEMA_REGISTRY: Dict[TPGameCategory, TPCanonicalSchema] = {
    TPGameCategory.RACING: RACING_SCHEMA,
    TPGameCategory.LIGHTGUN: LIGHTGUN_SCHEMA,
    TPGameCategory.FIGHTING: FIGHTING_SCHEMA,
    TPGameCategory.GENERIC: GENERIC_SCHEMA,
}


# -----------------------------------------------------------------------------
# Known Game Database (maps game profile to category)
# -----------------------------------------------------------------------------

# Maps TP profile names (lowercase) to game category
# Note: Profile names are normalized (lowercase, no spaces/dashes/underscores)
KNOWN_GAMES: Dict[str, TPGameCategory] = {
    # ==========================================================================
    # RACING GAMES
    # ==========================================================================
    # Initial D series
    "initiald8": TPGameCategory.RACING,
    "initialdarcade": TPGameCategory.RACING,
    "initiald5": TPGameCategory.RACING,
    "initiald6": TPGameCategory.RACING,
    "initiald7": TPGameCategory.RACING,
    "initialdthearcade": TPGameCategory.RACING,
    "initialdarcadestage": TPGameCategory.RACING,
    # Wangan Midnight Maximum Tune series
    "wmmt5": TPGameCategory.RACING,
    "wmmt5dx": TPGameCategory.RACING,
    "wmmt5dxplus": TPGameCategory.RACING,
    "wmmt6": TPGameCategory.RACING,
    "wmmt6r": TPGameCategory.RACING,
    "wmmt6rr": TPGameCategory.RACING,
    "wanganmidnight": TPGameCategory.RACING,
    # OutRun series
    "outrun2sp": TPGameCategory.RACING,
    "outrun2spdx": TPGameCategory.RACING,
    "outrun2": TPGameCategory.RACING,
    # Other racing
    "vt4": TPGameCategory.RACING,  # Virtua Tennis (uses steering-like controls)
    "vt3": TPGameCategory.RACING,
    "afterburner": TPGameCategory.RACING,
    "afterburnerclimax": TPGameCategory.RACING,
    "srallyevo": TPGameCategory.RACING,
    "srallyc": TPGameCategory.RACING,
    "daytona3": TPGameCategory.RACING,  # Daytona 3 Championship USA
    "daytonausa": TPGameCategory.RACING,
    "daytonausa2": TPGameCategory.RACING,
    "f355challenge": TPGameCategory.RACING,
    "cruzn": TPGameCategory.RACING,
    "cruznexotica": TPGameCategory.RACING,
    "cruznworld": TPGameCategory.RACING,
    "cruznblast": TPGameCategory.RACING,
    "fastfurious": TPGameCategory.RACING,
    "fastfuriousdrift": TPGameCategory.RACING,
    "fastfurioussupercar": TPGameCategory.RACING,
    "mariokart": TPGameCategory.RACING,
    "mkgp": TPGameCategory.RACING,  # Mario Kart GP
    "mkgpdx": TPGameCategory.RACING,
    
    # ==========================================================================
    # LIGHTGUN GAMES
    # ==========================================================================
    # House of the Dead series
    "hotd4": TPGameCategory.LIGHTGUN,
    "hotd4sp": TPGameCategory.LIGHTGUN,
    "hotd": TPGameCategory.LIGHTGUN,
    "hotd2": TPGameCategory.LIGHTGUN,
    "hotd3": TPGameCategory.LIGHTGUN,
    "houseofthedead": TPGameCategory.LIGHTGUN,
    "houseofthedead4": TPGameCategory.LIGHTGUN,
    # Let's Go Island/Jungle
    "lgi": TPGameCategory.LIGHTGUN,
    "lgi2": TPGameCategory.LIGHTGUN,
    "lgi3": TPGameCategory.LIGHTGUN,
    "letsgoisland": TPGameCategory.LIGHTGUN,
    "letsgojungle": TPGameCategory.LIGHTGUN,
    # Other lightgun
    "rambo": TPGameCategory.LIGHTGUN,
    "aliens": TPGameCategory.LIGHTGUN,
    "aliensextermination": TPGameCategory.LIGHTGUN,
    "transformers": TPGameCategory.LIGHTGUN,
    "transformershumanalliance": TPGameCategory.LIGHTGUN,
    "terminator": TPGameCategory.LIGHTGUN,
    "terminatorsalvation": TPGameCategory.LIGHTGUN,
    "ghostsquad": TPGameCategory.LIGHTGUN,
    "ghostsquadevo": TPGameCategory.LIGHTGUN,
    "deadstorm": TPGameCategory.LIGHTGUN,
    "deadstormpirates": TPGameCategory.LIGHTGUN,
    "timecrisis4": TPGameCategory.LIGHTGUN,
    "timecrisis5": TPGameCategory.LIGHTGUN,
    "timecrisis": TPGameCategory.LIGHTGUN,
    "razing": TPGameCategory.LIGHTGUN,
    "razingstorm": TPGameCategory.LIGHTGUN,
    "operationghost": TPGameCategory.LIGHTGUN,
    "darkescapearcade": TPGameCategory.LIGHTGUN,
    "jurassicpark": TPGameCategory.LIGHTGUN,
    "lostland": TPGameCategory.LIGHTGUN,
    "lostlandadventure": TPGameCategory.LIGHTGUN,
    
    # ==========================================================================
    # FIGHTING GAMES
    # ==========================================================================
    # Tekken series
    "tekken7": TPGameCategory.FIGHTING,
    "tekken7fr": TPGameCategory.FIGHTING,
    "tekken7fatedretribution": TPGameCategory.FIGHTING,
    "tekken8": TPGameCategory.FIGHTING,
    "tekken": TPGameCategory.FIGHTING,
    "tekkentag2": TPGameCategory.FIGHTING,
    "tekkentagtournament2": TPGameCategory.FIGHTING,
    # Pokken
    "pokken": TPGameCategory.FIGHTING,
    "pokkentournament": TPGameCategory.FIGHTING,
    "pokkentournamentdx": TPGameCategory.FIGHTING,
    # Arc System Works fighters
    "mbaa": TPGameCategory.FIGHTING,
    "mbaacc": TPGameCategory.FIGHTING,  # Melty Blood AACC
    "meltyblood": TPGameCategory.FIGHTING,
    "meltybloodactress": TPGameCategory.FIGHTING,
    "meltybloodtypelumina": TPGameCategory.FIGHTING,
    "blazblue": TPGameCategory.FIGHTING,
    "blazbluect": TPGameCategory.FIGHTING,
    "blazbluecs": TPGameCategory.FIGHTING,
    "blazbluecf": TPGameCategory.FIGHTING,
    "blazbluecentralfiction": TPGameCategory.FIGHTING,
    "blazbluechronophantasma": TPGameCategory.FIGHTING,
    "blazbluecpex": TPGameCategory.FIGHTING,
    "blazbluecsex": TPGameCategory.FIGHTING,
    "guiltygear": TPGameCategory.FIGHTING,
    "guiltygearxrd": TPGameCategory.FIGHTING,
    "guiltygearxrdsign": TPGameCategory.FIGHTING,
    "guiltygearxrdrevelator": TPGameCategory.FIGHTING,
    "guiltygearxrdrev2": TPGameCategory.FIGHTING,
    "ggxrd": TPGameCategory.FIGHTING,
    "ggxrdsign": TPGameCategory.FIGHTING,
    "ggxrdr": TPGameCategory.FIGHTING,
    "ggxrdrev2": TPGameCategory.FIGHTING,
    "ggst": TPGameCategory.FIGHTING,  # Guilty Gear Strive
    "guiltygearstrive": TPGameCategory.FIGHTING,
    "granblue": TPGameCategory.FIGHTING,
    "granblueversus": TPGameCategory.FIGHTING,
    "gbvs": TPGameCategory.FIGHTING,
    "dragonballfighterz": TPGameCategory.FIGHTING,
    "dbfz": TPGameCategory.FIGHTING,
    "dnf": TPGameCategory.FIGHTING,  # DNF Duel
    "dnfduel": TPGameCategory.FIGHTING,
    "personaarena": TPGameCategory.FIGHTING,
    "persona4arena": TPGameCategory.FIGHTING,
    "p4au": TPGameCategory.FIGHTING,
    "p4a": TPGameCategory.FIGHTING,
    "bbtag": TPGameCategory.FIGHTING,  # BlazBlue Cross Tag Battle
    "blazbluecrosstag": TPGameCategory.FIGHTING,
    # Capcom fighters
    "sf4": TPGameCategory.FIGHTING,
    "sf4arcadeedition": TPGameCategory.FIGHTING,
    "usf4": TPGameCategory.FIGHTING,
    "ultrastreetfighter4": TPGameCategory.FIGHTING,
    "streetfighter4": TPGameCategory.FIGHTING,
    "streetfighter5": TPGameCategory.FIGHTING,
    "sf5": TPGameCategory.FIGHTING,
    "sf6": TPGameCategory.FIGHTING,
    "streetfighter6": TPGameCategory.FIGHTING,
    "mvci": TPGameCategory.FIGHTING,  # Marvel vs Capcom Infinite
    "mvc": TPGameCategory.FIGHTING,
    "marvelvscapcom": TPGameCategory.FIGHTING,
    "umvc3": TPGameCategory.FIGHTING,  # Ultimate Marvel vs Capcom 3
    # SNK fighters
    "kof13": TPGameCategory.FIGHTING,
    "kof14": TPGameCategory.FIGHTING,
    "kof15": TPGameCategory.FIGHTING,
    "kof": TPGameCategory.FIGHTING,
    "kingoffighters": TPGameCategory.FIGHTING,
    "samshodown": TPGameCategory.FIGHTING,
    "samsho": TPGameCategory.FIGHTING,
    "samuraishodown": TPGameCategory.FIGHTING,
    "fatalfury": TPGameCategory.FIGHTING,
    "garou": TPGameCategory.FIGHTING,
    # Dead or Alive
    "doa5": TPGameCategory.FIGHTING,
    "doa6": TPGameCategory.FIGHTING,
    "deadoralive5": TPGameCategory.FIGHTING,
    "deadoralive6": TPGameCategory.FIGHTING,
    # Virtua Fighter
    "vf5": TPGameCategory.FIGHTING,
    "vf5fs": TPGameCategory.FIGHTING,
    "virtuafighter5": TPGameCategory.FIGHTING,
    "virtuafighter5fs": TPGameCategory.FIGHTING,
    "virtuafighter5ultimateshowdown": TPGameCategory.FIGHTING,
    # Soul Calibur
    "soulcalibur6": TPGameCategory.FIGHTING,
    "sc6": TPGameCategory.FIGHTING,
    # Other fighters
    "dengenreki": TPGameCategory.FIGHTING,  # Dengeki Bunko Fighting Climax
    "dengeki": TPGameCategory.FIGHTING,
    "dengekibunko": TPGameCategory.FIGHTING,
    "fightingclimax": TPGameCategory.FIGHTING,
    "fightingclimaxignition": TPGameCategory.FIGHTING,
    "undernight": TPGameCategory.FIGHTING,  # Under Night In-Birth
    "unib": TPGameCategory.FIGHTING,
    "uniclr": TPGameCategory.FIGHTING,
    "unist": TPGameCategory.FIGHTING,
    "aquapazza": TPGameCategory.FIGHTING,
    "arcana": TPGameCategory.FIGHTING,
    "arcanaheart": TPGameCategory.FIGHTING,
    "arcanaheart3": TPGameCategory.FIGHTING,
    "nitroplus": TPGameCategory.FIGHTING,
    "nitroplusblasterz": TPGameCategory.FIGHTING,
    "skullgirls": TPGameCategory.FIGHTING,
    "koihime": TPGameCategory.FIGHTING,  # Koihime Enbu
    "koihimeenbu": TPGameCategory.FIGHTING,
    "mortal": TPGameCategory.FIGHTING,
    "mortalkombat": TPGameCategory.FIGHTING,
    "mk11": TPGameCategory.FIGHTING,
    "injustice": TPGameCategory.FIGHTING,
    "injustice2": TPGameCategory.FIGHTING,
}


def get_game_category(profile_name: str) -> Optional[TPGameCategory]:
    """Determine game category from profile name.
    
    Returns None if game is unknown/unsupported.
    """
    # Normalize profile name: remove .xml, lowercase, remove spaces/dashes
    normalized = profile_name.lower().replace(".xml", "").replace(" ", "").replace("-", "").replace("_", "")
    
    # Direct lookup
    if normalized in KNOWN_GAMES:
        return KNOWN_GAMES[normalized]
    
    # Partial match heuristics
    for key, category in KNOWN_GAMES.items():
        if key in normalized or normalized in key:
            return category
    
    return None


def get_schema_for_game(profile_name: str) -> Optional[TPCanonicalSchema]:
    """Get canonical schema for a game profile.
    
    Returns None if game is unsupported.
    """
    category = get_game_category(profile_name)
    if category is None:
        return None
    return SCHEMA_REGISTRY.get(category)


# -----------------------------------------------------------------------------
# Canonical Mapping Builder
# -----------------------------------------------------------------------------

@dataclass
class TPBinding:
    """A single TeknoParrot input binding."""
    tp_name: str                    # TP XML element name
    input_type: TPInputType         # Type of input
    panel_control: Optional[str]    # Mapped panel control (e.g., "p1.button1")
    raw_value: Optional[str]        # Raw TP binding value (e.g., "DirectInput/0/Button 1")
    axis_range: Optional[Tuple[int, int]] = None


@dataclass
class TPCanonicalMapping:
    """Canonical mapping for a TeknoParrot game."""
    emulator: str = "teknoparrot"
    game: str = ""
    profile: str = ""
    category: TPGameCategory = TPGameCategory.GENERIC
    controls: Dict[str, TPBinding] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for API responses."""
        return {
            "emulator": self.emulator,
            "game": self.game,
            "profile": self.profile,
            "category": self.category.value,
            "controls": {
                name: {
                    "tp_name": binding.tp_name,
                    "input_type": binding.input_type.value,
                    "panel_control": binding.panel_control,
                    "raw_value": binding.raw_value,
                    "axis_range": list(binding.axis_range) if binding.axis_range else None,
                }
                for name, binding in self.controls.items()
            },
            "metadata": self.metadata,
        }


def build_canonical_mapping(
    profile_name: str,
    panel_mappings: Dict[str, Any],
    player: int = 1,
    input_mode: TPInputMode = TPInputMode.XINPUT,
) -> Optional[TPCanonicalMapping]:
    """Build canonical mapping for a TeknoParrot game profile.
    
    Args:
        profile_name: TP profile name (e.g., "InitialD8.xml")
        panel_mappings: Current arcade panel mappings from controls.json
        player: Player number (1-4)
        input_mode: Input device mode (XInput or DirectInput)
    
    Returns:
        TPCanonicalMapping or None if game is unsupported
    """
    schema = get_schema_for_game(profile_name)
    if schema is None:
        logger.warning(f"No canonical schema for TeknoParrot game: {profile_name}")
        return None
    
    prefix = f"p{player}."
    mapping_controls: Dict[str, TPBinding] = {}
    
    for control_name, ctrl_def in schema.controls.items():
        # Determine panel control to map
        panel_control = ctrl_def.default_binding
        if panel_control and not panel_control.startswith(prefix):
            # Adjust to correct player
            panel_control = prefix + panel_control.split(".", 1)[-1] if "." in panel_control else None
        
        # Get raw binding value based on input mode
        raw_value = None
        if panel_control:
            if input_mode == TPInputMode.XINPUT:
                # Use XInput format for PactoTech and other XInput controllers
                if panel_control in XINPUT_BUTTON_MAP:
                    raw_value = XINPUT_BUTTON_MAP[panel_control]
                elif panel_control in XINPUT_AXIS_MAP:
                    raw_value = XINPUT_AXIS_MAP[panel_control]
                else:
                    # Fallback: try to map by control name suffix
                    suffix = panel_control.split(".")[-1] if "." in panel_control else panel_control
                    controller_idx = player - 1
                    if suffix.startswith("button"):
                        button_num = int(suffix.replace("button", "")) if suffix.replace("button", "").isdigit() else 1
                        button_names = ["Button A", "Button B", "Button X", "Button Y", 
                                       "Left Shoulder", "Right Shoulder", "Left Trigger", "Right Trigger"]
                        if 1 <= button_num <= 8:
                            raw_value = f"XInput/{controller_idx}/{button_names[button_num - 1]}"
                    elif suffix in ["up", "down", "left", "right"]:
                        raw_value = f"XInput/{controller_idx}/DPad {suffix.capitalize()}"
                    elif suffix == "start":
                        raw_value = f"XInput/{controller_idx}/Start"
                    elif suffix == "coin":
                        raw_value = f"XInput/{controller_idx}/Back"
            else:
                # DirectInput mode (legacy)
                if panel_control in panel_mappings:
                    pin = panel_mappings[panel_control].get("pin")
                    if pin is not None:
                        raw_value = f"DirectInput/0/Button {pin}"
        
        mapping_controls[control_name] = TPBinding(
            tp_name=ctrl_def.tp_name,
            input_type=ctrl_def.input_type,
            panel_control=panel_control,
            raw_value=raw_value,
            axis_range=ctrl_def.axis_range,
        )
    
    return TPCanonicalMapping(
        emulator="teknoparrot",
        game=profile_name.replace(".xml", ""),
        profile=profile_name if profile_name.endswith(".xml") else f"{profile_name}.xml",
        category=schema.category,
        controls=mapping_controls,
        metadata={
            "player": player,
            "input_mode": input_mode.value,
            "schema_category": schema.category.value,
            "required_controls": schema.get_required_controls(),
            "optional_controls": schema.get_optional_controls(),
        },
    )


# -----------------------------------------------------------------------------
# XML Reading/Parsing
# -----------------------------------------------------------------------------

def read_tp_profile(profile_path: Path) -> Dict[str, Any]:
    """Read TeknoParrot UserProfile XML and extract current bindings.
    
    Returns dict of {tp_element_name: current_value}
    """
    if not profile_path.exists():
        return {}
    
    try:
        tree = ET.parse(profile_path)
        root = tree.getroot()
        
        bindings: Dict[str, Any] = {}
        
        # Extract all Input* elements
        for elem in root:
            if elem.tag.startswith("Input") or elem.tag.startswith("Joystick"):
                bindings[elem.tag] = {
                    "text": elem.text.strip() if elem.text else "",
                    "attribs": dict(elem.attrib),
                }
        
        return bindings
    
    except ET.ParseError as e:
        logger.error(f"Failed to parse TP profile {profile_path}: {e}")
        return {}


# -----------------------------------------------------------------------------
# Diff Generation
# -----------------------------------------------------------------------------

@dataclass
class TPBindingDiff:
    """Difference between current and canonical binding."""
    control_name: str
    tp_name: str
    current_value: Optional[str]
    proposed_value: Optional[str]
    changed: bool


@dataclass
class TPPreviewResult:
    """Result of previewing TP config changes."""
    profile: str
    profile_path: str
    has_changes: bool
    changes_count: int
    diffs: List[TPBindingDiff]
    file_exists: bool
    category: str
    summary: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.profile,
            "profile_path": self.profile_path,
            "has_changes": self.has_changes,
            "changes_count": self.changes_count,
            "file_exists": self.file_exists,
            "category": self.category,
            "summary": self.summary,
            "diffs": [
                {
                    "control_name": d.control_name,
                    "tp_name": d.tp_name,
                    "current": d.current_value,
                    "proposed": d.proposed_value,
                    "changed": d.changed,
                }
                for d in self.diffs
            ],
        }


def preview_tp_config(
    profile_path: Path,
    canonical: TPCanonicalMapping,
) -> TPPreviewResult:
    """Preview changes between current TP profile and canonical mapping.
    
    Does NOT write any files.
    """
    current_bindings = read_tp_profile(profile_path)
    diffs: List[TPBindingDiff] = []
    changes_count = 0
    
    for control_name, binding in canonical.controls.items():
        current_raw = current_bindings.get(binding.tp_name, {})
        current_value = current_raw.get("text") if isinstance(current_raw, dict) else None
        proposed_value = binding.raw_value
        
        changed = current_value != proposed_value and proposed_value is not None
        if changed:
            changes_count += 1
        
        diffs.append(TPBindingDiff(
            control_name=control_name,
            tp_name=binding.tp_name,
            current_value=current_value,
            proposed_value=proposed_value,
            changed=changed,
        ))
    
    # Build summary
    changed_controls = [d.control_name for d in diffs if d.changed]
    if changed_controls:
        summary = f"Changes needed: {', '.join(changed_controls[:5])}"
        if len(changed_controls) > 5:
            summary += f" (+{len(changed_controls) - 5} more)"
    else:
        summary = "No changes needed - bindings match canonical mapping"
    
    return TPPreviewResult(
        profile=canonical.profile,
        profile_path=str(profile_path),
        has_changes=changes_count > 0,
        changes_count=changes_count,
        diffs=diffs,
        file_exists=profile_path.exists(),
        category=canonical.category.value,
        summary=summary,
    )


# -----------------------------------------------------------------------------
# Apply/Write Functions
# -----------------------------------------------------------------------------

@dataclass
class TPApplyResult:
    """Result of applying TeknoParrot config changes."""
    success: bool
    profile: str
    profile_path: str
    backup_path: Optional[str]
    changes_applied: int
    changes_detail: List[Dict[str, Any]]
    log_entry: Optional[str]
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "profile": self.profile,
            "profile_path": self.profile_path,
            "backup_path": self.backup_path,
            "changes_applied": self.changes_applied,
            "changes_detail": self.changes_detail,
            "log_entry": self.log_entry,
            "error": self.error,
        }


def _create_backup(profile_path: Path, drive_root: Path) -> Optional[Path]:
    """Create a timestamped backup of the TP profile XML.
    
    Returns the backup path if successful, None otherwise.
    """
    import shutil
    from datetime import datetime
    
    if not profile_path.exists():
        return None
    
    # Create backup directory under drive_root/.aa/backups/teknoparrot/
    backup_dir = drive_root / ".aa" / "backups" / "teknoparrot"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Timestamp-based backup filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{profile_path.stem}_{timestamp}{profile_path.suffix}"
    backup_path = backup_dir / backup_name
    
    try:
        shutil.copy2(profile_path, backup_path)
        logger.info(f"Created TeknoParrot backup: {backup_path}")
        return backup_path
    except (OSError, shutil.Error) as e:
        logger.error(f"Failed to create backup: {e}")
        return None


def _log_tp_change(
    drive_root: Path,
    profile: str,
    profile_path: str,
    backup_path: Optional[str],
    changes_detail: List[Dict[str, Any]],
) -> Optional[str]:
    """Append a JSONL log entry describing the TeknoParrot config changes.
    
    Returns the log entry ID if successful.
    """
    import json
    import uuid
    from datetime import datetime
    
    log_file = drive_root / ".aa" / "logs" / "changes.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    log_id = str(uuid.uuid4())[:8]
    entry = {
        "id": log_id,
        "timestamp": datetime.now().isoformat(),
        "scope": "emulator",
        "panel": "teknoparrot",
        "action": "apply_config",
        "profile": profile,
        "profile_path": profile_path,
        "backup_path": backup_path,
        "changes_count": len(changes_detail),
        "changes": changes_detail,
    }
    
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        logger.info(f"Logged TeknoParrot config change: {log_id}")
        return log_id
    except OSError as e:
        logger.error(f"Failed to log change: {e}")
        return None


def _update_xml_bindings(
    profile_path: Path,
    canonical: TPCanonicalMapping,
    preview: TPPreviewResult,
) -> Tuple[bool, List[Dict[str, Any]], Optional[str]]:
    """Update TeknoParrot XML with new bindings.
    
    Only modifies elements that have actual changes according to preview.
    
    Returns:
        (success, changes_detail, error_message)
    """
    changes_detail: List[Dict[str, Any]] = []
    
    if not preview.has_changes:
        return True, [], None
    
    try:
        tree = ET.parse(profile_path)
        root = tree.getroot()
        
        for diff in preview.diffs:
            if not diff.changed or diff.proposed_value is None:
                continue
            
            # Find or create the element
            elem = root.find(diff.tp_name)
            if elem is None:
                # Create new element if it doesn't exist
                elem = ET.SubElement(root, diff.tp_name)
                logger.debug(f"Created new element: {diff.tp_name}")
            
            # Record the change
            old_value = elem.text.strip() if elem.text else ""
            changes_detail.append({
                "control": diff.control_name,
                "tp_name": diff.tp_name,
                "before": old_value,
                "after": diff.proposed_value,
            })
            
            # Update the element
            elem.text = diff.proposed_value
        
        # Write the updated XML
        tree.write(profile_path, encoding="utf-8", xml_declaration=True)
        logger.info(f"Updated TeknoParrot profile: {profile_path} ({len(changes_detail)} changes)")
        return True, changes_detail, None
    
    except ET.ParseError as e:
        error_msg = f"XML parse error: {e}"
        logger.error(error_msg)
        return False, [], error_msg
    except OSError as e:
        error_msg = f"File write error: {e}"
        logger.error(error_msg)
        return False, [], error_msg


def apply_tp_config(
    profile_path: Path,
    canonical: TPCanonicalMapping,
    drive_root: Path,
    backup: bool = True,
) -> TPApplyResult:
    """Apply TeknoParrot config changes from canonical mapping.
    
    This is the main entry point for writing TP configs.
    
    Safety flow:
    1. Preview changes (diff against current)
    2. Create backup (if backup=True)
    3. Modify only changed bindings in XML
    4. Log to changes.jsonl with before/after values
    
    Args:
        profile_path: Path to the TeknoParrot UserProfile XML
        canonical: Canonical mapping from Chuck
        drive_root: Drive root for backups and logs
        backup: Whether to create a backup before writing
    
    Returns:
        TPApplyResult with success status and details
    """
    profile_name = canonical.profile
    
    # Step 1: Check if profile exists
    if not profile_path.exists():
        return TPApplyResult(
            success=False,
            profile=profile_name,
            profile_path=str(profile_path),
            backup_path=None,
            changes_applied=0,
            changes_detail=[],
            log_entry=None,
            error=f"TeknoParrot profile not found: {profile_path}",
        )
    
    # Step 2: Preview changes
    preview = preview_tp_config(profile_path, canonical)
    
    if not preview.has_changes:
        return TPApplyResult(
            success=True,
            profile=profile_name,
            profile_path=str(profile_path),
            backup_path=None,
            changes_applied=0,
            changes_detail=[],
            log_entry=None,
            error=None,
        )
    
    # Step 3: Create backup
    backup_path: Optional[Path] = None
    if backup:
        backup_path = _create_backup(profile_path, drive_root)
        if backup_path is None:
            return TPApplyResult(
                success=False,
                profile=profile_name,
                profile_path=str(profile_path),
                backup_path=None,
                changes_applied=0,
                changes_detail=[],
                log_entry=None,
                error="Failed to create backup - aborting to prevent data loss",
            )
    
    # Step 4: Apply changes
    success, changes_detail, error = _update_xml_bindings(profile_path, canonical, preview)
    
    if not success:
        return TPApplyResult(
            success=False,
            profile=profile_name,
            profile_path=str(profile_path),
            backup_path=str(backup_path) if backup_path else None,
            changes_applied=0,
            changes_detail=[],
            log_entry=None,
            error=error,
        )
    
    # Step 5: Log the changes
    log_id = _log_tp_change(
        drive_root,
        profile_name,
        str(profile_path),
        str(backup_path) if backup_path else None,
        changes_detail,
    )
    
    return TPApplyResult(
        success=True,
        profile=profile_name,
        profile_path=str(profile_path),
        backup_path=str(backup_path) if backup_path else None,
        changes_applied=len(changes_detail),
        changes_detail=changes_detail,
        log_entry=log_id,
        error=None,
    )


# -----------------------------------------------------------------------------
# Utility: Create Sample Profile for Testing
# -----------------------------------------------------------------------------

def create_sample_profile(
    profile_path: Path,
    profile_name: str = "InitialD8",
    category: TPGameCategory = TPGameCategory.RACING,
) -> bool:
    """Create a sample TeknoParrot UserProfile XML for testing.
    
    This creates a minimal valid XML that can be used to test the apply flow
    when no actual TP installation exists.
    """
    schema = SCHEMA_REGISTRY.get(category)
    if not schema:
        return False
    
    root = ET.Element("GameProfile")
    
    # Add game metadata
    ET.SubElement(root, "GameName").text = profile_name
    ET.SubElement(root, "GameNameInternal").text = profile_name
    ET.SubElement(root, "GameGenre").text = category.value.capitalize()
    ET.SubElement(root, "InputAPI").text = "DirectInput"
    
    # Add empty input elements from schema
    for control_name, ctrl_def in schema.controls.items():
        elem = ET.SubElement(root, ctrl_def.tp_name)
        elem.text = ""  # Empty binding
    
    # Create parent directory if needed
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        tree = ET.ElementTree(root)
        tree.write(profile_path, encoding="utf-8", xml_declaration=True)
        logger.info(f"Created sample TeknoParrot profile: {profile_path}")
        return True
    except OSError as e:
        logger.error(f"Failed to create sample profile: {e}")
        return False


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def get_supported_games() -> List[Dict[str, str]]:
    """Return list of supported TeknoParrot games with categories."""
    return [
        {"profile": name, "category": cat.value}
        for name, cat in sorted(KNOWN_GAMES.items())
    ]


def get_schema(category: str) -> Optional[Dict[str, Any]]:
    """Get schema definition for a category."""
    try:
        cat = TPGameCategory(category)
        schema = SCHEMA_REGISTRY.get(cat)
        if schema:
            return {
                "category": schema.category.value,
                "description": schema.description,
                "controls": {
                    name: {
                        "tp_name": ctrl.tp_name,
                        "input_type": ctrl.input_type.value,
                        "description": ctrl.description,
                        "required": ctrl.required,
                        "default_binding": ctrl.default_binding,
                    }
                    for name, ctrl in schema.controls.items()
                },
                "required_controls": schema.get_required_controls(),
                "optional_controls": schema.get_optional_controls(),
            }
    except ValueError:
        pass
    return None


def is_game_supported(profile_name: str) -> bool:
    """Check if a game profile is supported."""
    return get_game_category(profile_name) is not None

