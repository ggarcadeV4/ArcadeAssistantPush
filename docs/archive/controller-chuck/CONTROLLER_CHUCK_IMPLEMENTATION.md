# Controller Chuck - Implementation Plan
**Character:** Chuck - Brooklyn mechanic, arcade encoder board expert
**Purpose:** Manage Mapping Dictionary (physical encoder pins → logical buttons)
**Priority:** CRITICAL - Foundation for LED Blinky, Console Wizard, all input systems
**Status:** 40% Complete (UI exists with mock data, no backend)

---

## 📖 **SESSION-BY-SESSION IMPLEMENTATION GUIDE**

**IMPORTANT:** Use this guide to track progress and resume after context breaks.

### **How to Use This Guide:**
1. Read the current session section completely before coding
2. Complete ALL tasks in the session before moving to next
3. Run acceptance tests at end of each session
4. Update the ✅ checkboxes as you complete tasks
5. If interrupted mid-session, start from the last unchecked task

---

### **SESSION 1: Setup + Backend Router (2-3 hours)**

**Goal:** Create Mapping Dictionary files and backend router skeleton

**Tasks:**
- [ ] 1.1: Create directory structure
  ```bash
  mkdir -p config/mappings
  mkdir -p config/mame/cfg
  ```

- [ ] 1.2: Create `config/mappings/controls.json`
  - Copy JSON schema from section 1.1 below
  - Set Greg's actual pin assignments (ask Greg for factory config)
  - Ensure all 4 players have mappings (P1/P2 full, P3/P4 basic)

- [ ] 1.3: Create `config/mappings/factory-default.json`
  - Copy controls.json as template
  - Add comment: "Greg's factory default - DO NOT MODIFY"
  - This is the rollback point for Factory Reset

- [ ] 1.4: Create `backend/routers/controller.py`
  - Copy imports from `backend/routers/led_blinky.py` (lines 1-11)
  - Create router instance: `router = APIRouter()`
  - Copy Pydantic models from section 1.2 below
  - Implement `GET /mapping` endpoint (section 1.2)
  - Copy `log_controller_change()` helper from section 1.2

- [ ] 1.5: Register router in `backend/app.py`
  ```python
  from backend.routers import controller
  app.include_router(controller.router, prefix="/api/local/controller", tags=["controller"])
  ```

- [ ] 1.6: Test endpoint
  ```bash
  # Start backend
  cd backend && python app.py

  # Test (should return 404 first time, then create file)
  curl http://localhost:8000/api/local/controller/mapping
  ```

**Acceptance Criteria:**
- ✅ `config/mappings/controls.json` exists with valid JSON
- ✅ `config/mappings/factory-default.json` exists (identical to controls.json)
- ✅ `backend/routers/controller.py` exists (~50 lines)
- ✅ Router registered in app.py
- ✅ `curl` returns mapping JSON (not 404 or 500 error)

**If Interrupted:** Check which file was last created/modified. Resume from that step.

---

### **SESSION 2: Preview/Apply/Reset Endpoints (2-3 hours)**

**Goal:** Complete CRUD operations with backup workflow

**Prerequisites:** Session 1 complete (mapping file exists, GET endpoint works)

**Tasks:**
- [ ] 2.1: Implement `POST /mapping/preview` endpoint
  - Copy pattern from `backend/routers/led_blinky.py` lines 132-180
  - Adapt for controls.json structure (not LED profile)
  - Validate: no duplicate pins, critical buttons mapped
  - Return diff using `compute_diff()` from services

- [ ] 2.2: Implement `POST /mapping/apply` endpoint
  - Copy pattern from led_blinky.py lines 182-268
  - Call `require_scope(request, "config")` first
  - Use `create_backup()` before writing
  - Call `log_controller_change()` after writing
  - Return backup_path in response

- [ ] 2.3: Implement `POST /mapping/reset` endpoint
  - Copy factory-default.json to controls.json
  - Create backup of current controls.json first
  - Log reset action
  - Return backup_path

- [ ] 2.4: Test all endpoints
  ```bash
  # Preview change
  curl -X POST http://localhost:8000/api/local/controller/mapping/preview \
    -H "Content-Type: application/json" \
    -d '{"mappings": {"p1.button1": {"pin": 7, "type": "button"}}}'

  # Apply change
  curl -X POST http://localhost:8000/api/local/controller/mapping/apply \
    -H "Content-Type: application/json" \
    -H "x-scope: config" \
    -H "x-panel: controller" \
    -d '{"mappings": {"p1.button1": {"pin": 7, "type": "button"}}}'

  # Verify backup created
  ls -la backups/$(date +%Y%m%d)/

  # Factory reset
  curl -X POST http://localhost:8000/api/local/controller/mapping/reset \
    -H "x-scope: config"
  ```

**Acceptance Criteria:**
- ✅ Preview returns diff (not error)
- ✅ Apply creates backup in `backups/{date}/`
- ✅ Apply updates controls.json
- ✅ Logs appear in `logs/changes.jsonl`
- ✅ Factory reset restores original mapping

**If Interrupted:** Run curl tests to see which endpoints work. Complete remaining.

---

### **SESSION 3: Frontend Integration (2-3 hours)**

**Goal:** Replace mock data with real API calls

