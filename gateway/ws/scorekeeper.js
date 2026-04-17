/**
 * ScoreKeeper SAM WebSocket Handler
 * 
 * Provides real-time score updates from MAME hiscore watcher to frontend.
 * 
 * Client connects to: ws://localhost:8787/scorekeeper/ws
 * Backend POSTs to: POST /api/scorekeeper/broadcast to push events
 */
import { attachWebSocketIdentity, extractWebSocketIdentity } from './identity.js'

// Track connected clients
const clients = new Set();

/**
 * Setup ScoreKeeper WebSocket on the shared WSS
 */
export function setupScorekeeperWebSocket(wss) {
    console.log('[ScoreKeeper WS] Setting up WebSocket handler...');

    wss.on('connection', (ws, req) => {
        try {
            const identity = extractWebSocketIdentity(req, {
                defaultPanel: 'scorekeeper',
                corrPrefix: 'scorekeeper'
            });
            const { url } = identity;

            if (url.pathname !== '/scorekeeper/ws') {
                return; // Not our path, let other handlers deal with it
            }

            // Cabinet scoreboards remain anonymous-compatible, but identity-bearing callers are preserved.
            const connectionId = identity.corrId;

            console.log(`[ScoreKeeper WS] ✅ Client connected: ${connectionId}`);

            // Track this client
            const client = attachWebSocketIdentity(ws, identity, {
                ws,
                id: connectionId,
                connectedAt: Date.now()
            });
            clients.add(client);

            // Send welcome message
            safeSend(ws, {
                type: 'connected',
                message: 'ScoreKeeper WebSocket ready',
                clientId: connectionId,
                device: client.deviceId || '',
                panel: client.panel,
                corr_id: client.corrId
            });

            // Handle incoming messages from clients
            ws.on('message', (raw) => {
                try {
                    const data = JSON.parse(raw.toString());
                    handleClientMessage(client, data);
                } catch (err) {
                    console.error('[ScoreKeeper WS] Message parse error:', err);
                    safeSend(ws, { type: 'error', message: 'Invalid JSON' });
                }
            });

            ws.on('close', (code, reason) => {
                console.log(`[ScoreKeeper WS] Client disconnected (${connectionId}): ${code}`);
                clients.delete(client);
            });

            ws.on('error', (err) => {
                console.error('[ScoreKeeper WS] Client error:', err);
                clients.delete(client);
            });

        } catch (err) {
            console.error('[ScoreKeeper WS] Connection handler error:', err);
        }
    });

    console.log('[ScoreKeeper WS] WebSocket handler configured');
}

/**
 * Handle messages from connected clients
 */
function handleClientMessage(client, data) {
    switch (data.type) {
        case 'ping':
            safeSend(client.ws, { type: 'pong', timestamp: Date.now() });
            break;

        case 'subscribe':
            // Client wants to subscribe to specific game leaderboard
            client.subscribedGame = data.game || null;
            safeSend(client.ws, {
                type: 'subscribed',
                game: data.game,
                timestamp: Date.now()
            });
            break;

        case 'advance_winner':
            // Tournament match result - forward to backend
            console.log('[ScoreKeeper WS] Advance winner:', data);
            // We'll handle this through HTTP for now
            break;

        case 'score_update':
            // Manual score submission - forward to backend (existing REST flow)
            console.log('[ScoreKeeper WS] Score update request:', data);
            break;

        default:
            console.log('[ScoreKeeper WS] Unknown message type:', data.type);
    }
}

/**
 * Broadcast a message to all connected clients
 * @param {object} message - The message to broadcast
 * @param {string} [filterGame] - Optional game filter for targeted broadcast
 */
export function broadcastToClients(message, filterGame = null) {
    let count = 0;

    for (const client of clients) {
        // If filterGame specified, only send to clients subscribed to that game
        if (filterGame && client.subscribedGame && client.subscribedGame !== filterGame) {
            continue;
        }

        if (safeSend(client.ws, message)) {
            count++;
        }
    }

    console.log(`[ScoreKeeper WS] Broadcast to ${count}/${clients.size} clients:`, message.type);
    return count;
}

/**
 * Get count of connected clients
 */
export function getClientCount() {
    return clients.size;
}

/**
 * Safe send that handles closed connections
 */
function safeSend(ws, payload) {
    try {
        const OPEN_STATE = typeof ws.OPEN === 'number' ? ws.OPEN : 1;
        if (ws.readyState === OPEN_STATE) {
            ws.send(JSON.stringify(payload));
            return true;
        }
    } catch (err) {
        console.error('[ScoreKeeper WS] Failed to send:', err.message);
    }
    return false;
}
