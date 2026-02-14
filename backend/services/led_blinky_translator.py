"""
LED Blinky Input Map Translator

Converts our JSON port mapping to LEDBlinkyInputMap.xml format.
This is the "Phase 2 Translator" that bridges our wizard output
to LEDBlinky's expected configuration.

Architecture:
    1. Reads led_port_mapping.json (our wizard output)
    2. Translates logical IDs to MAME input codes
    3. Generates LEDBlinkyInputMap.xml for LEDBlinky.exe

Cabinet Config:
    - 4 players, each with 8 buttons + start + coin = 40 LED ports
    - Joysticks are solid (no LEDs) - not mapped
"""

from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, Optional
from xml.dom import minidom
from datetime import datetime

from backend.constants.paths import Paths

logger = logging.getLogger(__name__)


# =============================================================================
# LOGICAL ID TO MAME INPUT CODE MAPPING
# =============================================================================
# NOTE: Joysticks use solid controllers (no LEDs) - only buttons/start/coin
# Supports both short format (p1.b1) and long format (p1.button1) from GUI

LOGICAL_TO_MAME = {
    # Player 1 - 8 buttons + start/coin (both formats)
    "p1.b1": "P1_BUTTON1", "p1.button1": "P1_BUTTON1",
    "p1.b2": "P1_BUTTON2", "p1.button2": "P1_BUTTON2",
    "p1.b3": "P1_BUTTON3", "p1.button3": "P1_BUTTON3",
    "p1.b4": "P1_BUTTON4", "p1.button4": "P1_BUTTON4",
    "p1.b5": "P1_BUTTON5", "p1.button5": "P1_BUTTON5",
    "p1.b6": "P1_BUTTON6", "p1.button6": "P1_BUTTON6",
    "p1.b7": "P1_BUTTON7", "p1.button7": "P1_BUTTON7",
    "p1.b8": "P1_BUTTON8", "p1.button8": "P1_BUTTON8",
    "p1.start": "START1",
    "p1.coin": "COIN1",
    
    # Player 2 - 8 buttons + start/coin
    "p2.b1": "P2_BUTTON1", "p2.button1": "P2_BUTTON1",
    "p2.b2": "P2_BUTTON2", "p2.button2": "P2_BUTTON2",
    "p2.b3": "P2_BUTTON3", "p2.button3": "P2_BUTTON3",
    "p2.b4": "P2_BUTTON4", "p2.button4": "P2_BUTTON4",
    "p2.b5": "P2_BUTTON5", "p2.button5": "P2_BUTTON5",
    "p2.b6": "P2_BUTTON6", "p2.button6": "P2_BUTTON6",
    "p2.b7": "P2_BUTTON7", "p2.button7": "P2_BUTTON7",
    "p2.b8": "P2_BUTTON8", "p2.button8": "P2_BUTTON8",
    "p2.start": "START2",
    "p2.coin": "COIN2",
    
    # Player 3 - 4 buttons + start/coin (reduced layout)
    "p3.b1": "P3_BUTTON1", "p3.button1": "P3_BUTTON1",
    "p3.b2": "P3_BUTTON2", "p3.button2": "P3_BUTTON2",
    "p3.b3": "P3_BUTTON3", "p3.button3": "P3_BUTTON3",
    "p3.b4": "P3_BUTTON4", "p3.button4": "P3_BUTTON4",
    "p3.start": "START3",
    "p3.coin": "COIN3",
    
    # Player 4 - 4 buttons + start/coin (reduced layout)
    "p4.b1": "P4_BUTTON1", "p4.button1": "P4_BUTTON1",
    "p4.b2": "P4_BUTTON2", "p4.button2": "P4_BUTTON2",
    "p4.b3": "P4_BUTTON3", "p4.button3": "P4_BUTTON3",
    "p4.b4": "P4_BUTTON4", "p4.button4": "P4_BUTTON4",
    "p4.start": "START4",
    "p4.coin": "COIN4",
}

# Reverse mapping for validation
MAME_TO_LOGICAL = {v: k for k, v in LOGICAL_TO_MAME.items()}


# =============================================================================
# TRANSLATOR SERVICE
# =============================================================================

