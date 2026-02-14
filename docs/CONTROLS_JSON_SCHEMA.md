# The Rosetta Stone: `controls.json` Schema

> **Purpose:** The canonical mapping file that sits between hardware detection and emulator config generation.

## File Location
```
A:\Arcade Assistant Local\config\mappings\controls.json
```

## Schema Version: 1.0

```json
{
  "comment": "String - Informational note (DO NOT MODIFY for factory default)",
  "version": "1.0",
  "created_at": "ISO 8601 timestamp",
  "last_modified": "ISO 8601 timestamp",
  "modified_by": "String - Agent/user identifier",
  
  "board": {
    "vid": "0x045E",         // Vendor ID (hex string)
    "pid": "0x028E",         // Product ID (hex string)
    "name": "PacDrive 2000T", // Human-readable name
    "detected": false,        // Whether board was detected at runtime
    "modes": {
      "twinstick": false,     // Twin-stick mode enabled
      "turbo": false,         // Turbo button enabled
      "six_button": false,    // 6-button layout
      "interlock": true       // Input interlock active
    }
  },
  
  "mappings": {
    "p1.coin":    { "pin": 1,  "type": "button",   "label": "P1 Coin" },
    "p1.start":   { "pin": 2,  "type": "button",   "label": "P1 Start" },
    "p1.button1": { "pin": 8,  "type": "button",   "label": "P1 Button 1" },
    "p1.up":      { "pin": 10, "type": "joystick", "label": "P1 Up" },
    // ... patterns for all P1-P4 controls
  }
}
```

---

## Control Key Format

```
p{player}.{control_name}
```

| Pattern | Examples | Type |
|---------|----------|------|
| `p1.up`, `p1.down`, `p1.left`, `p1.right` | Directions | `joystick` |
| `p1.button1` through `p1.button8` | Action buttons | `button` |
| `p1.start`, `p1.coin` | Service buttons | `button` |

---

## Pin Allocation (4-Player Cabinet)

| Player | Pin Range | Controls |
|--------|-----------|----------|
| P1 | 1-17 | Coin, Start, Buttons 1-8, UDLR |
| P2 | 18-31 | Coin, Start, Buttons 1-8, UDLR |
| P3 | 32-41 | Coin, Start, Buttons 1-4, UDLR |
| P4 | 42-51 | Coin, Start, Buttons 1-4, UDLR |

---

## Extended Mapping Entry (After Learn Wizard)

When the Learn Wizard captures an input, the mapping entry gains a `keycode` field:

```json
"p1.button1": {
  "pin": 8,
  "type": "button",
  "label": "P1 Button 1",
  "keycode": "BTN_0_JS0"  // Added by Learn Wizard
}
```

This `keycode` is used by `mame_config_generator.py` to produce:
- **XInput mode:** `JOYCODE_1_BUTTON1`
- **Keyboard mode:** `KEYCODE_LCONTROL`

---

## Safety Invariants

1. **Factory Default:** The file `factory-default.json` is the rollback point - never modify
2. **Backup on Write:** All changes via `/mapping/apply` create timestamped backups
3. **Schema Validation:** Pydantic validates structure before any write
