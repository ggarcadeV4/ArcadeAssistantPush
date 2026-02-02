# Arcade Assistant – Pegasus Integration Journal

> _Purpose:_ This document is the living record of how **Pegasus** is integrated into Arcade Assistant – architecture, customizations, quirks, and Golden Drive requirements.  
> If something breaks later, this is the first place we look.

---

## 1. High-Level Intent

Pegasus is our **primary "play mode" frontend** for the arcade:

- **Player-facing:** Modern, themeable game browser (gameOS, shinretro, XboxOS, etc.).
- **Under the hood:** Uses **Arcade Assistant + LaunchBox** as the actual launcher.
- **Philosophy:**  
  - Arcade Assistant is the **mechanic** and brain.  
  - Pegasus is the **stage** – what players see first when the cabinet boots.

Golden Drive expectation:

- On a properly provisioned cabinet, Pegasus should:
  - Show the full game library (10k+ games) with proper art.
  - Launch any game that LaunchBox can launch.
  - Return control cleanly when games exit.

---

## 2. Current Architecture (Pegasus Path Only)

### 2.1 Launch Flow (Ideal)

```text
Pegasus (Frontend)
  → metadata.pegasus.txt (per platform)
    → launch command (calls .bat)
      → aa_launch_pegasus_simple.bat (bridge script)
        → Arcade Assistant Gateway (:8787)
          → Arcade Assistant Backend (:8000)
            → LaunchBox / Emulator
```

### 2.2 Key Pieces (as of Dec 2025)

#### Metadata Generator Script

| Item | Value |
|------|-------|
| **File** | `scripts/generate_pegasus_metadata.py` |
| **Role** | Build `metadata.pegasus.txt` per platform using `A:\.aa\launchbox_games.json` as the source of truth |
| **Policy** | Zero-copy: points to existing `A:\LaunchBox\Images` and `Videos` folders for artwork |

#### Bridge Script

| Item | Value |
|------|-------|
| **File** | `scripts/aa_launch_pegasus_simple.bat` |
| **Role** | Take the game title/platform from Pegasus and call the AA gateway |
| **Endpoint** | `POST http://localhost:8787/api/launchbox/launch-by-title` |
| **Payload** | `{"title": "<game>", "collection": "<platform>"}` |

#### Pegasus Installation

| Item | Value |
|------|-------|
| **Location** | `A:\Tools\Pegasus\` |
| **Executable** | `pegasus-fe.exe` |
| **Version** | alpha16-92 (continuous build) |
| **Config** | `A:\Tools\Pegasus\config\settings.txt` |
| **Metadata** | `A:\Tools\Pegasus\metadata\<platform>\metadata.pegasus.txt` |

#### Pegasus Themes

| Theme | Location | Notes |
|-------|----------|-------|
| XboxOS-master | `A:\Tools\Pegasus\themes\XboxOS-master\` | Currently active |
| shinretro | `A:\Tools\Pegasus\themes\shinretro\` | Classic CRT/arcade vibe |
| pegasus-theme-flixnet-master | `A:\Tools\Pegasus\themes\pegasus-theme-flixnet-master\` | Netflix-style |

---

## 3. Visual Customizations (Platforms & Special Categories)

We are customizing Pegasus to feel like a G&G cabinet, not a stock install.

### 3.1 Artwork Folder Structure

Convention (Golden Drive):

```
A:\
  Artwork\
    Pegasus\
      platforms\
        nes.png
        snes.png
        genesis.png
        arcade.png
        ...
      categories\
        nes_gun_games.png
        snes_shmups.png
        arcade_fighters.png
        arcade_lightgun.png
        family_favorites.png
        party_games.png
        ...
      fallback\
        generic_lightgun.png
        generic_fighter.png
        generic_shmup.png
