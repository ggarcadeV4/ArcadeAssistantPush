/**
 * Player Tracking API Client
 * 
 * Provides functions to interact with player session management
 * and tendency tracking endpoints.
 */
import { buildStandardHeaders } from '../utils/identity'

const BASE_URL = '/api/local/scorekeeper'

/**
 * Start a player session (called by Vicky when player identified)
 */
export async function startPlayerSession(playerNameOrPayload, voiceId = null, options = {}) {
    const payload =
        typeof playerNameOrPayload === 'object'
            ? playerNameOrPayload
            : { playerName: playerNameOrPayload, voiceId, ...options }
    const {
        playerName,
        voiceId: resolvedVoiceId = null,
        playerId = null,
        players = null,
        panel = 'voice'
    } = payload

    const res = await fetch(`${BASE_URL}/session/start`, {
        method: 'POST',
        headers: buildStandardHeaders({
            panel,
            scope: 'state',
            extraHeaders: { 'Content-Type': 'application/json' }
        }),
        body: JSON.stringify({
            player_name: playerName,
            voice_id: resolvedVoiceId,
            player_id: playerId,
            players
        })
    })

    if (!res.ok) {
        throw await res.json().catch(() => ({ error: 'Failed to start session' }))
    }

    return await res.json()
}

/**
 * End the current player session
 */
export async function endPlayerSession({ panel = 'voice' } = {}) {
    const res = await fetch(`${BASE_URL}/session/end`, {
        method: 'POST',
        headers: buildStandardHeaders({
            panel,
            scope: 'state',
            extraHeaders: { 'Content-Type': 'application/json' }
        })
    })

    if (!res.ok) {
        throw await res.json().catch(() => ({ error: 'Failed to end session' }))
    }

    return await res.json()
}

/**
 * Get the current active player session
 */
export async function getCurrentSession({ panel = 'voice' } = {}) {
    const res = await fetch(`${BASE_URL}/session/current`, {
        method: 'GET',
        headers: buildStandardHeaders({ panel, scope: 'local' })
    })

    if (!res.ok) {
        throw await res.json().catch(() => ({ error: 'Failed to get session' }))
    }

    return await res.json()
}

/**
 * Track a game launch
 */
export async function trackGameLaunch(gameId, gameTitle, platform, genre = null, { panel = 'voice' } = {}) {
    const res = await fetch(`${BASE_URL}/events/launch-start`, {
        method: 'POST',
        headers: buildStandardHeaders({
            panel,
            scope: 'state',
            extraHeaders: { 'Content-Type': 'application/json' }
        }),
        body: JSON.stringify({
            game_id: gameId,
            game_title: gameTitle,
            platform,
            genre
        })
    })

    if (!res.ok) {
        throw await res.json().catch(() => ({ error: 'Failed to track launch' }))
    }

    return await res.json()
}

/**
 * Track game completion
 */
export async function trackGameCompletion(gameId, durationSeconds, score = null, { panel = 'voice' } = {}) {
    const res = await fetch(`${BASE_URL}/events/launch-end`, {
        method: 'POST',
        headers: buildStandardHeaders({
            panel,
            scope: 'state',
            extraHeaders: { 'Content-Type': 'application/json' }
        }),
        body: JSON.stringify({
            game_id: gameId,
            duration_seconds: durationSeconds,
            score
        })
    })

    if (!res.ok) {
        throw await res.json().catch(() => ({ error: 'Failed to track completion' }))
    }

    return await res.json()
}

/**
 * Get player tendencies by name
 */
export async function getPlayerTendencies(playerName, { panel = 'voice' } = {}) {
    const res = await fetch(`${BASE_URL}/tendencies/${encodeURIComponent(playerName)}`, {
        method: 'GET',
        headers: buildStandardHeaders({ panel, scope: 'local' })
    })

    if (!res.ok) {
        throw await res.json().catch(() => ({ error: 'Failed to get tendencies' }))
    }

    return await res.json()
}

/**
 * Get current active player's tendencies
 */
export async function getCurrentPlayerTendencies({ panel = 'voice' } = {}) {
    const res = await fetch(`${BASE_URL}/tendencies/current`, {
        method: 'GET',
        headers: buildStandardHeaders({ panel, scope: 'local' })
    })

    if (!res.ok) {
        throw await res.json().catch(() => ({ error: 'Failed to get current tendencies' }))
    }

    return await res.json()
}
