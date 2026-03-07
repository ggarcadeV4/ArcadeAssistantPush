import { useState, useCallback } from 'react'
import { chat as aiChat } from '../../../services/aiClient'
import { speakAsDewey } from '../../../services/ttsClient'

const MAX_CONTEXT_MESSAGES = 12

export function useNewsChat(headlines = []) {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [isSpeaking, setIsSpeaking] = useState(false)

  const send = useCallback(async (userText) => {
    const trimmed = userText.trim()
    if (!trimmed) return

    // Add user message
    const userMessage = { role: 'user', content: trimmed, timestamp: new Date() }
    setMessages(prev => [...prev, userMessage])

    if (!Array.isArray(headlines) || headlines.length === 0) {
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
      // Build context with headlines
      const headlinesContext = headlines.slice(0, 10).map((h, i) =>
        `${i + 1}. ${h.source}: "${h.title}" (${h.published_relative})`
      ).join('\n')

      const systemPrompt = [
        'You are Dewey, the gaming companion at G&G Arcade.',
        'You are helping users discuss gaming news and understand industry trends.',
        'Keep responses conversational and insightful (2-3 short paragraphs max).',
        '',
        'CURRENT GAMING HEADLINES:',
        headlinesContext || '(No headlines loaded yet)',
        '',
        'When discussing news, reference specific headlines by source and title.',
        'Provide context, analysis, and implications of gaming industry news.',
        'Be enthusiastic but balanced - hype and criticism where appropriate.'
      ].join('\n')

      const chatHistory = messages.slice(-MAX_CONTEXT_MESSAGES).map(msg => ({
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
        temperature: 0.7,
        max_tokens: 500,
        metadata: { panel: 'gaming-news', character: 'dewey' }
      })

      const assistantMessage = {
        role: 'assistant',
        content: response.message?.content || 'Sorry, I had trouble responding.',
        timestamp: new Date()
      }

      setMessages(prev => [...prev, assistantMessage])

      // Speak the response using TTS
      setIsSpeaking(true)
      speakAsDewey(assistantMessage.content)
        .catch(err => {
          console.warn('[useNewsChat] TTS failed:', err)
        })
        .finally(() => {
          setIsSpeaking(false)
        })
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
  }, [headlines, messages])

  const clearMessages = useCallback(() => {
    setMessages([])
    setError(null)
  }, [])

  return { messages, loading, error, isSpeaking, send, clearMessages }
}
