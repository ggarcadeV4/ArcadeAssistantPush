import { useState, useEffect, useCallback, useRef } from 'react';
import { buildStandardHeaders } from '../utils/identity';

const CAPTURE_PANEL = 'capture-mode';
const captureJsonHeaders = () => buildStandardHeaders({
    panel: CAPTURE_PANEL,
    scope: 'state',
    extraHeaders: { 'Content-Type': 'application/json' },
});
const captureStateHeaders = () => buildStandardHeaders({ panel: CAPTURE_PANEL, scope: 'state' });

/**
 * useCaptureMode - Hook for capturing keyboard and gamepad inputs
 * 
 * Used for the click-to-map controller mapping system.
 * When a user clicks a control on the GUI, this hook enters capture mode
 * and listens for the next keyboard key or gamepad button press.
 * 
 * Detection methods (in parallel):
 * 1. Browser keyboard events (keydown)
 * 2. Browser Gamepad API polling
 * 3. Backend pygame-based detection (polls /api/local/controller/input-detect)
 */
export function useCaptureMode() {
    // Currently capturing control key (e.g., "p1.up", "p2.button3")
    const [capturingControl, setCapturingControl] = useState(null);

    // Last captured keycode/input
    const [lastCapturedKey, setLastCapturedKey] = useState(null);

    // Source of capture (keyboard, gamepad, backend)
    const [captureSource, setCaptureSource] = useState(null);

    // Error state
    const [captureError, setCaptureError] = useState(null);

    // Ref to track gamepad baseline (to detect new presses)
    const gamepadBaselineRef = useRef({});

    // Ref to track if we already captured (to prevent duplicate captures)
    const hasCapturedRef = useRef(false);

    /**
     * Start capturing for a specific control
     * @param {string} controlKey - e.g., "p1.up", "p2.button3"
     */
    const startCapture = useCallback((controlKey) => {
        console.log('[CaptureMode] Starting capture for:', controlKey);
        setCapturingControl(controlKey);
        setLastCapturedKey(null);
        setCaptureSource(null);
        setCaptureError(null);
        hasCapturedRef.current = false;

        // Snapshot current gamepad state as baseline
        try {
            const gamepads = navigator.getGamepads ? navigator.getGamepads() : [];
            const baseline = {};
            for (const gamepad of gamepads) {
                if (gamepad) {
                    baseline[gamepad.index] = {
                        buttons: gamepad.buttons.map(b => b.pressed),
                        axes: [...gamepad.axes],
                    };
                }
            }
            gamepadBaselineRef.current = baseline;
        } catch (e) {
            console.debug('[CaptureMode] Could not snapshot gamepad baseline:', e);
        }

        // Clear any previous backend capture state and start backend detection
        fetch('/api/local/controller/input-detect/start', {
            method: 'POST',
            headers: captureJsonHeaders()
        }).then(() => {
            console.log('[CaptureMode] Backend input detection started');
        }).catch((e) => {
            console.debug('[CaptureMode] Backend start skipped:', e.message);
        });
    }, []);

    /**
     * Cancel capture mode without saving
     */
    const cancelCapture = useCallback(() => {
        console.log('[CaptureMode] Capture cancelled');
        setCapturingControl(null);
        setLastCapturedKey(null);
        setCaptureSource(null);
        setCaptureError(null);
        hasCapturedRef.current = false;
    }, []);

    /**
     * Confirm the captured key - returns the mapping data
     */
    const confirmCapture = useCallback(() => {
        if (!capturingControl || !lastCapturedKey) {
            return null;
        }

        const result = {
            controlKey: capturingControl,
            keycode: lastCapturedKey,
            source: captureSource,
        };

        console.log('[CaptureMode] Capture confirmed:', result);

        // Reset state
        setCapturingControl(null);
        setLastCapturedKey(null);
        setCaptureSource(null);
        hasCapturedRef.current = false;

        return result;
    }, [capturingControl, lastCapturedKey, captureSource]);

    // Listen for keyboard events when capturing
    useEffect(() => {
        if (!capturingControl) return;

        const handleKeyDown = (e) => {
            if (hasCapturedRef.current) return;

            // Prevent default to avoid triggering other shortcuts
            e.preventDefault();
            e.stopPropagation();

            // Get the keycode - use e.code for physical key position
            const keycode = e.code; // e.g., "KeyW", "ArrowUp", "Digit1", "Space"

            console.log('[CaptureMode] Keyboard captured:', keycode, 'key:', e.key);

            hasCapturedRef.current = true;
            setLastCapturedKey(keycode);
            setCaptureSource('keyboard');
        };

        // Using capture phase to catch events before other handlers
        window.addEventListener('keydown', handleKeyDown, { capture: true });

        return () => {
            window.removeEventListener('keydown', handleKeyDown, { capture: true });
        };
    }, [capturingControl]);

    // Listen for gamepad events when capturing (XInput/DInput) via browser API
    useEffect(() => {
        if (!capturingControl) return;

        let animationFrameId;

        const pollGamepad = () => {
            if (hasCapturedRef.current) return;

            try {
                const gamepads = navigator.getGamepads ? navigator.getGamepads() : [];

                for (const gamepad of gamepads) {
                    if (!gamepad) continue;

                    const baseline = gamepadBaselineRef.current[gamepad.index];
                    if (!baseline) continue;

                    // Check buttons
                    for (let i = 0; i < gamepad.buttons.length; i++) {
                        const wasPressed = baseline.buttons[i];
                        const isPressed = gamepad.buttons[i].pressed;

                        // Detect new button press
                        if (isPressed && !wasPressed) {
                            const keycode = `GAMEPAD_BTN_${i}`;
                            console.log('[CaptureMode] Gamepad button captured:', keycode);

                            hasCapturedRef.current = true;
                            setLastCapturedKey(keycode);
                            setCaptureSource('gamepad');
                            return; // Stop polling after capture
                        }
                    }

                    // Check axes (joystick/dpad)
                    for (let i = 0; i < gamepad.axes.length; i++) {
                        const wasValue = baseline.axes[i];
                        const isValue = gamepad.axes[i];

                        // Detect significant axis change (threshold 0.5)
                        if (Math.abs(isValue) > 0.5 && Math.abs(wasValue) < 0.5) {
                            let direction = isValue > 0 ? '+' : '-';
                            const keycode = `GAMEPAD_AXIS_${i}${direction}`;
                            console.log('[CaptureMode] Gamepad axis captured:', keycode, 'value:', isValue);

                            hasCapturedRef.current = true;
                            setLastCapturedKey(keycode);
                            setCaptureSource('gamepad');
                            return; // Stop polling after capture
                        }
                    }
                }
            } catch (e) {
                console.debug('[CaptureMode] Gamepad poll error:', e);
            }

            // Continue polling
            animationFrameId = requestAnimationFrame(pollGamepad);
        };

        // Start polling
        animationFrameId = requestAnimationFrame(pollGamepad);

        return () => {
            if (animationFrameId) {
                cancelAnimationFrame(animationFrameId);
            }
        };
    }, [capturingControl]);

    // Poll backend for pygame-based input detection (for XInput HAT/D-pad)
    useEffect(() => {
        if (!capturingControl) return;

        let pollInterval;

        const pollBackend = async () => {
            if (hasCapturedRef.current) return;

            try {
                const response = await fetch('/api/local/controller/input-detect', {
                    headers: captureStateHeaders()
                });

                if (response.ok) {
                    const data = await response.json();

                    if (data.captured_key && !hasCapturedRef.current) {
                        console.log('[CaptureMode] Backend captured:', data.captured_key, 'source:', data.source);

                        hasCapturedRef.current = true;
                        setLastCapturedKey(data.captured_key);
                        setCaptureSource(data.source || 'backend');

                        // Clear the backend state after capturing
                        fetch('/api/local/controller/input-detect/clear', {
                            method: 'POST',
                            headers: captureJsonHeaders()
                        }).catch(() => { });
                    }
                }
            } catch (e) {
                // Backend polling is optional, don't log errors
                console.debug('[CaptureMode] Backend poll skipped:', e.message);
            }
        };

        // Poll every 100ms
        pollInterval = setInterval(pollBackend, 100);

        return () => {
            if (pollInterval) {
                clearInterval(pollInterval);
            }
        };
    }, [capturingControl]);

    return {
        // State
        capturingControl,
        lastCapturedKey,
        captureSource,
        captureError,
        isCapturing: !!capturingControl,
        hasCaptured: !!lastCapturedKey,

        // Actions
        startCapture,
        cancelCapture,
        confirmCapture,
    };
}

export default useCaptureMode;
