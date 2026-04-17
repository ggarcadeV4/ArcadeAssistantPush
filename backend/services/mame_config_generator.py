"""MAME Configuration Generator

Generates MAME default.cfg XML from Controller Chuck's Mapping Dictionary.
Supports 4-player arcade configurations with proper MAME port/control mappings.
"""

from typing import Dict, Any, Optional, List
import xml.etree.ElementTree as ET
from xml.dom import minidom
import logging

from backend.constants.drive_root import get_drive_root

logger = logging.getLogger(__name__)

# MAME port mapping for arcade controls
# Maps our control keys to MAME's port/control identifiers
# Supports BOTH formats: "p1.up" (from controls.json) and "p1.joystick_up" (legacy)
MAME_PORT_MAPPINGS = {
    # Player 1 controls - both short and long format for directions
    "p1.up": {"port": "P1", "type": "JOYSTICK_UP", "mask": "0x01"},
    "p1.joystick_up": {"port": "P1", "type": "JOYSTICK_UP", "mask": "0x01"},
    "p1.down": {"port": "P1", "type": "JOYSTICK_DOWN", "mask": "0x02"},
    "p1.joystick_down": {"port": "P1", "type": "JOYSTICK_DOWN", "mask": "0x02"},
    "p1.left": {"port": "P1", "type": "JOYSTICK_LEFT", "mask": "0x04"},
    "p1.joystick_left": {"port": "P1", "type": "JOYSTICK_LEFT", "mask": "0x04"},
    "p1.right": {"port": "P1", "type": "JOYSTICK_RIGHT", "mask": "0x08"},
    "p1.joystick_right": {"port": "P1", "type": "JOYSTICK_RIGHT", "mask": "0x08"},
    "p1.button1": {"port": "P1", "type": "BUTTON1", "mask": "0x10"},
    "p1.button2": {"port": "P1", "type": "BUTTON2", "mask": "0x20"},
    "p1.button3": {"port": "P1", "type": "BUTTON3", "mask": "0x40"},
    "p1.button4": {"port": "P1", "type": "BUTTON4", "mask": "0x80"},
    "p1.button5": {"port": "P1", "type": "BUTTON5", "mask": "0x100"},
    "p1.button6": {"port": "P1", "type": "BUTTON6", "mask": "0x200"},
    "p1.button7": {"port": "P1", "type": "BUTTON7", "mask": "0x400"},
    "p1.button8": {"port": "P1", "type": "BUTTON8", "mask": "0x800"},
    "p1.start": {"port": "P1", "type": "START", "mask": "0x1000"},
    "p1.coin": {"port": "P1", "type": "COIN", "mask": "0x2000"},

    # Player 2 controls - both short and long format for directions
    "p2.up": {"port": "P2", "type": "JOYSTICK_UP", "mask": "0x01"},
    "p2.joystick_up": {"port": "P2", "type": "JOYSTICK_UP", "mask": "0x01"},
    "p2.down": {"port": "P2", "type": "JOYSTICK_DOWN", "mask": "0x02"},
    "p2.joystick_down": {"port": "P2", "type": "JOYSTICK_DOWN", "mask": "0x02"},
    "p2.left": {"port": "P2", "type": "JOYSTICK_LEFT", "mask": "0x04"},
    "p2.joystick_left": {"port": "P2", "type": "JOYSTICK_LEFT", "mask": "0x04"},
    "p2.right": {"port": "P2", "type": "JOYSTICK_RIGHT", "mask": "0x08"},
    "p2.joystick_right": {"port": "P2", "type": "JOYSTICK_RIGHT", "mask": "0x08"},
    "p2.button1": {"port": "P2", "type": "BUTTON1", "mask": "0x10"},
    "p2.button2": {"port": "P2", "type": "BUTTON2", "mask": "0x20"},
    "p2.button3": {"port": "P2", "type": "BUTTON3", "mask": "0x40"},
    "p2.button4": {"port": "P2", "type": "BUTTON4", "mask": "0x80"},
    "p2.button5": {"port": "P2", "type": "BUTTON5", "mask": "0x100"},
    "p2.button6": {"port": "P2", "type": "BUTTON6", "mask": "0x200"},
    "p2.button7": {"port": "P2", "type": "BUTTON7", "mask": "0x400"},
    "p2.button8": {"port": "P2", "type": "BUTTON8", "mask": "0x800"},
    "p2.start": {"port": "P2", "type": "START", "mask": "0x1000"},
    "p2.coin": {"port": "P2", "type": "COIN", "mask": "0x2000"},

    # Player 3 controls - both short and long format for directions
    "p3.up": {"port": "P3", "type": "JOYSTICK_UP", "mask": "0x01"},
    "p3.joystick_up": {"port": "P3", "type": "JOYSTICK_UP", "mask": "0x01"},
    "p3.down": {"port": "P3", "type": "JOYSTICK_DOWN", "mask": "0x02"},
    "p3.joystick_down": {"port": "P3", "type": "JOYSTICK_DOWN", "mask": "0x02"},
    "p3.left": {"port": "P3", "type": "JOYSTICK_LEFT", "mask": "0x04"},
    "p3.joystick_left": {"port": "P3", "type": "JOYSTICK_LEFT", "mask": "0x04"},
    "p3.right": {"port": "P3", "type": "JOYSTICK_RIGHT", "mask": "0x08"},
    "p3.joystick_right": {"port": "P3", "type": "JOYSTICK_RIGHT", "mask": "0x08"},
    "p3.button1": {"port": "P3", "type": "BUTTON1", "mask": "0x10"},
    "p3.button2": {"port": "P3", "type": "BUTTON2", "mask": "0x20"},
    "p3.button3": {"port": "P3", "type": "BUTTON3", "mask": "0x40"},
    "p3.button4": {"port": "P3", "type": "BUTTON4", "mask": "0x80"},
    "p3.start": {"port": "P3", "type": "START", "mask": "0x100"},
    "p3.coin": {"port": "P3", "type": "COIN", "mask": "0x200"},

    # Player 4 controls - both short and long format for directions
    "p4.up": {"port": "P4", "type": "JOYSTICK_UP", "mask": "0x01"},
    "p4.joystick_up": {"port": "P4", "type": "JOYSTICK_UP", "mask": "0x01"},
    "p4.down": {"port": "P4", "type": "JOYSTICK_DOWN", "mask": "0x02"},
    "p4.joystick_down": {"port": "P4", "type": "JOYSTICK_DOWN", "mask": "0x02"},
    "p4.left": {"port": "P4", "type": "JOYSTICK_LEFT", "mask": "0x04"},
    "p4.joystick_left": {"port": "P4", "type": "JOYSTICK_LEFT", "mask": "0x04"},
    "p4.right": {"port": "P4", "type": "JOYSTICK_RIGHT", "mask": "0x08"},
    "p4.joystick_right": {"port": "P4", "type": "JOYSTICK_RIGHT", "mask": "0x08"},
    "p4.button1": {"port": "P4", "type": "BUTTON1", "mask": "0x10"},
    "p4.button2": {"port": "P4", "type": "BUTTON2", "mask": "0x20"},
    "p4.button3": {"port": "P4", "type": "BUTTON3", "mask": "0x40"},
    "p4.button4": {"port": "P4", "type": "BUTTON4", "mask": "0x80"},
    "p4.start": {"port": "P4", "type": "START", "mask": "0x100"},
    "p4.coin": {"port": "P4", "type": "COIN", "mask": "0x200"},
}


