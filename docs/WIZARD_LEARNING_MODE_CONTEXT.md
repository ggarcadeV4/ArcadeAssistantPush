# Controller Chuck - Wizard Learning Mode Context Handoff

> **Created**: 2025-12-18  
> **Purpose**: Persistent context document for future sessions  
> **Save Location**: `docs/` (in repo for persistence across sessions)

---

## Executive Summary

**Wizard Learning Mode** is a paradigm shift in how Controller Chuck configures arcade cabinets:

| Old Way | New Way |
|---------|---------|
| "Press P1 Up to confirm" | "Which button IS P1 Up? Press it." |
| Assumes factory wiring | Learns from physical reality |
| Breaks on non-standard wiring | Works with ANY wiring |
| No conflict awareness | Detects Steam/system hotkey collisions |

**Key Insight**: The AI accepts what the user says as truth, then that becomes the new default for the entire system.

---

## The Cascade Effect

When the user presses **Save** on the GUI, the following cascade occurs:

```
User presses SAVE
    │
    ├─→ controls.json (source of truth for Chuck)
    │
    ├─→ MAME cfg files (per-game controller configs)
    │
    ├─→ TeknoParrot UserProfile XMLs (input bindings)
    │
    └─→ LED Blinky (logical buttons → LED channels)
```

---

## Real-World Problem This Solves

> "My son wired the coin button to call up Steam on accident."

With the declaration-based wizard:
1. User tells AI: "When I press Coin, Steam comes up"
2. AI understands this is a **conflict**
3. AI suggests: "Let's remap Coin to F5 instead"
4. User agrees, AI captures F5 as the new Coin keycode
5. On Save, all downstream systems (MAME, TeknoParrot, LED Blinky) update

---

## Existing Code That Supports This

### Backend (Already Implemented)

| File | Purpose | Status |
|------|---------|--------|
| `backend/routers/controller.py` | Learn Wizard endpoints | ✅ UPDATED - Declaration-based + undo + cascade |
| `backend/services/chuck/encoder_state.py` | Mode detection (keyboard/XInput/DInput) | ✅ Complete |
| `backend/services/mame_config_generator.py` | MAME cfg generation | ✅ Complete |
| `backend/services/teknoparrot_config_generator.py` | TeknoParrot XML writer | ✅ Complete |
| `backend/services/controller_cascade.py` | Cascade orchestration | ✅ Complete (minus LED Blinky) |


### Configuration (Already Exists)

| File | Purpose |
|------|---------|
| `config/mappings/controls.json` | Source of truth (261 lines, 4 players) |
| `config/mappings/factory-default.json` | Rollback point for reset |
| `config/launchers.json` | Emulator paths including TeknoParrot |

### Key Paths

| System | Config Location |
|--------|-----------------|
| **MAME** | `A:/Emulators/MAME/cfg/{rom}.cfg` |
| **TeknoParrot** | `A:/Emulators/TeknoParrot Latest/UserProfiles/*.xml` |
| **LED Blinky** | TBD - Need to verify with user |
| **Controls Source** | `A:/Arcade Assistant Local/config/mappings/controls.json` |

---

## What Was Built (2025-12-18 Session)

### Phase 1: Declaration Capture ✅ COMPLETE
- Modified Learn Wizard prompts: "Which button is X? Press it now."
- Capture keycode without assumptions
- Updated `/learn-wizard/start`, `/learn-wizard/confirm`, `/learn-wizard/skip`

### Step Back / Undo ✅ COMPLETE
- Added `/learn-wizard/undo` endpoint
- Allows stepping back to previous control
- Clears previous capture for re-entry

### Phase 4: Cascade on Save ✅ COMPLETE
- `/learn-wizard/save` now triggers cascade automatically
- Creates backup before saving
- Auto-cascades to MAME/TeknoParrot if preference is "auto"
- Shows cascade progress in response

### Bug Fix: Reset to Default ✅ COMPLETE
- Fixed duplicate `/mapping/reset` endpoints
- Now properly restores from `factory-default.json`
- Added `chuck_prompt` and `message` fields

---

## What Still Needs to Be Built

### Phase 2: Conflict Detection (DEFERRED)
- New service: `conflict_detector.py`
- Detect Steam Overlay (Shift+Tab), Task Manager, MAME defaults
- Suggest alternative keycodes

