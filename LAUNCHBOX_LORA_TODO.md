# LaunchBox LoRa - TODO for Next Session

**Status:** Code fixes complete, testing blocked by port conflict
**Priority:** CRITICAL - Panel not camera-worthy until backend works

---

## 🚨 CRITICAL PATH (Must Complete First)

### Step 1: Fix Backend Port Conflict
- [ ] Open PowerShell as Administrator
- [ ] Run: `Get-Process python* | Stop-Process -Force`
- [ ] Verify port free: `Get-NetTCPConnection -LocalPort 8000 -State Listen`
- [ ] Start backend: `npm run dev:backend`
- [ ] Verify no port errors in terminal
- [ ] Test health: Open `http://localhost:8000/health` (should see JSON)

**Exit Criteria:** Backend running cleanly on port 8000 with no errors

---

## 🧪 TESTING (After Backend Running)

### Step 2: Verify Adapter Registration
- [ ] Run diagnostic: `python -c "import sys; sys.path.insert(0, '.'); from backend.services.launcher_registry import ADAPTER_STATUS; import json; print(json.dumps(ADAPTER_STATUS, indent=2))"`
- [ ] Should show: `"retroarch": "ok"`, `"pcsx2": "ok"`, `"direct_app": "ok"`

### Step 3: Test Panel Loading
- [ ] Navigate to LaunchBox LoRa panel
- [ ] Verify: No infinite "Loading..." spinner
- [ ] Verify: Games list appears
- [ ] Verify: All games clickable (not grayed out)
- [ ] Verify: No errors in browser console (F12)

### Step 4: Test Game Launches
- [ ] Launch MAME game (Arcade platform)
  - Expected: `"✅ [Title] launched via direct"` or `"detected_emulator"`
  - Verify: Game actually opens in emulator
- [ ] Launch NES/SNES game
  - Expected: `"✅ [Title] launched via detected_emulator"` (RetroArch adapter)
  - Verify: RetroArch opens with correct core
- [ ] Launch PS2 game
  - Expected: `"✅ [Title] launched via detected_emulator"` (PCSX2 adapter)
  - Verify: PCSX2 opens with game

### Step 5: Camera-Worthy Check
- [ ] Panel loads smoothly (no errors)
- [ ] Games visible and organized
- [ ] Filters and search work
- [ ] Games launch reliably
- [ ] Launch method shown in chat
- [ ] No console errors
- [ ] Professional appearance

**Exit Criteria:** Panel is demo-ready

---

## 📁 FILES CHANGED THIS SESSION

**Backend (New):**
- `backend/services/config_loader.py` - Config file loader
- `backend/utils/adapter_config.py` - Adapter enablement checker
- `backend/utils/__init__.py` - Package init

**Backend (Modified):**
- `backend/services/launcher_registry.py` - Now uses config file

**Frontend (Modified):**
- `frontend/src/panels/launchbox/LaunchBoxPanel.jsx` - Platform filter + retry logic

---

## 🔍 TROUBLESHOOTING

**If backend won't start:**
- Check for zombie processes: `Get-Process python*`
- Check what's using port 8000: `Get-NetTCPConnection -LocalPort 8000`
- Kill specific PID: `Stop-Process -Id [PID] -Force`

**If panel shows infinite loading:**
- Check backend is running: `http://localhost:8000/health`
- Check browser console (F12) for error messages
- Check Network tab for failed requests

**If games don't launch:**
- Check adapter status (Step 2 above)
- Check chat messages for error details
- Check backend terminal for error logs
- Verify config/launchers.json has correct paths

---

## 📖 REFERENCE DOCS

- `SESSION_HANDOFF_2025-10-24.md` - Full technical details
- `README.md` - Session log (last entry: 2025-10-24)
- `PLAN.md` - Original completion plan
- `config/launchers.json` - Adapter configuration

---

**Last Updated:** 2025-10-24 03:00 AM
**Next Session:** Continue immediately after fixing port conflict
