/**
 * MODULE B: ARCADE WIZARD - WebSocket-based Controller Learning
 * 
 * This wizard uses the backend WebSocket for controller detection
 * for real-time input detection from arcade encoders (XInput/keyboard mode).
 * 
 * Governance:
 * - Uses backend InputDetectionService (pygame-based)
 * - Saves via POST /api/wizard/save (with automatic MAME config generation)
 * - Step-by-step learning with visual feedback
 */

import React, { useState, useEffect, useCallback, useRef } from 'react'
import './arcadeWizard.css'

// The step sequence for arcade cabinet learning
const WIZARD_STEPS = [
    { key: 'p1.up', label: 'UP', player: 1, type: 'joystick' },
    { key: 'p1.down', label: 'DOWN', player: 1, type: 'joystick' },
    { key: 'p1.left', label: 'LEFT', player: 1, type: 'joystick' },
    { key: 'p1.right', label: 'RIGHT', player: 1, type: 'joystick' },
    { key: 'p1.button1', label: 'BUTTON 1', player: 1, type: 'button' },
    { key: 'p1.button2', label: 'BUTTON 2', player: 1, type: 'button' },
    { key: 'p1.button3', label: 'BUTTON 3', player: 1, type: 'button' },
    { key: 'p1.button4', label: 'BUTTON 4', player: 1, type: 'button' },
    { key: 'p1.button5', label: 'BUTTON 5', player: 1, type: 'button' },
    { key: 'p1.button6', label: 'BUTTON 6', player: 1, type: 'button' },
    { key: 'p1.coin', label: 'COIN', player: 1, type: 'button' },
    { key: 'p1.start', label: 'START', player: 1, type: 'button' },
]

// WebSocket URL for the wizard input stream
import { getGatewayWsUrl, getGatewayUrl } from '../../services/gateway'

const WS_URL = getGatewayWsUrl('/api/wizard/listen')
const API_BASE = getGatewayUrl()

