"""Test for port_key collisions in MAME config generation."""

MAME_PORT_MAPPINGS = {
    'p1.up': {'port': 'P1', 'type': 'JOYSTICK_UP'},
    'p1.joystick_up': {'port': 'P1', 'type': 'JOYSTICK_UP'},
    'p2.up': {'port': 'P2', 'type': 'JOYSTICK_UP'},
    'p2.joystick_up': {'port': 'P2', 'type': 'JOYSTICK_UP'},
}

port_keys = {}
for ctrl, mapping in MAME_PORT_MAPPINGS.items():
    port_key = f"{mapping['port']}_{mapping['type']}"
    if port_key in port_keys:
        print(f'COLLISION: {ctrl} and {port_keys[port_key]} both map to {port_key}')
    else:
        port_keys[port_key] = ctrl
        print(f'{ctrl} => {port_key}')
