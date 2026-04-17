import React, { useState, useEffect, useCallback } from 'react'
import PropTypes from 'prop-types'
import CategorySelector from './CategorySelector'
import DifficultySelector from './DifficultySelector'
import QuestionScreen from './QuestionScreen'
import ResultsScreen from './ResultsScreen'
import { getQuestions, getStats, saveStats } from '../../../services/deweyClient'
import './TriviaExperience.css'
import { buildStandardHeaders } from '../../../utils/identity'

const SCREENS = {
  CATEGORY: 'category',
  DIFFICULTY: 'difficulty',
  QUESTIONS: 'questions',
  RESULTS: 'results',
  LOADING: 'loading'
}

const COLLECTION_LIBRARY_ERROR = 'Your Collection requires an active LaunchBox library. Start LaunchBox and try again.'
const DEFAULT_LOADING_MESSAGE = 'Loading trivia questions...'
const COLLECTION_LOADING_MESSAGE = 'Generating questions from your library...'

async function fetchCollectionTriviaQuestions(limit = 10) {
  const response = await fetch('/api/local/dewey/trivia/collection', {
    method: 'POST',
    headers: buildStandardHeaders({
      panel: 'dewey',
      scope: 'state',
      extraHeaders: { 'Content-Type': 'application/json' }
    }),
    body: JSON.stringify({ count: limit })
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: COLLECTION_LIBRARY_ERROR }))
    throw new Error(error.detail || COLLECTION_LIBRARY_ERROR)
  }

  return response.json()
}

