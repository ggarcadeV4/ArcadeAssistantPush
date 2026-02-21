# Learn Wizard Auto-Detection Fix

## Problem
The learn wizard was asking users to **manually type** the keycode instead of automatically detecting controller inputs. This happened because someone previously disabled the automatic detection to avoid Windows admin privilege issues.

## Root Cause
In [controller.py:1048-1050](backend/routers/controller.py#L1048-L1050), there was a comment saying:
```python
# NOTE: We're NOT starting the pynput listener anymore.
# The wizard uses manual keycode entry - user types the key they see in Notepad.
# This avoids Windows admin privilege issues and encoder mode detection problems.
```

**BUT** the codebase already had working dual-mode input detection (keyboard + XInput) that just wasn't being used!

## Solution
Re-enabled the existing `InputDetectionService` with dual-mode listening (keyboard + gamepad/XInput) for the learn wizard.

### Changes Made

#### 1. **Auto-Detect Connected Encoder Boards** ([controller.py:1048-1073](backend/routers/controller.py#L1048-L1073))
- Detects PactoTech, Ultimarc, and other arcade boards via USB VID/PID
- Automatically determines input mode:
  - **PactoTech boards** → XInput mode (default for 2000T/4000T)
  - **Ultimarc I-PAC** → Keyboard mode
  - **Unknown boards** → Dual-mode listening

#### 2. **Start Dual-Mode Input Detection** ([controller.py:1075-1092](backend/routers/controller.py#L1075-L1092))
- Enables `InputDetectionService` in learn mode
- Registers wizard-specific capture handler
- Starts listening for **both keyboard AND XInput gamepad** inputs simultaneously
- Uses existing `pynput` (keyboard) + `pygame` (gamepad) listeners

#### 3. **Improved User Prompts** ([controller.py:1098-1120](backend/routers/controller.py#L1098-L1120))
- Tells user what board was detected
- Explains what mode the encoder is in
- Instructs user to "just press the button" instead of typing

#### 4. **Cleanup Listeners on Stop/Save**
- [controller.py:1362-1368](backend/routers/controller.py#L1362-L1368) - Stop after save
- [controller.py:1427-1432](backend/routers/controller.py#L1427-L1432) - Stop on wizard cancel

## How It Works

### Detection Flow
```
1. User starts wizard → POST /controller/learn-wizard/start
2. Backend detects USB devices → finds PactoTech 2000T
3. Backend knows PactoTech uses XInput → sets detected_mode = "xinput"
4. Backend starts dual-mode listeners:
   - pynput keyboard listener (background thread)
   - pygame gamepad listener (background thread polling at 100Hz)
5. User presses UP on encoder → encoder sends XInput axis event
6. pygame detects AXIS_1- movement → calls capture_wizard_input("AXIS_1-_JS0")
7. Frontend polls /learn-wizard/status → gets captured keycode
8. Wizard advances to next control
```

### What Gets Detected
- **Keyboard inputs**: Arrow keys, WASD, function keys, etc.
- **XInput gamepad inputs**:
  - Buttons: BTN_0_JS0, BTN_1_JS0, etc.
  - Axes: AXIS_0+_JS0 (right), AXIS_0-_JS0 (left), AXIS_1+_JS0 (down), AXIS_1-_JS0 (up)
  - D-pad: Usually maps to axis or hat inputs

### Supported Boards
| Vendor | Board | VID:PID | Mode | Detection |
|--------|-------|---------|------|-----------|
| PactoTech | 2000T/4000T | 0d62:0001/0002 | XInput | Auto-detected ✅ |
| Ultimarc | I-PAC2/I-PAC4 | d209:0501/0502 | Keyboard | Auto-detected ✅ |
| Brook | Universal Fighting Board | 0c12:0ef8 | XInput | Auto-detected ✅ |

## Testing Instructions

### Prerequisites
1. Backend must be running: `npm run dev:backend`
2. PactoTech encoder connected via USB
3. Encoder in XInput mode (default for PactoTech)

### Test Steps
1. **Start the wizard**:
   ```bash
   # Via frontend UI: Click "Start Learn Wizard" in Controller Chuck panel
   # OR via API:
   curl -X POST http://localhost:8888/controller/learn-wizard/start \
     -H "x-scope: state" \
     -H "x-device-id: test-device"
   ```

2. **Check the response** - should include:
   ```json
   {
     "status": "started",
     "detected_board": "Paxco Tech 4000T",
     "detected_mode": "xinput",
     "dual_mode_enabled": true,
     "chuck_prompt": "I detected your Paxco Tech 4000T in XInput mode! Just press Player 1 Up on your controller and I'll capture it automatically."
   }
   ```

3. **Press UP on your encoder** → Should see in backend logs:
   ```
   [InputDetector] ✅ KEYBOARD LISTENER STARTED for generic
   [InputDetector] Started gamepad listener for generic (1 gamepads)
   [InputDetector] Initialized joystick 0: Controller (XBOX 360 For Windows)
   [InputDetector] Gamepad axis: AXIS_1-_JS0
   [LearnWizard] Captured input: AXIS_1-_JS0
   ```

4. **Poll wizard status**:
   ```bash
   curl http://localhost:8888/controller/learn-wizard/status \
     -H "x-scope: state"
   ```
   Should return:
   ```json
   {
     "status": "waiting",
     "captured_key": "AXIS_1-_JS0",
     "current_control": "p1.up"
   }
   ```

5. **Continue pressing buttons** → Wizard should advance automatically

### Expected Console Output (Backend)
```
[LearnWizard] Detected Paxco Tech 4000T - using XInput mode
[InputDetector] ✅ KEYBOARD LISTENER STARTED for generic
[InputDetector] Started gamepad listener for generic (1 gamepads)
[InputDetector] Initialized joystick 0: Controller (XBOX 360 For Windows)
[LearnWizard] Started dual-mode input detection (keyboard + XInput)
[InputDetector] Gamepad button: BTN_0_JS0
[LearnWizard] Captured input: BTN_0_JS0
```

## Troubleshooting

### "No gamepads detected" (pygame shows 0 gamepads)
**Cause**: Encoder is in keyboard mode, not XInput mode

**Fix**:
1. Check PactoTech mode pins or button combinations
2. See [pactotech.json](backend/profiles/controller_chuck/pactotech.json) for mode switching instructions
3. Default is XInput - check if jumpers were changed

### "Learn mode not capturing anything"
**Cause 1**: Backend not running
- Check: `curl http://localhost:8888/health`

**Cause 2**: pynput or pygame not installed
- Check backend logs for: `[InputDetector] ❌ pynput not installed`
- Fix: `pip install pynput pygame`

**Cause 3**: Windows permissions (rare - only for keyboard mode)
- pynput may need admin privileges on some Windows setups
- XInput (gamepad) doesn't have this issue

### "Captured wrong axis/button"
**Expected behavior** - different encoders map differently:
- PactoTech: Usually AXIS_0/AXIS_1 for joystick, BTN_0-7 for buttons
- Ultimarc: Keyboard codes (Up, Down, Left_Ctrl, etc.)

The wizard saves whatever it captures - that's the correct mapping!

## Architecture Notes

### Why Dual-Mode Listening?
PactoTech boards can be in:
- **XInput mode** (default) - shows as Xbox 360 controller
- **Keyboard mode** (via DIS pin or jumper) - sends keyboard scancodes

By listening to **both simultaneously**, we don't care which mode the encoder is in - we just capture whatever it sends!

### Performance
- Keyboard listener: Event-driven (zero CPU when idle)
- Gamepad listener: Polls at 100Hz (0.01s sleep) - minimal CPU usage
- Both run in background threads - non-blocking

### Dependencies
- `pynput` - Keyboard input capture (cross-platform)
- `pygame` - Gamepad/joystick detection (XInput on Windows, /dev/input on Linux)
- Both are already installed (see `backend/requirements.txt`)

## Related Files
- [backend/routers/controller.py](backend/routers/controller.py) - Wizard endpoints
- [backend/services/chuck/input_detector.py](backend/services/chuck/input_detector.py) - Dual-mode listener
- [backend/services/usb_detector.py](backend/services/usb_detector.py) - USB board detection
- [backend/profiles/controller_chuck/pactotech.json](backend/profiles/controller_chuck/pactotech.json) - PactoTech board profiles

## Next Steps
1. **Test with your actual PactoTech encoder** - see if it captures XInput events
2. **Check frontend polling** - ensure UI is calling `/learn-wizard/status` to get captured keys
3. **Verify auto-advance** - if `auto_advance=true`, wizard should move to next control automatically

---

**Status**: ✅ Backend changes complete, ready for testing
**Date**: 2025-12-19
