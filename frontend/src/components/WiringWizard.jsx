/**
 * WiringWizard.jsx
 * Part of: Phase 6.5 - Fix Broken GUI Wiring
 * 
 * Interactive LED calibration UI that syncs with the backend Wiring Wizard service.
 * Accepts hoisted handleMapButton from parent to share mapping logic with ArcadePanelPreview.
 */

import React, { useState, useEffect, useCallback } from 'react'
import PropTypes from 'prop-types'

// API endpoints
const API_BASE = '/api/cabinet'

/**
 * WiringWizard Component
 * 
 * Props:
 * - wizardState: object - shared wizard state from parent
 * - onMapButton: (buttonId: string) => Promise - hoisted mapping function
 * - onComplete: () => void - called when wizard finishes
 * - onCancel: () => void - called when wizard cancelled
 * - onStateChange: (state) => void - notify parent of state changes
 * - numPlayers: number - 2 or 4
 */
const WiringWizard = ({
    wizardState: externalState,
    onMapButton,
    onComplete,
    onCancel,
    onStateChange,
    numPlayers = 2
}) => {
    // Internal wizard state (will sync with external if provided)
    const [internalState, setInternalState] = useState({
        isActive: false,
        sessionId: null,
        currentPort: null,
        currentStep: 0,
        totalPorts: 0,
        mappedCount: 0,
        buttonToPortMap: {}
    })

    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState(null)
    const [blinkInfo, setBlinkInfo] = useState(null)

    // Use external state if provided, otherwise internal
    const wizardState = externalState || internalState
    const setWizardState = externalState ? onStateChange : setInternalState

    // Poll wizard state ALWAYS when mounted (Phase 6.5: removed isActive gate)
    useEffect(() => {
        let pollInterval = null

        const fetchState = async () => {
            try {
                const res = await fetch(`${API_BASE}/wizard/state`)
                const data = await res.json()
                if (data.success !== false) {
                    if (onStateChange) {
                        onStateChange(data)
                    } else {
                        setInternalState(data)
                    }

                    // Update blink info from state
                    if (data.currentPort && data.isActive) {
                        setBlinkInfo({
                            port: data.currentPort,
                            step: data.currentStep,
                            total: data.totalPorts,
                            instruction: `Press button for port ${data.currentPort}`
                        })
                    }
                }
            } catch (e) {
                console.error('[WiringWizard] State poll failed:', e)
            }
        }

        // Initial fetch immediately
        fetchState()

        // Poll every 500ms
        pollInterval = setInterval(fetchState, 500)

        return () => {
            if (pollInterval) clearInterval(pollInterval)
        }
    }, [onStateChange])

    // Start calibration
    const handleStart = useCallback(async () => {
        setIsLoading(true)
        setError(null)

        try {
            const res = await fetch(`${API_BASE}/wizard/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ numPlayers })
            })

            const data = await res.json()

            if (!data.success) {
                setError(data.error || 'Failed to start wizard')
                return
            }

            const newState = {
                ...wizardState,
                isActive: true,
                sessionId: data.sessionId,
                totalPorts: data.totalPorts
            }

            if (setWizardState) setWizardState(newState)

            // Immediately blink first port
            await handleBlink()

        } catch (e) {
            setError(e.message)
        } finally {
            setIsLoading(false)
        }
    }, [numPlayers, wizardState, setWizardState])

    // Blink next port
    const handleBlink = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/wizard/blink`, {
                method: 'POST'
            })

            const data = await res.json()

            if (data.complete) {
                setBlinkInfo(null)
                return
            }

            if (data.error) {
                setError(data.error)
                return
            }

            setBlinkInfo({
                port: data.port,
                buttonId: data.buttonId,
                step: data.step,
                total: data.total,
                instruction: data.instruction
            })

        } catch (e) {
            setError(e.message)
        }
    }, [])

    // Map button - use hoisted function if provided, otherwise call API directly
    const handleMapButtonInternal = useCallback(async (buttonId) => {
        if (!wizardState.isActive) return

        // Use hoisted function from parent if available
        if (onMapButton) {
            await onMapButton(buttonId)
            return
        }

        // Fallback: direct API call
        try {
            const res = await fetch(`${API_BASE}/wizard/map`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ buttonId })
            })

            const data = await res.json()

            if (data.complete) {
                handleFinish()
                return
            }

            if (data.success) {
                await handleBlink()
            }

        } catch (e) {
            setError(e.message)
        }
    }, [wizardState.isActive, onMapButton, handleBlink])

    // Skip current port
    const handleSkip = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/wizard/skip`, {
                method: 'POST'
            })

            const data = await res.json()

            if (data.complete) {
                handleFinish()
                return
            }

            if (data.success) {
                await handleBlink()
            }

        } catch (e) {
            setError(e.message)
        }
    }, [handleBlink])

    // Finish wizard and save
    const handleFinish = useCallback(async () => {
        setIsLoading(true)

        try {
            const res = await fetch(`${API_BASE}/wizard/finish`, {
                method: 'POST'
            })

            const data = await res.json()

            if (data.success) {
                if (setWizardState) {
                    setWizardState({ ...wizardState, isActive: false })
                }
                setBlinkInfo(null)
                onComplete?.()
            } else {
                setError(data.error || 'Failed to save mappings')
            }

        } catch (e) {
            setError(e.message)
        } finally {
            setIsLoading(false)
        }
    }, [onComplete, wizardState, setWizardState])

    // Cancel wizard
    const handleCancel = useCallback(async () => {
        try {
            await fetch(`${API_BASE}/wizard/cancel`, {
                method: 'POST'
            })

            if (setWizardState) {
                setWizardState({ ...wizardState, isActive: false })
            }
            setBlinkInfo(null)
            setError(null)
            onCancel?.()

        } catch (e) {
            console.error('[WiringWizard] Cancel failed:', e)
        }
    }, [onCancel, wizardState, setWizardState])

    // Calculate progress percentage
    const progressPercent = wizardState.totalPorts > 0
        ? Math.round((wizardState.currentStep / wizardState.totalPorts) * 100)
        : 0

    // Render: Not active state - show start button
    if (!wizardState.isActive) {
        return (
            <div style={{
                padding: '20px',
                background: '#0f0f0f',
                borderRadius: '12px',
                border: '1px solid #9333ea'
            }}>
                <div style={{
                    fontSize: '16px',
                    fontWeight: '700',
                    color: '#9333ea',
                    marginBottom: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                }}>
                    <span>🎓</span>
                    <span>LED Wiring Wizard</span>
                </div>

                <p style={{ color: '#9ca3af', fontSize: '14px', marginBottom: '16px' }}>
                    Map your physical buttons to LED-Wiz ports. The wizard will blink each port in sequence -
                    click the corresponding button on the panel below to create the mapping.
                </p>

                <button
                    onClick={handleStart}
                    disabled={isLoading}
                    style={{
                        background: 'linear-gradient(135deg, #9333ea, #7c3aed)',
                        border: 'none',
                        borderRadius: '8px',
                        color: 'white',
                        padding: '12px 24px',
                        fontSize: '14px',
                        fontWeight: '600',
                        cursor: isLoading ? 'not-allowed' : 'pointer',
                        opacity: isLoading ? 0.7 : 1
                    }}
                >
                    {isLoading ? '⏳ Starting...' : '🚀 Start Calibration'}
                </button>

                {error && (
                    <div style={{
                        marginTop: '12px',
                        color: '#ef4444',
                        fontSize: '13px',
                        padding: '8px',
                        background: 'rgba(239, 68, 68, 0.1)',
                        borderRadius: '6px'
                    }}>
                        ⚠️ {error}
                    </div>
                )}
            </div>
        )
    }

    // Render: Active wizard
    return (
        <div style={{
            padding: '20px',
            background: '#1a0a2e',
            borderRadius: '12px',
            border: '2px solid #10b981',
            boxShadow: '0 0 20px rgba(16, 185, 129, 0.3)'
        }}>
            {/* Header */}
            <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '16px'
            }}>
                <div style={{
                    fontSize: '16px',
                    fontWeight: '700',
                    color: '#10b981',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                }}>
                    <span style={{ animation: 'pulse 1.5s infinite' }}>🎓</span>
                    <span>Calibration Active</span>
                </div>

                <div style={{
                    fontSize: '13px',
                    color: '#d1d5db',
                    background: '#2a1a3e',
                    padding: '4px 12px',
                    borderRadius: '20px'
                }}>
                    Port {blinkInfo?.step || wizardState.currentStep + 1} of {wizardState.totalPorts}
                </div>
            </div>

            {/* Progress Bar */}
            <div style={{
                height: '8px',
                background: '#2a1a3e',
                borderRadius: '4px',
                marginBottom: '20px',
                overflow: 'hidden'
            }}>
                <div style={{
                    height: '100%',
                    width: `${progressPercent}%`,
                    background: 'linear-gradient(90deg, #10b981, #34d399)',
                    borderRadius: '4px',
                    transition: 'width 0.3s ease'
                }} />
            </div>

            {/* Instruction */}
            <div style={{
                textAlign: 'center',
                padding: '20px',
                background: 'rgba(16, 185, 129, 0.1)',
                borderRadius: '8px',
                marginBottom: '16px'
            }}>
                <div style={{
                    fontSize: '18px',
                    fontWeight: '700',
                    color: '#34d399',
                    marginBottom: '8px'
                }}>
                    {blinkInfo?.instruction || `Click button for port ${wizardState.currentPort || wizardState.currentStep + 1}`}
                </div>
                <div style={{ fontSize: '13px', color: '#9ca3af' }}>
                    👇 Click the matching button on the arcade panel preview below
                </div>
            </div>

            {/* Action Buttons */}
            <div style={{
                display: 'flex',
                gap: '12px',
                justifyContent: 'center'
            }}>
                <button
                    onClick={handleSkip}
                    style={{
                        background: 'transparent',
                        border: '1px solid #6b7280',
                        borderRadius: '8px',
                        color: '#9ca3af',
                        padding: '10px 20px',
                        fontSize: '13px',
                        cursor: 'pointer'
                    }}
                >
                    ⏭️ Skip Port
                </button>

                <button
                    onClick={handleFinish}
                    disabled={isLoading}
                    style={{
                        background: 'linear-gradient(135deg, #10b981, #059669)',
                        border: 'none',
                        borderRadius: '8px',
                        color: 'white',
                        padding: '10px 20px',
                        fontSize: '13px',
                        fontWeight: '600',
                        cursor: isLoading ? 'not-allowed' : 'pointer',
                        opacity: isLoading ? 0.7 : 1
                    }}
                >
                    💾 Save & Finish
                </button>

                <button
                    onClick={handleCancel}
                    style={{
                        background: 'transparent',
                        border: '1px solid #ef4444',
                        borderRadius: '8px',
                        color: '#ef4444',
                        padding: '10px 20px',
                        fontSize: '13px',
                        cursor: 'pointer'
                    }}
                >
                    ❌ Cancel
                </button>
            </div>

            {/* Mapped Count */}
            <div style={{
                marginTop: '16px',
                textAlign: 'center',
                fontSize: '12px',
                color: '#6b7280'
            }}>
                {wizardState.mappedCount || 0} buttons mapped so far
            </div>

            {/* Error Display */}
            {error && (
                <div style={{
                    marginTop: '12px',
                    color: '#ef4444',
                    fontSize: '13px',
                    padding: '8px',
                    background: 'rgba(239, 68, 68, 0.1)',
                    borderRadius: '6px',
                    textAlign: 'center'
                }}>
                    ⚠️ {error}
                </div>
            )}

            {/* Pulse animation style */}
            <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
        </div>
    )
}

WiringWizard.propTypes = {
    wizardState: PropTypes.object,
    onMapButton: PropTypes.func,
    onComplete: PropTypes.func,
    onCancel: PropTypes.func,
    onStateChange: PropTypes.func,
    numPlayers: PropTypes.number
}

export default WiringWizard
