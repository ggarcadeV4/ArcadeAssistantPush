/**
 * ArcadePanelPreview - Visual LED control panel preview
 * 
 * Shows a stylized arcade control panel that lights up in real-time
 * based on the selected color mapping. Used in LED Blinky panel
 * to give users visual feedback of their LED configuration.
 */
import React, { useMemo } from 'react'

// Button position layout (8-button layout for P1/P2, 4-button for P3/P4)
// Row 1: 1, 2, 3, 7
// Row 2: 4, 5, 6, 8
// Plus Start and Coin buttons
const BUTTON_POSITIONS = {
    // Player 1 - Top Left
    p1: {
        button1: { cx: 50, cy: 60, label: '1' },    // Row 1
        button2: { cx: 100, cy: 55, label: '2' },
        button3: { cx: 150, cy: 60, label: '3' },
        button7: { cx: 200, cy: 65, label: '7' },
        button4: { cx: 60, cy: 105, label: '4' },   // Row 2
        button5: { cx: 110, cy: 100, label: '5' },
        button6: { cx: 160, cy: 105, label: '6' },
        button8: { cx: 210, cy: 110, label: '8' },
        start: { cx: 80, cy: 150, label: 'ST' },    // Bottom
        coin: { cx: 170, cy: 150, label: 'CO' }
    },
    // Player 2 - Top Right
    p2: {
        button1: { cx: 380, cy: 60, label: '1' },   // Row 1
        button2: { cx: 430, cy: 55, label: '2' },
        button3: { cx: 480, cy: 60, label: '3' },
        button7: { cx: 530, cy: 65, label: '7' },
        button4: { cx: 390, cy: 105, label: '4' },  // Row 2
        button5: { cx: 440, cy: 100, label: '5' },
        button6: { cx: 490, cy: 105, label: '6' },
        button8: { cx: 540, cy: 110, label: '8' },
        start: { cx: 410, cy: 150, label: 'ST' },   // Bottom
        coin: { cx: 500, cy: 150, label: 'CO' }
    },
    // Player 3 - Bottom Left (4 buttons + start/coin)
    p3: {
        button1: { cx: 50, cy: 210, label: '1' },
        button2: { cx: 100, cy: 205, label: '2' },
        button3: { cx: 150, cy: 210, label: '3' },
        button4: { cx: 200, cy: 215, label: '4' },
        start: { cx: 80, cy: 255, label: 'ST' },
        coin: { cx: 170, cy: 255, label: 'CO' }
    },
    // Player 4 - Bottom Right (4 buttons + start/coin)
    p4: {
        button1: { cx: 380, cy: 210, label: '1' },
        button2: { cx: 430, cy: 205, label: '2' },
        button3: { cx: 480, cy: 210, label: '3' },
        button4: { cx: 530, cy: 215, label: '4' },
        start: { cx: 410, cy: 255, label: 'ST' },
        coin: { cx: 500, cy: 255, label: 'CO' }
    }
}

// Parse hex color to RGB components
const hexToRgb = (hex) => {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
    return result ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16)
    } : { r: 128, g: 128, b: 128 }
}

// Generate glow filter ID
const getGlowId = (color) => `glow-${color.replace('#', '')}`

/**
 * Single LED button with glow effect
 */
const LEDButton = ({ cx, cy, color = '#333', label, isActive = true, radius = 22, onClick }) => {
    const rgb = hexToRgb(color)
    const glowColor = isActive ? color : '#222'
    const fillColor = isActive ? color : '#1a1a1a'
    const glowId = getGlowId(color)

    return (
        <g
            style={{ cursor: onClick ? 'pointer' : 'default' }}
            onClick={onClick}
        >
            {/* Outer ring (plastic bezel) */}
            <circle
                cx={cx}
                cy={cy}
                r={radius + 4}
                fill="#1a1a1a"
                stroke="#333"
                strokeWidth="2"
            />

            {/* LED button face with glow */}
            <circle
                cx={cx}
                cy={cy}
                r={radius}
                fill={fillColor}
                stroke={isActive ? glowColor : '#333'}
                strokeWidth="2"
                style={{
                    filter: isActive ? `drop-shadow(0 0 8px ${glowColor}) drop-shadow(0 0 16px ${glowColor})` : 'none',
                    transition: 'all 0.2s ease'
                }}
            />

            {/* Highlight (top edge shine) */}
            <ellipse
                cx={cx}
                cy={cy - radius * 0.4}
                rx={radius * 0.5}
                ry={radius * 0.2}
                fill={`rgba(255, 255, 255, ${isActive ? 0.4 : 0.1})`}
                style={{ pointerEvents: 'none' }}
            />

            {/* Button label */}
            <text
                x={cx}
                y={cy + 5}
                textAnchor="middle"
                fill={isActive ? '#fff' : '#555'}
                fontSize="12"
                fontWeight="bold"
                fontFamily="system-ui, sans-serif"
                style={{
                    pointerEvents: 'none',
                    textShadow: isActive ? '0 0 4px rgba(0,0,0,0.8)' : 'none'
                }}
            >
                {label}
            </text>
        </g>
    )
}

// Joystick visualization - REMOVED per user request

