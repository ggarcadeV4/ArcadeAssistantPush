# ARCADE ASSISTANT - ARCHITECTURAL DOCTRINE
## NON-NEGOTIABLE RULES FOR ALL AI AGENTS

**Last Updated:** 2025-10-05
**Status:** LOCKED - Changes require explicit user approval
**Drive Structure Confirmed:** ✅ Screenshots verified

---

## ⚠️ CRITICAL: READ THIS FIRST

**This architecture is based on REAL-WORLD EXPERIENCE, not theory.**

Any AI agent (Claude, Codex, Gemini, ChatGPT, etc.) working on this codebase MUST:
1. **READ THIS FILE BEFORE making ANY path-related changes**
2. **NEVER introduce dynamic file finding** - it fails after 2-3 interactions
3. **NEVER add "where is your..." dialogs** - use fixed paths ONLY
4. **ALWAYS use the exact paths documented below**

**Violations of these rules will be rejected immediately.**

---

## Core Architectural Principle

**THE ARCADE ASSISTANT USES A FIXED STRUCTURE ARCHITECTURE.**

- ❌ NO dynamic file finding
- ❌ NO user-defined paths
- ❌ NO "browse for folder" dialogs
- ✅ ONLY hardcoded paths relative to `AA_DRIVE_ROOT`
- ✅ ONLY validation at startup
- ✅ ONLY clear error messages if structure is wrong

**Why?** AI agents lose context after 2-3 user interactions. Dynamic path configuration creates:
- Error cascades
- Lost settings
- User frustration
- Broken functionality

**The solution:** Fixed paths that work every time.

---

## The Two-Drive Architecture

### C: Drive - Application Code (ALWAYS runs from here)

```
C:\Arcade Assistant Local\
├── frontend/              # React UI (Vite dev server on port 5173)
├── gateway/               # Node.js BFF (serves on port 8787)
├── backend/               # FastAPI services (port 8000)
├── .env                   # Environment config: AA_DRIVE_ROOT=A:\
├── CLAUDE.md              # Development guidelines
├── ARCHITECTURE.md        # THIS FILE (architectural doctrine)
└── package.json           # Root package with dev scripts
```

**The application MUST run from C: drive.** Windows expects applications on C:.

### A: Drive - Content & Data (FIXED structure - CONFIRMED via screenshots)

```
A:\                                    # 4TB SSD "G and G Arcade"
├── LaunchBox\                        # ← LaunchBox installation
│   ├── Data\
│   │   └── Platforms\
│   │       ├── Arcade.xml           # Arcade platform games
│   │       ├── NES.xml              # NES platform games
│   │       ├── SNES.xml             # SNES platform games
│   │       └── [OTHER_PLATFORMS].xml
│   ├── Images\                      # Game artwork
│   ├── Videos\                      # Game videos
│   └── ThirdParty\                  # Plugins
│
├── Emulators\                        # ← All emulator installations
│   ├── MAME\
│   │   └── mame.exe
│   ├── RetroArch\
│   │   └── retroarch.exe
│   └── [OTHER_EMULATORS]\
│
├── Roms\                             # ← Arcade ROMs (lowercase 'o')
│   ├── MAME\
│   └── [OTHER_ARCADE_SYSTEMS]\
│
├── Console ROMs\                     # ← Console ROMs
│   ├── NES\
│   ├── SNES\
│   └── [OTHER_CONSOLES]\
│
├── Bios\                             # ← BIOS files for emulators
│   ├── mame\
│   ├── retroarch\
│   └── [OTHER_SYSTEMS]\
│
├── Gun Build\                        # ← Light gun calibration configs
│   └── [LIGHT_GUN_CONFIGS]
│
├── ThirdScreen-v5.0.12\             # ← Third screen software
│
├── Tools\                            # ← Utilities and tools
│
└── INSTALL\                          # ← Installation files
```

**This structure is LOCKED. No dynamic discovery. Period.**

---

## Non-Negotiable Path Rules

### Rule 1: Use Environment Variable for A: Drive Root

**ALWAYS** use `AA_DRIVE_ROOT` environment variable:

```python
# Python example - CORRECT
import os
LAUNCHBOX_ROOT = os.path.join(os.getenv('AA_DRIVE_ROOT'), 'LaunchBox')
ARCADE_XML = os.path.join(LAUNCHBOX_ROOT, 'Data', 'Platforms', 'Arcade.xml')
MAME_EXE = os.path.join(os.getenv('AA_DRIVE_ROOT'), 'Emulators', 'MAME', 'mame.exe')
```

