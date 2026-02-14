/**
 * scorekeeperClient: API client for ScoreKeeper Sam operations
 * Routes: /scores/* and backend proxied to FastAPI
 */

const BASE = '/api/local/scorekeeper'
const GATEWAY_URL = 'http://localhost:8787'

const resolveDeviceId = () => {
  if (typeof window === 'undefined') {
    return 'cabinet-001'
  }
  return window.AA_DEVICE_ID ?? window.__DEVICE_ID__ ?? 'cabinet-001'
}

const commonHeaders = (panel = 'scorekeeper', scope = 'local') => ({
  'Content-Type': 'application/json',
  'x-device-id': resolveDeviceId(),
  'x-panel': panel,
  'x-scope': scope
})

export async function getLeaderboard({ game = null, limit = 10 } = {}) {
  // Gateway proxy to plugin-first leaderboard (read-only)
  const params = new URLSearchParams({ limit: String(limit) })
  if (game) params.append('game', game)

  const res = await fetch(`${GATEWAY_URL}/api/launchbox/scores/leaderboard?${params.toString()}`, {
    method: 'GET',
    headers: { 'content-type': 'application/json', 'x-panel': 'launchbox' }
  })

  if (res.status === 503) {
    // Friendly offline signal
    const body = await res.json().catch(() => ({ success: false, error: 'plugin_unavailable' }))
    body.cached = false
    throw body
  }
  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to fetch leaderboard' }))

  const json = await res.json()
  // Normalize shape to { scores: [...], cached?: boolean }
  const scores = Array.isArray(json?.scores) ? json.scores : (Array.isArray(json?.leaderboard) ? json.leaderboard : [])
  return { scores, cached: !!json.cached }
}

export async function getByGame({ gameId }) {
  const params = new URLSearchParams({ gameId })
  const res = await fetch(`${GATEWAY_URL}/api/launchbox/scores/by-game?${params.toString()}`, {
    method: 'GET',
    headers: { 'content-type': 'application/json', 'x-panel': 'launchbox' }
  })
  if (res.status === 503) {
    const body = await res.json().catch(() => ({ success: false, error: 'plugin_unavailable' }))
    body.cached = false
    throw body
  }
  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to fetch scores' }))
  const json = await res.json()
  const scores = Array.isArray(json?.scores) ? json.scores : []
  return { gameId: json.gameId || gameId, scores, cached: !!json.cached }
}

export async function previewScoreSubmit(data) {
  const res = await fetch(`${BASE}/submit/preview`, {
    method: 'POST',
    headers: commonHeaders(),
    body: JSON.stringify(data)
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Preview failed' }))
  return await res.json()
}

export async function applyScoreSubmit(data) {
  const { deviceId = 'demo_001', panel = 'scorekeeper', ...payload } = data || {}
  const headers = commonHeaders(panel, 'state')
  headers['x-device-id'] = deviceId

  const res = await fetch(`${BASE}/submit/apply`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload)
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Submit failed' }))
  return await res.json()
}

export async function previewTournamentCreate({
  name,
  game,
  player_count,
  panel = 'scorekeeper',
  deviceId = resolveDeviceId()
}) {
  const headers = commonHeaders(panel, 'state')
  if (deviceId) headers['x-device-id'] = deviceId

  const res = await fetch(`${BASE}/tournaments/create/preview`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ name, game, player_count })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Preview failed' }))
  return await res.json()
}

export async function applyTournamentCreate({ name, game, player_count, deviceId = 'demo_001', panel = 'scorekeeper' }) {
  const headers = commonHeaders(panel, 'state')
  headers['x-device-id'] = deviceId

  const res = await fetch(`${BASE}/tournaments/create/apply`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ name, game, player_count })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Create failed' }))
  return await res.json()
}

