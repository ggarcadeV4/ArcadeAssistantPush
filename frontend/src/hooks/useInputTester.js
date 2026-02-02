import { useState, useEffect, useRef } from 'react';

/**
 * Live input tester that shows keyboard and gamepad inputs in real-time.
 * Similar to gamepad-tester.com but built into Arcade Assistant.
 */
export function useInputTester() {
    const [isActive, setIsActive] = useState(false);
    const [lastKeyboard, setLastKeyboard] = useState(null);
    const [keyboardHistory, setKeyboardHistory] = useState([]);
    const [gamepads, setGamepads] = useState([]);
    const [lastGamepadInput, setLastGamepadInput] = useState(null);

    const gamepadPollRef = useRef(null);
    const lastGamepadState = useRef({});

    // Start/stop the tester
    const start = () => {
        setIsActive(true);
        setKeyboardHistory([]);
        setLastKeyboard(null);
        setLastGamepadInput(null);
        lastGamepadState.current = {};
    };

    const stop = () => {
        setIsActive(false);
        if (gamepadPollRef.current) {
            cancelAnimationFrame(gamepadPollRef.current);
            gamepadPollRef.current = null;
        }
    };

    // Keyboard detection
    useEffect(() => {
        if (!isActive) return;

        const handleKeyDown = (e) => {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

            e.preventDefault();

            let key = e.key;
            if (key === ' ') key = 'Space';
            if (key === 'ArrowUp') key = 'Up';
            if (key === 'ArrowDown') key = 'Down';
            if (key === 'ArrowLeft') key = 'Left';
            if (key === 'ArrowRight') key = 'Right';

            const entry = {
                key,
                code: e.code,
                time: Date.now(),
            };

            setLastKeyboard(entry);
            setKeyboardHistory(prev => [entry, ...prev].slice(0, 10));
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [isActive]);

    // Gamepad detection
    useEffect(() => {
        if (!isActive) return;

        const pollGamepads = () => {
            const gps = navigator.getGamepads ? navigator.getGamepads() : [];
            const gamepadData = [];

            for (let i = 0; i < gps.length; i++) {
                const gp = gps[i];
                if (!gp) continue;

                const buttons = [];
                for (let b = 0; b < gp.buttons.length; b++) {
                    const isPressed = gp.buttons[b].pressed;
                    const value = gp.buttons[b].value;
                    buttons.push({ index: b, pressed: isPressed, value });

                    // Detect new presses
                    const buttonKey = `gp${i}_btn${b}`;
                    if (isPressed && !lastGamepadState.current[buttonKey]) {
                        setLastGamepadInput({
                            type: 'button',
                            gamepad: i,
                            button: b,
                            time: Date.now(),
                        });
                    }
                    lastGamepadState.current[buttonKey] = isPressed;
                }

                const axes = [];
                for (let a = 0; a < gp.axes.length; a++) {
                    const value = gp.axes[a];
                    axes.push({ index: a, value: Math.round(value * 100) / 100 });

                    // Detect axis movements
                    const axisKey = `gp${i}_axis${a}`;
                    const lastValue = lastGamepadState.current[axisKey] || 0;
                    if (Math.abs(value) > 0.5 && Math.abs(lastValue) <= 0.5) {
                        setLastGamepadInput({
                            type: 'axis',
                            gamepad: i,
                            axis: a,
                            direction: value > 0 ? 'positive' : 'negative',
                            time: Date.now(),
                        });
                    }
                    lastGamepadState.current[axisKey] = value;
                }

                gamepadData.push({
                    index: i,
                    id: gp.id,
                    buttons,
                    axes,
                    connected: gp.connected,
                });
            }

            setGamepads(gamepadData);
            gamepadPollRef.current = requestAnimationFrame(pollGamepads);
        };

        gamepadPollRef.current = requestAnimationFrame(pollGamepads);
        return () => {
            if (gamepadPollRef.current) cancelAnimationFrame(gamepadPollRef.current);
        };
    }, [isActive]);

    return {
        isActive,
        start,
        stop,
        lastKeyboard,
        keyboardHistory,
        gamepads,
        lastGamepadInput,
    };
}

export default useInputTester;
