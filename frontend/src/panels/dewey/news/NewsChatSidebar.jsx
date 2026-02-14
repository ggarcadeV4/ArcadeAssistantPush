import React, { useState, useRef, useEffect } from 'react'
import PropTypes from 'prop-types'
import { useNewsChat } from './useNewsChat'
import './NewsChatSidebar.css'

export default function NewsChatSidebar({ isOpen, onClose, headlines }) {
  const [input, setInput] = useState('')
  const [headlineContext, setHeadlineContext] = useState(() =>
    Array.isArray(headlines) ? headlines : []
  )
  const { messages, loading, isSpeaking, send } = useNewsChat(headlineContext)
  const messagesEndRef = useRef(null)
  const [isRecording, setIsRecording] = useState(false)
  const [speechSupported, setSpeechSupported] = useState(true)
  const recognitionRef = useRef(null)
  const processingTranscriptRef = useRef(false)
  const lastTranscriptRef = useRef('')
  const micStatusAlertsRef = useRef({ unsupportedNotified: false })
  const hasHeadlineContext = headlineContext.length > 0
  const inputPlaceholder = !hasHeadlineContext
    ? 'Loading gaming headlines...'
    : isRecording
      ? 'Listening...'
      : 'Ask Dewey about the news...'

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (Array.isArray(headlines) && headlines.length > 0) {
      setHeadlineContext(headlines)
    }
  }, [headlines])

  // Initialize Speech Recognition
  const initializeSpeechRecognition = () => {
    if (typeof window === 'undefined') return null
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      setSpeechSupported(false)
      return null
    }

    try {
      const recognition = new SpeechRecognition()
      recognition.continuous = false
      recognition.interimResults = true
      recognition.lang = 'en-US'
      recognition.maxAlternatives = 1

      recognition.onresult = (event) => {
        const result = event.results[event.results.length - 1]
        const transcript = result[0].transcript

        if (!result.isFinal) {
          console.log('[NewsChatSidebar] Interim:', transcript)
          setInput(transcript)
          return
        }

        console.log('[NewsChatSidebar] Final Transcribed:', transcript)

        if (processingTranscriptRef.current || transcript === lastTranscriptRef.current) {
          console.log('[NewsChatSidebar] Duplicate transcript ignored')
          return
        }

        processingTranscriptRef.current = true
        lastTranscriptRef.current = transcript
        setInput(transcript)
        setIsRecording(false)

        setTimeout(() => {
          if (transcript.trim()) {
            send(transcript)
            setInput('')
            setTimeout(() => {
              processingTranscriptRef.current = false
            }, 1000)
          } else {
            processingTranscriptRef.current = false
          }
        }, 100)
      }

      recognition.onerror = (event) => {
        console.error('[NewsChatSidebar] Speech recognition error:', event.error)
        setIsRecording(false)
        processingTranscriptRef.current = false

        if (event.error === 'not-allowed') {
          console.warn('[NewsChatSidebar] Microphone permission denied')
        } else if (event.error === 'no-speech') {
          console.warn('[NewsChatSidebar] No speech detected')
        }
      }

      recognition.onend = () => {
        setIsRecording(false)
      }

      recognitionRef.current = recognition
      setSpeechSupported(true)
      return recognition
    } catch (error) {
      console.error('[NewsChatSidebar] Failed to initialize speech recognition:', error)
      setSpeechSupported(false)
      return null
    }
  }

  // Initialize speech recognition on mount
  useEffect(() => {
    initializeSpeechRecognition()
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort()
        } catch {}
      }
    }
  }, [])

  // Start/stop voice recording
  const toggleVoice = () => {
    if (!hasHeadlineContext) {
      console.warn('[NewsChatSidebar] Voice input unavailable until headlines load')
      return
    }

    if (!isRecording) {
      const recognitionInstance = recognitionRef.current || initializeSpeechRecognition()

      if (!recognitionInstance) {
        if (!micStatusAlertsRef.current.unsupportedNotified) {
          console.warn('[NewsChatSidebar] Speech recognition not supported in this browser')
          micStatusAlertsRef.current.unsupportedNotified = true
        }
        setIsRecording(false)
        return
      }

      setIsRecording(true)
      console.log('[NewsChatSidebar] Recording started...')

      try {
        recognitionInstance.start()
      } catch (error) {
        console.error('[NewsChatSidebar] Failed to start recognition:', error)
        setIsRecording(false)
      }
    } else {
      stopRecording()
    }
  }

  const stopRecording = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop()
    }
    setIsRecording(false)
    console.log('[NewsChatSidebar] Recording stopped')
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!hasHeadlineContext || !input.trim() || loading || isRecording) return
    send(input.trim())
    setInput('')
  }

  if (!isOpen) return null

  return (
    <div className="news-chat-sidebar" role="dialog" aria-label="Chat with Dewey about gaming news">
      {/* Header */}
      <div className="news-chat-header">
        <div className="chat-header-left">
          <img
            src="/dewey-avatar.jpeg"
            alt="Dewey"
            className={`chat-avatar ${isSpeaking ? 'speaking' : ''}`}
          />
          <div className="chat-header-info">
            <h3>Chat with Dewey</h3>
            <span className="chat-subtitle">
              {isSpeaking ? '🔊 Speaking...' : 'Discuss Gaming News'}
            </span>
          </div>
        </div>
        <button
          className="chat-close-btn"
          onClick={onClose}
          aria-label="Close chat"
        >
          ✕
        </button>
      </div>

      {/* Messages Area */}
      <div className="news-chat-messages">
        {!hasHeadlineContext && (
          <div className="chat-loading-state" role="status">
            <div className="chat-loading-spinner" aria-hidden="true"></div>
            <p>Loading fresh gaming headlines so I have something real to chat about.</p>
          </div>
        )}

        {messages.length === 0 && hasHeadlineContext && (
          <div className="chat-welcome">
            <img src="/dewey-avatar.jpeg" alt="Dewey" className="welcome-avatar" />
            <p>Hey! Ask me about any of these gaming news stories, industry trends, or what it all means for gamers!</p>
            <div className="quick-questions">
              <button onClick={() => send("What's the most important news today?")}>
                What's most important?
              </button>
              <button onClick={() => send("Any big announcements?")}>
                Big announcements?
              </button>
              <button onClick={() => send("What's trending?")}>
                What's trending?
              </button>
            </div>
          </div>
        )}

        {messages.map((msg, index) => (
          <div
            key={index}
            className={`chat-message ${msg.role} ${msg.isError ? 'error' : ''}`}
          >
            {msg.role === 'assistant' && (
              <img src="/dewey-avatar.jpeg" alt="Dewey" className="message-avatar" />
            )}
            <div className="message-bubble">
              <div className="message-content">{msg.content}</div>
              <div className="message-time">
                {msg.timestamp.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="chat-message assistant loading-message">
            <img src="/dewey-avatar.jpeg" alt="Dewey" className="message-avatar" />
            <div className="message-bubble">
              <div className="typing-indicator">
                <div className="typing-dot"></div>
                <div className="typing-dot"></div>
                <div className="typing-dot"></div>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <form className="news-chat-input-form" onSubmit={handleSubmit}>
        <input
          type="text"
          className="news-chat-input"
          placeholder={inputPlaceholder}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading || isRecording || !hasHeadlineContext}
          aria-label="Chat input"
        />
        {speechSupported && (
          <button
            type="button"
            className={`news-chat-mic-btn ${isRecording ? 'recording' : ''}`}
            onClick={toggleVoice}
            disabled={loading || !hasHeadlineContext}
            aria-label={isRecording ? 'Stop recording' : 'Start voice input'}
            title={isRecording ? 'Stop recording' : 'Voice input'}
          >
            🎤
          </button>
        )}
        <button
          type="submit"
          className="news-chat-send-btn"
          disabled={loading || !input.trim() || isRecording || !hasHeadlineContext}
          aria-label="Send message"
        >
          {loading ? '...' : 'Send'}
        </button>
      </form>
    </div>
  )
}

NewsChatSidebar.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  headlines: PropTypes.array
}

NewsChatSidebar.defaultProps = {
  headlines: []
}
