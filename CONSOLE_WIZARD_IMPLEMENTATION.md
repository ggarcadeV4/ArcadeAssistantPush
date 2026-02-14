# Console Wizard - Implementation Plan
**Character:** Wiz - Old sage, handheld controller configuration expert
**Purpose:** Map handheld controllers (Xbox, PS4, Switch) to RetroArch/emulators
**Priority:** P1 - Completes input configuration system alongside Controller Chuck
**Status:** ✅ READY TO START (Controller Chuck prerequisites satisfied)
**Last Updated:** 2025-10-16

## 🎯 STATUS UPDATE (2025-10-16)

**Prerequisites Status:**
- ✅ Controller Chuck complete (6/6 sessions)
- ✅ Mapping Dictionary exists (`config/mappings/controls.json`)
- ✅ USB detection infrastructure ready (`backend/services/usb_detector.py`)
- ✅ Preview/apply/reset pattern validated
- ✅ Backup/logging system proven

**Console Wizard is NOW UNBLOCKED and ready for Session 1!**

---

## 📖 **SESSION-BY-SESSION IMPLEMENTATION GUIDE**

**IMPORTANT:** Use this guide to track progress and resume after context breaks.

### **How to Use This Guide:**
1. **PREREQUISITE:** ✅ Controller Chuck Phase 1-2 complete (controls.json exists)
2. Read the current session section completely before coding
3. Complete ALL tasks in the session before moving to next
4. Run acceptance tests at end of each session
5. Update the ✅ checkboxes as you complete tasks
6. If interrupted mid-session, start from the last unchecked task

---

### **SESSION 1: Controller Detection + Profiles (2-3 hours)**

**Goal:** Detect handheld controllers and load controller profiles

**Prerequisites:**
- ✅ Controller Chuck Phase 1 complete (`config/mappings/controls.json` exists)
- ✅ pyusb installed (from Chuck Phase 2)

**Tasks:**
- [ ] 1.1: Create controller profile directories
  ```bash
  mkdir -p backend/data/controller_profiles
  ```

- [ ] 1.2: Create controller profile JSON files
  - Create `backend/data/controller_profiles/xbox_360.json` (copy from section 1.2)
  - Create `backend/data/controller_profiles/ps4_dualshock.json` (copy from section 1.2)
  - Create `backend/data/controller_profiles/switch_pro.json` (similar structure)

- [ ] 1.3: Create `backend/services/controller_detection.py`
  - Copy ControllerDetector class from section 1.1
  - Add KNOWN_CONTROLLERS dict (Xbox, PS4, Switch)
  - Implement detect_controllers() method (returns list of connected controllers)

- [ ] 1.4: Create `backend/routers/console_wizard.py`
  - Copy imports from led_blinky.py or controller.py
  - Create router instance: `router = APIRouter()`
  - Implement `GET /controllers` endpoint (section 1.3)
  - Implement `GET /profiles` endpoint (list all profile JSONs)
  - Implement `GET /profiles/{profile_id}` endpoint (get specific profile)

- [ ] 1.5: Register router in `backend/app.py`
  ```python
  from backend.routers import console_wizard
  app.include_router(console_wizard.router, prefix="/api/local/console-wizard", tags=["console_wizard"])
  ```

- [ ] 1.6: Test endpoints
  ```bash
  # Detect controllers
  curl http://localhost:8000/api/local/console-wizard/controllers
  # Expect: {"status": "success", "controllers": [...], "count": N}

  # List profiles
  curl http://localhost:8000/api/local/console-wizard/profiles
  # Expect: {"profiles": [{"id": "xbox_360", "name": "Xbox 360 Controller", "type": "xinput"}]}

  # Get specific profile
  curl http://localhost:8000/api/local/console-wizard/profiles/xbox_360
  # Expect: Full profile JSON
  ```

**Acceptance Criteria:**
- ✅ 3 profile JSON files exist in `backend/data/controller_profiles/`
- ✅ controller_detection.py exists with ControllerDetector class
- ✅ console_wizard.py router exists with 3 endpoints
- ✅ Router registered in app.py
- ✅ All curl tests return valid JSON (not 404/500)

**If Interrupted:** Check which files exist. Resume from first missing file/endpoint.

---

### **SESSION 2: RetroArch Config Generation (2-3 hours)**

**Goal:** Generate RetroArch .cfg files from controller mappings

**Prerequisites:** Session 1 complete (controller detection working)

**Tasks:**
- [ ] 2.1: Create `backend/services/retroarch_config_writer.py`
  - Copy RetroArchConfigWriter class from section 2.1
  - Implement RETROARCH_BUTTON_MAP dict
  - Implement generate_config() method (writes .cfg file)
  - Implement generate_autoconfig() method (for autodetect)

