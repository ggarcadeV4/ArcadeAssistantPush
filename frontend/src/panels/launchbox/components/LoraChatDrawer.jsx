import React from 'react'

export default function LoraChatDrawer({
  open,
  onClose,
  isRecording,
  isChatLoading,
  messages,
  input,
  onInputChange,
  onInputKeyPress,
  onToggleMic,
  onSend,
  voiceBars,
  memoizedStyles,
  chatMessagesRef,
  ChatMessageComponent
}) {
  if (!open) return null

  return (
    <>
      <div className="panel-chat-overlay" onClick={onClose} />
      <div className="panel-chat-sidebar" role="dialog" aria-label="Chat with LoRa">
        <div className="chat-header">
          <img src="/lora-avatar.jpeg" alt="LoRa" className="chat-avatar" />
          <div className="chat-header-info">
            <h3>Chat with LoRa</h3>
            {isRecording && (
              <div className="voice-active-indicator">
                <span className="voice-wave-icon">〰️</span>
                Voice Active
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            className="chat-close-btn"
            aria-label="Close chat"
          >
            ×
          </button>
        </div>

        <div className="chat-messages" ref={chatMessagesRef}>
          {messages.map((msg, idx) => (
            <ChatMessageComponent
              key={idx}
              message={msg.text}
              role={msg.role}
            />
          ))}
          {isChatLoading && (
            <div className="chat-message assistant">
              <div className="message-bubble">
                <span className="typing-indicator">●●●</span>
              </div>
            </div>
          )}
        </div>

        {isRecording && (
          <div className="voice-visualization">
            <div className="voice-bars">
              {voiceBars.map((_, i) => (
                <div key={i} className="voice-bar" style={memoizedStyles.voiceBarDelays[i]} />
              ))}
            </div>
            <p className="voice-status">Listening...</p>
          </div>
        )}

        <div className="chat-input-container">
          <div className="chat-input-row">
            <input
              type="text"
              className="chat-input-field"
              value={input}
              onChange={onInputChange}
              onKeyPress={onInputKeyPress}
              placeholder={isRecording ? 'Listening...' : 'Type your message or use voice input...'}
              aria-label="Chat with LoRa"
              disabled={isChatLoading}
            />
            <button
              className={`chat-voice-btn ${isRecording ? 'recording' : ''}`}
              onClick={onToggleMic}
              title={isRecording ? 'Stop voice input' : 'Start voice input'}
              aria-label={isRecording ? 'Stop voice input' : 'Start voice input'}
            >
              {isRecording ? (
                <span style={memoizedStyles.stopIcon}>⏹️</span>
              ) : (
                <img src="/lora-mic.png" alt="Microphone" style={memoizedStyles.micIcon} />
              )}
            </button>
            <button
              className="chat-send-btn-sidebar"
              onClick={onSend}
              disabled={isChatLoading || !input.trim()}
              aria-label="Send message"
            >
              ➤
            </button>
          </div>
        </div>
      </div>
    </>
  )
}