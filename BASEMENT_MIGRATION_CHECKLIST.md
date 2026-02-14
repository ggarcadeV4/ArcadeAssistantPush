# Basement Migration Checklist - What's Entailed?

## QUESTION: What exactly is needed to move Arcade Assistant from this dev PC to the basement arcade cabinet?

---

## Physical Hardware Questions:

1. **What's the basement arcade setup?**
   - Do you have TWO arcade cabinets in the basement?
   - Does each cabinet have:
     - Monitor 1 (TV for games)?
     - Monitor 2 (Marquee display for AA UI)?
   - Are both cabinets running Windows?

2. **A: Drive - Does it move or get duplicated?**
   - Is the A: drive (LaunchBox + ROMs + Emulators) on THIS PC?
   - Or is A: drive already in the basement on a different machine?
   - Do we need to:
     - Copy the entire A: drive to basement PC?
     - Map to a network A: drive?
     - Or is A: already there?

3. **What PC hardware is in the basement cabinet(s)?**
   - Windows version?
   - RAM/CPU specs?
   - Do they have Node.js/Python already installed?

---

## Software Installation Questions:

1. **Does the basement PC need a fresh install of:**
   - Node.js (v18+)?
   - Python 3.10+?
   - Git?
   - npm packages (run `npm install:all`)?
   - Python packages (run `pip install -r backend/requirements.txt`)?

2. **Environment Configuration:**
   - Do we copy the `.env` file as-is?
   - Or does basement PC need different settings:
     - Different `AA_DRIVE_ROOT` path?
     - Different `FASTAPI_URL`?
     - Same API keys (Claude, OpenAI, ElevenLabs)?

3. **Service Setup:**
   - Does basement PC need AA to auto-start on boot?
   - Run as Windows Service?
   - Or just manual launch via `npm run dev`?

---

## Network & Connectivity Questions:

1. **Is basement PC connected to internet?**
   - Required for AI features (Claude, OpenAI, ElevenLabs)
   - Required for Supabase cloud sync

2. **Localhost vs Network:**
   - Will AA UI be accessed:
     - On the same PC (localhost:8787)?
     - From a different PC on local network?
   - Do we need to change from `localhost` to actual IP address?

3. **LaunchBox Plugin:**
   - Is LaunchBox running on the SAME PC as AA backend?
   - Or a different PC?
   - Plugin listens on port 10099 - does that need to change?

---

## Data Migration Questions:

1. **What data needs to transfer?**
   - User profiles (`backend/profiles/*.json`)?
   - Configuration files (`configs/`)?
   - State data (`state/`)?
   - Logs (`logs/`)?
   - Backups (`backups/`)?

2. **LaunchBox Integration:**
   - Does basement LaunchBox already have games configured?
   - Or do we need to import your current LaunchBox setup?
   - Are ROM paths the same on basement PC?

3. **Cabinet-Specific Settings:**
   - Controller mappings - same or different?
   - LED Blinky configs - same or different?
   - Light gun calibration - needs redoing?

---

## Testing & Validation Questions:

1. **What needs to work on Day 1?**
   - LaunchBox game launching?
   - LoRa AI chat?
   - Voice commands?
   - Controller detection?
   - LED lighting?
   - Light guns?

2. **What can wait?**
   - Cloud sync features?
   - ScoreKeeper tournament mode?
   - Advanced AI features?

---

## Deployment Method Questions:

1. **How do we physically move the code?**
   - USB drive copy?
   - Git clone from GitHub?
   - Network file share?
   - Cloud storage (Dropbox, OneDrive)?

2. **Version Control:**
   - Should we commit current state to Git first?
   - Create a "basement-ready" release branch?
   - Tag a version (v1.0-basement)?

3. **Rollback Plan:**
   - If something breaks in basement, can we roll back?
   - Do we keep a backup of working state on THIS PC?

---

## My Assumptions (PLEASE CONFIRM/CORRECT):