export async function getTournament(tournamentId) {
  const res = await fetch(`${BASE}/tournaments/${tournamentId}`, {
    method: 'GET',
    headers: commonHeaders()
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Tournament not found' }))
  return await res.json()
}

export async function listTournaments() {
  const res = await fetch(`${BASE}/tournaments`, {
    method: 'GET',
    headers: commonHeaders()
  })
  if (!res.ok) throw await res.json().catch(() => ({ error: 'List tournaments failed' }))
  return await res.json()
}

export async function submitScoreViaPlugin({ gameId, player, score }) {
  const GATEWAY_URL = 'http://localhost:8787'
  const res = await fetch(`${GATEWAY_URL}/api/launchbox/scores/submit`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-panel': 'scorekeeper' },
    body: JSON.stringify({ gameId, player, score })
  })
  // Plugin proxy returns 503 with {error:'plugin_unavailable'} if offline
  if (!res.ok) throw await res.json().catch(() => ({ error: 'plugin_submit_failed' }))
  return await res.json()
}

export async function resolveGameByTitle(title) {
  const GATEWAY_URL = 'http://localhost:8787'
  const res = await fetch(`${GATEWAY_URL}/api/launchbox/resolve`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-panel': 'scorekeeper' },
    body: JSON.stringify({ game_name: title, limit: 5 })
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw (body || { error: 'resolve_failed' })
  if (Array.isArray(body)) return body
  if (body?.status === 'resolved' && body.game) return [body.game]
  if (body?.status === 'multiple_matches' && Array.isArray(body.suggestions)) return body.suggestions
  return []
}

export async function previewTournamentReport({ tournament_id, match_index, winner_player }) {
  const res = await fetch(`${BASE}/tournaments/report/preview`, {
    method: 'POST',
    headers: commonHeaders(),
    body: JSON.stringify({ tournament_id, match_index, winner_player })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Preview failed' }))
  return await res.json()
}

export async function applyTournamentReport({ tournament_id, match_index, winner_player, deviceId = 'demo_001', panel = 'scorekeeper' }) {
  const headers = commonHeaders(panel, 'state')
  headers['x-device-id'] = deviceId

  const res = await fetch(`${BASE}/tournaments/report/apply`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ tournament_id, match_index, winner_player })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Report failed' }))
  return await res.json()
}

export async function undoScorekeeper({ panel = 'scorekeeper', deviceId = resolveDeviceId() } = {}) {
  const headers = commonHeaders(panel, 'state')
  if (deviceId) headers['x-device-id'] = deviceId

  const res = await fetch(`${BASE}/restore`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ strategy: 'last' })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Undo failed' }))
  return await res.json()
}

export async function restoreScorekeeper({ backupPath, dryRun = false, panel = 'scorekeeper', deviceId = resolveDeviceId() } = {}) {
  if (!backupPath) {
    throw new Error('backupPath is required for restoreScorekeeper')
  }

  const headers = commonHeaders(panel, 'state')
  if (deviceId) headers['x-device-id'] = deviceId

  const payload = { backup_path: backupPath }
  if (typeof dryRun === 'boolean') {
    payload.dry_run = dryRun
  }

  const res = await fetch(`${BASE}/restore`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload)
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Restore failed' }))
  return await res.json()
}

/**
 * Get top players for a specific game
 *
 * Calls the existing backend leaderboard endpoint that reads scores.jsonl,
 * filters by game name, and returns ranked players by score.
 *
 * @param {string} gameName - Game name to filter scores (exact match on "game" field in scores.jsonl)
 * @param {number} limit - Max number of top players to return (default 10)
 * @returns {Promise<{game: string, topPlayer: object|null, allScores: array}>}
 */
export async function getGameLeaderboard(gameName, limit = 10) {
  if (!gameName || typeof gameName !== 'string') {
    return { game: null, topPlayer: null, allScores: [] }
  }

  try {
    // Use existing getLeaderboard function that calls GET /api/local/scorekeeper/leaderboard?game={name}
    const result = await getLeaderboard({ game: gameName, limit })

    const scores = result?.scores || []

    return {
      game: gameName,
      topPlayer: scores.length > 0 ? scores[0] : null,
      allScores: scores
    }
  } catch (error) {
    console.error('[scorekeeperClient] Failed to fetch game leaderboard:', error)
    // Return empty result on error instead of throwing
    return { game: gameName, topPlayer: null, allScores: [] }
  }
}

/**
 * Get MAME high scores from the Lua plugin
 * 
 * Reads from mame_scores.json (written by arcade_assistant Lua plugin).
 * This is the real-time data that ScoreKeeper Sam uses for AI awareness.
 * 
 * @returns {Promise<{games: object, leaderboard: array, total_games: number, total_scores: number}>}
 */
export async function getMameScores() {
  try {
    const res = await fetch(`${GATEWAY_URL}/api/scores/mame`, {
      method: 'GET',
      headers: { 'content-type': 'application/json', 'x-panel': 'scorekeeper' }
    })

    if (!res.ok) {
      throw await res.json().catch(() => ({ error: 'Failed to fetch MAME scores' }))
    }

    return await res.json()
  } catch (error) {
    console.error('[scorekeeperClient] getMameScores failed:', error)
    return { games: {}, leaderboard: [], total_games: 0, total_scores: 0 }
  }
}

/**
 * Reset a MAME game's high score
 * 
 * Archives current .hi file, deletes it, and clears AI state.
 * 
 * @param {string} romName - MAME ROM name (e.g., 'galaga')
 * @returns {Promise<{game: string, backup_created: boolean, file_deleted: boolean, message: string}>}
 */
export async function resetMameScore(romName) {
  const res = await fetch(`${GATEWAY_URL}/api/scores/reset/${romName}`, {
    method: 'DELETE',
    headers: { 'content-type': 'application/json', 'x-panel': 'scorekeeper' }
  })

  if (!res.ok) {
    throw await res.json().catch(() => ({ error: 'Reset failed' }))
  }

  return await res.json()
}