class MAMEConfigError(Exception):
    """Raised when MAME config generation fails"""
    pass


# Keycode normalization map for common keys
_KEYCODE_NORMALIZE = {
    "arrowup": "UP",
    "arrowdown": "DOWN", 
    "arrowleft": "LEFT",
    "arrowright": "RIGHT",
    "enter": "ENTER",
    "escape": "ESC",
    "space": "SPACE",
    "backspace": "BACKSPACE",
    "tab": "TAB",
    "shift": "LSHIFT",
    "control": "LCONTROL",
    "alt": "LALT",
}


def _get_keycode_for_control(control_key: str, control_data: Dict[str, Any]) -> str:
    """Convert captured keycode to MAME KEYCODE format.
    
    Args:
        control_key: The control identifier (e.g., "p1.button1")
        control_data: The control's data from controls.json with keycode field
        
    Returns:
        MAME keycode string (e.g., "KEYCODE_F1", "KEYCODE_A")
    """
    # Try to get captured keycode
    raw_keycode = control_data.get("keycode", "")
    
    if not raw_keycode:
        logger.warning(f"No keycode captured for {control_key}, using default")
        # Fallback to a sensible default based on control type
        return _default_keycode_for_control(control_key)
    
    # Normalize the keycode
    # Remove KEY_ prefix if present
    kc = raw_keycode.replace("KEY_", "").upper()
    
    # Handle special key names
    kc_lower = kc.lower()
    if kc_lower in _KEYCODE_NORMALIZE:
        kc = _KEYCODE_NORMALIZE[kc_lower]
    
    # Single letter keys
    if len(kc) == 1 and kc.isalpha():
        return f"KEYCODE_{kc}"
    
    # Number keys
    if len(kc) == 1 and kc.isdigit():
        return f"KEYCODE_{kc}"
    
    # Function keys (F1-F12)
    if kc.startswith("F") and kc[1:].isdigit():
        return f"KEYCODE_{kc}"
    
    return f"KEYCODE_{kc}"


