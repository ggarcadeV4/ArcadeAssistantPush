# Hotkey System - Consolidated Audit & Action Plan
**Date:** 2025-12-01
**Status:** 🔴 **3 BUGS IDENTIFIED** - Backend/Gateway working but message protocol broken

---

## Combined Findings - Both Agents

### ✅ What's Working:
1. **Backend hotkey detection**: Service active, keyboard listener running
2. **Backend WebSocket**: Accepts gateway connection (1 client connected)
3. **Gateway bridge connection**: Successfully connects to `ws://127.0.0.1:8000/api/hotkey/ws`
4. **Environment config**: V2_HOTKEY_LAUNCHER=true now reads correctly in both services

### 🐛 Bugs Identified:

#### **BUG #1: Gateway Feature Flag Timing** (FIXED)
- **Agent:** Implementation Agent
- **Status:** ✅ FIXED
- **Problem:** Gateway checked `V2_HOTKEY_LAUNCHER` in constructor before dotenv loaded
- **Fix Applied:** Moved check to `initialize()` method
- **File:** [gateway/ws/hotkey.js:19-25](gateway/ws/hotkey.js#L19-L25)

#### **BUG #2: Backend Port Mismatch** (FIXED)
- **Agent:** Implementation Agent
- **Status:** ✅ FIXED
- **Problem:** .env had port 8888, backend runs on 8000
- **Fix Applied:** Updated FASTAPI_URL to http://127.0.0.1:8000
- **File:** [.env:3](.env#L3)

#### **BUG #3: JSON Parse Error on "pong" Messages** (NEW - NEEDS FIX)
- **Agent:** Codex (discovered via stderr)
- **Status:** 🔴 **ACTIVE BUG** - Repeating every few seconds
- **Error:** `SyntaxError: Unexpected token 'p', "pong" is not valid JSON`
- **Root Cause:**
  - Backend sends plain text `"pong"` (hotkey.py:34)
  - Gateway tries to `JSON.parse()` every message (hotkey.js:98)
  - Ping/pong should not be JSON parsed
- **Impact:** Error spam in logs, but doesn't break actual hotkey events
- **Files:**
  - Backend: [backend/routers/hotkey.py:33-34](backend/routers/hotkey.py#L33-L34)
  - Gateway: [gateway/ws/hotkey.js:96-104](gateway/ws/hotkey.js#L96-L104)

---

## Root Cause Analysis - BUG #3

### Backend Code (hotkey.py):
```python
# Line 33-34: Sends plain text "pong"
data = await websocket.receive_text()
if data == "ping":
    await websocket.send_text("pong")  # ❌ Not JSON
```

### Gateway Code (hotkey.js):
```javascript
// Line 96-98: Tries to parse everything as JSON
this.backendConnection.on('message', (data) => {
  try {
    const event = JSON.parse(data);  // ❌ Crashes on "pong"
```

### Actual Error:
```
[HotkeyBridge] Error parsing backend message: SyntaxError: Unexpected token 'p', "pong" is not valid JSON
```

---

## Action Plan - Three Options

### **OPTION A: Fix Gateway to Handle Plain Text** (RECOMMENDED)
**Approach:** Check if message is JSON before parsing

**Changes Required:**
```javascript
// gateway/ws/hotkey.js line 96-105
this.backendConnection.on('message', (data) => {
  const message = data.toString();

  // Handle ping/pong protocol
  if (message === 'pong') {
    return; // Silently ignore pong responses
  }

  try {
    const event = JSON.parse(message);

    // Log hotkey event
    if (event.type === 'hotkey_pressed') {
      console.log(`[HotkeyBridge] ${event.key} pressed at ${event.timestamp}`);
    }

    // Forward to frontend clients
    this.broadcastToFrontend(event);
  } catch (e) {
    console.error('[HotkeyBridge] Error parsing backend message:', e.message);
  }
});
```

**Pros:**
- Minimal change (1 file, 3 lines added)
- Preserves existing backend ping/pong protocol
- Consistent with other WebSocket bridges in codebase

**Cons:** None

---

### **OPTION B: Fix Backend to Send JSON "pong"**
**Approach:** Make ping/pong use JSON format

**Changes Required:**
```python
# backend/routers/hotkey.py line 33-34
data = await websocket.receive_text()
if data == "ping" or (data.startswith('{') and '"type":"ping"' in data):
    await websocket.send_text('{"type":"pong"}')
```

**Pros:**
- Consistent JSON protocol for all messages

**Cons:**
- Changes backend contract (may affect other clients)
- Less efficient (JSON overhead for heartbeat)
- Inconsistent with FastAPI WebSocket patterns

---

### **OPTION C: Remove Ping/Pong Entirely**
**Approach:** Let WebSocket library handle keep-alive

**Changes Required:**
1. Remove ping interval in gateway (hotkey.js:87-93)
2. Remove ping/pong handling in backend (hotkey.py:33-34)

**Pros:**
- Simplest code
- WebSocket protocol has built-in ping frames

**Cons:**
- May lose connection detection
- Inconsistent with other WebSocket handlers (LED, Gunner have pings)

---

## Recommended Implementation Plan

### **IMMEDIATE FIX (Option A):**
1. Modify [gateway/ws/hotkey.js:96-105](gateway/ws/hotkey.js#L96-L105)
2. Add check for "pong" before JSON.parse()
3. Restart gateway
4. Verify error logs stop

### **TESTING SEQUENCE:**
1. **Verify fix worked:**
   - Gateway logs should NOT show JSON parse errors
   - Backend still shows 1 connected client

2. **Test hotkey detection:**
   - Open test page: `test_hotkey.html`
   - Press A key 3 times
   - Should see:
     - Backend log: `[Hotkey] A pressed – triggering callbacks`
     - Gateway log: `[HotkeyBridge] A pressed at [timestamp]`
     - Browser page: `📨 WS MSG: {"type":"hotkey_pressed"...}`

3. **Test main app:**
   - Navigate to `http://localhost:8787`
   - Press A key
   - HotkeyOverlay should appear with Dewey panel

---

## Technical Details - Message Protocol

### Backend Sends TWO Types of Messages:

**Type 1: Ping/Pong (Keep-Alive)**
- Format: Plain text strings
- Client sends: `"ping"`
- Backend responds: `"pong"`
- Purpose: Detect disconnections
- Frequency: Every 30 seconds (gateway sends ping)

**Type 2: Hotkey Events**
- Format: JSON object
- Structure:
  ```json
  {
    "type": "hotkey_pressed",
    "key": "A",
    "timestamp": "2025-12-01T16:54:32.123456"
  }
  ```
- Triggered by: Physical A key press
- Purpose: Notify frontend to show overlay

### Gateway Must Handle BOTH:
- Plain text "pong" → ignore silently
- JSON hotkey events → parse and forward to frontend

---

## Comparison with Other WebSocket Bridges

### LED WebSocket Bridge (gateway/ws/led.js):
- **Does NOT** have ping/pong protocol
- Relies on WebSocket native keep-alive
- Only forwards JSON events from backend

### Gunner WebSocket Bridge (gateway/ws/gunner.js):
- **Does NOT** have ping/pong protocol
- Simpler message handling
- Only forwards JSON events

### Audio WebSocket Bridge (gateway/ws/audio.js):
- **Has** ping/pong protocol
- **Correctly handles** plain text "pong"
- Good reference implementation

**Recommendation:** Follow audio.js pattern for ping/pong handling.

---

## Expected Log Output (After Fix)

### Backend Startup:
```
DEBUG: V2_HOTKEY_LAUNCHER = true
[Hotkey] Starting hotkey service...
[Hotkey] Service started successfully!
INFO: WebSocket /api/hotkey/ws [accepted]
```

### Gateway Startup:
```
[HotkeyBridge] Connecting to backend: ws://127.0.0.1:8000/api/hotkey/ws
[HotkeyBridge] Connected to backend hotkey service
```

### When A Key Pressed (NO JSON ERRORS):
```
Backend:
  [Hotkey] A pressed – triggering callbacks
  [Hotkey WS] Broadcasting event to 1 client(s)

Gateway:
  [HotkeyBridge] A pressed at 2025-12-01T16:54:32.123456Z
  [HotkeyBridge] Forwarded event to 1 frontend client(s)

Frontend (browser console):
  📨 WS MSG: {"type":"hotkey_pressed","key":"A","timestamp":"2025-12-01T16:54:32.123456"}
```

---

## Go/No-Go Decision Criteria

After fixing BUG #3 and testing:

### ✅ GO - Continue with feature if:
1. Pressing A shows overlay in browser
2. No errors in any layer (backend/gateway/frontend)
3. Overlay hides when closed
4. Feature works on user's dual-monitor cabinet setup

### 🛑 NO-GO - Abandon feature if:
1. Keyboard library can't detect system-wide A key (not just browser)
2. Overlay only works when browser has focus
3. Performance issues (lag, dropped events)
4. User determines feature not valuable enough to maintain

---

## Files Modified This Session

1. ✅ [gateway/ws/hotkey.js](gateway/ws/hotkey.js) - Fixed feature flag timing (BUG #1)
2. ✅ [.env](.env) - Fixed backend port URL (BUG #2)
3. 🔄 [gateway/ws/hotkey.js](gateway/ws/hotkey.js) - Needs fix for pong handling (BUG #3)

---

## Next Steps - Coordinated Approach

### Implementation Agent:
1. Apply Option A fix to gateway/ws/hotkey.js
2. Restart gateway
3. Monitor logs to confirm JSON errors stop
4. Signal ready for testing

### Codex:
1. Review fix in gateway/ws/hotkey.js
2. Run manual test: Open test_hotkey.html, press A
3. Verify backend → gateway → frontend event flow
4. Report test results

### User:
1. Approve Option A approach
2. Test pressing A key when prompted
3. Make go/no-go decision based on test results

---

## Summary

**Current State:**
- Backend: ✅ Working
- Gateway: 🟡 Connected but has JSON parse errors
- Frontend: 🔄 Untested (awaiting BUG #3 fix)

**Blocking Issue:** BUG #3 (JSON parse error on "pong")

**Recommended Fix:** Option A (3-line change in gateway)

**ETA to Working System:** ~5 minutes after fix applied and tested

**Risk Level:** LOW - Fix is simple and isolated to message handling
