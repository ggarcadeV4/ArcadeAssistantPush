import React, { useState, useRef, useEffect, useCallback } from 'react'
import PropTypes from 'prop-types'
import { stopSpeaking } from '../../../services/ttsClient'
import { useNewsChat } from './useNewsChat'
import './NewsChatSidebar.css'

export default function NewsChatSidebar({ isOpen, onClose, headlines }) {
  const [input, setInput] = useState('')
  const [headlineContext, setHeadlineContext] = useState(() =>
    Array.isArray(headlines) ? headlines : []
  )
  const { messages, loading, isSpeaking, send } = useNewsChat(headlineContext)
  const messagesEndRef = useRef(null)
  const sendRef = useRef(send)
  const [isRecording, setIsRecording] = useState(false)
  const [speechSupported, setSpeechSupported] = useState(true)
  const recognitionRef = useRef(null)
  const processingTranscriptRef = useRef(false)
  const lastTranscriptRef = useRef('')
  const micStatusAlertsRef = useRef({ unsupportedNotified: false })
  const hasHeadlineContext = headlineContext.length > 0
  const inputPlaceholder = !hasHeadlineContext
    ? 'Headlines are syncing... you can still ask a follow-up.'
    : isRecording
      ? 'Listening...'
      : 'Ask Dewey about the news...'

  useEffect(() => {
    sendRef.current = send
  }, [send])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (Array.isArray(headlines) && headlines.length > 0) {
      setHeadlineContext(headlines)
    }
  }, [headlines])

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
          setInput(transcript)
          return
        }

        if (processingTranscriptRef.current || transcript === lastTranscriptRef.current) {
          return
        }

        processingTranscriptRef.current = true
        lastTranscriptRef.current = transcript
        setInput(transcript)
        setIsRecording(false)

        setTimeout(() => {
          if (transcript.trim()) {
            sendRef.current(transcript)
            setInput('')
            setTimeout(() => {
              processingTranscriptRef.current = false
            }, 1000)
          } else {
            processingTranscriptRef.current = false
          }
        }, 100)
      }

      recognition.onerror = () => {
        setIsRecording(false)
        processingTranscriptRef.current = false
      }

      recognition.onend = () => {
        setIsRecording(false)
      }

      recognitionRef.current = recognition
      setSpeechSupported(true)
      return recognition
    } catch {
      setSpeechSupported(false)
      return null
    }
  }

  useEffect(() => {
    initializeSpeechRecognition()
    return () => {
      try {
        if (recognitionRef.current) {
          recognitionRef.current.abort()
        }
      } catch {}
      stopSpeaking()
    }
  }, [])

  const stopRecording = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop()
    }
    setIsRecording(false)
  }, [])

  const toggleVoice = () => {
    if (!isRecording) {
      // Mic takes precedence: immediately interrupt TTS before listening.
      stopSpeaking()

      const recognitionInstance = recognitionRef.current || initializeSpeechRecognition()

      if (!recognitionInstance) {
        if (!micStatusAlertsRef.current.unsupportedNotified) {
          micStatusAlertsRef.current.unsupportedNotified = true
        }
        setIsRecording(false)
        return
      }

      setIsRecording(true)

      try {
        recognitionInstance.start()
      } catch {
        setIsRecording(false)
      }
    } else {
      stopRecording()
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!input.trim() || loading || isRecording) return

    // Typing a follow-up also interrupts any ongoing speech.
    stopSpeaking()
    send(input.trim())
    setInput('')
  }

  const handleClose = () => {
    stopRecording()
    stopSpeaking()
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="news-chat-sidebar" role="dialog" aria-label="Chat with Dewey about gaming news">
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
              {isSpeaking ? 'Speaking...' : 'Discuss Gaming News'}
            </span>
          </div>
        </div>
        <button
          className="chat-close-btn"
          onClick={handleClose}
          aria-label="Close chat"
        >
          X
        </button>
      </div>

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
            <p>Ask me about these stories, trends, or likely impact on the industry.</p>
            <div className="quick-questions">
              <button onClick={() => send("What's the most important news today?")}>
                What's most important?
              </button>
              <button onClick={() => send('Any big announcements?')}>
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

      <form className="news-chat-input-form" onSubmit={handleSubmit}>
        <input
          type="text"
          className="news-chat-input"
          placeholder={inputPlaceholder}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading || isRecording}
          aria-label="Chat input"
        />
        {speechSupported && (
          <button
            type="button"
            className={`news-chat-mic-btn ${isRecording ? 'recording' : ''}`}
            onClick={toggleVoice}
            disabled={loading}
            aria-label={isRecording ? 'Stop recording' : 'Start voice input'}
            title={isRecording ? 'Stop recording' : 'Voice input'}
          >
            Mic
          </button>
        )}
        <button
          type="submit"
          className="news-chat-send-btn"
          disabled={loading || !input.trim() || isRecording}
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