def _default_keycode_for_control(control_key: str) -> str:
    """Return a sensible default KEYCODE when no keycode was captured.
    
    These defaults match common I-PAC keyboard layouts.
    """
    # Common I-PAC default key assignments
    IPAC_DEFAULTS = {
        "p1.up": "KEYCODE_UP",
        "p1.down": "KEYCODE_DOWN",
        "p1.left": "KEYCODE_LEFT",
        "p1.right": "KEYCODE_RIGHT",
        "p1.button1": "KEYCODE_LCONTROL",
        "p1.button2": "KEYCODE_LALT",
        "p1.button3": "KEYCODE_SPACE",
        "p1.button4": "KEYCODE_LSHIFT",
        "p1.button5": "KEYCODE_Z",
        "p1.button6": "KEYCODE_X",
        "p1.button7": "KEYCODE_C",
        "p1.button8": "KEYCODE_V",
        "p1.start": "KEYCODE_1",
        "p1.coin": "KEYCODE_5",
        
        "p2.up": "KEYCODE_R",
        "p2.down": "KEYCODE_F",
        "p2.left": "KEYCODE_D",
        "p2.right": "KEYCODE_G",
        "p2.button1": "KEYCODE_A",
        "p2.button2": "KEYCODE_S",
        "p2.button3": "KEYCODE_Q",
        "p2.button4": "KEYCODE_W",
        "p2.button5": "KEYCODE_I",
        "p2.button6": "KEYCODE_K",
        "p2.button7": "KEYCODE_J",
        "p2.button8": "KEYCODE_L",
        "p2.start": "KEYCODE_2",
        "p2.coin": "KEYCODE_6",
    }
    
    if control_key in IPAC_DEFAULTS:
        return IPAC_DEFAULTS[control_key]
    
    # Generic fallback
    return "KEYCODE_SPACE"


def _get_joycode_for_control(control_key: str, xinput_map: Dict[str, str]) -> str:
    """Get MAME JOYCODE for XInput mode.

    Args:
        control_key: The control identifier (e.g., "p1.button1")
        xinput_map: The XINPUT_BUTTON_MAP dictionary

    Returns:
        MAME joycode string (e.g., "JOYCODE_1_BUTTON1")
    """
    joycode = xinput_map.get(control_key)
    if joycode:
        logger.debug(f"✅ Found mapping: {control_key} → {joycode}")
        return joycode

    # Fallback: construct a reasonable JOYCODE
    logger.warning(f"⚠️ No XINPUT_BUTTON_MAP entry for '{control_key}', using fallback logic")
    player_num = control_key[1] if control_key.startswith("p") else "1"
    
    if "button" in control_key:
        btn_num = control_key.split("button")[-1] if "button" in control_key else "1"
        return f"JOYCODE_{player_num}_BUTTON{btn_num}"
    elif control_key.endswith(".start"):
        return f"JOYCODE_{player_num}_START"
    elif control_key.endswith(".coin"):
        return f"JOYCODE_{player_num}_SELECT"
    elif "up" in control_key:
        return f"JOYCODE_{player_num}_YAXIS_UP_SWITCH"
    elif "down" in control_key:
        return f"JOYCODE_{player_num}_YAXIS_DOWN_SWITCH"
    elif "left" in control_key:
        return f"JOYCODE_{player_num}_XAXIS_LEFT_SWITCH"
    elif "right" in control_key:
        return f"JOYCODE_{player_num}_XAXIS_RIGHT_SWITCH"
    else:
        logger.warning(f"Unknown control '{control_key}' - defaulting to BUTTON1")
        return f"JOYCODE_{player_num}_BUTTON1"


