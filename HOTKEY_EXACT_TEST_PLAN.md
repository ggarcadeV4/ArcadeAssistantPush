# Hotkey System - EXACT TEST PLAN
**DO NOT DEVIATE FROM THESE STEPS**

---

## PRE-TEST CHECKLIST

### ✅ Verify Services Running:

**Step 1: Check Backend**
```bash
curl http://localhost:8000/api/hotkey/health
```
**EXPECTED OUTPUT:**
```json
{"service":"hotkey","status":"active","hotkey":"A","ws_clients":1,"feature_enabled":true}
```
**IF FAILS:** Backend not running - see TROUBLESHOOTING section

**Step 2: Check Gateway**
```bash
curl http://localhost:8787/api/health
```
**EXPECTED OUTPUT:**
```json
{"status":"healthy","timestamp":"...","fastapi":"http://127.0.0.1:8000"}
```
**IF FAILS:** Gateway not running - see TROUBLESHOOTING section

---

## TEST SEQUENCE A: Backend Keypress Detection

**Purpose:** Verify backend Python keyboard library can detect A key

### Step A1: Open Backend Logs
1. Open new terminal/command prompt
2. Run command to tail backend output:
```bash
# On Windows PowerShell:
Get-Content "C:\Users\Dad's PC\Desktop\Arcade Assistant Local\backend.log" -Wait -Tail 50

# OR watch the running process output in Claude Code's terminal
```

### Step A2: Press A Key
1. **With backend logs visible**, press the **A** key **3 times**
2. **WAIT 1 second between each press**

### Step A3: Expected Backend Log Output
**YOU MUST SEE THIS EXACT TEXT:**
```
[Hotkey] A pressed – triggering callbacks
[Hotkey WS] Broadcasting event to 1 client(s)
[Hotkey] A pressed – triggering callbacks
[Hotkey WS] Broadcasting event to 1 client(s)
[Hotkey] A pressed – triggering callbacks
[Hotkey WS] Broadcasting event to 1 client(s)
```

**IF YOU SEE THIS:** ✅ Backend detection WORKS → Proceed to TEST B
**IF YOU DON'T SEE THIS:** ❌ Backend detection FAILS → Go to TROUBLESHOOTING A

---

## TEST SEQUENCE B: Gateway Event Forwarding

**Purpose:** Verify gateway receives events from backend and forwards them

### Step B1: Open Gateway Logs
1. Open new terminal/command prompt
2. Run command to tail gateway output:
```bash
# On Windows PowerShell:
Get-Content "C:\Users\Dad's PC\Desktop\Arcade Assistant Local\gateway.log" -Wait -Tail 50

# OR watch the running process output in Claude Code's terminal
```

### Step B2: Press A Key
1. **With gateway logs visible**, press the **A** key **3 times**
2. **WAIT 1 second between each press**

### Step B3: Expected Gateway Log Output
**YOU MUST SEE THIS EXACT TEXT:**
```
[HotkeyBridge] A pressed at 2025-12-01T17:XX:XX.XXXZ
[HotkeyBridge] Forwarded event to 1 frontend client(s)
[HotkeyBridge] A pressed at 2025-12-01T17:XX:XX.XXXZ
[HotkeyBridge] Forwarded event to 1 frontend client(s)
[HotkeyBridge] A pressed at 2025-12-01T17:XX:XX.XXXZ
[HotkeyBridge] Forwarded event to 1 frontend client(s)
```

**IF YOU SEE THIS:** ✅ Gateway forwarding WORKS → Proceed to TEST C
**IF YOU DON'T SEE THIS:** ❌ Gateway forwarding FAILS → Go to TROUBLESHOOTING B

---

## TEST SEQUENCE C: Frontend WebSocket Connection

**Purpose:** Verify browser can connect to gateway WebSocket

### Step C1: Open Test Page
1. Open **Google Chrome** or **Edge** browser
2. Navigate to this EXACT URL:
```
file:///C:/Users/Dad's%20PC/Desktop/Arcade%20Assistant%20Local/test_hotkey.html
```
3. Press **F12** to open Developer Tools
4. Click **Console** tab

