# Codex Task 002: Gateway WebSocket Bridge for Hotkey Events

**Assigned:** 2025-11-30
**Priority:** HIGH (Part of Feature 2: Hotkey Launcher)
**Estimated Time:** 20 minutes
**Dependencies:** Task 2.1 complete (Backend hotkey service exists)

---

## **Context**

You've completed Task 2.1 (backend hotkey service with F9 detection). Now we need to bridge those hotkey events from the backend WebSocket to the frontend.

**Flow:** Backend detects F9 → Backend broadcasts via `/api/hotkey/ws` → Gateway forwards event → Frontend overlay appears

**This task:** Create the gateway WebSocket bridge that forwards F9 events from backend to frontend clients.

---

## **Files to Modify**

### **Primary File:**
- `gateway/ws/hotkey.js` (CREATE NEW FILE)

### **Registration File:**
- `gateway/server.js` (add WebSocket handler registration)

---

## **Step-by-Step Instructions**

### **Step 1: Create Gateway WebSocket Handler**

Create new file: `gateway/ws/hotkey.js`

```javascript
/**
 * Gateway WebSocket bridge for hotkey events
 * Forwards F9 presses from backend to frontend clients
 */

const WebSocket = require('ws');

class HotkeyWebSocketBridge {
  constructor() {
    this.frontendClients = [];
    this.backendConnection = null;
    this.reconnectInterval = null;
    this.isEnabled = process.env.V2_HOTKEY_LAUNCHER === 'true';
  }

  /**
   * Initialize WebSocket server for frontend clients
   * @param {WebSocketServer} wss - WebSocket server instance
   */
  initialize(wss) {
    if (!this.isEnabled) {
      console.log('[HotkeyBridge] Feature disabled (V2_HOTKEY_LAUNCHER=false)');
      return;
    }

    wss.on('connection', (ws, req) => {
      // Only handle /ws/hotkey path
      if (!req.url.startsWith('/ws/hotkey')) {
        return;
      }

      console.log('[HotkeyBridge] Frontend client connected');
      this.frontendClients.push(ws);

      // Send welcome message
      ws.send(JSON.stringify({
        type: 'connected',
        message: 'Hotkey WebSocket bridge ready',
        timestamp: new Date().toISOString()
      }));

      // Handle ping from frontend
      ws.on('message', (message) => {
        try {
          const data = JSON.parse(message);
          if (data.type === 'ping') {
            ws.send(JSON.stringify({ type: 'pong' }));
          }
        } catch (err) {
          console.error('[HotkeyBridge] Invalid message from frontend:', err);
        }
      });

      // Handle disconnect
      ws.on('close', () => {
        console.log('[HotkeyBridge] Frontend client disconnected');
        this.frontendClients = this.frontendClients.filter(client => client !== ws);
      });
    });

    // Connect to backend WebSocket
    this.connectToBackend();
  }

  /**
   * Connect to backend hotkey WebSocket
   */
  connectToBackend() {
    if (!this.isEnabled) return;

    const backendUrl = process.env.FASTAPI_URL || 'http://localhost:8888';
    const wsUrl = backendUrl.replace('http://', 'ws://').replace('https://', 'wss://');
    const backendWsUrl = `${wsUrl}/api/hotkey/ws`;

    console.log(`[HotkeyBridge] Connecting to backend: ${backendWsUrl}`);

    try {
      this.backendConnection = new WebSocket(backendWsUrl);

      this.backendConnection.on('open', () => {
        console.log('[HotkeyBridge] Connected to backend hotkey service');

        // Send ping to keep alive
        const pingInterval = setInterval(() => {
          if (this.backendConnection?.readyState === WebSocket.OPEN) {
            this.backendConnection.send('ping');
          }
        }, 30000); // Every 30 seconds

        this.backendConnection.on('close', () => {
          clearInterval(pingInterval);
        });
      });

      this.backendConnection.on('message', (data) => {
        try {
          const event = JSON.parse(data);

          // Log hotkey event
          if (event.type === 'hotkey_pressed') {
            console.log(`[HotkeyBridge] F9 pressed at ${event.timestamp}`);
          }

          // Forward to all frontend clients
          this.broadcastToFrontend(event);
        } catch (err) {
          console.error('[HotkeyBridge] Error parsing backend message:', err);
        }
      });

      this.backendConnection.on('error', (err) => {
        console.error('[HotkeyBridge] Backend connection error:', err.message);
      });

      this.backendConnection.on('close', () => {
        console.log('[HotkeyBridge] Backend connection closed, reconnecting in 5s...');
        this.scheduleReconnect();
      });

    } catch (err) {
      console.error('[HotkeyBridge] Failed to connect to backend:', err);
      this.scheduleReconnect();
    }
  }

  /**
   * Schedule reconnection to backend
   */
  scheduleReconnect() {
    if (this.reconnectInterval) {
      clearTimeout(this.reconnectInterval);
    }

    this.reconnectInterval = setTimeout(() => {
      console.log('[HotkeyBridge] Attempting to reconnect to backend...');
      this.connectToBackend();
    }, 5000);
  }

  /**
   * Broadcast event to all connected frontend clients
   */
  broadcastToFrontend(event) {
    const message = JSON.stringify(event);
    let sentCount = 0;

    this.frontendClients.forEach(client => {
      if (client.readyState === WebSocket.OPEN) {
        client.send(message);
        sentCount++;
      }
    });

    if (sentCount > 0) {
      console.log(`[HotkeyBridge] Forwarded event to ${sentCount} frontend client(s)`);
    }
  }

  /**
   * Cleanup on shutdown
   */
  shutdown() {
    console.log('[HotkeyBridge] Shutting down...');

    if (this.reconnectInterval) {
      clearTimeout(this.reconnectInterval);
    }

    if (this.backendConnection) {
      this.backendConnection.close();
    }

    this.frontendClients.forEach(client => client.close());
    this.frontendClients = [];
  }
}

// Export singleton instance
const hotkeyBridge = new HotkeyWebSocketBridge();

module.exports = {
  hotkeyBridge,
  initializeHotkeyBridge: (wss) => hotkeyBridge.initialize(wss)
};
```

