/**
 * Fast-Path Module - Regex patterns for bypass AI on simple launch commands
 * Part of: aa-lora gem (Gem-Agent Refactor)
 * 
 * Extracted from launchboxAI.js lines 440-700
 * 
 * This module bypasses AI for ~70% of requests, saving ~$0.001 per launch.
 * Uses dependency injection - does not access req directly.
 * 
 * REDLINES: 
 * - API contract maintained via createResponse() in index.js
 * - Does NOT touch ledwiz_driver.py or MAME JOYCODE logic
 */

import { parseRequestedGame, normalizeTitleForMatch, formatCandidateList } from './parsers.js';
import { sessionStore } from './session_store.js';
import { fetchWithRetry } from '../../lib/http.js';

/**
 * Context object for fast-path operations (dependency injection)
 * @typedef {Object} FastPathContext
 * @property {string} backendUrl - FastAPI backend URL
 * @property {string} deviceId - Device identifier from x-device-id header
 * @property {Object} identityHeaders - Headers for user identity (x-user-profile, x-user-name, x-session-owner)
 * @property {string} [profileId] - Optional user profile ID for favorites lookup
 */

/**
 * Fast-path regex patterns for extracting game name from conversational input
 * Bypasses AI for simple launch commands
 */
export const FAST_PATH_PATTERNS = {
    // Pattern 1: Direct commands ("launch X", "play X", "start X")
    direct: /(?:can you |please |could you |would you )?(?:launch|play|start|run)\s+(.+?)(?:\s+please)?$/i,

    // Pattern 2: "I want to play X"
    wantToPlay: /(?:i want to|i'd like to|let's|how about)\s+(?:play|launch|start)?\s*(.+?)(?:\s+please)?$/i,

    // Pattern 3: Conversational "X can you help" or "how about X"
    helpRequest: /(.+?)\s+(?:can you help|please|thanks)$/i,

    // Pattern 4: "how about X" at the start
    howAbout: /^(?:how about|what about)\s+(.+?)(?:\s+please)?$/i,

    // Relaunch pattern
    relaunch: /^(?:re\s*-?launch|launch\s+again|play\s+again|start\s+again)\s*(?:please)?\s*$/i
};

/**
 * Check if message is a relaunch request
 * @param {string} msg - Lowercase trimmed message
 * @returns {boolean}
 */
export function isRelaunchRequest(msg) {
    return FAST_PATH_PATTERNS.relaunch.test(msg);
}

/**
 * Extract game name from user message using fast-path patterns
 * @param {string} msgRaw - Raw user message
 * @returns {{ gameName: string|null, platformHint: string|null, yearHint: number|null }}
 */
export function extractGameName(msgRaw) {
    const msg = (msgRaw || '').toString().trim().toLowerCase();
    let gameName = null;
    let platformHint = null;
    let yearHint = null;

    // Pattern 1: Direct commands
    const directMatch = msg.match(FAST_PATH_PATTERNS.direct);
    if (directMatch) {
        gameName = directMatch[1].trim();
    }

    // Pattern 2: "I want to play X"
    if (!gameName) {
        const wantMatch = msg.match(FAST_PATH_PATTERNS.wantToPlay);
        if (wantMatch) {
            gameName = wantMatch[1].trim();
        }
    }

    // Pattern 3: Conversational "X can you help"
    if (!gameName) {
        const helpMatch = msg.match(FAST_PATH_PATTERNS.helpRequest);
        if (helpMatch) {
            const candidate = helpMatch[1].replace(/^(?:i want to play|i went to play|how about)\s+/i, '').trim();
            if (candidate && !candidate.includes('show') && !candidate.includes('find')) {
                gameName = candidate;
            }
        }
    }

    // Pattern 4: "how about X"
    if (!gameName) {
        const howAboutMatch = msg.match(FAST_PATH_PATTERNS.howAbout);
        if (howAboutMatch) {
            gameName = howAboutMatch[1].trim();
        }
    }

    // Parse and clean up game name
    if (gameName) {
        const parsed = parseRequestedGame(gameName);
        gameName = parsed.title;
        platformHint = parsed.platform;
        yearHint = parsed.year;

        gameName = gameName
            .replace(/^(?:the|a|an)\s+/i, '')
            .replace(/\s+(?:game|please|thanks|thank you|again)$/i, '')
            .trim();

        // Skip if it looks like a complex query (not a game name)
        if (gameName.includes('?') || gameName.includes('show me') || gameName.includes('find me') ||
            gameName.includes('what') || gameName.includes('which') || gameName.length > 60 ||
            gameName.split(' ').length > 8) {
            gameName = null;
        }
    }

    return { gameName, platformHint, yearHint };
}