### Step C2: Expected Console Output (On Page Load)
**YOU MUST SEE THIS EXACT TEXT:**
```
Initializing WebSocket connection...
✅ WS OPEN - Connection established!
```

**IF YOU SEE THIS:** ✅ WebSocket connection WORKS → Proceed to TEST D
**IF YOU SEE ERROR:** ❌ WebSocket connection FAILS → Go to TROUBLESHOOTING C

---

## TEST SEQUENCE D: End-to-End Event Flow

**Purpose:** Verify A key press reaches the browser

### Step D1: With Test Page Still Open
1. **Browser Developer Tools Console tab still visible**
2. Press the **A** key **3 times** (1 second apart)

### Step D2: Expected Console Output (Per Keypress)
**FOR EACH A KEY PRESS, YOU MUST SEE:**
```
📨 WS MSG: {"type":"hotkey_pressed","key":"A","timestamp":"2025-12-01T17:XX:XX.XXXXXX"}
🎯 HOTKEY DETECTED: Key "A" pressed!
⌨️ Local A key detected in browser
```

**CRITICAL:** You should see **3 sets** of these 3 messages (9 total lines)

**IF YOU SEE ALL 9 LINES:** ✅ End-to-end flow WORKS → Proceed to TEST E
**IF YOU SEE FEWER:** ❌ Event flow FAILS → Go to TROUBLESHOOTING D

---

## TEST SEQUENCE E: HotkeyOverlay Component

**Purpose:** Verify overlay appears in main application

### Step E1: Open Main Application
1. Open **new browser tab** (keep test page open for comparison)
2. Navigate to this EXACT URL:
```
http://localhost:8787
```
3. Wait for page to fully load (see main AA UI)
4. Press **F12** for Developer Tools → **Console** tab

### Step E2: Verify WebSocket Connection
**IN CONSOLE, YOU MUST SEE:**
```
[hotkeyClient] Connecting to: ws://localhost:8787/ws/hotkey
[hotkeyClient] Connected
```

**IF YOU DON'T SEE THIS:** Component not connecting → Go to TROUBLESHOOTING E

### Step E3: Press A Key
1. **With main app visible**, press the **A** key **ONCE**
2. **LOOK AT THE SCREEN** (not console)

### Step E4: Expected Visual Result
**YOU MUST SEE:**
- Fullscreen dark overlay appears instantly
- "Dewey Overlay" title at top
- Dewey panel content inside
- "Close" button at top-right
- "Press A again or ESC to close" hint

**IF YOU SEE THIS:** ✅ **COMPLETE SUCCESS** → Feature works!
**IF YOU DON'T SEE THIS:** ❌ Overlay render FAILS → Go to TROUBLESHOOTING E

### Step E5: Close Overlay
1. Press **A** key again OR press **ESC** OR click **Close** button
2. Overlay should disappear

### Step E6: Test Toggle
1. Press **A** to open overlay
2. Press **A** to close overlay
3. Press **A** to open overlay
4. Press **ESC** to close overlay

**ALL 4 ACTIONS MUST WORK**

---

## TROUBLESHOOTING A: Backend Detection Fails

**Symptom:** Backend logs don't show "[Hotkey] A pressed" when you press A

### Fix A1: Verify Backend Running with Admin
```bash
# Check if backend process is running:
curl http://localhost:8000/api/hotkey/health
```
**If 404 or connection refused:** Backend is not running

**SOLUTION:**
```bash
# Kill all old backend processes:
taskkill /F /IM python.exe

# Restart backend with Admin:
# Right-click Command Prompt → "Run as Administrator"
cd "C:\Users\Dad's PC\Desktop\Arcade Assistant Local"
python -m backend.app
```

### Fix A2: Verify Keyboard Library Installed
```bash
pip show keyboard
```
**If "not found":**
```bash
pip install keyboard
```

