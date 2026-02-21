# Player 2 Mapping Fix

## Problem
Player 2 (and all joystick directions) could not be mapped in the wizard. Controls would not be captured when pressing UP/DOWN/LEFT/RIGHT.

## Root Cause
Someone added overly aggressive AXIS filtering in [controller.py:1142-1144](backend/routers/controller.py#L1142-L1144):

```python
# BROKEN CODE (removed):
if "AXIS" in keycode:
    logger.debug(f"[LearnWizard] Ignored AXIS noise: {keycode}")
    return
```

This **blocked ALL axis inputs**, including:
- Joystick UP/DOWN/LEFT/RIGHT (sent as `AXIS_0+`, `AXIS_1-`, etc.)
- D-pad movements (sent as `DPAD_UP`, etc.)

The intent was to filter out **trigger noise** (Xbox triggers rest at -1.0 and spam events), but it accidentally blocked all joystick movement!

## Solution
Changed the filter to only block TRIGGER events, not all AXIS events:

```python
# FIXED CODE:
if "TRIGGER" in keycode:
    logger.debug(f"[LearnWizard] Ignored trigger noise: {keycode}")
    return
```

### What Gets Blocked vs Allowed

**❌ BLOCKED** (Trigger noise):
- `TRIGGER_0_JS0` - Left Xbox trigger
- `TRIGGER_1_JS0` - Right Xbox trigger

**✅ ALLOWED** (Actual controls):
- `AXIS_0+_JS0` - Joystick RIGHT
- `AXIS_0-_JS0` - Joystick LEFT
- `AXIS_1+_JS0` - Joystick DOWN
- `AXIS_1-_JS0` - Joystick UP
- `DPAD_UP_JS0` - D-pad UP
- `DPAD_DOWN_JS0` - D-pad DOWN
- `DPAD_LEFT_JS0` - D-pad LEFT
- `DPAD_RIGHT_JS0` - D-pad RIGHT
- `BTN_0_JS0` through `BTN_15_JS0` - All buttons

## Technical Details

### How Input Detection Works

The `InputDetectionService` uses pygame to detect XInput/gamepad inputs:

1. **Joystick Axes** (0-3): Regular joystick movement
   - Axis 0: Left/Right
   - Axis 1: Up/Down
   - Axis 2: Right stick Left/Right (if present)
   - Axis 3: Right stick Up/Down (if present)

2. **Trigger Axes** (4-5): Xbox triggers
   - Axis 4: Left trigger (LT)
   - Axis 5: Right trigger (RT)
   - **Problem**: Rest at -1.0, pressed moves toward +1.0
   - **Issue**: Spam events constantly at rest position

3. **Buttons** (0-15): All face/shoulder buttons
   - BTN_0 = A, BTN_1 = B, etc.

4. **HATs** (D-pad): Directional pad
   - Sent as `DPAD_UP`, `DPAD_DOWN`, etc.

### Why Triggers Are Noisy

Xbox controllers (and XInput-compatible devices like PactoTech) have analog triggers that:
- Rest at value `-1.0` (not pressed)
- Move to `+1.0` when fully pressed
- Constantly send events due to analog nature
- Can generate hundreds of events per second even when idle

The input detector correctly distinguishes triggers from joystick axes:
- [input_detector.py:298-305](backend/services/chuck/input_detector.py#L298-L305) - Trigger detection logic
- [input_detector.py:307-312](backend/services/chuck/input_detector.py#L307-L312) - Joystick axis detection logic

## Testing

### Prerequisites
1. Backend running: `npm run dev:backend`
2. PactoTech encoder connected (or Xbox controller for testing)
3. Encoder in XInput mode

### Test Steps

1. **Start the wizard**:
   ```bash
   # Frontend: Open Controller Chuck panel → Start Learn Wizard
   # OR via API:
   curl -X POST http://localhost:8888/controller/learn-wizard/start \
     -H "x-scope: state" \
     -H "x-device-id: test-device"
   ```

2. **Map Player 1 controls** (should work as before):
   - P1 UP → Should capture `AXIS_1-_JS0` or `DPAD_UP_JS0`
   - P1 DOWN → Should capture `AXIS_1+_JS0` or `DPAD_DOWN_JS0`
   - P1 LEFT → Should capture `AXIS_0-_JS0` or `DPAD_LEFT_JS0`
   - P1 RIGHT → Should capture `AXIS_0+_JS0` or `DPAD_RIGHT_JS0`
   - P1 Button 1-6 → Should capture `BTN_0_JS0` through `BTN_5_JS0`

3. **Map Player 2 controls** (previously broken, now fixed):
   - P2 UP → Should now capture (was blocked before!)
   - P2 DOWN → Should now capture
   - P2 LEFT → Should now capture
   - P2 RIGHT → Should now capture
   - P2 Buttons → Should capture

4. **Verify triggers are filtered**:
   - Backend console should NOT show spam from `TRIGGER_0_JS0` or `TRIGGER_1_JS0`
   - Only show "Ignored trigger noise" at debug level if triggers move

### Expected Console Output (Backend)

```
[LearnWizard] Started dual-mode input detection (keyboard + XInput)
[InputDetector] Initialized joystick 0: Controller (XBOX 360 For Windows)
[InputDetector] Gamepad axis: AXIS_1-_JS0
[LearnWizard] Captured input: AXIS_1-_JS0
[InputDetector] Gamepad button: BTN_0_JS0
[LearnWizard] Captured input: BTN_0_JS0
```

**NOT**:
```
[InputDetector] Gamepad trigger: TRIGGER_0_JS0
[LearnWizard] Ignored trigger noise: TRIGGER_0_JS0  # (only in debug logs)
```

## Related Issues

### "First Input Lost" Bug
There's a known issue where the first button press after wizard start is sometimes lost. This is due to pygame initialization timing:
- [input_detector.py:165-170](backend/services/chuck/input_detector.py#L165-L170) - Wait logic commented out
- **Workaround**: Press any button once to "prime" the listener, then start mapping

### D-pad vs Analog Stick
PactoTech encoders can be configured for:
- **DPAD mode**: Sends HAT events (`DPAD_UP_JS0`, etc.)
- **ANA-F/ANA-S mode**: Sends AXIS events (`AXIS_0+_JS0`, etc.)

Both modes now work correctly - the wizard captures whichever the encoder sends!

## Files Changed
- [backend/routers/controller.py](backend/routers/controller.py#L1140-1149) - Fixed AXIS filtering logic

## Related Documentation
- [WIZARD_AUTO_DETECT_FIX.md](WIZARD_AUTO_DETECT_FIX.md) - Original auto-detection implementation
- [backend/profiles/controller_chuck/pactotech.json](backend/profiles/controller_chuck/pactotech.json) - PactoTech board modes
- [backend/services/chuck/input_detector.py](backend/services/chuck/input_detector.py) - Dual-mode input detection

---

**Status**: ✅ Fixed - Player 2 (and all joystick directions) can now be mapped
**Date**: 2025-12-19
**Fix**: Changed `if "AXIS" in keycode` to `if "TRIGGER" in keycode`
