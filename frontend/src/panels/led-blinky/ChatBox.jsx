import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useBlinkyChat } from './useBlinkyChat'
import { speakAsBlinky } from '../../services/ttsClient'

export default function ChatBox() {
  const { loading, error, history, send } = useBlinkyChat()
  const [autoSpeak, setAutoSpeak] = useState(true) // Default to TRUE so audio plays automatically
  const [isSpeaking, setIsSpeaking] = useState(false)
  const lastPlaybackIdRef = useRef(0)
  const lastSpokenRef = useRef(null)

  const latestAssistant = useMemo(() => {
    if (!history || history.length === 0) {
      return null
    }
    for (let i = history.length - 1; i >= 0; i -= 1) {
      if (history[i].role === 'assistant' && history[i].content) {
        return history[i]
      }
    }
    return null
  }, [history])

  const handleSubmit = useCallback((e) => {
    e.preventDefault()
    const input = e.target.q
    const value = input.value.trim()
    if (value && !loading) {
      send(value)
      input.value = ''
    }
  }, [send, loading])

  const playAssistantMessage = useCallback(
    async (content) => {
      if (!content) return
      const playbackId = Date.now()
      lastPlaybackIdRef.current = playbackId
      lastSpokenRef.current = content
      setIsSpeaking(true)
      try {
        await speakAsBlinky(content)
      } catch (err) {
        console.warn('[LED Blinky TTS] Failed to speak response:', err)
      } finally {
        if (lastPlaybackIdRef.current === playbackId) {
          setIsSpeaking(false)
        }
      }
    },
    []
  )

  useEffect(() => {
    if (!autoSpeak) {
      return
    }
    if (!latestAssistant || lastSpokenRef.current === latestAssistant.content) {
      return
    }
    playAssistantMessage(latestAssistant.content)
  }, [autoSpeak, latestAssistant, playAssistantMessage])

  return (
    <div className="led-chatbox" role="region" aria-label="AI Assistant">
      <form onSubmit={handleSubmit} className="led-chatbox-form">
        <div className="led-chatbox-input-group">
          <input
            name="q"
            className="led-chatbox-input"
            placeholder="Ask LED Blinky assistant..."
            aria-label="Ask LED Blinky assistant"
            disabled={loading}
          />
          <button
            type="submit"
            className="led-chatbox-submit"
            disabled={loading}
            aria-label="Send message"
          >
            {loading ? '...' : 'Send'}
          </button>
        </div>
      </form>

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '12px',
          marginTop: '8px',
          marginBottom: '12px',
          flexWrap: 'wrap'
        }}
      >
        <button
          type="button"
          onClick={() => playAssistantMessage(latestAssistant?.content)}
          disabled={!latestAssistant || loading}
          style={{
            padding: '6px 12px',
            borderRadius: '6px',
            border: '1px solid #7c3aed',
            background: latestAssistant ? '#111827' : '#1f2937',
            color: '#e5e7eb',
            fontSize: '12px',
            cursor: latestAssistant && !loading ? 'pointer' : 'not-allowed',
            opacity: latestAssistant && !loading ? 1 : 0.5
          }}
        >
          {isSpeaking ? 'Playing…' : 'Play Last Reply'}
        </button>
        <label
          style={{
            color: '#d1d5db',
            fontSize: '12px',
            display: 'flex',
            alignItems: 'center',
            gap: '6px'
          }}
        >
          <input
            type="checkbox"
            checked={autoSpeak}
            onChange={(event) => setAutoSpeak(event.target.checked)}
          />
          Auto-play replies
        </label>
      </div>

      <div className="led-chatbox-responses" aria-live="polite">
        {history && history.length > 0 ? (
          history.map((entry, index) => {
            console.log(`[ChatBox] Rendering message ${index}:`, entry.role, entry.content?.substring(0, 30))
            return (
              <div
                key={`${entry.role}-${index}-${entry.content?.slice(0, 12) || 'msg'}`}
                style={{
                  background: entry.role === 'assistant' ? '#101010' : '#050505',
                  border: '1px solid #1f2937',
                  borderRadius: '8px',
                  padding: '10px',
                  marginBottom: '8px'
                }}
              >
                <div
                  style={{
                    fontSize: '11px',
                    textTransform: 'uppercase',
                    color: '#9ca3af',
                    marginBottom: '4px'
                  }}
                >
                  {entry.role === 'assistant' ? 'LED Assistant' : 'You'}
                </div>
                <div style={{ color: '#d1d5db', fontSize: '13px', lineHeight: 1.4 }}>
                  {entry.content}
                </div>
              </div>
            )
          })
        ) : (
          !loading &&
          !error && (
            <div style={{ color: '#6b7280', fontSize: '13px', textAlign: 'center', padding: '12px' }}>
              Start the conversation by asking a question about LED wiring or hardware.
            </div>
          )
        )}

        {loading && (
          <div className="led-chatbox-loading" aria-label="Assistant is thinking">
            <span>dY'- Thinking...</span>
          </div>
        )}

        {error && (
          <div className="led-chatbox-error" role="alert">
            <span>�?O {error.message || 'Something went wrong. Please try again.'}</span>
          </div>
        )}
      </div>
    </div>
  )
}
