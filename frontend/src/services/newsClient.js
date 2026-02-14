/**
 * Gaming News Client
 * Fetches latest gaming headlines from RSS feeds via backend
 */

const API_BASE = '/api/local/news'

/**
 * Get latest gaming headlines
 * @param {Object} options - Query options
 * @param {number} options.limit - Maximum headlines to return (default: 20)
 * @param {string} options.source - Filter by source (e.g., 'ign', 'gamespot')
 * @param {string} options.search - Search keyword in title or summary
 * @param {number} options.hours - Only show news from last N hours
 * @returns {Promise<Object>} - { headlines, count, sources, cached, cache_age_minutes, total_available }
 */
export async function getHeadlines(options = {}) {
  const { limit = 20, source = null, search = null, hours = null } = options

  const params = new URLSearchParams()
  if (limit) params.append('limit', limit)
  if (source) params.append('source', source)
  if (search) params.append('search', search)
  if (hours) params.append('hours', hours)

  const url = `${API_BASE}/headlines?${params.toString()}`

  const response = await fetch(url)

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to fetch headlines' }))
    throw new Error(error.detail || 'Failed to fetch gaming news')
  }

  return response.json()
}

/**
 * Get list of available news sources
 * @returns {Promise<Object>} - { sources, count }
 */
export async function getSources() {
  const response = await fetch(`${API_BASE}/sources`)

  if (!response.ok) {
    throw new Error('Failed to fetch news sources')
  }

  return response.json()
}

/**
 * Get trending topics from recent headlines
 * @param {number} hours - Hours to analyze (default: 24)
 * @param {number} limit - Number of results (default: 10)
 * @returns {Promise<Object>} - { timeframe_hours, articles_analyzed, trending_keywords, top_headlines }
 */
export async function getTrending(hours = 24, limit = 10) {
  const params = new URLSearchParams()
  params.append('hours', hours)
  params.append('limit', limit)

  const response = await fetch(`${API_BASE}/trending?${params.toString()}`)

  if (!response.ok) {
    throw new Error('Failed to fetch trending topics')
  }

  return response.json()
}

/**
 * Force refresh the headlines cache
 * @returns {Promise<Object>} - { success, headlines_count, sources_count, timestamp }
 */
export async function refreshHeadlines() {
  const response = await fetch(`${API_BASE}/refresh`, {
    method: 'POST'
  })

  if (!response.ok) {
    throw new Error('Failed to refresh headlines')
  }

  return response.json()
}

/**
 * Get cache statistics
 * @returns {Promise<Object>} - Cache stats
 */
export async function getCacheStats() {
  const response = await fetch(`${API_BASE}/stats`)

  if (!response.ok) {
    throw new Error('Failed to fetch cache stats')
  }

  return response.json()
}
