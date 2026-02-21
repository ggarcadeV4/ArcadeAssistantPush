# Arcade Assistant - Cabinet Quick Reference

**For Basement Arcade Cabinets** | Version 1.0 | December 2025

---

## Quick Start

**To launch Arcade Assistant:**
1. Double-click **"Arcade Assistant"** on desktop
2. Wait 10 seconds
3. Double-click **"Open Arcade Assistant"**

**That's it!**

---

## What You'll See

### When Services Start:
- Two command windows open:
  - `AA Backend [AA-####]` (Python/FastAPI)
  - `AA Gateway [AA-####]` (Node.js/Express)
- **Do NOT close these windows!**

### When Browser Opens:
- URL: `http://localhost:8787`
- Arcade Assistant interface with all panels
- Click any panel to interact

---

## Daily Use

### Starting AA:
```
Desktop → "Arcade Assistant" → Wait 10 sec → "Open Arcade Assistant"
```

### Stopping AA:
```
Close Backend window → Close Gateway window → Close browser
```

### Quick Test:
```
Click "LaunchBox LoRa" → Type "show me arcade games" → Press Enter
If LoRa responds: ✅ Working!
```

---

## Common Tasks

### Talk to LoRa (LaunchBox Games):
- Click **"LaunchBox LoRa"** panel
- Ask about games: "What arcade games do you have?"
- Launch games: "Launch Street Fighter 2"
- Get recommendations: "Suggest a fighting game"

### Talk to Dewey (General AI):
- Click **"Dewey"** panel
- Ask anything: "Tell me about this cabinet"
- Get help: "How do I configure controllers?"

### ScoreKeeper (Tournaments):
- Click **"ScoreKeeper Sam"** panel
- Create bracket: "Start an 8-player tournament"
- Track scores: Click to advance winners

### Controller Setup:
- Click **"Controller Chuck"** panel
- Detect controllers: Auto-detects on panel load
- Get help: "How do I configure player 1?"

### LED Lighting:
- Click **"LED Blinky"** panel
- Test lights: "Flash all LEDs red"
- Game-specific: "What lighting is configured for Pac-Man?"

---

## Serial Number

**Your cabinet is:** `[Check command window title]`

Example: If window shows `AA Backend [AA-0001]`, your serial is `AA-0001`

**Why it matters:**
- Identifies this specific cabinet
- Used in logs and analytics
- Required for support

---

## File Locations

### Installation:
```
C:\ArcadeAssistant\
```

### Configuration:
```
C:\ArcadeAssistant\.env (API keys and settings)
```

### Logs:
```
C:\ArcadeAssistant\backend.log
C:\ArcadeAssistant\gateway.log
C:\ArcadeAssistant\startup.log
```

### LaunchBox & ROMs:
```
A:\LaunchBox\
A:\Roms\
A:\Emulators\
```

---

## Troubleshooting

### Problem: Services won't start
**Fix:** Right-click "Arcade Assistant" → "Run as Administrator"

### Problem: Browser shows errors
**Fix:** Wait 30 seconds, refresh browser (F5)

### Problem: A: drive not found
**Fix:** Check drive letter in File Explorer, update `.env` if needed

### Problem: AI doesn't respond
**Fix:** Check API keys in `.env` file

### Problem: Port already in use
**Fix:** Close all command windows, restart PC, try again

**For more help:** See `CABINET_TROUBLESHOOTING.md`

---

## Updates

### When new version is released:
1. Close all Arcade Assistant windows
2. Copy new files from USB to `C:\ArcadeAssistant\`
3. **Do NOT overwrite .env file** (keep your keys)
4. Relaunch Arcade Assistant

---

## System Requirements

### Minimum:
- Windows 10/11
- 8GB RAM
- 50GB free disk space
- Internet connection
- A: drive with LaunchBox

### Recommended:
- Windows 11
- 16GB RAM
- 100GB free disk space
- Wired ethernet
- Dual monitors (game + marquee)

---

## Support Files

- **CABINET_INSTALL.md** - Full installation guide
- **CABINET_TROUBLESHOOTING.md** - Detailed problem solving
- **BASEMENT_DEPLOYMENT_PLAN.md** - Technical architecture
- **SERIAL_REGISTRY.md** - Cabinet tracking

---

## Important Notes

✅ **DO:**
- Run as Administrator
- Keep command windows open while using AA
- Wait for services to fully start
- Back up .env file before updates

❌ **DON'T:**
- Close command windows while AA is running
- Delete .env file
- Share API keys
- Rename installation folder after setup

---

## Emergency Contact

If something is broken and you can't fix it:

1. **Check logs** for error messages
2. **See CABINET_TROUBLESHOOTING.md** for solutions
3. **Complete reset** (last resort): Delete folder, reinstall from USB

---

## Quick Commands

### Check if services are running:
```
Open Task Manager (Ctrl+Shift+Esc)
Look for: python.exe and node.exe
```

### Check serial number:
```
Open: C:\ArcadeAssistant\.env
Find: DEVICE_SERIAL=AA-####
```

### View logs:
```
Navigate to: C:\ArcadeAssistant\
Open: backend.log or gateway.log
```

---

**Need help? Check CABINET_TROUBLESHOOTING.md for detailed solutions.**