def _convert_captured_to_mame_joycode(captured_code: str, control_key: str) -> str:
    """Convert a captured XInput/gamepad code to MAME JOYCODE format.
    
    The Learn Wizard captures codes like:
    - BTN_0_JS0, BTN_6_JS0 (button on joystick 0)
    - DPAD_UP_JS0 (D-pad direction)
    - AXIS_0-_JS0, AXIS_1+_JS0 (analog axis)
    
    This converts them to MAME format:
    - JOYCODE_1_BUTTON1, JOYCODE_1_BUTTON7
    - JOYCODE_1_YAXIS_UP_SWITCH
    - JOYCODE_1_XAXIS_LEFT_SWITCH
    
    Args:
        captured_code: The code captured by Learn Wizard (e.g., "BTN_6_JS0")
        control_key: The control being mapped (e.g., "p1.button3") for player context
        
    Returns:
        MAME-compatible JOYCODE string
    """
    # Extract joystick number from captured code (JS0 = joystick 1, JS1 = joystick 2)
    js_num = 1  # Default to joystick 1
    if "_JS" in captured_code:
        try:
            js_num = int(captured_code.split("_JS")[-1]) + 1  # JS0 -> 1, JS1 -> 2
        except ValueError:
            pass
    
    code_upper = captured_code.upper()
    
    # Handle button captures (BTN_0_JS0 -> JOYCODE_1_BUTTON1)
    if code_upper.startswith("BTN_"):
        try:
            btn_num = int(code_upper.split("_")[1]) + 1  # BTN_0 -> BUTTON1, BTN_6 -> BUTTON7
            return f"JOYCODE_{js_num}_BUTTON{btn_num}"
        except (ValueError, IndexError):
            pass
    
    # Handle D-pad captures
    if "DPAD_UP" in code_upper:
        return f"JOYCODE_{js_num}_YAXIS_UP_SWITCH"
    if "DPAD_DOWN" in code_upper:
        return f"JOYCODE_{js_num}_YAXIS_DOWN_SWITCH"
    if "DPAD_LEFT" in code_upper:
        return f"JOYCODE_{js_num}_XAXIS_LEFT_SWITCH"
    if "DPAD_RIGHT" in code_upper:
        return f"JOYCODE_{js_num}_XAXIS_RIGHT_SWITCH"
    
    # Handle axis captures (AXIS_0-_JS0 = left stick left)
    if "AXIS_" in code_upper:
        # Axis 0 = X (left/right), Axis 1 = Y (up/down)
        if "AXIS_0-" in code_upper:
            return f"JOYCODE_{js_num}_XAXIS_LEFT_SWITCH"
        if "AXIS_0+" in code_upper:
            return f"JOYCODE_{js_num}_XAXIS_RIGHT_SWITCH"
        if "AXIS_1-" in code_upper:
            return f"JOYCODE_{js_num}_YAXIS_UP_SWITCH"
        if "AXIS_1+" in code_upper:
            return f"JOYCODE_{js_num}_YAXIS_DOWN_SWITCH"
    
    # Handle START/SELECT if captured directly
    if "START" in code_upper:
        return f"JOYCODE_{js_num}_START"
    if "SELECT" in code_upper or "BACK" in code_upper:
        return f"JOYCODE_{js_num}_SELECT"
    
    # Fallback: try to guess from control_key
    logger.warning(f"Couldn't parse captured code '{captured_code}', falling back to control_key")
    player_num = control_key[1] if control_key.startswith("p") else str(js_num)
    
    if "button" in control_key:
        btn_num = control_key.split("button")[-1]
        return f"JOYCODE_{player_num}_BUTTON{btn_num}"
    elif "start" in control_key:
        return f"JOYCODE_{player_num}_START"
    elif "coin" in control_key:
        return f"JOYCODE_{player_num}_SELECT"
    
    return f"JOYCODE_{js_num}_BUTTON1"

