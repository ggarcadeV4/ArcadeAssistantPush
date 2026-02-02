import React, { useState, useEffect, useCallback } from 'react'
import PropTypes from 'prop-types'
import { DIFFICULTIES } from './DifficultySelector'
import { speakAsDewey, stopSpeaking } from '../../../services/ttsClient'

// Dewey reactions based on performance
const DEWEY_REACTIONS = {
  correct: [
    "Nice!",
    "You got it!",
    "Someone knows their games!",
    "Exactly right!",
    "Boom! Correct!",
    "That's the one!",
    "You're on fire!"
  ],
  wrong: [
    "Oof - close but no quarter!",
    "Not quite!",
    "Almost had it!",
    "Better luck next time!",
    "Don't worry, happens to the best!",
    "Keep trying!"
  ],
  streak3: "Nice combo! 3 in a row!",
  streak5: "UNSTOPPABLE! 5-streak!",
  streak7: "LEGENDARY! 7-streak!"
}

function getRandomReaction(type) {
  const reactions = DEWEY_REACTIONS[type]
  return reactions[Math.floor(Math.random() * reactions.length)]
}

export default function QuestionScreen({
  questions,
  category,
  difficulty,
  onComplete,
  onQuit
}) {
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0)
  const [score, setScore] = useState(0)
  const [streak, setStreak] = useState(0)
  const [bestStreak, setBestStreak] = useState(0)
  const [correctCount, setCorrectCount] = useState(0)
  const [selectedAnswer, setSelectedAnswer] = useState(null)
  const [isAnswered, setIsAnswered] = useState(false)
  const [showFeedback, setShowFeedback] = useState(false)
  const [deweyReaction, setDeweyReaction] = useState('')
  const [timeLeft, setTimeLeft] = useState(10)
  const [timerActive, setTimerActive] = useState(false) // Start as false, will activate after narration
  const [isNarrating, setIsNarrating] = useState(false)
  const [narrateEnabled, setNarrateEnabled] = useState(true)

  const currentQuestion = questions[currentQuestionIndex]
  const difficultyConfig = DIFFICULTIES.find(d => d.id === difficulty) || DIFFICULTIES[1]
  const pointsPerQuestion = 100 * difficultyConfig.multiplier
  const totalQuestions = questions.length

  // Narration effect - narrate question when it changes
  useEffect(() => {
    if (!narrateEnabled || isAnswered) return

    // Stop any previous narration first
    stopSpeaking()

    setIsNarrating(true)
    setTimerActive(false)

    // Build full narration with answer choices
    const choicesText = currentQuestion.choices
      .map((choice, index) => `${String.fromCharCode(65 + index)}: ${choice}`)
      .join(', ')

    const fullNarration = `${currentQuestion.question} ${choicesText}`

    // Small delay to ensure previous speech stopped
    const timeoutId = setTimeout(() => {
      speakAsDewey(fullNarration)
        .then(() => {
          setIsNarrating(false)
          setTimerActive(true) // Start timer after narration completes
        })
        .catch(err => {
          console.warn('Question narration failed:', err)
          setIsNarrating(false)
          setTimerActive(true) // Start timer anyway if narration fails
        })
    }, 100)

    // Cleanup: stop speaking if user navigates away
    return () => {
      clearTimeout(timeoutId)
      stopSpeaking()
    }
  }, [currentQuestionIndex, narrateEnabled])

  // Timer effect
  useEffect(() => {
    if (!timerActive || isAnswered) return

    setTimeLeft(difficultyConfig.timeLimit)

    const timer = setInterval(() => {
      setTimeLeft(prev => {
        if (prev <= 1) {
          // Time's up!
          handleAnswer(null, true)
          return 0
        }
        return prev - 1
      })
    }, 1000)

    return () => clearInterval(timer)
  }, [currentQuestionIndex, timerActive, isAnswered, difficultyConfig.timeLimit])

  const handleAnswer = useCallback((answerIndex, timeExpired = false) => {
    if (isAnswered) return

    setIsAnswered(true)
    setTimerActive(false)
    setSelectedAnswer(answerIndex)

    const isCorrect = answerIndex === currentQuestion.correct_index
    const isTimeOut = timeExpired

    // Debug logging
    console.log('=== ANSWER DEBUG ===')
    console.log('Question:', currentQuestion.question)
    console.log('User selected index:', answerIndex, '→', currentQuestion.choices[answerIndex])
    console.log('Correct index:', currentQuestion.correct_index, '→', currentQuestion.choices[currentQuestion.correct_index])
    console.log('Is correct?', isCorrect)
    console.log('===================')

    let reaction = ''

    if (isTimeOut) {
      reaction = "Time's up! Quick, pick faster!"
      setDeweyReaction(reaction)
      setStreak(0)
    } else if (isCorrect) {
      const newScore = score + pointsPerQuestion
      const newStreak = streak + 1
      const newCorrectCount = correctCount + 1

      setScore(newScore)
      setStreak(newStreak)
      setCorrectCount(newCorrectCount)

      if (newStreak > bestStreak) {
        setBestStreak(newStreak)
      }

      // Special streak reactions
      if (newStreak === 7) {
        reaction = DEWEY_REACTIONS.streak7
      } else if (newStreak === 5) {
        reaction = DEWEY_REACTIONS.streak5
      } else if (newStreak === 3) {
        reaction = DEWEY_REACTIONS.streak3
      } else {
        reaction = getRandomReaction('correct')
      }
      setDeweyReaction(reaction)
    } else {
      setStreak(0)
      reaction = getRandomReaction('wrong')
      setDeweyReaction(reaction)
    }

    setShowFeedback(true)

    // Speak the reaction if narration is enabled
    if (narrateEnabled && reaction) {
      speakAsDewey(reaction).catch(err => {
        console.warn('Reaction narration failed:', err)
      })
    }

    // Auto-advance to next question after 2 seconds
    setTimeout(() => {
      // Stop any feedback narration before advancing
      stopSpeaking()

      if (currentQuestionIndex < totalQuestions - 1) {
        setCurrentQuestionIndex(prev => prev + 1)
        setSelectedAnswer(null)
        setIsAnswered(false)
        setShowFeedback(false)
        // Don't set timerActive here - let the narration effect handle it
      } else {
        // Quiz complete!
        onComplete({
          category,
          difficulty,
          questions_answered: totalQuestions,
          correct_answers: isCorrect ? correctCount + 1 : correctCount,
          score: isCorrect ? score + pointsPerQuestion : score,
          best_streak: isCorrect && streak + 1 > bestStreak ? streak + 1 : bestStreak
        })
      }
    }, 2000)
  }, [
    currentQuestion,
    currentQuestionIndex,
    totalQuestions,
    score,
    streak,
    bestStreak,
    correctCount,
    pointsPerQuestion,
    category,
    difficulty,
    onComplete,
    isAnswered
  ])

  const skipNarration = () => {
    stopSpeaking()
    setIsNarrating(false)
    setTimerActive(true)
  }

  const toggleNarration = () => {
    if (narrateEnabled) {
      stopSpeaking()
      setIsNarrating(false)
      setTimerActive(true)
    }
    setNarrateEnabled(!narrateEnabled)
  }

  const progress = ((currentQuestionIndex + 1) / totalQuestions) * 100

  return (
    <div className="question-screen">
      {/* Header */}
      <div className="question-header">
        <div className="question-progress">
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <div className="progress-text">
            Question {currentQuestionIndex + 1} of {totalQuestions}
          </div>
        </div>

        <div className="question-stats">
          <div className="stat-item">
            <span className="stat-label">Score</span>
            <span className="stat-value">{score}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Streak</span>
            <span className={`stat-value ${streak >= 3 ? 'hot-streak' : ''}`}>
              {streak > 0 ? `${streak}` : '-'}
            </span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Time</span>
            <span className={`stat-value ${timeLeft <= 3 ? 'time-warning' : ''}`}>
              {timeLeft}s
            </span>
          </div>
        </div>
      </div>

      {/* Narration Indicator */}
      {isNarrating && (
        <div className="narration-indicator">
          <div className="narration-avatar">
            <img src="/dewey-avatar.jpeg" alt="Dewey speaking" className="speaking-avatar" />
          </div>
          <div className="narration-text">
            🔒 Listen to all choices before answering...
          </div>
          <button className="skip-narration-btn" onClick={skipNarration}>
            Skip ⏭️
          </button>
        </div>
      )}

      {/* Question */}
      <div className="question-content">
        <div className="question-text">
          {currentQuestion.question}
        </div>

        {/* Choices */}
        <div className="choices-grid">
          {currentQuestion.choices.map((choice, index) => {
            const isCorrect = index === currentQuestion.correct_index
            const isSelected = index === selectedAnswer
            const showCorrect = isAnswered && isCorrect
            const showWrong = isAnswered && isSelected && !isCorrect

            return (
              <button
                key={index}
                className={`choice-button ${showCorrect ? 'correct' : ''} ${showWrong ? 'wrong' : ''} ${isSelected ? 'selected' : ''} ${isNarrating ? 'locked' : ''}`}
                onClick={() => handleAnswer(index)}
                disabled={isAnswered || isNarrating}
              >
                <span className="choice-letter">{String.fromCharCode(65 + index)}</span>
                <span className="choice-text">{choice}</span>
                {showCorrect && <span className="choice-icon">✓</span>}
                {showWrong && <span className="choice-icon">✗</span>}
              </button>
            )
          })}
        </div>

        {/* Dewey Reaction */}
        {showFeedback && (
          <div className={`dewey-reaction ${selectedAnswer === currentQuestion.correct_index ? 'positive' : 'negative'}`}>
            <div className="reaction-avatar">
              <img src="/dewey-avatar.jpeg" alt="Dewey" />
            </div>
            <div className="reaction-text">{deweyReaction}</div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="question-footer">
        <div className="footer-left">
          <button className="quit-button" onClick={onQuit}>
            Quit Trivia
          </button>
          <button
            className={`narration-toggle-btn ${narrateEnabled ? 'active' : 'muted'}`}
            onClick={toggleNarration}
            title={narrateEnabled ? 'Voice narration enabled' : 'Voice narration disabled'}
          >
            {narrateEnabled ? '🔊' : '🔇'} Dewey Voice
          </button>
        </div>
        <div className="difficulty-badge" style={{ '--difficulty-color': difficultyConfig.color }}>
          {difficulty.toUpperCase()} - x{difficultyConfig.multiplier} Points
        </div>
      </div>
    </div>
  )
}

QuestionScreen.propTypes = {
  questions: PropTypes.arrayOf(PropTypes.shape({
    id: PropTypes.string.isRequired,
    question: PropTypes.string.isRequired,
    choices: PropTypes.arrayOf(PropTypes.string).isRequired,
    correct_index: PropTypes.number.isRequired
  })).isRequired,
  category: PropTypes.string.isRequired,
  difficulty: PropTypes.string.isRequired,
  onComplete: PropTypes.func.isRequired,
  onQuit: PropTypes.func.isRequired
}