- [ ] 2.2: Add Pydantic models to console_wizard.py
  ```python
  class ControllerMapping(BaseModel):
      controller_type: str  # "xinput", "dinput", "sdl"
      mappings: Dict[str, str]

  class RetroArchConfig(BaseModel):
      core: str  # e.g., "mame", "snes9x"
      player: int  # 1-4
      mappings: Dict[str, Any]
  ```

- [ ] 2.3: Add RetroArch config endpoints
  - `POST /retroarch/config/preview` (section 2.2)
  - `POST /retroarch/config/apply` (section 2.2)
  - Add log_wizard_change() helper (copy from Chuck)

- [ ] 2.4: Test RetroArch config generation
  ```bash
  # Preview config
  curl -X POST http://localhost:8000/api/local/console-wizard/retroarch/config/preview \
    -H "Content-Type: application/json" \
    -d '{"core": "mame", "player": 1, "mappings": {}}'
  # Expect: {"preview": "...", "core": "mame", "player": 1}

  # Apply config
  curl -X POST http://localhost:8000/api/local/console-wizard/retroarch/config/apply \
    -H "Content-Type: application/json" \
    -H "x-scope: config" \
    -d '{"core": "mame", "player": 1, "mappings": {}}'
  # Expect: {"status": "applied", "config_file": "..."}

  # Verify file created
  ls -la config/retroarch/configs/
  ```

**Acceptance Criteria:**
- ✅ retroarch_config_writer.py exists
- ✅ Preview endpoint returns config text
- ✅ Apply endpoint creates .cfg file
- ✅ Config file is valid (check with cat)
- ✅ Log entry in changes.jsonl

**If Interrupted:** Check if retroarch_config_writer.py exists. Resume endpoint implementation.

---

### **SESSION 3: Frontend Panel (2-3 hours)**

**Goal:** Create Console Wizard React panel

**Prerequisites:** Session 2 complete (backend working)

**Tasks:**
- [ ] 3.1: Create frontend directory
  ```bash
  mkdir -p frontend/src/panels/console-wizard
  ```

- [ ] 3.2: Create `frontend/src/panels/console-wizard/ConsoleWizardPanel.jsx`
  - Copy structure from section 3.1
  - Add state for controllers, selectedController, mappings
  - Add useEffect to fetch controllers on mount
  - Create controller detection display
  - Create controller selection cards

- [ ] 3.3: Add controller mapping table
  - Similar to Chuck's mapping table
  - Show button → RetroArch input mappings
  - Add Edit buttons (can wire later)

- [ ] 3.4: Add Wiz chat sidebar
  - Copy pattern from Chuck's chat sidebar
  - Use `/wiz-avatar.jpeg`
  - Wiz personality: old sage, calm, wise

- [ ] 3.5: Register route in `frontend/src/App.jsx`
  ```jsx
  import ConsoleWizardPanel from './panels/console-wizard/ConsoleWizardPanel';
  // In routes:
  <Route path="/console-wizard" element={<ConsoleWizardPanel />} />
  ```

- [ ] 3.6: Test UI
  - Open http://localhost:8787/console-wizard
  - Should see controller detection section
  - Should see "No controllers detected" or list of controllers
  - Wiz chat sidebar should toggle

**Acceptance Criteria:**
- ✅ ConsoleWizardPanel.jsx exists
- ✅ Route registered in App.jsx
- ✅ Panel loads without errors
- ✅ Controller detection displays
- ✅ Wiz chat sidebar works

**If Interrupted:** Check which component exists. Continue from missing piece.

---

### **SESSION 4: Chuck Integration (Cascade Effect) (1-2 hours)**

**Goal:** Read Chuck's Mapping Dictionary and suggest mappings

**Prerequisites:** Session 3 complete (UI working)

**Tasks:**
- [ ] 4.1: Add `GET /cabinet-layout` endpoint in console_wizard.py
  - Read from `config/mappings/controls.json`
  - Parse Chuck's mappings
  - Return cabinet button layout
  - Handle case where controls.json doesn't exist yet

- [ ] 4.2: Update frontend to fetch cabinet layout
  ```jsx
  useEffect(() => {
    // Fetch cabinet layout from Chuck
    fetch('http://localhost:8000/api/local/console-wizard/cabinet-layout')
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          setCabinetLayout(data.cabinet_layout);
        }
      });
  }, []);
  ```

