# Hotkey System Audit - Specific Diagnostic Commands for Codex

**Context:** We've implemented a global hotkey system (A key) that should trigger an overlay in the frontend. The backend reports the service is working, but pressing A does nothing visible in the browser.

**Your job:** Run these EXACT commands and report the EXACT output. No interpretation needed - just run and report.

---

## **STEP 1: Verify Backend Service Status**

**Command 1a:** Check if hotkey service reports as active
```bash
curl -s http://localhost:8888/api/hotkey/health | python -m json.tool
```

**Expected output:**
```json
{
  "service": "hotkey",
  "status": "active",
  "hotkey": "A",
  "ws_clients": 0,
  "feature_enabled": true
}
```

**Question:** What is the exact JSON output? Copy/paste it.

---

**Command 1b:** Check backend logs for hotkey initialization

Search backend logs for these EXACT strings:
```
DEBUG: V2_HOTKEY_LAUNCHER =
[Hotkey] Starting hotkey service...
[Hotkey] Service started successfully!
```

**Question:** Do you see ALL THREE of these lines in the backend logs? Copy/paste them if yes. If no, which ones are missing?

---

**Command 1c:** Test if backend detects A key press

1. Make sure backend logs are visible
2. Press the A key on your keyboard 3 times
3. Look for this EXACT log line each time you press A:
```
[Hotkey] A pressed – triggering callbacks
```

**Question:** Do you see this log appear 3 times? Copy/paste the exact lines.

---

## **STEP 2: Verify Gateway Bridge Status**

**Command 2a:** Check if gateway has hotkey bridge file
```bash
ls -la "C:\Users\Dad's PC\Desktop\Arcade Assistant Local\gateway\ws\hotkey.js"
```

**Question:** Does the file exist? What is the file size?

---

**Command 2b:** Check if gateway imports hotkey bridge

```bash
grep -n "hotkeyBridge" "C:\Users\Dad's PC\Desktop\Arcade Assistant Local\gateway\server.js"
```

**Expected output:** Should see import line and initialization line

**Question:** Copy/paste the exact grep output. How many lines matched?

---

**Command 2c:** Check gateway startup logs

Search gateway logs for these EXACT strings:
```
[HotkeyBridge] Connecting to backend: ws://localhost:8888/api/hotkey/ws
[HotkeyBridge] Connected to backend hotkey service
```

**Question:** Do you see BOTH of these lines in gateway logs? Copy/paste them if yes. If no, what error do you see instead?

---

**Command 2d:** Test if gateway receives backend events

1. Make sure gateway logs are visible
2. Press the A key 3 times
3. Look for this EXACT log line:
```
[HotkeyBridge] A pressed at
```

**Question:** Do you see this log 3 times? Copy/paste the exact lines.

---

## **STEP 3: Verify Frontend WebSocket Connection**

**Command 3a:** Check if hotkeyClient file exists
```bash
cat "C:\Users\Dad's PC\Desktop\Arcade Assistant Local\frontend\src\services\hotkeyClient.js" | grep "_url"
```

**Expected output:** Should show WebSocket URL

**Question:** What is the EXACT URL in the output? Should be `ws://${host}/ws/hotkey`

---

**Command 3b:** Check if HotkeyOverlay component exists and is imported

```bash
grep -n "HotkeyOverlay" "C:\Users\Dad's PC\Desktop\Arcade Assistant Local\frontend\src\App.jsx"
```

**Expected output:** Should see import statement and `<HotkeyOverlay />` tag

**Question:** Copy/paste the exact grep output. Do you see both import AND component usage?

---

**Command 3c:** Test WebSocket connection from browser

Open browser at `http://localhost:8787`, open DevTools console (F12), and run this EXACT code:

```javascript
window.testWS = new WebSocket('ws://localhost:8787/ws/hotkey');
window.testWS.onopen = () => console.log('✅ WS OPEN');
window.testWS.onmessage = (e) => console.log('📨 WS MSG:', e.data);
window.testWS.onerror = (e) => console.log('❌ WS ERROR');
window.testWS.onclose = (e) => console.log('🔌 WS CLOSE:', e.code);
```

**Question 1:** After running this code, do you see "✅ WS OPEN" in console? YES or NO

**Question 2:** Now press the A key 3 times. Do you see "📨 WS MSG:" appear? Copy/paste the exact messages.

**Question 3:** If you see errors, copy/paste the EXACT error text.

---

## **STEP 4: Verify HotkeyOverlay Component Mounting**

**Command 4a:** Check if component has mount logging

