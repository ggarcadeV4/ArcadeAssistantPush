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

### GP-Wiz 49 / GP-Wiz 40 (GroovyGameGear)
- **GP-Wiz family**: GroovyGameGear input-only encoder boards. Standard USB HID joystick/gamepad devices - NOT keyboard encoders and NOT LED controllers.
  - VID/PID: `0xFAFA:0x00F7`
  - Some firmware revisions also enumerate under VID `0xD209`; treat the PID + product string as the authoritative identity.
  - **Variant split:** GP-Wiz 49 exposes 49 logical inputs. GP-Wiz 40 exposes 40 logical inputs. Same operating model, different input count.
- **Windows presentation**:
  - Usually appears as `GP-Wiz49`, `GP-Wiz40`, or a generic HID-compliant game controller in Device Manager and `joy.cpl`.
  - HID descriptor is standard joystick/gamepad style, so Windows treats it as a DirectInput-style USB game controller with sequential button numbers.
- **Button numbering and MAME mapping**:
  - Windows numbers inputs sequentially as Button 1, Button 2, Button 3, etc.
  - In MAME these appear as `JOYCODE_1_BUTTON1`, `JOYCODE_1_BUTTON2`, `JOYCODE_1_BUTTON3`, and so on.
  - Chuck must translate those button numbers into cabinet roles such as `P1_BUTTON1`, `P1_BUTTON2`, `P1_START`, `COIN1`, etc. through `controls.json`, not by assuming keyboard keycodes.
  - Directionals still map as joystick directions (`P1_JOYSTICK_UP`, `P1_JOYSTICK_DOWN`, `P1_JOYSTICK_LEFT`, `P1_JOYSTICK_RIGHT`) rather than button codes.
- **RetroArch autoconfig**:
  - RetroArch may catch GP-Wiz automatically if the exact device name and VID/PID already exist in `autoconfig/`.
  - If no exact profile exists, build a manual `.cfg` using the detected device name plus the correct button indices.
  - Treat GP-Wiz as a HID/DInput joystick profile, not an XInput pad and not a keyboard encoder.
- **Critical quirk - do not confuse with LED-Wiz**:
  - GP-Wiz and LED-Wiz both come from GroovyGameGear and can share vendor-space history.
  - **LED-Wiz = LED control only. GP-Wiz = input only.**
  - Same family, different job. Different PIDs. If the board is answering as an input device in `joy.cpl`, it is not an LED-Wiz problem.
- **Controller Cascade integration**:
  - On detection, `controls.json` should at minimum reflect `board.vid`, `board.pid`, `board.name`, and `board.detected`.
  - Input assignments still live under `mappings.*` with `pin`, `type`, and `label`.
  - Chuck should classify GP-Wiz as a HID joystick encoder and populate the cabinet mapping summary from button numbers, not from keyboard scancodes.
- **Troubleshooting**:
  - Check Device Manager under **Human Interface Devices** and **Sound, video and game controllers** for a GP-Wiz or HID game controller entry.
  - Open `joy.cpl` and verify button presses increment on the correct button numbers.
  - If Windows sees only an LED-Wiz or no game controller entry at all, verify VID/PID with USBView or Device Manager Details -> Hardware Ids.
  - If detection fails entirely, reseat the USB cable, avoid passive hubs, and confirm the board is enumerating as a HID-compliant game controller.

### Brook Universal Fighting Board (UFB)
- **Brook UFB**: common aftermarket fight-stick encoder in the FGC. Multi-console board that changes how it presents to Windows depending on the active mode.
  - VID: `0x0C12`
  - On PC, Brook recommends `XB 360` mode for the most compatible Windows/XInput presentation.
- **Dual-mode behavior**:
  - XInput mode is the normal PC-friendly path and commonly shows up in Windows as `Xbox 360 Controller`.
  - DirectInput mode is the legacy HID joystick path.
  - This matters because **MAME defaults to DirectInput-style controller enumeration**, while **RetroArch usually behaves best with XInput** on Windows.
  - If the active emulator changes, the operator may need to reconnect the board in the correct mode.
  - Older shop shorthand sometimes describes the PC mode toggle as holding **Select+Start** at connect. Current Brook documentation emphasizes explicit manual mode selection instead. If behavior is inconsistent, force the mode deliberately rather than guessing.