### Fix A3: Verify Feature Flag
```bash
# Check .env file has this exact line:
findstr "V2_HOTKEY_LAUNCHER" "C:\Users\Dad's PC\Desktop\Arcade Assistant Local\.env"
```
**MUST OUTPUT:**
```
V2_HOTKEY_LAUNCHER=true
```
**If missing or "false":** Edit .env, set to "true", restart backend

### Fix A4: Test Keyboard Library Directly
Create file `test_keyboard.py`:
```python
import keyboard
print("Press A key (Press ESC to quit)...")
keyboard.wait('a')
print("✅ A key detected!")
keyboard.wait('esc')
```
Run with Admin:
```bash
python test_keyboard.py
```
**If this doesn't detect A:** Your keyboard library installation is broken

---

## TROUBLESHOOTING B: Gateway Forwarding Fails

**Symptom:** Backend logs show "[Hotkey] A pressed" but gateway logs don't show "[HotkeyBridge] A pressed"

### Fix B1: Verify Gateway Connected to Backend
```bash
curl http://localhost:8000/api/hotkey/health
```
**Check `ws_clients` field:**
```json
{"ws_clients": 1}  ← Must be 1 or more
```
**If 0:** Gateway not connected

**SOLUTION:**
```bash
# Kill all old gateway processes:
taskkill /F /IM node.exe

# Restart gateway:
cd "C:\Users\Dad's PC\Desktop\Arcade Assistant Local"
node gateway/server.js
```

**Wait for log line:**
```
[HotkeyBridge] Connected to backend hotkey service
```

### Fix B2: Check Gateway Logs for Errors
Look for:
```
[HotkeyBridge] Error parsing backend message
[HotkeyBridge] Backend connection error
```

**If you see "Error parsing backend message":**
- The BUG #3 fix didn't apply correctly
- Verify `gateway/ws/hotkey.js` lines 96-102 have the pong check
- Restart gateway after verifying code

### Fix B3: Verify Backend Port in .env
```bash
findstr "FASTAPI_URL" "C:\Users\Dad's PC\Desktop\Arcade Assistant Local\.env"
```
**MUST OUTPUT:**
```
FASTAPI_URL=http://127.0.0.1:8000
```
**NOT 8888!** If wrong, edit .env, restart gateway

---

## TROUBLESHOOTING C: WebSocket Connection Fails

**Symptom:** Test page shows "WS ERROR" or "WS CLOSE" instead of "WS OPEN"

### Fix C1: Verify Gateway Running
```bash
curl http://localhost:8787/api/health
```
**If connection refused:** Gateway not running → See Fix B1

### Fix C2: Check Browser Console Error Details
In console, you might see:
```
WebSocket connection to 'ws://localhost:8787/ws/hotkey' failed: Error: ...
```

**If "ERR_CONNECTION_REFUSED":**
- Gateway not running → See Fix B1

**If "404 Not Found":**
- Gateway doesn't have /ws/hotkey route registered
- Verify `gateway/server.js` has this line:
  ```javascript
  initializeHotkeyBridge(wss);
  ```
- Restart gateway

