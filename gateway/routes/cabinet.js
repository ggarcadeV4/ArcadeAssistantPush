/**
 * Cabinet Config API Routes
 * Part of: Phase 5.5 - Dynamic Config Exposure
 * 
 * Exposes cabinet configuration to the frontend, including:
 * - num_players (from remote_config.js / Supabase)
 * - LED channel mapping status
 * - Wiring wizard state
 */

import express from 'express';
import { getConfig } from '../services/remote_config.js';
import wizard, { getLedChannelsPath } from '../services/wiring_wizard.js';
import { speakingMode } from '../gems/aa-blinky/index.js';
import fs from 'fs';

const router = express.Router();

// ============================================================================
// GET /api/cabinet/config - Main configuration endpoint
// ============================================================================

/**
 * GET /api/cabinet/config
 * Returns cabinet configuration for frontend rendering
 * 
 * Response: {
 *   num_players: number,
 *   device_id: string,
 *   led_channels_path: string,
 *   led_channels_exists: boolean,
 *   wiring_wizard_active: boolean
 * }
 */
router.get('/config', async (req, res) => {
    try {
        const deviceId = req.headers['x-device-id'] || 'CAB-0001';

        // Get config from remote_config.js (Supabase-backed with cache)
        const config = await getConfig(deviceId);

        // Check if LED channels mapping exists
        const ledChannelsPath = getLedChannelsPath();
        const ledChannelsExists = fs.existsSync(ledChannelsPath);

        // Get wizard state
        const wizardState = wizard.getState();

        res.json({
            success: true,
            config: {
                num_players: config.num_players || 2,
                device_id: deviceId,
                model: config.model,
                fallback_models: config.fallback_models,
                feature_flags: config.feature_flags || {}
            },
            led: {
                channels_path: ledChannelsPath,
                channels_exists: ledChannelsExists,
                wizard_active: wizardState.isActive,
                wizard_session: wizardState.sessionId
            }
        });

    } catch (error) {
        console.error('[cabinet-config] Error fetching config:', error);
        res.status(500).json({
            success: false,
            error: error.message,
            config: {
                num_players: 2,  // Safe default
                device_id: 'CAB-0001'
            }
        });
    }
});

// ============================================================================
// GET /api/cabinet/num_players - Quick endpoint for player count
// ============================================================================

/**
 * GET /api/cabinet/num_players
 * Quick endpoint returning just the player count for frontend rendering
 */
router.get('/num_players', async (req, res) => {
    try {
        const deviceId = req.headers['x-device-id'] || 'CAB-0001';
        const config = await getConfig(deviceId);

        res.json({
            num_players: config.num_players || 2
        });

    } catch (error) {
        res.json({
            num_players: 2  // Safe default
        });
    }
});

// ============================================================================
// WIRING WIZARD ENDPOINTS
// ============================================================================

/**
 * POST /api/cabinet/wizard/start
 * Start a new wiring wizard session
 * Body: { buttons?: string[], numPlayers?: number }
 */
router.post('/wizard/start', async (req, res) => {
    try {
        const { buttons, numPlayers } = req.body || {};
        const result = await wizard.start({ buttons, numPlayers });

        if (result.error) {
            return res.status(400).json({ success: false, error: result.error, ...result });
        }

        res.json({ success: true, ...result });

    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

/**
 * POST /api/cabinet/wizard/blink
 * Blink the next port in the sequence
 */
router.post('/wizard/blink', async (req, res) => {
    try {
        const result = await wizard.blinkNext();

        if (result.error) {
            return res.status(400).json({ success: false, ...result });
        }

        res.json({ success: true, ...result });

    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

/**
 * POST /api/cabinet/wizard/map
 * Record a button press mapping
 * Body: { buttonId: string, portOverride?: number }
 */
router.post('/wizard/map', (req, res) => {
    try {
        const { buttonId, portOverride } = req.body || {};

        if (!buttonId) {
            return res.status(400).json({ success: false, error: 'buttonId required' });
        }

        const result = wizard.recordButtonPress(buttonId, portOverride);

        if (result.error) {
            return res.status(400).json({ success: false, ...result });
        }

        res.json({ success: true, ...result });

    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

/**
 * POST /api/cabinet/wizard/skip
 * Skip the current port
 */
router.post('/wizard/skip', (req, res) => {
    try {
        const result = wizard.skip();

        if (result.error) {
            return res.status(400).json({ success: false, ...result });
        }

        res.json({ success: true, ...result });

    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

/**
 * GET /api/cabinet/wizard/state
 * Get current wizard state
 */
router.get('/wizard/state', (req, res) => {
    res.json({
        success: true,
        ...wizard.getState()
    });
});

/**
 * POST /api/cabinet/wizard/finish
 * Complete the wizard and save
 */
router.post('/wizard/finish', async (req, res) => {
    try {
        const result = await wizard.finish();

        if (result.error) {
            return res.status(400).json({ success: false, ...result });
        }

        res.json({ success: true, ...result });

    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

/**
 * POST /api/cabinet/wizard/cancel
 * Cancel the current wizard session
 */
router.post('/wizard/cancel', (req, res) => {
    wizard.cancel();
    res.json({ success: true, cancelled: true });
});

/**
 * GET /api/cabinet/led_channels
 * Get the current LED channel mapping
 */
router.get('/led_channels', (req, res) => {
    try {
        const mapping = wizard.load();

        if (!mapping) {
            return res.status(404).json({
                success: false,
                error: 'No LED channel mapping found',
                path: getLedChannelsPath()
            });
        }

        res.json({ success: true, ...mapping });

    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

// ============================================================================
// LIGHTING ENDPOINTS
// ============================================================================

/**
 * POST /api/cabinet/lighting/speaking
 * Enable/disable speaking mode LED animation (P1/P2 Start buttons breathe)
 * Body: { enabled: boolean }
 */
router.post('/lighting/speaking', (req, res) => {
    try {
        const { enabled } = req.body || {};
        speakingMode(!!enabled);
        console.log(`[cabinet] Speaking mode ${enabled ? 'enabled' : 'disabled'}`);
        res.json({ success: true, speaking: !!enabled });
    } catch (error) {
        console.error('[cabinet] Speaking mode error:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

export default router;
