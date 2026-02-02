// frontend/src/components/VoiceAssistantPanel.jsx

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import PropTypes from 'prop-types'
import PanelShell from '../panels/_kit/PanelShell'

// WebSocket manager extracted outside component for performance
class VoiceWebSocketManager {
  constructor(url, handlers) {
    this.url = url
    this.handlers = handlers
    this.ws = null
    this.reconnectTimer = null
    this.reconnectAttempts = 0
  }

  connect() {
    try {
      this.ws = new WebSocket(this.url)

      this.ws.onopen = () => {
        this.reconnectAttempts = 0
        this.handlers.onConnect?.()
      }

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          this.handlers.onMessage?.(message)
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err)
        }
      }

      this.ws.onclose = () => {
        this.handlers.onDisconnect?.()
        this.attemptReconnect()
      }

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        this.handlers.onError?.(error)
      }
    } catch (err) {
      console.error('Failed to create WebSocket:', err)
      this.attemptReconnect()
    }
  }

  attemptReconnect() {
    if (this.reconnectAttempts >= 5) return

    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts++
      this.connect()
    }, 2000 * Math.pow(2, this.reconnectAttempts))
  }

  send(message) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    }
  }

  disconnect() {
    clearTimeout(this.reconnectTimer)
    this.ws?.close()
  }
}

/**
 * Voice Assistant Panel Component
 * Manages voice profiles, sessions, and controller assignments
 */
