import { useState, useRef, useEffect, useCallback } from 'react'

/**
 * useNewsChat – lightweight hook for chatting with Dewey about gaming news.
 * Uses the gateway's /api/ai/chat endpoint with Gemini.
 * Includes TTS via ElevenLabs proxy for voice responses.
 */
export default function useNewsChat(headlines = []) {
    const [messages, setMessages] = useState([])
    const [input, setInput] = useState('')
    const [loading, setLoading] = useState(false)
    const [isRecording, setIsRecording] = useState(false)
    const [isSpeaking, setIsSpeaking] = useState(false)
    const scrollRef = useRef(null)
    const recognitionRef = useRef(null)
    const sendingRef = useRef(false)     // Ref-based guard to prevent echo/duplicate sends
    const audioRef = useRef(null)        // Current audio playback
    const ttsEnabledRef = useRef(true)   // TTS toggle

    // Auto-scroll on new messages
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight
        }
    }, [messages])

    // Cleanup audio on unmount
    useEffect(() => {
        return () => {
            if (audioRef.current) {
                audioRef.current.pause()
                audioRef.current = null
            }
        }
    }, [])

    // Build system prompt from current headlines
    const buildSystemPrompt = () => {
        if (!headlines || headlines.length === 0) {
            return `You are Dewey, a friendly and warm arcade gaming assistant at G&G Arcade. The user opened the Gaming News chat but no headlines are loaded yet. Be conversational and friendly — greet users warmly, ask how they're doing, and chat about gaming in general. You can suggest they check back for headlines or just have a fun gaming conversation.`
        }
        const topHeadlines = headlines.slice(0, 10).map((h, i) =>
            `${i + 1}. ${h.title} (${h.source || 'Unknown'}) – ${h.summary || ''}`
        ).join('\n')
        return `You are Dewey, a friendly and warm arcade gaming assistant at G&G Arcade. You're chatty, enthusiastic about gaming, and love connecting with people.

The user is viewing gaming news headlines. Here are the current top headlines for context:

${topHeadlines}

IMPORTANT: Be conversational FIRST. If the user greets you or asks how you're doing, respond naturally and warmly like a friend — don't immediately launch into headlines. Only discuss specific headlines when the user asks about news, a specific story, or seems interested in the headlines. Keep responses concise but engaging. Vary your language — don't start every response the same way.`
    }

    // TTS: speak Dewey's response via ElevenLabs proxy
    const speakResponse = useCallback(async (text) => {
        if (!ttsEnabledRef.current || !text) return
        try {
            setIsSpeaking(true)
            // Stop any currently playing audio
            if (audioRef.current) {
                audioRef.current.pause()
                audioRef.current = null
            }

            const res = await fetch('/api/voice/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: text.slice(0, 500),  // Limit TTS length
                    voice_id: 't0A4EWIngExKpUqW6AWI',  // Dewey's voice
                    panel: 'dewey-news-chat'
                })
            })

            if (!res.ok) {
                console.warn('[NewsChat TTS] Failed:', res.status)
                setIsSpeaking(false)
                return
            }

            const blob = await res.blob()
            const url = URL.createObjectURL(blob)
            const audio = new Audio(url)
            audioRef.current = audio

            audio.onended = () => {
                setIsSpeaking(false)
                URL.revokeObjectURL(url)
                audioRef.current = null
            }
            audio.onerror = () => {
                setIsSpeaking(false)
                URL.revokeObjectURL(url)
                audioRef.current = null
            }

            await audio.play()
        } catch (err) {
            console.warn('[NewsChat TTS] Error:', err)
            setIsSpeaking(false)
        }
    }, [])

    // Stop TTS playback
    const stopSpeaking = useCallback(() => {
        if (audioRef.current) {
            audioRef.current.pause()
            audioRef.current = null
        }
        setIsSpeaking(false)
    }, [])

    const sendMessage = async (text) => {
        const trimmed = (text || '').trim()
        if (!trimmed || loading) return

        // Ref-based guard: prevents duplicate sends from rapid-fire calls
        if (sendingRef.current) return
        sendingRef.current = true

        const userMsg = { role: 'user', text: trimmed, ts: Date.now() }
        setMessages(prev => [...prev, userMsg])
        setInput('')
        setLoading(true)

        try {
            // Build conversation history from existing messages (last 8 turns)
            const historyMessages = messages.slice(-8).map(m => ({
                role: m.role === 'user' ? 'user' : 'assistant',
                content: m.text
            }))

            const allMessages = [...historyMessages, { role: 'user', content: trimmed }]

            const res = await fetch('/api/ai/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-scope': 'state'
                },
                body: JSON.stringify({
                    provider: 'gemini',
                    system: buildSystemPrompt(),
                    messages: allMessages,
                    temperature: 0.7,
                    max_tokens: 500,
                    panel: 'dewey-news-chat'
                })
            })

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}))
                throw new Error(errData.error || `Chat failed: ${res.status}`)
            }

            const data = await res.json()
            const reply = data.message?.content  // Gateway Gemini adapter: { message: { role, content } }
                || data.content?.[0]?.text  // Claude-compatible format
                || data.choices?.[0]?.message?.content  // OpenAI format
                || data.reply
                || data.response
                || (typeof data.message === 'string' ? data.message : null)
                || 'Sorry, I couldn\'t process that.'

            setMessages(prev => [...prev, { role: 'assistant', text: reply, ts: Date.now() }])

            // Speak the response
            speakResponse(reply)
        } catch (err) {
            console.error('[NewsChat] Error:', err)
            setMessages(prev => [...prev, {
                role: 'assistant',
                text: `Dewey's having some trouble: ${err.message}. Try again!`,
                ts: Date.now()
            }])
        } finally {
            setLoading(false)
            sendingRef.current = false  // Release the guard
        }
    }

    // Voice input via Web Speech API
    const toggleMic = () => {
        if (isRecording) {
            recognitionRef.current?.stop()
            setIsRecording(false)
            return
        }

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
        if (!SpeechRecognition) {
            console.warn('[NewsChat] SpeechRecognition not supported')
            return
        }

        const recognition = new SpeechRecognition()
        recognition.continuous = false
        recognition.interimResults = false
        recognition.lang = 'en-US'

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript
            if (transcript.trim()) {
                setInput(transcript)
                // User must click Send — no auto-send
            }
            setIsRecording(false)
        }

        recognition.onerror = (event) => {
            console.error('[NewsChat] Speech recognition error:', event.error)
            setIsRecording(false)
        }

        recognition.onend = () => {
            setIsRecording(false)
        }

        recognitionRef.current = recognition
        recognition.start()
        setIsRecording(true)
    }

    return {
        messages, input, setInput, loading, sendMessage, scrollRef,
        isRecording, toggleMic, isSpeaking, stopSpeaking,
        ttsEnabled: ttsEnabledRef.current,
        setTtsEnabled: (v) => { ttsEnabledRef.current = v }
    }
}
