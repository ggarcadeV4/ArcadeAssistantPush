/**
 * aa-sam Gem - ScoreKeeper Sam Entry Point
 * Part of: Phase 4 Sam Gem Pivot
 * 
 * Provides identity hydration from Supabase sessions and score deduplication.
 * Fixes the Identity Source Mismatch by pulling active_player from Supabase
 * instead of local active_session.json.
 * 
 * REDLINES (from GEMS_PIVOT_VIGILANCE.md):
 * - DO NOT modify ledwiz_driver.py SUPPORTED_IDS
 * - DO NOT modify mame_config_generator.py JOYCODE logic
 * - MUST preserve /api/scores/mame contract
 * - MUST preserve /api/scorekeeper/broadcast contract
 */

import { getActivePlayer, setActivePlayer } from '../aa-lora/session_store.js';
import { isDuplicate, recordScoreHash } from './dedup.js';
import { hydratePlayerFromSession } from './identity.js';

// Re-export for convenience
export { getActivePlayer, setActivePlayer };
export { isDuplicate, recordScoreHash };
export { hydratePlayerFromSession };

/**
 * Gem metadata
 */
export const gemInfo = {
    name: 'aa-sam',
    version: '1.0.0',
    description: 'ScoreKeeper Sam - Identity hydration and score deduplication',
    author: 'Arcade Assistant',
    created: '2026-02-03',
    phase: 'Phase 4 Sam Gem Pivot'
};

/**
 * Get player information for score attribution
 * Uses Supabase session active_player, falls back to defaults
 * 
 * @param {string} deviceId - Device identifier
 * @returns {Promise<object>} Player info { player_name, player_id, initials }
 */
export async function getPlayerForScore(deviceId) {
    const activePlayer = await getActivePlayer(deviceId);

    if (activePlayer && activePlayer.player_name) {
        return {
            player_name: activePlayer.player_name,
            player_id: activePlayer.player_id || null,
            initials: activePlayer.initials || activePlayer.player_name.substring(0, 3).toUpperCase(),
            source: 'supabase_session'
        };
    }

    // Fallback to unknown
    return {
        player_name: 'Unknown',
        player_id: null,
        initials: '???',
        source: 'fallback'
    };
}

/**
 * Check if a score should be recorded (not a duplicate)
 * 
 * @param {string} rom - ROM name
 * @param {number} score - Score value
 * @param {string} playerName - Player name
 * @returns {Promise<boolean>} True if score should be recorded
 */
export async function shouldRecordScore(rom, score, playerName) {
    const duplicate = await isDuplicate(rom, score, playerName);
    return !duplicate;
}

// =============================================================================
// TOURNAMENT MONITOR - Sam's Real-Time Tournament Eyes
// =============================================================================

import fs from 'fs';
import path from 'path';

/** @type {fs.FSWatcher|null} */
let tournamentWatcher = null;

/** @type {Array<Function>} */
const matchResultCallbacks = [];

/**
 * Get the match results file path (DRIVE_ROOT based)
 * @returns {string} Path to match_results.json
 */
function getMatchResultsPath() {
    const driveRoot = process.env.AA_DRIVE_ROOT || 'A:\\';
    return path.join(driveRoot, '.aa', 'state', 'scorekeeper', 'match_results.json');
}

/**
 * Register a callback to be notified of match results
 * @param {Function} callback - Function called with match result data
 */
export function onMatchResult(callback) {
    matchResultCallbacks.push(callback);
}

/**
 * Correlate match result with active player from Supabase session
 * Ensures the win is attributed to the correct player
 * 
 * @param {Object} matchResult - Raw match result from MAME plugin
 * @param {string} deviceId - Device identifier
 * @returns {Promise<Object>} Enriched match result with player identity
 */
// TODO: Replace CAB-0001 with cabinet UUID from env or request context
// before enabling this monitor in production fleet deployment.
export async function correlateMatchWithPlayer(matchResult, deviceId = 'CAB-0001') {
    const activePlayer = await getActivePlayer(deviceId);

    return {
        ...matchResult,
        attributed_player: activePlayer?.player_name || matchResult.winner_name,
        attributed_player_id: activePlayer?.player_id || null,
        attribution_source: activePlayer?.player_name ? 'supabase_session' : 'mame_plugin',
        correlated_at: new Date().toISOString()
    };
}

/**
 * Start the tournament monitor - watches match_results.json for changes
 * When a match result is detected, correlates with active player and notifies callbacks
 * 
 * @param {string} [deviceId='CAB-0001'] - Device identifier for player correlation
 * @returns {Object} Monitor status { running, path }
 */
// TODO: Replace CAB-0001 with cabinet UUID from env or request context
// before enabling this monitor in production fleet deployment.
export function startTournamentMonitor(deviceId = 'CAB-0001') {
    if (tournamentWatcher) {
        console.log('[Sam Tournament] Monitor already running');
        return { running: true, path: getMatchResultsPath() };
    }

    const matchResultsPath = getMatchResultsPath();
    const watchDir = path.dirname(matchResultsPath);

    // Ensure directory exists
    try {
        fs.mkdirSync(watchDir, { recursive: true });
    } catch (e) {
        // Directory may already exist
    }

    let lastMtime = 0;

    try {
        // Watch the directory, filter for match_results.json changes
        tournamentWatcher = fs.watch(watchDir, async (eventType, filename) => {
            if (filename !== 'match_results.json') return;
            if (eventType !== 'change') return;

            try {
                const stats = fs.statSync(matchResultsPath);
                const mtime = stats.mtimeMs;

                // Debounce: only process if file actually changed
                if (mtime <= lastMtime) return;
                lastMtime = mtime;

                const content = fs.readFileSync(matchResultsPath, 'utf-8');
                const matchResult = JSON.parse(content);

                console.log(`[Sam Tournament] Match detected: ${matchResult.winner_name} wins!`);

                // Correlate with active player
                const enrichedResult = await correlateMatchWithPlayer(matchResult, deviceId);

                // Notify all callbacks (for Big Board, WebSocket broadcast, etc.)
                for (const callback of matchResultCallbacks) {
                    try {
                        await callback(enrichedResult);
                    } catch (cbError) {
                        console.error('[Sam Tournament] Callback error:', cbError);
                    }
                }
            } catch (parseError) {
                console.error('[Sam Tournament] Parse error:', parseError.message);
            }
        });

        console.log(`[Sam Tournament] Monitor started, watching: ${matchResultsPath}`);
        console.log('[Sam Tournament] 🎮 Connected to MAME memory hook. Ready to detect match results!');

        return { running: true, path: matchResultsPath };

    } catch (err) {
        console.error('[Sam Tournament] Failed to start monitor:', err);
        return { running: false, error: err.message };
    }
}

/**
 * Stop the tournament monitor
 */
export function stopTournamentMonitor() {
    if (tournamentWatcher) {
        tournamentWatcher.close();
        tournamentWatcher = null;
        console.log('[Sam Tournament] Monitor stopped');
    }
}

/**
 * Get tournament monitor status
 * @returns {Object} Status { running, path }
 */
export function getTournamentMonitorStatus() {
    return {
        running: !!tournamentWatcher,
        path: getMatchResultsPath(),
        callbackCount: matchResultCallbacks.length
    };
}

export default {
    gemInfo,
    getActivePlayer,
    setActivePlayer,
    getPlayerForScore,
    shouldRecordScore,
    isDuplicate,
    recordScoreHash,
    hydratePlayerFromSession,
    // Tournament functions
    startTournamentMonitor,
    stopTournamentMonitor,
    getTournamentMonitorStatus,
    onMatchResult,
    correlateMatchWithPlayer
};
