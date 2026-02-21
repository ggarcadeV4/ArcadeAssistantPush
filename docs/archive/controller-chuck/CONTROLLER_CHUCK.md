# Controller Chuck - Development Documentation

## Session Summary (2025-12-18)

This document captures all work completed and planned for Controller Chuck, the arcade encoder management system.

---

## ✅ COMPLETED WORK

### 1. Player Identity Calibration

**Purpose**: Allow wizard to learn which physical station corresponds to P1/P2 even if wiring is swapped.

**Files Created/Modified**:

| File | Status | Description |
|------|--------|-------------|
| `backend/services/player_identity.py` | **NEW** | Persistence service for identity bindings |
| `backend/services/chuck/input_detector.py` | Modified | Added `source_id` field, `resolve_player_with_identity()` |
| `backend/routers/controller.py` | Modified | Added 5 identity endpoints, updated wizard state |

**New API Endpoints**:
```
GET  /api/local/controller/wizard/identity          - Check calibration status
POST /api/local/controller/wizard/identity/bind     - Start binding flow
POST /api/local/controller/wizard/identity/capture  - Capture input for player
POST /api/local/controller/wizard/identity/apply    - Persist bindings
POST /api/local/controller/wizard/identity/reset    - Clear calibration
```

**Persistence**: `state/controller/player_identity.json` with backup + audit logging.

---

### 2. Device Scan Fix (Scan Devices Button)

**Problem**: `/api/local/controller/devices` endpoint was missing, so "Scan Devices" button returned 404.

**Solution**: Added `/devices` endpoint in `controller.py` that:
- Scans USB/HID devices via `device_scanner.py`
- Uses **user classification** (not VID/PID guessing) to identify encoders
- Respects classifications from device registry
- Returns format expected by StatusCard component

**Key Insight**: PactoTech 2000T emulates Xbox controller (VID 0x045E:028E), not native VID. Solution: let user declare what device is their encoder instead of guessing.

---

### 3. Encoder Mode Detection (Partial)

**Added to `input_detector.py`**:
```python
ENCODER_MODES = {
    "keyboard": "Keyboard Mode - sends keystrokes",
    "xinput": "XInput Mode - Xbox controller emulation",
    "dinput": "DirectInput Mode - Generic gamepad",
    "unknown": "Unknown mode",
}

def detect_input_mode(keycode: str) -> str:
    """Detect encoder mode from keycode pattern."""
    # Returns: keyboard, xinput, dinput, or unknown
```

**Added `input_mode` field to `InputEvent` dataclass**.

---

## 🚧 PLANNED WORK (Not Yet Implemented)

### Feature 1: Mode Detection & Display in UI

**Backend Changes Needed**:
- Add `/encoder/mode` endpoint to get current detected mode
- Store `board.mode` in `controls.json`
- Update `/devices` response to include `detected_mode`

**Frontend Changes Needed**:
- Update `StatusCard` to show mode badge:
  - 🎹 Keyboard | 🎮 XInput | 🕹️ DirectInput

---

### Feature 2: Flexible "Press Anything" Wizard

**Current Problem**: Wizard says "Press P1 Joy Up now" but encoder mode affects what input is received.

**Proposed Solution**:
- Change prompt to: "Press the button you want to map to **P1 Joy Up**"
- Show what was detected: `Detected: KEY_W` or `AXIS_Y: -1.0`
- Add buttons: [✓ Confirm] [↻ Retry] [⏭ Skip]
- Accept ANY input, let user confirm

**Backend Changes**:
- Update Learn Wizard to accept any input type
- Add `/learn-wizard/retry` endpoint
- Store input type (key, axis, button) with mapping

**Frontend Changes**:
- Update wizard UI with confirm/retry/skip flow
- Show captured input details

---

### Feature 3: Mode Change Warning

**Purpose**: Alert user when encoder mode differs from last session (mappings may break).

**Backend**:
- Add `/encoder/mode-check` endpoint
- Compare stored `board.mode` with current detected mode
- Return: `{match: false, stored: "keyboard", current: "xinput"}`

**Frontend**:
- Create `ModeWarning.jsx` component
- Show warning banner on mode mismatch
- Offer: [Re-run Learn Wizard] [Update Stored Mode] [Dismiss]

---

### Feature 4: Chuck AI Encoder Awareness

**Purpose**: Chuck should understand encoder modes and available commands.

**Backend Changes** (`controller_ai.py`):
```python
# Inject into system prompt:
ENCODER_CONTEXT = """
Current encoder: {name}
Mode: {mode} ({mode_description})
Available commands you can help with:
- "reset mappings" - clears all learned mappings
- "what mode is my encoder in" - explain current mode
- "run learn wizard" - start the mapping wizard
- "scan for devices" - refresh device list
"""
```

---

## 📁 Key Files Reference

| File | Purpose |
|------|---------|
| `backend/services/chuck/input_detector.py` | Core input detection, mode detection |
| `backend/services/player_identity.py` | Player identity calibration persistence |
| `backend/routers/controller.py` | All controller API endpoints |
| `backend/routers/controller_ai.py` | Chuck AI chat for controller panel |
| `backend/services/device_scanner.py` | USB/HID device enumeration |
| `frontend/src/panels/controller/ControllerPanel.jsx` | Main controller UI |
| `frontend/src/services/deviceClient.js` | Frontend API client for controller |

---

## 🔧 Configuration Files

| File | Purpose |
|------|---------|
| `config/mappings/controls.json` | Button mappings + board config |
| `state/controller/player_identity.json` | P1/P2 identity calibration |
| `state/controller/known_devices.json` | Device classifications |

---

## 🧪 Testing Commands

```powershell
# Test device scan
curl http://localhost:8000/api/local/controller/devices `
  -H "x-device-id: test" -H "x-scope: state" -H "x-panel: controller"

# Test identity status
curl http://localhost:8000/api/local/controller/wizard/identity `
  -H "x-device-id: test" -H "x-scope: state" -H "x-panel: controller"

# Test reset mappings
curl -X POST http://localhost:8000/api/local/controller/mapping/reset `
  -H "x-device-id: test" -H "x-scope: config" -H "x-panel: controller"
```

---

## 🐛 Known Issues

1. **Reset button** - Frontend has `resetMappingToDefault()` function but unclear where UI button triggers it
2. **Mode endpoint** - `/encoder/mode` endpoint not yet implemented
3. **Learn Wizard** - Still uses fixed "press P1 Up" prompts, needs flexible mode

---

## 📋 Next Session TODO

1. Add `/encoder/mode` and `/encoder/mode-check` endpoints
2. Update StatusCard to show mode badge
3. Implement flexible "press anything" wizard flow
4. Add ModeWarning component
5. Update Chuck AI system prompt with encoder context
6. Wire up Reset button properly in UI
