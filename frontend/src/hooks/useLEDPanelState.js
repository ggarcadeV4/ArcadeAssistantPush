/**
 * useLEDPanelState — State machine for the LED Blinky single-view panel.
 *
 * Manages four states: idle, active, calibration, design.
 * Integrates useLEDCalibrationWizard for the blink-click-map flow.
 * Integrates useLEDCalibrationSession for AI command global helpers.
 * Integrates useDesignMode for button color painting + profile save/load.
 *
 * Usage:
 *   const panel = useLEDPanelState({ showToast })
 *   panel.mode          → 'idle' | 'active' | 'calibration' | 'design'
 *   panel.wizard        → calibration wizard state & actions
 *   panel.calibration   → calibration session (flash/assign for AI)
 *   panel.design       → design mode state (brush, paint, profiles)
 */
import { useState, useCallback } from 'react'
import { useLEDCalibrationWizard } from './useLEDCalibrationWizard'
import { useLEDCalibrationSession } from './useLEDCalibrationSession'
import useDesignMode from './useDesignMode'
import { runLEDPattern, listLEDChannelMappings } from '../services/ledBlinkyClient'

// ─── Default idle colors (purple buttons, amber start/coin) ──────────
const IDLE_COLORS = (() => {
    const colors = {}
    const purple = '#9333ea'
    const utilColor = '#f59e0b'
    for (const player of [1, 2, 3, 4]) {
        const count = player <= 2 ? 8 : 4
        for (let i = 1; i <= count; i++) colors[`p${player}.button${i}`] = purple
        colors[`p${player}.start`] = utilColor
        colors[`p${player}.coin`] = utilColor
    }
    return colors
})()

// ─── Preset animations for idle state ────────────────────────────────
const PRESET_ANIMATIONS = [
    { id: 'idle_pulse', label: 'Idle Pulse' },
    { id: 'rainbow', label: 'Rainbow' },
    { id: 'chase', label: 'Chase' },
    { id: 'breathe', label: 'Breathe' },
    { id: 'knight_rider', label: 'Knight Rider' },
]

/**
 * @param {Object} opts
 * @param {Function} opts.showToast  — portable toast function
 */
