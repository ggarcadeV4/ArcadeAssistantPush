# Basement Deployment Plan - FINAL REQUIREMENTS

## Your Setup (Confirmed):

### Physical Hardware:
- **Two arcade cabinets** in basement (treated independently)
- **Each cabinet has:**
  - Its own Windows PC
  - Its own A: drive (identical copies)
  - Dual monitors (game TV + marquee)
  - Controllers, light guns, LED strips

### A: Drive Setup:
- **Both cabinets have identical A: drives**
- You duplicated A: drive BEFORE creating Arcade Assistant
- Everything lives in the exact same paths on both:
  - `A:\LaunchBox`
  - `A:\Roms\MAME\`
  - `A:\Emulators\`
  - `A:\Bios\`
  - etc.

### Startup Behavior:
- **LaunchBox:** Auto-starts on boot ✅ (already configured)
- **Arcade Assistant:** Manual start for now
  - V2 feature: Make AA auto-start after installation
  - Current iteration: User manually launches AA on basement PC

### Network:
- **Internet available** in basement ✅
- AI features (Claude, OpenAI, ElevenLabs) will work
- Cloud sync (Supabase) will work

### Deployment Scope:
- **One cabinet at a time**
- Each cabinet gets its own independent AA installation
- Both run identical code, just on different PCs

---

## What This Means for Feature 3: Cabinet Duplication Documentation

### My Job (Feature 3):
Create a **portable deployment package** that works identically on Cabinet 1 OR Cabinet 2.

### The Package Includes:

#### 1. **Pre-Deployment Checklist** (`CABINET_PREREQUISITES.md`)
- [ ] Windows 10/11 installed
- [ ] A: drive accessible with LaunchBox installed
- [ ] Internet connection active
- [ ] Administrator access available

#### 2. **Installation Guide** (`CABINET_INSTALL.md`)
**Steps:**
1. Copy `Arcade Assistant Local` folder to basement PC (anywhere, e.g., `C:\ArcadeAssistant\`)
2. Install Node.js v18+ (provide download link + silent install command)
3. Install Python 3.10+ (provide download link + silent install command)
4. Run `install-cabinet.bat` (automated setup script)
5. Copy `.env` file with API keys
6. Test: Run `npm run dev` to verify everything works

#### 3. **Automated Setup Script** (`install-cabinet.bat`)
```batch
@echo off
echo ========================================
echo Arcade Assistant - Cabinet Installation
echo ========================================

REM Check for Node.js
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Node.js not found. Install from https://nodejs.org/
    pause
    exit /b 1
)

REM Check for Python
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python not found. Install from https://python.org/
    pause
    exit /b 1
)

REM Check for A: drive
if not exist A:\ (
    echo ERROR: A: drive not found. Ensure drive is connected.
    pause
    exit /b 1
)

REM Install dependencies
echo Installing Node.js dependencies...
call npm install

echo Installing frontend dependencies...
cd frontend
call npm install
cd ..

echo Installing backend dependencies...
pip install -r backend\requirements.txt

REM Check for .env file
if not exist .env (
    echo WARNING: .env file not found!
    echo Please copy .env from your dev PC before running.
    pause
)

echo ========================================
echo Installation complete!
echo ========================================
echo Next steps:
echo 1. Copy .env file with API keys
echo 2. Run: npm run dev
echo 3. Open browser to http://localhost:8787
pause
```

#### 4. **Desktop Shortcuts** (auto-created by install script)
- `Start Arcade Assistant.lnk` → Runs `npm run dev` in this folder
- `Open Arcade Assistant.lnk` → Opens browser to `http://localhost:8787`

#### 5. **Troubleshooting Guide** (`CABINET_TROUBLESHOOTING.md`)
Common issues:
- A: drive not accessible
- Port conflicts (8787, 8000)
- Missing API keys
- LaunchBox plugin not connecting
- Node.js/Python version issues

#### 6. **Environment Template** (`.env.cabinet-template`)
```env
# Gateway Configuration
PORT=8787
FASTAPI_URL=http://127.0.0.1:8000

# Cloud Services (REQUIRED - Copy from dev PC)
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-proj-...
ELEVENLABS_API_KEY=sk_...

# Voice Profiles
VICKY_VOICE_ID=ThT5KcBeYPX3keUQqHPh
LORA_VOICE_ID=pFZP5JQG7iQjIQuC4Bku
CHUCK_VOICE_ID=5Q0t7uMcjvnagumLfvZi
BLINKY_VOICE_ID=DTKMou8ccj1ZaWGBiotd
GUNNER_VOICE_ID=5Q0t7uMcjvnagumLfvZi

# Local Operations
AA_DRIVE_ROOT=A:\
AA_BACKUP_ON_WRITE=true
AA_DRY_RUN_DEFAULT=false
AA_QUICKSTART=true
AA_PRELOAD_LB_CACHE=true

# ... rest of settings
```