### What I THINK the setup is:
1. **Two arcade cabinets in basement**, each with:
   - Main TV (for games)
   - Marquee monitor (for AA UI)
   - Windows PC inside
   - Controllers, light guns, LED strips

2. **A: drive is a network share** accessible from both cabinets
   - Contains LaunchBox installation
   - Contains all ROMs (~14k games)
   - Contains all emulators

3. **Each cabinet needs its own AA installation:**
   - Cabinet 1: Run backend + gateway + frontend on its own PC
   - Cabinet 2: Same, independent installation
   - Both access the same A: drive

4. **Migration = Copy this folder** to each basement PC:
   - Copy entire `Arcade Assistant Local` folder
   - Run `npm install:all`
   - Copy `.env` file with API keys
   - Start services via `npm run dev`

### What I THINK I need to prepare:
1. **Installation script** (`install.bat` or `install.ps1`)
   - Checks for Node.js/Python
   - Runs `npm install:all`
   - Prompts for API keys if `.env` missing
   - Creates desktop shortcuts to start AA

2. **Cabinet-specific .env templates:**
   - `.env.cabinet1` with correct paths
   - `.env.cabinet2` with correct paths

3. **Startup script** (`start-cabinet.bat`)
   - Starts backend
   - Starts gateway
   - Opens browser to localhost:8787 on Monitor 2

4. **README for basement PC** with:
   - Prerequisites checklist
   - Installation steps
   - Troubleshooting common issues
   - How to update AA later

---

## CRITICAL QUESTIONS I NEED ANSWERED:

### **Question 1: Physical Setup**
Is A: drive on THIS PC, or already in the basement?

### **Question 2: Number of Installations**
Do you need AA installed on:
- [ ] One basement PC only?
- [ ] Two separate basement PCs (one per cabinet)?
- [ ] This dev PC PLUS basement PC(s)?

### **Question 3: A: Drive Access**
How does basement PC access A: drive:
- [ ] Local drive on basement PC
- [ ] Network share from another PC
- [ ] External USB drive plugged into basement PC
- [ ] Something else?

### **Question 4: Deployment Method**
How should I package this for you:
- [ ] Create a ZIP file you copy to basement PC
- [ ] Create Git repo you clone on basement PC
- [ ] Create installer script that downloads everything
- [ ] Just give you manual instructions

### **Question 5: Auto-Start**
When basement PC boots, should AA:
- [ ] Auto-start and show on Monitor 2
- [ ] Require manual launch
- [ ] Launch with Windows but stay hidden until F9 pressed

### **Question 6: Internet Requirement**
Basement PC has internet for AI features?
- [ ] Yes, wired ethernet
- [ ] Yes, WiFi
- [ ] No, offline mode only

---

## What I Can Start Preparing NOW:

While you answer those questions, I can:

1. **Create installation script** (works for any PC)
2. **Document environment setup** (Node.js, Python versions, etc.)
3. **Create troubleshooting guide** (common issues + fixes)
4. **List all file dependencies** (what MUST be copied vs what's auto-generated)
5. **Test portability** (does this code work if moved to `D:\` instead of `C:\Users\Dad's PC\Desktop\`?)

---

## My Recommendation:

**Before you move anything to basement, let's create a "portable release package" that includes:**

1. Installation checklist
2. Automated setup script
3. Environment template
4. Startup shortcuts
5. Troubleshooting guide

**This way, whether it's basement Cabinet 1, Cabinet 2, or a future Cabinet 3, the deployment process is identical and foolproof.**

---

## ANSWER THESE 6 QUESTIONS AND I'LL BUILD THE MIGRATION PACKAGE:

1. **A: drive location?** (this PC / basement PC / network share)
2. **How many AA installations?** (1 PC / 2 PCs / more)
3. **A: drive access method?** (local / network / USB)
4. **Deployment preference?** (ZIP / Git / installer / manual)
5. **Auto-start behavior?** (yes / no / hidden)
6. **Internet available?** (yes ethernet / yes wifi / no)

**Once I have these answers, I'll create Feature 3: Cabinet Duplication Documentation with EXACT steps for your specific setup.**