```bash
grep -A 3 "useEffect" "C:\Users\Dad's PC\Desktop\Arcade Assistant Local\frontend\src\components\HotkeyOverlay.jsx" | head -20
```

**Question:** Does the useEffect call `hotkeyClient.connect()`? Copy/paste the relevant lines.

---

**Command 4b:** Add temporary debug logging

Add this line at the TOP of the HotkeyOverlay component (right after the function declaration):

```javascript
export default function HotkeyOverlay() {
  console.log('[AUDIT] HotkeyOverlay mounted at', new Date().toISOString());  // ADD THIS LINE
  const [visible, setVisible] = useState(false);
```

Then reload the browser and check console.

**Question:** Do you see "[AUDIT] HotkeyOverlay mounted" in browser console? Copy/paste the exact line.

---

**Command 4c:** Add listener debug logging

In `hotkeyClient.js`, add console.log to the message handler:

```javascript
this.ws.onmessage = (event) => {
  console.log('[AUDIT] hotkeyClient received:', event.data);  // ADD THIS LINE
  try {
    const data = JSON.parse(event.data)
    this._notify(data)
```

Reload browser, press A key 3 times.

**Question:** Do you see "[AUDIT] hotkeyClient received:" appear 3 times? Copy/paste the exact messages.

---

## **STEP 5: Check CSS and Visibility**

**Command 5a:** Check if CSS file exists
```bash
ls -la "C:\Users\Dad's PC\Desktop\Arcade Assistant Local\frontend\src\components\HotkeyOverlay.css"
```

**Question:** Does the file exist? What is the file size?

---

**Command 5b:** Force overlay to visible for testing

Temporarily modify HotkeyOverlay component to ALWAYS show:

```javascript
export default function HotkeyOverlay() {
  const [visible, setVisible] = useState(true);  // CHANGE false to true
```

Reload browser.

**Question:** Do you see the overlay appear immediately? Take a screenshot and describe what you see (or "nothing visible").

---

## **FINAL DIAGNOSIS**

Based on the above tests, fill in this table:

| Component | Status | Evidence |
|-----------|--------|----------|
| Backend hotkey detection | PASS/FAIL | (output from Step 1c) |
| Backend WebSocket broadcast | PASS/FAIL | (ws_clients count > 0?) |
| Gateway bridge connection | PASS/FAIL | (output from Step 2c) |
| Gateway event forwarding | PASS/FAIL | (output from Step 2d) |
| Frontend WebSocket connection | PASS/FAIL | (output from Step 3c Q1) |
| Frontend receives events | PASS/FAIL | (output from Step 3c Q2) |
| HotkeyOverlay mounts | PASS/FAIL | (output from Step 4b) |
| HotkeyOverlay receives events | PASS/FAIL | (output from Step 4c) |
| Overlay renders when visible=true | PASS/FAIL | (output from Step 5b) |

**Where does the chain break?** Identify the FIRST failing step above.

**Root cause:** (State the specific reason based on which step failed)

**Fix needed:** (Specific file and line number to fix)

### **1. Backend Hotkey Detection**

**Question:** Is the backend actually detecting A key presses?

**What to check:**
- Run the dev stack and press the A key multiple times
- Check backend logs for: `[Hotkey] A pressed – triggering callbacks`
- Check backend logs for: `[Hotkey WS] Broadcasting event to X client(s)`
- If no logs appear when pressing A, diagnose why the keyboard library isn't detecting keypresses
- Verify the backend is running with Administrator privileges (required for keyboard library)

**Expected result:** Backend should log keypress detection AND broadcast events

---

### **2. Gateway WebSocket Bridge**

**Question:** Is the gateway WebSocket bridge actually running and connected to the backend?

**What to check:**
- Check gateway startup logs for: `[HotkeyBridge] Connecting to backend: ws://localhost:8888/api/hotkey/ws`
- Check gateway logs for: `[HotkeyBridge] Connected to backend hotkey service`
- If not connected, check if `V2_HOTKEY_LAUNCHER=true` is set in `.env`
- Check if `gateway/ws/hotkey.js` file exists
- Check if it's imported in `gateway/server.js`
- Check if it's initialized in `gateway/server.js` (look for `initializeHotkeyBridge(wss)`)
- When A is pressed, check gateway logs for: `[HotkeyBridge] A pressed at [timestamp]`

**Expected result:** Gateway should connect to backend on startup AND log forwarded events when A is pressed

---

### **3. Frontend WebSocket Client**

