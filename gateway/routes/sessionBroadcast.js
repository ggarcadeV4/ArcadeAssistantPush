/**
 * Session Broadcast Route
 * 
 * HTTP endpoint for backend to push session/user events to WebSocket clients.
 * Backend (sessions.py, profile.py) POSTs here when user/session state changes.
 * 
 * POST /api/session/broadcast
 */

import express from 'express';
import { broadcastToClients, getClientCount } from '../ws/session.js';

const router = express.Router();

/**
 * POST /api/session/broadcast
 * 
 * Body: {
 *   type: 'user_changed' | 'session_created' | 'session_ended' | 'profile_updated',
 *   user_id?: string,
 *   session_id?: string,
 *   ... any event data
 * }
 */
router.post('/broadcast', (req, res) => {
    try {
        const event = req.body;

        if (!event || !event.type) {
            return res.status(400).json({
                error: 'Missing event type',
                expected: { type: 'user_changed', user_id: 'dallas', display_name: 'Dallas' }
            });
        }

        const clientCount = broadcastToClients(event);

        res.json({
            success: true,
            broadcast_to: clientCount,
            total_clients: getClientCount(),
            event_type: event.type
        });

    } catch (err) {
        console.error('[Session Broadcast] Error:', err);
        res.status(500).json({ error: 'Broadcast failed', message: err.message });
    }
});

/**
 * GET /api/session/ws/status
 * 
 * Health check for WebSocket connections
 */
router.get('/ws/status', (req, res) => {
    res.json({
        connected_clients: getClientCount(),
        status: 'operational'
    });
});

export default router;
