/**
 * useLEDCalibrationWizard - Hook for 4-player LED port calibration
 * 
 * This hook manages the calibration wizard that maps physical LED ports
 * to logical button positions via a blink-to-click flow.
 * 
 * Flow:
 * 1. User starts wizard → backend begins blinking port 1
 * 2. User clicks the button that's physically lit → records mapping
 * 3. Backend advances to next port, repeat until done
 * 4. Mappings saved to JSON for physical-to-logical translation
 */
import { useState, useCallback, useRef } from 'react'
import { getGatewayUrl } from '../services/gateway'
import { buildStandardHeaders } from '../utils/identity'

// API base URL helper
const getApiBase = () => {
    if (typeof window === 'undefined' || !window.location) {
        return getGatewayUrl()
    }
    if (window.location.port === '5173') {
        return getGatewayUrl()
    }
    return window.location.origin
}

// Button layout definition for 4-player cabinet
// Total: 32 buttons (P1: 10, P2: 10, P3: 6, P4: 6)
export const CABINET_BUTTONS = {
    p1: {
        buttons: ['1', '2', '3', '4', '5', '6', '7', '8'],
        controls: ['start', 'select'],
        total: 10
    },
    p2: {
        buttons: ['1', '2', '3', '4', '5', '6', '7', '8'],
        controls: ['start', 'select'],
        total: 10
    },
    p3: {
        buttons: ['1', '2', '3', '4'],
        controls: ['start', 'select'],
        total: 6
    },
    p4: {
        buttons: ['1', '2', '3', '4'],
        controls: ['start', 'select'],
        total: 6
    }
}

// Calculate total buttons
export const TOTAL_CABINET_BUTTONS = Object.values(CABINET_BUTTONS).reduce((sum, p) => sum + p.total, 0)

/**
 * Convert player/button to logical ID format
 */
export const toLogicalId = (player, button) => {
    // Normalize button name
    const btn = button.toString().toLowerCase()
    return `p${player}.${btn}`
}

/**
 * Main calibration wizard hook
 */