def generate_mame_config(mapping_dict: Dict[str, Any]) -> str:
    """Generate MAME default.cfg XML from Mapping Dictionary.
    
    Supports adaptive mode detection:
    - XInput mode: Generates JOYCODE_* entries (Xbox controller)
    - Keyboard mode: Generates KEYCODE_* entries (keyboard scancodes)

    Args:
        mapping_dict: Complete mapping dictionary from controls.json

    Returns:
        Formatted XML string for MAME default.cfg

    Raises:
        MAMEConfigError: If mapping data is invalid or generation fails
    """
    try:
        # Validate input structure
        if "mappings" not in mapping_dict:
            raise MAMEConfigError("Missing 'mappings' key in mapping dictionary")

        mappings = mapping_dict["mappings"]
        
        # Detect encoder mode - default to xinput for arcade cabinets
        encoder_mode = mapping_dict.get("encoder_mode", "xinput")
        logger.info(f"Generating MAME config for encoder_mode: {encoder_mode}")

        # Create root mameconfig element
        root = ET.Element("mameconfig", version="10")

        # Add system element with default tag
        system = ET.SubElement(root, "system", name="default")

        # Add input section
        input_elem = ET.SubElement(system, "input")

        # Generate port entries for each mapped control
        ports_added = set()
        
        # XInput button name to MAME JOYCODE mapping
        # For XInput controllers (like PactoTech-2000T), MAME uses JOYCODE format
        XINPUT_BUTTON_MAP = {
            # Player 1 buttons (joystick 1)
            "p1.button1": "JOYCODE_1_BUTTON1",  # A button
            "p1.button2": "JOYCODE_1_BUTTON2",  # B button
            "p1.button3": "JOYCODE_1_BUTTON3",  # X button
            "p1.button4": "JOYCODE_1_BUTTON4",  # Y button
            "p1.button5": "JOYCODE_1_BUTTON5",  # LB
            "p1.button6": "JOYCODE_1_BUTTON6",  # RB
            "p1.button7": "JOYCODE_1_BUTTON7",  # LT (as button)
            "p1.button8": "JOYCODE_1_BUTTON8",  # RT (as button)
            "p1.start": "JOYCODE_1_START",
            "p1.coin": "JOYCODE_1_SELECT",      # Back button = coin
            "p1.up": "JOYCODE_1_YAXIS_UP_SWITCH",
            "p1.down": "JOYCODE_1_YAXIS_DOWN_SWITCH", 
            "p1.left": "JOYCODE_1_XAXIS_LEFT_SWITCH",
            "p1.right": "JOYCODE_1_XAXIS_RIGHT_SWITCH",
            # Alternate joystick direction names
            "p1.joystick_up": "JOYCODE_1_YAXIS_UP_SWITCH",
            "p1.joystick_down": "JOYCODE_1_YAXIS_DOWN_SWITCH",
            "p1.joystick_left": "JOYCODE_1_XAXIS_LEFT_SWITCH",
            "p1.joystick_right": "JOYCODE_1_XAXIS_RIGHT_SWITCH",
            
            # Player 2 buttons (joystick 2)
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
            "p2.up": "JOYCODE_2_YAXIS_UP_SWITCH",
            "p2.down": "JOYCODE_2_YAXIS_DOWN_SWITCH",
            "p2.left": "JOYCODE_2_XAXIS_LEFT_SWITCH",
            "p2.right": "JOYCODE_2_XAXIS_RIGHT_SWITCH",
            "p2.joystick_up": "JOYCODE_2_YAXIS_UP_SWITCH",
            "p2.joystick_down": "JOYCODE_2_YAXIS_DOWN_SWITCH",
            "p2.joystick_left": "JOYCODE_2_XAXIS_LEFT_SWITCH",
            "p2.joystick_right": "JOYCODE_2_XAXIS_RIGHT_SWITCH",
            
            # Player 3 buttons (joystick 3)
            "p3.button1": "JOYCODE_3_BUTTON1",
            "p3.button2": "JOYCODE_3_BUTTON2",
            "p3.button3": "JOYCODE_3_BUTTON3",
            "p3.button4": "JOYCODE_3_BUTTON4",
            "p3.start": "JOYCODE_3_START",
            "p3.coin": "JOYCODE_3_SELECT",
            "p3.up": "JOYCODE_3_YAXIS_UP_SWITCH",
            "p3.down": "JOYCODE_3_YAXIS_DOWN_SWITCH",
            "p3.left": "JOYCODE_3_XAXIS_LEFT_SWITCH",
            "p3.right": "JOYCODE_3_XAXIS_RIGHT_SWITCH",
            "p3.joystick_up": "JOYCODE_3_YAXIS_UP_SWITCH",
            "p3.joystick_down": "JOYCODE_3_YAXIS_DOWN_SWITCH",
            "p3.joystick_left": "JOYCODE_3_XAXIS_LEFT_SWITCH",
            "p3.joystick_right": "JOYCODE_3_XAXIS_RIGHT_SWITCH",
            
            # Player 4 buttons (joystick 4)
            "p4.button1": "JOYCODE_4_BUTTON1",
            "p4.button2": "JOYCODE_4_BUTTON2",
            "p4.button3": "JOYCODE_4_BUTTON3",
            "p4.button4": "JOYCODE_4_BUTTON4",
            "p4.start": "JOYCODE_4_START",
            "p4.coin": "JOYCODE_4_SELECT",
            "p4.up": "JOYCODE_4_YAXIS_UP_SWITCH",
            "p4.down": "JOYCODE_4_YAXIS_DOWN_SWITCH",
            "p4.left": "JOYCODE_4_XAXIS_LEFT_SWITCH",
            "p4.right": "JOYCODE_4_XAXIS_RIGHT_SWITCH",
            "p4.joystick_up": "JOYCODE_4_YAXIS_UP_SWITCH",
            "p4.joystick_down": "JOYCODE_4_YAXIS_DOWN_SWITCH",
            "p4.joystick_left": "JOYCODE_4_XAXIS_LEFT_SWITCH",
            "p4.joystick_right": "JOYCODE_4_XAXIS_RIGHT_SWITCH",
        }

        for control_key, control_data in mappings.items():
            # Get MAME mapping for this control
            mame_mapping = MAME_PORT_MAPPINGS.get(control_key)
            if not mame_mapping:
                logger.debug(f"No MAME mapping for control: {control_key}")
                continue

            port_name = mame_mapping["port"]
            control_type = mame_mapping["type"]

            # Create port entry
            port_key = f"{port_name}_{control_type}"
            if port_key not in ports_added:
                # Get mask value from MAME_PORT_MAPPINGS
                mask_value = mame_mapping.get("mask", "0x00")

                # Add port element with correct MAME attributes
                # CRITICAL: tag and type must match EXACTLY for MAME to recognize the port
                port_tag = f"{port_name}_{control_type}"
                port = ET.SubElement(
                    input_elem,
                    "port",
                    tag=port_tag,
                    type=port_tag,  # Must match tag exactly!
                    mask=mask_value,
                    defvalue="0x00"  # Default value when not pressed
                )

                # Generate code based on encoder mode
                if encoder_mode == "keyboard":
                    # Keyboard mode: use captured keycode from controls.json
                    mame_code = _get_keycode_for_control(control_key, control_data)
                else:
                    # XInput mode: use captured keycode if available, else fallback
                    captured_keycode = control_data.get("keycode", "")
                    if captured_keycode:
                        # Convert captured XInput code to MAME JOYCODE format
                        mame_code = _convert_captured_to_mame_joycode(captured_keycode, control_key)
                    else:
                        # Fallback to hardcoded mapping if no capture
                        mame_code = _get_joycode_for_control(control_key, XINPUT_BUTTON_MAP)

                # Add newseq element with our binding
                # CRITICAL: Only ONE newseq per port! Multiple newseqs create OR chains.
                # type="standard" tells MAME this is the primary binding (not "increment"/"decrement")
                newseq = ET.SubElement(port, "newseq", type="standard")
                newseq.text = mame_code

                # IMPORTANT: Clear increment/decrement sequences to prevent MAME adding default bindings
                # This stops MAME from creating OR chains with arrow keys or other defaults
                newseq_inc = ET.SubElement(port, "newseq", type="increment")
                newseq_inc.text = "NONE"  # Explicitly clear increment binding

                newseq_dec = ET.SubElement(port, "newseq", type="decrement")
                newseq_dec.text = "NONE"  # Explicitly clear decrement binding

                ports_added.add(port_key)

        # Convert to pretty-printed XML string
        xml_string = minidom.parseString(
            ET.tostring(root, encoding='unicode')
        ).toprettyxml(indent="  ")

        # Remove extra blank lines
        xml_lines = [line for line in xml_string.split('\n') if line.strip()]
        formatted_xml = '\n'.join(xml_lines)

        return formatted_xml

    except ET.ParseError as e:
        raise MAMEConfigError(f"XML generation failed: {str(e)}")
    except Exception as e:
        logger.error(f"MAME config generation error: {e}")
        raise MAMEConfigError(f"Failed to generate MAME config: {str(e)}")


