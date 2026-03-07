import React, { useState, useEffect } from 'react'
import PropTypes from 'prop-types'
import { getHeadlines, getSources, getTrending } from '../../../services/newsClient'
import './GamingNews.css'

export default function GamingNews({ onExit }) {
  const [headlines, setHeadlines] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sources, setSources] = useState([])
  const [selectedSource, setSelectedSource] = useState('all')
  const [searchTerm, setSearchTerm] = useState('')
  const [view, setView] = useState('headlines') // 'headlines', 'trending', or 'by-source'
  const [trending, setTrending] = useState(null)
  const [cacheInfo, setCacheInfo] = useState(null)
  const [sourceStats, setSourceStats] = useState({})
  const [isInitialLoad, setIsInitialLoad] = useState(true)

  // Load headlines on mount and when filters change
  useEffect(() => {
    loadHeadlines()
  }, [selectedSource, searchTerm])

  // Load sources and stats on mount
  useEffect(() => {
    loadSources()
    loadStats()
  }, [])

  const loadHeadlines = async (retryCount = 0) => {
    setLoading(true)
    setError(null)

    try {
      const options = {
        limit: 100, // Increased to get more headlines for source grouping
        ...(selectedSource !== 'all' && { source: selectedSource }),
        ...(searchTerm && { search: searchTerm })
      }

      console.log('[GamingNews] Loading headlines with options:', options)

      const data = await getHeadlines(options)
      console.log('[GamingNews] Received data:', {
        count: data.count,
        headlinesLength: data.headlines?.length,
        totalAvailable: data.total_available,
        cached: data.cached,
        sources: data.sources
      })

      setHeadlines(data.headlines || [])
      setCacheInfo({
        cached: data.cached,
        cacheAgeMinutes: data.cache_age_minutes,
        totalAvailable: data.total_available
      })
      setIsInitialLoad(false)
      setError(null)
      setLoading(false)
    } catch (err) {
      console.error('Failed to load headlines:', err)

      // Auto-retry on initial load (backend might be fetching RSS feeds)
      if (isInitialLoad && retryCount < 2) {
        console.log(`[GamingNews] Initial load failed, retrying in 2s (attempt ${retryCount + 1}/2)`)
        setTimeout(() => loadHeadlines(retryCount + 1), 2000)
      } else {
        setError(err.message || 'Failed to load gaming news')
        setLoading(false)
      }
    }
  }

  const loadSources = async () => {
    try {
      const data = await getSources()
      setSources(data.sources || [])
    } catch (err) {
      console.warn('Failed to load sources:', err)
    }
  }

  const loadStats = async () => {
    try {
      const { getCacheStats } = await import('../../../services/newsClient')
      const data = await getCacheStats()
      console.log('[GamingNews] Cache stats:', data)
      setSourceStats(data.source_breakdown || {})
    } catch (err) {
      console.warn('Failed to load stats:', err)
    }
  }

  const loadTrending = async () => {
    setLoading(true)
    setError(null)

    try {
      console.log('[GamingNews] Loading trending data...')
      const data = await getTrending(24, 10)
      console.log('[GamingNews] Trending data received:', data)
      setTrending(data)
    } catch (err) {
      console.error('[GamingNews] Failed to load trending:', err)
      setError(err.message || 'Failed to load trending topics')
    } finally {
      setLoading(false)
    }
  }

  const handleViewChange = (newView) => {
    setView(newView)
    if (newView === 'trending' && !trending) {
      loadTrending()
    }
  }

  const openArticle = (url) => {
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  return (
    <div className="gaming-news-wrapper">
      {/* Header */}
      <div className="news-header">
        <div className="header-left">
          <div className="news-icon">
            <img src="/dewey-news.png" alt="Gaming News" />
          </div>
          <div className="header-info">
            <h1>Gaming News</h1>
            <div className="news-subtitle">
              {cacheInfo && (
                <span>
                  {cacheInfo.totalAvailable} articles •
                  Updated {cacheInfo.cacheAgeMinutes} min ago
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="header-actions">
          <button className="exit-btn" onClick={onExit}>
            ← Back to Dewey
          </button>
        </div>
      </div>

      {/* View Tabs */}
      <div className="view-tabs">
        <button
          className={`tab-btn ${view === 'headlines' ? 'active' : ''}`}
          onClick={() => handleViewChange('headlines')}
        >
          📰 Headlines
        </button>
        <button
          className={`tab-btn ${view === 'trending' ? 'active' : ''}`}
          onClick={() => handleViewChange('trending')}
        >
          🔥 Trending
        </button>
      </div>

      {/* Filters */}
      {view === 'headlines' && (
        <div className="news-filters">
          <div className="filter-group">
            <label>Source:</label>
            <select
              value={selectedSource}
              onChange={(e) => setSelectedSource(e.target.value)}
              className="source-select"
            >
              <option value="all">All Sources</option>
              {sources.map(source => {
                const count = sourceStats[source.key]?.count || 0
                return (
                  <option
                    key={source.key}
                    value={source.key}
                    disabled={count === 0}
                  >
                    {source.name} {count > 0 ? `(${count})` : '(unavailable)'}
                  </option>
                )
              })}
            </select>
          </div>

          <div className="filter-group">
            <label>Search:</label>
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search headlines..."
              className="search-input"
            />
            {searchTerm && (
              <button
                className="clear-search-btn"
                onClick={() => setSearchTerm('')}
                title="Clear search"
              >
                ✕
              </button>
            )}
          </div>
        </div>
      )}

      {/* Content Area */}
      <div className="news-content">
        {loading && (
          <div className="news-loading">
            <div className="loading-spinner"></div>
            <p>Loading gaming news...</p>
          </div>
        )}

        {error && (
          <div className="news-error">
            <div className="error-icon">⚠️</div>
            <div className="error-message">{error}</div>
            <button className="retry-btn" onClick={view === 'headlines' ? loadHeadlines : loadTrending}>
              Try Again
            </button>
          </div>
        )}

        {!loading && !error && view === 'headlines' && (
          <div className="headlines-list">
            {headlines.length === 0 ? (
              <div className="no-results">
                <p>No headlines found</p>
                {selectedSource !== 'all' && sourceStats[selectedSource]?.count === 0 && (
                  <p className="no-results-hint">
                    This source may be temporarily unavailable or blocked by network filters.
                  </p>
                )}
                {(selectedSource !== 'all' || searchTerm) && (
                  <button
                    className="clear-filters-btn"
                    onClick={() => {
                      setSelectedSource('all')
                      setSearchTerm('')
                    }}
                  >
                    Clear Filters
                  </button>
                )}
              </div>
            ) : (
              headlines.map((headline, index) => (
                <div
                  key={index}
                  className="headline-card"
                  onClick={() => openArticle(headline.url)}
                >
                  <div className="headline-header">
                    <span className="headline-source">{headline.source}</span>
                    <span className="headline-time">{headline.published_relative}</span>
                  </div>
                  <h3 className="headline-title">{headline.title}</h3>
                  {headline.summary && (
                    <p className="headline-summary">{headline.summary.substring(0, 200)}{headline.summary.length > 200 ? '...' : ''}</p>
                  )}
                  {headline.author && (
                    <div className="headline-footer">
                      <span className="headline-author">By {headline.author}</span>
                    </div>
                  )}
                  <div className="headline-categories">
                    {headline.categories && headline.categories.slice(0, 3).map((cat, i) => (
                      <span key={i} className="category-tag">{cat}</span>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {!loading && !error && view === 'trending' && trending && (
          <div className="trending-view">
            <div className="trending-stats">
              <h2>🔥 What's Hot in Gaming</h2>
              <p>Analyzed {trending.articles_analyzed} articles from the last {trending.timeframe_hours} hours</p>
            </div>

            <div className="trending-keywords">
              <h3>Trending Keywords</h3>
              <div className="keywords-grid">
                {trending.trending_keywords.slice(0, 15).map((kw, index) => (
                  <div key={index} className="keyword-chip">
                    <span className="keyword-word">{kw.word}</span>
                    <span className="keyword-count">{kw.mentions}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="trending-headlines">
              <h3>Top Stories</h3>
              {trending.top_headlines.slice(0, 10).map((headline, index) => (
                <div
                  key={index}
                  className="headline-card trending"
                  onClick={() => openArticle(headline.url)}
                >
                  <div className="trending-rank">#{index + 1}</div>
                  <div className="headline-content">
                    <div className="headline-header">
                      <span className="headline-source">{headline.source}</span>
                      <span className="headline-time">{headline.published_relative}</span>
                    </div>
                    <h3 className="headline-title">{headline.title}</h3>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

    </div>
  )
}

GamingNews.propTypes = {
  onExit: PropTypes.func.isRequired
}
