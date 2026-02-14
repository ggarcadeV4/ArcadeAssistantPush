/**
 * Score Deduplication Module - Idempotency guard for score recording
 * Part of: aa-sam gem (Phase 4 Sam Gem Pivot)
 * 
 * Prevents duplicate scores from being recorded to cabinet_game_score.
 * Uses a combination of ROM + Score + Player Name as the dedup key.
 * 
 * Approach:
 * 1. Generate a hash from (rom, score, playerName)
 * 2. Check if hash exists in recent records (in-memory cache + Supabase query)
 * 3. If exists, reject as duplicate
 * 4. If new, record hash and allow score
 */

import { getClient } from '../../services/supabase_client.js';

// In-memory cache of recent score hashes (fast reject for immediate duplicates)
const recentHashes = new Map();
const HASH_TTL_MS = 5 * 60 * 1000; // 5 minutes

/**
 * Generate a dedup hash from score components
 * 
 * @param {string} rom - ROM name (case-insensitive)
 * @param {number} score - Score value
 * @param {string} playerName - Player name (case-insensitive)
 * @returns {string} Hash string
 */
export function generateScoreHash(rom, score, playerName) {
    const normalizedRom = String(rom || '').trim().toLowerCase();
    const normalizedScore = Number(score) || 0;
    const normalizedPlayer = String(playerName || '???').trim().toLowerCase();

    return `${normalizedRom}:${normalizedScore}:${normalizedPlayer}`;
}

/**
 * Check if a score is a duplicate (recently recorded)
 * 
 * @param {string} rom - ROM name
 * @param {number} score - Score value
 * @param {string} playerName - Player name
 * @returns {Promise<boolean>} True if duplicate
 */
export async function isDuplicate(rom, score, playerName) {
    const hash = generateScoreHash(rom, score, playerName);

    // Check in-memory cache first (fast path)
    const cached = recentHashes.get(hash);
    if (cached) {
        const age = Date.now() - cached.timestamp;
        if (age < HASH_TTL_MS) {
            console.log(`[Sam Dedup] Duplicate found in cache: ${hash}`);
            return true;
        }
        // Expired, remove from cache
        recentHashes.delete(hash);
    }

    // Check Supabase for recent score with same hash
    const client = getClient();
    if (client) {
        try {
            const fiveMinutesAgo = new Date(Date.now() - HASH_TTL_MS).toISOString();

            const { data, error } = await client
                .from('cabinet_game_score')
                .select('id')
                .eq('game_rom', rom.toLowerCase())
                .eq('score', score)
                .ilike('player', playerName)
                .gte('created_at', fiveMinutesAgo)
                .limit(1);

            if (!error && data && data.length > 0) {
                console.log(`[Sam Dedup] Duplicate found in Supabase: ${hash}`);
                // Cache it to avoid future DB lookups
                recentHashes.set(hash, { timestamp: Date.now() });
                return true;
            }
        } catch (err) {
            console.warn('[Sam Dedup] Supabase check failed:', err.message);
            // Fall through - allow score if we can't check
        }
    }

    return false;
}

/**
 * Record a score hash to prevent future duplicates
 * Call this after successfully writing a score
 * 
 * @param {string} rom - ROM name
 * @param {number} score - Score value
 * @param {string} playerName - Player name
 */
export function recordScoreHash(rom, score, playerName) {
    const hash = generateScoreHash(rom, score, playerName);
    recentHashes.set(hash, { timestamp: Date.now() });

    // Cleanup old hashes periodically
    if (recentHashes.size > 1000) {
        const now = Date.now();
        for (const [key, value] of recentHashes.entries()) {
            if (now - value.timestamp > HASH_TTL_MS) {
                recentHashes.delete(key);
            }
        }
    }
}

/**
 * Clear all cached hashes (for testing)
 */
export function clearHashCache() {
    recentHashes.clear();
}

export default {
    generateScoreHash,
    isDuplicate,
    recordScoreHash,
    clearHashCache
};