```

Notes:

- Names use lowercase + underscores so scripts can map category IDs → filenames.
- Themes can reference:
  - Platform art: `Artwork/Pegasus/platforms/<platform>.png`
  - Special categories: `Artwork/Pegasus/categories/<category>.png`
  - Fallbacks: when no specific art exists for that category.

### 3.2 Special Categories (Non-Standard but Important)

These categories are not typical stock builds, but part of our signature:

- NES Gun Games
- SNES Gun Games
- Genesis Gun Games
- Master System Gun Games
- Arcade Lightgun (MAME Gun Games)
- TeknoParrot Gun Games
- Wii Gun Games
- PS2 Gun Games
- PSX Gun Games
- Dreamcast Gun Games
- Saturn Gun Games
- Model 2 Gun Games
- Model 3 Gun Games
- Naomi Gun Games
- Atomiswave Gun Games
- Flash Gun Games
- PC Gun Games
- PS3 Gun Games

**Rule:**  
If it appears as a category in Pegasus on the Golden Drive, it must have non-embarrassing art here.

### 3.3 Theme Asset Manager Tool

| Item | Value |
|------|-------|
| **CLI Script** | `scripts/theme_asset_manager.py` |
| **Backend API** | `/api/local/theme-assets/*` |
| **Gateway Proxy** | `/api/theme-assets/*` |
| **Purpose** | Deploy custom collection artwork (logos, backgrounds) across all themes at once |

Usage:
```bash
# Create a custom collection
python scripts/theme_asset_manager.py create "NES Gun Games" --shortname "nes-gun"

# Deploy a logo to that collection across ALL themes
python scripts/theme_asset_manager.py deploy "NES Gun Games" --logo "path/to/logo.png"
```

---

## 4. Pegasus Launch Issues & Fix History

This section tracks launch-related problems and how we fixed them.  
**Newest entries go on top.**

### 4.0 [2025-12-12] – {file.stem} Variable Not Supported (404 "Game not found")

#### Symptom

After fixing the boot loop issue, games would still fail to launch with a 404 error:
- Backend logs showed: `Game not found for title '{file.stem}'`
- The literal string `{file.stem}` was being passed instead of the actual game title.

#### Root Cause

Pegasus **only supports `{file.path}`** as a launch command variable. The `{file.stem}` variable (filename without extension) is NOT supported by Pegasus and is passed as a literal string.

#### Fix Applied (2025-12-12 ~12:30am)

**1. Modified `generate_pegasus_metadata.py`** (line 173):
```python
# OLD (broken):
f'launch: A:\\Tools\\aa_pegasus.bat "{file.stem}" "{platform}"'

# NEW (working):
f'launch: A:\\Tools\\aa_pegasus.bat "{{file.path}}" "{platform}"'
```

**2. Modified `scripts/aa_launch_pegasus_simple.bat`**:
- Changed from using `%~1` (full argument) to `%~n1` (filename without extension)
- `%~n1` extracts the title from the full path provided by Pegasus

```batch
REM Extract just the filename without extension from the full path
REM %~n1 gives us the filename without extension
set "GAME_TITLE=%~n1"
```

**3. Regenerated all Pegasus metadata** for all 50 platforms.

#### Files Changed

| File | Change |
|------|--------|
| `scripts/generate_pegasus_metadata.py` | Line 173: Changed `{file.stem}` to `{file.path}` |
| `scripts/aa_launch_pegasus_simple.bat` | Extract title from path using `%~n1` |
| `A:\Tools\Pegasus\metadata\*\metadata.pegasus.txt` | All regenerated |

#### Multi-Platform Verification

| Platform | Game | Status |
|----------|------|--------|
| Atari 2600 | Air Raid, Barnstorming | ✅ Launched |
| Atari 7800 | Asteroids | ✅ Launched |
| NEC TurboGrafx-16 | Aero Blasters | ✅ Launched |
| Arcade MAME | 1000 Miglia: Great 1000 Miles Rally | ✅ Launched |
| Atari Jaguar | Fever Pitch Soccer | ✅ Launched |
| Sega Genesis | Alien Soldier | ✅ Launched |
| Super Nintendo | Battletoads in Battlemaniacs | ✅ Launched |

#### Key Lesson

- **Always test Pegasus variables in isolation** - The `{file.stem}` variable is documented in some Pegasus resources but doesn't actually work. Only `{file.path}` and `{file.name}` are reliable.
- **Windows batch has file path utilities** - `%~n1` is the Windows batch equivalent of getting the file stem (basename without extension).

---

### 4.1 [2025-12-11] – Pegasus "Boot Loop" (Game Looks Like It Will Launch, Then Doesn't)

#### Symptom

Game selection in Pegasus:
- Screen acts like it's about to launch.
- Game never starts (or starts very briefly); Pegasus regains control.
- Same game launches perfectly from LaunchBox directly.

#### Scope

- Emulators + LaunchBox configs: ✅ healthy.
- Problem area: ❌ Pegasus → AA → LaunchBox launch bridge.

#### Root Cause (IDENTIFIED 2025-12-11 ~10pm)

The `launch_game` function in `backend/routers/launchbox.py` uses `AA_LAUNCH_POLICY` which defaults to `direct_only`. When `direct_only`:

1. It tries `launcher.launch(game, 'direct', ...)` first
2. If that fails, it tries `launcher.launch(game, 'detected_emulator', ...)`
3. **It NEVER reaches the plugin bridge** (the known-working LaunchBox path)

The plugin bridge (which uses LaunchBox's native launch mechanism) is only tried when `policy_mode != "direct_only"`.

Additionally, the bridge script used `curl -s` (silent mode) which swallowed all HTTP errors, so Pegasus saw an immediate return and thought the game had ended.

#### Fix Applied (2025-12-11 ~10pm)

**1. Backend policy override for Pegasus** (`backend/routers/launchbox.py` lines 2238-2241):
```python
# Override: Pegasus launches should use plugin_first to use the known-working LaunchBox path
if panel == "pegasus":
    policy_mode = "plugin_first"
    logger.info(f"Pegasus launch detected - using plugin_first policy for '{game.title}'")
```

**2. Bridge script with logging** (`scripts/aa_launch_pegasus_simple.bat`):
- Added response logging to `A:\Arcade Assistant Local\logs\pegasus_launch.log`
- Added HTTP status code capture
- Improved emulator wait loop with more process names
- Added 5-second initial wait for LaunchBox to start the emulator

#### Files Changed

| File | Change |
|------|--------|
| `backend/routers/launchbox.py` | Added Pegasus panel detection to force `plugin_first` policy |
| `scripts/aa_launch_pegasus_simple.bat` | Added logging, HTTP status capture, improved wait loop |
| `scripts/generate_pegasus_metadata.py` | Changed launch command to use wrapper script |
| `A:\Tools\aa_pegasus.bat` | **NEW** - Wrapper script to avoid path-with-spaces issue |

**3. Path with spaces fix** - The original launch command used `cmd /c` with the path `A:\Arcade Assistant Local\scripts\...` which broke due to the space. Created a wrapper at `A:\Tools\aa_pegasus.bat` (no spaces) that calls the real script.

#### How to Test

1. Ensure AA backend is running (`npm run dev` or gateway + backend)
2. Launch Pegasus
3. Select any game and press launch
4. Game should launch via LaunchBox plugin bridge
5. Check `A:\Arcade Assistant Local\logs\pegasus_launch.log` for details

#### Definition of Done (for this bug)

- [x] From Pegasus, launching the test game starts the game fully via AA/LaunchBox. ✅ **VERIFIED 2025-12-11**
- [x] Uses the same game that works from LaunchBox alone. ✅
- [x] `aa_launch_pegasus_simple.bat` points at the gateway (`http://localhost:8787/...`). ✅
- [x] AA logs show a launch request from Pegasus with no errors. ✅
- [x] No emulator or LaunchBox configs were changed to "fix" this. ✅

#### Struggles & Debugging Journey

This bug took multiple attempts to fix. Here's what we tried and why each attempt failed:

| Attempt | What We Tried | Why It Failed |
|---------|---------------|---------------|
| 1 | Added `cmd /c` wrapper to handle path spaces in launch command | Quoting was still incorrect for `cmd.exe` |
| 2 | Simplified `aa_launch_pegasus.bat` with better wait logic | Script wasn't being called at all - path issue |
| 3 | Created `aa_launch_pegasus_simple.bat` - minimal script | Same path issue - space in "Arcade Assistant Local" |
| 4 | Fresh Pegasus reinstall (alpha16-92) | Problem was in our code, not Pegasus |
| 5 | Added Pegasus panel detection for `plugin_first` policy | Correct fix for backend, but script still not running |
| 6 | Created wrapper at `A:\Tools\aa_pegasus.bat` (no spaces) | ✅ **WORKED** |

**Key Lessons:**
1. **Silent failures are deadly** - The original `curl -s` swallowed all errors, making it impossible to diagnose.
2. **Path with spaces + cmd.exe = pain** - Windows `cmd /c` quoting is notoriously tricky. A wrapper script in a space-free path is the cleanest solution.
3. **Policy defaults matter** - `AA_LAUNCH_POLICY=direct_only` was blocking the known-working plugin path for Pegasus.
4. **Test the bridge script manually first** - Running the `.bat` from a console immediately revealed the "not recognized as a command" error.

**Diagnostic Commands Used:**
```cmd
# Test the bridge script manually
cmd /c """A:\Tools\aa_pegasus.bat"" ""Air Raid"" ""Atari 2600"""

# Check the log file
type "A:\Arcade Assistant Local\logs\pegasus_launch.log"

# Verify gateway is running
netstat -ano | findstr ":8787"
```

---

## 5. Golden Drive Requirements for Pegasus

For a drive to be "Golden" with respect to Pegasus:

### Library & Metadata

- [ ] `generate_pegasus_metadata.py` has been run for all planned platforms.
- [ ] `metadata.pegasus.txt` exists for each platform (currently 50 platforms).
- [ ] Artwork paths in metadata point to stable `A:\` locations (no `C:\` dev paths).

### Pegasus Launch Path

- [ ] Bridge script (`aa_launch_pegasus_simple.bat`) is present and tested.
- [ ] Pegasus successfully launches at least:
  - [ ] One NES game (RetroArch)
  - [ ] One MAME game
  - [ ] One TeknoParrot game (if in scope for that cabinet)
- [ ] Launches go through AA (gateway + backend), not direct EXE hacks.

### Visuals

- [ ] Platform art for all major systems populated.
- [ ] Special categories (NES Gun Games, etc.) have correct art.
- [ ] No "TODO" placeholder art visible in the UI on a demo cabinet.

### No Local Path Leaks

- [ ] No references to:
  - Dev-only paths (`C:\Users\...`, local desktop folders).
  - Hard-coded usernames.
- [ ] All Pegasus-related paths are under `A:\...` per deterministic layout.

---

## 6. Configuration Reference

### 6.1 Pegasus Settings (`A:\Tools\Pegasus\config\settings.txt`)

```ini
general.theme: A:/Tools/Pegasus/themes/XboxOS-master/
general.verify-files: true
general.input-mouse-support: true
general.fullscreen: true
providers.pegasus_media.enabled: true
providers.steam.enabled: true
providers.gog.enabled: true
providers.es2.enabled: true
providers.launchbox.enabled: true
providers.logiqx.enabled: true
providers.playnite.enabled: true
providers.skraper.enabled: true
keys.menu: F1,GamepadStart
keys.page-down: PgDown,GamepadR2
keys.prev-page: Q,A,GamepadL1
keys.next-page: E,D,GamepadR1
keys.filters: F,GamepadY
keys.details: I,GamepadX
keys.cancel: Backspace
keys.page-up: PgUp,GamepadL2
keys.accept: Return,Enter,GamepadA
keys.quit: Alt+F4
```

### 6.2 Metadata Launch Command Format

```
launch: cmd /c ""A:\Arcade Assistant Local\scripts\aa_launch_pegasus_simple.bat"" "{file.stem}" "<Platform Name>"
```

### 6.3 Bridge Script (`aa_launch_pegasus_simple.bat`)

```batch
@echo off
REM Simple Pegasus Launch Bridge
REM Calls API to launch game, then waits for emulator to close

set "GAME=%~1"
set "PLATFORM=%~2"

REM Launch via API
curl -s -X POST "http://localhost:8787/api/launchbox/launch-by-title" -H "Content-Type: application/json" -d "{\"title\": \"%GAME%\", \"collection\": \"%PLATFORM%\"}" > nul

REM Wait 3 seconds for emulator to start
timeout /t 3 /nobreak > nul

REM Wait for any common emulator to close
:WAIT
timeout /t 1 /nobreak > nul
tasklist | findstr /i "retroarch.exe mame.exe TeknoParrotUi.exe Dolphin.exe pcsx2 PPSSPP Cemu.exe Supermodel.exe emulator_multicpu.exe" > nul
if %ERRORLEVEL%==0 goto WAIT
```

---

## 7. How to Extend This Document (For Future Sessions)

Whenever we make a Pegasus-related change, we add:

1. A new subsection under **"4. Pegasus Launch Issues & Fix History"** or a new **"7. New Feature – [Name]"** section.

2. For each change:
   - What we changed (1–3 bullets).
   - Files touched.
   - Why we changed it.
   - How to test it.

3. If the change affects Golden Drive behavior:
   - Update **section 5. Golden Drive Requirements** accordingly.

---

## 8. Related Documentation

| Document | Purpose |
|----------|---------|
| `docs/PEGASUS_INTEGRATION_PLAN.md` | Original integration planning document |
| `docs/GOLDEN_DRIVE_SPEC.md` | Full Golden Drive specification |
| `AGENTS.md` | Repository guidelines and agent instructions |

---

_Last updated: 2025-12-12_
