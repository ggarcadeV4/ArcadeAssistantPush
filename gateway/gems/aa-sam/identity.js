/**
 * Identity Hydration Module - Supabase session-based player identity
 * Part of: aa-sam gem (Phase 4 Sam Gem Pivot)
 * 
 * Replaces the local active_session.json lookup in hiscore_watcher.py
 * with Supabase session-based identity.
 * 
 * Before: get_active_session() -> reads from local active_session.json
 * After:  hydratePlayerFromSession() -> reads from Supabase aa_lora_sessions.active_player
 */

import { getActivePlayer } from '../aa-lora/session_store.js';

/**
 * Hydrate player information from Supabase session
 * This is the replacement for the Python get_active_session() call
 * 
 * @param {string} deviceId - Device identifier (from x-device-id header)
 * @returns {Promise<object|null>} Player info or null
 */
export async function hydratePlayerFromSession(deviceId) {
    if (!deviceId) {
        console.log('[Sam Identity] No deviceId provided, returning null');
        return null;
    }

    try {
        const activePlayer = await getActivePlayer(deviceId);

        if (!activePlayer) {
            console.log(`[Sam Identity] No active player for device ${deviceId}`);
            return null;
        }

        console.log(`[Sam Identity] Hydrated player: ${activePlayer.player_name} for device ${deviceId}`);

        return {
            player_name: activePlayer.player_name,
            player_id: activePlayer.player_id || null,
            initials: activePlayer.initials || null,
            source: 'supabase_session'
        };
    } catch (error) {
        console.error('[Sam Identity] Hydration error:', error.message);
        return null;
    }
}

/**
 * Check if a player name should be hydrated (unknown/empty)
 * 
 * @param {string} playerName - Current player name from score
 * @returns {boolean} True if should hydrate from session
 */
export function shouldHydratePlayer(playerName) {
    if (!playerName) return true;

    const normalized = String(playerName).trim().toLowerCase();
    const unknownValues = new Set(['', '??', '???', 'unknown', 'aaa']);

    return unknownValues.has(normalized);
}

/**
 * Hydrate a score entry with player information
 * Only hydrates if the existing player name is unknown/empty
 * 
 * @param {object} scoreEntry - Score entry to hydrate
 * @param {string} deviceId - Device identifier
 * @returns {Promise<object>} Hydrated score entry
 */
export async function hydrateScoreEntry(scoreEntry, deviceId) {
    if (!scoreEntry) return scoreEntry;

    const currentName = scoreEntry.player || scoreEntry.name || '';

    // Only hydrate if player name is unknown
    if (!shouldHydratePlayer(currentName)) {
        // Preserve existing player name (game initials like AAA, JON, etc.)
        return scoreEntry;
    }

    // Hydrate from Supabase session
    const player = await hydratePlayerFromSession(deviceId);

    if (player && player.player_name) {
        return {
            ...scoreEntry,
            player: player.player_name,
            player_userId: player.player_id,
            player_source: player.source
        };
    }

    return scoreEntry;
}

export default {
    hydratePlayerFromSession,
    shouldHydratePlayer,
    hydrateScoreEntry
};