### Fix C3: Verify WebSocket Path in Frontend
Check `frontend/src/services/hotkeyClient.js` line 12:
```javascript
this._url = `${scheme}://${host}/ws/hotkey`  // Must be /ws/hotkey
```
**If different:** Fix it, rebuild frontend:
```bash
cd frontend
npm run build
```

---

## TROUBLESHOOTING D: Events Don't Reach Browser

**Symptom:**
- Test page shows "WS OPEN" ✅
- Backend logs show "[Hotkey] A pressed" ✅
- Gateway logs show "[HotkeyBridge] A pressed" ✅
- BUT browser console doesn't show "📨 WS MSG"

### Fix D1: Check Gateway Forwarding Count
Gateway log should say:
```
[HotkeyBridge] Forwarded event to X frontend client(s)
```

**If X = 0:** No frontend clients connected
**SOLUTION:** Refresh test page (F5), check for "WS OPEN" again

**If X ≥ 1:** Gateway is forwarding, but browser not receiving

### Fix D2: Check Browser WebSocket State
In browser console, type:
```javascript
window.testWS.readyState
```
**Expected:** `1` (OPEN)
**If 0 (CONNECTING):** Still connecting, wait
**If 2 (CLOSING) or 3 (CLOSED):** Connection dropped, refresh page

### Fix D3: Manual WebSocket Test
In browser console, type:
```javascript
window.testWS.onmessage = (e) => {
  console.log("🔔 MANUAL TEST:", e.data);
};
```
Then press A key.
**If you now see "🔔 MANUAL TEST":** Original event listener wasn't working
**If still nothing:** WebSocket is broken

---

## TROUBLESHOOTING E: Overlay Doesn't Appear

**Symptom:**
- Test page receives events ✅
- Main app WebSocket connected ✅
- Main app console shows messages ✅
- BUT no visual overlay appears

### Fix E1: Verify HotkeyOverlay Component Mounted
In browser console:
```javascript
document.querySelector('.hotkey-overlay-backdrop')
```
**Expected when overlay CLOSED:** `null`
**Expected when overlay OPEN:** `<div class="hotkey-overlay-backdrop">...</div>`

**If always `null`:** Component not mounted in App.jsx

### Fix E2: Check React Component State
Install React DevTools extension, then:
1. Open React DevTools tab
2. Find "HotkeyOverlay" component
3. Check `open` state

**When you press A:**
- `open` should toggle `false` → `true` → `false`

**If `open` never changes:** Event not reaching component

### Fix E3: Check CSS Loading
In browser console:
```javascript
getComputedStyle(document.querySelector('.hotkey-overlay-backdrop')).display
```
**Expected when overlay should be visible:** NOT "none"
**If "none":** CSS is hiding it

**SOLUTION:** Verify `frontend/src/components/HotkeyOverlay.css` exists and is imported

### Fix E4: Check for JavaScript Errors
Look in console for red error messages when pressing A.
Common errors:
```
TypeError: Cannot read property 'xyz' of undefined
ReferenceError: DeweyPanel is not defined
```
These indicate code bugs in the component.

---

## SUCCESS CRITERIA CHECKLIST

**YOU MUST CHECK ALL BOXES:**

### Backend Layer:
- [ ] `curl http://localhost:8000/api/hotkey/health` returns `"status":"active"`
- [ ] Backend logs show "[Hotkey] A pressed" when A key pressed
- [ ] Backend logs show "[Hotkey WS] Broadcasting event to 1 client(s)"

### Gateway Layer:
- [ ] `curl http://localhost:8787/api/health` returns `"status":"healthy"`
- [ ] Gateway startup logs show "[HotkeyBridge] Connected to backend hotkey service"
- [ ] Gateway logs show "[HotkeyBridge] A pressed at [timestamp]" when A pressed
- [ ] Gateway logs show "[HotkeyBridge] Forwarded event to X frontend client(s)"
- [ ] Gateway logs have **ZERO** "Error parsing backend message" errors

### Test Page (test_hotkey.html):
- [ ] Page loads without JavaScript errors
- [ ] Console shows "✅ WS OPEN - Connection established!" on page load
- [ ] Console shows "📨 WS MSG: {..." when A key pressed
- [ ] Console shows "🎯 HOTKEY DETECTED: Key "A" pressed!" when A pressed
- [ ] Each A key press produces exactly 3 console messages

### Main Application (http://localhost:8787):
- [ ] Page loads without JavaScript errors
- [ ] Console shows "[hotkeyClient] Connected"
- [ ] Pressing A makes overlay appear on screen
- [ ] Overlay shows "Dewey Overlay" title
- [ ] Overlay shows Close button
- [ ] Pressing A again makes overlay disappear
- [ ] Pressing ESC makes overlay disappear
- [ ] Can toggle overlay open/close repeatedly

