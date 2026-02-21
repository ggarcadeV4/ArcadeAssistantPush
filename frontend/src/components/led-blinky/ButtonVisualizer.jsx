/**
 * ButtonVisualizer — Central arcade panel visualizer
 * 
 * Evolved from ArcadePanelPreview. Renders the 4-player button layout
 * with a central trackball. Supports multiple modes:
 *   - idle: uniform preset colors, passive display
 *   - active: game-specific colors per button
 *   - calibration: highlight blinking port, click to map
 *   - design: click to open color picker
 * 
 * Layout toggle: 2-Player shows P1+P2 only, 4-Player shows all.
 */
import React, { useMemo } from 'react'

// ─── Button Layout Definitions ───────────────────────────────────────
// 8-button layout for P1/P2 (Row 1: 1,2,3,7 | Row 2: 4,5,6,8 + ST/SE)
// 4-button layout for P3/P4 (1,2,3,4 + ST/SE)
const BUTTON_LAYOUTS = {
    p1: {
        label: 'P1',
        buttons: [
            { id: 'button1', row: 1, col: 0, label: '1' },
            { id: 'button2', row: 1, col: 1, label: '2' },
            { id: 'button3', row: 1, col: 2, label: '3' },
            { id: 'button7', row: 1, col: 3, label: '7' },
            { id: 'button4', row: 2, col: 0, label: '4' },
            { id: 'button5', row: 2, col: 1, label: '5' },
            { id: 'button6', row: 2, col: 2, label: '6' },
            { id: 'button8', row: 2, col: 3, label: '8' },
            { id: 'start', row: 0, col: 0, label: 'ST', isUtil: true },
            { id: 'coin', row: 0, col: 1, label: 'SE', isUtil: true },
        ]
    },
    p2: {
        label: 'P2',
        buttons: [
            { id: 'button1', row: 1, col: 0, label: '1' },
            { id: 'button2', row: 1, col: 1, label: '2' },
            { id: 'button3', row: 1, col: 2, label: '3' },
            { id: 'button7', row: 1, col: 3, label: '7' },
            { id: 'button4', row: 2, col: 0, label: '4' },
            { id: 'button5', row: 2, col: 1, label: '5' },
            { id: 'button6', row: 2, col: 2, label: '6' },
            { id: 'button8', row: 2, col: 3, label: '8' },
            { id: 'start', row: 0, col: 0, label: 'ST', isUtil: true },
            { id: 'coin', row: 0, col: 1, label: 'SE', isUtil: true },
        ]
    },
    p3: {
        label: 'P3',
        buttons: [
            { id: 'button1', row: 1, col: 0, label: '1' },
            { id: 'button2', row: 1, col: 1, label: '2' },
            { id: 'start', row: 1, col: 2, label: 'ST', isUtil: true },
            { id: 'button3', row: 2, col: 0, label: '3' },
            { id: 'button4', row: 2, col: 1, label: '4' },
            { id: 'coin', row: 2, col: 2, label: 'SE', isUtil: true },
        ]
    },
    p4: {
        label: 'P4',
        buttons: [
            { id: 'start', row: 1, col: 0, label: 'ST', isUtil: true },
            { id: 'button1', row: 1, col: 1, label: '1' },
            { id: 'button2', row: 1, col: 2, label: '2' },
            { id: 'coin', row: 2, col: 0, label: 'SE', isUtil: true },
            { id: 'button3', row: 2, col: 1, label: '3' },
            { id: 'button4', row: 2, col: 2, label: '4' },
        ]
    }
}

