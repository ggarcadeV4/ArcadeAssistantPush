# Controller Chuck - Domain Knowledge Base
> Factory baseline. Ships on every Golden Drive.

## Encoder Boards

### Ultimarc I-PAC Series
- **I-PAC 2**: 32 inputs, active-low with internal pull-ups. USB HID keyboard by default.
  - VID: `0xD209` PID: `0x0301` (I-PAC 2), `0x0501` (I-PAC 4)
  - Firmware update via WinIPAC utility. Firmware v1.60+ supports analog axes.
  - **Quirk:** Default key assignments use legacy MAME mappings. Must remap via WinIPAC or controls.json for modern cabinets.
  - Ground daisy-chains allowed - all buttons share a common ground rail.
  - LED header (I-PAC Ultimate I/O only): directly drives LEDs via LEDWIZ protocol.
- **I-PAC Ultimate I/O**: 96 inputs + 96 LED outputs. Replaces I-PAC + LED-Wiz combo.
  - Same VID, PID `0x0801`. Use IPAC_LED protocol for LED control.

### Xin-Mo Dual USB Encoder
- **XM-10**: 2-player, 24 inputs total (12 per player). USB HID gamepad (NOT keyboard).
  - VID: `0x16C0` PID: `0x05E1`
  - **Critical quirk:** Reports as two separate gamepads. Player 1 = first ~12 inputs, Player 2 = next 12.
  - No onboard firmware update - what ships is what you get.
  - Common failure mode: **phantom inputs** from poor ground connections. Fix: re-solder or replace JST connectors.
  - **DirectInput only** - does NOT appear as XInput. Use x360ce or Steam Input for XInput games.

### Zero Delay USB Encoder
- **Generic Zero Delay**: ~12 inputs per board. USB HID. Cheapest option.
  - VID/PID varies by manufacturer. Common: `0x0079:0x0006` or `0x0810:0x0001`.
  - **Quirk:** Some boards report as a single device with combined axes. Others as keyboard.
  - Ground pin is shared across all inputs. Wiring: one wire per button + one common ground.
  - Do NOT use for 4-player cabinets - get an I-PAC 4 instead.

---

## MAME Input Configuration

### File Hierarchy (precedence, low -> high)
1. **Compiled defaults** - MAME's internal fallback (hardcoded)
2. `cfg/default.cfg` - Global overrides for ALL games
3. `cfg/{romname}.cfg` - Per-game overrides (highest priority)
4. `-ctrlr {name}` flag - Loads `ctrlr/{name}.cfg` BEFORE default.cfg

### default.cfg Structure
```xml
<mameconfig version="10">
  <system name="default">
    <input>
      <port type="P1_JOYSTICK_UP">
        <newseq type="standard">KEYCODE_UP</newseq>
      </port>
      <port type="P1_BUTTON1">
        <newseq type="standard">KEYCODE_LCONTROL</newseq>
      </port>
    </input>
  </system>
</mameconfig>
```

### Key MAME Input Names
| Control | MAME Port Type | Default Key |
|---------|----------------|-------------|
| P1 Up | P1_JOYSTICK_UP | KEYCODE_UP |
| P1 Down | P1_JOYSTICK_DOWN | KEYCODE_DOWN |
| P1 Left | P1_JOYSTICK_LEFT | KEYCODE_LEFT |
| P1 Right | P1_JOYSTICK_RIGHT | KEYCODE_RIGHT |
| P1 Button 1 | P1_BUTTON1 | KEYCODE_LCONTROL |
| P1 Button 2 | P1_BUTTON2 | KEYCODE_LALT |
| P1 Button 3 | P1_BUTTON3 | KEYCODE_SPACE |
| P1 Start | P1_START | KEYCODE_1 |
| P1 Coin | COIN1 | KEYCODE_5 |
| P2 Button 1 | P2_BUTTON1 | KEYCODE_A |

### -ctrlr Flag Usage
```bash
mame.exe sf2 -ctrlr arcade_cabinet
# Loads ctrlr/arcade_cabinet.cfg, then cfg/default.cfg, then cfg/sf2.cfg
```

## RetroArch Joypad Autoconfig

### How It Works
1. RetroArch detects a gamepad via its VID:PID.
2. Looks for a matching `.cfg` in `autoconfig/` directory.
3. If found, maps buttons automatically. If not, prompts manual mapping.

### retroarch.cfg Key Settings
```ini
input_autodetect_enable = "true"              # Enable autoconfig
input_joypad_driver = "dinput"                # Windows: dinput or xinput
input_player1_joypad_index = "0"              # Which gamepad for P1
input_player1_a_btn = "1"                     # A button = gamepad button 1
input_player1_b_btn = "0"                     # B button = gamepad button 0
```

### Autoconfig File Format (autoconfig/{device_name}.cfg)
```ini
input_device = "Ultimarc I-PAC 2"
input_driver = "dinput"
input_device_display_name = "I-PAC 2 Arcade Encoder"
input_b_btn = "0"
input_a_btn = "1"
input_start_btn = "9"
input_select_btn = "8"
```

## Troubleshooting: XInput vs. DirectInput

### The Conflict
- DirectInput (DInput): Legacy API. Supports any HID device. No rumble standardization.
- XInput: Xbox controller standard. Only supports Xbox-layout controllers. Rumble standardized.
- Most encoder boards are DirectInput-only. XInput games may not see them.

### Symptoms
| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Ghost inputs (buttons press themselves) | Floating ground pin | Re-solder ground wire, check JST connectors |
| Reversed Y-axis | DInput vs XInput axis convention | Invert axis in MAME/RetroArch config |
| Controller not detected in game | Game requires XInput | Use x360ce or Steam Input wrapper |
| Two players swapped | Gamepad index wrong | Change input_player1_joypad_index in retroarch.cfg |
| Buttons work but stick doesn't | Stick wired to wrong pins | Check pin assignments - sticks use 4 pins (U/D/L/R) |
| Intermittent disconnects | Bad USB cable or hub | Use direct USB port, not a hub. Try USB 2.0 port |

### x360ce Setup (DInput -> XInput bridge)
1. Download x360ce from github.com/x360ce
2. Place `x360ce.exe` + `xinput1_3.dll` in the game's folder
3. Run x360ce, map your DInput device to Xbox layout
4. Save - the DLL intercepts XInput calls and redirects to DInput

## Sacred Button Law (G&G Arcade Standard)
- P1/P2 (6-button): Top row = Buttons 1, 2, 3, 7 | Bottom row = Buttons 4, 5, 6, 8
- P3/P4 (4-button): Top row = Buttons 1, 2 | Bottom row = Buttons 3, 4
- This layout is NON-NEGOTIABLE for G&G cabinets. All mappings must respect it.
