import React, { useState, useRef } from 'react'

/**
 * GunnerChatSidebar — AI assistant chat panel on the right side
 * Displays message history and handles text input
 */
export default function GunnerChatSidebar({ chatState, onSend }) {
    const [input, setInput] = useState('')
    const messagesEndRef = useRef(null)
    const { history = [], loading = false } = chatState || {}

    const handleSubmit = (e) => {
        e.preventDefault()
        if (!input.trim() || loading) return
        onSend(input.trim())
        setInput('')
    }

    // Welcome message when no history
    const displayMessages = history.length === 0
        ? [{ role: 'assistant', content: "Welcome! I've detected your Retro Shooter hardware. Let's get it configured. Do you want to start with devices or calibration?" }]
        : history

    return (
        <aside className="gunner-chat-sidebar">
            {/* Header */}
            <div className="gunner-chat-sidebar__header">
                <img
                    className="gunner-chat-sidebar__avatar"
                    src="/gunner-avatar.jpeg"
                    alt="Gunner"
                    onError={e => { e.target.src = '/characters/gunner-char.png' }}
                />
                <div>
                    <div className="gunner-chat-sidebar__name">Gunner Assistant</div>
                    <div className="gunner-chat-sidebar__status">● ONLINE</div>
                </div>
            </div>

            {/* Messages */}
            <div className="gunner-chat-sidebar__messages">
                {displayMessages.map((msg, i) => (
                    <div key={i} className={`gunner-chat-msg gunner-chat-msg--${msg.role}`}>
                        <div className="gunner-chat-msg__role">
                            {msg.role === 'assistant' ? '[Gunner]:' : '[User]:'}
                        </div>
                        {msg.content}
                    </div>
                ))}
                {loading && (
                    <div className="gunner-chat-msg gunner-chat-msg--assistant">
                        <div className="gunner-chat-msg__role">[Gunner]:</div>
                        Analyzing...
                    </div>
                )}
                <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <form className="gunner-chat-sidebar__input-area" onSubmit={handleSubmit}>
                <input
                    className="gunner-chat-sidebar__input"
                    type="text"
                    placeholder="Enter command..."
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    disabled={loading}
                />
                <button
                    className="gunner-chat-sidebar__send"
                    type="submit"
                    disabled={loading}
                >
                    ▶
                </button>
            </form>
        </aside>
    )
}