---

### **Step 2: Register WebSocket Handler in Gateway Server**

Modify `gateway/server.js` to initialize the hotkey bridge.

**Find the WebSocket server initialization section** (likely around where audio WebSocket is set up), and add:

```javascript
// Import hotkey bridge
const { initializeHotkeyBridge, hotkeyBridge } = require('./ws/hotkey.js');

// ... existing WebSocket server setup ...

// Initialize hotkey bridge (add after audio WebSocket setup)
initializeHotkeyBridge(wss);

// Shutdown handler (add to existing shutdown logic)
process.on('SIGINT', () => {
  console.log('Shutting down gateway...');
  hotkeyBridge.shutdown();
  process.exit(0);
});
```

**If there's no existing WebSocket server setup in `gateway/server.js`:**

Add this WebSocket server initialization:

```javascript
const WebSocket = require('ws');
const { initializeHotkeyBridge, hotkeyBridge } = require('./ws/hotkey.js');

// Create WebSocket server (attach to existing HTTP server)
const wss = new WebSocket.Server({ server }); // 'server' is your existing HTTP server

// Initialize hotkey bridge
initializeHotkeyBridge(wss);

// Shutdown handler
process.on('SIGINT', () => {
  console.log('Shutting down gateway...');
  hotkeyBridge.shutdown();
  server.close();
  process.exit(0);
});
```

---

## **Expected Outcome**

After completing this task:

1. **Gateway listens at:** `ws://localhost:8787/ws/hotkey`
2. **Backend connection:** Gateway connects to `ws://localhost:8888/api/hotkey/ws`
3. **Event flow:**
   - User presses F9
   - Backend detects and broadcasts `{"type": "hotkey_pressed", "key": "F9", "timestamp": "..."}`
   - Gateway receives event from backend
   - Gateway forwards event to all connected frontend clients
4. **Reconnection:** If backend disconnects, gateway auto-reconnects every 5 seconds
5. **Feature flag:** Only active if `V2_HOTKEY_LAUNCHER=true` in `.env`

---

## **Testing**

### **Test 1: Gateway starts without errors**

```bash
# Start backend first (with V2_HOTKEY_LAUNCHER=true in .env)
npm run dev:backend

# Start gateway
npm run dev:gateway

# Check logs for:
# [HotkeyBridge] Connecting to backend: ws://localhost:8888/api/hotkey/ws
# [HotkeyBridge] Connected to backend hotkey service
```

