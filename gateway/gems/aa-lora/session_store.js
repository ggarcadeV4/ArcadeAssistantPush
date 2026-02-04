/**
 * SessionStore - Supabase-backed session persistence for LoRa AI
 * Part of: Gem-Agent Refactor Phase 2
 * 
 * Replaces the in-memory sessionStore (Map) from launchboxAI.js lines 66-135
 * with Supabase persistence for stateless cabinet operation.
 * 
 * Features:
 * - Local cache for low-latency reads
 * - Async Supabase persistence
 * - TTL enforcement via expires_at column
 * - Compatible with existing session interface
 */

import { getClient } from '../../services/supabase_client.js';

// Local cache for fast reads (avoids Supabase round-trip on every request)
const localCache = new Map();
const LOCAL_CACHE_TTL_MS = 30 * 1000; // 30 seconds local cache

// Session TTL (matches the trigger in Supabase)
const SESSION_TTL_MS = 10 * 60 * 1000; // 10 minutes

// Default session structure (matches launchboxAI.js structure)
const DEFAULT_SESSION = {
    chatState: 'IDLE',
    history: [],
    lastCandidates: [],
    lastTitle: null,
    lastPlatform: null,
    pendingLaunch: null,
    lastLaunchedGameId: null,
    lastLaunchedTitle: null,
    lastLaunchedAt: null,
    lastAccess: null,
    // Phase 4: Active player for score attribution (Sam gem identity hydration)
    activePlayer: null  // { player_name, player_id, initials }
};

/**
 * Get session from local cache if valid
 * @param {string} deviceId 
 * @returns {object|null}
 */
function getFromLocalCache(deviceId) {
    const entry = localCache.get(deviceId);
    if (!entry) return null;

    const now = Date.now();
    if (now - entry.cachedAt > LOCAL_CACHE_TTL_MS) {
        localCache.delete(deviceId);
        return null;
    }

    return entry.session;
}

/**
 * Update local cache
 * @param {string} deviceId 
 * @param {object} session 
 */
function updateLocalCache(deviceId, session) {
    localCache.set(deviceId, {
        session,
        cachedAt: Date.now()
    });
}

/**
 * SessionStore class - manages session state with Supabase persistence
 */
export class SessionStore {
    /**
     * Get session for a device
     * @param {string} deviceId - Device identifier (from x-device-id header)
     * @returns {Promise<object>} Session object
     */
    async get(deviceId) {
        if (!deviceId) {
            return { ...DEFAULT_SESSION, lastAccess: Date.now() };
        }

        // Check local cache first
        const cached = getFromLocalCache(deviceId);
        if (cached) {
            cached.lastAccess = Date.now();
            return cached;
        }

        // Try to fetch from Supabase
        const client = getClient();
        if (!client) {
            console.log('[SessionStore] Supabase not available, using ephemeral session');
            const newSession = { ...DEFAULT_SESSION, lastAccess: Date.now() };
            updateLocalCache(deviceId, newSession);
            return newSession;
        }

        try {
            const { data, error } = await client
                .from('aa_lora_sessions')
                .select('*')
                .eq('device_id', deviceId)
                .maybeSingle();

            if (error) {
                console.error('[SessionStore] Fetch error:', error.message);
                const newSession = { ...DEFAULT_SESSION, lastAccess: Date.now() };
                updateLocalCache(deviceId, newSession);
                return newSession;
            }

            if (!data) {
                // No session exists, create new one
                const newSession = { ...DEFAULT_SESSION, lastAccess: Date.now() };
                updateLocalCache(deviceId, newSession);
                return newSession;
            }

            // Check if session is expired
            if (data.expires_at && new Date(data.expires_at) < new Date()) {
                console.log(`[SessionStore] Session ${deviceId} expired, creating new`);
                const newSession = { ...DEFAULT_SESSION, lastAccess: Date.now() };
                updateLocalCache(deviceId, newSession);
                // Delete expired session in background
                this._deleteSession(deviceId).catch(() => { });
                return newSession;
            }

            // Reconstruct session from Supabase data
            const session = {
                chatState: data.chat_state || 'IDLE',
                history: Array.isArray(data.history) ? data.history : [],
                lastCandidates: data.pending_launch?.candidates || [],
                lastTitle: data.pending_launch?.requestedTitle || null,
                lastPlatform: null,
                pendingLaunch: data.pending_launch || null,
                lastLaunchedGameId: data.last_launched?.gameId || null,
                lastLaunchedTitle: data.last_launched?.title || null,
                lastLaunchedAt: data.last_launched?.launchedAt || null,
                lastAccess: Date.now(),
                // Phase 4: Active player for Sam gem identity hydration
                activePlayer: data.active_player || null
            };

            updateLocalCache(deviceId, session);
            return session;
        } catch (error) {
            console.error('[SessionStore] Exception:', error.message);
            const newSession = { ...DEFAULT_SESSION, lastAccess: Date.now() };
            updateLocalCache(deviceId, newSession);
            return newSession;
        }
    }