- [ ] 4.3: Add "suggested mapping" feature
  - When user selects Xbox controller, show:
    > "Your cabinet has 8 buttons for Player 1. I'll map the Xbox controller to match."
  - Display suggested button mappings

- [ ] 4.4: Test cascade effect
  - Verify GET /cabinet-layout returns Chuck's data
  - Verify UI shows cabinet layout info
  - Update Chuck's controls.json → reload Wizard → see updated suggestion

**Acceptance Criteria:**
- ✅ GET /cabinet-layout endpoint works
- ✅ Returns Chuck's mapping structure
- ✅ Frontend displays cabinet layout
- ✅ Suggested mappings shown to user
- ✅ Cascade works (Chuck update → Wizard sees it)

**If Interrupted:** Check if endpoint exists. Resume frontend integration.

---

### **PROGRESS TRACKING**

**Current Status:** Ready to Start (Controller Chuck complete ✅)

**Completed Sessions:** (update as you go)
- [ ] Session 1: Controller Detection + Profiles - READY TO START
- [ ] Session 2: RetroArch Config Generation
- [ ] Session 3: Frontend Panel
- [ ] Session 4: Chuck Integration

**Next Session:** Session 1 (Controller Detection + Profiles)

**Blocked?** ✅ UNBLOCKED - Chuck complete, all prerequisites satisfied

---

### **RESUME INSTRUCTIONS (If Context Breaks)**

1. **Verify prerequisites:**
   ```bash
   # Check if Chuck's mapping exists
   cat config/mappings/controls.json
   # If this fails, DO NOT proceed with Wizard
   ```

2. **Check file system:**
   ```bash
   ls -la backend/data/controller_profiles/
   ls -la backend/routers/console_wizard.py
   ls -la backend/services/controller_detection.py
   ls -la frontend/src/panels/console-wizard/
   ```

3. **Test endpoints:**
   ```bash
   curl http://localhost:8000/api/local/console-wizard/controllers
   curl http://localhost:8000/api/local/console-wizard/profiles
   curl http://localhost:8000/api/local/console-wizard/cabinet-layout
   ```

4. **Find last completed session:**
   - If no profile JSONs exist → Resume at Session 1, step 1.2
   - If profiles exist but no router → Resume at Session 1, step 1.4
   - If router exists but no retroarch_config_writer.py → Resume at Session 2
   - If backend works but no frontend → Resume at Session 3
   - If frontend works but no cabinet-layout endpoint → Resume at Session 4

5. **Read relevant section above and continue from first unchecked task**

---

### **INTEGRATION WITH CONTROLLER CHUCK**

**Dependency Flow:**
```
Controller Chuck creates controls.json (Session 1)
    ↓
Console Wizard reads controls.json (Session 4)
    ↓
Wizard suggests controller mappings based on cabinet layout
    ↓
Wizard generates RetroArch configs
    ↓
RetroArch loads configs → controller works in games
```

**Critical:**
- Wizard can be built independently (Sessions 1-3)
- But Session 4 (Chuck integration) requires Chuck's controls.json to exist
- Test cascade by updating Chuck → reload Wizard → see changes

---

## 🎯 **THE PROBLEM WIZ SOLVES**

**Scenario:** Customer has Xbox/PS4 controller → wants to play retro games → configs don't match
**Wiz's Solution:** Maps handheld controller buttons to RetroArch/emulator inputs
- Reads from Chuck's Mapping Dictionary (cascade effect)
- Generates RetroArch configs per-core
- Supports XInput, DirectInput, SDL controllers
- Per-game controller profiles

**Relationship with Controller Chuck:**
```
Chuck (Arcade Encoders)
    ↓ writes
Mapping Dictionary (controls.json)
    ↓ reads
Wiz (Handheld Controllers)
    ↓ generates
RetroArch Configs (.cfg files)
```

**Key Difference from Chuck:**
- **Chuck:** Physical encoder pins → Logical buttons (source of truth)
- **Wiz:** Handheld controller buttons → RetroArch/MAME mappings (reads from Chuck)

---

## 📁 **CURRENT STATE AUDIT**

### **❌ What Does NOT Exist**

#### **Frontend (0%)**
- ❌ No panel directory (`frontend/src/panels/console-wizard/`)
- ❌ No component file (need to create `ConsoleWizardPanel.jsx`)
- ✅ Avatar exists (`wiz-avatar.jpeg`)

#### **Backend (0%)**
- ❌ No router (`backend/routers/console_wizard.py`)
- ❌ No controller detection service
- ❌ No RetroArch config writer

#### **Config Files (0%)**
- ❌ No RetroArch configs directory
- ❌ No controller profile templates

---

