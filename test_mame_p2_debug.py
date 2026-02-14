"""
Debug script to trace P2 joystick mapping issue in MAME config generation.
"""
import sys
sys.path.insert(0, 'backend')

from services.mame_config_generator import generate_mame_config
import json

# Load controls
with open('config/mappings/controls.json') as f:
    controls_data = json.load(f)

print("=" * 80)
print("P2 JOYSTICK MAPPING DEBUG")
print("=" * 80)

# Check what's in controls.json for P2 joystick
print("\nP2 Joystick entries in controls.json:")
for key in ['p2.up', 'p2.down', 'p2.left', 'p2.right']:
    if key in controls_data['mappings']:
        print(f"  {key}: {controls_data['mappings'][key]}")
    else:
        print(f"  {key}: MISSING")

# Generate config
print("\nGenerating MAME config...")
result = generate_mame_config(controls_data)

print(f"\nConfig generated with {result['summary']['port_count']} ports")
print(f"  Players: {result['summary']['players']}")

# Extract P2 joystick mappings from generated XML
import xml.etree.ElementTree as ET
root = ET.fromstring(result['xml_content'])

print("\nP2 Joystick JOYCODE assignments in generated config:")
for port in root.findall('.//port'):
    tag = port.get('tag', '')
    if tag.startswith('P2_JOYSTICK'):
        newseq = port.find('newseq[@type="standard"]')
        if newseq is not None:
            joycode = newseq.text
            status = "OK" if "JOYCODE_2_" in joycode else "WRONG"
            print(f"  {tag}: {joycode} [{status}]")

print("\n" + "=" * 80)
print("DIAGNOSIS:")
print("=" * 80)
print("If P2 joystick shows JOYCODE_1 instead of JOYCODE_2, the bug is in")
print("the config generator's assignment logic.")
print("=" * 80)
