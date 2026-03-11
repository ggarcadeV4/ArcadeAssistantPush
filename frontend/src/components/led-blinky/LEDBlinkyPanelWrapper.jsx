/**
 * LEDBlinkyPanelWrapper
 *
 * Adds error boundary + calibration TTS around the core LED Blinky panel.
 * This file is imported by Assistants.jsx instead of LEDBlinkyPanelNew.
 */
import React, { useEffect, useRef } from 'react'
import LEDBlinkyPanelCore from './LEDBlinkyPanelNew'
import { speakAsBlinky } from '../../services/ttsClient'

// ═══ Error Boundary ═════════════════════════════════════════════════════
class LEDBlinkyErrorBoundary extends React.Component {
    constructor(props) {
        super(props)
        this.state = { hasError: false, error: null }
    }
    static getDerivedStateFromError(error) {
        return { hasError: true, error }
    }
    componentDidCatch(error, info) {
        console.error('[LEDBlinky] Panel crash:', error, info)
    }
    render() {
        if (this.state.hasError) {
            return (
                <div className="led-panel" style={{ padding: '3rem', textAlign: 'center' }}>
                    <h2 style={{ color: '#ef4444', marginBottom: '1rem' }}>⚡ Blinky Hit a Snag</h2>
                    <p style={{ color: '#94a3b8', marginBottom: '1.5rem' }}>
                        {this.state.error?.message || 'The LED panel encountered an error. This usually means the hardware connection dropped.'}
                    </p>
                    <p style={{ color: '#64748b', fontSize: '0.85rem', marginBottom: '1.5rem' }}>
                        If the problem persists, check that LEDBlinky.exe is installed and the backend is running.
                    </p>
                    <button
                        className="led-panel__preset-btn"
                        onClick={() => this.setState({ hasError: false, error: null })}
                        style={{ fontSize: '0.9rem', padding: '0.5rem 1.5rem' }}
                    >
                        🔄 Try Again
                    </button>
                </div>
            )
        }
        return this.props.children
    }
}

// ═══ Wrapped Panel export ═══════════════════════════════════════════════
export default function LEDBlinkyPanel() {
    return (
        <LEDBlinkyErrorBoundary>
            <LEDBlinkyPanelCore />
        </LEDBlinkyErrorBoundary>
    )
}