/**
 * Main arcade panel preview component
 * Supports 1-4 player layouts
 */
export default function ArcadePanelPreview({
    mappingForm = {},
    activeButtons = new Set(),
    onButtonClick,
    showLabels = true,
    playerCount = 4  // Changed from twoPlayer to playerCount
}) {
    // Build button colors from mapping form
    const buttonColors = useMemo(() => {
        const colors = {}

        // Parse mapping form keys like "p1_button1" → { player: 1, button: 1, color: "#FF0000" }
        Object.entries(mappingForm).forEach(([key, color]) => {
            const match = key.match(/^p(\d+)_button(\d+)$/i)
            if (match) {
                const [, player, button] = match
                colors[`p${player}.button${button}`] = color
            }
            // Also support start/coin format
            const startCoinMatch = key.match(/^p(\d+)_(start|coin)$/i)
            if (startCoinMatch) {
                const [, player, control] = startCoinMatch
                colors[`p${player}.${control.toLowerCase()}`] = color
            }
        })

        return colors
    }, [mappingForm])

    const renderPlayerButtons = (playerNum, positions) => {
        return Object.entries(positions).map(([buttonKey, pos]) => {
            const logicalKey = `p${playerNum}.${buttonKey}`
            const color = buttonColors[logicalKey] || '#333333'
            const isActive = !activeButtons.size || activeButtons.has(logicalKey)

            return (
                <LEDButton
                    key={logicalKey}
                    cx={pos.cx}
                    cy={pos.cy}
                    color={color}
                    label={showLabels ? pos.label : ''}
                    isActive={isActive}
                    onClick={onButtonClick ? () => onButtonClick(playerNum, buttonKey) : undefined}
                />
            )
        })
    }

    // Calculate viewBox height based on player count
    const viewBoxHeight = playerCount > 2 ? 300 : 180
    const panelHeight = viewBoxHeight - 10

    // Player colors
    const playerColors = {
        1: '#9333ea',  // Purple
        2: '#06b6d4',  // Cyan
        3: '#f59e0b',  // Orange
        4: '#10b981'   // Green
    }

    return (
        <div className="arcade-panel-preview" style={{
            background: 'linear-gradient(180deg, #0a0a0a 0%, #151515 100%)',
            borderRadius: '12px',
            padding: '16px',
            border: '1px solid #333'
        }}>
            <svg
                viewBox={`0 0 590 ${viewBoxHeight}`}
                width="100%"
                height="auto"
                style={{ maxWidth: '600px', display: 'block', margin: '0 auto' }}
            >
                {/* Panel background */}
                <rect
                    x="5" y="5"
                    width="580" height={panelHeight}
                    rx="12" ry="12"
                    fill="linear-gradient(180deg, #1a1a1a 0%, #0d0d0d 100%)"
                    stroke="#2a2a2a"
                    strokeWidth="2"
                />

                {/* Control panel surface texture */}
                <rect
                    x="10" y="10"
                    width="570" height={panelHeight - 10}
                    rx="8" ry="8"
                    fill="url(#panelGradient)"
                    opacity="0.9"
                />

                {/* Player labels */}
                {showLabels && (
                    <>
                        <text x="140" y="35" textAnchor="middle" fill={playerColors[1]} fontSize="14" fontWeight="bold">
                            PLAYER 1
                        </text>
                        {playerCount >= 2 && (
                            <text x="450" y="35" textAnchor="middle" fill={playerColors[2]} fontSize="14" fontWeight="bold">
                                PLAYER 2
                            </text>
                        )}
                        {playerCount >= 3 && (
                            <text x="140" y="185" textAnchor="middle" fill={playerColors[3]} fontSize="14" fontWeight="bold">
                                PLAYER 3
                            </text>
                        )}
                        {playerCount >= 4 && (
                            <text x="450" y="185" textAnchor="middle" fill={playerColors[4]} fontSize="14" fontWeight="bold">
                                PLAYER 4
                            </text>
                        )}
                    </>
                )}

                {/* Player 1 buttons - always shown */}
                {renderPlayerButtons(1, BUTTON_POSITIONS.p1)}

                {/* Player 2 buttons */}
                {playerCount >= 2 && renderPlayerButtons(2, BUTTON_POSITIONS.p2)}

                {/* Player 3 buttons */}
                {playerCount >= 3 && renderPlayerButtons(3, BUTTON_POSITIONS.p3)}

                {/* Player 4 buttons */}
                {playerCount >= 4 && renderPlayerButtons(4, BUTTON_POSITIONS.p4)}

                {/* Gradients and effects */}
                <defs>
                    <linearGradient id="panelGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                        <stop offset="0%" stopColor="#1f1f1f" />
                        <stop offset="50%" stopColor="#141414" />
                        <stop offset="100%" stopColor="#0a0a0a" />
                    </linearGradient>
                </defs>
            </svg>

            {/* Legend */}
            <div style={{
                display: 'flex',
                justifyContent: 'center',
                gap: '16px',
                marginTop: '12px',
                fontSize: '11px',
                color: '#888'
            }}>
                <span>ST = Start</span>
                <span>CO = Coin</span>
                <span>1-8 = Action Buttons</span>
            </div>
        </div>
    )
}