### Phase 3: Visual Feedback (DEFERRED)
- Button blinks twice on successful capture
- "Is this correct for P1?" confirmation
- Save button glows when all declarations complete

### LED Blinky Cascade (DEFERRED - needs path)
- Add LED Blinky step to cascade
- Need to confirm where LED Blinky configuration is stored

### Auto Input Detection (BLOCKED)
- `pynput` keyboard listener is installed but not capturing encoder inputs
- Likely encoder is in gamepad mode, not keyboard mode
- Workaround: Manual key entry via `/learn-wizard/set-key`

---

## API Reference

### Learn Wizard Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/learn-wizard/start` | POST | Start the wizard (optional `?player=1` or `?player=2`) |
| `/learn-wizard/status` | GET | Get current progress and captured key |
| `/learn-wizard/confirm` | POST | Confirm auto-captured key and move to next |
| `/learn-wizard/set-key` | POST | **NEW** - Manual keycode entry `{"keycode":"F1"}` |
| `/learn-wizard/skip` | POST | Skip current control |
| `/learn-wizard/undo` | POST | **NEW** - Go back one step |
| `/learn-wizard/save` | POST | Save all captures and trigger cascade |
| `/learn-wizard/stop` | POST | Cancel wizard without saving |
| `/mapping/reset` | POST | Reset to factory-default.json |

### Frontend Functions (deviceClient.js)

```javascript
import { 
  startLearnWizard,
  getLearnWizardStatus,
  confirmLearnWizardCapture,
  setLearnWizardKey,      // NEW
  undoLearnWizardCapture, // NEW
  skipLearnWizardControl,
  saveLearnWizard,
  stopLearnWizard,
  resetMappingToDefault
} from '../../services/deviceClient';
```



---

## Known System Conflicts to Detect

```python
SYSTEM_CONFLICTS = {
    # Steam
    "Shift+Tab": "Steam Overlay",
    "F12": "Steam Screenshot",
    
    # Windows
    "Alt+Tab": "Task Switcher",
    "Ctrl+Shift+Escape": "Task Manager",
    "Win+D": "Show Desktop",
    
    # MAME Defaults
    "Escape": "MAME Exit",
    "P": "MAME Pause",
    "Tab": "MAME Menu",
    "F3": "MAME Reset",
}
```

---

## Session History Reference

### Previous Conversations (from summaries)
1. **Controller Calibration and Mode Detection** (2025-12-18)
   - Mode detection for Pactech board (keyboard/XInput/DInput)
   - Learn Wizard enhancements
   - Reset to Default issues

2. **Refining Controller Detection & Reset** (2025-12-18)
   - Scan for Devices functionality
   - Device registry classification
   - Reset functionality debugging

3. **Implementing Controller Learn Mode** (2025-12-17)
   - Initial Learn Mode implementation
   - Voice-guided wizard integration
   - Mapping persistence to controls.json

---

## Quick Resume Instructions

### If Starting a New Session:

1. Read this document first
2. Check the implementation plan: `implementation_plan.md`
3. Check the task tracker: `task.md`
4. Ask user for any updates since this document was created

### Key Files to Examine:

```bash
# Backend controller router (main logic)
view_file backend/routers/controller.py

# Encoder state (mode detection)
view_file backend/services/chuck/encoder_state.py

# Cascade orchestration
view_file backend/services/controller_cascade.py

# Current controls mapping
view_file config/mappings/controls.json
```

---

## User Preferences (from this session)

1. **Declaration-based paradigm** - AI asks what IS the control, doesn't assume
2. **Conflict detection** - Must handle Steam/system hotkey collisions
3. **Cascade on Save** - Single button updates all downstream systems
4. **Visual feedback** - Buttons blink, Save glows when ready
5. **LED Blinky integration** - Critical for complete arcade experience
6. **4-player support** - Universal image that works on any cabinet (1-4 players)
7. **Configurable button counts** - Support 6, 8, or 10 buttons per player
8. **Auto-advance** - Automatically confirm and advance when button pressed

---

## Related Documents

- **[LED Blinky Wizard Context](./LED_BLINKY_WIZARD_CONTEXT.md)** - Separate wizard for LED output mapping (because LEDWiz and encoder boards may be wired differently)

---

## Answered Questions

1. **LED Blinky path** - Needs separate wizard due to independent wiring
2. **Players to configure** - Configurable via `?players=X` param (1-4)
3. **Quick remap** - Undo endpoint allows stepping back