- **Console/manual mode switching**:
  - Brook UFB supports console-mode switching at connect time, and the chosen mode is remembered by firmware.
  - On the official Brook manual selection chart:
    - `1P` = PS3
    - `2P` = PS4
    - `3P` = Xbox 360
    - `4P` = Xbox One
    - `1K` = Wii U / Switch
    - `2K` = Original Xbox
    - `3K` = NeoGeo Mini
  - Changing console mode changes how the board identifies to Windows. Chuck should warn operators that a board which suddenly looks different after reconnect is often just in the wrong console mode, not dead.
- **Known Windows behavior**:
  - In XInput mode, Windows often reports the board as `Xbox 360 Controller`.
  - That is correct Brook behavior, not a detection failure.
  - In DirectInput mode, Windows may show `Brook Universal Fighting Board` or a generic HID game controller name.
- **Button layout and MAME equivalents**:
  - Standard 8-button Noir layout on many Brook fight sticks:
    - Top row: `Y`, `R1`, `L1`, `L2`
    - Bottom row: `B`, `A`, `R2`, `L3`
  - For G&G cabinet normalization under the Sacred Button Law:
    - `Y` -> `P1_BUTTON1`
    - `R1` -> `P1_BUTTON2`
    - `L1` -> `P1_BUTTON3`
    - `L2` -> `P1_BUTTON7`
    - `B` -> `P1_BUTTON4`
    - `A` -> `P1_BUTTON5`
    - `R2` -> `P1_BUTTON6`
    - `L3` -> `P1_BUTTON8`
  - If the stick wiring does not match the silk-screened Brook harness order, trust continuity testing over label assumptions.
- **RetroArch autoconfig**:
  - RetroArch usually ships a Brook profile, but the operator should verify that a `Brook Universal Fighting Board` autoconfig file actually exists before building a manual mapping.
  - If the board is in XInput mode and Windows presents it as `Xbox 360 Controller`, RetroArch may bind the stock Xbox 360 autoconfig instead of a Brook-named file. That is normal.
- **Firmware update behavior**:
  - Brook firmware tools can change the board's presentation mode and, in some cases, the effective VID/PID signature exposed to Windows.
  - If Chuck cannot match the board cleanly, always ask whether firmware was updated recently.
  - If the board enters Brook firmware-transfer mode instead of controller mode, finish the firmware cycle and reconnect in the intended PC mode.
- **Controller Cascade behavior**:
  - In XInput mode, Brook UFB should follow the XInput mapping profile.
  - In DirectInput mode, it should follow the HID joystick profile.
  - Chuck should never diagnose a Brook board from the connector labels alone - always confirm the live Windows mode first.

### Ultimarc ServoStik
- **ServoStik**: motorized joystick which physically rotates its restrictor plate between 4-way and 8-way operation. It is not just a joystick - it is a joystick plus a separate USB control path.
  - Ultimarc family VID: `0xD209`
  - The joystick input side enumerates as a standard HID joystick.
  - The servo control side enumerates as a separate Ultimarc HID interface with a different PID from the joystick input side. Record the exact control-interface PID from Device Manager or USBView during install; do not assume it matches the joystick PID.
- **Two USB personalities**:
  - **Input personality**: standard joystick input seen by Windows/MAME/RetroArch.
  - **Control personality**: HID output-report target used to command the servo motor to rotate the restrictor.
  - Chuck must treat these as two related devices with different jobs.
- **4-way vs 8-way operation**:
  - In 4-way mode, the restrictor physically blocks diagonals for games such as Pac-Man, Donkey Kong, and other classic maze/platform titles.
  - In 8-way mode, diagonals are physically allowed for fighters, beat-'em-ups, shooters, and most modern arcade control schemes.
  - The MAME control profile must match the physical mode. A cabinet set to 4-way while MAME expects 8-way will feel broken even when the encoder is healthy.
- **Mode-switch command**:
  - ServoStik switching is done through a HID output report.
  - Command byte `0x00` = 4-way mode
  - Command byte `0x01` = 8-way mode
  - MAME can launch an external helper script before or during game start to issue that one-byte command to the ServoStik control interface.
