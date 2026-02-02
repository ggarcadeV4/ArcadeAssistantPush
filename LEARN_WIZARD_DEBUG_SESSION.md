# Learn Wizard Input Detection - Session Summary
**Date:** December 19, 2024
**Status:** IN PROGRESS - D-pad input not registering in wizard despite backend detection working

---

## The Problem
The Learn Wizard prompts user to "press UP" but when UP is pressed on the arcade encoder, **nothing happens**. The wizard does not advance, Chuck doesn't speak the next prompt, and the UI doesn't update.

---

## What We Discovered

### 1. Encoder Hardware Setup
- **Encoder type:** PactoTech encoder (operating in XInput/Xbox 360 mode)
- **pygame sees:** 2 Xbox 360 Controllers (joystick index 0 and 1)
- **User's encoder is:** Joystick index **1** (not 0)
- **D-pad type:** HAT (not axis, not button)

### 2. Raw Event Dump Proof
We ran `dump_joy_events.py` and confirmed pygame DOES see the inputs:
```
JOYHATMOTION: joy=1 hat=0 value=(0, 1)   ← This is D-pad UP
JOYHATMOTION: joy=1 hat=0 value=(0, -1)  ← D-pad DOWN
JOYHATMOTION: joy=1 hat=0 value=(-1, 0)  ← D-pad LEFT
JOYHATMOTION: joy=1 hat=0 value=(1, 0)   ← D-pad RIGHT
```

### 3. The 500 Error Root Cause
The initial 500 error was caused by **emoji characters (✅❌)** in Python print statements:
- Windows console uses cp1252 encoding which can't handle Unicode emojis
- Error message: `'charmap' codec can't encode character '\u2705'`
- **Fixed by:** Removing emojis from `input_detector.py` lines 143, 151 and `controller.py` lines 1048, 1075

### 4. Missing HAT Detection
The original `input_detector.py` only checked:
- Buttons (`get_button()`)
- Axes (`get_axis()`)

It did NOT check:
- **HATs (`get_hat()`)** ← This is what D-pads use on Xbox controllers!

**Fixed by:** Adding HAT polling loop that now emits `DPAD_UP_JS1`, `DPAD_DOWN_JS1`, etc.

---

## Changes Made This Session

### File: `backend/services/chuck/input_detector.py`
1. Removed emoji from print statements (lines 143, 151)
2. Added `prev_hats` tracking in gamepad loop initialization
3. Added HAT polling loop after axes check (detects D-pad as `DPAD_UP_JS{n}`, `DPAD_DOWN_JS{n}`, etc.)

### File: `backend/routers/controller.py`
1. Removed emoji from code comments (lines 1048, 1075)

### File: `frontend/src/hooks/useLearnWizard.js`
1. Rewrote to poll backend `/learn-wizard/status` instead of using browser gamepad API
2. Added console logging: `console.log('[LearnWizard] Poll response:', data);`

### File: `.env`
1. Added `DEBUG=true` to show real error messages instead of generic "An error occurred"

### New Files Created:
- `backend_diag.py` - Diagnostic script checking Python/pygame/admin/A: drive
- `dump_joy_events.py` - Raw pygame event dump for debugging

---

## Current Known Issues

### Issue 1: D-pad UP Still Not Registering in Wizard
**Symptom:** User presses UP, wizard does not advance, Chuck says nothing
**Suspected causes:**
- The new HAT detection code may not be running (backend not restarted?)
- Frontend polling may not be receiving `captured_key` from backend
- Possible issue with how `_learn_mode_latest_key` is being set from gamepad events

**To debug:**
1. Restart backend and watch console for `[InputDetector] Gamepad HAT/D-pad: DPAD_UP_JS1`
2. Check browser console for `[LearnWizard] Poll response:` - does it contain `captured_key`?

### Issue 2: Skip Button Causes Echo
**Symptom:** When user clicks "Skip", there's an audio echo effect
**Likely cause:** TTS being called multiple times or overlapping speech

### Issue 3: LED-Wiz Shown as Encoder (User Report)
**User said:** GUI shows "LED-Wiz Device 3 (0xfafa:0x00f2)" as the encoder
**Investigation:** Device snapshot API does NOT show LED-Wiz classified as encoder
**Status:** May be display logic issue in Controller Panel, not a data issue

---

## Architecture Understanding

### Input Detection Flow (How It SHOULD Work):
```
1. User presses D-pad UP on encoder
   ↓
2. pygame receives JOYHATMOTION event
   ↓
3. InputDetectionService._gamepad_listener_loop() polls joystick.get_hat(0)
   ↓
4. HAT changed from (0,0) to (0,1) → emit "DPAD_UP_JS1"
   ↓
5. _handle_gamepad_input() calls raw handlers
   ↓
6. capture_wizard_input() sets global _learn_mode_latest_key = "DPAD_UP_JS1"
   ↓
7. Frontend polls /learn-wizard/status every 200ms
   ↓
8. Status endpoint returns { captured_key: "DPAD_UP_JS1", ... }
   ↓
9. Frontend sees captured_key, calls /learn-wizard/confirm
   ↓
10. Backend advances wizard, frontend updates UI, Chuck speaks next control
```

### Key Files:
| File | Purpose |
|------|---------|
| `backend/services/chuck/input_detector.py` | Pygame gamepad polling loop, HAT/button/axis detection |
| `backend/routers/controller.py` | `/learn-wizard/start`, `/learn-wizard/status`, `/learn-wizard/confirm` endpoints |
| `frontend/src/hooks/useLearnWizard.js` | Frontend hook that polls backend status |
| `frontend/src/panels/controller/ControllerPanel.jsx` | Main controller panel UI |

---

## Environment Details
- **Python:** 3.11.9
- **pygame:** 2.6.1
- **Admin:** Not running as admin (may affect some device access)
- **AA_DRIVE_ROOT:** Set in `.env` as `A:\` (loads correctly via `load_env_file()` in app.py)

---

## Next Steps for Tomorrow

1. **Restart backend** and verify HAT detection prints to console
2. **Check browser DevTools Console** for poll response data
3. If `captured_key` is NOT in poll response → debug backend capture handler
4. If `captured_key` IS in poll response → debug frontend processing
5. Fix Skip button echo issue
6. Clarify LED-Wiz display confusion

---

## Diagnostic Commands

### Test pygame detection directly:
```powershell
cd "a:\Arcade Assistant Local"
python dump_joy_events.py
# Press D-pad UP - should see JOYHATMOTION: joy=1 hat=0 value=(0, 1)
```

### Check backend environment:
```powershell
python backend_diag.py
```

### Manual API test (bypass frontend):
```powershell
# Start wizard
Invoke-RestMethod -Method POST -Uri "http://localhost:8787/api/local/controller/learn-wizard/start?players=2&buttons=6" -Headers @{"x-scope"="state"}

# Check status (should show captured_key after pressing button)
Invoke-RestMethod -Uri "http://localhost:8787/api/local/controller/learn-wizard/status" -Headers @{"x-scope"="state"}
```
