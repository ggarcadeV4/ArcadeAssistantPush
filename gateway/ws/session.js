/**
 * Session WebSocket Handler
 * 
 * Manages WebSocket connections for session/user events.
 * Frontend panels connect here to receive real-time user/session updates.
 * 
 * ws://localhost:8787/ws/session
 */
import { attachWebSocketIdentity, ensureDeviceIdentity, extractWebSocketIdentity } from './identity.js'

const clients = new Set();

/**
 * Setup the Session WebSocket handler
 */
export function setupSessionWebSocket(wss) {
    wss.on('connection', (ws, req) => {
        try {
            const identity = extractWebSocketIdentity(req, {
                defaultPanel: 'session',
                corrPrefix: 'session'
            });
            const { url } = identity;

            if (url.pathname !== '/ws/session') {
                return; // Not for us
            }

            if (!ensureDeviceIdentity(ws, identity, { channel: 'session websocket' })) {
                console.warn('[Session WS] Rejected anonymous session websocket');
                return;
            }

            const client = attachWebSocketIdentity(ws, identity, {
                ws,
                connectedAt: Date.now()
            });

            console.log('[Session WS] Client connected', {
                deviceId: client.deviceId,
                panel: client.panel,
                corrId: client.corrId
            });

            clients.add(client);

            // Send welcome message
            safeSend(ws, {
                type: 'connected',
                message: 'Session WebSocket connected',
                device: client.deviceId,
                panel: client.panel,
                corr_id: client.corrId,
                timestamp: new Date().toISOString()
            });

            ws.on('close', () => {
                clients.delete(client);
                console.log(`[Session WS] Client disconnected. Total: ${clients.size}`);
            });

            ws.on('error', (err) => {
                console.error('[Session WS] Client error:', err.message);
                clients.delete(client);
            });

        } catch (err) {
            console.error('[Session WS] Connection handler error:', err);
        }
    });

    console.log('[Session WS] Handler initialized');
}

/**
 * Safely send a message to a WebSocket client
 */
function safeSend(ws, message) {
    try {
        if (ws.readyState === 1) { // WebSocket.OPEN
            ws.send(JSON.stringify(message));
            return true;
        }
    } catch (err) {
        console.error('[Session WS] Send error:', err.message);
    }
    return false;
}

/**
 * Broadcast a message to all connected clients
 */
export function broadcastToClients(message) {
    let count = 0;

    for (const client of clients) {
        if (safeSend(client.ws, message)) {
            count++;
        }
    }

    console.log(`[Session WS] Broadcast to ${count}/${clients.size} clients:`, message.type);
    return count;
}

/**
 * Get the number of connected clients
 */
export function getClientCount() {
    return clients.size;
}
