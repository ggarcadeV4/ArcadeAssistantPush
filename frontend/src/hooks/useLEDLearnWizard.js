import { useState, useEffect, useRef, useCallback } from 'react';

const LED_BASE = '/api/local/led';
const POLL_INTERVAL_MS = 200;

const resolveDeviceId = () => {
    if (typeof window === 'undefined') {
        return 'CAB-0001'
    }
    return window.AA_DEVICE_ID ?? window.__DEVICE_ID__ ?? 'CAB-0001'
}

/**
 * LED Learn Wizard Hook - Polls backend for input detection during LED calibration.
 * 
 * Uses controller input detection (read-only) to capture button presses.
 * Flashes LEDs during calibration so user knows which LED to map.
 * Stores mappings in led_channels.json (separate from color profiles).
 */
export function useLEDLearnWizard({ onToast } = {}) {
    const [isActive, setIsActive] = useState(false);
    const [currentControl, setCurrentControl] = useState(null);
    const [displayName, setDisplayName] = useState('');
    const [currentIndex, setCurrentIndex] = useState(0);
    const [currentChannel, setCurrentChannel] = useState(1);
    const [totalControls, setTotalControls] = useState(0);
    const [captures, setCaptures] = useState({});
    const [isComplete, setIsComplete] = useState(false);
    const [capturedInput, setCapturedInput] = useState(null);
    const [chuckPrompt, setChuckPrompt] = useState('');
    const [error, setError] = useState(null);
    const [isLoading, setIsLoading] = useState(false);

    const mountedRef = useRef(false);
    const pollIntervalRef = useRef(null);

    useEffect(() => {
        mountedRef.current = true;
        return () => {
            mountedRef.current = false;
            if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
        };
    }, []);

    /**
     * Poll the backend for wizard status
     */
    const pollStatus = useCallback(async () => {
        if (!isActive) return;

        try {
            const res = await fetch(`${LED_BASE}/learn-wizard/status`, {
                headers: {
                    'x-scope': 'state',
                    'x-panel': 'led-blinky',
                    'x-device-id': window.AA_DEVICE_ID || 'CAB-0001'
                }
            });

            if (!res.ok) return;

            const data = await res.json();
            if (!mountedRef.current) return;

            // Update state from backend
            if (data.captured_input && data.captured_input !== capturedInput) {
                setCapturedInput(data.captured_input);
                // Auto-confirm when input detected
                await confirmCapture();
            }

            if (data.status === 'complete') {
                setIsComplete(true);
                setCaptures(data.captures || {});
                setChuckPrompt(data.chuck_prompt || "All done! Click Save.");
            } else if (data.status === 'waiting') {
                setCurrentControl(data.current_control);
                setDisplayName(data.display_name || '');
                setCurrentIndex(data.current_index || 0);
                setCurrentChannel(data.current_channel || 1);
                setCaptures(data.captures || {});
            }

        } catch (err) {
            console.debug('[LEDLearnWizard] Poll error:', err);
        }
    }, [isActive, capturedInput]);

    // Start polling when wizard is active
    useEffect(() => {
        if (isActive && !isComplete) {
            pollIntervalRef.current = setInterval(pollStatus, POLL_INTERVAL_MS);
            return () => {
                if (pollIntervalRef.current) {
                    clearInterval(pollIntervalRef.current);
                    pollIntervalRef.current = null;
                }
            };
        }
    }, [isActive, isComplete, pollStatus]);

    const startWizard = useCallback(async (options = {}) => {
        setIsLoading(true);
        setError(null);
        setCaptures({});
        setCapturedInput(null);

        try {
            const params = new URLSearchParams();
            if (options.players) params.set('players', options.players);
            if (options.skip_trackball) params.set('skip_trackball', 'true');

            const url = `${LED_BASE}/learn-wizard/start?${params.toString()}`;
            const res = await fetch(url, {
                method: 'POST',
                headers: {
                    'x-scope': 'config',
                    'x-panel': 'led-blinky',
                    'x-device-id': window.AA_DEVICE_ID || 'CAB-0001'
                }
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || 'Failed to start');
            }

            const data = await res.json();
            if (!mountedRef.current) return;

            setIsActive(true);
            setIsComplete(false);
            setCurrentControl(data.current_control);
            setDisplayName(data.display_name || '');
            setCurrentIndex(data.current_index || 0);
            setCurrentChannel(data.current_channel || 1);
            setTotalControls(data.total_controls || 0);
            setChuckPrompt(data.chuck_prompt || `Press ${data.display_name} now!`);

        } catch (err) {
            console.error('[LEDLearnWizard] Start failed:', err);
            if (mountedRef.current) {
                setError(err.message);
                setIsActive(false);
            }
        } finally {
            if (mountedRef.current) setIsLoading(false);
        }
    }, []);

    const confirmCapture = useCallback(async () => {
        try {
            const res = await fetch(`${LED_BASE}/learn-wizard/confirm`, {
                method: 'POST',
                headers: {
                    'x-scope': 'config',
                    'x-panel': 'led-blinky',
                    'x-device-id': window.AA_DEVICE_ID || 'CAB-0001'
                }
            });

            if (!res.ok) return;

            const data = await res.json();
            if (!mountedRef.current) return;

            setCapturedInput(null);

            if (data.status === 'complete') {
                setIsComplete(true);
                setCaptures(data.captures || {});
                setChuckPrompt(data.chuck_prompt || "All done! Click Save.");
            } else {
                setCurrentControl(data.next_control);
                setDisplayName(data.display_name || '');
                setCurrentIndex(data.current_index);
                setCurrentChannel(data.current_channel);
                setCaptures(data.captures || {});
                setChuckPrompt(data.chuck_prompt || `Press ${data.display_name}`);
            }
        } catch (err) {
            console.error('[LEDLearnWizard] Confirm failed:', err);
        }
    }, []);

    const skipControl = useCallback(async () => {
        try {
            const res = await fetch(`${LED_BASE}/learn-wizard/skip`, {
                method: 'POST',
                headers: {
                    'x-scope': 'config',
                    'x-panel': 'led-blinky',
                    'x-device-id': resolveDeviceId()
                }
            });

            const data = await res.json();
            if (!mountedRef.current) return;

            setCapturedInput(null);

            if (data.status === 'complete') {
                setIsComplete(true);
            } else {
                setCurrentControl(data.next_control);
                setDisplayName(data.display_name || '');
                setCurrentIndex(data.current_index);
                setChuckPrompt(data.chuck_prompt || '');
            }
        } catch (err) {
            setError(err.message);
        }
    }, []);

    const saveWizard = useCallback(async () => {
        setIsLoading(true);
        try {
            const res = await fetch(`${LED_BASE}/learn-wizard/save`, {
                method: 'POST',
                headers: {
                    'x-scope': 'config',
                    'x-panel': 'led-blinky',
                    'x-device-id': resolveDeviceId()
                }
            });

            const data = await res.json();
            if (!mountedRef.current) return data;

            setIsActive(false);
            setIsComplete(false);
            if (onToast) onToast(data.chuck_prompt || 'Saved!', 'success');
            return data;
        } catch (err) {
            setError(err.message);
            throw err;
        } finally {
            setIsLoading(false);
        }
    }, [onToast]);

    const stopWizard = useCallback(async () => {
        try {
            await fetch(`${LED_BASE}/learn-wizard/stop`, {
                method: 'POST',
                headers: {
                    'x-scope': 'config',
                    'x-panel': 'led-blinky',
                    'x-device-id': resolveDeviceId()
                }
            });
        } catch (err) { console.warn('[LEDLearnWizard]', err) }

        setIsActive(false);
        setIsComplete(false);
        setCurrentControl(null);
        setCaptures({});
        setCapturedInput(null);
        setChuckPrompt('');
        setError(null);
    }, []);

    const progressPercent = totalControls > 0 ? Math.round((currentIndex / totalControls) * 100) : 0;

    return {
        isActive,
        isComplete,
        isLoading,
        currentControl,
        displayName,
        currentIndex,
        currentChannel,
        totalControls,
        progressPercent,
        captures,
        capturedInput,
        chuckPrompt,
        error,
        startWizard,
        stopWizard,
        skipControl,
        saveWizard,
    };
}

export default useLEDLearnWizard;