### **✅ What CAN Be Reused**

#### **From Controller Chuck:**
- ✅ Preview/apply/backup pattern (copy controller.py)
- ✅ Mapping Dictionary structure (read from controls.json)
- ✅ Logging system (copy log helpers)
- ✅ Validation logic (duplicate checks, etc.)

#### **From LED Blinky:**
- ✅ Router template (led_blinky.py)
- ✅ Pydantic models pattern

#### **Existing Services:**
- ✅ `backend/services/backup.py`
- ✅ `backend/services/diffs.py`
- ✅ `backend/services/policies.py`

---

## 🛠️ **WHAT NEEDS TO BE BUILT**

### **Phase 1: Controller Detection + Profile System**

#### **1.1 Controller Detection Service**
**File:** `backend/services/controller_detection.py` (NEW)

**Purpose:** Detect Xbox, PS4, Switch Pro controllers via USB/Bluetooth

```python
import subprocess
from typing import Optional, Dict, List

class ControllerDetector:
    """Detect handheld gaming controllers"""

    KNOWN_CONTROLLERS = {
        # Xbox 360 Controller
        ("0x045E", "0x028E"): {"name": "Xbox 360 Controller", "type": "xinput"},
        # Xbox One Controller
        ("0x045E", "0x02EA"): {"name": "Xbox One Controller", "type": "xinput"},
        # PS4 DualShock 4
        ("0x054C", "0x05C4"): {"name": "PlayStation 4 Controller", "type": "dinput"},
        ("0x054C", "0x09CC"): {"name": "PlayStation 4 Controller (v2)", "type": "dinput"},
        # PS5 DualSense
        ("0x054C", "0x0CE6"): {"name": "PlayStation 5 DualSense", "type": "dinput"},
        # Nintendo Switch Pro
        ("0x057E", "0x2009"): {"name": "Switch Pro Controller", "type": "sdl"},
    }

    def detect_controllers(self) -> List[Dict]:
        """Detect all connected controllers

        Returns:
            List of detected controllers with vid, pid, name, type
        """
        import usb.core

        devices = usb.core.find(find_all=True)
        controllers = []

        for device in devices:
            vid = f"0x{device.idVendor:04X}"
            pid = f"0x{device.idProduct:04X}"
            key = (vid, pid)

            if key in self.KNOWN_CONTROLLERS:
                info = self.KNOWN_CONTROLLERS[key]
                controllers.append({
                    "vid": vid,
                    "pid": pid,
                    "name": info["name"],
                    "type": info["type"],
                    "detected": True
                })

        return controllers

    def test_controller_input(self, controller_index: int = 0) -> Dict:
        """Test controller input using SDL or XInput

        Args:
            controller_index: Controller index (0-3)

        Returns:
            Current button states
        """
        # TODO: Use pygame or python-xinput to read controller state
        # For now, return mock data
        return {
            "buttons": {
                "a": False,
                "b": False,
                "x": False,
                "y": False,
                "start": False,
                "select": False,
                "lb": False,
                "rb": False,
                "lt": 0.0,  # Analog trigger
                "rt": 0.0
            },
            "axes": {
                "left_x": 0.0,
                "left_y": 0.0,
                "right_x": 0.0,
                "right_y": 0.0
            }
        }
```

---

#### **1.2 Controller Profile Templates**
**Location:** `backend/data/controller_profiles/`

**File:** `backend/data/controller_profiles/xbox_360.json`
```json
{
  "name": "Xbox 360 Controller",
  "type": "xinput",
  "button_layout": {
    "a": "button_1",
    "b": "button_2",
    "x": "button_3",
    "y": "button_4",
    "lb": "button_5",
    "rb": "button_6",
    "lt": "button_7",
    "rt": "button_8",
    "start": "button_9",
    "select": "button_10",
    "left_stick": "button_11",
    "right_stick": "button_12",
    "dpad_up": "axis_1_up",
    "dpad_down": "axis_1_down",
    "dpad_left": "axis_0_left",
    "dpad_right": "axis_0_right"
  },
  "retroarch_mapping": {
    "input_player1_a": "1",
    "input_player1_b": "0",
    "input_player1_x": "3",
    "input_player1_y": "2",
    "input_player1_l": "4",
    "input_player1_r": "5",
    "input_player1_l2": "6",
    "input_player1_r2": "7",
    "input_player1_start": "9",
    "input_player1_select": "8"
  }
}
```

