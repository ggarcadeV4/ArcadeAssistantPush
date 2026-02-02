/**
 * ScoreKeeper Broadcast Route
 * 
 * HTTP endpoint for backend to push score events to WebSocket clients.
 * Backend (hiscore_watcher.py) POSTs here when scores change.
 * 
 * POST /api/scorekeeper/broadcast
 */

import express from 'express';
import { broadcastToClients, getClientCount } from '../ws/scorekeeper.js';

const router = express.Router();

/**
 * POST /api/scorekeeper/broadcast
 * 
 * Body: {
 *   type: 'score_updated' | 'bracket_update' | 'leaderboard_update',
 *   game?: string,
 *   scores?: array,
 *   ... any event data
 * }
 */
router.post('/broadcast', (req, res) => {
    try {
        const event = req.body;

        if (!event || !event.type) {
            return res.status(400).json({
                error: 'Missing event type',
                expected: { type: 'score_updated', game: 'pacman', scores: [] }
            });
        }

        const game = event.game || null;
        const clientCount = broadcastToClients(event, game);

        res.json({
            success: true,
            broadcast_to: clientCount,
            total_clients: getClientCount(),
            event_type: event.type
        });

    } catch (err) {
        console.error('[ScoreKeeper Broadcast] Error:', err);
        res.status(500).json({ error: 'Broadcast failed', message: err.message });
    }
});

/**
 * GET /api/scorekeeper/ws/status
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
