/**
 * Gateway WebSocket bridge for hotkey events
 * Forwards A key presses from backend to frontend clients
 */

import WebSocket from 'ws';
import { startupState, inStartupGracePeriod } from '../startup_manager.js';

class HotkeyWebSocketBridge {
  constructor() {
    this.frontendClients = [];
    this.backendConnection = null;
    this.reconnectInterval = null;
  }

  /**
   * Initialize WebSocket server for frontend clients
   * @param {WebSocketServer} wss - WebSocket server instance
   */
  initialize(wss) {
    // Check feature flag at initialization time (after dotenv loaded)
    this.isEnabled = process.env.V2_HOTKEY_LAUNCHER === 'true';
    if (!this.isEnabled) {
      console.log('[HotkeyBridge] Feature disabled (V2_HOTKEY_LAUNCHER=' + process.env.V2_HOTKEY_LAUNCHER + ')');
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

    // NOTE: This is the GATEWAY connecting to BACKEND - not a bypass.
    // The gateway acts as a bridge: frontend -> gateway WS -> gateway -> backend WS -> backend.
    // Frontend clients connect to gateway's /ws/hotkey, never directly to backend.
    const backendUrl = process.env.FASTAPI_URL || 'http://localhost:8000';
    const wsUrl = backendUrl.replace('http://', 'ws://').replace('https://', 'wss://');
    const backendWsUrl = `${wsUrl}/api/hotkey/ws`;

    // Only log connection attempts after startup grace period
    if (!inStartupGracePeriod()) {
      console.log(`[HotkeyBridge] Connecting to backend: ${backendWsUrl}`);
    }

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
        const message = data.toString();

        // Handle ping/pong protocol (plain text, not JSON)
        if (message === 'pong') {
          return; // Silently ignore pong responses
        }

        try {
          const event = JSON.parse(message);

          // Log hotkey event
          if (event.type === 'hotkey_pressed') {
            console.log(`[HotkeyBridge] ${event.key} pressed at ${event.timestamp}`);
          }

          // Forward to all frontend clients
          this.broadcastToFrontend(event);
        } catch (err) {
          console.error('[HotkeyBridge] Error parsing backend message:', err.message);
        }
      });

      this.backendConnection.on('error', (err) => {
        // Suppress ECONNREFUSED during startup
        if (inStartupGracePeriod() && err.message.includes('ECONNREFUSED')) {
          return;
        }
        console.error('[HotkeyBridge] Backend connection error:', err.message);
      });

      this.backendConnection.on('close', () => {
        // Suppress reconnection spam during startup
        if (!inStartupGracePeriod()) {
          console.log('[HotkeyBridge] Backend connection closed, reconnecting in 5s...');
        }
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
      // Suppress reconnection log during startup
      if (!inStartupGracePeriod()) {
        console.log('[HotkeyBridge] Attempting to reconnect to backend...');
      }
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

export { hotkeyBridge, hotkeyBridge as default };
export const initializeHotkeyBridge = (wss) => hotkeyBridge.initialize(wss);