def validate_mame_config(xml_content: str) -> List[str]:
    """Validate MAME config XML for correctness

    Args:
        xml_content: XML string to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    try:
        # Try to parse XML
        root = ET.fromstring(xml_content)

        # Validate root element
        if root.tag != "mameconfig":
            errors.append("Root element must be 'mameconfig'")

        # Validate version attribute
        if "version" not in root.attrib:
            errors.append("Missing 'version' attribute on mameconfig element")

        # Find system element
        systems = root.findall("system")
        if not systems:
            errors.append("Missing 'system' element")
        elif len(systems) > 1:
            errors.append("Multiple 'system' elements found (expected 1)")
        else:
            system = systems[0]

            # Validate system name
            if "name" not in system.attrib:
                errors.append("Missing 'name' attribute on system element")
            elif system.attrib["name"] != "default":
                errors.append("System name should be 'default'")

            # Find input element
            inputs = system.findall("input")
            if not inputs:
                errors.append("Missing 'input' element")
            elif len(inputs) > 1:
                errors.append("Multiple 'input' elements found (expected 1)")
            else:
                input_elem = inputs[0]

                # Validate port elements
                ports = input_elem.findall("port")
                if not ports:
                    errors.append("No 'port' elements found in input section")

                for port in ports:
                    # Validate port attributes
                    if "tag" not in port.attrib:
                        errors.append(f"Port missing 'tag' attribute")
                    if "type" not in port.attrib:
                        errors.append(f"Port missing 'type' attribute")

                    # Validate newseq element
                    newseqs = port.findall("newseq")
                    if not newseqs:
                        errors.append(f"Port {port.attrib.get('tag', 'unknown')} missing 'newseq' element")

    except ET.ParseError as e:
        errors.append(f"XML parse error: {str(e)}")
    except Exception as e:
        errors.append(f"Validation error: {str(e)}")

    return errors


def get_mame_config_summary(xml_content: str) -> Dict[str, Any]:
    """Extract summary information from MAME config XML

    Args:
        xml_content: XML string to summarize

    Returns:
        Dictionary with config summary (port count, player count, etc.)
    """
    summary = {
        "valid": False,
        "port_count": 0,
        "player_count": 0,
        "players": [],
        "controls_by_player": {}
    }

    try:
        root = ET.fromstring(xml_content)
        system = root.find("system")
        if system is None:
            return summary

        input_elem = system.find("input")
        if input_elem is None:
            return summary

        ports = input_elem.findall("port")
        summary["port_count"] = len(ports)

        # Extract player numbers from port types
        players_seen = set()
        controls_by_player = {}

        for port in ports:
            port_type = port.attrib.get("type", "")
            # Extract player number (e.g., "P1_BUTTON1" -> "P1")
            if port_type.startswith("P"):
                player = port_type.split("_")[0]
                players_seen.add(player)

                if player not in controls_by_player:
                    controls_by_player[player] = []

                # Extract control type
                control_type = "_".join(port_type.split("_")[1:])
                controls_by_player[player].append(control_type)

        summary["player_count"] = len(players_seen)
        summary["players"] = sorted(list(players_seen))
        summary["controls_by_player"] = controls_by_player
        summary["valid"] = True

    except Exception as e:
        logger.error(f"Failed to generate MAME config summary: {e}")

    return summary


# =============================================================================
# MODULE A.4: MameConfigWriter Class - The Final Mile
# =============================================================================
# This class wraps the generation logic with file I/O and safety protocols.
# Governance: Safety First (Rule #1) - Always backup before writing.
# =============================================================================

from pathlib import Path
from datetime import datetime
import json
import shutil


class MameConfigWriter:
    """
    Writes MAME default.cfg from controls.json with built-in safety.
    
    Critical Constraints:
    - Device Indexing: Uses device_id from captured inputs (JS0→1, JS1→2)
    - Safety First: Creates timestamped backup before writing
    - No OR Logic: Single input per function (cleared increment/decrement)
    - Trigger Fix: Handles TRIGGER_0→BUTTON7, TRIGGER_1→BUTTON8
    """
    
    # Default paths resolved from the canonical drive root contract.
    DEFAULT_CONTROLS_JSON = get_drive_root(context="mame_config_generator controls") / "config" / "mappings" / "controls.json"
    DEFAULT_MAME_CFG = get_drive_root(context="mame_config_generator cfg") / "Emulators" / "MAME Gamepad" / "cfg" / "default.cfg"
    DEFAULT_BACKUP_DIR = get_drive_root(context="mame_config_generator backups") / ".aa" / "backups" / "configs"
    
    def __init__(
        self,
        controls_json_path: Optional[Path] = None,
        mame_cfg_path: Optional[Path] = None,
        backup_dir: Optional[Path] = None,
    ):
        self.controls_json_path = controls_json_path or self.DEFAULT_CONTROLS_JSON
        self.mame_cfg_path = mame_cfg_path or self.DEFAULT_MAME_CFG
        self.backup_dir = backup_dir or self.DEFAULT_BACKUP_DIR
        
        self._last_backup_path: Optional[Path] = None
        self._last_summary: Optional[Dict[str, Any]] = None
    
    def read_controls(self) -> Dict[str, Any]:
        """Read controls.json mapping file."""
        if not self.controls_json_path.exists():
            raise MAMEConfigError(f"Controls file not found: {self.controls_json_path}")
        
        with open(self.controls_json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def create_backup(self) -> Optional[Path]:
        """
        Create timestamped backup of existing MAME config.
        
        Returns:
            Path to backup file, or None if no existing file to backup
        """
        if not self.mame_cfg_path.exists():
            logger.info("No existing MAME config to backup")
            return None
        
        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Create timestamped backup filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"default.cfg.{timestamp}.bak"
        backup_path = self.backup_dir / backup_name
        
        # Copy existing file to backup
        shutil.copy2(self.mame_cfg_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
        
        self._last_backup_path = backup_path
        return backup_path
    
    def generate(self) -> str:
        """
        Generate MAME config XML from controls.json.
        
        Returns:
            Generated XML string (does not write to disk)
        """
        mapping_data = self.read_controls()
        xml_content = generate_mame_config(mapping_data)
        
        # Validate before returning
        errors = validate_mame_config(xml_content)
        if errors:
            raise MAMEConfigError(f"Generated config failed validation: {', '.join(errors)}")
        
        self._last_summary = get_mame_config_summary(xml_content)
        return xml_content
    
    def write(self, create_backup: bool = True) -> Dict[str, Any]:
        """
        Generate and write MAME config with safety backup.
        
        Args:
            create_backup: If True, backup existing config first (default: True)
        
        Returns:
            Dictionary with status, backup_path, and summary
        """
        # SAFETY FIRST: Create backup before any changes
        backup_path = None
        if create_backup:
            backup_path = self.create_backup()
        
        # Generate the new config
        xml_content = self.generate()
        
        # Ensure output directory exists
        self.mame_cfg_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write the new config
        with open(self.mame_cfg_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)
        
        logger.info(f"Wrote MAME config: {self.mame_cfg_path}")
        
        return {
            "status": "success",
            "mame_cfg_path": str(self.mame_cfg_path),
            "backup_path": str(backup_path) if backup_path else None,
            "summary": self._last_summary,
        }
    
    def rollback(self) -> bool:
        """
        Restore the last backup (undo last write).
        
        Returns:
            True if rollback succeeded, False if no backup available
        """
        if not self._last_backup_path or not self._last_backup_path.exists():
            logger.warning("No backup available for rollback")
            return False
        
        shutil.copy2(self._last_backup_path, self.mame_cfg_path)
        logger.info(f"Rolled back to: {self._last_backup_path}")
        return True
    
    @property
    def last_backup_path(self) -> Optional[Path]:
        return self._last_backup_path
    
    @property
    def last_summary(self) -> Optional[Dict[str, Any]]:
        return self._last_summary


# Convenience function for one-liner usage
def write_mame_config_safe(
    controls_path: Optional[Path] = None,
    mame_cfg_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    One-liner to generate and write MAME config with safety backup.
    
    Example:
        result = write_mame_config_safe()
        print(f"Written to {result['mame_cfg_path']}, backup at {result['backup_path']}")
    """
    writer = MameConfigWriter(
        controls_json_path=controls_path,
        mame_cfg_path=mame_cfg_path,
    )
    return writer.write(create_backup=True)


