"""Per-Game MAME Configuration Generator

Generates game-specific MAME cfg files with clean bindings optimized for
specific genres (fighting, racing, shooter, etc.).

This allows Chuck to fix game-specific issues like:
- Fighting games with special move problems (removes OR fallbacks)
- Racing games needing analog steering
- Games needing custom button layouts
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.dom import minidom
import logging

logger = logging.getLogger(__name__)


# Genre definitions with button layouts
GENRE_TEMPLATES = {
    "fighting": {
        "description": "6-button fighting game (Street Fighter, MvC, etc.)",
        "buttons": {
            "p1.button1": "LP",  # Light Punch
            "p1.button2": "MP",  # Medium Punch
            "p1.button3": "HP",  # Hard Punch
            "p1.button4": "LK",  # Light Kick
            "p1.button5": "MK",  # Medium Kick
            "p1.button6": "HK",  # Hard Kick
        },
        "use_clean_bindings": True,  # No ORs
    },
    "fighting_4button": {
        "description": "4-button fighting game (Mortal Kombat, etc.)",
        "buttons": {
            "p1.button1": "HP",
            "p1.button2": "LP", 
            "p1.button3": "HK",
            "p1.button4": "LK",
            "p1.button5": "Block",
            "p1.button6": "Run",
        },
        "use_clean_bindings": True,
    },
    "shooter": {
        "description": "Shooter game (1-3 buttons)",
        "buttons": {
            "p1.button1": "Fire",
            "p1.button2": "Bomb",
            "p1.button3": "Special",
        },
        "use_clean_bindings": True,
    },
    "racing": {
        "description": "Racing game (gas, brake, steering)",
        "buttons": {
            "p1.button1": "Gas",
            "p1.button2": "Brake",
            "p1.button3": "Shift Up",
            "p1.button4": "Shift Down",
        },
        "use_analog": True,
    },
    "default": {
        "description": "Standard 8-button layout",
        "buttons": {
            "p1.button1": "Button 1",
            "p1.button2": "Button 2",
            "p1.button3": "Button 3",
            "p1.button4": "Button 4",
            "p1.button5": "Button 5",
            "p1.button6": "Button 6",
            "p1.button7": "Button 7",
            "p1.button8": "Button 8",
        },
        "use_clean_bindings": False,  # Allow ORs
    },
}


# =============================================================================
# AUTHENTIC ARCADE PANEL LAYOUTS
# =============================================================================
# Maps game control inputs to physical panel buttons
# Key = game's internal button (1-based), Value = panel button to use (1-8)
# 
# Example: Tekken uses buttons 1,2,4,5 (LP, RP, LK, RK) laid out as:
#   [1][2]     <- Punches (top row)
#   [4][5]     <- Kicks (bottom row)
#
# On a standard 8-button panel:
#   [1][2][3][4]  <- Top row (buttons 1-4)
#   [5][6][7][8]  <- Bottom row (buttons 5-8)
#
# So Tekken maps: Game BTN1->Panel 1, Game BTN2->Panel 2, 
#                 Game BTN3->Panel 5, Game BTN4->Panel 6
# =============================================================================

ARCADE_PANEL_LAYOUTS = {
    # Tekken series - 4 buttons: LP, RP (top), LK, RK (bottom)
    # Original cabinet: Square layout, punches on top, kicks on bottom
    # Tekken 1 & 2: Row 1 = 1,2 | Row 2 = 4,5
    "tekken": {
        "description": "Tekken (1,2,4,5 - square layout)",
        "button_map": {1: 1, 2: 2, 3: 4, 4: 5},  # Game BTN -> Panel BTN
        "button_count": 4,
    },
    "tekken2": {
        "description": "Tekken 2 (1,2,4,5 - square layout)",
        "button_map": {1: 1, 2: 2, 3: 4, 4: 5},
        "button_count": 4,
    },
    # Tekken 3+ may use different layout
    "tekken3": {
        "description": "Tekken 3 (1,2,4,5 - square layout)",
        "button_map": {1: 1, 2: 2, 3: 4, 4: 5},
        "button_count": 4,
    },
    
    # Street Fighter series - 6 buttons in 2x3 layout
    # LP MP HP (top row = panel 1,2,3)
    # LK MK HK (bottom row = panel 4,5,6)
    "sf2": {
        "description": "Street Fighter 2 (1,2,3,4,5,6 - 6-button)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
        "button_count": 6,
    },
    "sf2ce": {
        "description": "SF2 Champion Edition (1,2,3,4,5,6)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
        "button_count": 6,
    },
    "sf2hf": {
        "description": "SF2 Hyper Fighting (1,2,3,4,5,6)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
        "button_count": 6,
    },
    "ssf2": {
        "description": "Super SF2 (1,2,3,4,5,6)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
        "button_count": 6,
    },
    "ssf2t": {
        "description": "Super SF2 Turbo (1,2,3,4,5,6)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
        "button_count": 6,
    },
    "sfa": {
        "description": "Street Fighter Alpha (1,2,3,4,5,6)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
        "button_count": 6,
    },
    "sfa2": {
        "description": "Street Fighter Alpha 2 (1,2,3,4,5,6)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
        "button_count": 6,
    },
    "sfa3": {
        "description": "Street Fighter Alpha 3 (1,2,3,4,5,6)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
        "button_count": 6,
    },
    
    # Marvel vs Capcom series - 6 buttons
    "msh": {
        "description": "Marvel Super Heroes (1,2,3,4,5,6)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
        "button_count": 6,
    },
    "mshvsf": {
        "description": "Marvel vs SF (1,2,3,4,5,6)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
        "button_count": 6,
    },
    "mvsc": {
        "description": "Marvel vs Capcom (1,2,3,4,5,6)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
        "button_count": 6,
    },
    "xmvsf": {
        "description": "X-Men vs SF (1,2,3,4,5,6)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
        "button_count": 6,
    },
    "xmcota": {
        "description": "X-Men Children of the Atom (1,2,3,4,5,6)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
        "button_count": 6,
    },
    
    # SNK Neo-Geo - 4 buttons (A, B, C, D) in straight line
    "kof94": {
        "description": "KoF 94 (1,2,3,4 - Neo-Geo 4-button)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4},
        "button_count": 4,
    },
    "kof98": {
        "description": "KoF 98 (1,2,3,4 - Neo-Geo 4-button)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4},
        "button_count": 4,
    },
    "garou": {
        "description": "Garou: Mark of the Wolves (1,2,3,4)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4},
        "button_count": 4,
    },
    "samsho2": {
        "description": "Samurai Shodown 2 (1,2,3,4)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4},
        "button_count": 4,
    },
    
    # Mortal Kombat - 5 buttons (HP, LP, BL, HK, LK) + Run in later games
    "mk": {
        "description": "Mortal Kombat (1,2,3,5,6 - Block in middle)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 5, 5: 6},
        "button_count": 5,
    },
    "mk2": {
        "description": "Mortal Kombat 2 (1,2,3,5,6)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 5, 5: 6},
        "button_count": 5,
    },
    "umk3": {
        "description": "Ultimate MK3 (1,2,3,4,5,6 - with Run)",
        "button_map": {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
        "button_count": 6,
    },
    
    # Virtua Fighter - 3 buttons (Punch, Kick, Guard)
    "vf": {
        "description": "Virtua Fighter (1,2,3)",
        "button_map": {1: 1, 2: 2, 3: 3},
        "button_count": 3,
    },
    "vf2": {
        "description": "Virtua Fighter 2 (1,2,3)",
        "button_map": {1: 1, 2: 2, 3: 3},
        "button_count": 3,
    },
    
    # Dead or Alive - 3 buttons (Punch, Kick, Hold/Guard)
    "doa": {
        "description": "Dead or Alive (1,2,3)",
        "button_map": {1: 1, 2: 2, 3: 3},
        "button_count": 3,
    },
}


# Known fighting game ROMs with their genre (for games not in ARCADE_PANEL_LAYOUTS)
FIGHTING_GAME_ROMS = {
    # Street Fighter series (use layouts above)
    "sf2": "fighting",
    "sf2ce": "fighting",
    "sf2hf": "fighting",
    "ssf2": "fighting",
    "ssf2t": "fighting",
    "sfa": "fighting",
    "sfa2": "fighting",
    "sfa3": "fighting",
    "sf3": "fighting",
    "sf3ng": "fighting",
    "sf33rd": "fighting",
    
    # Marvel vs Capcom series
    "msh": "fighting",
    "mshvsf": "fighting",
    "mvsc": "fighting",
    "xmvsf": "fighting",
    "xmcota": "fighting",
    
    # SNK fighting games
    "kof94": "fighting",
    "kof95": "fighting",
    "kof96": "fighting",
    "kof97": "fighting",
    "kof98": "fighting",
    "kof99": "fighting",
    "kof2000": "fighting",
    "kof2001": "fighting",
    "kof2002": "fighting",
    "fatfury1": "fighting",
    "fatfury2": "fighting",
    "fatfury3": "fighting",
    "garou": "fighting",
    "samsho": "fighting",
    "samsho2": "fighting",
    "samsho3": "fighting",
    "samsho4": "fighting",
    "samsho5": "fighting",
    
    # Mortal Kombat (4-button)
    "mk": "fighting_4button",
    "mk2": "fighting_4button",
    "mk3": "fighting_4button",
    "umk3": "fighting_4button",
    "mk4": "fighting_4button",
    
    # Tekken series
    "tekken": "fighting",
    "tekken2": "fighting",
    "tekken3": "fighting",
    "tekken4": "fighting",
    "tekken5": "fighting",
    
    # Other fighters
    "doa": "fighting",
    "doa2": "fighting",
    "vf": "fighting",
    "vf2": "fighting",
    "vf3": "fighting",
    "vf4": "fighting",
    "ggx": "fighting",
    "ggxx": "fighting",
}


# XInput to MAME JOYCODE mapping (clean, no ORs)
XINPUT_CLEAN_MAP = {
    # Player 1
    "p1.up": "JOYCODE_1_YAXIS_UP_SWITCH",
    "p1.down": "JOYCODE_1_YAXIS_DOWN_SWITCH",
    "p1.left": "JOYCODE_1_XAXIS_LEFT_SWITCH",
    "p1.right": "JOYCODE_1_XAXIS_RIGHT_SWITCH",
    "p1.button1": "JOYCODE_1_BUTTON1",
    "p1.button2": "JOYCODE_1_BUTTON2",
    "p1.button3": "JOYCODE_1_BUTTON3",
    "p1.button4": "JOYCODE_1_BUTTON4",
    "p1.button5": "JOYCODE_1_BUTTON5",
    "p1.button6": "JOYCODE_1_BUTTON6",
    "p1.button7": "JOYCODE_1_BUTTON7",
    "p1.button8": "JOYCODE_1_BUTTON8",
    "p1.start": "JOYCODE_1_START",
    "p1.coin": "JOYCODE_1_SELECT",
    
    # Player 2
    "p2.up": "JOYCODE_2_YAXIS_UP_SWITCH",
    "p2.down": "JOYCODE_2_YAXIS_DOWN_SWITCH",
    "p2.left": "JOYCODE_2_XAXIS_LEFT_SWITCH",
    "p2.right": "JOYCODE_2_XAXIS_RIGHT_SWITCH",
    "p2.button1": "JOYCODE_2_BUTTON1",
    "p2.button2": "JOYCODE_2_BUTTON2",
    "p2.button3": "JOYCODE_2_BUTTON3",
    "p2.button4": "JOYCODE_2_BUTTON4",
    "p2.button5": "JOYCODE_2_BUTTON5",
    "p2.button6": "JOYCODE_2_BUTTON6",
    "p2.button7": "JOYCODE_2_BUTTON7",
    "p2.button8": "JOYCODE_2_BUTTON8",
    "p2.start": "JOYCODE_2_START",
    "p2.coin": "JOYCODE_2_SELECT",
}


def get_genre_for_rom(rom_name: str) -> str:
    """Look up genre for a ROM name.
    
    Args:
        rom_name: The MAME ROM name (e.g., 'mshvsf', 'sf2ce')
        
    Returns:
        Genre string (e.g., 'fighting', 'default')
    """
    # Normalize ROM name
    rom_lower = rom_name.lower().replace(".zip", "").replace(".7z", "")
    
    if rom_lower in FIGHTING_GAME_ROMS:
        return FIGHTING_GAME_ROMS[rom_lower]
    
    # TODO: Add more genre lookups (shooters, racing, etc.)
    
    return "default"


def generate_pergame_config(
    rom_name: str,
    genre: Optional[str] = None,
    include_ui_controls: bool = True,
    players: int = 2,
) -> str:
    """Generate per-game MAME cfg with clean bindings.
    
    Args:
        rom_name: The MAME ROM name
        genre: Genre override (auto-detected if None)
        include_ui_controls: Whether to include ESC and menu controls
        players: Number of players to configure (1-4)
        
    Returns:
        Formatted XML string for the per-game cfg
    """
    # Auto-detect genre if not specified
    if genre is None:
        genre = get_genre_for_rom(rom_name)
    
    template = GENRE_TEMPLATES.get(genre, GENRE_TEMPLATES["default"])
    use_clean = template.get("use_clean_bindings", False)
    
    logger.info(f"Generating per-game config for {rom_name} (genre: {genre})")
    
    # Create root mameconfig element
    root = ET.Element("mameconfig", version="10")
    
    # Add system element for this specific game
    system = ET.SubElement(root, "system", name=rom_name)
    
    # Add input section
    input_elem = ET.SubElement(system, "input")
    
    # Add UI controls first (ESC to exit, etc.)
    if include_ui_controls:
        _add_ui_controls(input_elem)
    
    # Add player controls for each player
    for player in range(1, players + 1):
        _add_player_controls(input_elem, player, genre, use_clean, rom_name=rom_name)
    
    # Convert to pretty-printed XML string
    xml_string = minidom.parseString(
        ET.tostring(root, encoding='unicode')
    ).toprettyxml(indent="  ")
    
    # Remove extra blank lines
    xml_lines = [line for line in xml_string.split('\n') if line.strip()]
    formatted_xml = '\n'.join(xml_lines)
    
    return formatted_xml


def _add_ui_controls(input_elem: ET.Element) -> None:
    """Add UI/system controls to the config."""
    ui_mappings = [
        ("UI_CANCEL", "KEYCODE_ESC"),
        ("UI_UP", "KEYCODE_UP"),
        ("UI_DOWN", "KEYCODE_DOWN"),
        ("UI_LEFT", "KEYCODE_LEFT"),
        ("UI_RIGHT", "KEYCODE_RIGHT"),
        ("UI_SELECT", "KEYCODE_ENTER"),
        ("UI_PAUSE", "KEYCODE_P"),
    ]
    
    for ui_type, keycode in ui_mappings:
        port = ET.SubElement(input_elem, "port", type=ui_type)
        newseq = ET.SubElement(port, "newseq", type="standard")
        newseq.text = keycode


def _add_player_controls(
    input_elem: ET.Element, 
    player: int, 
    genre: str,
    use_clean: bool,
    rom_name: str = None
) -> None:
    """Add controls for a specific player.
    
    Uses ARCADE_PANEL_LAYOUTS if available for authentic button mapping,
    otherwise falls back to genre template.
    """
    prefix = f"p{player}."
    
    # Joystick directions (same for all games)
    directions = [
        (f"P{player}_JOYSTICK_UP", f"{prefix}up"),
        (f"P{player}_JOYSTICK_DOWN", f"{prefix}down"),
        (f"P{player}_JOYSTICK_LEFT", f"{prefix}left"),
        (f"P{player}_JOYSTICK_RIGHT", f"{prefix}right"),
    ]
    
    for mame_type, control_key in directions:
        joycode = XINPUT_CLEAN_MAP.get(control_key)
        if joycode:
            port = ET.SubElement(input_elem, "port", type=mame_type)
            newseq = ET.SubElement(port, "newseq", type="standard")
            newseq.text = joycode
    
    # Check for authentic arcade panel layout
    layout = ARCADE_PANEL_LAYOUTS.get(rom_name) if rom_name else None
    
    if layout:
        # Use authentic arcade panel button mapping
        button_map = layout.get("button_map", {})
        for game_btn, panel_btn in button_map.items():
            # game_btn = game's internal button (1-6)
            # panel_btn = physical panel button to use (1-8)
            control_key = f"{prefix}button{panel_btn}"  # Use panel button
            joycode = XINPUT_CLEAN_MAP.get(control_key)
            if joycode:
                # MAME expects P1_BUTTON1, P1_BUTTON2, etc. for game buttons
                port = ET.SubElement(input_elem, "port", type=f"P{player}_BUTTON{game_btn}")
                newseq = ET.SubElement(port, "newseq", type="standard")
                newseq.text = joycode
                logger.debug(f"  Game BTN{game_btn} → Panel BTN{panel_btn} → {joycode}")
    else:
        # Fallback: use genre template (buttons 1-N sequentially)
        template = GENRE_TEMPLATES.get(genre, GENRE_TEMPLATES["default"])
        button_count = len([k for k in template["buttons"].keys() if "button" in k])
        
        for btn_num in range(1, button_count + 1):
            control_key = f"{prefix}button{btn_num}"
            joycode = XINPUT_CLEAN_MAP.get(control_key)
            if joycode:
                port = ET.SubElement(input_elem, "port", type=f"P{player}_BUTTON{btn_num}")
                newseq = ET.SubElement(port, "newseq", type="standard")
                newseq.text = joycode
    
    # Start and Coin
    for special, mame_type in [("start", "START"), ("coin", "COIN1")]:
        control_key = f"{prefix}{special}"
        joycode = XINPUT_CLEAN_MAP.get(control_key)
        if joycode:
            # Coin uses COIN1/COIN2 format, Start uses P1_START format
            port_type = f"COIN{player}" if special == "coin" else f"P{player}_{mame_type}"
            port = ET.SubElement(input_elem, "port", type=port_type)
            newseq = ET.SubElement(port, "newseq", type="standard")
            newseq.text = joycode


def save_pergame_config(
    rom_name: str,
    cfg_dir: Path,
    genre: Optional[str] = None,
    backup: bool = True,
) -> Path:
    """Generate and save per-game config to disk.
    
    Args:
        rom_name: The MAME ROM name
        cfg_dir: Path to MAME's cfg directory
        genre: Genre override (auto-detected if None)
        backup: Whether to backup existing config
        
    Returns:
        Path to the saved config file
    """
    config_content = generate_pergame_config(rom_name, genre)
    
    cfg_path = cfg_dir / f"{rom_name}.cfg"
    
    # Create backup if file exists
    if backup and cfg_path.exists():
        backup_path = cfg_path.with_suffix(".cfg.bak")
        cfg_path.rename(backup_path)
        logger.info(f"Backed up existing config to {backup_path}")
    
    # Write new config
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(config_content, encoding="utf-8")
    logger.info(f"Saved per-game config to {cfg_path}")
    
    return cfg_path


def get_supported_fighting_games() -> List[Dict[str, str]]:
    """Return list of known fighting game ROMs with their genres."""
    games = []
    for rom, genre in FIGHTING_GAME_ROMS.items():
        games.append({
            "rom": rom,
            "genre": genre,
            "description": GENRE_TEMPLATES.get(genre, {}).get("description", "Unknown"),
        })
    return games
