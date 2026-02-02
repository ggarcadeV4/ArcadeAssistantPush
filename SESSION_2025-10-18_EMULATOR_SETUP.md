# Session 2025-10-18 - Emulator Setup Summary

**Date:** 2025-10-18
**Duration:** ~3 hours
**Focus:** TeknoParrot, Daphne/Hypseus, PS2/PCSX2

---

## ✅ What Was Accomplished Tonight

### 1. TeknoParrot (Taito Type X) - ✅ WORKING
- Updated all UserProfiles XML files (D:\ → A:\)
- Created 62 game profile aliases in `/mnt/a/configs/teknoparrot-aliases.json`
- Simplified adapter to just open TeknoParrot UI with game loaded
- User will configure TeknoParrot for auto-launch/fullscreen manually

### 2. Daphne/Hypseus - ✅ WORKING
- Created `direct_app_adapter.py` to handle AHK script launches
- Fixed ApplicationPath resolution bug (was using wrong base directory)
- Normalized backslash paths for WSL compatibility
- Successfully launching Dragon's Lair and other games

### 3. American Laser Games (Singe2) - ✅ CONFIGURED
- Updated all AHK scripts (D:\ → A:\)
- Backed up to SINGE2.backup-YYYYMMDD directories
- Ready for light gun hardware testing

### 4. PS2 (PCSX2) - ⚙️ NEEDS ONE MORE STEP
- Adapter already existed and is enabled
- Added to `config/launchers.json`
- Copied 6 BIOS files to `/mnt/a/Emulators/PCSX2/bios/`
- **NEXT:** User needs to open PCSX2 manually once to select BIOS

---

## 🔴 IMPORTANT: Why Fixes "Forget" Between Sessions

### The Problem
When you close the backend and start a new session, MAME/emulators stop working even though we fixed them before.

### Why This Happens
**The backend caches configuration when it starts!**

When you run `python backend/app.py`, it:
1. Loads `config/launchers.json` into memory
2. Registers adapters based on `.env` flags
3. Keeps that configuration until stopped

**File changes don't auto-reload** - the backend keeps using the OLD config in memory!

### The Solution
**ALWAYS restart the backend after changing configuration:**

```powershell
# Stop backend (Ctrl+C in the PowerShell window)
# Then restart:
python backend/app.py
```

### What Persists vs What Doesn't

**✅ PERSISTS (saved to disk):**
- `config/launchers.json` - emulator paths
- `.env` - environment flags
- `/mnt/a/configs/*.json` - game aliases, etc.
- Adapter code changes
- BIOS files you copied
- Path updates (D:\ → A:\)

**❌ DOESN'T AUTO-UPDATE (needs backend restart):**
- Adapters enabled/disabled
- Emulator exe paths
- Platform mappings
- ROM resolution logic

### Simple Rule
**Changed a config file? Restart the backend!**

---

## 📋 Checklist for Starting Next Session

### To Restore Context
Tell Claude:
> "Read SESSION_2025-10-18_EMULATOR_SETUP.md and the last 60 lines of README.md to catch up."

### To Make Sure Everything Works
1. **Start Backend:**
   ```powershell
   cd "C:\Users\Dad's PC\Desktop\Arcade Assistant Local"
   python backend/app.py
   ```

2. **Verify it loaded configs:**
   - Look for "LaunchBox parser ready" in logs
   - Check for "PCSX2 adapter registered" or similar

3. **Test a working platform:**
   - Launch a Daphne game (Dragon's Lair)
   - Should work immediately

4. **If it doesn't work:**
   - Backend probably using old config
   - Restart backend with Ctrl+C → `python backend/app.py`

---

## 🎯 Next Session Tasks

### Immediate: PS2 Setup
1. Open PCSX2 manually: `A:\Emulators\PCSX2\pcsx2-qt.exe`
2. Go to Settings → BIOS
3. Select a BIOS (recommend scph7001.bin for USA)
4. Close PCSX2
5. Test launching PS2 game from LaunchBox LoRa
6. Create PS2_SETUP_SUMMARY.md if successful

### Future Platforms
User can choose:
- Dolphin (GameCube/Wii)
- PPSSPP (PSP)
- Model 2 (Sega Model 2 arcade)
- Supermodel (Sega Model 3 arcade)
- Or any other emulator in `/mnt/a/Emulators/`

---

## 📁 Key Files Modified Tonight

### Configuration
- `config/launchers.json` - Added teknoparrot, pcsx2
- `/mnt/a/configs/teknoparrot-aliases.json` - 62 game mappings

### Code
- `backend/services/adapters/direct_app_adapter.py` - NEW (handles AHK scripts)
- `backend/services/adapters/teknoparrot_adapter.py` - Simplified
- `backend/services/launcher_registry.py` - Registered direct_app adapter

### Data
- `/mnt/a/Emulators/TeknoParrot Latest/UserProfiles/*.xml` - D:→A: (300+ files)
- `/mnt/a/Gun Build/Roms/SINGE2/*.ahk` - D:→A:
- `/mnt/a/Emulators/PCSX2/bios/scph*.bin` - 6 BIOS files copied

### Documentation
- `DAPHNE_SETUP_SUMMARY.md` - Complete setup guide
- `SESSION_2025-10-18_EMULATOR_SETUP.md` - This file

---

## 🔍 Quick Reference

### Verify Backend is Using Latest Config
```powershell
# After starting backend, check logs for:
"pcsx2 adapter registered"  # Should see this
"teknoparrot adapter registered"  # Should see this
"direct_app adapter registered"  # Should see this
```

### Test Endpoints
```bash
curl http://localhost:8888/health
curl http://localhost:8888/api/launchbox/stats
```

### Backend Restart (Most Common Fix!)
```powershell
# In PowerShell window running backend:
Ctrl+C  # Stop
python backend/app.py  # Restart
```

---

## 💡 Pro Tips

1. **Keep backend visible** - Run in PowerShell (not background) to see logs
2. **Restart after config changes** - Don't assume auto-reload
3. **Check timestamps** - `ls -lt config/` shows if files are actually saved
4. **One emulator at a time** - Get one working before moving to next
5. **Document as you go** - Create PLATFORM_SETUP.md for each emulator

---

**Ready for next session!** Just restart the backend and everything will work. 🚀
