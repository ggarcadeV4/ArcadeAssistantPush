import React, { useCallback, useMemo } from 'react';
import PropTypes from 'prop-types';

/**
 * ClickableCabinetDisplay - Visual arcade cabinet control panel with clickable controls
 * 
 * Users click any control (joystick direction or button) to enter capture mode for that control.
 * Visual states show mapped vs unmapped vs capturing controls.
 */

// Control definitions for each player
const PLAYER_CONFIGS = {
    1: { buttons: 8, position: 'bottom-left', label: 'P1' },
    2: { buttons: 8, position: 'bottom-right', label: 'P2' },
    3: { buttons: 4, position: 'top-left', label: 'P3' },
    4: { buttons: 4, position: 'top-right', label: 'P4' },
};

/**
 * Get display name for a control key
 */
function getControlDisplayName(controlKey) {
    if (!controlKey) return '';
    const [player, control] = controlKey.split('.');
    const playerNum = player.replace('p', 'Player ');

    if (control === 'up') return `${playerNum} ↑ Up`;
    if (control === 'down') return `${playerNum} ↓ Down`;
    if (control === 'left') return `${playerNum} ← Left`;
    if (control === 'right') return `${playerNum} → Right`;
    if (control === 'start') return `${playerNum} START`;
    if (control === 'coin') return `${playerNum} COIN`;
    if (control?.startsWith('button')) {
        const num = control.replace('button', '');
        return `${playerNum} Button ${num}`;
    }
    return controlKey;
}

/**
 * Clickable Joystick Component - 4 directional arrows
 */
function ClickableJoystick({ player, mappings, capturingControl, onControlClick }) {
    const directions = ['up', 'down', 'left', 'right'];
    const arrows = { up: '↑', down: '↓', left: '←', right: '→' };

    return (
        <div className="clickable-joystick">
            {directions.map(dir => {
                const controlKey = `p${player}.${dir}`;
                const isMapped = !!mappings[controlKey]?.keycode;
                const isCapturing = capturingControl === controlKey;

                const classes = [
                    'joystick-arrow',
                    dir,
                    isMapped ? 'control-mapped' : 'control-unmapped',
                    isCapturing ? 'control-capturing' : '',
                ].filter(Boolean).join(' ');

                return (
                    <button
                        key={dir}
                        className={classes}
                        onClick={() => onControlClick(controlKey)}
                        title={`Click to map ${getControlDisplayName(controlKey)}`}
                        aria-label={getControlDisplayName(controlKey)}
                    >
                        {arrows[dir]}
                    </button>
                );
            })}
            <div className="joystick-center" />
        </div>
    );
}

/**
 * Clickable Action Button Component
 */
function ClickableActionButton({ player, buttonNum, mappings, capturingControl, onControlClick }) {
    const controlKey = `p${player}.button${buttonNum}`;
    const isMapped = !!mappings[controlKey]?.keycode;
    const isCapturing = capturingControl === controlKey;

    const classes = [
        'clickable-button',
        isMapped ? 'control-mapped' : 'control-unmapped',
        isCapturing ? 'control-capturing' : '',
    ].filter(Boolean).join(' ');

    return (
        <button
            className={classes}
            onClick={() => onControlClick(controlKey)}
            title={`Click to map ${getControlDisplayName(controlKey)}`}
            aria-label={getControlDisplayName(controlKey)}
            style={{ position: 'relative' }}
        >
            {buttonNum}
        </button>
    );
}

/**
 * Clickable System Button (START/COIN)
 */
function ClickableSystemButton({ player, type, mappings, capturingControl, onControlClick }) {
    const controlKey = `p${player}.${type}`;
    const isMapped = !!mappings[controlKey]?.keycode;
    const isCapturing = capturingControl === controlKey;

    const classes = [
        'clickable-system-button',
        isMapped ? 'control-mapped' : 'control-unmapped',
        isCapturing ? 'control-capturing' : '',
    ].filter(Boolean).join(' ');

    return (
        <button
            className={classes}
            onClick={() => onControlClick(controlKey)}
            title={`Click to map ${getControlDisplayName(controlKey)}`}
            aria-label={getControlDisplayName(controlKey)}
            style={{ position: 'relative' }}
        >
            {type.toUpperCase()}
        </button>
    );
}

/**
 * Single Player Area Component
 */
function PlayerArea({ player, config, mappings, capturingControl, onControlClick, isActive, isHighlighted }) {
    // 8-button layout: Top row 1,2,3,7 / Bottom row 4,5,6,8
    // 4-button layout (P3/P4): Single row 1,2,3,4 across
    const buttonLayout = useMemo(() => {
        if (config.buttons === 8) {
            // 2 rows for 8-button players (P1, P2)
            return [
                [1, 2, 3, 7],  // Top row
                [4, 5, 6, 8],  // Bottom row
            ];
        } else {
            // 2 rows for 4-button players (P3, P4)
            return [
                [1, 2],  // Top row
                [3, 4],  // Bottom row
            ];
        }
    }, [config.buttons]);


    return (
        <div
            className={`controller-player-area ${config.label.toLowerCase()} ${isActive ? 'active' : ''} ${isHighlighted ? 'highlight' : ''}`}
            data-player={player}
        >
            <div className="controller-player-label">{config.label}</div>

            <div className="controller-player-controls">
                {/* Joystick with clickable arrows */}
                <ClickableJoystick
                    player={player}
                    mappings={mappings}
                    capturingControl={capturingControl}
                    onControlClick={onControlClick}
                />

                {/* Action buttons - arranged in rows */}
                <div className={`controller-button-grid controller-button-grid-${config.buttons}`}>
                    {buttonLayout.map((row, rowIndex) => (
                        <div key={rowIndex} className="controller-button-row">
                            {row.map(num => (
                                <ClickableActionButton
                                    key={num}
                                    player={player}
                                    buttonNum={num}
                                    mappings={mappings}
                                    capturingControl={capturingControl}
                                    onControlClick={onControlClick}
                                />
                            ))}
                        </div>
                    ))}
                </div>
            </div>

            {/* System buttons */}
            <div className="controller-start-coin-buttons">
                <ClickableSystemButton
                    player={player}
                    type="start"
                    mappings={mappings}
                    capturingControl={capturingControl}
                    onControlClick={onControlClick}
                />
                <ClickableSystemButton
                    player={player}
                    type="coin"
                    mappings={mappings}
                    capturingControl={capturingControl}
                    onControlClick={onControlClick}
                />
            </div>
        </div>
    );
}

