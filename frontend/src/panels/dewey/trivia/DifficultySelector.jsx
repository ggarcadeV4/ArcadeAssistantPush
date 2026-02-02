import React from 'react'
import PropTypes from 'prop-types'

const DIFFICULTIES = [
  {
    id: 'easy',
    name: 'Easy',
    icon: '😊',
    description: 'Perfect for casual players',
    multiplier: 1,
    timeLimit: 15,
    color: '#00ff88'
  },
  {
    id: 'medium',
    name: 'Medium',
    icon: '🎯',
    description: 'For the seasoned gamer',
    multiplier: 2,
    timeLimit: 10,
    color: '#00d4ff'
  },
  {
    id: 'hard',
    name: 'Hard',
    icon: '🔥',
    description: 'True arcade legends only',
    multiplier: 3,
    timeLimit: 8,
    color: '#ff00ff'
  }
]

export default function DifficultySelector({
  selectedCategory,
  onSelectDifficulty,
  onBack,
  preferredDifficulty
}) {
  const categoryName = selectedCategory
    ? selectedCategory.charAt(0).toUpperCase() + selectedCategory.slice(1)
    : 'Selected'

  return (
    <div className="difficulty-selector">
      <div className="difficulty-header">
        <h2>{categoryName} Trivia</h2>
        <p className="difficulty-subtitle">
          Choose your difficulty level
        </p>
      </div>

      <div className="difficulty-grid">
        {DIFFICULTIES.map(difficulty => (
          <button
            key={difficulty.id}
            className={`difficulty-tile ${preferredDifficulty === difficulty.id ? 'preferred' : ''}`}
            onClick={() => onSelectDifficulty(difficulty.id)}
            style={{
              '--difficulty-color': difficulty.color
            }}
          >
            <div className="difficulty-icon">{difficulty.icon}</div>
            <div className="difficulty-name">{difficulty.name}</div>
            <div className="difficulty-description">{difficulty.description}</div>

            <div className="difficulty-stats">
              <div className="stat">
                <span className="stat-label">Points</span>
                <span className="stat-value">x{difficulty.multiplier}</span>
              </div>
              <div className="stat">
                <span className="stat-label">Time</span>
                <span className="stat-value">{difficulty.timeLimit}s</span>
              </div>
            </div>

            {preferredDifficulty === difficulty.id && (
              <div className="preferred-badge">Last Played</div>
            )}
          </button>
        ))}
      </div>

      <div className="difficulty-footer">
        <button className="back-button" onClick={onBack}>
          ← Back to Categories
        </button>
        <p className="difficulty-hint">
          Higher difficulty = More points & less time!
        </p>
      </div>
    </div>
  )
}

DifficultySelector.propTypes = {
  selectedCategory: PropTypes.string.isRequired,
  onSelectDifficulty: PropTypes.func.isRequired,
  onBack: PropTypes.func.isRequired,
  preferredDifficulty: PropTypes.string
}

DifficultySelector.defaultProps = {
  preferredDifficulty: null
}

// Export difficulty configurations for use in QuestionScreen
export { DIFFICULTIES }
