import { useState, useCallback, useEffect, useRef } from 'react'
import { chat as aiChat } from '../../../services/aiClient'
import { speakAsDewey, stopSpeaking } from '../../../services/ttsClient'

const MAX_CONTEXT_MESSAGES = 12

export function useNewsChat(headlines = []) {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [isSpeaking, setIsSpeaking] = useState(false)

  const messagesRef = useRef(messages)
  const cachedHeadlinesRef = useRef(Array.isArray(headlines) ? headlines : [])
  const speakTokenRef = useRef(0)
  const lastSpokenContentRef = useRef('')
  const lastSpokenAtRef = useRef(0)

  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  useEffect(() => {
    if (Array.isArray(headlines) && headlines.length > 0) {
      cachedHeadlinesRef.current = headlines
    }
  }, [headlines])

  useEffect(() => {
    return () => {
      // Prevent any late TTS completion handlers from mutating state after unmount.
      speakTokenRef.current += 1
      setIsSpeaking(false)
      stopSpeaking()
    }
  }, [])

  const send = useCallback(async (userText) => {
    const trimmed = userText.trim()
    if (!trimmed) return

    if (isSpeaking) {
      stopSpeaking()
      setIsSpeaking(false)
    }

    const userMessage = { role: 'user', content: trimmed, timestamp: new Date() }
    setMessages(prev => [...prev, userMessage])

    const activeHeadlines = Array.isArray(headlines) && headlines.length > 0
      ? headlines
      : cachedHeadlinesRef.current

    // Only block the very first turn when we have zero headline context.
    // Follow-up turns continue with conversation context.
    if ((!Array.isArray(activeHeadlines) || activeHeadlines.length === 0) && messagesRef.current.length === 0) {
      const waitingMessage = {
        role: 'assistant',
        content: "I'm still loading today's gaming headlines so I can give you the real scoop. Give me a moment and try again once they appear!",
        timestamp: new Date(),
        isInfo: true
      }
      setMessages(prev => [...prev, waitingMessage])
      return
    }

    setLoading(true)
    setError(null)

    try {
      const headlinesContext = (Array.isArray(activeHeadlines) ? activeHeadlines : [])
        .slice(0, 10)
        .map((h, i) => `${i + 1}. ${h.source}: "${h.title}" (${h.published_relative})`)
        .join('\n')

      const systemPrompt = [
        'You are Dewey, the gaming companion at G&G Arcade.',
        'You explain gaming industry news clearly and directly.',
        'Keep responses concise: 2-4 sentences, usually under 90 words unless asked for detail.',
        'Do not ramble, do not repeat yourself, and avoid long preambles.',
        '',
        'CURRENT GAMING HEADLINES:',
        headlinesContext || '(No headlines loaded yet - use chat context and note headlines are still syncing if needed.)',
        '',
        'When possible, reference specific headlines by source and title.',
        'Focus on impact, risks, and what it means for players/developers.'
      ].join('\n')

      const chatHistory = messagesRef.current.slice(-MAX_CONTEXT_MESSAGES).map(msg => ({
        role: msg.role,
        content: msg.content
      }))

      const response = await aiChat({
        provider: 'gemini',
        scope: 'state',
        messages: [
          { role: 'system', content: systemPrompt },
          ...chatHistory,
          { role: 'user', content: trimmed }
        ],
        temperature: 0.5,
        max_tokens: 260,
        metadata: { panel: 'gaming-news', character: 'dewey' }
      })

      const assistantMessage = {
        role: 'assistant',
        content: response.message?.content || 'Sorry, I had trouble responding.',
        timestamp: new Date()
      }

      setMessages(prev => [...prev, assistantMessage])

      const speechText = (assistantMessage.content || '').trim()
      if (speechText) {
        const now = Date.now()
        const isRapidDuplicate =
          speechText === lastSpokenContentRef.current &&
          (now - lastSpokenAtRef.current) < 7000

        if (isRapidDuplicate) {
          console.warn('[useNewsChat] Suppressing rapid duplicate TTS playback')
        } else {
          lastSpokenContentRef.current = speechText
          lastSpokenAtRef.current = now

          const token = ++speakTokenRef.current
          setIsSpeaking(true)

          speakAsDewey(speechText)
            .catch(err => {
              console.warn('[useNewsChat] TTS failed:', err)
            })
            .finally(() => {
              if (speakTokenRef.current === token) {
                setIsSpeaking(false)
              }
            })
        }
      }
    } catch (err) {
      console.error('News chat error:', err)
      setError(err.message || 'Failed to get response')

      const errorMessage = {
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        timestamp: new Date(),
        isError: true
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setLoading(false)
    }
  }, [headlines, isSpeaking])

  const clearMessages = useCallback(() => {
    setMessages([])
    setError(null)
  }, [])

  return { messages, loading, error, isSpeaking, send, clearMessages }
}