**Prerequisites:** Session 2 complete (all backend endpoints working)

**Tasks:**
- [ ] 3.1: Update `frontend/src/panels/controller/ControllerPanel.jsx`
  - Remove hardcoded PLAYER_MAPPINGS (lines 6-59)
  - Add state: `const [mappings, setMappings] = useState({})`
  - Add useEffect to fetch on mount (section 1.4)

- [ ] 3.2: Transform API data for display
  - Copy transformation logic from section 1.4
  - Filter mappings by current player (p1, p2, p3, p4)
  - Display in existing mapping table component

- [ ] 3.3: Add Preview/Apply workflow
  - Copy handleEditMapping from section 1.4
  - Add diff modal component (can reuse from Panel Kit)
  - Wire up "Edit" buttons in mapping table

- [ ] 3.4: Add Factory Reset button
  - Copy button code from section 1.4
  - Add confirmation dialog
  - Reload page after reset

- [ ] 3.5: Test UI
  - Open http://localhost:8787/controller
  - Mapping table shows real data from controls.json
  - Edit button → preview → apply → success
  - Factory reset → confirm → mapping reverts

**Acceptance Criteria:**
- ✅ Panel loads without errors
- ✅ Mapping table shows data from controls.json
- ✅ Edit workflow: preview → diff modal → apply → success notification
- ✅ Factory Reset button works (with confirmation)
- ✅ Changes persist after page reload

**If Interrupted:** Check which step was last modified in ControllerPanel.jsx. Resume from there.

---

### **SESSION 4: USB Board Detection (2 hours)**

**Goal:** Detect encoder boards and display board info

**Prerequisites:** Session 3 complete (frontend working)

**Tasks:**
- [ ] 4.1: Add pyusb to requirements
  ```bash
  echo "pyusb>=1.2.1" >> backend/requirements.txt
  pip install pyusb
  ```

- [ ] 4.2: Create `backend/services/usb_detection.py`
  - Copy USBBoardDetector class from section 2.2
  - Add KNOWN_BOARDS dict (PacDrive, I-PAC2, Zero Delay)
  - Implement detect_board() method

- [ ] 4.3: Add `GET /board` endpoint in controller.py
  - Copy code from section 2.3
  - Import USBBoardDetector
  - Return detected board or available_devices list

- [ ] 4.4: Add board status tile to frontend
  - Copy board status JSX from section 2.4
  - Add fetch in useEffect
  - Display detected board or "No board" message

- [ ] 4.5: Test detection
  ```bash
  # With board connected
  curl http://localhost:8000/api/local/controller/board
  # Expect: {"status": "detected", "board": {...}}

  # Without board (or in dev environment)
  # Expect: {"status": "not_detected", "available_devices": [...]}
  ```

**Acceptance Criteria:**
- ✅ pyusb installed without errors
- ✅ GET /board endpoint works
- ✅ UI shows board status tile
- ✅ With board: shows "PacDrive 2000T detected"
- ✅ Without board: shows "No board detected" + Retry button

**If Interrupted:** Check if pyusb installed. If yes, check if usb_detection.py exists.

---

### **SESSION 5: MAME Config Generation (2-3 hours)**

**Goal:** Generate per-game MAME configs from Mapping Dictionary

**Prerequisites:** Session 4 complete (USB detection working)

**Tasks:**
- [ ] 5.1: Create `backend/services/mame_config_writer.py`
  - Copy MAMEConfigWriter class from section 3.2
  - Implement generate_cfg() method (XML generation)
  - Implement _map_to_mame_type() helper

- [ ] 5.2: Add GameOverride Pydantic model
  ```python
  class GameOverride(BaseModel):
      rom_name: str
      mappings: Dict[str, Any]
  ```

- [ ] 5.3: Add MAME config endpoints
  - `POST /game-override/preview` (section 3.3)
  - `POST /game-override/apply` (section 3.3)

- [ ] 5.4: Test MAME config generation
  ```bash
  # Preview sf2 config
  curl -X POST http://localhost:8000/api/local/controller/game-override/preview \
    -H "Content-Type: application/json" \
    -d '{"rom_name": "sf2", "mappings": {"p1.button1": {"pin": 1}}}'

  # Apply sf2 config
  curl -X POST http://localhost:8000/api/local/controller/game-override/apply \
    -H "Content-Type: application/json" \
    -H "x-scope: config" \
    -d '{"rom_name": "sf2", "mappings": {}}'

  # Verify file created
  cat config/mame/cfg/sf2.cfg
  ```

**Acceptance Criteria:**
- ✅ mame_config_writer.py exists
- ✅ Preview returns XML preview
- ✅ Apply creates sf2.cfg file
- ✅ XML is valid (check with cat/xmllint)
- ✅ Log entry in changes.jsonl

**If Interrupted:** Check if mame_config_writer.py exists. Resume endpoint implementation.

---

### **SESSION 6: Validation & Polish (1-2 hours)**

**Goal:** Add validation, error handling, final testing

**Prerequisites:** Session 5 complete (MAME config working)

**Tasks:**
- [ ] 6.1: Add validation logic to preview endpoint
  - Check for duplicate pins
  - Warn if critical buttons unmapped (coin, start, button1)
  - Validate pin numbers (1-32 for PacDrive)

