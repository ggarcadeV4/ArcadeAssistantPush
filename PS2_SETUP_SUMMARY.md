# PS2/PCSX2 Setup Summary

**Date:** 2025-10-18
**Status:** ✅ CONFIGURED & READY FOR TESTING
**Issue Fixed:** BIOS path persistence

---

## 🔴 Problem: BIOS Path Kept Resetting

### What Was Happening
- PCSX2 was "forgetting" where the BIOS files were located
- BIOS path was pointing to wrong/non-existent directory
- User had to manually select BIOS every session

### Root Cause
**Incorrect BIOS path in PCSX2.ini:**
```ini
Bios = ..\..\Bios\351ELEC-20211122-BIOS  # ❌ Wrong path (doesn't exist)
```

This relative path doesn't exist and was from a different system (351ELEC).

---

## ✅ Fixes Applied

### Fix 1: Updated BIOS Folder Path
**File:** `/mnt/a/Emulators/PCSX2/inis/PCSX2.ini` (Line 21)

**Before:**
```ini
Bios = ..\..\Bios\351ELEC-20211122-BIOS
```

**After:**
```ini
Bios = A:\Bios\system
```

### Fix 2: Set Default BIOS File
**File:** `/mnt/a/Emulators/PCSX2/inis/PCSX2.ini` (Line 434)

**Before:**
```ini
BIOS =
```

**After:**
```ini
BIOS = scph7001.bin
```

**Why scph7001.bin?**
- USA BIOS (v4.0)
- Most compatible with USA/NTSC games
- Recommended for general use

---

## 📁 BIOS File Locations

### Actual BIOS Location (Verified)
```
A:\Bios\system\
├── scph1001.bin  (512 KB) - USA v1.0
├── scph5500.bin  (512 KB) - Japan v2.0
├── scph5501.bin  (512 KB) - USA v2.0
├── scph5502.bin  (512 KB) - Europe v2.0
├── scph7001.bin  (512 KB) - USA v4.0 ✅ SELECTED
└── scph7502.bin  (512 KB) - Europe v4.0
```

### PCSX2 Configuration Now Points To
- **BIOS Folder:** `A:\Bios\system`
- **Selected BIOS:** `scph7001.bin`
- **Status:** ✅ Configured and should persist across restarts

---

## 🎮 PS2 Adapter Features

The PS2 adapter has advanced capabilities built-in:

### Archive Extraction Support
- **Supported formats:** `.7z`, `.zip`, `.gz`
- **How it works:**
  1. Detects compressed ROM file
  2. Extracts to temp directory
  3. Launches PCSX2 with extracted file
  4. Cleans up temp files after exit

### Platform Detection
Recognizes multiple PS2 platform names:
- "Sony PlayStation 2"
- "PlayStation 2"
- "PS2"
- "PS2 Gun Games"

### WSL Path Conversion
Automatically converts paths between WSL and Windows:
- `/mnt/a/` ↔ `A:\`
- Ensures compatibility when running backend in WSL

---

## 🚀 Testing Steps

### 1. Restart Backend (REQUIRED!)
Since we updated PCSX2.ini and config/launchers.json:

```powershell
# Stop backend with Ctrl+C, then restart:
python backend/app.py
```

### 2. Verify PCSX2 BIOS Configuration
Open PCSX2 manually to confirm settings:

```powershell
A:\Emulators\PCSX2\pcsx2-qt.exe
```

Check:
- ✅ Settings → BIOS → Should show `scph7001.bin` selected
- ✅ BIOS folder path: `A:\Bios\system`
- ✅ Close PCSX2 (settings should be saved)

### 3. Test PS2 Game Launch
1. Open LaunchBox LoRa panel
2. Filter platform: "Sony PlayStation 2"
3. Select a game
4. Click Launch
5. PCSX2 should launch without asking for BIOS

### 4. Expected Behavior
- ✅ PCSX2 opens automatically
- ✅ No BIOS selection prompt
- ✅ Game loads and runs
- ✅ Settings persist after closing

---

## 🔍 Verification Commands

### Check BIOS Files Exist
```bash
ls -lh /mnt/a/Bios/system/scph*.bin
```

### Check PCSX2 Configuration
```bash
grep "Bios = " /mnt/a/Emulators/PCSX2/inis/PCSX2.ini
grep "BIOS = " /mnt/a/Emulators/PCSX2/inis/PCSX2.ini
```

### Test Backend Health
```bash
curl http://localhost:8888/health
```

### Check PS2 Platform Games
```bash
curl http://localhost:8888/api/launchbox/platforms | grep -i "playstation 2"
```

---

## 📋 Launch Chain for PS2 Games

When you launch a PS2 game from LaunchBox LoRa:

1. **Plugin Bridge** (localhost:9999)
   - If available: ✅ Launch via LaunchBox plugin
   - If not: ⬇️ Fall back

2. **Auto-Detected Emulator**
   - Reads LaunchBox emulator config
   - If PCSX2 configured: ✅ Launch
   - If not: ⬇️ Fall back

3. **Direct PCSX2 Launch** ✅ **ENABLED**
   - Uses: `A:\Emulators\PCSX2\pcsx2-qt.exe`
   - BIOS: `A:\Bios\system\scph7001.bin`
   - Auto-extracts compressed ROMs
   - Command: `pcsx2-qt.exe {rom_path}`

4. **LaunchBox.exe** (Last resort)

---

## 📁 Files Modified

### Configuration Files
1. **A:\Emulators\PCSX2\inis\PCSX2.ini**
   - Line 21: Updated BIOS folder path
   - Line 434: Set default BIOS file

2. **config/launchers.json** (from previous session)
   - `allow_direct_pcsx2: true`
   - PCSX2 emulator configuration with platforms

### Environment Variables (Already Set)
- `AA_ALLOW_DIRECT_PCSX2=true` in `.env`

---

## 💡 Pro Tips

### 1. BIOS Path is Absolute
Using absolute path `A:\Bios\system` instead of relative path ensures it always works.

### 2. Backend Must Restart
Config changes don't auto-reload! Always restart backend after modifying configs.

### 3. Compressed ROMs Work
PS2 games in `.7z`, `.zip`, or `.gz` format will auto-extract - no manual extraction needed!

### 4. Multiple BIOS Available
If a specific game has issues with scph7001.bin:
1. Open PCSX2 settings
2. Select different BIOS (scph5501.bin, scph7502.bin, etc.)
3. Close and save

### 5. Check Logs for Issues
If launch fails, check backend logs for specific errors (ROM not found, BIOS missing, etc.)

---

## 🎯 Summary of Changes (Both Tasks)

### MAME Gun Games ✅
- Added "MAME Gun Games" to ROM fallback (launcher.py:1137)
- Added "MAME Gun Games" to direct launch (launcher.py:881)
- Enabled direct MAME launch in config
- Added MAME configuration with platforms

### PS2/PCSX2 ✅
- Fixed BIOS folder path in PCSX2.ini
- Set default BIOS to scph7001.bin
- PCSX2 adapter already enabled and configured
- Archive extraction support built-in

---

## ✅ Ready for Testing!

**Both systems configured and ready:**
1. **MAME Gun Games** - Should launch directly via MAME
2. **PS2** - Should launch with correct BIOS, no prompts

**Next Step:** Restart backend and test both!

```powershell
# Restart backend
python backend/app.py

# Then test:
# 1. MAME gun game (Area 51, Time Crisis)
# 2. PS2 game (any game)
```

---

**Status: 🟢 READY FOR TESTING**

Let me know the results!
