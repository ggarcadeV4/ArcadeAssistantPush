import React from 'react'
import PropTypes from 'prop-types'

export default function ResultsScreen({
  sessionData,
  lifetimeStats,
  onPlayAgain,
  onChangeCategory,
  onExit
}) {
  const { questions_answered, correct_answers, score, best_streak, category, difficulty } = sessionData

  const accuracy = questions_answered > 0
    ? Math.round((correct_answers / questions_answered) * 100)
    : 0

  const isNewHighScore = lifetimeStats && score > lifetimeStats.best_score
  const isNewBestStreak = lifetimeStats && best_streak > lifetimeStats.best_streak

  // Performance rating
  let performanceRating = 'Good Try!'
  let performanceColor = '#00d4ff'

  if (accuracy >= 90) {
    performanceRating = 'LEGENDARY!'
    performanceColor = '#c8ff00'
  } else if (accuracy >= 75) {
    performanceRating = 'Excellent!'
    performanceColor = '#00ff88'
  } else if (accuracy >= 60) {
    performanceRating = 'Great Job!'
    performanceColor = '#00d4ff'
  } else if (accuracy >= 40) {
    performanceRating = 'Not Bad!'
    performanceColor = '#ff6b00'
  } else {
    performanceRating = 'Keep Trying!'
    performanceColor = '#ff00ff'
  }

  return (
    <div className="results-screen">
      <div className="results-header">
        <div className="results-avatar">
          <img src="/dewey-avatar.jpeg" alt="Dewey" />
        </div>
        <h2 className="results-title">Trivia Complete!</h2>
        <div
          className="results-performance"
          style={{ color: performanceColor }}
        >
          {performanceRating}
        </div>
      </div>

      <div className="results-content">
        {/* Main Stats */}
        <div className="results-main-stats">
          <div className="main-stat">
            <div className="main-stat-value">{score}</div>
            <div className="main-stat-label">Total Score</div>
            {isNewHighScore && (
              <div className="new-record">NEW HIGH SCORE!</div>
            )}
          </div>

          <div className="main-stat">
            <div className="main-stat-value">{accuracy}%</div>
            <div className="main-stat-label">Accuracy</div>
          </div>

          <div className="main-stat">
            <div className="main-stat-value">{best_streak}</div>
            <div className="main-stat-label">Best Streak</div>
            {isNewBestStreak && (
              <div className="new-record">NEW RECORD!</div>
            )}
          </div>
        </div>

        {/* Detailed Stats */}
        <div className="results-details">
          <div className="detail-row">
            <span className="detail-label">Questions Answered</span>
            <span className="detail-value">{questions_answered}</span>
          </div>
          <div className="detail-row">
            <span className="detail-label">Correct Answers</span>
            <span className="detail-value correct">{correct_answers}</span>
          </div>
          <div className="detail-row">
            <span className="detail-label">Wrong Answers</span>
            <span className="detail-value wrong">{questions_answered - correct_answers}</span>
          </div>
          <div className="detail-row">
            <span className="detail-label">Category</span>
            <span className="detail-value">{category.charAt(0).toUpperCase() + category.slice(1)}</span>
          </div>
          <div className="detail-row">
            <span className="detail-label">Difficulty</span>
            <span className="detail-value">{difficulty.charAt(0).toUpperCase() + difficulty.slice(1)}</span>
          </div>
        </div>

        {/* Lifetime Stats (if available) */}
        {lifetimeStats && (
          <div className="lifetime-stats">
            <h3>Your Lifetime Stats</h3>
            <div className="lifetime-grid">
              <div className="lifetime-stat">
                <div className="lifetime-value">{lifetimeStats.total_questions}</div>
                <div className="lifetime-label">Total Questions</div>
              </div>
              <div className="lifetime-stat">
                <div className="lifetime-value">
                  {lifetimeStats.total_questions > 0
                    ? Math.round((lifetimeStats.total_correct / lifetimeStats.total_questions) * 100)
                    : 0}%
                </div>
                <div className="lifetime-label">Overall Accuracy</div>
              </div>
              <div className="lifetime-stat">
                <div className="lifetime-value">{lifetimeStats.best_score}</div>
                <div className="lifetime-label">Best Score</div>
              </div>
              <div className="lifetime-stat">
                <div className="lifetime-value">{lifetimeStats.best_streak}</div>
                <div className="lifetime-label">Best Streak</div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="results-actions">
        <button className="results-btn primary" onClick={onPlayAgain}>
          Play Again
        </button>
        <button className="results-btn secondary" onClick={onChangeCategory}>
          Change Category
        </button>
        <button className="results-btn tertiary" onClick={onExit}>
          Exit Trivia
        </button>
      </div>

      {/* Footer Message */}
      <div className="results-footer">
        <p>Thanks for playing! Your stats have been saved.</p>
      </div>
    </div>
  )
}

ResultsScreen.propTypes = {
  sessionData: PropTypes.shape({
    category: PropTypes.string.isRequired,
    difficulty: PropTypes.string.isRequired,
    questions_answered: PropTypes.number.isRequired,
    correct_answers: PropTypes.number.isRequired,
    score: PropTypes.number.isRequired,
    best_streak: PropTypes.number.isRequired
  }).isRequired,
  lifetimeStats: PropTypes.shape({
    total_questions: PropTypes.number,
    total_correct: PropTypes.number,
    best_score: PropTypes.number,
    best_streak: PropTypes.number
  }),
  onPlayAgain: PropTypes.func.isRequired,
  onChangeCategory: PropTypes.func.isRequired,
  onExit: PropTypes.func.isRequired
}

ResultsScreen.defaultProps = {
  lifetimeStats: null
}
