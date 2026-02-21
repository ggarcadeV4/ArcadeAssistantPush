# Arcade Assistant - Cabinet Troubleshooting Guide

**Quick Reference for Common Issues**

---

## Table of Contents

1. [Installation Issues](#installation-issues)
2. [Startup Issues](#startup-issues)
3. [A: Drive Issues](#a-drive-issues)
4. [API Key Issues](#api-key-issues)
5. [Network/Port Issues](#networkport-issues)
6. [LaunchBox Integration Issues](#launchbox-integration-issues)
7. [Performance Issues](#performance-issues)
8. [Emergency Procedures](#emergency-procedures)

---

## Installation Issues

### Issue: "Node.js not found"

**Error:**
```
[ERROR] Node.js not found!
Please install Node.js v18 or higher
```

**Solution:**
1. Download Node.js from: https://nodejs.org/
2. Install using default options
3. Restart the install-cabinet.bat script
4. Verify: Open Command Prompt, type `node --version`

---

### Issue: "Python not found"

**Error:**
```
[ERROR] Python not found!
Please install Python 3.10 or higher
```

**Solution:**
1. Download Python from: https://python.org/
2. **IMPORTANT:** Check "Add Python to PATH" during installation
3. Restart the install-cabinet.bat script
4. Verify: Open Command Prompt, type `python --version`

---

### Issue: "Failed to install dependencies"

**Error:**
```
[ERROR] Failed to install root dependencies!
```

**Solution:**
1. Check internet connection is active
2. Open Command Prompt as Administrator
3. Navigate to: `cd C:\ArcadeAssistant`
4. Run manually: `npm install`
5. Check for specific error messages and resolve them
6. Common fix: Delete `node_modules` folder and run `npm install` again

---

## Startup Issues

### Issue: "Services don't start when clicking shortcut"

**Symptoms:**
- Desktop shortcut does nothing
- Command windows flash and close immediately
- No browser window opens

**Solution:**
1. **Check .env file exists:**
   - Navigate to `C:\ArcadeAssistant\`
   - Verify `.env` file is present (not `.env.template`)
   - If missing, run `install-cabinet.bat` again

2. **Run as Administrator:**
   - Right-click "Arcade Assistant" shortcut
   - Select "Run as Administrator"
   - Click "Yes" on UAC prompt

3. **Check prerequisites:**
   - Open Command Prompt
   - Type: `node --version` (should show v18+)
   - Type: `python --version` (should show 3.10+)

---

### Issue: "Backend window shows errors and closes"

**Error:**
```
ModuleNotFoundError: No module named 'fastapi'
```

**Solution:**
1. Open Command Prompt as Administrator
2. Navigate to: `cd C:\ArcadeAssistant`
3. Run: `pip install -r backend\requirements.txt`
4. Wait for installation to complete
5. Try starting again

---

### Issue: "Gateway window shows errors"

**Error:**
```
Error: Cannot find module 'express'
```

**Solution:**
1. Open Command Prompt as Administrator
2. Navigate to: `cd C:\ArcadeAssistant`
3. Run: `npm install`
4. Wait for installation to complete
5. Try starting again

---

## A: Drive Issues

### Issue: "A: drive not accessible"

**Symptoms:**
- Warning during startup
- LoRa can't find games
- LaunchBox errors

**Solutions:**

**Solution 1: Verify drive letter**
1. Open File Explorer
2. Check if A: drive appears in "This PC"
3. If not visible, drive may not be connected
4. If visible but different letter (e.g., D:), edit `.env`:
   ```env
   AA_DRIVE_ROOT=D:\
   ```

**Solution 2: Check LaunchBox installation**
1. Open File Explorer → Navigate to A: drive
2. Verify `A:\LaunchBox\LaunchBox.exe` exists
3. Verify `A:\LaunchBox\Data\` folder exists
4. If missing, LaunchBox needs to be installed

**Solution 3: Permission issues**
1. Right-click A: drive → Properties
2. Go to Security tab
3. Verify your user account has "Read" permission
4. If not, click Edit → Add → Grant permissions

---

## API Key Issues

### Issue: "AI doesn't respond"

**Symptoms:**
- LoRa, Dewey, or other AI doesn't reply
- Console shows "Unauthorized" errors
- "Invalid API key" messages

**Solution:**
1. Open `C:\ArcadeAssistant\.env` in Notepad
2. Find these lines:
   ```env
   ANTHROPIC_API_KEY=
   OPENAI_API_KEY=
   ELEVENLABS_API_KEY=
   ```
3. Verify they are NOT blank
4. Verify they start with correct prefixes:
   - `ANTHROPIC_API_KEY=sk-ant-...`
   - `OPENAI_API_KEY=sk-proj-...`
   - `ELEVENLABS_API_KEY=sk_...`
5. If wrong, copy correct keys from dev PC
6. Save file
7. Restart Arcade Assistant (close command windows, launch again)

---

### Issue: "API key expired or invalid"

**Error:**
```
{
  "error": {
    "message": "Invalid API key",
    "type": "invalid_request_error"
  }
}
```

**Solution:**
1. Generate new API key from provider's website:
   - Anthropic Claude: https://console.anthropic.com/
   - OpenAI: https://platform.openai.com/api-keys
   - ElevenLabs: https://elevenlabs.io/
2. Update `.env` file with new key
3. Restart services

---

## Network/Port Issues

### Issue: "Port 8787 already in use"

**Error:**
```
Error: listen EADDRINUSE: address already in use :::8787
```

**Solution:**

**Solution 1: Close old instances**
1. Press Ctrl+Shift+Esc to open Task Manager
2. Go to "Details" tab
3. Find all `node.exe` processes
4. Right-click each → End Task
5. Try starting again

**Solution 2: Change port**
1. Open `.env` in Notepad
2. Change `PORT=8787` to `PORT=8788` (or any unused port)
3. Save file
4. Restart services
5. Open browser to `http://localhost:8788` instead

---

### Issue: "Port 8000 already in use"

**Error:**
```
ERROR:    [Errno 10048] error while attempting to bind on address ('0.0.0.0', 8000)
```

**Solution:**

**Solution 1: Close old instances**
1. Press Ctrl+Shift+Esc to open Task Manager
2. Go to "Details" tab
3. Find all `python.exe` processes
4. Right-click each → End Task
5. Try starting again

**Solution 2: Restart computer**
1. Save all work
2. Restart PC
3. Launch Arcade Assistant
4. Should work after restart

---

### Issue: "Browser shows 404 or can't connect"

**Symptoms:**
- `http://localhost:8787` doesn't load
- "This site can't be reached"
- "ERR_CONNECTION_REFUSED"

**Solution:**

**Step 1: Verify services are running**
1. Check if two command windows are open:
   - `AA Backend [AA-####]`
   - `AA Gateway [AA-####]`
2. If not, launch "Arcade Assistant" from desktop

**Step 2: Check for errors**
1. Look at Gateway window
2. Should see: `🚀 Gateway running on http://localhost:8787`
3. If you see errors instead, read error message and resolve

**Step 3: Wait longer**
1. Services take 10-30 seconds to fully start
2. Wait 30 seconds after launching
3. Try refreshing browser (F5)

**Step 4: Try different URL**
1. If `localhost` doesn't work, try: `http://127.0.0.1:8787`
2. Or check `.env` for correct PORT number

---

## LaunchBox Integration Issues

### Issue: "LoRa can't find any games"

**Symptoms:**
- LoRa says "No games found"
- Game list is empty
- LaunchBox integration not working

**Solution:**

**Step 1: Verify A: drive**
1. Open File Explorer → A: drive
2. Check `A:\LaunchBox\Data\Platforms\` folder exists
3. Check folder contains .xml files (one per platform)

**Step 2: Check cache loading**
1. Look at Backend window
2. Should see: `LaunchBox cache preload complete`
3. If you see errors about XML parsing, LaunchBox data may be corrupted

**Step 3: Force cache rebuild**
1. Close Arcade Assistant
2. Navigate to `C:\ArcadeAssistant\backend\`
3. Delete `launchbox_cache.pkl` file (if it exists)
4. Restart Arcade Assistant
5. Cache will rebuild from XML files

---

### Issue: "Games launch but don't start"

**Symptoms:**
- LoRa confirms launch
- No emulator window appears
- Or emulator appears then crashes

**Solution:**

**Step 1: Check emulator paths**
1. Open File Explorer → `A:\Emulators\`
2. Verify emulator folders exist:
   - `MAME\mame.exe`
   - `RetroArch\retroarch.exe`
   - `PCSX2\pcsx2.exe`
   - etc.

**Step 2: Check ROM paths**
1. Open File Explorer → `A:\Roms\`
2. Verify ROM folders match platforms:
   - `MAME\` for arcade games
   - `Sony Playstation 2\` for PS2 games
   - etc.

**Step 3: Enable launch tracing**
1. Open `.env` in Notepad
2. Verify: `AA_LAUNCH_TRACE=1`
3. Save file
4. Restart services
5. Try launching game again
6. Check backend window for detailed launch logs

---

### Issue: "LaunchBox Plugin not connecting"

**Error:**
```
Plugin health check failed: Connection to localhost timed out
```

**Solution:**

**Solution 1: Plugin not enabled**
- This is just a warning if you're not using the LaunchBox plugin
- Arcade Assistant works fine without it
- You can ignore this message

**Solution 2: If you DO want plugin integration**
1. Install plugin in LaunchBox
2. Verify LaunchBox is running
3. Check port 10099 is not blocked by firewall
4. Restart both LaunchBox and Arcade Assistant

---

## Performance Issues

### Issue: "UI is slow or laggy"

**Symptoms:**
- Browser feels sluggish
- AI responses take forever
- Pages take long to load

**Solution:**

**Solution 1: Close other programs**
1. Press Ctrl+Shift+Esc (Task Manager)
2. Close unnecessary programs
3. Especially browsers, games, video players

**Solution 2: Check system resources**
1. In Task Manager, check "Performance" tab
2. If CPU is at 100%, something is using too much
3. If RAM is full, close programs or add more RAM

**Solution 3: Reduce cache size**
1. Open `.env` in Notepad
2. Change `AA_PRELOAD_LB_CACHE=true` to `false`
3. Save and restart
4. Cache will load on-demand instead of all at once

---

### Issue: "Backend/Gateway crashes or freezes"

**Symptoms:**
- Command windows close unexpectedly
- Services stop responding
- UI stops updating

**Solution:**

**Solution 1: Check logs**
1. Navigate to `C:\ArcadeAssistant\`
2. Open `backend.log` and `gateway.log`
3. Look for error messages near the end
4. Google the error message for solutions

**Solution 2: Restart services**
1. Close all command windows
2. Wait 5 seconds
3. Launch "Arcade Assistant" again

**Solution 3: Restart computer**
1. If issue persists, restart PC
2. Launch Arcade Assistant fresh
3. Should resolve most transient issues

---

## Emergency Procedures

### Complete Reset (Nuclear Option)

**Use this only if nothing else works!**

1. **Backup your .env file:**
   - Copy `C:\ArcadeAssistant\.env` to desktop
   - You'll need your API keys later

2. **Delete installation:**
   - Delete entire `C:\ArcadeAssistant\` folder
   - Empty Recycle Bin

3. **Reinstall from scratch:**
   - Copy fresh files from USB drive
   - Run `install-cabinet.bat`
   - Enter same serial number as before
   - Copy API keys back from backup

---

### Get Help

If you've tried everything and still can't resolve the issue:

1. **Collect diagnostic information:**
   - Serial number from Desktop/startup.log
   - Error messages from command windows
   - Screenshots of errors
   - Contents of `backend.log` and `gateway.log`

2. **Check documentation:**
   - CABINET_INSTALL.md
   - BASEMENT_DEPLOYMENT_PLAN.md
   - README.md

3. **System requirements:**
   - Windows 10/11
   - 8GB RAM minimum (16GB recommended)
   - 50GB free disk space
   - Internet connection
   - A: drive with LaunchBox

---

## Prevention Tips

### Avoid Common Mistakes

1. **Never rename the installation folder** after running install script
2. **Never delete .env file** - it contains your config
3. **Always run as Administrator** when launching
4. **Keep API keys secret** - don't share in screenshots
5. **Wait for services to start** before opening browser
6. **Don't close command windows** while using AA

### Regular Maintenance

1. **Weekly:** Restart Arcade Assistant (fresh start)
2. **Monthly:** Check for Windows updates
3. **As needed:** Update API keys if they expire
4. **Before updates:** Backup .env file

---

## Log Files Reference

Useful files for troubleshooting:

- `C:\ArcadeAssistant\backend.log` - Backend errors
- `C:\ArcadeAssistant\gateway.log` - Gateway errors
- `C:\ArcadeAssistant\startup.log` - Launch timestamps
- `C:\ArcadeAssistant\SERIAL_REGISTRY.log` - Installation history
- `C:\ArcadeAssistant\logs\changes.jsonl` - Config changes
- `C:\ArcadeAssistant\logs\agent_calls\` - AI agent activity

---

## Quick Diagnostic Checklist

When something goes wrong, check these in order:

- [ ] Are both command windows (Backend + Gateway) open and running?
- [ ] Does `http://localhost:8787` load in browser?
- [ ] Is A: drive accessible in File Explorer?
- [ ] Does `.env` file exist and have API keys filled in?
- [ ] Did you wait 30 seconds after launch before testing?
- [ ] Are you running as Administrator?
- [ ] Is internet connection active?
- [ ] Did you restart after making changes?

**If all are yes and it still doesn't work:** See "Emergency Procedures" section above.