class LEDBlinkyTranslator:
    """
    Translates our JSON mapping to LEDBlinkyInputMap.xml.
    
    This enables the hybrid approach:
    - Our UI-driven wizard creates the physical-to-logical mapping
    - LEDBlinky's engine handles game-aware lighting at runtime
    """
    
    @classmethod
    def json_path(cls) -> Path:
        """Our source JSON mapping file from calibration wizard."""
        return Paths.drive_root() / ".aa" / "config" / "led_port_mapping.json"
    
    @classmethod
    def xml_path(cls) -> Path:
        """LEDBlinky's target XML file."""
        return Paths.Tools.LEDBlinky.root() / "LEDBlinkyInputMap.xml"
    
    @classmethod
    def backup_path(cls) -> Path:
        """Backup location for existing XML."""
        return Paths.Tools.LEDBlinky.root() / "LEDBlinkyInputMap.xml.bak"
    
    @classmethod
    def load_mapping(cls) -> Dict[str, Any]:
        """Load our JSON mapping file."""
        path = cls.json_path()
        if not path.exists():
            return {"mappings": {}, "version": 0}
        
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"[Translator] Failed to load mapping: {e}")
            return {"mappings": {}, "error": str(e)}
    
    @classmethod
    def get_logical_label(cls, logical_id: str) -> str:
        """Generate a human-readable label from logical ID."""
        # Convert p1.b1 -> "P1 Button 1"
        parts = logical_id.lower().split(".")
        if len(parts) != 2:
            return logical_id
        
        player = parts[0].upper()  # "P1"
        control = parts[1]
        
        if control.startswith("b") and control[1:].isdigit():
            return f"{player} Button {control[1:]}"
        elif control == "start":
            return f"{player} Start"
        elif control == "coin":
            return f"{player} Coin"
        else:
            return logical_id
    
    @classmethod
    def translate(cls) -> Dict[str, Any]:
        """
        Convert led_port_mapping.json → LEDBlinkyInputMap.xml
        
        Returns:
            Status dict with success/error info
        """
        json_path = cls.json_path()
        xml_path = cls.xml_path()
        
        # Check source exists
        if not json_path.exists():
            return {
                "success": False,
                "error": f"Source mapping not found: {json_path}",
                "hint": "Run the calibration wizard first to create port mappings"
            }
        
        # Load our JSON mapping
        try:
            mapping_data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to parse JSON: {e}"
            }
        
        mappings = mapping_data.get("mappings", {})
        
        if not mappings:
            return {
                "success": False,
                "error": "No port mappings found in JSON",
                "hint": "Complete the calibration wizard to map ports to buttons"
            }
        
        # Build XML structure
        root = ET.Element("LEDBlinkyInputMap")
        root.set("generatedBy", "ArcadeAssistant")
        root.set("generatedAt", datetime.now().isoformat())
        
        translated_count = 0
        unknown_ids = []
        
        for port_str, entry in sorted(mappings.items(), key=lambda x: int(x[0])):
            logical_id = entry.get("logical_id", "")
            description = entry.get("description", "")
            
            # Convert to MAME input code
            input_code = LOGICAL_TO_MAME.get(logical_id.lower(), "")
            
            if not input_code:
                unknown_ids.append(logical_id)
                # Still create the port entry, just without input code
                logger.warning(f"[Translator] Unknown logical ID: {logical_id}")
            else:
                translated_count += 1
            
            # Generate label if not provided
            label = description if description else cls.get_logical_label(logical_id)
            
            # Create port element
            port_elem = ET.SubElement(root, "port")
            port_elem.set("index", port_str)
            port_elem.set("deviceId", "1")  # First LED-Wiz
            port_elem.set("label", label)
            port_elem.set("ledType", "Single")  # Single color LEDs
            port_elem.set("inputCodes", input_code)
            port_elem.set("colorAdjust", "0")
        
        # Pretty-print XML
        xml_str = minidom.parseString(
            ET.tostring(root, encoding="unicode")
        ).toprettyxml(indent="  ")
        
        # Remove extra blank lines from pretty print
        lines = [line for line in xml_str.split("\n") if line.strip()]
        xml_str = "\n".join(lines)
        
        # Backup existing file
        if xml_path.exists():
            try:
                backup_path = cls.backup_path()
                xml_path.rename(backup_path)
                logger.info(f"[Translator] Backed up existing InputMap to {backup_path}")
            except Exception as e:
                logger.warning(f"[Translator] Could not backup existing file: {e}")
        
        # Write new XML
        try:
            xml_path.write_text(xml_str, encoding="utf-8")
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to write XML: {e}"
            }
        
        logger.info(f"[Translator] Translated {translated_count} mappings to {xml_path}")
        
        result = {
            "success": True,
            "mappings_count": len(mappings),
            "translated_count": translated_count,
            "xml_path": str(xml_path),
            "json_path": str(json_path)
        }
        
        if unknown_ids:
            result["warnings"] = f"Unknown logical IDs: {unknown_ids}"
        
        return result
    
    @classmethod
    def validate_xml(cls) -> Dict[str, Any]:
        """Validate the generated XML file exists and is parseable."""
        xml_path = cls.xml_path()
        
        if not xml_path.exists():
            return {
                "valid": False,
                "error": "LEDBlinkyInputMap.xml does not exist",
                "path": str(xml_path)
            }
        
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            port_count = len(root.findall("port"))
            
            return {
                "valid": True,
                "path": str(xml_path),
                "port_count": port_count,
                "generated_by": root.get("generatedBy", "unknown"),
                "generated_at": root.get("generatedAt", "unknown")
            }
        except ET.ParseError as e:
            return {
                "valid": False,
                "error": f"XML parse error: {e}",
                "path": str(xml_path)
            }
    
    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Get current translator status including both files."""
        json_path = cls.json_path()
        xml_path = cls.xml_path()
        
        return {
            "json_exists": json_path.exists(),
            "json_path": str(json_path),
            "xml_exists": xml_path.exists(),
            "xml_path": str(xml_path),
            "supported_controls": len(LOGICAL_TO_MAME),
            "validation": cls.validate_xml() if xml_path.exists() else None
        }
