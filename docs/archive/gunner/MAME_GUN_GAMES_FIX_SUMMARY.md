# MAME Gun Games Fix Summary

**Date:** 2025-10-18
**Issue:** MAME gun games failed to launch from LaunchBox LoRa
**Root Cause:** Plugin bridge down + gun games not included in fallback methods

---

## 🔴 Problem Diagnosis

### What Happened
1. User tried to launch MAME gun games from LaunchBox LoRa
2. LaunchBox plugin error occurred
3. Games failed to launch

### Root Causes Found
1. **LaunchBox plugin bridge not running** (port 9999)
   - Primary launch method unavailable
2. **Gun games not in direct MAME fallback**
   - Platform check only included "Arcade" and "Arcade MAME"
   - Missing "MAME Gun Games" platform
3. **Direct MAME launch disabled**
   - `allow_direct_mame: false` in config

---

## ✅ Fixes Applied

### Fix 1: ROM Path Fallback (Line 1137)
**File:** `backend/services/launcher.py`

**Before:**
```python
if not rom_path.exists() and game.platform in ("Arcade", "Arcade MAME"):
    rom_name = rom_path.stem or game.title.replace(" ", "").lower()
    rom_path = LaunchBoxPaths.MAME_ROMS / f"{rom_name}.zip"
```

**After:**
```python
if not rom_path.exists() and game.platform in ("Arcade", "Arcade MAME", "MAME Gun Games"):
    rom_name = rom_path.stem or game.title.replace(" ", "").lower()
    rom_path = LaunchBoxPaths.MAME_ROMS / f"{rom_name}.zip"
```

### Fix 2: Direct Launch Platform Check (Line 881)
**File:** `backend/services/launcher.py`

**Before:**
```python
# MAME path for Arcade
if game.platform in ("Arcade", "Arcade MAME"):
    rom_path = self._resolve_rom_path(game)
    command = self._build_mame_command(rom_path)
```

**After:**
```python
# MAME path for Arcade (including gun games)
if game.platform in ("Arcade", "Arcade MAME", "MAME Gun Games"):
    rom_path = self._resolve_rom_path(game)
    command = self._build_mame_command(rom_path)
```

### Fix 3: Enable Direct MAME + Add Configuration
**File:** `config/launchers.json`

**Changes:**
1. Enabled direct MAME: `"allow_direct_mame": true`
2. Added MAME emulator configuration:
```json
"mame": {
  "exe": "A:/Emulators/MAME/mame.exe",
  "rompath": "A:/Roms/MAME",
  "platforms": ["Arcade", "Arcade MAME", "MAME Gun Games"],
  "flags": ["-skip_gameinfo"]
}
```

---

## 🎯 How It Works Now

### Launch Chain for MAME Gun Games
1. **Plugin Bridge** (localhost:9999) - Try first
   - If available: ✅ Launch via LaunchBox plugin
   - If unavailable: ⬇️ Fall back to next method
2. **Auto-Detected Emulator** - Try LaunchBox config
   - If configured: ✅ Launch via detected emulator
   - If not: ⬇️ Fall back to next method
3. **Direct MAME Launch** - Use hardcoded config ✅ **NOW INCLUDES GUN GAMES**
   - Platform check: "Arcade", "Arcade MAME", **"MAME Gun Games"**
   - ROM fallback: Try `A:\Roms\MAME\{rom_name}.zip`
   - Command: `mame.exe -rompath A:\Roms\MAME -skip_gameinfo {rom_name}`
4. **LaunchBox.exe** - Last resort fallback

---

## 📋 Testing Steps

### 1. Restart Backend (REQUIRED!)
```powershell
# Stop backend with Ctrl+C, then:
python backend/app.py
```

### 2. Verify Config Loaded
Look for in backend logs:
- "LaunchBox parser ready"
- "allow_direct_mame: true" in config

### 3. Test Gun Game Launch
1. Open LaunchBox LoRa panel
2. Filter platform: "MAME Gun Games"
3. Select a game (e.g., "Area 51", "Time Crisis")
4. Click Launch
5. Should see MAME launch with the gun game

### 4. Expected Behavior
- ✅ MAME window opens
- ✅ Gun game loads
- ✅ Game runs in fullscreen (may need to press F key for fullscreen)
- ✅ No plugin error

### 5. If Still Fails
Check:
- Backend restarted after config changes?
- ROM file exists at `A:\Roms\MAME\{game}.zip`?
- MAME executable exists at `A:\Emulators\MAME\mame.exe`?
- Check backend logs for specific error

---

## 🔍 Verification Commands

### Check MAME Executable
```bash
ls -lh /mnt/a/Emulators/MAME/mame.exe
```

### Check Gun Games Platform XML
```bash
ls -lh /mnt/a/LaunchBox/Data/Platforms/MAME\ Gun\ Games.xml
```

### Test Backend Health
```bash
curl http://localhost:8888/health
```

### Test LaunchBox Plugin
```bash
curl http://localhost:9999/health
# If this fails, plugin bridge is down (expected)
```

---

## 📁 Files Modified

1. **backend/services/launcher.py**
   - Line 881: Added "MAME Gun Games" to direct launch check
   - Line 1137: Added "MAME Gun Games" to ROM fallback

2. **config/launchers.json**
   - Changed `allow_direct_mame` from `false` to `true`
   - Added complete MAME emulator configuration

---

## 🎮 Supported Gun Games

MAME Gun Games platform includes ~200-300 light gun arcade games:
- Area 51
- Time Crisis
- Police Trainer
- Virtua Cop
- House of the Dead
- Beast Busters
- Lethal Enforcers
- Operation Wolf
- And many more...

All games use same MAME emulator, same ROM path (`A:\Roms\MAME\`), no special configuration needed.

---

## 💡 Pro Tips

1. **Always restart backend after config changes** - Config doesn't auto-reload!
2. **Gun games need light gun hardware** - For proper play (Sinden, Gun4IR, etc.)
3. **Plugin bridge is preferred** - If it's working, it's more reliable than direct launch
4. **Check ROM names** - MAME ROMs must match exact MAME ROM names (e.g., `area51.zip`)

---

## ✅ Status

**MAME Gun Games: READY FOR TESTING**

All three fixes applied. Waiting for backend restart and test launch.

---

**Next Steps:**
1. User restarts backend
2. User tests gun game launch
3. Verify success or troubleshoot specific errors