- [ ] 6.2: Add error banners to frontend
  - "Board not detected" banner
  - "Duplicate pin assignment" inline error
  - "Critical button unmapped" warning

- [ ] 6.3: Run full acceptance test suite
  - All CLI curls (sections 1-3)
  - All UI tests (sections 1-3)
  - Verify backups directory populated
  - Verify logs/changes.jsonl has entries

- [ ] 6.4: Test LED Blinky integration
  - Open LED Blinky panel
  - Verify it can read controls.json
  - Update Chuck mapping → LED Blinky should reflect change

**Acceptance Criteria:**
- ✅ Validation catches duplicate pins
- ✅ Warning shown for unmapped critical buttons
- ✅ All error states tested (no board, bad pin, etc.)
- ✅ Full test suite passes
- ✅ LED Blinky reads Chuck's mapping (cascade works)

**If Interrupted:** Run test suite to see what passes/fails. Fix remaining.

---

### **PROGRESS TRACKING**

**Current Status:** Not started

**Completed Sessions:** (update as you go)
- [ ] Session 1: Setup + Backend Router
- [ ] Session 2: Preview/Apply/Reset
- [ ] Session 3: Frontend Integration
- [ ] Session 4: USB Detection
- [ ] Session 5: MAME Config Generation
- [ ] Session 6: Validation & Polish

**Next Session:** Session 1

**Blocked?** No blockers identified

---

### **RESUME INSTRUCTIONS (If Context Breaks)**

1. **Check file system:**
   ```bash
   ls -la config/mappings/
   ls -la backend/routers/controller.py
   ls -la backend/services/usb_detection.py
   ```

2. **Test endpoints:**
   ```bash
   curl http://localhost:8000/api/local/controller/mapping
   curl http://localhost:8000/api/local/controller/board
   ```

3. **Find last completed session:**
   - If controls.json exists but router doesn't → Resume at Session 1, step 1.4
   - If GET /mapping works but preview doesn't → Resume at Session 2
   - If backend complete but frontend shows mock data → Resume at Session 3
   - If frontend works but no board detection → Resume at Session 4
   - If board detection works but no MAME config → Resume at Session 5

4. **Read relevant section above and continue from first unchecked task**

---

## 🎯 **THE PROBLEM CHUCK SOLVES**

**Scenario:** Customer buys cabinet → Windows update breaks configs → weeks of setup lost
**Chuck's Solution:** Single source of truth (`controls.json`) that regenerates all configs
- When configs break → Chuck restores from Mapping Dictionary
- When buttons remapped → LED Blinky, Console Wizard, MAME all update automatically
- Factory Reset restores Greg's golden config in seconds

**Cascade Effect:**
```
Chuck's Mapping Dictionary (controls.json)
    ↓
    ├─> LED Blinky (button lighting)
    ├─> Console Wizard (RetroArch configs)
    └─> MAME (per-game .cfg files)
```

---

## 📁 **CURRENT STATE AUDIT**

### **✅ What Exists**

#### **Frontend (40% Complete)**
- **File:** `frontend/src/panels/controller/ControllerPanel.jsx` (543 lines)
- **Status:** UI scaffold complete, **uses mock data**
- **What Works:**
  - 4-player cabinet visualization (lines 110-163)
  - Mapping table with hardcoded `PLAYER_MAPPINGS` (lines 6-59)
  - Chuck chat sidebar (lines 210-280)
  - Player switching (1-4)
  - Notification system
  - Keyboard shortcuts (1-4 keys switch players)
  - Chat integration with AI client
- **What's Missing:**
  - Real API calls (fetch from backend)
  - Live button test mode (press button → detect pin)
  - Preview/apply workflow for edits
  - Factory reset button
  - Board status display

#### **Backend (0% Complete)**
- ❌ **Router:** `backend/routers/controller.py` **DOES NOT EXIST**
- ❌ **Services:** None exist
- ❌ **Config Files:** Mapping Dictionary doesn't exist

#### **Reusable Code (LED Blinky Template)**
- **File:** `backend/routers/led_blinky.py` (336 lines)
- **Perfect Template:** Provides 95% of pattern Chuck needs
  - `/test` endpoint (lines 76-130) → adapt for button testing
  - `/mapping/preview` endpoint (lines 132-180) → copy directly
  - `/mapping/apply` endpoint (lines 182-268) → copy directly
  - Logging with headers (lines 54-73) → copy directly
  - Backup creation (lines 239-240) → copy directly

#### **Existing Services (Reusable)**
- ✅ `backend/services/backup.py` - create_backup(), restore_from_backup()
- ✅ `backend/services/diffs.py` - compute_diff(), has_changes()
- ✅ `backend/services/policies.py` - require_scope(), is_allowed_file()

---

## 🛠️ **WHAT NEEDS TO BE BUILT**

### **Phase 1: Core CRUD (No USB Hardware Required)**

#### **1.1 Create Mapping Dictionary Files**
**Location:** `config/mappings/`