    /**
     * Save session for a device
     * @param {string} deviceId - Device identifier
     * @param {object} session - Session object
     * @returns {Promise<boolean>} Success status
     */
    async set(deviceId, session) {
        if (!deviceId) return false;

        // Always update local cache immediately
        session.lastAccess = Date.now();
        updateLocalCache(deviceId, session);

        // Persist to Supabase in background
        const client = getClient();
        if (!client) {
            return true; // Local cache only mode
        }

        try {
            const dbSession = {
                device_id: deviceId,
                chat_state: session.chatState || 'IDLE',
                history: session.history || [],
                pending_launch: session.pendingLaunch || null,
                last_launched: session.lastLaunchedGameId ? {
                    gameId: session.lastLaunchedGameId,
                    title: session.lastLaunchedTitle,
                    launchedAt: session.lastLaunchedAt
                } : null,
                // Phase 4: Active player for Sam gem identity hydration
                active_player: session.activePlayer || null,
                updated_at: new Date().toISOString()
                // expires_at is auto-set by trigger
            };

            const { error } = await client
                .from('aa_lora_sessions')
                .upsert(dbSession, { onConflict: 'device_id' });

            if (error) {
                console.error('[SessionStore] Save error:', error.message);
                return false;
            }

            return true;
        } catch (error) {
            console.error('[SessionStore] Save exception:', error.message);
            return false;
        }
    }

    /**
     * Clear session for a device
     * @param {string} deviceId - Device identifier
     * @returns {Promise<boolean>} Success status
     */
    async clear(deviceId) {
        if (!deviceId) return false;

        // Clear local cache
        localCache.delete(deviceId);

        // Delete from Supabase
        return this._deleteSession(deviceId);
    }

    /**
     * Delete session from Supabase
     * @private
     */
    async _deleteSession(deviceId) {
        const client = getClient();
        if (!client) return true;

        try {
            const { error } = await client
                .from('aa_lora_sessions')
                .delete()
                .eq('device_id', deviceId);

            if (error) {
                console.error('[SessionStore] Delete error:', error.message);
                return false;
            }
            return true;
        } catch (error) {
            console.error('[SessionStore] Delete exception:', error.message);
            return false;
        }
    }

    /**
     * Check if a session exists
     * @param {string} deviceId - Device identifier
     * @returns {boolean}
     */
    has(deviceId) {
        return localCache.has(deviceId);
    }
}

// Singleton instance for use across the gem
export const sessionStore = new SessionStore();

/**
 * Get active player from session (for Sam gem identity hydration)
 * @param {string} deviceId - Device identifier
 * @returns {Promise<object|null>} Active player { player_name, player_id, initials } or null
 */
export async function getActivePlayer(deviceId) {
    const session = await sessionStore.get(deviceId);
    return session?.activePlayer || null;
}

/**
 * Set active player in session (called by frontend on profile select)
 * @param {string} deviceId - Device identifier  
 * @param {object} player - { player_name, player_id, initials }
 * @returns {Promise<boolean>} Success status
 */
export async function setActivePlayer(deviceId, player) {
    const session = await sessionStore.get(deviceId);
    session.activePlayer = player;
    return sessionStore.set(deviceId, session);
}

export default sessionStore;
