import { useState, useRef, useEffect } from 'react'

/**
 * useNewsChat – lightweight hook for chatting with Dewey about gaming news.
 * Uses the gateway's /api/ai/chat endpoint with Gemini.
 */
export default function useNewsChat(headlines = []) {
    const [messages, setMessages] = useState([])
    const [input, setInput] = useState('')
    const [loading, setLoading] = useState(false)
    const [isRecording, setIsRecording] = useState(false)
    const scrollRef = useRef(null)
    const recognitionRef = useRef(null)

    // Auto-scroll on new messages
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight
        }
    }, [messages])

    // Build system prompt from current headlines
    const buildSystemPrompt = () => {
        if (!headlines || headlines.length === 0) {
            return `You are Dewey, a friendly arcade gaming assistant. The user opened the Gaming News chat. No headlines are loaded yet — help them with general gaming news topics, or suggest they wait a moment for headlines to appear on the page.`
        }
        const topHeadlines = headlines.slice(0, 10).map((h, i) =>
            `${i + 1}. ${h.title} (${h.source || 'Unknown'}) – ${h.summary || ''}`
        ).join('\n')
        return `You are Dewey, a friendly arcade gaming assistant. The user is viewing gaming news headlines. Here are the current top headlines:\n\n${topHeadlines}\n\nHelp the user discuss, summarize, or explore these gaming news stories. Be conversational, warm, and knowledgeable about gaming. Keep responses concise but informative.`
    }

    const sendMessage = async (text) => {
        if (!text.trim() || loading) return

        const userMsg = { role: 'user', text: text.trim(), ts: Date.now() }
        setMessages(prev => [...prev, userMsg])
        setInput('')
        setLoading(true)

        try {
            // Build messages array in the format the gateway expects
            const chatMessages = [
                { role: 'user', content: text.trim() }
            ]

            // Add conversation history (last 8 exchanges)
            const historyMessages = messages.slice(-8).map(m => ({
                role: m.role === 'user' ? 'user' : 'assistant',
                content: m.text
            }))

            const allMessages = [...historyMessages, { role: 'user', content: text.trim() }]

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
            // The gateway returns different response shapes depending on provider
            const reply = data.content?.[0]?.text  // Gemini/Claude format
                || data.choices?.[0]?.message?.content  // OpenAI format
                || data.reply
                || data.response
                || data.message
                || 'Sorry, I couldn\'t process that.'

            setMessages(prev => [...prev, { role: 'assistant', text: reply, ts: Date.now() }])
        } catch (err) {
            console.error('[NewsChat] Error:', err)
            setMessages(prev => [...prev, {
                role: 'assistant',
                text: `Dewey's having some trouble: ${err.message}. Try again!`,
                ts: Date.now()
            }])
        } finally {
            setLoading(false)
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
                // Auto-send after voice input
                sendMessage(transcript)
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

    return { messages, input, setInput, loading, sendMessage, scrollRef, isRecording, toggleMic }
}