```javascript
// JavaScript example - CORRECT
import path from 'path';
const LAUNCHBOX_ROOT = path.join(process.env.AA_DRIVE_ROOT, 'LaunchBox');
const ARCADE_XML = path.join(LAUNCHBOX_ROOT, 'Data', 'Platforms', 'Arcade.xml');
const MAME_EXE = path.join(process.env.AA_DRIVE_ROOT, 'Emulators', 'MAME', 'mame.exe');
```

**NEVER** hardcode `A:\` directly - always use `AA_DRIVE_ROOT`.

### Rule 2: Validate at Startup, Not Runtime

On application startup (gateway/backend initialization):

1. ✅ Check `AA_DRIVE_ROOT` environment variable is set
2. ✅ Verify A: drive is accessible (`fs.existsSync()` / `os.path.exists()`)
3. ✅ Validate critical files exist:
   - LaunchBox XML files
   - Emulator executables
   - Required BIOS files
4. ✅ **FAIL FAST** with clear error message if structure is wrong

**Example error message:**
```
ERROR: LaunchBox XML not found!
Expected location: A:\LaunchBox\Data\Platforms\Arcade.xml

Please ensure:
1. A: drive is connected (4TB SSD "G and G Arcade")
2. LaunchBox is installed at A:\LaunchBox\
3. Arcade platform is configured in LaunchBox

Current AA_DRIVE_ROOT: A:\
```

### Rule 3: NO Dynamic File Finding - EVER

❌ **FORBIDDEN PATTERNS:**
```python
# NEVER DO THIS
def find_launchbox():
    for drive in ['A:', 'C:', 'D:', 'E:']:
        if os.path.exists(f"{drive}\\LaunchBox"):
            return f"{drive}\\LaunchBox"
```

```javascript
// NEVER DO THIS
async function findMAME() {
  const paths = ['/Emulators/MAME', '/MAME', '/Games/MAME'];
  for (const p of paths) {
    if (await exists(p)) return p;
  }
}
```

✅ **CORRECT PATTERN:**
```python
# ALWAYS DO THIS
def get_launchbox_path():
    return os.path.join(os.getenv('AA_DRIVE_ROOT'), 'LaunchBox')

# If file doesn't exist, raise clear error - don't search
```

### Rule 4: No User Path Configuration

❌ **NEVER implement:**
- "Browse for LaunchBox folder" dialogs
- "Select emulator directory" prompts
- "Where are your ROMs?" questions
- Settings page with path inputs

✅ **INSTEAD provide:**
- Clear documentation of required structure
- Startup validation with actionable errors
- One-time setup guide (not runtime configuration)

---

## Confirmed Hardcoded Paths

### LaunchBox Panel (LoRa)
```python
LAUNCHBOX_ROOT = os.path.join(os.getenv('AA_DRIVE_ROOT'), 'LaunchBox')
PLATFORMS_DIR = os.path.join(LAUNCHBOX_ROOT, 'Data', 'Platforms')

# Platform XMLs
ARCADE_XML = os.path.join(PLATFORMS_DIR, 'Arcade.xml')
NES_XML = os.path.join(PLATFORMS_DIR, 'NES.xml')
SNES_XML = os.path.join(PLATFORMS_DIR, 'SNES.xml')

# Images
IMAGES_DIR = os.path.join(LAUNCHBOX_ROOT, 'Images')
```

### Emulator Paths
```python
EMULATORS_ROOT = os.path.join(os.getenv('AA_DRIVE_ROOT'), 'Emulators')

MAME_EXE = os.path.join(EMULATORS_ROOT, 'MAME', 'mame.exe')
RETROARCH_EXE = os.path.join(EMULATORS_ROOT, 'RetroArch', 'retroarch.exe')
```

### ROM Paths
```python
ARCADE_ROMS = os.path.join(os.getenv('AA_DRIVE_ROOT'), 'Roms')  # lowercase 'o'
CONSOLE_ROMS = os.path.join(os.getenv('AA_DRIVE_ROOT'), 'Console ROMs')

NES_ROMS = os.path.join(CONSOLE_ROMS, 'NES')
SNES_ROMS = os.path.join(CONSOLE_ROMS, 'SNES')
```

### BIOS Files
```python
BIOS_ROOT = os.path.join(os.getenv('AA_DRIVE_ROOT'), 'Bios')