**File:** `backend/data/controller_profiles/ps4_dualshock.json`
```json
{
  "name": "PlayStation 4 Controller",
  "type": "dinput",
  "button_layout": {
    "cross": "button_2",
    "circle": "button_3",
    "square": "button_1",
    "triangle": "button_4",
    "l1": "button_5",
    "r1": "button_6",
    "l2": "button_7",
    "r2": "button_8",
    "share": "button_9",
    "options": "button_10",
    "l3": "button_11",
    "r3": "button_12",
    "ps": "button_13",
    "touchpad": "button_14"
  },
  "retroarch_mapping": {
    "input_player1_a": "2",
    "input_player1_b": "3",
    "input_player1_x": "1",
    "input_player1_y": "4",
    "input_player1_l": "5",
    "input_player1_r": "6",
    "input_player1_l2": "7",
    "input_player1_r2": "8",
    "input_player1_start": "10",
    "input_player1_select": "9"
  }
}
```

---

#### **1.3 Backend Router**
**File:** `backend/routers/console_wizard.py` (NEW - copy from controller.py)

```python
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from pathlib import Path
from typing import Dict, Any, Optional, List
import json
from datetime import datetime

from ..services.backup import create_backup
from ..services.diffs import compute_diff, has_changes
from ..services.policies import require_scope, is_allowed_file
from ..services.controller_detection import ControllerDetector

router = APIRouter()

# Pydantic models
class ControllerMapping(BaseModel):
    controller_type: str  # "xinput", "dinput", "sdl"
    mappings: Dict[str, str]  # e.g., {"a": "p1.button1", "b": "p1.button2"}

class RetroArchConfig(BaseModel):
    core: str  # e.g., "mame", "snes9x", "genesis_plus_gx"
    player: int  # 1-4
    mappings: Dict[str, Any]

@router.get("/controllers")
async def detect_controllers(request: Request):
    """Detect connected handheld controllers"""
    try:
        detector = ControllerDetector()
        controllers = detector.detect_controllers()

        return {
            "status": "success",
            "controllers": controllers,
            "count": len(controllers)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Controller detection failed: {str(e)}")

@router.get("/profiles")
async def list_controller_profiles(request: Request):
    """List available controller profiles"""
    profiles_dir = Path(__file__).parent.parent / "data" / "controller_profiles"

    if not profiles_dir.exists():
        return {"profiles": [], "count": 0}

    profiles = []
    for profile_file in profiles_dir.glob("*.json"):
        with open(profile_file, 'r') as f:
            data = json.load(f)
            profiles.append({
                "id": profile_file.stem,
                "name": data["name"],
                "type": data["type"]
            })

    return {
        "profiles": profiles,
        "count": len(profiles)
    }

@router.get("/profiles/{profile_id}")
async def get_controller_profile(request: Request, profile_id: str):
    """Get specific controller profile"""
    profiles_dir = Path(__file__).parent.parent / "data" / "controller_profiles"
    profile_file = profiles_dir / f"{profile_id}.json"

    if not profile_file.exists():
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile_id}")

    with open(profile_file, 'r') as f:
        data = json.load(f)

    return data

@router.post("/mapping/preview")
async def preview_controller_mapping(request: Request, mapping_data: ControllerMapping):
    """Preview controller mapping changes"""
    # TODO: Generate RetroArch config preview
    # Show how controller buttons map to emulator inputs
    return {
        "preview": "Generated RetroArch config preview",
        "has_changes": True
    }

@router.post("/mapping/apply")
async def apply_controller_mapping(request: Request, mapping_data: ControllerMapping):
    """Apply controller mapping (generate RetroArch configs)"""
    require_scope(request, "config")

    # TODO: Generate RetroArch .cfg files
    # Save to RetroArch config directory

    return {
        "status": "applied",
        "config_files": []
    }
```

---

### **Phase 2: RetroArch Config Generation**

#### **2.1 RetroArch Config Writer Service**
**File:** `backend/services/retroarch_config_writer.py` (NEW)