---

## Deployment Process (What You'll Do):

### For Cabinet 1 (Basement PC #1):
1. Copy `Arcade Assistant Local` folder to basement PC via USB drive
2. Run `install-cabinet.bat`
3. Copy `.env` file from dev PC
4. Run `npm run dev`
5. Test: Open `http://localhost:8787` and verify LoRa works
6. Done - leave it running or close for later

### For Cabinet 2 (Basement PC #2):
**Exact same process** - the deployment package is identical.

---

## V2 Feature: Auto-Start on Boot

**Not included in this iteration**, but documented for future:

### Windows Auto-Start Methods:
1. **Task Scheduler** (Recommended)
   - Create scheduled task: Run `start-arcade-assistant.bat` at login
   - Task runs as Administrator (needed for hotkey detection)
   - Delayed start: 30 seconds after login (wait for LaunchBox)

2. **Windows Service** (Advanced)
   - Install backend as Windows Service (`pm2` or `nssm`)
   - Install gateway as Windows Service
   - Auto-restart on failure

3. **Startup Folder Shortcut** (Simple but less reliable)
   - Copy shortcut to `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`
   - May not have Admin privileges for hotkey detection

**Decision:** Defer to V2 - manual start is fine for first iteration.

---

## Testing Plan (Before You Deploy):

### On Dev PC (THIS PC):
1. Create ZIP of `Arcade Assistant Local` folder
2. Extract ZIP to `D:\TestDeploy\` (simulate different PC)
3. Run `install-cabinet.bat` in test folder
4. Verify AA works from `D:\TestDeploy\`
5. If works → Package is portable ✅
6. If fails → Fix portability issues

### On Basement PC:
1. Deploy to Cabinet 1 first
2. Test all major features:
   - LaunchBox game launching
   - LoRa AI chat
   - Voice commands
   - Controller detection
3. If Cabinet 1 works → Deploy to Cabinet 2
4. If Cabinet 1 fails → Debug before touching Cabinet 2

---

## Files I'll Create for Feature 3:

1. ✅ `BASEMENT_DEPLOYMENT_PLAN.md` (this file)
2. 📝 `CABINET_PREREQUISITES.md` - What you need before installing
3. 📝 `CABINET_INSTALL.md` - Step-by-step installation guide
4. 📝 `install-cabinet.bat` - Automated setup script
5. 📝 `start-arcade-assistant.bat` - Startup script
6. 📝 `CABINET_TROUBLESHOOTING.md` - Common issues + fixes
7. 📝 `.env.cabinet-template` - Environment file template
8. 📝 `DEPLOYMENT_CHECKLIST.txt` - Quick reference checklist

---

## Timeline Estimate:

**Feature 3 (Cabinet Duplication Documentation):** 1 hour
- Write all 8 documents above
- Test portability on dev PC
- Create desktop shortcuts
- Package into ZIP

**Actual Deployment (You):** 30 minutes per cabinet
- Copy files: 10 minutes
- Run install script: 5 minutes
- Copy .env: 1 minute
- Test launch: 10 minutes
- Troubleshoot (if needed): 5 minutes

---

## Questions Before I Start Feature 3:

### Question 1: Where should AA live on basement PCs?
- [ ] `C:\ArcadeAssistant\` (clean, dedicated folder)
- [ ] `C:\Users\[User]\Desktop\Arcade Assistant Local\` (same as dev PC)
- [ ] `D:\ArcadeAssistant\` (different drive)
- [ ] Doesn't matter, my choice

### Question 2: Should install script create desktop shortcuts?
- [ ] Yes - create "Start Arcade Assistant" shortcut
- [ ] No - I'll launch manually from folder

### Question 3: What username on basement PCs?
- If same as dev PC (`Dad's PC`), paths will be identical
- If different, I need to make paths relative

### Question 4: Package format?
- [ ] ZIP file (you extract manually)
- [ ] Self-extracting installer (runs setup automatically)
- [ ] Git repository (you clone, I create .gitignore for secrets)
- [ ] Just the documentation (you copy folder manually)

---

## My Recommendation:

**Package Format:** ZIP file with all docs + install script
**Location:** `C:\ArcadeAssistant\` on basement PCs
**Shortcuts:** Yes, create Start + Open shortcuts on desktop
**Testing:** I test portability on dev PC before you deploy

**Ready to start Feature 3 when you give the word.** 🎯