export default function ArcadeWizard({ onClose, playerCount = 1 }) {
    // Wizard state
    const [currentStepIndex, setCurrentStepIndex] = useState(0)
    const [mappings, setMappings] = useState({})
    const [isListening, setIsListening] = useState(false)
    const [lastInput, setLastInput] = useState(null)
    const [wsStatus, setWsStatus] = useState('disconnected') // disconnected, connecting, connected
    const [saveStatus, setSaveStatus] = useState(null) // null, saving, success, error
    const [error, setError] = useState(null)

    // WebSocket ref
    const wsRef = useRef(null)
    const reconnectTimeoutRef = useRef(null)

    // Current step
    const currentStep = WIZARD_STEPS[currentStepIndex]
    const isComplete = currentStepIndex >= WIZARD_STEPS.length

    // Build steps for all players
    const allSteps = React.useMemo(() => {
        const steps = []
        for (let p = 1; p <= playerCount; p++) {
            WIZARD_STEPS.forEach(step => {
                steps.push({
                    ...step,
                    key: step.key.replace('p1.', `p${p}.`),
                    label: step.label,
                    player: p,
                })
            })
        }
        return steps
    }, [playerCount])

    // Connect to WebSocket
    const connectWebSocket = useCallback(() => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            console.log('[ArcadeWizard] WebSocket already connected')
            return
        }

        setWsStatus('connecting')
        console.log('[ArcadeWizard] Connecting to WebSocket:', WS_URL)

        const ws = new WebSocket(WS_URL)
        wsRef.current = ws

        ws.onopen = () => {
            console.log('[ArcadeWizard] WebSocket connected')
            setWsStatus('connected')
            setError(null)
        }

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data)

                // Ignore ping messages
                if (data.type === 'ping') return

                console.log('[ArcadeWizard] Input received:', data)
                setLastInput(data)

                // If we're listening and not complete, capture this input
                if (isListening && !isComplete && currentStep) {
                    // Map the input to the current step
                    setMappings(prev => ({
                        ...prev,
                        [allSteps[currentStepIndex].key]: {
                            pin: data.pin || currentStepIndex + 1,
                            type: allSteps[currentStepIndex].type,
                            label: `P${allSteps[currentStepIndex].player} ${allSteps[currentStepIndex].label}`,
                            keycode: data.code,
                            device_id: data.device_id,
                        }
                    }))

                    // Auto-advance to next step
                    setCurrentStepIndex(prev => prev + 1)
                }
            } catch (e) {
                console.error('[ArcadeWizard] Failed to parse message:', e)
            }
        }

        ws.onerror = (error) => {
            console.error('[ArcadeWizard] WebSocket error:', error)
            setError('WebSocket connection failed. Is the backend running?')
            setWsStatus('disconnected')
        }

        ws.onclose = () => {
            console.log('[ArcadeWizard] WebSocket closed')
            setWsStatus('disconnected')

            // Auto-reconnect after 3 seconds
            reconnectTimeoutRef.current = setTimeout(() => {
                if (isListening) {
                    connectWebSocket()
                }
            }, 3000)
        }
    }, [isListening, isComplete, currentStep, currentStepIndex, allSteps])

    // Start listening
    const startListening = useCallback(() => {
        setIsListening(true)
        connectWebSocket()
    }, [connectWebSocket])

    // Stop listening
    const stopListening = useCallback(() => {
        setIsListening(false)
        if (wsRef.current) {
            wsRef.current.close()
            wsRef.current = null
        }
        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current)
        }
    }, [])

    // Save mappings
    const handleSave = useCallback(async () => {
        setSaveStatus('saving')
        setError(null)

        try {
            const controls = {
                version: '1.0',
                comment: 'Generated by Arcade Wizard',
                encoder_mode: 'xinput',
                mappings: mappings,
            }

            const response = await fetch(`${API_BASE}/api/wizard/save`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    controls: controls,
                    generate_mame_config: true,
                }),
            })

            const result = await response.json()

            if (result.status === 'success') {
                setSaveStatus('success')
                console.log('[ArcadeWizard] Save successful:', result)
            } else {
                setSaveStatus('error')
                setError(result.error || 'Save failed')
            }
        } catch (e) {
            console.error('[ArcadeWizard] Save error:', e)
            setSaveStatus('error')
            setError(e.message)
        }
    }, [mappings])

    // Skip current step
    const handleSkip = useCallback(() => {
        setCurrentStepIndex(prev => prev + 1)
    }, [])

    // Reset wizard
    const handleReset = useCallback(() => {
        setCurrentStepIndex(0)
        setMappings({})
        setLastInput(null)
        setSaveStatus(null)
        setError(null)
    }, [])

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            if (wsRef.current) {
                wsRef.current.close()
            }
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current)
            }
        }
    }, [])

    // Progress percentage
    const progress = Math.round((currentStepIndex / allSteps.length) * 100)

    return (
        <div className="arcade-wizard">
            <div className="wizard-header">
                <h2>🕹️ Arcade Controller Wizard</h2>
                <button className="close-btn" onClick={onClose}>✕</button>
            </div>

            {/* Status Bar */}
            <div className="status-bar">
                <div className={`ws-status ${wsStatus}`}>
                    <span className="status-dot"></span>
                    {wsStatus === 'connected' ? 'Connected' : wsStatus === 'connecting' ? 'Connecting...' : 'Disconnected'}
                </div>
                {lastInput && (
                    <div className="last-input">
                        Last: <code>{lastInput.code}</code> (Device {lastInput.device_id})
                    </div>
                )}
            </div>

            {/* Progress Bar */}
            <div className="progress-container">
                <div className="progress-bar" style={{ width: `${progress}%` }}></div>
                <span className="progress-text">{currentStepIndex} / {allSteps.length} controls mapped</span>
            </div>

            {/* Main Content */}
            <div className="wizard-content">
                {!isComplete ? (
                    <>
                        {/* Current Step Prompt */}
                        <div className="step-prompt">
                            <div className="player-badge">Player {allSteps[currentStepIndex]?.player}</div>
                            <div className="step-label">
                                PRESS <span className="highlight">{allSteps[currentStepIndex]?.label}</span>
                            </div>
                            <div className="step-hint">
                                {allSteps[currentStepIndex]?.type === 'joystick' ? '🎮 Joystick Direction' : '🔘 Button'}
                            </div>
                        </div>

                        {/* Controls */}
                        <div className="wizard-controls">
                            {!isListening ? (
                                <button className="btn-primary" onClick={startListening}>
                                    ▶ Start Learning
                                </button>
                            ) : (
                                <button className="btn-secondary" onClick={stopListening}>
                                    ⏹ Stop
                                </button>
                            )}
                            <button className="btn-outline" onClick={handleSkip}>
                                Skip →
                            </button>
                        </div>

                        {/* Live Input Display */}
                        {isListening && (
                            <div className="input-display">
                                <div className="input-label">Waiting for input...</div>
                                {lastInput && (
                                    <div className="input-code">
                                        <span className="code">{lastInput.code}</span>
                                        <span className="device">Device {lastInput.device_id}</span>
                                    </div>
                                )}
                            </div>
                        )}
                    </>
                ) : (
                    /* Completion Screen */
                    <div className="completion-screen">
                        <div className="completion-icon">✅</div>
                        <h3>All Controls Mapped!</h3>
                        <p>Ready to save your configuration.</p>

                        {saveStatus === 'success' ? (
                            <div className="save-success">
                                <p>🎉 Configuration saved!</p>
                                <p>MAME config generated at <code>MAME Gamepad/cfg/default.cfg</code></p>
                            </div>
                        ) : (
                            <div className="wizard-controls">
                                <button
                                    className="btn-primary"
                                    onClick={handleSave}
                                    disabled={saveStatus === 'saving'}
                                >
                                    {saveStatus === 'saving' ? 'Saving...' : '💾 Save & Generate MAME Config'}
                                </button>
                                <button className="btn-outline" onClick={handleReset}>
                                    🔄 Start Over
                                </button>
                            </div>
                        )}
                    </div>
                )}

                {/* Error Display */}
                {error && (
                    <div className="error-message">
                        ⚠️ {error}
                    </div>
                )}

                {/* Mapped Controls Summary */}
                <div className="mappings-summary">
                    <h4>Mapped Controls</h4>
                    <div className="mappings-grid">
                        {Object.entries(mappings).map(([key, value]) => (
                            <div key={key} className="mapping-item">
                                <span className="mapping-key">{key}</span>
                                <span className="mapping-value">{value.keycode}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    )
}
