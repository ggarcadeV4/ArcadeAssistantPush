import React from 'react'
import useNewsChat from './useNewsChat'
import './NewsChatSidebar.css'

export default function NewsChatSidebar({ headlines, onClose }) {
    const {
        messages, input, setInput, loading,
        sendMessage, scrollRef, isRecording, toggleMic
    } = useNewsChat(headlines)

    const handleSubmit = (e) => {
        e.preventDefault()
        sendMessage(input)
    }

    return (
        <div className="news-chat-sidebar">
            {/* Header */}
            <div className="news-chat-header">
                <h3>💬 Chat with Dewey</h3>
                <button className="news-chat-close" onClick={onClose} title="Close chat">✕</button>
            </div>

            {/* Messages */}
            <div className="news-chat-messages" ref={scrollRef}>
                {messages.length === 0 && (
                    <div className="news-chat-empty">
                        <span className="empty-icon">🎮</span>
                        Ask Dewey about today&apos;s gaming news!
                        <span className="empty-hint">Try: &quot;Summarize the top stories&quot; or &quot;What&apos;s trending?&quot;</span>
                    </div>
                )}
                {messages.map((msg, i) => (
                    <div key={i} className={`news-chat-bubble ${msg.role}`}>
                        {msg.text}
                    </div>
                ))}
                {loading && (
                    <div className="typing-indicator">Dewey is thinking…</div>
                )}
            </div>

            {/* Input */}
            <form className="news-chat-input-area" onSubmit={handleSubmit}>
                <button
                    type="button"
                    className={`news-chat-mic ${isRecording ? 'recording' : ''}`}
                    onClick={toggleMic}
                    title={isRecording ? 'Stop listening' : 'Voice input'}
                >
                    {isRecording ? '⏹' : '🎤'}
                </button>
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder={isRecording ? 'Listening...' : 'Ask about these headlines...'}
                    disabled={loading || isRecording}
                    autoFocus
                />
                <button type="submit" className="news-chat-send" disabled={loading || !input.trim()}>
                    Send
                </button>
            </form>
        </div>
    )
}
