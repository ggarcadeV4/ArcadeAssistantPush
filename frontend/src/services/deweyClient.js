/**
 * Dewey Trivia Client
 * API client for Dewey trivia features
 */
import { buildStandardHeaders } from '../utils/identity'

const API_BASE = '/api/local/dewey'
const DEWEY_HEADERS = (scope = 'state', json = true) =>
  buildStandardHeaders({
    panel: 'dewey',
    scope,
    extraHeaders: json ? { 'Content-Type': 'application/json' } : {}
  })

/**
 * Get trivia questions filtered by category and difficulty
 * @param {string} category - arcade, console, genre, decade, collection, mixed
 * @param {string} difficulty - easy, medium, hard (optional)
 * @param {number} limit - number of questions (default: 10)
 * @returns {Promise<{questions: Array, count: number, filters: Object}>}
 */
export async function getQuestions(category = 'mixed', difficulty = null, limit = 10) {
  const params = new URLSearchParams({
    category,
    limit: limit.toString()
  })

  if (difficulty) {
    params.append('difficulty', difficulty)
  }

  const response = await fetch(`${API_BASE}/trivia/questions?${params}`, {
    method: 'GET',
    headers: DEWEY_HEADERS()
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to fetch questions' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

/**
 * Get trivia questions based on LaunchBox collection
 * @param {number} limit - number of questions (default: 10)
 * @returns {Promise<{questions: Array, count: number, note: string}>}
 */
export async function getCollectionQuestions(limit = 10) {
  const response = await fetch(`${API_BASE}/trivia/collection-questions?limit=${limit}`, {
    method: 'GET',
    headers: DEWEY_HEADERS()
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to fetch collection questions' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

/**
 * Get trivia stats for a profile
 * @param {string} profileId - The profile ID
 * @returns {Promise<{profile_id: string, stats: Object}>}
 */
export async function getStats(profileId) {
  const response = await fetch(`${API_BASE}/trivia/stats/${profileId}`, {
    method: 'GET',
    headers: DEWEY_HEADERS()
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to fetch stats' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

/**
 * Save trivia session stats to tendency file
 * @param {string} profileId - The profile ID
 * @param {Object} sessionData - Session stats to save
 * @param {string} sessionData.category - Category played
 * @param {string} sessionData.difficulty - Difficulty level
 * @param {number} sessionData.questions_answered - Total questions answered
 * @param {number} sessionData.correct_answers - Number correct
 * @param {number} sessionData.score - Total score
 * @param {number} sessionData.best_streak - Longest streak
 * @returns {Promise<{success: boolean, profile_id: string, updated_stats: Object}>}
 */
export async function saveStats(profileId, sessionData) {
  const response = await fetch(`${API_BASE}/trivia/save-stats`, {
    method: 'POST',
    headers: DEWEY_HEADERS('state'),
    body: JSON.stringify({
      profile_id: profileId,
      session_data: sessionData
    })
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to save stats' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

/**
 * Future hook: Start screenshot scramble mode
 * Will use LaunchBox media for visual trivia
 */
export function startScreenshotMode() {
  console.warn('Screenshot mode not yet implemented - placeholder for Session 2')
  // TODO: Implement screenshot-based trivia using LaunchBox media
  return Promise.resolve({ mode: 'screenshot', status: 'not_implemented' })
}

/**
 * Future hook: Start sound check mode
 * Guess-that-sound trivia
 */
export function startSoundMode() {
  console.warn('Sound mode not yet implemented - placeholder for Session 2')
  // TODO: Implement sound-based trivia
  return Promise.resolve({ mode: 'sound', status: 'not_implemented' })
}

/**
 * Future hook: Start versus/multiplayer mode
 * @param {number} playerCount - Number of players (2-4)
 */
export function startVersusMode(playerCount = 2) {
  console.warn('Versus mode not yet implemented - placeholder for Session 2')
  // TODO: Implement multiplayer trivia using seat map
  return Promise.resolve({ mode: 'versus', playerCount, status: 'not_implemented' })
}

/**
 * Future hook: Award badge/achievement
 * @param {string} badgeId - Badge identifier
 */
export function awardBadge(badgeId) {
  console.warn('Badge system not yet implemented - placeholder for Session 2')
  // TODO: Implement achievement/badge system
  return Promise.resolve({ badge: badgeId, awarded: false, status: 'not_implemented' })
}

/**
 * Future hook: Evaluate daily/weekly challenges
 */
export function evaluateDailyChallenges() {
  console.warn('Daily challenges not yet implemented - placeholder for Session 2')
  // TODO: Implement daily/weekly challenge system
  return Promise.resolve({ challenges: [], status: 'not_implemented' })
}

/**
 * Future hook: Update cross-profile leaderboard
 * @param {string} profileId - Profile ID
 * @param {number} score - Score to submit
 */
export function updateLeaderboard(profileId, score) {
  console.warn('Leaderboard not yet implemented - placeholder for Session 2')
  // TODO: Implement global leaderboard system
  return Promise.resolve({ profile: profileId, score, rank: null, status: 'not_implemented' })
}