# Module-level test function
if __name__ == "__main__":
    print("MAME Config Generator Test")
    print("=" * 50)

    # Test with minimal mapping
    test_mapping = {
        "version": "1.0",
        "board": {
            "vid": "0xd209",
            "pid": "0x0501",
            "name": "Ultimarc I-PAC2"
        },
        "mappings": {
            "p1.joystick_up": {"pin": 1, "type": "joystick", "label": "P1 Up"},
            "p1.joystick_down": {"pin": 2, "type": "joystick", "label": "P1 Down"},
            "p1.button1": {"pin": 5, "type": "button", "label": "P1 Button 1"},
            "p1.button2": {"pin": 6, "type": "button", "label": "P1 Button 2"},
            "p1.start": {"pin": 9, "type": "button", "label": "P1 Start"},
            "p2.button1": {"pin": 21, "type": "button", "label": "P2 Button 1"},
        }
    }

    try:
        print("\nGenerating MAME config from test mapping...")
        xml_output = generate_mame_config(test_mapping)

        print("\nGenerated XML:")
        print(xml_output)

        print("\n" + "=" * 50)
        print("\nValidating generated XML...")
        errors = validate_mame_config(xml_output)

        if errors:
            print(f"Validation FAILED with {len(errors)} error(s):")
            for error in errors:
                print(f"  - {error}")
        else:
            print("Validation PASSED - XML is well-formed")

        print("\n" + "=" * 50)
        print("\nConfig Summary:")
        summary = get_mame_config_summary(xml_output)
        print(f"  Valid: {summary['valid']}")
        print(f"  Port Count: {summary['port_count']}")
        print(f"  Player Count: {summary['player_count']}")
        print(f"  Players: {', '.join(summary['players'])}")

        for player, controls in summary['controls_by_player'].items():
            print(f"  {player}: {len(controls)} controls - {', '.join(controls[:3])}{'...' if len(controls) > 3 else ''}")

    except MAMEConfigError as e:
        print(f"\nERROR: {e}")

