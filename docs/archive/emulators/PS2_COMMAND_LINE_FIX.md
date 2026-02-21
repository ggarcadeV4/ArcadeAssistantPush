# PS2 Command Line Fix

**Date:** 2025-10-18
**Issue:** PCSX2 launches but games don't load (blank window)
**Root Cause:** Missing command line flags for PCSX2-qt

---

## 🔴 Problem

PCSX2 was launching but showing a blank window instead of loading the game.

### Symptoms
- PCSX2-qt.exe process starts
- Window opens but remains blank
- No game loads
- No error messages

### Root Cause
PCSX2-qt (Qt version) requires specific command line flags to:
1. Launch in proper mode (not game browser)
2. Accept ROM path as argument
3. Run in fullscreen without menus

Without these flags, PCSX2-qt opens to the game browser/main menu, ignoring the ROM path.

---

## ✅ Fix Applied

### Updated Configuration
**File:** `config/launchers.json`

**Added command line flags:**
```json
"pcsx2": {
  "exe": "A:/Emulators/PCSX2/pcsx2-qt.exe",
  "platforms": ["Sony Playstation 2", "PS2", "PS2 Gun Games"],
  "flags": ["--fullscreen", "--nogui", "--"]
}
```

### Flag Explanations

1. **`--fullscreen`**
   - Launches game in fullscreen mode
   - No windowed mode borders
   - Immersive arcade experience

2. **`--nogui`**
   - Disables PCSX2 GUI/menus
   - Goes straight to game
   - No game browser or settings screens

3. **`--`** (separator)
   - Tells PCSX2: "everything after this is a file"
   - Prevents ROM path from being interpreted as flags
   - Standard Unix/Linux convention for command line tools

### Complete Command Line
```bash
pcsx2-qt.exe --fullscreen --nogui -- "A:\Console ROMs\playstation 2\Batman Begins (USA).iso"
```

**What happens:**
1. PCSX2 launches in fullscreen mode
2. No GUI/menus shown
3. Game loads directly from the extracted ISO
4. Player sees game, not PCSX2 interface

---

## 🎮 How PS2 Launch Works (Full Flow)

### Step 1: User Clicks Launch in LaunchBox LoRa
```
Game: Batman Begins (USA)
Platform: Sony PlayStation 2
ROM: A:\Console ROMs\playstation 2\Batman Begins (USA).gz
```

### Step 2: Backend Resolves ROM Path
```python
# Check if file exists
src = Path("A:/Console ROMs/playstation 2/Batman Begins (USA).gz")

# Resolve with alternative extensions
actual, how = resolve_rom_path(src)  # Finds .gz file
```

### Step 3: Extract Archive (if needed)
```python
# Detect .gz compression
result = extract_if_archive(actual, temp_dir)

# Extracts to: /tmp/aa_XXXXXX/Batman Begins (USA).iso
iso_path = result.extracted_path
```

### Step 4: Build PCSX2 Command
```python
cmd = [
    "A:/Emulators/PCSX2/pcsx2-qt.exe",
    "--fullscreen",
    "--nogui",
    "--",
    "/tmp/aa_XXXXXX/Batman Begins (USA).iso"
]
```

### Step 5: Launch PCSX2
```python
# Convert WSL paths to Windows paths
win_cmd = convert_wsl_paths(cmd)

# Execute
subprocess.Popen(win_cmd)
```

### Step 6: Cleanup After Exit
```python
# When PCSX2 closes, cleanup temp files
shutil.rmtree(temp_dir)  # Remove extracted ISO
```

---

## 📋 Testing Steps

### 1. Restart Backend (REQUIRED!)
```powershell
# Stop backend with Ctrl+C, then:
python backend/app.py
```

### 2. Test PS2 Game Launch
1. Open LaunchBox LoRa panel
2. Filter: "Sony PlayStation 2"
3. Select any game
4. Click Launch

### 3. Expected Behavior
- ✅ PCSX2 launches in fullscreen
- ✅ No PCSX2 menus/interface
- ✅ Game loads directly
- ✅ Plays normally
- ✅ Temp files cleaned up after exit

### 4. Alternative: Test Direct Command
For debugging, you can test manually:

```powershell
# From Windows:
cd "A:\Emulators\PCSX2"
.\pcsx2-qt.exe --fullscreen --nogui -- "A:\Console ROMs\playstation 2\Batman Begins (USA).gz"
```

**Note:** PCSX2 can read `.gz` files directly in some cases, but our backend extracts them first for better compatibility.

---

## 🔍 Troubleshooting

### Issue: PCSX2 Still Shows Blank Window
**Possible causes:**
1. Backend not restarted (old config still loaded)
2. ROM file doesn't exist or path is wrong
3. Extraction failed (check disk space)

**Solutions:**
- Restart backend: `python backend/app.py`
- Check ROM exists: `ls "A:\Console ROMs\playstation 2\"`
- Check backend logs for errors

### Issue: PCSX2 Shows GUI/Game Browser
**Cause:** `--nogui` flag not being passed

**Solutions:**
- Verify config updated: `grep "pcsx2" config/launchers.json`
- Backend must be restarted to load new config
- Check backend logs for command line being used

### Issue: Game Launches But Not Fullscreen
**Cause:** `--fullscreen` flag not working

**Solutions:**
- Check PCSX2 settings (might override command line)
- Try launching manually to verify flag works
- Alternative: Set fullscreen in PCSX2.ini

### Issue: Extraction Fails (Disk Space)
**Symptoms:** Error about insufficient space

**Solutions:**
- Free up space on temp drive
- Check: `AA_EXTRACT_MIN_FREE_GB` in `.env` (default 10GB)
- Adjust minimum: Set lower value if needed

---

## 📊 Complete Summary (All PS2 Fixes)

### Fix 1: BIOS Path (Previous)
- Updated: `A:\Bios\system` (was wrong path)
- Set default: `scph7001.bin`
- File: `A:\Emulators\PCSX2\inis\PCSX2.ini`

### Fix 2: Command Line Flags (This Fix)
- Added: `--fullscreen --nogui --`
- File: `config/launchers.json`

### Fix 3: Archive Extraction (Already Working)
- Auto-extracts: `.gz`, `.7z`, `.zip`
- Cleanup: Removes temp files after exit
- Code: `backend/services/launcher.py` (lines 619-664, 916-974)

---

## 🎯 Expected Result

After both fixes + backend restart:

```
User clicks "Batman Begins" in LaunchBox LoRa
  ↓
Backend extracts Batman Begins (USA).gz → .iso
  ↓
PCSX2 launches: --fullscreen --nogui -- {iso_path}
  ↓
Game plays in fullscreen (no PCSX2 interface)
  ↓
User plays game
  ↓
User exits game
  ↓
Temp ISO cleaned up automatically
```

**All working! ✅**

---

## 📁 Files Modified

1. **config/launchers.json**
   - Added PCSX2 flags: `["--fullscreen", "--nogui", "--"]`

2. **A:\Emulators\PCSX2\inis\PCSX2.ini** (previous fix)
   - Line 21: `Bios = A:\Bios\system`
   - Line 434: `BIOS = scph7001.bin`

---

## ✅ Status

**PS2/PCSX2: READY FOR FINAL TEST**

Both BIOS path and command line flags configured correctly. Just needs backend restart and test launch!
