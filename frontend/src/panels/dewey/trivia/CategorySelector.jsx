import React from 'react'
import PropTypes from 'prop-types'

const CATEGORIES = [
  {
    id: 'arcade',
    name: 'Arcade Classics',
    icon: '🕹️',
    description: 'Test your knowledge of golden age arcade games',
    color: '#ff00ff' // Magenta
  },
  {
    id: 'console',
    name: 'Console Era',
    icon: '🎮',
    description: 'From NES to PS5 - the evolution of home gaming',
    color: '#00d4ff' // Cyan
  },
  {
    id: 'genre',
    name: 'Genres',
    icon: '🎯',
    description: 'Fighting, shmups, platformers, and more',
    color: '#c8ff00' // Yellow-green
  },
  {
    id: 'decade',
    name: 'Decades',
    icon: '📅',
    description: 'Journey through gaming history by era',
    color: '#ff6b00' // Orange
  },
  {
    id: 'popculture',
    name: 'Pop Culture',
    icon: '🎬',
    description: 'Gaming movies, TV shows, and crossover culture',
    color: '#ff3366' // Red-pink
  },
  {
    id: 'collection',
    name: 'Your Collection',
    icon: '📚',
    description: 'Questions about games in your LaunchBox library',
    color: '#00ff88' // Green
  },
  {
    id: 'mixed',
    name: 'Mixed Madness',
    icon: '🎲',
    description: 'A little bit of everything - good luck!',
    color: '#ff0099' // Pink
  }
]

export default function CategorySelector({ onSelectCategory, preferredCategory }) {
  return (
    <div className="category-selector">
      <div className="category-header">
        <h2>Choose Your Trivia Category</h2>
        <p className="category-subtitle">
          Pick a topic and prove your gaming knowledge!
        </p>
      </div>

      <div className="category-grid">
        {CATEGORIES.map(category => (
          <button
            key={category.id}
            className={`category-tile ${preferredCategory === category.id ? 'preferred' : ''}`}
            onClick={() => onSelectCategory(category.id)}
            style={{
              '--category-color': category.color
            }}
          >
            <div className="category-icon">{category.icon}</div>
            <div className="category-name">{category.name}</div>
            <div className="category-description">{category.description}</div>
            {preferredCategory === category.id && (
              <div className="preferred-badge">Last Played</div>
            )}
          </button>
        ))}
      </div>

      <div className="category-footer">
        <p>7 unique categories - Each with Easy, Medium, and Hard questions</p>
      </div>
    </div>
  )
}

CategorySelector.propTypes = {
  onSelectCategory: PropTypes.func.isRequired,
  preferredCategory: PropTypes.string
}

CategorySelector.defaultProps = {
  preferredCategory: null
}
