# Arcade Assistant - Cabinet Installation Guide

**Version:** 1.0
**Date:** December 2025
**Estimated Time:** 30 minutes per cabinet

---

## Overview

This guide walks you through installing Arcade Assistant on a basement arcade cabinet PC. The installation process is **identical** for all cabinets - only the serial number changes.

---

## Prerequisites Checklist

Before you begin, ensure the cabinet PC has:

- [ ] **Windows 10 or 11** installed and updated
- [ ] **A: drive** accessible with LaunchBox installed
- [ ] **Internet connection** active (for AI features)
- [ ] **Administrator access** (you can right-click → "Run as Administrator")
- [ ] **Node.js v18+** installed ([Download](https://nodejs.org/))
- [ ] **Python 3.10+** installed ([Download](https://python.org/))
- [ ] **USB drive** with Arcade Assistant files copied from dev PC

---

## Installation Steps

### Step 1: Copy Files to Cabinet PC

1. **Plug in USB drive** containing Arcade Assistant
2. **Open File Explorer** and navigate to the USB drive
3. **Copy the entire `ArcadeAssistant` folder** to `C:\`
   - Final location: `C:\ArcadeAssistant\`
   - **Do NOT** rename the folder

**Expected result:** You should see `C:\ArcadeAssistant\` with all files inside.

---

### Step 2: Run Installation Script

1. **Navigate to** `C:\ArcadeAssistant\`
2. **Right-click** `install-cabinet.bat`
3. **Select** "Run as Administrator"
4. **Click "Yes"** on the UAC prompt

The installation script will now run in a command window.

---

### Step 3: Installation Wizard Prompts

The script will check prerequisites and ask you questions. Here's what to expect:

#### **Prompt 1: Administrator Warning**
```
[WARNING] Not running as Administrator
Right-click this file and select "Run as Administrator"
```
**What to do:** Close the window, right-click the .bat file, select "Run as Administrator"

#### **Prompt 2: Prerequisites Check**
```
[1/8] Checking prerequisites...
[OK] Node.js found: v18.17.0
[OK] Python found: Python 3.10.11
[OK] A: drive accessible
```
**What to do:** Verify all show `[OK]`. If any show `[ERROR]`, install the missing software.

#### **Prompt 3: Device Serialization**
```
[2/8] Device Serialization

Enter cabinet serial number (e.g., AA-0001): _
```
**What to enter:**
- **Cabinet 1:** `AA-0001`
- **Cabinet 2:** `AA-0002`
- **Future cabinets:** `AA-0003`, `AA-0004`, etc.

**IMPORTANT:** Serial numbers must be **unique** and **never reused**.

#### **Prompt 4: Device Name**
```
Enter cabinet name (e.g., Basement Cabinet 1): _
```
**What to enter:**
- **Cabinet 1:** `Basement Cabinet 1`
- **Cabinet 2:** `Basement Cabinet 2`
- Or any descriptive name you prefer

#### **Prompts 5-7: Dependency Installation**
```
[3/8] Creating environment configuration...
[4/8] Installing Node.js dependencies...
[5/8] Installing frontend dependencies...
[6/8] Installing backend dependencies...
```
**What to do:** Wait. This takes 3-5 minutes. You'll see lots of output scrolling by - this is normal.

#### **Prompt 8: Desktop Shortcuts**
```
[7/8] Creating desktop shortcuts...
[OK] Desktop shortcut "Arcade Assistant" created
[OK] Desktop shortcut "Open Arcade Assistant" created
```
**What to do:** Nothing - shortcuts are created automatically.

#### **Prompt 9: Installation Complete**
```
========================================
  INSTALLATION COMPLETE!
========================================

Device Serial: AA-0001
Device Name: Basement Cabinet 1

NEXT STEPS:
1. Edit .env file and add your API keys
2. Double-click "Arcade Assistant" on desktop
3. Double-click "Open Arcade Assistant"
```
**What to do:** Press any key to close the installer.

---

### Step 4: Add API Keys

**CRITICAL:** Arcade Assistant **will not work** without API keys.

1. **Navigate to** `C:\ArcadeAssistant\`
2. **Right-click** `.env` file
3. **Select** "Edit" or "Open with Notepad"
4. **Find these lines:**
   ```env
   ANTHROPIC_API_KEY=
   OPENAI_API_KEY=
   ELEVENLABS_API_KEY=
   ```
5. **Paste your API keys** from the dev PC's `.env` file:
   ```env
   ANTHROPIC_API_KEY=sk-ant-api03-VERD...
   OPENAI_API_KEY=sk-proj-gus9nOO...
   ELEVENLABS_API_KEY=sk_121cdba1fad...
   ```
6. **Save the file** and close Notepad

**Where to find API keys:** On your dev PC, open `C:\Users\Dad's PC\Desktop\Arcade Assistant Local\.env` and copy the keys.

---

### Step 5: Launch Arcade Assistant

1. **Double-click** "Arcade Assistant" shortcut on desktop
2. **Wait 10 seconds** for services to start
3. Two command windows will open:
   - `AA Backend [AA-0001]`
   - `AA Gateway [AA-0001]`
4. **Do NOT close these windows!** They must stay open.

---

### Step 6: Open the UI

1. **Double-click** "Open Arcade Assistant" shortcut on desktop
2. **OR** open your browser and go to: `http://localhost:8787`
3. You should see the Arcade Assistant interface

---

### Step 7: Test the Installation

1. **Click on "LaunchBox LoRa"** panel
2. **Type a message:** "Hey LoRa, show me some arcade games"
3. **Verify LoRa responds** with game suggestions
4. **If LoRa works:** Installation successful! ✅
5. **If errors appear:** See Troubleshooting section below

---

## Troubleshooting

### Problem: "Services don't start"

**Symptoms:**
- Desktop shortcut does nothing
- Command windows open and close immediately
- Error about missing .env file

**Solutions:**
1. Right-click "Arcade Assistant" shortcut → "Run as Administrator"
2. Verify `.env` file exists in `C:\ArcadeAssistant\`
3. Check that Node.js and Python are installed (`node --version`, `python --version`)

---

### Problem: "A: drive not accessible"

**Symptoms:**
- Warning about A: drive during startup
- LoRa can't find any games
- LaunchBox errors

**Solutions:**
1. Verify A: drive is connected and has a drive letter
2. Open File Explorer → Check if `A:\LaunchBox` exists
3. If drive letter is different, edit `.env` and change `AA_DRIVE_ROOT=A:\` to correct letter

---

### Problem: "AI doesn't respond"

**Symptoms:**
- LoRa, Dewey, or other AI characters don't respond
- Error about API keys in console
- "Unauthorized" or "Invalid API key" messages

**Solutions:**
1. Open `C:\ArcadeAssistant\.env` in Notepad
2. Verify API keys are filled in (not blank)
3. Verify API keys are correct (copy again from dev PC)
4. Restart services (close command windows, launch again)

---

### Problem: "Port already in use"

**Symptoms:**
- Error: "Port 8787 already in use"
- Error: "Port 8000 already in use"
- Services fail to start

**Solutions:**
1. Close any old instances of Arcade Assistant
2. Open Task Manager → End any `node.exe` or `python.exe` processes
3. Restart computer
4. Launch Arcade Assistant again

---

### Problem: "Browser shows 404 or connection refused"

**Symptoms:**
- `http://localhost:8787` doesn't load
- Browser says "Can't reach this page"
- "Connection refused" error

**Solutions:**
1. Verify both command windows (Backend + Gateway) are still open
2. Wait 30 seconds for services to fully start
3. Check gateway window for errors
4. Try refreshing the browser (F5)

---

## Post-Installation

### Daily Use

**To Start Arcade Assistant:**
1. Double-click "Arcade Assistant" on desktop
2. Wait 10 seconds
3. Double-click "Open Arcade Assistant"

**To Stop Arcade Assistant:**
1. Close the two command windows (Backend + Gateway)
2. Close the browser tab

### Updating Arcade Assistant

When a new version is released:
1. Close all Arcade Assistant windows
2. Copy new files from USB drive to `C:\ArcadeAssistant\`
3. **Do NOT overwrite `.env` file** (keep your API keys)
4. Re-run `install-cabinet.bat` if instructed
5. Launch Arcade Assistant normally

### Serial Number Registry

Keep track of which cabinet has which serial:

| Serial  | Location           | Install Date | Status |
|---------|--------------------|--------------|--------|
| AA-0001 | Basement Cabinet 1 | 2025-12-01   | Active |
| AA-0002 | Basement Cabinet 2 | 2025-12-01   | Active |

---

## Support

For additional help, see:
- **CABINET_TROUBLESHOOTING.md** - Detailed troubleshooting guide
- **BASEMENT_DEPLOYMENT_PLAN.md** - Technical architecture details
- **Backend logs:** `C:\ArcadeAssistant\backend.log`
- **Gateway logs:** `C:\ArcadeAssistant\gateway.log`
- **Installation log:** `C:\ArcadeAssistant\SERIAL_REGISTRY.log`

---

## Success Checklist

Installation is complete when:

- [ ] Desktop has "Arcade Assistant" and "Open Arcade Assistant" shortcuts
- [ ] Double-clicking "Arcade Assistant" opens two command windows
- [ ] Browser opens to `http://localhost:8787` and shows UI
- [ ] LoRa responds to messages about games
- [ ] Serial number appears in command window titles
- [ ] No errors in backend or gateway windows

**If all boxes are checked: Installation successful!** ✅