```python
from pathlib import Path
from typing import Dict
import configparser

class RetroArchConfigWriter:
    """Generate RetroArch controller configs"""

    RETROARCH_BUTTON_MAP = {
        # RetroPad layout
        "b": "input_player{}_b_btn",
        "y": "input_player{}_y_btn",
        "select": "input_player{}_select_btn",
        "start": "input_player{}_start_btn",
        "up": "input_player{}_up_btn",
        "down": "input_player{}_down_btn",
        "left": "input_player{}_left_btn",
        "right": "input_player{}_right_btn",
        "a": "input_player{}_a_btn",
        "x": "input_player{}_x_btn",
        "l": "input_player{}_l_btn",
        "r": "input_player{}_r_btn",
        "l2": "input_player{}_l2_btn",
        "r2": "input_player{}_r2_btn",
        "l3": "input_player{}_l3_btn",
        "r3": "input_player{}_r3_btn",
    }

    def generate_config(self, controller_profile: Dict, player: int, output_path: Path) -> Path:
        """Generate RetroArch .cfg file for controller

        Args:
            controller_profile: Controller profile JSON
            player: Player number (1-4)
            output_path: Path to RetroArch config directory

        Returns:
            Path to created .cfg file
        """
        cfg_file = output_path / f"controller_p{player}.cfg"

        config = configparser.ConfigParser()
        config.optionxform = str  # Preserve case

        # Map controller buttons to RetroArch inputs
        for button, retroarch_key in self.RETROARCH_BUTTON_MAP.items():
            key = retroarch_key.format(player)
            # Look up button in controller profile
            if button in controller_profile.get("button_layout", {}):
                value = controller_profile["button_layout"][button]
                config.set("DEFAULT", key, value)

        # Write to file
        with open(cfg_file, 'w') as f:
            config.write(f)

        return cfg_file

    def generate_autoconfig(self, controller_name: str, mappings: Dict, output_path: Path) -> Path:
        """Generate RetroArch autoconfig file

        AutoConfig files live in RetroArch/autoconfig/ and auto-detect controllers
        """
        safe_name = controller_name.replace(" ", "_").lower()
        cfg_file = output_path / f"{safe_name}.cfg"

        lines = [
            f'input_driver = "xinput"',
            f'input_device = "{controller_name}"',
            f'input_vendor_id = "1118"',
            f'input_product_id = "654"',
        ]

        # Add button mappings
        for retroarch_key, button_value in mappings.items():
            lines.append(f'{retroarch_key} = "{button_value}"')

        with open(cfg_file, 'w') as f:
            f.write('\n'.join(lines))

        return cfg_file
```

---

#### **2.2 RetroArch Config Endpoints**
**File:** `backend/routers/console_wizard.py`

**Add:**
```python
from ..services.retroarch_config_writer import RetroArchConfigWriter

@router.post("/retroarch/config/preview")
async def preview_retroarch_config(request: Request, config_data: RetroArchConfig):
    """Preview RetroArch config file"""
    # Load controller profile
    profiles_dir = Path(__file__).parent.parent / "data" / "controller_profiles"
    # Generate preview
    writer = RetroArchConfigWriter()
    preview_text = "# RetroArch Config Preview\n"
    # ... generate config text ...

    return {
        "preview": preview_text,
        "core": config_data.core,
        "player": config_data.player
    }

@router.post("/retroarch/config/apply")
async def apply_retroarch_config(request: Request, config_data: RetroArchConfig):
    """Apply RetroArch config"""
    require_scope(request, "config")

    drive_root = request.app.state.drive_root
    retroarch_cfg_dir = drive_root / "config" / "retroarch" / "configs"
    retroarch_cfg_dir.mkdir(parents=True, exist_ok=True)

    # Load controller profile
    profiles_dir = Path(__file__).parent.parent / "data" / "controller_profiles"
    # ... load profile ...

    # Generate config
    writer = RetroArchConfigWriter()
    cfg_path = writer.generate_config(profile_data, config_data.player, retroarch_cfg_dir)

    # Log
    log_wizard_change(request, drive_root, "retroarch_config_apply",
        {"core": config_data.core, "player": config_data.player, "file": str(cfg_path)}, None)

    return {
        "status": "applied",
        "config_file": str(cfg_path),
        "core": config_data.core
    }

def log_wizard_change(request: Request, drive_root: Path, action: str, details: Dict[str, Any], backup_path: Optional[Path] = None):
    """Log Console Wizard changes"""
    log_file = drive_root / "logs" / "changes.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    device = request.headers.get('x-device-id', 'unknown')
    panel = request.headers.get('x-panel', 'console_wizard')

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "scope": "console_wizard",
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

### **Phase 3: Frontend Panel**

#### **3.1 Create Panel Component**
**File:** `frontend/src/panels/console-wizard/ConsoleWizardPanel.jsx` (NEW)

**Pattern:** Similar to Controller Chuck but with controller image instead of cabinet

```jsx
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const CONTROLLER_TYPES = {
  xbox: { name: 'Xbox Controller', image: '/controllers/xbox.png' },
  ps4: { name: 'PlayStation 4', image: '/controllers/ps4.png' },
  switch: { name: 'Switch Pro', image: '/controllers/switch.png' }
};