- **Integration with launch-time control logic**:
  - The Controller Cascade should keep the joystick mapping stable, then let launch-time game logic decide whether the restrictor should be 4-way or 8-way.
  - `game_lifecycle.py` or equivalent launch hooks can use genre tags and cabinet logic to choose the mode:
    - classic maze / puzzle / early 4-way titles -> `0x00`
    - fighters / brawlers / most 8-way titles -> `0x01`
  - Example rule of thumb: `LED:FIGHTING` style tags imply 8-way. Classic maze/puzzle tags often imply 4-way.
- **Operational safety**:
  - Chuck should never issue a servo command unless the cabinet is confirmed to have a ServoStik installed.
  - Sending a servo command to a non-ServoStik Ultimarc device is usually harmless, but it creates noisy diagnostics and confuses the operator.
- **Troubleshooting**:
  - If the joystick works but the restrictor never rotates, check for the second HID control device in Device Manager - not just the joystick entry.
  - If the servo motor does not respond, make sure **WinIPAC** is not already holding the USB control interface open.
  - If commands are being sent but the stick stays in the wrong mode, verify power to the servo hardware and confirm the helper script is talking to the control interface, not the joystick interface.
  - If MAME behavior is wrong only on certain titles, check that the launch script, `-ctrlr` profile, and physical restrictor mode all agree.

### Ultimarc U-Trak / SpinTrak
- **U-Trak and SpinTrak**: analog motion devices, not digital button encoders.
  - Ultimarc family VID: `0xD209`
  - Product IDs vary by the attached interface/control board; verify the exact PID in Device Manager or USBView when documenting the cabinet.
  - **U-Trak** presents analog X/Y movement for trackball use.
  - **SpinTrak** presents a single analog rotary axis for spinner use.
- **Windows presentation**:
  - U-Trak commonly appears as a HID joystick-style or mouse-style analog device with X/Y movement.
  - SpinTrak appears as a single-axis analog spinner input.
  - These are not regular digital buttons. If Chuck diagnoses them like pushbuttons, the fix will be wrong.
- **MAME requirements**:
  - Trackball titles such as Missile Command, Centipede, and Golden Tee must use analog input handling, not button mappings.
  - Spinner titles such as Tempest, Arkanoid, and Breakout also require analog handling.
  - In MAME configs, these belong in analog input sections, not the standard button-map section.
  - Critical route hint:
    ```xml
    <mapdevice device="U-Trak Trackball" controller="mouse"/>
    ```
  - Without that mapping, MAME may not route trackball movement to the proper in-game axis.
- **Sensitivity tuning**:
  - Both U-Trak and SpinTrak use hardware DIP-switch sensitivity options.
  - If motion feels too slow or too fast, check the hardware DIP settings first.
  - Software sensitivity should be the second step, not the first.
- **RetroArch behavior**:
  - Trackball and spinner input should use the `mouse` input driver path, not `joypad`.
  - The active core must also support analog mouse input. Not all RetroArch cores do.
  - If the core ignores movement entirely, verify both the RetroArch input driver and the core's mouse/analog support before blaming the encoder.
- **Known conflict**:
  - If a joystick and a trackball/spinner are both connected, Windows can produce axis conflicts.
  - U-Trak should be the only device assigned to relative X/Y mouse-style movement for trackball titles.
  - If joystick axes are interfering, remap the non-trackball device with Ultimarc utilities so the analog movement source stays unambiguous.
- **Controller Cascade behavior**:
  - When U-Trak or SpinTrak is detected, the cascade must generate an **analog-mode** MAME config section instead of the normal button-mapping section.
  - Chuck should treat these devices as analog specialists and preserve separate button mappings for the rest of the panel.
- **Troubleshooting**:
  - Verify Windows sees motion live before touching MAME. If the cursor/test panel never moves, it is a device-level issue.
  - Confirm the correct `mapdevice` entry exists in the MAME config for the analog device name actually reported by Windows.
  - If motion exists in Windows but not in RetroArch, check that RetroArch is using the `mouse` input driver and that the core supports analog mouse input.