MAME_BIOS = os.path.join(BIOS_ROOT, 'mame')
RETROARCH_BIOS = os.path.join(BIOS_ROOT, 'retroarch')
```

### Light Gun Configuration
```python
GUN_BUILD_ROOT = os.path.join(os.getenv('AA_DRIVE_ROOT'), 'Gun Build')
```

### Utilities
```python
TOOLS_ROOT = os.path.join(os.getenv('AA_DRIVE_ROOT'), 'Tools')
THIRDSCREEN_ROOT = os.path.join(os.getenv('AA_DRIVE_ROOT'), 'ThirdScreen-v5.0.12')
```

---

## Panel-Specific Path Requirements

### LaunchBox LoRa Panel
- **Purpose:** Game library management, launching games
- **Required paths:**
  - `A:\LaunchBox\Data\Platforms\*.xml` (platform data)
  - `A:\LaunchBox\Images\` (artwork)
  - Emulator executables in `A:\Emulators\`
- **No dynamic discovery** - if XML doesn't exist, show error with expected path

### LED Blinky Panel
- **Purpose:** Button LED control via LED-Wiz hardware
- **Driver location:** `C:\Arcade Assistant Local\backend\services\led_engine\`
- **Config location:** `C:\Arcade Assistant Local\config\led_mapping.json`
- **Required components:**
  - `ledwiz_direct.py` - Python ctypes HID driver (Named Pipe daemon)
  - `led_enhancement_demo.py` - Visual stress test (Gamma 2.5, color scaling)
  - `roll_call.py` - Port mapping diagnostic (lights ports 1-32 sequentially)
- **Hardware:** LED-Wiz boards (VID: 0xFAFA, PIDs: 0x00F0-0x00FF)
- **No runtime path finding** - uses fixed config path

---

## LED Calibration Wizard (Future Feature)

### Concept: Interactive GUI-Driven Port Mapping

The LED-Wiz hardware uses port numbers 1-32 per board, but physical cabinet wiring
varies. Instead of hardcoding port assignments, the Calibration Wizard will allow
users to create a mapping between logical button names and physical port numbers.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    LED CALIBRATION WIZARD                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────────┐         ┌──────────────┐                    │
│   │   Backend    │  Named  │   Gateway    │   WebSocket        │
│   │  ledwiz_     │ ───────►│  aa-blinky   │◄─────────────────► │
│   │  direct.py   │  Pipe   │   gem        │                    │
│   └──────────────┘         └──────────────┘                    │
│          │                        │                             │
│          │                        │                             │
│          ▼                        ▼                             │
│   ┌──────────────┐         ┌──────────────┐                    │
│   │  LED-Wiz     │         │   Frontend   │                    │
│   │  Hardware    │         │   Wizard UI  │                    │
│   └──────────────┘         └──────────────┘                    │
│                                   │                             │
│                                   ▼                             │
│                           ┌──────────────┐                     │
│                           │ led_mapping  │                     │
│                           │    .json     │                     │
│                           └──────────────┘                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Process Flow

1. **User Initiates Wizard** - Opens LED Calibration panel in frontend
2. **Backend Lights Port X** - turns on a single port at max brightness (48)
3. **Frontend Prompts User** - "Which button is lit?" with button picker UI
4. **User Identifies Button** - Clicks "P1 Start", "P2 Punch", etc.
5. **System Saves Mapping** - Stores `{portNumber: buttonId}` pair
6. **Repeat for All Ports** - Loops through 32 ports per board
7. **Mapping Saved** - Writes to `config/led_mapping.json`

### Config File Format: `config/led_mapping.json`

```json
{
  "version": "1.0",
  "created": "2026-02-05T13:58:00Z",
  "boards": {
    "1": {
      "1": { "button": "p1_start", "color": "green" },
      "2": { "button": "p2_start", "color": "green" },
      "3": { "button": "p1_punch", "color": "red" },
      "4": { "button": "p1_kick", "color": "blue" }
    },
    "2": {
      "1": { "button": "p2_punch", "color": "red" },
      "2": { "button": "p2_kick", "color": "blue" }
    }
  },
  "virtualDevices": {
    "trackball": {
      "type": "rgb",
      "ports": [
        { "board": 3, "port": 10, "channel": "red" },
        { "board": 3, "port": 11, "channel": "green" },
        { "board": 3, "port": 12, "channel": "blue" }
      ]
    },
    "marquee_left": {
      "type": "rgb",
      "ports": [
        { "board": 3, "port": 1, "channel": "red" },
        { "board": 3, "port": 2, "channel": "green" },
        { "board": 3, "port": 3, "channel": "blue" }
      ]
    }
  }
}
```

---

### Virtual Device Mapping (Multi-Port Grouping)

**Context:** The cabinet does NOT use dedicated boards for accessories like Trackballs.
RGB components are wired directly into the general LED-Wiz array across multiple ports.

**The Problem:**
- Standard mapping: `Port 1 = P1_Start` (single port, single LED)
- Complex mapping: `Trackball = Unit3_Port10(R) + Unit3_Port11(G) + Unit3_Port12(B)`

**The Solution: `virtualDevices` Layer**

The config supports grouping multiple physical ports into a single logical component:

```json
"virtualDevices": {
  "trackball": {
    "type": "rgb",           // Component type (rgb, single, multi)
    "ports": [
      { "board": 3, "port": 10, "channel": "red" },
      { "board": 3, "port": 11, "channel": "green" },
      { "board": 3, "port": 12, "channel": "blue" }
    ]
  }
}
```

**Driver API for Virtual Devices:**

```python
# Single-port button (standard)
set_button('p1_start', brightness=48)