**Expected:** No errors, backend connection established

---

### **Test 2: Frontend client can connect**

Open browser console at `http://localhost:8787` and run:

```javascript
const ws = new WebSocket('ws://localhost:8787/ws/hotkey');

ws.onopen = () => console.log('Connected to hotkey bridge');
ws.onmessage = (event) => console.log('Received:', JSON.parse(event.data));
ws.onerror = (err) => console.error('WebSocket error:', err);

// You should see:
// Connected to hotkey bridge
// Received: {type: "connected", message: "Hotkey WebSocket bridge ready", timestamp: "..."}
```

---

### **Test 3: F9 event forwarding (requires admin privileges)**

**IMPORTANT:** Backend must be running as administrator (Windows) or with sudo (Linux) for keyboard library to work.

1. Ensure backend is running with admin privileges
2. Connect frontend WebSocket client (from Test 2)
3. Press F9 key
4. Check browser console for:
   ```
   Received: {type: "hotkey_pressed", key: "F9", timestamp: "2025-11-30T..."}
   ```

**If F9 doesn't trigger:**
- Check backend logs for errors from `keyboard` library
- Verify backend is running with admin/sudo
- Check `backend/routers/hotkey.py` health endpoint: `curl http://localhost:8888/api/hotkey/health`

---

### **Test 4: Reconnection logic**

1. Start gateway (backend already running)
2. Stop backend (`Ctrl+C`)
3. Check gateway logs for:
   ```
   [HotkeyBridge] Backend connection closed, reconnecting in 5s...
   [HotkeyBridge] Attempting to reconnect to backend...
   ```
4. Restart backend
5. Check gateway logs for:
   ```
   [HotkeyBridge] Connected to backend hotkey service
   ```

---

## **Validation Checklist**

- ✅ Gateway starts without errors
- ✅ Backend WebSocket connection established
- ✅ Frontend clients can connect to `ws://localhost:8787/ws/hotkey`
- ✅ F9 press forwards event from backend → gateway → frontend
- ✅ Auto-reconnect works if backend restarts
- ✅ Feature flag respected (no errors if V2_HOTKEY_LAUNCHER=false)
- ✅ Ping/pong keep-alive working
- ✅ Multiple frontend clients supported (broadcast works)

---

## **Common Issues**

### **Issue 1: Backend connection fails**
- **Symptom:** `[HotkeyBridge] Backend connection error: ECONNREFUSED`
- **Fix:** Ensure backend is running (`npm run dev:backend`)
- **Fix:** Check `FASTAPI_URL` in `.env` matches backend port (8000 or 8888)

### **Issue 2: F9 not detected**
- **Symptom:** No events received when pressing F9
- **Fix:** Backend must run as administrator (Windows) or sudo (Linux)
- **Fix:** Check backend logs for keyboard library errors
- **Workaround:** Test with manual WebSocket message to backend (simulate F9)

### **Issue 3: WebSocket server not found**
- **Symptom:** `Cannot read property 'Server' of undefined`
- **Fix:** Install WebSocket library: `cd gateway && npm install ws`

### **Issue 4: Multiple WebSocket servers conflict**
- **Symptom:** Port 8787 already in use
- **Fix:** Reuse existing WebSocket server instance (don't create new one)
- **Fix:** Use path-based routing (`/ws/hotkey` vs `/ws/audio`)

---

## **Next Task After This**

Once Task 2.2 is complete and tested, the next task will be:

**Task 2.3: Frontend Overlay Component**
- Build React overlay that appears when F9 is pressed
- Dewey avatar with voice activation
- VAD (Voice Activity Detection) for auto-stop microphone
- Estimated time: 90 minutes

---

## **Questions? Issues?**

If you encounter any blockers:
1. Document the exact error message
2. Note which file/line number
3. Check if `ws` library is installed (`npm list ws` in gateway directory)
4. Verify backend health endpoint: `curl http://localhost:8888/api/hotkey/health`
5. Report back via status update markdown

**Status Update Template:** See `V2_STATUS_TEMPLATE.md`

---

**Codex - this is a straightforward WebSocket bridge following the same pattern as the audio WebSocket. The key is proper reconnection logic and event forwarding. Start with Step 1 and test each component as you go. Good luck! 🚀**
