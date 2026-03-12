/**
 * Scoring Middleware - Sam Gem Integration Layer
 * Part of: Phase 4 Sam Gem Pivot (Task 4.3)
 *
 * This middleware wraps score submission to:
 * 1. Hydrate player identity from Supabase session (replaces local active_session.json)
 * 2. Check for duplicate scores before recording
 * 3. Preserve API contract for /api/scores/* and /api/scorekeeper/broadcast
 *
 * REDLINES (from GEMS_PIVOT_VIGILANCE.md):
 * - Response shape for /api/scores/mame MUST remain identical
 * - Broadcast format for /api/scorekeeper/broadcast MUST remain identical
 */

import {
    getPlayerForScore,
    shouldRecordScore,
    recordScoreHash
} from '../gems/aa-sam/index.js';
import { hydrateScoreEntry } from '../gems/aa-sam/identity.js';
import { resolveRequestDeviceId } from '../utils/cabinetIdentity.js';

export async function injectPlayerIdentity(req, res, next) {
    const deviceId = resolveRequestDeviceId(req) || 'UNPROVISIONED';

    try {
        const player = await getPlayerForScore(deviceId);
        req.samPlayer = player;
        console.log(`[Sam Middleware] Player identity: ${player.player_name} (${player.source})`);
    } catch (err) {
        console.warn('[Sam Middleware] Identity hydration failed:', err.message);
        req.samPlayer = {
            player_name: 'Unknown',
            player_id: null,
            initials: '???',
            source: 'fallback'
        };
    }

    next();
}

export async function checkScoreDuplicate(req, res, next) {
    const scoreData = req.body;

    if (!scoreData || !scoreData.game_rom || scoreData.score === undefined) {
        return next();
    }

    const rom = scoreData.game_rom;
    const score = scoreData.score;
    const playerName = scoreData.player || req.samPlayer?.player_name || 'Unknown';

    try {
        const shouldRecord = await shouldRecordScore(rom, score, playerName);

        if (!shouldRecord) {
            console.log(`[Sam Middleware] Duplicate score rejected: ${rom} ${score} ${playerName}`);
            return res.status(200).json({
                success: true,
                skipped: true,
                reason: 'duplicate_score',
                message: 'Score already recorded within the last 5 minutes'
            });
        }

        req.samRecordHash = { rom, score, playerName };

    } catch (err) {
        console.warn('[Sam Middleware] Dedup check failed:', err.message);
    }

    next();
}

export function recordScoreAfterWrite(req, res, next) {
    const originalJson = res.json.bind(res);

    res.json = function (data) {
        if (req.samRecordHash && data && (data.success === true || res.statusCode === 200)) {
            const { rom, score, playerName } = req.samRecordHash;
            recordScoreHash(rom, score, playerName);
            console.log(`[Sam Middleware] Recorded hash: ${rom}:${score}:${playerName}`);
        }
        return originalJson(data);
    };

    next();
}

export async function hydrateScoreEntries(entries, deviceId) {
    if (!Array.isArray(entries) || entries.length === 0) {
        return entries;
    }

    const hydrated = [];
    for (const entry of entries) {
        const hydEntry = await hydrateScoreEntry(entry, deviceId);
        hydrated.push(hydEntry);
    }

    return hydrated;
}

export default {
    injectPlayerIdentity,
    checkScoreDuplicate,
    recordScoreAfterWrite,
    hydrateScoreEntries
};
