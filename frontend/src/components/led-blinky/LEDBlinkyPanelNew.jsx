/**
 * LEDBlinkyPanel — Single-view LED Blinky Control Dashboard
 *
 * New architecture: one panel, four states (idle/active/calibration/design).
 * All tabs removed. The ButtonVisualizer IS the panel.
 *
 * Core hooks preserved:
 *   - useBlinkyChat → AI chat + command dispatch
 *   - executeLEDCommands → command processing
 *   - useLEDPanelState → state machine (idle/active/calibration/design)
 *     ↳ useLEDCalibrationWizard → blink-click-map flow
 *     ↳ useLEDCalibrationSession → flash/assign + AI helpers
 *   - Web Speech API → voice input
 *
 * See: implementation_plan.md, revelations R-01 through R-23
 */
import React, { useState, useEffect, useRef, useCallback } from 'react'
import { speakAsBlinky } from '../../services/ttsClient'
import { useBlinkyChat } from '../../panels/led-blinky/useBlinkyChat'
import { executeLEDCommands } from '../../panels/led-blinky/commandExecutor'
import useLEDPanelState from '../../hooks/useLEDPanelState'
import ButtonVisualizer from './ButtonVisualizer'
import UserProfileSelector from './UserProfileSelector'
import ColorPalette from './ColorPalette'
import './LEDBlinkyPanel.css'
import { EngineeringBaySidebar } from '../../panels/_kit/EngineeringBaySidebar'
import '../../panels/_kit/EngineeringBaySidebar.css'

import {
    getLEDStatus,
    setLEDBrightness,
    buildGatewayWebSocketUrl,
} from '../../services/ledBlinkyClient'

