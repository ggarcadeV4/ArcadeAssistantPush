# Arcade Assistant Troubleshooting Guide

## Quick Fixes

### Backend Won't Start

**Symptom:** "Backend imports" fails in pre-flight check

**Fix:**
1. Close any running Arcade Assistant windows
2. Open PowerShell/CMD in the Arcade Assistant folder
3. Run: `python -c "from backend.app import app"`
4. The error message will tell you exactly what's wrong
5. Common issues:
   - **ImportError** - A module is missing. Run `pip install -r requirements.txt`
   - **IndentationError** - A Python file has bad formatting. Contact support.
   - **ModuleNotFoundError** - Check that you're in the correct folder

### Port Already In Use

**Symptom:** "Port 8000/8787 may be in use" warning

**Fix:**
1. Check if Arcade Assistant is already running (look for AA Backend/Gateway windows)
2. Close those windows and try again
3. If the issue persists, find what's using the port:
   ```powershell
   netstat -ano | findstr :8000
   netstat -ano | findstr :8787
   ```

### A: Drive Not Accessible

**Symptom:** "A: drive not accessible" error

**Fix:**
1. Make sure your external drive (with LaunchBox) is plugged in
2. Check that it's mapped to drive letter A:
3. To map a drive: Open File Explorer → Right-click "This PC" → "Map network drive" OR use `subst A: D:\YourFolder`

### Game Library Empty / Won't Load

**Symptom:** No games show in the LoRa panel

**Fixes:**
1. **Rebuild the game cache:**
   ```powershell
   python scripts/build_launchbox_cache.py
   ```
2. **Check LaunchBox folder exists:** `A:\LaunchBox` should contain `Data\` and `Games\`

### Gateway Won't Connect

**Symptom:** Backend runs but gateway fails

**Fix:**
1. Make sure Node.js is installed: `node --version` (should be 18+)
2. Install dependencies: `npm install`
3. Check for errors: `node gateway/server.js`

---

## Getting Help

If these fixes don't work:

1. **Run the pre-flight check:** `python scripts/preflight_check.py`
2. **Check the logs:**
   - `logs/backend.audit.err` - Backend errors
   - `logs/gateway.audit.err` - Gateway errors
3. **Contact support** with:
   - Screenshot of the pre-flight check output
   - Contents of error logs

---

## Prevention

To avoid future issues:

1. **Before updates:** Always run `python scripts/preflight_check.py`
2. **After updates:** Rebuild game cache if games don't appear
3. **Daily:** Make sure A: drive is connected before starting