/**
 * Check user's favorite games for instant match
 * @param {FastPathContext} ctx - Context object
 * @param {string} gameName - Game name to check
 * @returns {Promise<string>} Updated game name (may be exact favorite match)
 */
async function checkFavorites(ctx, gameName) {
    if (!ctx.profileId) return gameName;

    try {
        // This would need the protocol and host - simplified for gem extraction
        // In practice, favorites lookup happens at the route level
        return gameName;
    } catch (err) {
        return gameName;
    }
}

/**
 * Resolve game name to game ID via /api/launchbox/resolve
 * @param {FastPathContext} ctx - Context object
 * @param {string} gameName - Game name to resolve
 * @param {string|null} platformHint - Platform filter
 * @param {number|null} yearHint - Year filter
 * @returns {Promise<Object>} Resolve response data
 */
export async function resolveGame(ctx, gameName, platformHint = null, yearHint = null) {
    const { backendUrl, deviceId, identityHeaders = {} } = ctx;

    const resolveResp = await fetchWithRetry(`${backendUrl}/api/launchbox/resolve`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-panel': 'launchbox',
            'x-device-id': deviceId || 'unknown',
            ...identityHeaders
        },
        body: JSON.stringify({
            title: gameName,
            platform: platformHint || undefined,
            year: Number.isFinite(yearHint) ? yearHint : undefined,
            limit: 25
        })
    });

    return resolveResp.json().catch(() => ({}));
}

/**
 * Launch a game by ID
 * @param {FastPathContext} ctx - Context object
 * @param {string} gameId - Game ID to launch
 * @returns {Promise<Object>} Launch response data
 */