// ─── Component ───────────────────────────────────────────────────────
const LEDBlinkyPanel = () => {

    // ─── Core Hooks ──────────────────────────────────────────────────
    const blinkyChat = useBlinkyChat()

    // ─── Toast (portable) ────────────────────────────────────────────
    const showToast = useCallback((message, type = 'success') => {
        console.log(`Toast [${type}]: ${message}`)
    }, [])

    // ─── Panel State Machine (Phase 2 + 3) ───────────────────────────
    const panel = useLEDPanelState({ showToast })

    // ─── Layout & Brightness ─────────────────────────────────────────
    const [playerCount, setPlayerCount] = useState(4)
    const [brightness, setBrightness] = useState(75)

    // ─── User Profile ────────────────────────────────────────────────
    const [activeProfileId, setActiveProfileId] = useState('bobby')

    // ─── Connection ──────────────────────────────────────────────────
    const [connectionStatus, setConnectionStatus] = useState('disconnected')

    // ─── Chat & Voice ────────────────────────────────────────────────
    const [chatOpen, setChatOpen] = useState(false)
    const [chatInput, setChatInput] = useState('')
    const [chatMessages, setChatMessages] = useState([
        { type: 'ai', message: "Hey! I'm Blinky. Tell me what to do with the lights." }
    ])
    const [isSending, setIsSending] = useState(false)
    const [isVoiceRecording, setIsVoiceRecording] = useState(false)
    const recognitionRef = useRef(null)
    const chatEndRef = useRef(null)

    // ─── Command Context (bridges hooks → dispatch) ──────────────────
    const commandContext = {
        calibrationToken: panel.calibration.calibrationToken,
        setCalibrationToken: panel.calibration.setCalibrationToken,
        showToast,
        loadChannelMappings: panel.loadChannelMappings,
    }

    // ─── WebSocket Connection ────────────────────────────────────────
    useEffect(() => {
        const wsUrl = buildGatewayWebSocketUrl('/api/local/led/ws')
        const checkStatus = async () => {
            try {
                const status = await getLEDStatus()
                if (status?.connected) {
                    setConnectionStatus('connected')
                } else {
                    setConnectionStatus('simulated')
                }
            } catch {
                setConnectionStatus('disconnected')
            }
        }
        checkStatus()
    }, [])

    // ─── Brightness Handler ──────────────────────────────────────────
    const handleBrightnessChange = useCallback((value) => {
        setBrightness(value)
        const timer = setTimeout(() => {
            setLEDBrightness(value).catch(err => {
                console.error('[LEDBlinky] Brightness error:', err)
            })
        }, 200)
        return () => clearTimeout(timer)
    }, [])

    // ─── Chat Send (Text) ───────────────────────────────────────────
    const sendChatMessage = useCallback(async () => {
        if (!chatInput.trim() || isSending) return
        const userMessage = chatInput.trim()
        setChatMessages(prev => [...prev, { type: 'user', message: userMessage }])
        setChatInput('')
        setIsSending(true)

        try {
            const result = await blinkyChat.send(userMessage, 'state')
            const response = result?.message?.content || 'I did not receive a response.'
            const commands = result?.commands || []

            setChatMessages(prev => [...prev, { type: 'ai', message: response }])
            setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)

            if (commands.length > 0) {
                console.log('[LEDBlinky] Executing', commands.length, 'commands')
                await executeLEDCommands(commands, commandContext)
            }
        } catch (err) {
            console.error('[LEDBlinky] Chat error:', err)
            setChatMessages(prev => [...prev, { type: 'ai', message: 'Sorry, I encountered an error.' }])
        } finally {
            setIsSending(false)
        }
    }, [chatInput, isSending, blinkyChat, commandContext])

    // ─── Chat Send (Voice) ──────────────────────────────────────────
    const toggleVoiceInput = useCallback(async () => {
        if (isVoiceRecording) {
            if (recognitionRef.current) recognitionRef.current.stop()
            setIsVoiceRecording(false)
            return
        }

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
        if (!SpeechRecognition) {
            showToast('Voice input not supported in this browser.', 'error')
            return
        }

        try {
            const recognition = new SpeechRecognition()
            recognition.continuous = false
            recognition.interimResults = false
            recognition.lang = 'en-US'
            recognitionRef.current = recognition

            recognition.onstart = () => {
                setIsVoiceRecording(true)
                showToast('Listening…', 'success')
            }

            recognition.onresult = async (event) => {
                if (!event.results[0].isFinal) return
                const transcript = event.results[0][0].transcript
                setIsVoiceRecording(false)
                recognitionRef.current = null
                if (!transcript.trim()) return

                setChatMessages(prev => [...prev, { type: 'user', message: transcript }])

                try {
                    const result = await blinkyChat.send(transcript, 'state')
                    const response = result?.message?.content || 'I did not receive a response.'
                    const commands = result?.commands || []

                    setChatMessages(prev => [...prev, { type: 'ai', message: response }])

                    if (commands.length > 0) {
                        await executeLEDCommands(commands, commandContext)
                    }

                    try { await speakAsBlinky(response) } catch { }
                } catch (err) {
                    console.error('[LEDBlinky Voice] Error:', err)
                    setChatMessages(prev => [...prev, { type: 'ai', message: 'Sorry, I encountered an error.' }])
                }
            }

            recognition.onerror = (event) => {
                showToast(`Voice error: ${event.error}`, 'error')
                setIsVoiceRecording(false)
                recognitionRef.current = null
            }

            recognition.onend = () => {
                setIsVoiceRecording(false)
                recognitionRef.current = null
            }

            recognition.start()
        } catch (err) {
            showToast('Failed to start voice input', 'error')
            setIsVoiceRecording(false)
        }
    }, [isVoiceRecording, blinkyChat, commandContext, showToast])

    // ─── Keyboard: Enter to send ─────────────────────────────────────
    const handleChatKeyDown = useCallback((e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            sendChatMessage()
        }
    }, [sendChatMessage])

    // ─── Dewey Handoff Detection ─────────────────────────────────────
    useEffect(() => {
        const urlParams = new URLSearchParams(window.location.search)
        const context = urlParams.get('context')
        if (context) {
            setChatMessages([])
        }
    }, [])

    // ─── Status Badge (from state machine) ───────────────────────────
    const badge = panel.getStatusBadge(connectionStatus)

    const BLINKY_PERSONA = {
        id: 'blinky',
        name: 'BLINKY',
        icon: '💡',
        icon2: '🎮',
        accentColor: '#06B6D4',
        accentGlow: 'rgba(6,182,212,0.35)',
        scannerLabel: 'STROBING...',
        emptyHint: 'Ask Blinky about LED colors, zones, themes, or calibration.',
        chips: [
            { id: 'scan', label: 'Scan LEDs', prompt: 'Scan all connected LED controllers and list their status.' },
            { id: 'theme', label: 'Apply Theme', prompt: 'Show me all available lighting themes and apply one.' },
            { id: 'cal', label: 'Calibrate', prompt: 'Start the LED calibration wizard.' },
            { id: 'reset', label: 'Reset Colors', prompt: 'Reset all button colors to default white.' },
        ],
    }

    // ─── Render ──────────────────────────────────────────────────────
    return (
        <div className="eb-layout">
            <div className="eb-layout__main">
                <div className="led-panel">
                    {/* ── Header ────────────────────────────────── */}
                    <div className="led-panel__header">
                        <div className="led-panel__title-group">
                            <h1 className="led-panel__title">LED Blinky</h1>
                            <div className={`led-panel__status-badge ${badge.className}`}>
                                <span className={`led-panel__status-dot ${badge.dotClass}`} />
                                {badge.text}
                            </div>
                        </div>

                        <UserProfileSelector
                            activeProfileId={activeProfileId}
                            onProfileChange={setActiveProfileId}
                        />
                    </div>

                    {/* ── Controls Row ──────────────────────────── */}
                    <div className="led-panel__controls">
                        {/* Layout toggle */}
                        <div className="led-panel__control-group">
                            <span className="led-panel__control-label">Layout:</span>
                            <select
                                className="led-panel__select"
                                value={playerCount}
                                onChange={(e) => setPlayerCount(Number(e.target.value))}
                            >
                                <option value={4}>4-Player</option>
                                <option value={2}>2-Player</option>
                            </select>
                        </div>

                        {/* Calibration toggle */}
                        <div className="led-panel__control-group">
                            <button
                                className={`led-panel__preset-btn ${panel.mode === 'calibration' ? 'led-panel__preset-btn--active' : ''}`}
                                onClick={panel.toggleCalibration}
                                disabled={panel.wizard.isLoading}
                                style={panel.mode === 'calibration' ? { borderColor: '#eab308', color: '#fde047' } : {}}
                            >
                                {panel.wizard.isLoading ? '⏳ Working…' : panel.mode === 'calibration' ? '⏹ Stop Calibration' : '🔧 Calibrate'}
                            </button>
                        </div>

                        {/* Design mode toggle */}
                        <div className="led-panel__control-group">
                            <button
                                className={`led-panel__preset-btn ${panel.mode === 'design' ? 'led-panel__preset-btn--active' : ''}`}
                                onClick={panel.toggleDesign}
                                style={panel.mode === 'design' ? { borderColor: '#22c55e', color: '#4ade80' } : {}}
                            >
                                {panel.mode === 'design' ? '⏹ Exit Design' : '🎨 Design'}
                            </button>
                        </div>

                        {/* Brightness slider */}
                        <div className="led-panel__control-group led-panel__brightness">
                            <span className="led-panel__control-label">Brightness</span>
                            <input
                                type="range"
                                className="led-panel__slider"
                                min={10}
                                max={100}
                                value={brightness}
                                onChange={(e) => handleBrightnessChange(Number(e.target.value))}
                            />
                            <span className="led-panel__brightness-value">{brightness}%</span>
                        </div>
                    </div>

                    {/* ── Calibration Progress Bar ──────────────── */}
                    {panel.mode === 'calibration' && (
                        <div className="led-panel__calibration-bar">
                            <div style={{ display: 'flex', alignItems: 'center', gap: 12, width: '100%' }}>
                                <span className="led-panel__calibration-text">
                                    Port {panel.wizard.currentPort} of {panel.wizard.totalPorts}
                                </span>
                                <div className="led-panel__calibration-progress" style={{ flex: 1 }}>
                                    <div
                                        className="led-panel__calibration-fill"
                                        style={{ width: `${panel.wizard.progressPercent}%` }}
                                    />
                                </div>
                                <span className="led-panel__calibration-text" style={{ fontSize: 11, opacity: 0.7, whiteSpace: 'nowrap' }}>
                                    {panel.wizard.mappedCount} mapped · {panel.wizard.skippedCount} skipped
                                </span>
                            </div>
                            <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                                <span className="led-panel__calibration-text" style={{ fontSize: 12 }}>
                                    Click the button that is lit on your cabinet
                                </span>
                                <button
                                    className="led-panel__preset-btn"
                                    onClick={panel.skipPort}
                                    disabled={panel.wizard.isLoading}
                                    style={{ fontSize: 11, padding: '2px 10px', marginLeft: 'auto' }}
                                >
                                    ⏭ Skip Port
                                </button>
                            </div>
                        </div>
                    )}

                    {/* ── Visualizer ────────────────────────────── */}
                    <ButtonVisualizer
                        playerCount={playerCount}
                        buttonColors={panel.resolvedColors}
                        mode={panel.mode}
                        blinkingButton={null}
                        onButtonClick={panel.handleButtonClick}
                    />

                    {/* ── Color Palette (Design Mode) ───────────── */}
                    {panel.mode === 'design' && (
                        <ColorPalette
                            colors={panel.design.PALETTE_COLORS}
                            selectedColor={panel.design.selectedColor}
                            onColorSelect={panel.design.setSelectedColor}
                            onFillAll={() => panel.design.fillAll(playerCount)}
                            onClearAll={panel.design.clearAll}
                            onSaveProfile={panel.design.saveProfile}
                            onLoadProfile={panel.design.loadProfile}
                            onDeleteProfile={panel.design.deleteProfile}
                            profileNames={panel.design.profileNames}
                            activeProfileName={panel.design.activeProfileName}
                            hasChanges={panel.design.hasChanges}
                        />
                    )}

                    {/* ── Footer ────────────────────────────────── */}
                    <div className="led-panel__footer">
                        {/* Idle → preset animation buttons */}
                        {panel.mode === 'idle' && (
                            <div className="led-panel__presets">
                                <span className="led-panel__control-label" style={{ marginRight: 4 }}>Animations:</span>
                                {panel.PRESET_ANIMATIONS.map(preset => (
                                    <button
                                        key={preset.id}
                                        className={`led-panel__preset-btn ${panel.activeAnimation === preset.id ? 'led-panel__preset-btn--active' : ''}`}
                                        onClick={() => panel.playPreset(preset.id)}
                                    >
                                        {preset.label}
                                    </button>
                                ))}
                            </div>
                        )}

                        {/* Active → profile name + playtime */}
                        {panel.mode === 'active' && (
                            <div className="led-panel__footer-info">
                                <span className="led-panel__profile-label">Active Profile:</span>
                                <span className="led-panel__profile-name">{panel.activeGame?.profile || 'Default'}</span>
                                <span className="led-panel__playtime">
                                    🕐 Playing for {panel.activeGame?.playtime || '0m'}
                                </span>
                            </div>
                        )}

                        {/* ── Chat Bar ──────────────────────────────── */}
                        <div className="led-panel__chat-bar">
                            {/* Large mic button */}
                            <button
                                className={`led-panel__mic-btn ${isVoiceRecording ? 'led-panel__mic-btn--recording' : ''}`}
                                onClick={toggleVoiceInput}
                                title={isVoiceRecording ? 'Stop recording' : 'Talk to Blinky'}
                            >
                                <svg viewBox="0 0 24 24" fill="currentColor" width="22" height="22">
                                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                                    <path d="M19 10v2a7 7 0 0 1-14 0v-2H3v2a9 9 0 0 0 8 8.94V22H9v2h6v-2h-2v-1.06A9 9 0 0 0 21 12v-2h-2z" />
                                </svg>
                                {isVoiceRecording && <span className="led-panel__mic-label">Listening…</span>}
                            </button>

                            <input
                                className="led-panel__chat-input"
                                placeholder="Ask Blinky..."
                                value={chatInput}
                                onChange={(e) => setChatInput(e.target.value)}
                                onKeyDown={handleChatKeyDown}
                                disabled={isSending}
                            />
                            <button
                                className="led-panel__chat-send"
                                onClick={sendChatMessage}
                                disabled={isSending || !chatInput.trim()}
                                title="Send"
                            >
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <path d="M22 2L11 13" />
                                    <path d="M22 2L15 22L11 13L2 9L22 2Z" />
                                </svg>
                            </button>

                            {/* Toggle slide-in chat history */}
                            <button
                                className={`led-panel__chat-toggle ${chatOpen ? 'led-panel__chat-toggle--open' : ''}`}
                                onClick={() => setChatOpen(o => !o)}
                                title="Open chat history"
                            >
                                💬
                            </button>
                        </div>
                    </div>

                    {/* ── Slide-in Chat Drawer ───────────────────── */}
                    <div className={`led-panel__chat-drawer ${chatOpen ? 'led-panel__chat-drawer--open' : ''}`}>
                        <div className="led-panel__chat-drawer-header">
                            <span>🤖 Blinky Chat</span>
                            <button className="led-panel__chat-drawer-close" onClick={() => setChatOpen(false)}>✕</button>
                        </div>
                        <div className="led-panel__chat-drawer-messages">
                            {chatMessages.map((msg, i) => (
                                <div key={i} className={`led-panel__chat-msg led-panel__chat-msg--${msg.type}`}>
                                    {msg.type === 'ai' && <span className="led-panel__chat-msg-avatar">🤖</span>}
                                    <span className="led-panel__chat-msg-text">{msg.message}</span>
                                </div>
                            ))}
                            {isSending && (
                                <div className="led-panel__chat-msg led-panel__chat-msg--ai">
                                    <span className="led-panel__chat-msg-avatar">🤖</span>
                                    <span className="led-panel__chat-msg-text led-panel__chat-typing">●●●</span>
                                </div>
                            )}
                            <div ref={chatEndRef} />
                        </div>
                        <div className="led-panel__chat-drawer-input">
                            <button
                                className={`led-panel__mic-btn led-panel__mic-btn--sm ${isVoiceRecording ? 'led-panel__mic-btn--recording' : ''}`}
                                onClick={toggleVoiceInput}
                                title={isVoiceRecording ? 'Stop' : 'Voice'}
                            >
                                <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16">
                                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                                    <path d="M19 10v2a7 7 0 0 1-14 0v-2H3v2a9 9 0 0 0 8 8.94V22H9v2h6v-2h-2v-1.06A9 9 0 0 0 21 12v-2h-2z" />
                                </svg>
                            </button>
                            <input
                                className="led-panel__chat-input"
                                placeholder="Ask Blinky..."
                                value={chatInput}
                                onChange={(e) => setChatInput(e.target.value)}
                                onKeyDown={handleChatKeyDown}
                                disabled={isSending}
                            />
                            <button
                                className="led-panel__chat-send"
                                onClick={sendChatMessage}
                                disabled={isSending || !chatInput.trim()}
                            >
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <path d="M22 2L11 13" />
                                    <path d="M22 2L15 22L11 13L2 9L22 2Z" />
                                </svg>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            <EngineeringBaySidebar persona={BLINKY_PERSONA} />
        </div>
    )
}

export default LEDBlinkyPanel
