/**
 * RemoteConfigService - Gateway service for fetching cabinet configuration from Supabase
 * Part of: Gem-Agent Refactor Phase 2
 * 
 * Provides 5-minute TTL cache for AI model and feature flag configuration.
 * Falls back to environment defaults if Supabase is unavailable.
 */

import { getClient } from './supabase_client.js';

// Cache configuration
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes
const configCache = new Map();

// Default configuration (fallback when Supabase unavailable)
const DEFAULT_CONFIG = {
    ai_model: process.env.LAUNCHBOX_FORCE_CLAUDE === 'true'
        ? 'claude-3-5-sonnet-20241022'
        : 'gemini-2.0-flash',
    fallback_models: ['claude-3-5-sonnet-20241022', 'gpt-4o-mini'],
    feature_flags: {}
};

/**
 * Get cached config entry if valid
 * @param {string} deviceId 
 * @returns {object|null}
 */
function getCached(deviceId) {
    const entry = configCache.get(deviceId);
    if (!entry) return null;

    const now = Date.now();
    if (now - entry.fetchedAt > CACHE_TTL_MS) {
        configCache.delete(deviceId);
        return null;
    }

    return entry.config;
}

/**
 * Fetch configuration from Supabase cabinet_config table
 * @param {string} deviceId - UUID of the device
 * @returns {Promise<object>} Configuration object
 */
async function fetchConfig(deviceId) {
    const client = getClient();

    if (!client) {
        console.log('[RemoteConfig] Supabase not available, using defaults');
        return { ...DEFAULT_CONFIG };
    }

    try {
        const { data, error } = await client
            .from('cabinet_config')
            .select('ai_model, fallback_models, feature_flags')
            .eq('device_id', deviceId)
            .maybeSingle();

        if (error) {
            console.error('[RemoteConfig] Fetch error:', error.message);
            return { ...DEFAULT_CONFIG };
        }

        if (!data) {
            // No config row for this device, use defaults
            console.log(`[RemoteConfig] No config for device ${deviceId}, using defaults`);
            return { ...DEFAULT_CONFIG };
        }

        // Parse fallback_models if it's a string
        let fallbackModels = data.fallback_models;
        if (typeof fallbackModels === 'string') {
            try {
                fallbackModels = JSON.parse(fallbackModels);
            } catch (e) {
                fallbackModels = DEFAULT_CONFIG.fallback_models;
            }
        }

        return {
            ai_model: data.ai_model || DEFAULT_CONFIG.ai_model,
            fallback_models: Array.isArray(fallbackModels) ? fallbackModels : DEFAULT_CONFIG.fallback_models,
            feature_flags: data.feature_flags || {}
        };
    } catch (error) {
        console.error('[RemoteConfig] Exception:', error.message);
        return { ...DEFAULT_CONFIG };
    }
}

/**
 * Get configuration for a device (with caching)
 * @param {string} deviceId - UUID of the device
 * @returns {Promise<object>} Configuration object
 */
export async function getConfig(deviceId) {
    if (!deviceId) {
        return { ...DEFAULT_CONFIG };
    }

    // Check cache first
    const cached = getCached(deviceId);
    if (cached) {
        return cached;
    }

    // Fetch from Supabase
    const config = await fetchConfig(deviceId);

    // Cache the result
    configCache.set(deviceId, {
        config,
        fetchedAt: Date.now()
    });

    return config;
}

/**
 * Get the AI model for a device
 * @param {string} deviceId - UUID of the device
 * @returns {Promise<string>} Model identifier (e.g., 'gemini-2.0-flash')
 */
export async function getModel(deviceId) {
    const config = await getConfig(deviceId);
    return config.ai_model;
}

/**
 * Get fallback models for a device
 * @param {string} deviceId - UUID of the device
 * @returns {Promise<string[]>} Array of fallback model identifiers
 */
export async function getFallbackModels(deviceId) {
    const config = await getConfig(deviceId);
    return config.fallback_models;
}

/**
 * Check if a feature flag is enabled for a device
 * @param {string} deviceId - UUID of the device
 * @param {string} flagName - Name of the feature flag
 * @returns {Promise<boolean>} Whether the flag is enabled
 */
export async function isFeatureEnabled(deviceId, flagName) {
    const config = await getConfig(deviceId);
    return Boolean(config.feature_flags?.[flagName]);
}

/**
 * Invalidate cached config for a device
 * @param {string} deviceId - UUID of the device
 */
export function invalidateCache(deviceId) {
    if (deviceId) {
        configCache.delete(deviceId);
    }
}

/**
 * Clear all cached configurations
 */
export function clearCache() {
    configCache.clear();
}

export default {
    getConfig,
    getModel,
    getFallbackModels,
    isFeatureEnabled,
    invalidateCache,
    clearCache
};