export async function launchGame(ctx, gameId) {
    const { backendUrl, deviceId, identityHeaders = {} } = ctx;

    const launchResp = await fetch(`${backendUrl}/api/launchbox/launch/${gameId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-panel': 'launchbox',
            'x-device-id': deviceId || 'unknown',
            ...identityHeaders
        }
    });

    return launchResp.json().catch(() => ({}));
}

/**
 * Handle relaunch request
 * @param {FastPathContext} ctx - Context object
 * @param {Object} session - Session object
 * @returns {Promise<Object|null>} Response object or null if can't relaunch
 */
export async function handleRelaunch(ctx, session) {
    if (!session.lastLaunchedGameId) {
        return {
            success: true,
            response: 'Tell me the game title to launch.',
            rounds: 0,
            game_launched: false
        };
    }

    try {
        const launchData = await launchGame(ctx, session.lastLaunchedGameId);
        if (launchData.success) {
            session.pendingLaunch = null;
            session.lastCandidates = [];
            session.lastLaunchedAt = Date.now();
            const title = session.lastLaunchedTitle || launchData.game_title || 'that game';
            return {
                success: true,
                response: `🎮 Launching ${title}!`,
                rounds: 0,
                game_launched: true
            };
        }
    } catch (_) {
        // Fall through to AI
    }

    return null;
}

/**
 * Process fast-path game launch
 * @param {FastPathContext} ctx - Context object
 * @param {Object} session - Session object
 * @param {string} gameName - Game name to launch
 * @param {string|null} platformHint - Platform filter
 * @param {number|null} yearHint - Year filter
 * @returns {Promise<Object|null>} Response object or null to fall through to AI
 */
export async function processFastPathLaunch(ctx, session, gameName, platformHint, yearHint) {
    console.log(`[LaunchBox AI] Fast path: Direct launch for "${gameName}"`);

    // Clear stale pending launch if title changed
    if (session.pendingLaunch && normalizeTitleForMatch(session.pendingLaunch.requestedTitle) !== normalizeTitleForMatch(gameName)) {
        session.pendingLaunch = null;
    }

    try {
        const resolveData = await resolveGame(ctx, gameName, platformHint, yearHint);
        const requestedNorm = normalizeTitleForMatch(gameName);

        // Handle array of candidates
        if (resolveData && Array.isArray(resolveData.candidates) && resolveData.candidates.length > 0) {
            session.chatState = 'PENDING_SELECTION';
            const pool = resolveData.candidates;
            const shown = pool.slice(0, 5);
            session.pendingLaunch = {
                requestedTitle: gameName,
                candidates: shown,
                originalCandidates: pool,
                createdAt: Date.now()
            };
            const preview = formatCandidateList(pool, 5);
            return {
                success: true,
                response: `I found a few matches for "${gameName}". Reply with the number to launch:\n${preview}`,
                rounds: 0,
                game_launched: false
            };
        }

        // Handle direct array response
        if (Array.isArray(resolveData) && resolveData.length > 0) {
            session.chatState = 'PENDING_SELECTION';
            const pool = resolveData;
            const shown = pool.slice(0, 5);
            session.pendingLaunch = {
                requestedTitle: gameName,
                candidates: shown,
                originalCandidates: pool,
                createdAt: Date.now()
            };
            const preview = formatCandidateList(pool, 5);
            return {
                success: true,
                response: `I found a few matches for "${gameName}". Reply with the number to launch:\n${preview}`,
                rounds: 0,
                game_launched: false
            };
        }

        // Handle exact resolved game
        if (resolveData && resolveData.status === 'resolved' && resolveData.game) {
            const resolved = resolveData.game;
            const resolvedNorm = normalizeTitleForMatch(resolved.title);

            // Only auto-launch on exact match
            if (resolveData.source === 'cache_exact' || requestedNorm === resolvedNorm) {
                const launchData = await launchGame(ctx, resolved.id);
                if (launchData.success) {
                    session.pendingLaunch = null;
                    session.lastLaunchedGameId = resolved.id;
                    session.lastLaunchedTitle = resolved.title || launchData.game_title || session.lastLaunchedTitle;
                    session.lastLaunchedAt = Date.now();
                    return {
                        success: true,
                        response: `🎮 Launching ${resolved.title}!`,
                        rounds: 0,
                        game_launched: true
                    };
                }
            }

            // Not exact: ask for confirmation
            session.chatState = 'PENDING_SELECTION';
            session.pendingLaunch = {
                requestedTitle: gameName,
                candidates: [resolved],
                originalCandidates: [resolved],
                createdAt: Date.now()
            };
            return {
                success: true,
                response: `I found "${resolved.title}" for "${gameName}". Reply "1" to launch, or refine (e.g., "the arcade version").`,
                rounds: 0,
                game_launched: false
            };
        }

        // Handle multiple matches
        if (resolveData && resolveData.status === 'multiple_matches' && Array.isArray(resolveData.suggestions)) {
            session.chatState = 'PENDING_SELECTION';
            const pool = resolveData.suggestions;
            const shown = pool.slice(0, 5);
            session.pendingLaunch = {
                requestedTitle: gameName,
                candidates: shown,
                originalCandidates: pool,
                createdAt: Date.now()
            };
            const preview = formatCandidateList(pool, 5);
            return {
                success: true,
                response: `I found a few matches for "${gameName}". Reply with the number to launch:\n${preview}`,
                rounds: 0,
                game_launched: false
            };
        }

        // No matches found - fall through to AI
        return null;
    } catch (error) {
        console.error('[LaunchBox AI] Fast path error:', error.message);
        return null;
    }
}

export default {
    FAST_PATH_PATTERNS,
    isRelaunchRequest,
    extractGameName,
    resolveGame,
    launchGame,
    handleRelaunch,
    processFastPathLaunch
};
