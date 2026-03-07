import { useState, useRef, useEffect } from 'react'

/**
 * useNewsChat – lightweight hook for chatting with Dewey about gaming news.
 * Uses the gateway's /api/ai/chat endpoint with Gemini.
 */
export default function useNewsChat(headlines = []) {
    const [messages, setMessages] = useState([])
    const [input, setInput] = useState('')
    const [loading, setLoading] = useState(false)
    const scrollRef = useRef(null)

    // Auto-scroll on new messages
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight
        }
    }, [messages])

    // Build context from current headlines
    const buildContext = () => {
        const topHeadlines = headlines.slice(0, 10).map((h, i) =>
            `${i + 1}. ${h.title} (${h.source || 'Unknown'}) – ${h.description || ''}`
        ).join('\n')
        return `You are Dewey, a friendly arcade gaming assistant. The user is viewing gaming news headlines. Here are the current top headlines:\n\n${topHeadlines}\n\nHelp the user discuss, summarize, or explore these gaming news stories. Be conversational, warm, and knowledgeable about gaming.`
    }

    const sendMessage = async (text) => {
        if (!text.trim() || loading) return

        const userMsg = { role: 'user', text: text.trim(), ts: Date.now() }
        setMessages(prev => [...prev, userMsg])
        setInput('')
        setLoading(true)

        try {
            const res = await fetch('/api/ai/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text.trim(),
                    provider: 'gemini',
                    systemPrompt: buildContext(),
                    history: messages.slice(-10).map(m => ({
                        role: m.role === 'user' ? 'user' : 'assistant',
                        content: m.text
                    }))
                })
            })

            if (!res.ok) throw new Error(`Chat failed: ${res.status}`)
            const data = await res.json()
            const reply = data.reply || data.response || data.message || 'Sorry, I couldn\'t process that.'

            setMessages(prev => [...prev, { role: 'assistant', text: reply, ts: Date.now() }])
        } catch (err) {
            console.error('[NewsChat] Error:', err)
            setMessages(prev => [...prev, {
                role: 'assistant',
                text: 'Sorry, I had trouble responding. Try again in a moment!',
                ts: Date.now()
            }])
        } finally {
            setLoading(false)
        }
    }

    return { messages, input, setInput, loading, sendMessage, scrollRef }
}
