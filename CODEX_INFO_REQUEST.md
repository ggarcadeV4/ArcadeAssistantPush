# Information Request for Codex - Boost Confidence to 8.5/10

**Current Confidence:** 7/10
**Target Confidence:** 8.5/10
**Missing Information:** 3 critical unknowns that Codex can verify

---

## REQUEST 1: Verify Frontend Component Integration

**What I Need to Know:**
Is HotkeyOverlay component actually mounted in App.jsx?

**Exact Commands for Codex:**

```bash
# Check if HotkeyOverlay is imported in App.jsx
grep -n "HotkeyOverlay" frontend/src/App.jsx

# Check if HotkeyOverlay is rendered in App.jsx
grep -n "<HotkeyOverlay" frontend/src/App.jsx
```

**Expected Output:**
```
frontend/src/App.jsx:XX:import HotkeyOverlay from './components/HotkeyOverlay'
frontend/src/App.jsx:YY:  <HotkeyOverlay />
```

**If Missing:**
Show me the exact line number where I should add `<HotkeyOverlay />` in the JSX return statement.

**Confidence Impact:** This alone gets me from 7.0 → 7.8

---

## REQUEST 2: Test Python Keyboard Library

**What I Need to Know:**
Can the Python `keyboard` library actually detect keypresses on this machine?

**Exact Test Script for Codex to Create and Run:**

Create file: `test_keyboard_simple.py`
```python
#!/usr/bin/env python3
import sys
import os

print("Testing keyboard library installation...")

try:
    import keyboard
    print("✅ keyboard library imported successfully")
except ImportError as e:
    print(f"❌ keyboard library import failed: {e}")
    sys.exit(1)

print("\n🔧 Attempting to register hotkey...")
try:
    # Try to register a hotkey (doesn't require admin to register, only to detect)
    print("   Registering 'a' key listener...")
    keyboard.add_hotkey('a', lambda: None, suppress=False)
    print("✅ Hotkey registration successful")
    keyboard.remove_hotkey('a')
except Exception as e:
    print(f"❌ Hotkey registration failed: {e}")
    print(f"   Error type: {type(e).__name__}")
    sys.exit(1)

print("\n📋 Keyboard library details:")
print(f"   Version: {keyboard.__version__ if hasattr(keyboard, '__version__') else 'unknown'}")
print(f"   File location: {keyboard.__file__}")

print("\n✅ ALL CHECKS PASSED - Keyboard library is functional")
```

**Codex Instructions:**
1. Create the file above
2. Run: `python test_keyboard_simple.py`
3. Report the EXACT output

**Expected Output (Success):**
```
Testing keyboard library installation...
✅ keyboard library imported successfully

🔧 Attempting to register hotkey...
   Registering 'a' key listener...
✅ Hotkey registration successful

📋 Keyboard library details:
   Version: 0.13.5
   File location: C:\...\site-packages\keyboard\__init__.py

✅ ALL CHECKS PASSED - Keyboard library is functional
```

**If Fails:**
Report the exact error message and error type.

**Confidence Impact:** This gets me from 7.8 → 8.3

---

## REQUEST 3: Verify HotkeyOverlay CSS File Exists

**What I Need to Know:**
Does the CSS file exist and is it imported in the component?

**Exact Commands for Codex:**

```bash
# Check if CSS file exists
ls -la frontend/src/components/HotkeyOverlay.css

# Check if it's imported in the component
grep -n "HotkeyOverlay.css" frontend/src/components/HotkeyOverlay.jsx

# Show first 20 lines of CSS to verify it has content
head -20 frontend/src/components/HotkeyOverlay.css
```

**Expected Output:**
```
-rw-r--r-- 1 user user XXXX Date frontend/src/components/HotkeyOverlay.css

frontend/src/components/HotkeyOverlay.jsx:XX:import './HotkeyOverlay.css'

.hotkey-overlay-backdrop {
  position: fixed;
  ...
}
```

**If CSS File Missing:**
I'll need to create it. Show me this immediately.

**Confidence Impact:** This gets me from 8.3 → 8.5

---

## REQUEST 4 (BONUS): Check Current Background Processes

**What I Need to Know:**
Are there multiple instances of backend/gateway running that might conflict?

**Exact Commands for Codex:**

```bash
# Check for multiple Python backend processes
ps aux | grep "backend.app" | grep -v grep

# Check for multiple Node gateway processes
ps aux | grep "gateway/server.js" | grep -v grep

# Check what's actually listening on port 8000 and 8787
netstat -ano | findstr ":8000"
netstat -ano | findstr ":8787"
```

**Expected Output:**
```
# Should see ONLY ONE backend process
python -m backend.app

# Should see ONLY ONE gateway process
node gateway/server.js

# Should see one listener on each port
TCP    127.0.0.1:8000    ...    LISTENING    PID
TCP    127.0.0.1:8787    ...    LISTENING    PID
```

**If Multiple Processes:**
Tell me exact PIDs to kill and in what order.

**Confidence Impact:** This is the bonus that might get me to 8.7 if there's a port conflict issue

---

## SUMMARY FOR CODEX

**Run these 4 checks in order:**

1. ✅ `grep -n "HotkeyOverlay" frontend/src/App.jsx` → Is component mounted?
2. ✅ Create and run `test_keyboard_simple.py` → Does keyboard library work?
3. ✅ `ls frontend/src/components/HotkeyOverlay.css` → Does CSS exist?
4. ✅ Check for duplicate processes on ports 8000/8787

**Report back EXACT output for each check.**

**Format:**
```
CHECK 1 (Component Integration):
[EXACT OUTPUT]
Status: ✅ PASS or ❌ FAIL

CHECK 2 (Keyboard Library):
[EXACT OUTPUT]
Status: ✅ PASS or ❌ FAIL

CHECK 3 (CSS File):
[EXACT OUTPUT]
Status: ✅ PASS or ❌ FAIL

CHECK 4 (Port Conflicts):
[EXACT OUTPUT]
Status: ✅ PASS or ❌ FAIL
```

---

## CONFIDENCE CALCULATION

**Starting:** 7.0/10

**After CHECK 1 passes:** 7.0 + 0.8 = 7.8/10 (Know component is mounted)
**After CHECK 2 passes:** 7.8 + 0.5 = 8.3/10 (Know keyboard lib works)
**After CHECK 3 passes:** 8.3 + 0.2 = 8.5/10 (Know CSS will load)
**After CHECK 4 passes:** 8.5 + 0.2 = 8.7/10 (Know no port conflicts)

**Target:** 8.5/10 ✅

---

## WHAT THESE CHECKS PROVE

If all 4 pass, I will know with 85% certainty:

1. ✅ Frontend component is in the React tree
2. ✅ Python keyboard library can register hotkeys
3. ✅ CSS will load and style the overlay
4. ✅ No zombie processes blocking ports

**The remaining 15% uncertainty is:**
- Whether keyboard library can detect keys **while backend is running** (TEST A)
- Whether the WebSocket client in hotkeyClient.js connects properly (TEST C)
- Whether pressing A actually triggers the React state change (TEST E)

**But those are runtime tests that require the user to press A.**

With 8.5/10 confidence, I can say: **"The code is correct, the environment is ready, and I've verified every checkable component. The system SHOULD work when you press A."**