function VoiceAssistantPanel() {
  // Session & connection state
  const [wsConnected, setWsConnected] = useState(false)
  const [activeSession, setActiveSession] = useState(null)
  const [activePreset, setActivePreset] = useState(null)
  const [sessionIdInput, setSessionIdInput] = useState('')

  // Profile state
  const [profiles, setProfiles] = useState([])
  const [selectedUser, setSelectedUser] = useState('dad')
  const [profileForm, setProfileForm] = useState({
    username: '',
    stt_engine: 'google',
    tts_engine: 'pyttsx3',
    tts_voice: 'default',
    wake_word: 'arcade'
  })

  // Controller assignments from session
  const [controllerAssignments, setControllerAssignments] = useState({
    1: null,
    2: null,
    3: null,
    4: null
  })

  // UI state
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  // WebSocket manager ref
  const wsManager = useRef(null)

  // Flash message handlers
  const showError = useCallback((msg) => {
    setError(msg)
    setTimeout(() => setError(null), 3000)
  }, [])

  const showSuccess = useCallback((msg) => {
    setSuccess(msg)
    setTimeout(() => setSuccess(null), 3000)
  }, [])

  // WebSocket message handler
  const handleWsMessage = useCallback((message) => {
    switch (message.type) {
      case 'session_updated':
        setActiveSession(message.session)
        if (message.session?.controller_assignments) {
          setControllerAssignments(message.session.controller_assignments)
        }
        break
      case 'session_started':
        setActiveSession(message.data)
        showSuccess('Session started successfully')
        break
      default:
        console.log('Unknown WebSocket message:', message)
    }
  }, [showSuccess])

  // Initialize WebSocket connection
  useEffect(() => {
    wsManager.current = new VoiceWebSocketManager(
      'ws://localhost:8787/voice_assistant/ws',
      {
        onConnect: () => setWsConnected(true),
        onDisconnect: () => setWsConnected(false),
        onMessage: handleWsMessage,
        onError: (err) => showError('WebSocket error')
      }
    )

    wsManager.current.connect()

    return () => {
      wsManager.current?.disconnect()
    }
  }, [handleWsMessage, showError])

  // Load profiles on mount
  useEffect(() => {
    loadProfiles()
  }, [])

  // Load available profiles
  const loadProfiles = async () => {
    try {
      const response = await fetch('http://localhost:8787/api/voice_assistant/profiles')
      if (response.ok) {
        const data = await response.json()
        setProfiles(data)
      }
    } catch (err) {
      console.error('Failed to load profiles:', err)
    }
  }

  // Load specific user profile
  const loadUserProfile = useCallback(async (username) => {
    try {
      const response = await fetch(`http://localhost:8787/api/voice_assistant/profiles/${username}`)
      if (response.ok) {
        const profile = await response.json()
        setProfileForm(profile)
      }
    } catch (err) {
      showError(`Failed to load profile for ${username}`)
    }
  }, [showError])

  // Start session with preset
  const startPresetSession = useCallback(async (preset) => {
    setLoading(true)
    try {
      const response = await fetch('http://localhost:8787/api/voice_assistant/session/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preset })
      })

      if (response.ok) {
        const data = await response.json()
        setActivePreset(preset)
        setActiveSession(data)
        showSuccess(`Started ${preset} session`)
      } else {
        showError('Failed to start session')
      }
    } catch (err) {
      showError('Network error starting session')
    } finally {
      setLoading(false)
    }
  }, [showError, showSuccess])

  // Switch to different session
  const switchSession = useCallback(async () => {
    if (!sessionIdInput.trim()) {
      showError('Please enter a session ID')
      return
    }

    setLoading(true)
    try {
      const response = await fetch('http://localhost:8787/api/voice_assistant/session/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionIdInput })
      })

      if (response.ok) {
        wsManager.current?.send({
          type: 'session_switch',
          data: { session_id: sessionIdInput }
        })
        showSuccess('Switched session')
        setSessionIdInput('')
      } else {
        showError('Failed to switch session')
      }
    } catch (err) {
      showError('Network error switching session')
    } finally {
      setLoading(false)
    }
  }, [sessionIdInput, showError, showSuccess])

  // Save profile
  const saveProfile = useCallback(async () => {
    if (!profileForm.username.trim()) {
      showError('Username is required')
      return
    }

    setLoading(true)
    try {
      const response = await fetch('http://localhost:8787/api/voice_assistant/profiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profileForm)
      })

      if (response.ok) {
        showSuccess('Profile saved successfully')
        loadProfiles()
      } else {
        showError('Failed to save profile')
      }
    } catch (err) {
      showError('Network error saving profile')
    } finally {
      setLoading(false)
    }
  }, [profileForm, showError, showSuccess])

  // Memoized preset buttons
  const presetButtons = useMemo(() => [
    { id: 'dad_solo', label: 'Dad Solo', icon: '👤' },
    { id: 'full_family', label: 'Full Family', icon: '👨‍👩‍👧‍👦' },
    { id: 'custom', label: 'Custom', icon: '⚙️' }
  ], [])

  // Memoized controller grid
  const controllerGrid = useMemo(() => {
    return [1, 2, 3, 4].map(port => ({
      port,
      user: controllerAssignments[port] || 'Unassigned'
    }))
  }, [controllerAssignments])

  return (
    <PanelShell
      title="Voice Assistant"
      subtitle="Session Setup & Configuration"
      icon={<img src="/vicky-avatar.jpeg" alt="Vicky" className="panel-avatar" />}
      status={wsConnected ? 'online' : 'offline'}
    >
      <div className="voice-assistant-panel">
        {/* Flash messages */}
        {error && <div className="flash-error">{error}</div>}
        {success && <div className="flash-success">{success}</div>}

        {/* Session presets section */}
        <section className="preset-section">
          <h3>Quick Start Presets</h3>
          <div className="preset-buttons">
            {presetButtons.map(preset => (
              <button
                key={preset.id}
                className={`preset-btn ${activePreset === preset.id ? 'active' : ''}`}
                onClick={() => startPresetSession(preset.id)}
                disabled={loading}
              >
                <span className="preset-icon">{preset.icon}</span>
                <span className="preset-label">{preset.label}</span>
              </button>
            ))}
          </div>
        </section>

        {/* Controller assignments grid */}
        <section className="controller-section">
          <h3>Controller Assignments</h3>
          <div className="controller-grid">
            {controllerGrid.map(controller => (
              <div key={controller.port} className="controller-port">
                <div className="port-number">Port {controller.port}</div>
                <div className="port-user">{controller.user}</div>
              </div>
            ))}
          </div>
        </section>

        {/* Profile editor section */}
        <section className="profile-section">
          <h3>Voice Profile Editor</h3>

          <div className="profile-selector">
            <label>Select User:</label>
            <select
              value={selectedUser}
              onChange={(e) => {
                setSelectedUser(e.target.value)
                loadUserProfile(e.target.value)
              }}
              className="profile-dropdown"
            >
              <option value="dad">Dad</option>
              <option value="mom">Mom</option>
              <option value="tim">Tim</option>
              <option value="sarah">Sarah</option>
              <option value="guest">Guest</option>
            </select>
          </div>

          <div className="profile-form">
            <div className="form-field">
              <label>Username:</label>
              <input
                type="text"
                value={profileForm.username}
                onChange={(e) => setProfileForm({...profileForm, username: e.target.value})}
                className="form-input"
              />
            </div>

            <div className="form-field">
              <label>STT Engine:</label>
              <select
                value={profileForm.stt_engine}
                onChange={(e) => setProfileForm({...profileForm, stt_engine: e.target.value})}
                className="form-input"
              >
                <option value="google">Google</option>
                <option value="whisper">Whisper</option>
                <option value="azure">Azure</option>
              </select>
            </div>

            <div className="form-field">
              <label>TTS Engine:</label>
              <select
                value={profileForm.tts_engine}
                onChange={(e) => setProfileForm({...profileForm, tts_engine: e.target.value})}
                className="form-input"
              >
                <option value="pyttsx3">Pyttsx3</option>
                <option value="elevenlabs">ElevenLabs</option>
                <option value="azure">Azure</option>
              </select>
            </div>

            <div className="form-field">
              <label>TTS Voice:</label>
              <input
                type="text"
                value={profileForm.tts_voice}
                onChange={(e) => setProfileForm({...profileForm, tts_voice: e.target.value})}
                className="form-input"
              />
            </div>

            <div className="form-field">
              <label>Wake Word:</label>
              <input
                type="text"
                value={profileForm.wake_word}
                onChange={(e) => setProfileForm({...profileForm, wake_word: e.target.value})}
                className="form-input"
              />
            </div>

            <button
              className="save-profile-btn"
              onClick={saveProfile}
              disabled={loading}
            >
              Save Profile
            </button>
          </div>
        </section>

        {/* Session control section */}
        <section className="session-control">
          <h3>Session Control</h3>

          {activeSession && (
            <div className="active-session-info">
              <strong>Active Session:</strong> {activeSession.id}
              <br />
              <strong>Status:</strong> {activeSession.status || 'Active'}
            </div>
          )}

          <div className="session-switch">
            <input
              type="text"
              placeholder="Enter session ID"
              value={sessionIdInput}
              onChange={(e) => setSessionIdInput(e.target.value)}
              className="session-input"
            />
            <button
              onClick={switchSession}
              disabled={loading || !sessionIdInput}
              className="switch-btn"
            >
              Switch Session
            </button>
          </div>

          <button
            className="start-session-btn"
            onClick={() => startPresetSession('custom')}
            disabled={loading}
          >
            Start New Session
          </button>
        </section>
      </div>
    </PanelShell>
  )
}

VoiceAssistantPanel.propTypes = {
  // No props required for this component
}

export default React.memo(VoiceAssistantPanel)