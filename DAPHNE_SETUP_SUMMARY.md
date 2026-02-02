# Daphne/Hypseus Setup Summary

**Date:** 2025-10-18
**Status:** ✅ Fully configured and tested
**Platforms:** Daphne, American Laser Games (Singe2)

---

## What Was Done

### 1. Identified Three Laserdisc Platforms

**Daphne Platform** (classic laserdisc games):
- Dragon's Lair
- Space Ace
- Road Blaster
- GP World
- And more...

**American Laser Games Platform** (light gun laserdisc):
- Sonic Fury
- Blue Thunder
- Crime Patrol
- Mad Dog McCree series
- And more...

**Emulators:**
- **Hypseus Singe** at `/mnt/a/Roms/SINGE-HYPSEUS/hypseus.exe`
- **Classic Daphne** at `/mnt/a/Roms/DAPHNE/daphne.exe`
- **Singe v2.00** at `/mnt/a/Gun Build/Roms/SINGE2/Singe-v2.00-Windows-x86_64.exe`

### 2. Created Direct ApplicationPath Adapter

**File:** `backend/services/adapters/direct_app_adapter.py`

**Purpose:** Launches games that use custom AHK scripts or standalone executables configured in LaunchBox's ApplicationPath field.

**Supported Platforms:**
- Taito Type X
- Daphne
- American Laser Games

**Key Features:**
- Resolves ApplicationPath relative to LaunchBox root (not Data/Platforms)
- Normalizes backslashes to forward slashes for WSL compatibility
- Supports .ahk, .exe, .bat, and .cmd file types
- Launches via AutoHotkey when appropriate

### 3. Updated Drive Letters

**Singe2 AHK Scripts:**
- Backed up to: `SINGE2.backup-YYYYMMDD-HHMMSS`
- Updated all D:\ paths to A:\
- Example: `D:\Gun Build\Tools\...` → `A:\Gun Build\Tools\...`

**Note:** Daphne/Hypseus AHK scripts already used relative paths, no changes needed.

### 4. Fixed Path Resolution Bug

**Issue:** ApplicationPath was being resolved against `LaunchBox/Data/Platforms` instead of `LaunchBox` root.

**Fix:**
```python
# Before (incorrect)
launchbox_data_dir = LaunchBoxPaths.LAUNCHBOX_ROOT / "Data" / "Platforms"
resolved_path = (launchbox_data_dir / app_path).resolve()

# After (correct)
app_path = app_path.replace("\\", "/")  # Normalize slashes
launchbox_root = LaunchBoxPaths.LAUNCHBOX_ROOT
resolved_path = (launchbox_root / app_path).resolve()
```

**Result:** Paths now resolve correctly:
- `A:\LaunchBox\..\Roms\SINGE-HYPSEUS\Dragons Lair.ahk` → `A:\Roms\SINGE-HYPSEUS\Dragons Lair.ahk` ✅

---

## How It Works

### Daphne Launch Flow

1. User clicks "Dragon's Lair" in LaunchBox LoRa panel
2. Backend receives launch request for game with platform "Daphne"
3. `direct_app_adapter.can_handle()` returns True (platform is supported)
4. Adapter resolves ApplicationPath: `A:\Roms\SINGE-HYPSEUS\Dragons Lair.ahk`
5. Detects .ahk extension → launches via AutoHotkey
6. AutoHotkey script runs:
   ```autohotkey
   Run, Hypseus.exe dle21 vldp -framefile vldp/lair60fps/lair60fps.txt -fullscreen
   ```
7. Hypseus launches with Dragon's Lair loaded

### Example AHK Scripts

**Daphne (relative paths - already correct):**
```autohotkey
SetWorkingDir %A_ScriptDir%
Run, Hypseus.exe dle21 vldp -framefile vldp/lair60fps/lair60fps.txt -fullscreen
```

**Singe2 (updated from D:\ to A:\):**
```autohotkey
SetWorkingDir %A_ScriptDir%
Run, A:\Gun Build\Tools\Sinden Lightgun V2.01 beta\Lightgun.exe
Run, Singe-v2.00-Windows-x86_64.exe -k -f -z -d data -v ActionMax/frame_SonicFury.txt
```

---

## Testing Results

✅ **Daphne games launch successfully**
✅ **American Laser Games work (with light gun hardware)**
✅ **No more "ApplicationPath not found" errors**
✅ **AutoHotkey integration working**

---

## Configuration Files

### launchers.json
No Daphne-specific configuration needed - uses direct ApplicationPath method.

### Adapter Registration
**File:** `backend/services/launcher_registry.py`

```python
# Direct ApplicationPath adapter (enabled for Daphne/American Laser Games AHK scripts)
from backend.services.adapters import direct_app_adapter as dapp
REGISTERED.append(dapp)
ADAPTER_STATUS['direct_app'] = 'ok'
```

**Priority:** Runs BEFORE TeknoParrot adapter to handle custom ApplicationPath configs first.

---

## Troubleshooting

### Game doesn't launch
1. Check if AutoHotkey is installed: `C:\Program Files\AutoHotkey\AutoHotkey.exe`
2. Verify ApplicationPath in LaunchBox XML points to correct .ahk file
3. Check backend logs for "ApplicationPath not found" errors

### Wrong path errors
1. Ensure all AHK scripts use A:\ drive (not D:\)
2. Backups available in `.backup-YYYYMMDD` directories
3. Re-run path replacement if needed

### AHK script fails
1. Check emulator executable exists (hypseus.exe, daphne.exe, Singe.exe)
2. Verify game data folders are in correct location
3. Test AHK script manually by double-clicking it

---

## Future Enhancements

- [ ] Add more platforms that use ApplicationPath (if needed)
- [ ] Support for other script types (.ps1, .vbs, etc.)
- [ ] Automatic D:\ to A:\ migration tool
- [ ] Direct emulator launch option (bypass AHK for simpler games)

---

**Status:** ✅ Ready for production
**Session Complete:** 2025-10-18
**Next Platform:** Your choice! 🎮