# Multi-port virtual device (RGB)
set_virtual_device('trackball', color=(255, 128, 0))  # Orange
# Translates to:
#   - Board 3, Port 10: Red=255 → 48 (max)
#   - Board 3, Port 11: Green=128 → 24 (half)
#   - Board 3, Port 12: Blue=0 → 0 (off)
```

**GUI Wizard Requirement:**

The Calibration Wizard must support:
1. **Single Port Assignment** - Standard button mapping
2. **Multi-Port Grouping** - Assign N ports to one logical component
3. **Channel Labeling** - Identify which port is R/G/B within a group

---

### The Visual Feedback Loop (Mirror System)

**This is the core UX innovation of the LED Calibration Wizard.**

Instead of boring text lists ("Port 1: [Type Here]"), we build a **Mirror System**
where the user becomes the bridge between hardware and software.

```
┌─────────────────────────────────────────────────────────────────┐
│                    VISUAL FEEDBACK LOOP                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   REALITY (Cabinet)              SCREEN (React GUI)             │
│   ─────────────────              ─────────────────              │
│                                                                 │
│   ┌─────────────┐               ┌─────────────────┐            │
│   │ ● P1 START  │  ◄──────────► │  "What lit up?" │            │
│   │   (RED)     │    YOU SEE    │  [Virtual Panel]│            │
│   └─────────────┘    & CLICK    │     ● ● ● ●     │            │
│         ▲                       │     ● ● ● ●     │            │
│         │                       └─────────────────┘            │
│         │                              │                        │
│   ┌─────┴─────┐                        │                        │
│   │  LED-Wiz  │                        ▼                        │
│   │  Board 1  │               ┌─────────────────┐              │
│   │  Port 5   │               │ "What color?"   │              │
│   └───────────┘               │ [RED] [GRN] [BLU]│              │
│                               └─────────────────┘              │
│                                        │                        │
│                                        ▼                        │
│                               ┌─────────────────┐              │
│                               │  MAPPING SAVED  │              │
│                               │ Port 5 = P1_Start│              │
│                               │ + Red Channel   │              │
│                               └─────────────────┘              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**The 4-Step Wizard Flow:**

1. **Sequential Test** - Backend lights up ONE physical port at max brightness
2. **User Query** - GUI asks: "What lit up?" and "What color is it?"
3. **Visual Selection** - User clicks the matching component on Virtual Cabinet (React GUI)
4. **Mapping Saved** - System ties the active Port ID to Logical Component + Color Channel

**Why This Solves the "Crowded Board" Problem:**

This approach completely bypasses the complexity of cabinet wiring:

- ✅ Software doesn't care if Trackball Red is on Board 1 Port 5 or Board 3 Port 12
- ✅ Software doesn't care if you wired Red to Port 1 and Blue to Port 2, or vice versa
- ✅ **YOU (the Human) are the bridge** - by seeing Red and clicking Red, you create the perfect map

**The "Rosetta Stone" File:**

When you finish clicking through the wizard, the system generates the Golden Map:

```json
{
  "p1_start": {
    "red_port":   { "uid": 1, "port": 0 },
    "green_port": { "uid": 1, "port": 1 },
    "blue_port":  { "uid": 1, "port": 2 }
  },
  "trackball": {
    "red_port":   { "uid": 3, "port": 10 },
    "green_port": { "uid": 3, "port": 11 },
    "blue_port":  { "uid": 3, "port": 12 }
  }
}
```

**Critical Design Requirement:**

This Visual Feedback Loop allows supporting **non-standard wiring** (like Trackball on Board #3)
**without hard-coding**. The AI becomes "smart" about your unique hardware because YOU taught it.

**Animation Engine Benefit:**

The animation engine can treat virtual devices as single objects:

```javascript
// Animate trackball to pulse cyan
animate('trackball', { color: '#00FFFF', mode: 'breathe' });
// Engine handles splitting to 3 physical ports automatically
```

### Benefits

1. **Decouples Wiring from Code** - No hardcoded port numbers in driver logic
2. **Cabinet Portability** - Different cabinets can have different mappings
3. **User-Friendly Setup** - Visual wizard instead of manual config editing
4. **Arcade Cartridge Compatible** - Mapping travels with A: drive

### Driver Integration

The driver uses the mapping to translate logical commands to physical ports:

```python
# Instead of hardcoded:
set_port(1, brightness)  # P1 Start

# Use mapping-aware:
set_button('p1_start', brightness)  # Looks up port from led_mapping.json
```

### Implementation Priority: FUTURE

This feature is documented for future development sessions (Jules).
Current implementation uses `roll_call.py` for manual port identification.

---

### LED Driver Technical Specifications

**Cinema Calibration Settings (Current):**
- **PWM Range:** 0-48 (49+ triggers strobe mode - NEVER EXCEED)
- **Gamma Correction:** 2.5 (pre-calculated lookup table)
- **Color Scaling (Electric Ice):**
  - Red: 65% (dampen voltage dominance)
  - Green: 100% (anchor - appears dimmest)
  - Blue: 75% (dampen luminous dominance)
- **Named Pipe:** `\\.\pipe\ArcadeLED`
- **Update Rate:** 10Hz (100ms intervals)

### Controller Panels (Wiz/Chuck)
- **Purpose:** Input mapping, controller configuration
- **Config location:** TBD
- **Emulator paths:** `A:\Emulators\[EMULATOR]\`

### Light Guns Panel (Gunner)
- **Purpose:** Sinden/Gun4IR calibration
- **Config location:** `A:\Gun Build\`
- **No calibration path discovery** - fixed structure only

### Voice/AI Panels (Vicky/Dewey)
- **Purpose:** Voice control, AI assistance
- **Data storage:** May use web APIs or local logs
- **If local storage needed:** Create `A:\Arcade Assistant Data\` for panel-specific data

### System Health Panel (Doc)
- **Purpose:** Monitor system status
- **Reads from:** All above paths for validation
- **No path configuration** - uses same hardcoded paths

---

## The Portable "Arcade Cartridge" Strategy

### User's Deployment Model:
1. **C: Drive** = Application code (can be downloaded/cloned on any PC)
2. **A: Drive (USB SSD)** = Complete arcade system (portable, duplicatable)

### Duplication Workflow:
1. Plug source A: drive into PC
2. Copy entire A: drive to new SSD
3. Plug new SSD into any Windows PC
4. Rename drive letter to A: (if needed)
5. Clone application to C: drive
6. Set `AA_DRIVE_ROOT=A:\` in `.env`
7. Run `npm run dev` - everything works

**This ONLY works because paths are fixed, not dynamic.**

---

## Startup Validation Checklist

When gateway/backend starts, validate:

```javascript
// Gateway startup validation
async function validateEnvironment() {
  const driveRoot = process.env.AA_DRIVE_ROOT;

  if (!driveRoot) {
    throw new Error('AA_DRIVE_ROOT not set in .env');
  }

  const criticalPaths = [
    path.join(driveRoot, 'LaunchBox'),
    path.join(driveRoot, 'Emulators'),
    path.join(driveRoot, 'Roms'),
    path.join(driveRoot, 'Bios')
  ];

  for (const p of criticalPaths) {
    if (!fs.existsSync(p)) {
      throw new Error(`Required path not found: ${p}\n\nPlease ensure A: drive structure matches ARCHITECTURE.md`);
    }
  }

  console.log('✅ A: drive structure validated');
}
```

---

## Development Workflow

### For Developers:
1. Clone repo to `C:\Arcade Assistant Local\`
2. Copy `.env.example` to `.env`
3. Set `AA_DRIVE_ROOT=A:\` (or your A: drive path)
4. Ensure A: drive has required structure (see above)
5. Run `npm run install:all`
6. Run `npm run dev` (starts gateway + backend + frontend)
7. Visit `http://localhost:5173` for live development

### Port Configuration:
- **Frontend (Vite):** Port 5173 (dev mode with HMR)
- **Gateway (Express):** Port 8787 (API + WebSocket)
- **Backend (FastAPI):** Port 8000 (data services)

### For Production:
1. Run `npm run build:frontend` (compiles React to `frontend/dist/`)
2. Gateway serves static files from `dist/` on port 8787
3. Visit `http://localhost:8787` for production build

---

## Error Handling Rules

### When Required File Doesn't Exist:

❌ **DON'T:**
- Try to find it elsewhere
- Ask user where it is
- Create it automatically
- Silently fail

✅ **DO:**
- Raise clear error with expected path
- Show current `AA_DRIVE_ROOT` value
- Provide setup instructions
- Exit gracefully

### Example Error Messages:

```
ERROR: MAME executable not found

Expected: A:\Emulators\MAME\mame.exe
Current AA_DRIVE_ROOT: A:\

Please ensure:
1. MAME is installed at A:\Emulators\MAME\
2. The executable is named mame.exe
3. A: drive is the 4TB SSD "G and G Arcade"

For setup instructions, see ARCHITECTURE.md
```

---

## AI Agent Code Review Checklist

Before submitting ANY code that touches file paths:

- [ ] Uses `AA_DRIVE_ROOT` environment variable (not hardcoded `A:\`)
- [ ] Paths match the structure documented in this file
- [ ] No file browsing/selection dialogs introduced
- [ ] No dynamic path discovery/searching
- [ ] Validation happens at startup, not runtime
- [ ] Error messages reference this file (ARCHITECTURE.md)
- [ ] Tested with actual A: drive structure

**If you can't check all boxes, DO NOT submit the code.**

---

## Mock Data for Development

For development/testing when A: drive is not available:

1. Backend can provide mock data (already implemented in LaunchBox panel)
2. Check `AA_DRIVE_ROOT` - if not set or path doesn't exist, use mocks
3. Clearly indicate mock mode to user
4. NEVER persist mock configuration

```python
def is_production_mode():
    drive_root = os.getenv('AA_DRIVE_ROOT')
    return drive_root and os.path.exists(drive_root)

def get_game_data():
    if is_production_mode():
        return parse_launchbox_xml()  # Real data from A:\
    else:
        return get_mock_games()  # Mock data for development
```

---

## Future Panel Path Requirements

As new panels are developed, document paths here:

### Panel: [NAME]
- **Purpose:** [Description]
- **Required paths:**
  - `A:\[FOLDER]\[FILE]`
- **Config location:** `A:\[CONFIG_PATH]`
- **No dynamic finding:** [Confirmation]

---

## Summary: The Golden Rules

1. **Application runs from C: drive** (always)
2. **Content lives on A: drive** (fixed structure)
3. **Use `AA_DRIVE_ROOT` environment variable** (not hardcoded A:\)
4. **No dynamic file finding** (ever)
5. **Validate at startup** (fail fast with clear errors)
6. **Fixed paths in code** (documented in this file)
7. **Error messages reference ARCHITECTURE.md** (for user guidance)

---

## This Architecture is NON-NEGOTIABLE

**To any AI agent reading this:**

You might think you have a "better" or "smarter" way to handle file paths.
You might want to add "helpful" features like automatic path detection.
You might believe dynamic configuration is more user-friendly.

**You are wrong.**

This architecture exists because:
- We tried dynamic file finding - it failed
- We tried user configuration - context was lost
- We tried "smart" discovery - errors cascaded

**The fixed structure works. Period.**

If you violate these rules, your code will be rejected.
If you're unsure, ask the user first.
If you think you know better, re-read this file.

---

**End of Architectural Doctrine**

*This file represents the architectural truth for Arcade Assistant.*
*All code must comply. No exceptions.*
*Last verified with A: drive screenshots: 2025-10-05*