**File 1:** `config/mappings/controls.json` (source of truth)
```json
{
  "version": "1.0",
  "created_at": "2025-10-16T10:00:00Z",
  "board": {
    "vid": "0x045E",
    "pid": "0x028E",
    "name": "PacDrive 2000T",
    "detected": true,
    "modes": {
      "twinstick": false,
      "turbo": false,
      "six_button": false,
      "interlock": true
    }
  },
  "mappings": {
    "p1.coin": {"pin": 1, "type": "button", "label": "P1 Coin"},
    "p1.start": {"pin": 2, "type": "button", "label": "P1 Start"},
    "p1.button1": {"pin": 4, "type": "button", "label": "P1 Button 1"},
    "p1.button2": {"pin": 5, "type": "button", "label": "P1 Button 2"},
    "p1.button3": {"pin": 6, "type": "button", "label": "P1 Button 3"},
    "p1.button4": {"pin": 7, "type": "button", "label": "P1 Button 4"},
    "p1.button5": {"pin": 14, "type": "button", "label": "P1 Button 5"},
    "p1.button6": {"pin": 15, "type": "button", "label": "P1 Button 6"},
    "p1.button7": {"pin": 16, "type": "button", "label": "P1 Button 7"},
    "p1.button8": {"pin": 17, "type": "button", "label": "P1 Button 8"},
    "p1.up": {"pin": 10, "type": "joystick", "label": "P1 Up"},
    "p1.down": {"pin": 11, "type": "joystick", "label": "P1 Down"},
    "p1.left": {"pin": 12, "type": "joystick", "label": "P1 Left"},
    "p1.right": {"pin": 13, "type": "joystick", "label": "P1 Right"},
    "p2.coin": {"pin": 18, "type": "button", "label": "P2 Coin"},
    "p2.start": {"pin": 19, "type": "button", "label": "P2 Start"},
    "p2.button1": {"pin": 20, "type": "button", "label": "P2 Button 1"},
    "p2.button2": {"pin": 21, "type": "button", "label": "P2 Button 2"}
  },
  "last_modified": "2025-10-16T10:00:00Z",
  "modified_by": "system"
}
```

