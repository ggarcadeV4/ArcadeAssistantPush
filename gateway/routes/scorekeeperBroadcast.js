/**
 * ScoreKeeper Broadcast Route
 * 
 * HTTP endpoint for backend to push score events to WebSocket clients.
 * Backend (hiscore_watcher.py) POSTs here when scores change.
 * 
 * POST /api/scorekeeper/broadcast
 */

import express from 'express';
import { insertScore } from '../services/supabase_client.js';
import { resolveRequestDeviceId } from '../utils/cabinetIdentity.js';
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
 * POST /api/scorekeeper/supabase-sync
 *
 * Option A chosen: restore the dead gateway route with the least surface area.
 * hiscore_watcher.py already persisted/broadcast the local score event, so this
 * route only mirrors the record into Supabase instead of proxying through
 * backend score write handlers that would duplicate local writes.
 */
router.post('/supabase-sync', async (req, res) => {
    try {
        const { game_id, player, score, meta } = req.body || {};

        if (!game_id || !player || score === undefined || score === null) {
            return res.status(400).json({
                error: 'Missing required fields',
                expected: { game_id: 'pacman', player: 'AAA', score: 12345, meta: {} }
            });
        }

        const deviceId = resolveRequestDeviceId(req) || 'UNPROVISIONED';
        const success = await insertScore(deviceId, game_id, player, score, meta || {});

        if (!success) {
            return res.status(503).json({
                success: false,
                error: 'Supabase score mirror failed'
            });
        }

        res.json({
            success: true,
            cabinet_id: deviceId,
            game_id,
            player
        });
    } catch (err) {
        console.error('[ScoreKeeper Broadcast] Supabase sync error:', err);
        res.status(500).json({ success: false, error: 'Supabase sync failed', message: err.message });
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