**Question:** Is the frontend `hotkeyClient` actually connecting to the gateway?

**What to check:**
- Verify `frontend/src/services/hotkeyClient.js` exists
- Check the WebSocket URL in hotkeyClient - should be `ws://${host}/ws/hotkey`
- Open browser DevTools console and look for any WebSocket connection attempts
- Manually test WebSocket connection from browser console:
  ```javascript
  const ws = new WebSocket('ws://localhost:8787/ws/hotkey');
  ws.onopen = () => console.log('CONNECTED');
  ws.onmessage = (e) => console.log('MESSAGE:', e.data);
  ws.onerror = (e) => console.error('ERROR:', e);
  ```
- Press A and see if MESSAGE appears
- Check browser Network tab for WebSocket connections to `/ws/hotkey`

**Expected result:** Browser should successfully connect to `ws://localhost:8787/ws/hotkey` and receive events when A is pressed

---

### **4. HotkeyOverlay Component**

**Question:** Is the HotkeyOverlay component actually rendering and listening for events?

**What to check:**
- Verify `frontend/src/components/HotkeyOverlay.jsx` exists
- Check if it's imported and rendered in `frontend/src/App.jsx`
- Look for `<HotkeyOverlay />` in App.jsx
- Check if the component has a `useEffect` that calls `hotkeyClient.connect()`
- Add console.log to HotkeyOverlay component to verify it mounts:
  ```javascript
  useEffect(() => {
    console.log('[HotkeyOverlay] Component mounted');
    hotkeyClient.connect();
    // ... rest of code
  }, []);
  ```
- Check browser console for "[HotkeyOverlay] Component mounted"
- Check if CSS file `HotkeyOverlay.css` exists

**Expected result:** Component should mount, connect to hotkeyClient, and log events when A is pressed

---

### **5. End-to-End Flow Test**

**Question:** Can you trace a single A key press through the entire system?

**What to trace:**
1. Press A key on keyboard
2. Backend logs: `[Hotkey] A pressed – triggering callbacks`
3. Backend logs: `[Hotkey WS] Broadcasting event to X client(s)` (X should be > 0)
4. Gateway logs: `[HotkeyBridge] A pressed at [timestamp]`
5. Gateway logs: `[HotkeyBridge] Forwarded event to Y frontend client(s)` (Y should be > 0)
6. Browser console: Should show WebSocket message received (if hotkeyClient has debug logging)
7. Browser UI: Overlay should appear

**Where is the chain breaking?** Identify the exact point where the event stops propagating.

---

### **6. Common Failure Points to Check**

**Check these specific issues:**

- **A. Gateway crashed on startup?**
  - Look for gateway error logs mentioning "hotkey" or "SyntaxError"
  - Check if gateway is actually running: `curl http://localhost:8787/api/health`

- **B. Wrong WebSocket URL?**
  - Frontend trying `/api/hotkey/ws` instead of `/ws/hotkey`?
  - Check `hotkeyClient.js` line where `_url` is set

- **C. WebSocket path not allowed?**
  - Check `gateway/server.js` for `allowedPaths` set
  - Should include `/ws/hotkey`

- **D. Frontend not on correct port?**
  - User is viewing `http://localhost:5173` (Vite dev server)
  - Should WebSocket connect to `ws://localhost:8787` (gateway) or `ws://localhost:5173` (vite)?
  - Check Vite proxy configuration

- **E. HotkeyOverlay not in DOM?**
  - Run in browser console: `document.querySelector('.hotkey-overlay-backdrop')`
  - Should return `null` when closed, but component should still be listening

---

## **Audit Deliverables**

**Please provide:**

1. **Status of each component:**
   - Backend hotkey detection: WORKING / NOT WORKING / UNKNOWN
   - Gateway bridge: WORKING / NOT WORKING / UNKNOWN
   - Frontend WebSocket client: WORKING / NOT WORKING / UNKNOWN
   - HotkeyOverlay component: WORKING / NOT WORKING / UNKNOWN

2. **Exact point of failure:** Where in the chain is the event lost?

3. **Root cause:** What is preventing the overlay from appearing?

4. **Fix recommendation:** What specific code changes are needed?

---

## **Test Procedure for Codex**

1. Start the dev stack: `npm run dev`
2. Wait for all services to start
3. Press the A key 3-5 times
4. Check all logs (backend, gateway, browser console)
5. Document what you see at each layer
6. Identify where the chain breaks

---

**Goal:** Determine definitively whether this hotkey feature is viable or if we should abandon it and pursue a different approach.