/**
 * Capture Overlay - Shows when capturing a control
 */
function CaptureOverlay({
    controlKey,
    lastCapturedKey,
    captureSource,
    onConfirm,
    onCancel
}) {
    if (!controlKey) return null;

    const displayName = getControlDisplayName(controlKey);

    return (
        <div className="capture-overlay">
            <div className="capture-overlay-content">
                <div className="capture-overlay-title">Mapping Control</div>
                <div className="capture-overlay-control">{displayName}</div>
                <div className="capture-overlay-instruction">
                    Press the physical button on your control panel now...
                </div>

                <div className="capture-overlay-status">
                    <div className={`capture-overlay-key ${lastCapturedKey ? '' : 'waiting'}`}>
                        {lastCapturedKey || '⏳ Waiting for input...'}
                    </div>
                    {captureSource && (
                        <div className="capture-overlay-source">
                            Source: {captureSource === 'keyboard' ? '⌨️ Keyboard' : '🎮 Gamepad'}
                        </div>
                    )}
                </div>

                <div className="capture-overlay-actions">
                    <button
                        className="capture-overlay-btn secondary"
                        onClick={onCancel}
                    >
                        Cancel
                    </button>
                    <button
                        className="capture-overlay-btn primary"
                        onClick={onConfirm}
                        disabled={!lastCapturedKey}
                    >
                        Confirm
                    </button>
                </div>
            </div>
        </div>
    );
}

/**
 * Main ClickableCabinetDisplay Component
 */
export function ClickableCabinetDisplay({
    mappings = {},
    capturingControl = null,
    lastCapturedKey = null,
    captureSource = null,
    onControlClick,
    onConfirmCapture,
    onCancelCapture,
    activePlayer = 1,
    playerCount = 4,  // 2, 3, or 4 player mode
    highlightControl = null,  // For wizard compatibility - highlights a specific control
}) {
    const handleControlClick = useCallback((controlKey) => {
        if (onControlClick) {
            onControlClick(controlKey);
        }
    }, [onControlClick]);

    // Filter players based on playerCount setting
    const visiblePlayers = useMemo(() => {
        const allPlayers = Object.entries(PLAYER_CONFIGS);
        if (playerCount === 2) {
            // Only show P1 and P2
            return allPlayers.filter(([num]) => parseInt(num) <= 2);
        } else if (playerCount === 3) {
            // Show P1, P2, P3
            return allPlayers.filter(([num]) => parseInt(num) <= 3);
        }
        // Show all 4 players
        return allPlayers;
    }, [playerCount]);

    // Determine which player is highlighted (for wizard)
    const highlightedPlayer = useMemo(() => {
        if (!highlightControl) return null;
        const [player] = highlightControl.split('.');
        const num = parseInt(player?.replace('p', ''));
        return isNaN(num) ? null : num;
    }, [highlightControl]);

    return (
        <>
            <div className={`controller-cabinet-display clickable-cabinet players-${playerCount}`}>
                <div className="controller-players-layout">
                    {/* Trackball in center */}
                    <div className="controller-center-trackball">TRACK</div>

                    {/* Render visible player areas */}
                    {visiblePlayers.map(([playerNum, config]) => (
                        <PlayerArea
                            key={playerNum}
                            player={parseInt(playerNum)}
                            config={config}
                            mappings={mappings}
                            capturingControl={capturingControl}
                            onControlClick={handleControlClick}
                            isActive={activePlayer === parseInt(playerNum)}
                            isHighlighted={highlightedPlayer === parseInt(playerNum)}
                        />
                    ))}
                </div>
            </div>

            {/* Capture overlay when mapping a control */}
            <CaptureOverlay
                controlKey={capturingControl}
                lastCapturedKey={lastCapturedKey}
                captureSource={captureSource}
                onConfirm={onConfirmCapture}
                onCancel={onCancelCapture}
            />
        </>
    );
}

ClickableCabinetDisplay.propTypes = {
    mappings: PropTypes.object,
    capturingControl: PropTypes.string,
    lastCapturedKey: PropTypes.string,
    captureSource: PropTypes.string,
    onControlClick: PropTypes.func.isRequired,
    onConfirmCapture: PropTypes.func,
    onCancelCapture: PropTypes.func,
    activePlayer: PropTypes.number,
    playerCount: PropTypes.oneOf([2, 3, 4]),
    highlightControl: PropTypes.string,
};

// Also export the display name helper
export { getControlDisplayName };

export default ClickableCabinetDisplay;