---

## FINAL VERIFICATION SCRIPT

**Copy and paste this entire block into PowerShell:**

```powershell
Write-Host "=== HOTKEY SYSTEM VERIFICATION ===" -ForegroundColor Cyan
Write-Host ""

Write-Host "1. Testing Backend..." -ForegroundColor Yellow
$backend = Invoke-RestMethod -Uri "http://localhost:8000/api/hotkey/health" -ErrorAction SilentlyContinue
if ($backend.status -eq "active") {
    Write-Host "   ✅ Backend: ACTIVE" -ForegroundColor Green
    Write-Host "   ✅ Hotkey: $($backend.hotkey)" -ForegroundColor Green
    Write-Host "   ✅ WS Clients: $($backend.ws_clients)" -ForegroundColor Green
} else {
    Write-Host "   ❌ Backend: FAILED" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "2. Testing Gateway..." -ForegroundColor Yellow
$gateway = Invoke-RestMethod -Uri "http://localhost:8787/api/health" -ErrorAction SilentlyContinue
if ($gateway.status -eq "healthy") {
    Write-Host "   ✅ Gateway: HEALTHY" -ForegroundColor Green
} else {
    Write-Host "   ❌ Gateway: FAILED" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "3. Checking Environment..." -ForegroundColor Yellow
$env_content = Get-Content ".env" | Select-String "V2_HOTKEY_LAUNCHER|FASTAPI_URL"
foreach ($line in $env_content) {
    Write-Host "   📋 $line" -ForegroundColor White
}

Write-Host ""
Write-Host "=== READY FOR MANUAL TESTING ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "NEXT STEPS:" -ForegroundColor Yellow
Write-Host "1. Open test_hotkey.html in browser"
Write-Host "2. Press A key 3 times"
Write-Host "3. Check browser console for messages"
Write-Host ""
```

**Expected output:**
```
=== HOTKEY SYSTEM VERIFICATION ===

1. Testing Backend...
   ✅ Backend: ACTIVE
   ✅ Hotkey: A
   ✅ WS Clients: 1

2. Testing Gateway...
   ✅ Gateway: HEALTHY

3. Checking Environment...
   📋 V2_HOTKEY_LAUNCHER=true
   📋 FASTAPI_URL=http://127.0.0.1:8000

=== READY FOR MANUAL TESTING ===

NEXT STEPS:
1. Open test_hotkey.html in browser
2. Press A key 3 times
3. Check browser console for messages
```

---

## WHAT TO REPORT BACK

**For each test sequence, report EXACT result:**

### Test A (Backend Detection):
```
Backend logs showed:
[PASTE EXACT LOG OUTPUT HERE]

Result: ✅ PASS or ❌ FAIL
```

### Test B (Gateway Forwarding):
```
Gateway logs showed:
[PASTE EXACT LOG OUTPUT HERE]

Result: ✅ PASS or ❌ FAIL
```

### Test C (WebSocket Connection):
```
Browser console showed:
[PASTE EXACT CONSOLE OUTPUT HERE]

Result: ✅ PASS or ❌ FAIL
```

### Test D (End-to-End Flow):
```
Browser console showed after pressing A 3 times:
[PASTE EXACT CONSOLE OUTPUT HERE]

Number of messages: [COUNT]
Result: ✅ PASS or ❌ FAIL
```

### Test E (Overlay Visual):
```
What I saw on screen:
[DESCRIBE EXACTLY WHAT APPEARED]

Result: ✅ PASS or ❌ FAIL
```

---

## DO NOT PROCEED UNLESS:

1. ✅ You have run the verification PowerShell script
2. ✅ All 3 checks passed (Backend, Gateway, Environment)
3. ✅ You have test_hotkey.html open in browser
4. ✅ You see "WS OPEN" in console
5. ✅ You are ready to press A key and report exact results

**IF ANY OF ABOVE ARE ❌, GO TO TROUBLESHOOTING SECTION FIRST**