export function useLEDCalibrationWizard({ onToast = () => { } } = {}) {
    const [isActive, setIsActive] = useState(false)
    const [currentPort, setCurrentPort] = useState(1)
    const [totalPorts, setTotalPorts] = useState(TOTAL_CABINET_BUTTONS)
    const [mappedCount, setMappedCount] = useState(0)
    const [skippedCount, setSkippedCount] = useState(0)
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState(null)
    const [token, setToken] = useState(null)

    // Debounce ref to prevent double-clicks
    const confirmingRef = useRef(false)

    /**
     * Start the calibration wizard
     */
    const startWizard = useCallback(async (config = {}) => {
        setIsLoading(true)
        setError(null)

        try {
            const response = await fetch(`${getApiBase()}/api/local/led/calibrate/wizard/start`, {
                method: 'POST',
                headers: buildStandardHeaders({
                    panel: 'led-blinky',
                    scope: 'config',
                    extraHeaders: { 'Content-Type': 'application/json' }
                }),
                body: JSON.stringify({
                    total_ports: config.totalPorts || TOTAL_CABINET_BUTTONS,
                    player_count: 4
                })
            })

            if (!response.ok) {
                throw new Error(`Failed to start wizard: ${response.status}`)
            }

            const data = await response.json()

            setIsActive(true)
            setCurrentPort(data.current_port || 1)
            setTotalPorts(data.total_ports || TOTAL_CABINET_BUTTONS)
            setMappedCount(0)
            setSkippedCount(0)
            setToken(data.token)

            onToast('Calibration started - click the button that lights up!', 'success')
            return data
        } catch (err) {
            setError(err.message)
            onToast(`Failed to start calibration: ${err.message}`, 'error')
            throw err
        } finally {
            setIsLoading(false)
        }
    }, [onToast])

    /**
     * Confirm a button mapping - user clicked the button that was blinking
     */
    const confirmButton = useCallback(async (player, button) => {
        // Debounce protection
        if (confirmingRef.current || !isActive) {
            return null
        }

        confirmingRef.current = true
        setIsLoading(true)
        setError(null)

        const logicalId = toLogicalId(player, button)

        try {
            const response = await fetch(`${getApiBase()}/api/local/led/calibrate/wizard/confirm`, {
                method: 'POST',
                headers: buildStandardHeaders({
                    panel: 'led-blinky',
                    scope: 'config',
                    extraHeaders: { 'Content-Type': 'application/json' }
                }),
                body: JSON.stringify({
                    logical_id: logicalId,
                    description: `Port ${currentPort} mapped via wizard`
                })
            })

            if (!response.ok) {
                throw new Error(`Failed to confirm mapping: ${response.status}`)
            }

            const data = await response.json()

            setCurrentPort(data.current_port || currentPort + 1)
            setMappedCount(data.mapped_count || mappedCount + 1)

            if (data.status === 'complete') {
                setIsActive(false)
                onToast(`Calibration complete! Mapped ${data.mapped_count} buttons.`, 'success')
            } else {
                onToast(`Mapped: ${logicalId} → Port ${currentPort}`, 'info')
            }

            return data
        } catch (err) {
            setError(err.message)
            onToast(`Failed to confirm mapping: ${err.message}`, 'error')
            throw err
        } finally {
            setIsLoading(false)
            // Reset debounce after short delay
            setTimeout(() => {
                confirmingRef.current = false
            }, 300)
        }
    }, [isActive, currentPort, mappedCount, onToast])

    /**
     * Skip the current port (no LED visible or broken)
     */
    const skipPort = useCallback(async () => {
        setIsLoading(true)
        setError(null)

        try {
            const response = await fetch(`${getApiBase()}/api/local/led/calibrate/wizard/skip`, {
                method: 'POST',
                headers: buildStandardHeaders({
                    panel: 'led-blinky',
                    scope: 'config',
                    extraHeaders: { 'Content-Type': 'application/json' }
                })
            })

            if (!response.ok) {
                throw new Error(`Failed to skip port: ${response.status}`)
            }

            const data = await response.json()

            setCurrentPort(data.current_port || currentPort + 1)
            setSkippedCount(data.skipped_count || skippedCount + 1)

            if (data.status === 'complete') {
                setIsActive(false)
                onToast('Calibration complete!', 'success')
            } else {
                onToast(`Skipped port ${currentPort}`, 'warning')
            }

            return data
        } catch (err) {
            setError(err.message)
            onToast(`Failed to skip port: ${err.message}`, 'error')
            throw err
        } finally {
            setIsLoading(false)
        }
    }, [currentPort, skippedCount, onToast])

    /**
     * Finish the calibration wizard and save mappings
     */
    const finishWizard = useCallback(async () => {
        setIsLoading(true)
        setError(null)

        try {
            const response = await fetch(`${getApiBase()}/api/local/led/calibrate/wizard/finish`, {
                method: 'POST',
                headers: buildStandardHeaders({
                    panel: 'led-blinky',
                    scope: 'config',
                    extraHeaders: { 'Content-Type': 'application/json' }
                })
            })

            if (!response.ok) {
                throw new Error(`Failed to finish wizard: ${response.status}`)
            }

            const data = await response.json()

            setIsActive(false)

            // Show translation result if available (Phase 2 translator)
            if (data.translation?.success) {
                onToast(`✅ Mapped ${data.mapped_count} buttons → LEDBlinkyInputMap.xml updated!`, 'success')
            } else if (data.translation?.error) {
                onToast(`⚠️ Saved ${data.mapped_count} mappings but XML translation failed: ${data.translation.error}`, 'warning')
            } else {
                onToast(`Saved ${data.mapped_count} mappings to ${data.file_path}`, 'success')
            }

            return data
        } catch (err) {
            setError(err.message)
            onToast(`Failed to save mappings: ${err.message}`, 'error')
            throw err
        } finally {
            setIsLoading(false)
        }
    }, [onToast])

    /**
     * Cancel the calibration wizard without saving
     */
    const cancelWizard = useCallback(async () => {
        setIsLoading(true)
        setError(null)

        try {
            const response = await fetch(`${getApiBase()}/api/local/led/calibrate/wizard/cancel`, {
                method: 'POST',
                headers: buildStandardHeaders({
                    panel: 'led-blinky',
                    scope: 'config',
                    extraHeaders: { 'Content-Type': 'application/json' }
                })
            })

            if (!response.ok) {
                throw new Error(`Failed to cancel wizard: ${response.status}`)
            }

            setIsActive(false)
            setCurrentPort(1)
            setMappedCount(0)
            setSkippedCount(0)

            onToast('Calibration cancelled', 'info')
            return { status: 'cancelled' }
        } catch (err) {
            setError(err.message)
            onToast(`Failed to cancel: ${err.message}`, 'error')
            // Still reset state even if API fails
            setIsActive(false)
            throw err
        } finally {
            setIsLoading(false)
        }
    }, [onToast])

    /**
     * Get current wizard status from backend
     */
    const refreshStatus = useCallback(async () => {
        try {
            const response = await fetch(`${getApiBase()}/api/local/led/calibrate/wizard/status`, {
                headers: buildStandardHeaders({ panel: 'led-blinky', scope: 'state' })
            })

            if (!response.ok) {
                return null
            }

            const data = await response.json()

            setIsActive(data.is_active)
            setCurrentPort(data.current_port)
            setTotalPorts(data.total_ports)
            setMappedCount(data.mapped_count)
            setSkippedCount(data.skipped_count)

            return data
        } catch (err) {
            console.warn('Failed to refresh calibration status:', err)
            return null
        }
    }, [])

    // Computed progress percentage
    const progressPercent = totalPorts > 0
        ? Math.round((currentPort - 1) / totalPorts * 100)
        : 0

    return {
        // State
        isActive,
        currentPort,
        totalPorts,
        mappedCount,
        skippedCount,
        progressPercent,
        isLoading,
        error,
        token,

        // Actions
        startWizard,
        confirmButton,
        skipPort,
        finishWizard,
        cancelWizard,
        refreshStatus,

        // Constants
        CABINET_BUTTONS,
        TOTAL_CABINET_BUTTONS
    }
}

export default useLEDCalibrationWizard
