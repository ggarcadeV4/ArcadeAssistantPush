/**
 * aa-lora Gem - Main Entry Point
 * Part of: Gem-Agent Refactor Phase 3
 * 
 * This gem encapsulates the LoRa AI assistant logic extracted from launchboxAI.js.
 * It maintains the public-stable API contract: { success, response, rounds, game_launched }
 * 
 * REDLINES (from GEMS_PIVOT_VIGILANCE.md):
 * - DO NOT modify ledwiz_driver.py SUPPORTED_IDS
 * - DO NOT modify mame_pergame_generator.py XINPUT_CLEAN_MAP
 * - DO NOT modify mame_config_generator.py JOYCODE logic
 * - DO NOT modify config/mappings/controls.json schema
 * - MUST maintain API contract keys: success, response, rounds, game_launched
 */

import { sessionStore } from './session_store.js';
import { getModel, getFallbackModels, isFeatureEnabled } from '../../services/remote_config.js';
import { executeToolCallingLoop } from './tool_loop.js';
import { executeManageShader } from './shader_handler.js';

// Re-export session store for use by launchboxAI.js during migration
export { sessionStore };

/**
 * API Response structure - maintains GUI compatibility
 * @typedef {Object} LoRaResponse
 * @property {boolean} success - Whether the request was processed successfully
 * @property {string} response - The text response to display
 * @property {number} rounds - Number of AI conversation rounds used
 * @property {boolean} game_launched - Whether a game was launched
 */

/**
 * Create a standardized LoRa response
 * Ensures API contract is always maintained
 * 
 * @param {object} options
 * @param {boolean} [options.success=true]
 * @param {string} options.response
 * @param {number} [options.rounds=0]
 * @param {boolean} [options.game_launched=false]
 * @returns {LoRaResponse}
 */
export function createResponse({
    success = true,
    response,
    rounds = 0,
    game_launched = false
}) {
    // HARD CONSTRAINT: These four keys MUST be present in every response
    return {
        success: Boolean(success),
        response: String(response || ''),
        rounds: Number(rounds) || 0,
        game_launched: Boolean(game_launched)
    };
}

/**
 * Get session key from request
 * @param {import('express').Request} req
 * @returns {string}
 */
export function getSessionKey(req) {
    return (req.headers['x-device-id'] || req.ip || 'anon').toString();
}

/**
 * Get session for a request (async, Supabase-backed)
 * @param {import('express').Request} req
 * @returns {Promise<object>}
 */
export async function getSession(req) {
    const key = getSessionKey(req);
    return sessionStore.get(key);
}

/**
 * Save session for a request
 * @param {import('express').Request} req
 * @param {object} session
 * @returns {Promise<boolean>}
 */
export async function saveSession(req, session) {
    const key = getSessionKey(req);
    return sessionStore.set(key, session);
}

/**
 * Clear session for a request
 * @param {import('express').Request} req
 * @returns {Promise<boolean>}
 */
export async function clearSession(req) {
    const key = getSessionKey(req);
    return sessionStore.clear(key);
}

/**
 * Get AI model configuration for request
 * @param {import('express').Request} req
 * @returns {Promise<{model: string, fallbacks: string[]}>}
 */
export async function getAIConfig(req) {
    const deviceId = req.headers['x-device-id'] || process.env.AA_DEVICE_ID;

    const model = await getModel(deviceId);
    const fallbacks = await getFallbackModels(deviceId);

    return { model, fallbacks };
}

/**
 * Check if a feature is enabled for request
 * @param {import('express').Request} req
 * @param {string} flagName
 * @returns {Promise<boolean>}
 */
export async function checkFeature(req, flagName) {
    const deviceId = req.headers['x-device-id'] || process.env.AA_DEVICE_ID;
    return isFeatureEnabled(deviceId, flagName);
}

// Constants for session state
export const SessionState = {
    IDLE: 'IDLE',
    PENDING_SELECTION: 'PENDING_SELECTION',
    AWAITING_CONFIRMATION: 'AWAITING_CONFIRMATION'
};

// Session TTL values (matching launchboxAI.js)
export const SESSION_TTL_MS = 10 * 60 * 1000; // 10 minutes
export const PENDING_SELECTION_TTL_MS = 3 * 60 * 1000; // 3 minutes

/**
 * Invoke the LoRa AI tool loop
 * Main entry point for the gem - used by skinny controller in launchboxAI.js
 * 
 * @param {Object} options
 * @param {string} options.systemPrompt - System prompt for AI
 * @param {Array} options.messages - Conversation messages
 * @param {Object} options.toolEnv - Tool environment { backendUrl, headers, tools, callAI }
 * @param {Function} [options.onTelemetry] - Optional telemetry callback
 * @returns {Promise<Object>} Tool loop result with { finalText, toolCallsMade, rounds, gameLaunched, ... }
 */
export async function invoke({ systemPrompt, messages, toolEnv, onTelemetry }) {
    const result = await executeToolCallingLoop(systemPrompt, messages, toolEnv);

    // Fire telemetry callback if provided (dependency injection pattern)
    if (typeof onTelemetry === 'function') {
        try {
            onTelemetry(result);
        } catch (err) {
            console.warn('[LoRa] Telemetry callback failed:', err.message);
        }
    }

    return result;
}

// Re-export tool loop for direct access if needed
export { executeToolCallingLoop };
export { executeManageShader };

/**
 * Gem metadata
 */
export const gemInfo = {
    name: 'aa-lora',
    version: '2.0.0',
    description: 'LoRa AI Assistant for LaunchBox game discovery and launching',
    author: 'Arcade Assistant',
    created: '2026-02-03',
    transplantDate: '2026-02-03'
};

export default {
    sessionStore,
    createResponse,
    getSessionKey,
    getSession,
    saveSession,
    clearSession,
    getAIConfig,
    checkFeature,
    invoke,
    executeToolCallingLoop,
    SessionState,
    SESSION_TTL_MS,
    PENDING_SELECTION_TTL_MS,
    gemInfo
};
