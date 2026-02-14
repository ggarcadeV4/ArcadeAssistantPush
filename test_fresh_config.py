"""Generate fresh config and check P2 joystick mappings."""
import sys
sys.path.insert(0, 'backend')

from services.mame_config_generator import generate_mame_config
import json
import xml.etree.ElementTree as ET

# Load controls
with open('config/mappings/controls.json') as f:
    data = json.load(f)

# Generate config
xml_str = generate_mame_config(data)

# Parse and check P2 joystick
root = ET.fromstring(xml_str)

print("P2 Joystick mappings in FRESH config:")
for port in root.findall('.//port'):
    tag = port.get('tag', '')
    if 'P2_JOYSTICK' in tag:
        newseq = port.find('newseq[@type="standard"]')
        if newseq is not None:
            joycode = newseq.text
            status = "OK" if "JOYCODE_2_" in joycode else "WRONG"
            print(f"  {tag}: {joycode} [{status}]")