export default function TriviaExperience({ currentUser, onExit }) {
  const [currentScreen, setCurrentScreen] = useState(SCREENS.CATEGORY)
  const [selectedCategory, setSelectedCategory] = useState(null)
  const [selectedDifficulty, setSelectedDifficulty] = useState(null)
  const [questions, setQuestions] = useState([])
  const [sessionData, setSessionData] = useState(null)
  const [lifetimeStats, setLifetimeStats] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadingMessage, setLoadingMessage] = useState(DEFAULT_LOADING_MESSAGE)

  const profileId = currentUser?.id || 'guest'

  // Load user stats on mount
  useEffect(() => {
    loadUserStats()
  }, [profileId])

  const loadUserStats = async () => {
    try {
      const response = await getStats(profileId)
      setLifetimeStats(response.stats?.lifetime || null)

      // Set preferred category/difficulty if available
      if (response.stats?.preferred_category && !selectedCategory) {
        // Note: Don't auto-select, just use for UI hints
      }
    } catch (err) {
      console.warn('Could not load user stats:', err)
      // Not critical - continue without stats
    }
  }

  const handleSelectCategory = async (category) => {
    setSelectedCategory(category)
    setError(null)
    setCurrentScreen(SCREENS.DIFFICULTY)
  }

  const loadTriviaQuestions = useCallback(async (category, difficulty) => {
    if (category === 'collection') {
      return fetchCollectionTriviaQuestions(10)
    }
    return getQuestions(category, difficulty, 10)
  }, [])

  const handleSelectDifficulty = async (difficulty) => {
    setSelectedDifficulty(difficulty)
    setError(null)
    setLoading(true)
    setLoadingMessage(selectedCategory === 'collection' ? COLLECTION_LOADING_MESSAGE : DEFAULT_LOADING_MESSAGE)
    setCurrentScreen(SCREENS.LOADING)

    try {
      const response = await loadTriviaQuestions(selectedCategory, difficulty)

      if (!response.questions || response.questions.length === 0) {
        throw new Error('No questions available for this category/difficulty combination')
      }

      setQuestions(response.questions)
      setCurrentScreen(SCREENS.QUESTIONS)
    } catch (err) {
      console.error('Failed to load questions:', err)
      if (selectedCategory === 'collection') {
        setError(COLLECTION_LIBRARY_ERROR)
      } else {
        setError(err.message || 'Failed to load trivia questions')
      }
      setCurrentScreen(SCREENS.DIFFICULTY)
    } finally {
      setLoading(false)
    }
  }

  const handleQuizComplete = async (sessionResults) => {
    setSessionData(sessionResults)

    // Save stats to backend
    try {
      const response = await saveStats(profileId, sessionResults)
      setLifetimeStats(response.updated_stats?.lifetime || lifetimeStats)
    } catch (err) {
      console.error('Failed to save stats:', err)
      // Continue anyway - show results even if save failed
    }

    setCurrentScreen(SCREENS.RESULTS)
  }

  const handlePlayAgain = useCallback(() => {
    // Same category/difficulty - just load new questions
    setError(null)
    setLoading(true)
    setLoadingMessage(selectedCategory === 'collection' ? COLLECTION_LOADING_MESSAGE : DEFAULT_LOADING_MESSAGE)
    setCurrentScreen(SCREENS.LOADING)

    loadTriviaQuestions(selectedCategory, selectedDifficulty)
      .then(response => {
        setQuestions(response.questions)
        setCurrentScreen(SCREENS.QUESTIONS)
      })
      .catch(err => {
        console.error('Failed to load questions:', err)
        if (selectedCategory === 'collection') {
          setError(COLLECTION_LIBRARY_ERROR)
        } else {
          setError(err.message || 'Failed to load trivia questions')
        }
        setCurrentScreen(SCREENS.DIFFICULTY)
      })
      .finally(() => {
        setLoading(false)
      })
  }, [loadTriviaQuestions, selectedCategory, selectedDifficulty])

  const handleChangeCategory = () => {
    setSelectedCategory(null)
    setSelectedDifficulty(null)
    setQuestions([])
    setSessionData(null)
    setError(null)
    setCurrentScreen(SCREENS.CATEGORY)
  }

  const handleQuit = () => {
    if (currentScreen === SCREENS.QUESTIONS) {
      const confirmQuit = window.confirm('Are you sure you want to quit? Your progress will be lost.')
      if (!confirmQuit) return
    }
    onExit()
  }

  const handleBackToDifficulty = () => {
    setSelectedDifficulty(null)
    setError(null)
    setCurrentScreen(SCREENS.DIFFICULTY)
  }

  const handleBackToCategory = () => {
    setSelectedCategory(null)
    setSelectedDifficulty(null)
    setError(null)
    setCurrentScreen(SCREENS.CATEGORY)
  }

  return (
    <div className="trivia-experience">
      {/* Loading Screen */}
      {currentScreen === SCREENS.LOADING && (
        <div className="trivia-loading">
          <div className="loading-spinner"></div>
          <p>{loadingMessage}</p>
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="trivia-error">
          <div className="error-icon">⚠️</div>
          <div className="error-message">{error}</div>
          <button className="error-btn" onClick={handleBackToDifficulty}>
            Try Again
          </button>
        </div>
      )}

      {/* Category Selection */}
      {currentScreen === SCREENS.CATEGORY && (
        <CategorySelector
          onSelectCategory={handleSelectCategory}
          preferredCategory={lifetimeStats?.preferred_category}
        />
      )}

      {/* Difficulty Selection */}
      {currentScreen === SCREENS.DIFFICULTY && !error && (
        <DifficultySelector
          selectedCategory={selectedCategory}
          onSelectDifficulty={handleSelectDifficulty}
          onBack={handleBackToCategory}
          preferredDifficulty={lifetimeStats?.preferred_difficulty}
        />
      )}

      {/* Question Screen */}
      {currentScreen === SCREENS.QUESTIONS && questions.length > 0 && (
        <QuestionScreen
          questions={questions}
          category={selectedCategory}
          difficulty={selectedDifficulty}
          onComplete={handleQuizComplete}
          onQuit={handleQuit}
        />
      )}

      {/* Results Screen */}
      {currentScreen === SCREENS.RESULTS && sessionData && (
        <ResultsScreen
          sessionData={sessionData}
          lifetimeStats={lifetimeStats}
          onPlayAgain={handlePlayAgain}
          onChangeCategory={handleChangeCategory}
          onExit={handleQuit}
        />
      )}
    </div>
  )
}

TriviaExperience.propTypes = {
  currentUser: PropTypes.shape({
    id: PropTypes.string,
    name: PropTypes.string
  }).isRequired,
  onExit: PropTypes.func.isRequired
}