export default function ConsoleWizardPanel() {
  const [controllers, setControllers] = useState([]);
  const [selectedController, setSelectedController] = useState(null);
  const [mappings, setMappings] = useState({});
  const [chatOpen, setChatOpen] = useState(false);

  useEffect(() => {
    // Detect controllers on mount
    fetch('http://localhost:8000/api/local/console-wizard/controllers')
      .then(res => res.json())
      .then(data => setControllers(data.controllers))
      .catch(err => console.error('Failed to detect controllers:', err));
  }, []);

  return (
    <div className="console-wizard-panel">
      <div className="wizard-header">
        <img src="/wiz-avatar.jpeg" alt="Wiz" className="wizard-avatar" />
        <h1>Console Wizard</h1>
        <p>Configure handheld controllers for retro gaming</p>
      </div>

      <div className="wizard-content">
        {/* Controller Detection */}
        <div className="controller-detection">
          <h2>Detected Controllers</h2>
          {controllers.length === 0 ? (
            <div className="no-controllers">
              <p>No controllers detected</p>
              <button onClick={() => window.location.reload()}>Retry</button>
            </div>
          ) : (
            <div className="controller-list">
              {controllers.map((ctrl, idx) => (
                <div
                  key={idx}
                  className={`controller-card ${selectedController === idx ? 'selected' : ''}`}
                  onClick={() => setSelectedController(idx)}
                >
                  <div className="controller-icon">🎮</div>
                  <div>{ctrl.name}</div>
                  <div className="controller-type">{ctrl.type.toUpperCase()}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Controller Mapping */}
        {selectedController !== null && (
          <div className="controller-mapping">
            <h2>Button Mapping</h2>
            <div className="controller-image">
              {/* TODO: Add controller diagram */}
              <img src="/controllers/generic.png" alt="Controller" />
            </div>
            <div className="mapping-table">
              {/* TODO: Mapping table like Chuck */}
            </div>
          </div>
        )}
      </div>

      {/* Chat Sidebar with Wiz */}
      {chatOpen && (
        <div className="wizard-chat-sidebar">
          <div className="chat-header">
            <img src="/wiz-avatar.jpeg" alt="Wiz" className="chat-avatar" />
            <h4>Wiz - Console Wizard</h4>
            <button onClick={() => setChatOpen(false)}>✕</button>
          </div>
          {/* Chat messages */}
        </div>
      )}

      <button className="chat-toggle" onClick={() => setChatOpen(!chatOpen)}>
        {chatOpen ? '✕' : '💬'}
      </button>
    </div>
  );
}
```

---

#### **3.2 Register Panel Route**
**File:** `frontend/src/App.jsx` or routing config

**Add:**
```jsx
import ConsoleWizardPanel from './panels/console-wizard/ConsoleWizardPanel';

// In routes:
<Route path="/console-wizard" element={<ConsoleWizardPanel />} />
```

---

### **Phase 4: Integration with Controller Chuck**

#### **4.1 Read from Chuck's Mapping Dictionary**
**Pattern:** Console Wizard reads `controls.json` to understand cabinet layout

**File:** `backend/routers/console_wizard.py`

**Add:**
```python
@router.get("/cabinet-layout")
async def get_cabinet_layout(request: Request):
    """Get cabinet layout from Controller Chuck's Mapping Dictionary

    This allows Wiz to suggest mappings based on cabinet setup
    """
    drive_root = request.app.state.drive_root
    controls_file = drive_root / "config" / "mappings" / "controls.json"

    if not controls_file.exists():
        return {
            "status": "no_chuck_mapping",
            "message": "Controller Chuck not configured yet"
        }

    with open(controls_file, 'r') as f:
        chuck_data = json.load(f)

    # Extract button layout
    layout = {}
    for key, value in chuck_data['mappings'].items():
        player, button = key.split('.')
        if player not in layout:
            layout[player] = {}
        layout[player][button] = value

    return {
        "status": "success",
        "cabinet_layout": layout,
        "board": chuck_data.get('board', {})
    }
```

**Use Case:** When user selects Xbox controller, Wiz can say:
> "I see your cabinet has 8 buttons for Player 1. I'll map the Xbox controller to match that layout."

---

## 📋 **IMPLEMENTATION CHECKLIST**

### **Phase 1: Controller Detection (Session 1)**
- [ ] Create `backend/services/controller_detection.py`
  - [ ] `ControllerDetector` class
  - [ ] KNOWN_CONTROLLERS dict (Xbox, PS4, Switch)
  - [ ] `detect_controllers()` method
- [ ] Create `backend/data/controller_profiles/`
  - [ ] `xbox_360.json`
  - [ ] `ps4_dualshock.json`
  - [ ] `switch_pro.json`
- [ ] Create `backend/routers/console_wizard.py`
  - [ ] `GET /controllers` - Detect controllers
  - [ ] `GET /profiles` - List profiles
  - [ ] `GET /profiles/{id}` - Get profile
- [ ] Register router in `backend/app.py`
- [ ] Test CLI (curl endpoints)

### **Phase 2: RetroArch Config Generation (Session 2)**
- [ ] Create `backend/services/retroarch_config_writer.py`
  - [ ] `RetroArchConfigWriter` class
  - [ ] `generate_config()` method
  - [ ] `generate_autoconfig()` method
- [ ] Add RetroArch endpoints in console_wizard.py
  - [ ] `POST /retroarch/config/preview`
  - [ ] `POST /retroarch/config/apply`
- [ ] Test config generation (curl)
- [ ] Verify .cfg files created in `config/retroarch/`

### **Phase 3: Frontend Panel (Session 3)**
- [ ] Create `frontend/src/panels/console-wizard/`
- [ ] Create `ConsoleWizardPanel.jsx`
  - [ ] Controller detection display
  - [ ] Controller selection
  - [ ] Mapping table
  - [ ] Chat sidebar with Wiz
- [ ] Add controller images to `/public/controllers/`
- [ ] Register route in `App.jsx`
- [ ] Test UI (detect, select, map)

### **Phase 4: Chuck Integration (Session 4)**
- [ ] Add `GET /cabinet-layout` endpoint
- [ ] Frontend: Fetch cabinet layout from Chuck
- [ ] Show suggested mappings based on cabinet
- [ ] Test integration (Chuck → Wiz cascade)

---

## 🎯 **SUCCESS METRICS**

### **Must Have:**
- [ ] Detects Xbox/PS4/Switch controllers
- [ ] Generates RetroArch .cfg files
- [ ] Reads from Chuck's Mapping Dictionary
- [ ] Logs to changes.jsonl
- [ ] Preview/apply workflow

### **Should Have:**
- [ ] 3 controller profiles (Xbox, PS4, Switch)
- [ ] Per-core RetroArch configs
- [ ] Wiz chat personality (old sage)

### **Nice to Have:**
- [ ] Controller button test mode
- [ ] Visual controller diagram
- [ ] Per-game controller profiles

---

## 🔗 **DEPENDENCIES**

**Wiz Depends On:**
- Controller Chuck (reads from controls.json)
- USB detection (reuse from Chuck)
- Backup/diff services (exist)

**Depends On Wiz:**
- RetroArch emulators (read generated .cfg files)

**Cascade Flow:**
```
1. Chuck creates controls.json (arcade layout)
2. Wiz reads controls.json (understands cabinet)
3. Wiz generates RetroArch configs (map handheld → cabinet)
4. RetroArch loads configs (controller works in games)
```

---

## 📝 **KEY DIFFERENCES FROM CONTROLLER CHUCK**

| Aspect | Controller Chuck | Console Wizard |
|--------|------------------|----------------|
| **Target Hardware** | Arcade encoder boards (PacDrive, I-PAC) | Handheld controllers (Xbox, PS4, Switch) |
| **Detection** | USB VID/PID for encoders | USB VID/PID for controllers |
| **Input Source** | Physical pins (1-32) | Controller buttons (A, B, X, Y, etc.) |
| **Output Format** | MAME XML (.cfg) | RetroArch config (.cfg) |
| **Data Flow** | WRITES Mapping Dictionary | READS Mapping Dictionary |
| **UI** | Cabinet visualization (4 players) | Controller image |
| **Personality** | Chuck - Brooklyn mechanic | Wiz - Old sage |
| **Priority** | CRITICAL (foundation) | CRITICAL (completes input system) |

---

## 📞 **CONTACT & HANDOFF**

**Owner:** Greg
**Priority:** CRITICAL (completes input configuration alongside Chuck)
**Estimated Time:** 4 sessions (2-3 hours each)

**For Next Developer:**
1. Build Controller Chuck FIRST (Wiz depends on Chuck's controls.json)
2. Copy Chuck's pattern (90% same logic, different output)
3. Focus on Phase 1-2 (detection + config generation)
4. Phase 3-4 can wait (frontend polish)

**Questions?** Reference:
- `backend/routers/controller.py` (Chuck's router - copy pattern)
- `backend/routers/led_blinky.py` (preview/apply template)
- `CONTROLLER_CHUCK_IMPLEMENTATION.md` (sister panel)

---

**Status:** Ready for implementation (after Controller Chuck complete)
**Last Updated:** 2025-10-16
**Next Session:** Phase 1 - Controller Detection