// ─── Single LED Button ───────────────────────────────────────────────
function LEDButton({ color = '#333', label, isActive = true, isBlinking = false, isUtil = false, onClick, style }) {
    const radius = isUtil ? 16 : 22
    const glowColor = isActive ? color : '#222'
    const fillColor = isActive ? color : '#1a1a1a'

    return (
        <div
            className={`led-btn ${isBlinking ? 'led-btn--blinking' : ''} ${isUtil ? 'led-btn--util' : ''}`}
            onClick={onClick}
            style={{
                width: radius * 2 + 8,
                height: radius * 2 + 8,
                borderRadius: '50%',
                background: '#1a1a1a',
                border: `2px solid ${isActive ? glowColor : '#333'}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: onClick ? 'pointer' : 'default',
                position: 'relative',
                boxShadow: isActive
                    ? `0 0 8px ${glowColor}, 0 0 16px ${glowColor}40, inset 0 0 6px ${glowColor}30`
                    : 'none',
                transition: 'all 0.2s ease',
                ...style,
            }}
        >
            {/* Button face */}
            <div
                style={{
                    width: radius * 2,
                    height: radius * 2,
                    borderRadius: '50%',
                    background: fillColor,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    position: 'relative',
                    overflow: 'hidden',
                }}
            >
                {/* Highlight shine */}
                <div
                    style={{
                        position: 'absolute',
                        top: '15%',
                        left: '25%',
                        width: '50%',
                        height: '25%',
                        borderRadius: '50%',
                        background: `rgba(255,255,255,${isActive ? 0.35 : 0.08})`,
                        pointerEvents: 'none',
                    }}
                />
                {/* Label */}
                <span
                    style={{
                        color: isActive ? '#fff' : '#555',
                        fontSize: isUtil ? 10 : 13,
                        fontWeight: 700,
                        fontFamily: 'system-ui, sans-serif',
                        textShadow: isActive ? '0 0 4px rgba(0,0,0,0.8)' : 'none',
                        pointerEvents: 'none',
                        userSelect: 'none',
                        position: 'relative',
                        zIndex: 1,
                    }}
                >
                    {label}
                </span>
            </div>
        </div>
    )
}

// ─── Trackball ───────────────────────────────────────────────────────
function Trackball() {
    return (
        <div
            style={{
                width: 120,
                height: 120,
                borderRadius: '50%',
                background: 'radial-gradient(circle at 40% 35%, #1a3a4a, #0a1520)',
                border: '3px solid #0ea5e9',
                boxShadow: '0 0 20px #0ea5e940, 0 0 40px #0ea5e920, inset 0 0 20px #0ea5e915',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
            }}
        >
            <span
                style={{
                    color: '#0ea5e9',
                    fontSize: 14,
                    fontWeight: 700,
                    letterSpacing: 2,
                    textTransform: 'uppercase',
                    opacity: 0.7,
                }}
            >
                TRACK
            </span>
        </div>
    )
}

// ─── Player Button Group ─────────────────────────────────────────────
function PlayerGroup({ player, layout, buttonColors, blinkingButton, mode, onButtonClick }) {
    const { label, buttons } = layout

    // Separate util buttons and action buttons by row
    const utilButtons = buttons.filter(b => b.isUtil)
    const row1 = buttons.filter(b => b.row === 1 && !b.isUtil)
    const row2 = buttons.filter(b => b.row === 2 && !b.isUtil)

    const getColor = (buttonId) => {
        const key = `p${player}.${buttonId}`
        return buttonColors[key] || '#333'
    }

    const isBlinking = (buttonId) => {
        return mode === 'calibration' && blinkingButton === `p${player}.${buttonId}`
    }

    const handleClick = (buttonId) => {
        if (onButtonClick) {
            onButtonClick(player, buttonId)
        }
    }

    const isClickable = mode === 'calibration' || mode === 'design'

    return (
        <div className="player-group" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
            <span style={{ color: '#9ca3af', fontSize: 14, fontWeight: 700, letterSpacing: 1, marginBottom: 4 }}>
                {label}
            </span>

            {/* Utility buttons (ST/SE) */}
            <div style={{ display: 'flex', gap: 6, marginBottom: 4 }}>
                {utilButtons.map(btn => (
                    <LEDButton
                        key={btn.id}
                        color={getColor(btn.id)}
                        label={btn.label}
                        isActive={true}
                        isUtil={true}
                        isBlinking={isBlinking(btn.id)}
                        onClick={isClickable ? () => handleClick(btn.id) : undefined}
                    />
                ))}
            </div>

            {/* Row 1 — action buttons */}
            <div style={{ display: 'flex', gap: 6 }}>
                {row1.map(btn => (
                    <LEDButton
                        key={btn.id}
                        color={getColor(btn.id)}
                        label={btn.label}
                        isActive={true}
                        isBlinking={isBlinking(btn.id)}
                        onClick={isClickable ? () => handleClick(btn.id) : undefined}
                    />
                ))}
            </div>

            {/* Row 2 — action buttons */}
            <div style={{ display: 'flex', gap: 6 }}>
                {row2.map(btn => (
                    <LEDButton
                        key={btn.id}
                        color={getColor(btn.id)}
                        label={btn.label}
                        isActive={true}
                        isBlinking={isBlinking(btn.id)}
                        onClick={isClickable ? () => handleClick(btn.id) : undefined}
                    />
                ))}
            </div>
        </div>
    )
}

// ─── Main Visualizer ─────────────────────────────────────────────────
export default function ButtonVisualizer({
    playerCount = 4,
    buttonColors = {},
    mode = 'idle',         // idle | active | calibration | design
    blinkingButton = null, // e.g. "p1.button3" — for calibration mode
    onButtonClick,         // (player, buttonId) => void
}) {
    const showP3P4 = playerCount > 2

    // Build color map from either mapped form or direct colors
    const resolvedColors = useMemo(() => {
        const colors = {}
        Object.entries(buttonColors).forEach(([key, color]) => {
            // Support both formats: "p1.button1" and "p1_button1"
            const dotKey = key.replace(/_/g, '.')
            const underKey = key.replace(/\./g, '_')
            // Normalize to dot format
            if (key.includes('_')) {
                const match = key.match(/^p(\d+)_(.+)$/i)
                if (match) colors[`p${match[1]}.${match[2]}`] = color
            } else {
                colors[key] = color
            }
        })
        return colors
    }, [buttonColors])

    return (
        <div
            className="button-visualizer"
            style={{
                background: '#0a0b14',
                border: '1px solid #1f2937',
                borderRadius: 16,
                padding: '32px 24px',
                position: 'relative',
                overflow: 'hidden',
            }}
        >
            {/* Subtle gradient overlay */}
            <div
                style={{
                    position: 'absolute',
                    inset: 0,
                    background: 'radial-gradient(ellipse at center, transparent 40%, #0a0b1480 100%)',
                    pointerEvents: 'none',
                }}
            />

            {/* Layout grid */}
            <div
                style={{
                    position: 'relative',
                    display: 'grid',
                    gridTemplateColumns: '1fr auto 1fr',
                    gridTemplateRows: showP3P4 ? 'auto auto' : 'auto',
                    gap: '24px 32px',
                    alignItems: 'center',
                    justifyItems: 'center',
                    minHeight: showP3P4 ? 360 : 200,
                }}
            >
                {/* Row 1: P3 / Trackball / P4 (only if 4-player) */}
                {showP3P4 && (
                    <>
                        <PlayerGroup
                            player={3}
                            layout={BUTTON_LAYOUTS.p3}
                            buttonColors={resolvedColors}
                            blinkingButton={blinkingButton}
                            mode={mode}
                            onButtonClick={onButtonClick}
                        />
                        <Trackball />
                        <PlayerGroup
                            player={4}
                            layout={BUTTON_LAYOUTS.p4}
                            buttonColors={resolvedColors}
                            blinkingButton={blinkingButton}
                            mode={mode}
                            onButtonClick={onButtonClick}
                        />
                    </>
                )}

                {/* Row 2 (or Row 1 if 2-player): P1 / (Trackball if 2P) / P2 */}
                <PlayerGroup
                    player={1}
                    layout={BUTTON_LAYOUTS.p1}
                    buttonColors={resolvedColors}
                    blinkingButton={blinkingButton}
                    mode={mode}
                    onButtonClick={onButtonClick}
                />
                {!showP3P4 && <Trackball />}
                {showP3P4 && <div />} {/* Empty center cell for 4P */}
                <PlayerGroup
                    player={2}
                    layout={BUTTON_LAYOUTS.p2}
                    buttonColors={resolvedColors}
                    blinkingButton={blinkingButton}
                    mode={mode}
                    onButtonClick={onButtonClick}
                />
            </div>
        </div>
    )
}