**File 2:** `config/mappings/factory-default.json` (Greg's golden config - read-only)
```json
{
  "version": "1.0",
  "comment": "Greg's factory default - DO NOT MODIFY",
  "board": { ... same as above ... },
  "mappings": { ... Greg's original wiring ... }
}
```

**Required Logical Keys:**
- **Player 1:** p1.coin, p1.start, p1.button1-8, p1.up/down/left/right
- **Player 2:** p2.coin, p2.start, p2.button1-8, p2.up/down/left/right
- **Player 3:** p3.coin, p3.start, p3.button1-4, p3.up/down/left/right
- **Player 4:** p4.coin, p4.start, p4.button1-4, p4.up/down/left/right

**Validation Rules:**
- No duplicate pins (one pin = one logical button)
- Critical buttons (coin, start, button1) must be mapped
- Pin numbers must be valid for board (1-32 for PacDrive 2000T)

---

#### **1.2 Create Backend Router**
**File:** `backend/routers/controller.py` (NEW - copy from led_blinky.py)

**Copy Pattern From:** `backend/routers/led_blinky.py` lines 1-268

**Endpoints to Create:**

```python
# GET /api/local/controller/mapping
# Returns current Mapping Dictionary
@router.get("/mapping")
async def get_controller_mapping(request: Request):
    drive_root = request.app.state.drive_root
    mapping_file = drive_root / "config" / "mappings" / "controls.json"

    if not mapping_file.exists():
        raise HTTPException(status_code=404, detail="Mapping file not found")

    with open(mapping_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return {
        "mapping": data,
        "file_path": "config/mappings/controls.json"
    }
```

```python
# POST /api/local/controller/mapping/preview
# Preview mapping changes (copy from LED Blinky lines 132-180)
@router.post("/mapping/preview")
async def preview_controller_mapping(request: Request, mapping_data: MappingUpdate):
    # Same pattern as LED Blinky preview
    # 1. Read current controls.json
    # 2. Merge with new mappings
    # 3. Validate (no duplicate pins, critical buttons mapped)
    # 4. Generate diff
    # 5. Return diff + validation results
```

```python
# POST /api/local/controller/mapping/apply
# Apply mapping changes with backup (copy from LED Blinky lines 182-268)
@router.post("/mapping/apply")
async def apply_controller_mapping(request: Request, mapping_data: MappingUpdate):
    require_scope(request, "config")
    # Same pattern as LED Blinky apply
    # 1. Validate scope header
    # 2. Create backup
    # 3. Write new content
    # 4. Log to changes.jsonl
    # 5. Return backup_path
```

```python
# POST /api/local/controller/mapping/reset
# Restore factory defaults
@router.post("/mapping/reset")
async def reset_to_factory_defaults(request: Request):
    require_scope(request, "config")
    drive_root = request.app.state.drive_root
    factory_file = drive_root / "config" / "mappings" / "factory-default.json"
    controls_file = drive_root / "config" / "mappings" / "controls.json"

    # Create backup of current
    backup_path = create_backup(controls_file, drive_root)

    # Copy factory default to controls.json
    shutil.copy2(factory_file, controls_file)

    # Log reset
    log_controller_change(request, drive_root, "factory_reset", {}, backup_path)

    return {
        "status": "reset",
        "backup_path": str(backup_path)
    }
```

**Pydantic Models:**
```python
from pydantic import BaseModel
from typing import Dict, Any, Optional

class MappingUpdate(BaseModel):
    mappings: Dict[str, Any]  # e.g., {"p1.button1": {"pin": 7, "type": "button"}}

class MappingValidation(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]
```

**Helper Function (copy from LED Blinky lines 54-73):**
```python
def log_controller_change(request: Request, drive_root: Path, action: str, details: Dict[str, Any], backup_path: Optional[Path] = None):
    log_file = drive_root / "logs" / "changes.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    device = request.headers.get('x-device-id', 'unknown')
    panel = request.headers.get('x-panel', 'controller')

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "scope": "controller",
        "action": action,
        "details": details,
        "backup_path": str(backup_path) if backup_path else None,
        "device": device,
        "panel": panel,
    }

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry) + "\n")
```

---

#### **1.3 Register Router in FastAPI App**
**File:** `backend/app.py`

**Add:**
```python
from backend.routers import controller

app.include_router(controller.router, prefix="/api/local/controller", tags=["controller"])
```

---

#### **1.4 Update Frontend to Use Real API**
**File:** `frontend/src/panels/controller/ControllerPanel.jsx`

**Replace:** Hardcoded `PLAYER_MAPPINGS` (lines 6-59)

**With:** API fetch on mount
```jsx
const [mappings, setMappings] = useState({});
const [boardInfo, setBoardInfo] = useState(null);

useEffect(() => {
  // Fetch current mapping
  fetch('http://localhost:8000/api/local/controller/mapping')
    .then(res => res.json())
    .then(data => {
      setMappings(data.mapping.mappings);
      setBoardInfo(data.mapping.board);
    })
    .catch(err => console.error('Failed to load mappings:', err));
}, []);

// Transform mappings for display
const currentMappings = useMemo(() => {
  const player = `p${currentPlayer}`;
  return Object.entries(mappings)
    .filter(([key]) => key.startsWith(player + '.'))
    .map(([key, value]) => ({
      input: value.label || key,
      mapping: `Pin ${value.pin}`,
      status: value.pin ? 'MAPPED' : 'UNMAPPED'
    }));
}, [mappings, currentPlayer]);
```

**Add:** Preview/Apply workflow
```jsx
const handleEditMapping = async (logicalKey, newPin) => {
  // 1. Preview change
  const previewRes = await fetch('http://localhost:8000/api/local/controller/mapping/preview', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      mappings: { [logicalKey]: { pin: newPin, type: 'button' } }
    })
  });
  const preview = await previewRes.json();

  // 2. Show diff modal
  setDiffPreview(preview.diff);

  // 3. On user confirmation, apply
  if (userConfirmed) {
    const applyRes = await fetch('http://localhost:8000/api/local/controller/mapping/apply', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-scope': 'config',
        'x-panel': 'controller'
      },
      body: JSON.stringify({
        mappings: { [logicalKey]: { pin: newPin, type: 'button' } }
      })
    });
    const result = await applyRes.json();
    showNotification(`Applied! Backup: ${result.backup_path}`);
  }
};
```

**Add:** Factory Reset button
```jsx
<button onClick={async () => {
  if (confirm('Reset to factory defaults? Current mapping will be backed up.')) {
    const res = await fetch('http://localhost:8000/api/local/controller/mapping/reset', {
      method: 'POST',
      headers: {'x-scope': 'config', 'x-panel': 'controller'}
    });
    const result = await res.json();
    showNotification(`Reset complete! Backup: ${result.backup_path}`);
    // Reload mappings
    window.location.reload();
  }
}}>
  Factory Reset
</button>
```

---

### **Phase 1 Acceptance Criteria**

**CLI Tests:**
```bash
# 1. Get current mapping
curl http://localhost:8000/api/local/controller/mapping
# Expect: JSON with "mapping" key containing board + mappings

# 2. Preview change
curl -X POST http://localhost:8000/api/local/controller/mapping/preview \
  -H "Content-Type: application/json" \
  -d '{"mappings": {"p1.button1": {"pin": 7, "type": "button"}}}'
# Expect: {"diff": "...", "has_changes": true}

# 3. Apply change
curl -X POST http://localhost:8000/api/local/controller/mapping/apply \
  -H "Content-Type: application/json" \
  -H "x-scope: config" \
  -H "x-panel: controller" \
  -d '{"mappings": {"p1.button1": {"pin": 7, "type": "button"}}}'
# Expect: {"status": "applied", "backup_path": "..."}

# 4. Verify backup created
ls -la config/../backups/*/config_mappings_controls.json

# 5. Factory reset
curl -X POST http://localhost:8000/api/local/controller/mapping/reset \
  -H "x-scope: config"
# Expect: {"status": "reset", "backup_path": "..."}
```

**UI Tests:**
1. Open Controller Chuck panel (`/controller`)
2. Mapping table shows real data from `controls.json`
3. Click "Edit P1 Button 1" → modal appears
4. Enter new pin → Preview shows diff
5. Apply → success notification, backup path logged
6. Verify: `config/mappings/controls.json` updated
7. Verify: `backups/{date}/` contains backup
8. Verify: `logs/changes.jsonl` has entry with panel:"controller"
9. Click "Factory Reset" → confirm → table reverts
10. Verify: `controls.json` matches `factory-default.json`

---

## 🔌 **Phase 2: USB Board Detection**

### **2.1 Add USB Library**
**File:** `backend/requirements.txt`

**Add:**
```txt
pyusb>=1.2.1
```

**Install:**
```bash
pip install pyusb
```

---

### **2.2 Create USB Detection Service**
**File:** `backend/services/usb_detection.py` (NEW)

```python
import usb.core
import usb.util
from typing import Optional, Dict

class USBBoardDetector:
    """Detect arcade encoder boards via USB VID/PID"""

    KNOWN_BOARDS = {
        # PacDrive 2000T
        ("0xD209", "0x1601"): "PacDrive 2000T",
        # I-PAC2
        ("0xD209", "0x0301"): "I-PAC2",
        # I-PAC4
        ("0xD209", "0x0401"): "I-PAC4",
        # Zero Delay (generic)
        ("0x0079", "0x0006"): "Zero Delay USB Encoder",
    }

    def detect_board(self) -> Optional[Dict]:
        """Scan USB devices for known encoder boards

        Returns:
            Dict with vid, pid, name, or None if not found
        """
        devices = usb.core.find(find_all=True)

        for device in devices:
            vid = f"0x{device.idVendor:04X}"
            pid = f"0x{device.idProduct:04X}"
            key = (vid, pid)

            if key in self.KNOWN_BOARDS:
                return {
                    "vid": vid,
                    "pid": pid,
                    "name": self.KNOWN_BOARDS[key],
                    "detected": True,
                    "manufacturer": device.manufacturer if hasattr(device, 'manufacturer') else "Unknown",
                    "product": device.product if hasattr(device, 'product') else "Unknown"
                }

        return None

    def list_all_devices(self) -> list[Dict]:
        """List all USB devices (for debugging unknown boards)"""
        devices = usb.core.find(find_all=True)
        result = []

        for device in devices:
            result.append({
                "vid": f"0x{device.idVendor:04X}",
                "pid": f"0x{device.idProduct:04X}",
                "manufacturer": device.manufacturer if hasattr(device, 'manufacturer') else None,
                "product": device.product if hasattr(device, 'product') else None
            })

        return result
```

---

### **2.3 Add Board Detection Endpoint**
**File:** `backend/routers/controller.py`

**Add:**
```python
from ..services.usb_detection import USBBoardDetector

@router.get("/board")
async def detect_encoder_board(request: Request):
    """Detect connected arcade encoder board"""
    try:
        detector = USBBoardDetector()
        board_info = detector.detect_board()

        if board_info:
            return {
                "status": "detected",
                "board": board_info
            }
        else:
            # Return list of all USB devices for troubleshooting
            all_devices = detector.list_all_devices()
            return {
                "status": "not_detected",
                "board": None,
                "available_devices": all_devices[:10]  # Limit to 10
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"USB detection failed: {str(e)}")
```

---

### **2.4 Update Frontend Board Status**
**File:** `frontend/src/panels/controller/ControllerPanel.jsx`

**Add:** Board status tile
```jsx
const [boardStatus, setBoardStatus] = useState(null);

useEffect(() => {
  // Fetch board info
  fetch('http://localhost:8000/api/local/controller/board')
    .then(res => res.json())
    .then(data => setBoardStatus(data))
    .catch(err => console.error('Board detection failed:', err));
}, []);

// In render:
<div className="board-status-tile">
  {boardStatus?.status === 'detected' ? (
    <>
      <div className="status-icon">✓</div>
      <div>Detected: {boardStatus.board.name}</div>
      <div>VID: {boardStatus.board.vid} | PID: {boardStatus.board.pid}</div>
    </>
  ) : (
    <>
      <div className="status-icon">⚠</div>
      <div>No encoder board detected</div>
      <button onClick={() => window.location.reload()}>Retry Detection</button>
    </>
  )}
</div>
```

---

### **Phase 2 Acceptance Criteria**

**CLI Tests:**
```bash
# 1. Detect board (with board connected)
curl http://localhost:8000/api/local/controller/board
# Expect: {"status": "detected", "board": {"vid": "0xD209", "pid": "0x1601", "name": "PacDrive 2000T"}}

# 2. Detect board (without board)
curl http://localhost:8000/api/local/controller/board
# Expect: {"status": "not_detected", "board": null, "available_devices": [...]}
```

**UI Tests:**
1. With board connected: Status tile shows "PacDrive 2000T detected"
2. Without board: Status tile shows "No board detected" + Retry button

---

## 🎮 **Phase 3: Live Button Testing + MAME Configs**

### **3.1 Live Button Test Endpoint**
**File:** `backend/routers/controller.py`

**Approach:** Poll USB device for input events

```python
@router.post("/test/start")
async def start_button_test(request: Request):
    """Start live button testing mode"""
    # TODO: Start background thread that polls USB device
    # Return test_session_id
    return {"status": "test_started", "session_id": "test_123"}

@router.get("/test/poll")
async def poll_button_test(request: Request, session_id: str):
    """Poll for detected button press"""
    # TODO: Check if any button pressed since last poll
    # Return pin number if detected
    return {"pin": 7, "timestamp": datetime.now().isoformat()}

@router.post("/test/stop")
async def stop_button_test(request: Request, session_id: str):
    """Stop live button testing"""
    # TODO: Stop background thread
    return {"status": "test_stopped"}
```

**Note:** This requires USB HID input reading - may need `hidapi` library or direct USB interrupt reads. Implementation complexity: MEDIUM.

---

### **3.2 MAME Config Writer Service**
**File:** `backend/services/mame_config_writer.py` (NEW)

```python
from pathlib import Path
from typing import Dict
import xml.etree.ElementTree as ET

class MAMEConfigWriter:
    """Generate MAME per-game .cfg files from Mapping Dictionary"""

    def generate_cfg(self, rom_name: str, mappings: Dict, output_dir: Path) -> Path:
        """Generate MAME .cfg file for specific game

        Args:
            rom_name: ROM name (e.g., "sf2")
            mappings: Mapping Dictionary
            output_dir: Path to MAME cfg directory (e.g., A:/LaunchBox/Emulators/MAME/cfg/)

        Returns:
            Path to created .cfg file
        """
        cfg_file = output_dir / f"{rom_name}.cfg"

        # Create XML structure
        root = ET.Element("mameconfig", version="10")
        system = ET.SubElement(root, "system", name=rom_name)
        input_elem = ET.SubElement(system, "input")

        # Map each button to MAME input
        for logical_key, physical in mappings.items():
            if not logical_key.startswith('p1.'):  # MAME only uses P1 in single-player context
                continue

            button_type = self._map_to_mame_type(logical_key)
            if button_type:
                port = ET.SubElement(input_elem, "port",
                    tag="IN0",
                    type=button_type,
                    mask="1",
                    defvalue="0"
                )
                newseq = ET.SubElement(port, "newseq", type="standard")
                newseq.text = f"JOYCODE_1_BUTTON{physical['pin']}"

        # Write to file
        tree = ET.ElementTree(root)
        tree.write(cfg_file, encoding="utf-8", xml_declaration=True)

        return cfg_file

    def _map_to_mame_type(self, logical_key: str) -> str:
        """Map logical key to MAME input type"""
        mapping = {
            "p1.button1": "P1_BUTTON1",
            "p1.button2": "P1_BUTTON2",
            "p1.button3": "P1_BUTTON3",
            "p1.button4": "P1_BUTTON4",
            "p1.button5": "P1_BUTTON5",
            "p1.button6": "P1_BUTTON6",
            "p1.up": "P1_JOYSTICK_UP",
            "p1.down": "P1_JOYSTICK_DOWN",
            "p1.left": "P1_JOYSTICK_LEFT",
            "p1.right": "P1_JOYSTICK_RIGHT",
            "p1.start": "P1_START",
            "p1.coin": "COIN1",
        }
        return mapping.get(logical_key)
```

---

### **3.3 MAME Config Endpoints**
**File:** `backend/routers/controller.py`

```python
from ..services.mame_config_writer import MAMEConfigWriter

@router.post("/game-override/preview")
async def preview_mame_config(request: Request, override_data: GameOverride):
    """Preview MAME .cfg file for specific game"""
    drive_root = request.app.state.drive_root
    mapping_file = drive_root / "config" / "mappings" / "controls.json"

    with open(mapping_file, 'r') as f:
        mappings = json.load(f)['mappings']

    # Merge with override
    merged = {**mappings, **override_data.mappings}

    # Generate XML preview
    writer = MAMEConfigWriter()
    cfg_content = writer.generate_cfg_preview(override_data.rom_name, merged)

    return {
        "rom": override_data.rom_name,
        "cfg_preview": cfg_content,
        "target_file": f"config/mame/cfg/{override_data.rom_name}.cfg"
    }

@router.post("/game-override/apply")
async def apply_mame_config(request: Request, override_data: GameOverride):
    """Apply MAME .cfg file for specific game"""
    require_scope(request, "config")

    drive_root = request.app.state.drive_root
    mame_cfg_dir = drive_root / "config" / "mame" / "cfg"
    mame_cfg_dir.mkdir(parents=True, exist_ok=True)

    mapping_file = drive_root / "config" / "mappings" / "controls.json"
    with open(mapping_file, 'r') as f:
        mappings = json.load(f)['mappings']

    merged = {**mappings, **override_data.mappings}

    writer = MAMEConfigWriter()
    cfg_path = writer.generate_cfg(override_data.rom_name, merged, mame_cfg_dir)

    # Log
    log_controller_change(request, drive_root, "game_override_apply",
        {"rom": override_data.rom_name, "target_file": str(cfg_path)}, None)

    return {
        "status": "applied",
        "target_file": str(cfg_path),
        "rom": override_data.rom_name
    }

class GameOverride(BaseModel):
    rom_name: str
    mappings: Dict[str, Any]
```

---

### **Phase 3 Acceptance Criteria**

**CLI Tests:**
```bash
# 1. Preview MAME config
curl -X POST http://localhost:8000/api/local/controller/game-override/preview \
  -H "Content-Type: application/json" \
  -d '{"rom_name": "sf2", "mappings": {"p1.button1": {"pin": 1}}}'
# Expect: {"cfg_preview": "<mameconfig>...</mameconfig>"}

# 2. Apply MAME config
curl -X POST http://localhost:8000/api/local/controller/game-override/apply \
  -H "Content-Type: application/json" \
  -H "x-scope: config" \
  -d '{"rom_name": "sf2", "mappings": {"p1.button1": {"pin": 1}}}'
# Expect: {"status": "applied", "target_file": "config/mame/cfg/sf2.cfg"}

# 3. Verify file created
cat config/mame/cfg/sf2.cfg
# Expect: Valid XML with MAME config
```

---

## 📋 **IMPLEMENTATION CHECKLIST**

### **Phase 1: Core CRUD (Session 1-2)**
- [ ] Create `config/mappings/controls.json` with schema
- [ ] Create `config/mappings/factory-default.json` (Greg's golden config)
- [ ] Create `backend/routers/controller.py`
  - [ ] Copy Pydantic models from LED Blinky
  - [ ] `GET /mapping` - Return controls.json
  - [ ] `POST /mapping/preview` - Copy LED Blinky pattern
  - [ ] `POST /mapping/apply` - Copy LED Blinky pattern + backup
  - [ ] `POST /mapping/reset` - Copy factory-default.json to controls.json
  - [ ] `log_controller_change()` helper
- [ ] Register router in `backend/app.py`
- [ ] Update `frontend/src/panels/controller/ControllerPanel.jsx`
  - [ ] Replace PLAYER_MAPPINGS with API fetch
  - [ ] Add preview/apply workflow
  - [ ] Add Factory Reset button
- [ ] Test CLI endpoints (curl)
- [ ] Test UI (mapping table, preview, apply, reset)
- [ ] Verify backups created in `backups/{date}/`
- [ ] Verify logs in `logs/changes.jsonl`

### **Phase 2: USB Detection (Session 3)**
- [ ] Add `pyusb>=1.2.1` to `backend/requirements.txt`
- [ ] Run `pip install pyusb`
- [ ] Create `backend/services/usb_detection.py`
  - [ ] `USBBoardDetector` class
  - [ ] `detect_board()` method
  - [ ] KNOWN_BOARDS dict (PacDrive, I-PAC2, Zero Delay)
- [ ] Add `GET /board` endpoint in controller.py
- [ ] Update frontend to show board status tile
- [ ] Test with board connected
- [ ] Test without board (fallback to device list)

### **Phase 3: Live Testing + MAME (Session 4)**
- [ ] Create `backend/services/mame_config_writer.py`
  - [ ] `MAMEConfigWriter` class
  - [ ] `generate_cfg()` method (XML generation)
- [ ] Add MAME config endpoints
  - [ ] `POST /game-override/preview`
  - [ ] `POST /game-override/apply`
- [ ] Test MAME config generation (sf2.cfg)
- [ ] Live button test (if time allows - complexity: MEDIUM)

### **Phase 4: Validation & Polish (Session 5)**
- [ ] Add validation logic
  - [ ] Duplicate pin detection
  - [ ] Unmapped critical buttons warning
  - [ ] Invalid pin numbers (outside board range)
- [ ] Error banners in UI
  - [ ] Board not detected
  - [ ] Duplicate pin assignment
- [ ] Voice guidance (Chuck speaks via TTS) - OPTIONAL
- [ ] Smoke tests
- [ ] Full acceptance test run

---

## 🎯 **SUCCESS METRICS**

### **Must Have (Blocking):**
- [ ] Mapping Dictionary (controls.json) exists and loads
- [ ] Preview → Apply → Backup workflow works
- [ ] Factory Reset restores Greg's config
- [ ] Logs every change to changes.jsonl
- [ ] LED Blinky can read from controls.json (integration test)

### **Should Have:**
- [ ] USB board detection works
- [ ] MAME .cfg generation works for 1 game (sf2)
- [ ] Validation catches duplicate pins

### **Nice to Have:**
- [ ] Live button test mode
- [ ] Board mode detection (Twinstick, Turbo)
- [ ] Voice guidance (Chuck's Brooklyn accent)

---

## 🔗 **DEPENDENCIES**

**Chuck Depends On:**
- LED Blinky router pattern (template)
- Backup/diff/policies services (exist)
- Python 3.12 (installed)

**Depends On Chuck:**
- LED Blinky (reads controls.json for button illumination)
- Console Wizard (reads controls.json for RetroArch configs)
- MAME launch (reads .cfg files)

---

## 📞 **CONTACT & HANDOFF**

**Owner:** Greg
**Priority:** CRITICAL (foundation for all input panels)
**Estimated Time:** 4-5 sessions (2-3 hours each)

**For Next Developer:**
1. Read this plan top-to-bottom
2. Start with Phase 1 (Core CRUD) - testable without hardware
3. Copy LED Blinky pattern exactly (don't reinvent)
4. Test CLI endpoints before touching frontend
5. Use curl acceptance tests to verify each step
6. Phase 2-4 can be done in any order after Phase 1 complete

**Questions?** Reference:
- `backend/routers/led_blinky.py` (perfect template)
- `CLAUDE.md` (architectural patterns)
- This plan (comprehensive checklist)

---

**Status:** Ready for implementation
**Last Updated:** 2025-10-16
**Next Session:** Phase 1 - Core CRUD
