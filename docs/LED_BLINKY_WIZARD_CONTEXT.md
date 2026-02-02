# LED Blinky Wizard - Implementation Context

## Overview

A **declaration-based wizard** for mapping physical button LEDs to LEDWiz/LED Blinky outputs. Works the same way as Controller Chuck's Learn Wizard but for LEDs instead of keycodes.

---

## Why This Is Needed

### The Problem: Independent Wiring

```
ENCODER BOARD                     LEDWIZ BOARD
┌─────────────────────┐          ┌─────────────────────┐
│ P1 Button 1 → Pin 5 │          │ P1 Button 1 LED → ? │
│ P1 Button 2 → Pin 8 │          │ P1 Button 2 LED → ? │
└─────────────────────┘          └─────────────────────┘
       ↓                                ↓
  Sends KEY_F5                    Output 3? Output 7?
```

**The encoder board and LEDWiz board are wired independently.**
- Button 1 might send `KEY_F5` (encoder)
- But Button 1's LED might be on LEDWiz Output 7

Cascade logic cannot assume alignment. Each board must be mapped separately.

---

## Wizard Flow

### Step 1: Start Wizard
```
POST /led-blinky/learn-wizard/start?players=2&buttons=6
```

### Step 2: AI Flashes LED, User Identifies
```
AI: "I'm flashing LED Output 1. Which button is this?"
    → LEDWiz Output 1 flashes

User sees physical LED light up
    → "That's Player 1 Button 3!"

User can either:
  a) Press that button (if encoder is mapped)
  b) Use GUI to select "P1 Button 3"
  c) Voice command: "That's Player 1 Button 3"
```

### Step 3: System Records Mapping
```json
{
  "p1.button3": {"led_output": 1, "led_board": 0}
}
```

### Step 4: Repeat for All Outputs
Continue until all LED outputs are mapped to controls.

### Step 5: Save
Save LED mappings to LED Blinky configuration.

---

## Controls That Need LED Mapping

| Control | LED Mapping |
|---------|-------------|
| p1.button1-10 | ✅ Yes |
| p1.start | ✅ Yes |
| p1.coin | ✅ Yes |
| p1.up/down/left/right | ❌ No (no LEDs) |
| p2.* | Same pattern |
| p3.*, p4.* | Same pattern |

---

## API Endpoints (To Be Built)

| Endpoint | Description |
|----------|-------------|
| `POST /led-blinky/learn-wizard/start` | Start wizard with params |
| `GET /led-blinky/learn-wizard/status` | Get current LED being mapped |
| `POST /led-blinky/learn-wizard/identify` | User identifies which control the LED belongs to |
| `POST /led-blinky/learn-wizard/skip` | Skip this LED output |
| `POST /led-blinky/learn-wizard/undo` | Go back one step |
| `POST /led-blinky/learn-wizard/save` | Save mappings |
| `POST /led-blinky/learn-wizard/stop` | Cancel wizard |

---

## Backend Requirements

### 1. LED Output Control
Need ability to:
- Flash a specific LED output on the LEDWiz board
- Control brightness/color if RGB
- Turn off LED after identification

### 2. LED Board Detection
- Detect connected LEDWiz/LedWiz32/LedBlinky boards
- Know how many outputs each board has (typically 32)

### 3. Configuration Storage
- Save LED mappings to LED Blinky configuration files
- Support multiple LED boards if present

---

## Integration with Controller Chuck

### Shared Data
- Both wizards map to the same logical controls (p1.button1, etc.)
- Controller Chuck: control → keycode
- LED Blinky: control → led_output

### Combined Configuration
After both wizards complete:
```json
{
  "p1.button1": {
    "keycode": "KEY_F5",      // From Controller Chuck
    "led_output": 3,          // From LED Blinky Wizard
    "led_board": 0
  }
}
```

### Visual Feedback During Controller Wizard
Once LED mapping is known, Controller Chuck wizard CAN flash LEDs:
```
"Which button is P1 Button 1? Press it now."
     ↓
Flash LED for P1 Button 1 (if mapping known)
```

---

## Control-LED Synchronization (Important!)

### Core Principle
**LEDs must always match the active control layout.**

When a custom control layout is applied (e.g., "use row 1 for shmups"), 
the LED configuration must update to light up the new active buttons.

### Example
```
Default layout:     Shmups use buttons 4, 5, 6 → LEDs 4, 5, 6 light up
Custom layout:      Shmups use buttons 1, 2, 3 → LEDs 1, 2, 3 light up
```

### Why This Matters
- Maintains "magical" arcade experience
- Player sees exactly which buttons to use
- No confusion between lit buttons and actual controls

### Implementation
When Chuck generates a custom control config:
1. Update MAME per-game config (control layout)
2. Update LED Blinky config (which buttons light up)
3. Both configs stay in sync

### User Guidance
```
"I've set up your custom button layout. The LEDs will now light up 
the correct buttons for this game, so you'll always know which 
ones are active."
```

## Files to Modify/Create

### Backend
- `backend/routers/led.py` or new `led_blinky.py` - Wizard endpoints
- `backend/services/led_blinky_wizard.py` - Wizard state management
- `backend/services/ledwiz_control.py` - Direct LEDWiz hardware control

### Frontend
- `frontend/src/panels/LEDBlinkyPanel.jsx` - Wizard UI
- `frontend/src/services/ledBlinkyClient.js` - API client functions

### Configuration
- `config/led_blinky/mappings.json` - LED output mappings

---

## Open Questions

1. **Multiple LED boards** - Some cabinets have 2+ LEDWiz boards. How to identify which board?
2. **RGB LEDs** - Do we need to handle color configuration in the wizard?
3. **LED Blinky software** - Does LED Blinky have its own config files we should update?
4. **Trackball/Spinner LEDs** - Some have illumination. Include in wizard?

---

## Related Documents

- [Controller Chuck Wizard Context](./WIZARD_LEARNING_MODE_CONTEXT.md)
- LED Blinky documentation in project docs