export default function useLEDPanelState({ showToast }) {
    // ─── Core State ──────────────────────────────────────────────────
    const [mode, setMode] = useState('idle')
    const [activeGame, setActiveGame] = useState(null)
    const [activeAnimation, setActiveAnimation] = useState('idle_pulse')
    const [buttonColors, setButtonColors] = useState(IDLE_COLORS)

    // ─── Channel mappings loader (shared by session + commandContext) ─
    const loadChannelMappings = useCallback(async () => {
        try {
            const result = await listLEDChannelMappings()
            console.log('[LEDBlinky] Channel mappings loaded:', result)
            return result
        } catch (err) {
            console.error('[LEDBlinky] Failed to load channel mappings:', err)
        }
    }, [])

    // ─── Calibration Wizard (blink-click-map flow) ───────────────────
    const wizard = useLEDCalibrationWizard({ onToast: showToast })

    // ─── Calibration Session (flash/assign + AI global helpers) ──────
    const calibration = useLEDCalibrationSession({
        showToast,
        loadChannelMappings,
        channelSelection: null,  // will be wired when design mode adds channel picker
    })

    // ─── Design Mode (button color painting + profiles) ───────────────
    const design = useDesignMode({ showToast })

    // ─── Transition: → idle ──────────────────────────────────────────
    const enterIdle = useCallback(() => {
        setMode('idle')
        setActiveGame(null)
        setButtonColors(IDLE_COLORS)
    }, [])

    // ─── Transition: → active (game launched) ────────────────────────
    const enterActive = useCallback((game) => {
        setMode('active')
        setActiveGame(game)
        if (game?.colors) {
            setButtonColors(game.colors)
        }
    }, [])

    // ─── Transition: → calibration (toggle) ──────────────────────────
    const toggleCalibration = useCallback(async () => {
        if (mode === 'calibration') {
            // Exit — finish or cancel based on progress
            if (wizard.mappedCount > 0) {
                try {
                    await wizard.finishWizard()
                } catch {
                    // finishWizard already toasts errors
                }
            } else {
                try {
                    await wizard.cancelWizard()
                } catch {
                    // cancelWizard already toasts errors
                }
            }
            setMode('idle')
            setButtonColors(IDLE_COLORS)
        } else {
            // Enter calibration
            try {
                await wizard.startWizard()
                setMode('calibration')
            } catch {
                // startWizard already toasts errors
            }
        }
    }, [mode, wizard])

    // ─── Transition: → design (toggle) ───────────────────────────────
    const toggleDesign = useCallback(() => {
        if (mode === 'design') {
            setMode('idle')
            setButtonColors(IDLE_COLORS)
        } else {
            setMode('design')
        }
    }, [mode])

    // ─── Button click dispatcher (mode-aware) ────────────────────────
    const handleButtonClick = useCallback((player, buttonId) => {
        if (mode === 'calibration') {
            // Map the blinking port to this button via wizard
            wizard.confirmButton(player, buttonId)
        } else if (mode === 'design') {
            // Paint with selected brush color
            design.paintButton(player, buttonId)
        }
    }, [mode, wizard, design])

    // ─── Skip port (calibration only) ────────────────────────────────
    const skipPort = useCallback(() => {
        if (mode === 'calibration') {
            wizard.skipPort()
        }
    }, [mode, wizard])

    // ─── Animation preset (idle only) ────────────────────────────────
    const playPreset = useCallback(async (presetId) => {
        setActiveAnimation(presetId)
        try {
            await runLEDPattern(presetId)
            showToast(`Playing: ${presetId}`, 'success')
        } catch (err) {
            console.error('[LEDBlinky] Pattern error:', err)
        }
    }, [showToast])

    // ─── Resolve current button colors based on mode ─────────────────
    const resolvedColors = (() => {
        if (mode === 'active' && activeGame?.colors) return activeGame.colors
        if (mode === 'design' && design.hasChanges) {
            // Merge: custom painted colors override idle defaults
            return { ...IDLE_COLORS, ...design.customColors }
        }
        return buttonColors
    })()

    // ─── Status badge info ───────────────────────────────────────────
    const getStatusBadge = useCallback((connectionStatus) => {
        switch (mode) {
            case 'active':
                return {
                    className: 'led-panel__status-badge--active',
                    dotClass: 'led-panel__status-dot--active',
                    text: `Steam Mode Active: Playing ${activeGame?.name || 'Unknown'}`,
                }
            case 'calibration':
                return {
                    className: 'led-panel__status-badge--calibration',
                    dotClass: 'led-panel__status-dot--calibration',
                    text: `Calibration — Port ${wizard.currentPort} of ${wizard.totalPorts}`,
                }
            case 'design':
                return {
                    className: 'led-panel__status-badge--design',
                    dotClass: 'led-panel__status-dot--design',
                    text: 'Design Mode — Click buttons to set colors',
                }
            default:
                return {
                    className: 'led-panel__status-badge--idle',
                    dotClass: 'led-panel__status-dot--idle',
                    text:
                        connectionStatus === 'connected'
                            ? 'Connected'
                            : connectionStatus === 'simulated'
                                ? 'Simulation Mode'
                                : connectionStatus === 'error'
                                    ? 'LED Service Error'
                                    : connectionStatus === 'connecting'
                                        ? 'Connecting to Gateway'
                                        : connectionStatus === 'disconnected'
                                            ? 'Gateway Disconnected'
                                            : 'LED Status Unknown',
                }
        }
    }, [mode, activeGame, wizard.currentPort, wizard.totalPorts])

    return {
        // State
        mode,
        activeGame,
        activeAnimation,
        resolvedColors,

        // Wizard (full blink-click-map flow)
        wizard,

        // Calibration session (flash/assign + AI global helpers)
        calibration,

        // Design mode (brush, paint, profiles)
        design,

        // Channel mappings
        loadChannelMappings,

        // Transitions
        enterIdle,
        enterActive,
        toggleCalibration,
        toggleDesign,

        // Handlers
        handleButtonClick,
        skipPort,
        playPreset,
        getStatusBadge,

        // Constants
        PRESET_ANIMATIONS,
        IDLE_COLORS,
    }
}
