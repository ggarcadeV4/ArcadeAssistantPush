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
import { resolveRequestDeviceId } from '../utils/cabinetIdentity.js';
import fs from 'fs';

const router = express.Router();
let speakingModeActive = false;

router.get('/config', async (req, res) => {
    try {
        const deviceId = resolveRequestDeviceId(req) || 'UNPROVISIONED';
        const config = await getConfig(deviceId);
        const ledChannelsPath = getLedChannelsPath();
        const ledChannelsExists = fs.existsSync(ledChannelsPath);
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
                num_players: 2,
                device_id: resolveRequestDeviceId(req) || 'UNPROVISIONED'
            }
        });
    }
});

router.get('/num_players', async (req, res) => {
    try {
        const deviceId = resolveRequestDeviceId(req) || 'UNPROVISIONED';
        const config = await getConfig(deviceId);

        res.json({
            num_players: config.num_players || 2
        });

    } catch (error) {
        res.json({
            num_players: 2
        });
    }
});

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

router.get('/wizard/state', (req, res) => {
    res.json({
        success: true,
        ...wizard.getState()
    });
});

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

router.post('/wizard/cancel', (req, res) => {
    try {
        const result = wizard.cancel();
        res.json({ success: true, ...result });
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

router.get('/wizard/speaking', (req, res) => {
    res.json({ success: true, speaking: speakingModeActive });
});

router.post('/lighting/speaking', (req, res) => {
    try {
        const enabled = Boolean(req.body?.enabled);
        speakingMode(enabled);
        speakingModeActive = enabled;
        res.json({ success: true, speaking: speakingModeActive });
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

export default router;
