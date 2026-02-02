import { useState, useEffect, useRef, useCallback } from 'react';
import { speak, stopSpeaking } from '../services/ttsClient';

const CONTROLLER_BASE = '/api/local/controller';
const CHUCK_VOICE_ID = 'f5HLTX707KIM4SzJYzSz';
const POLL_INTERVAL_MS = 200; // Poll backend every 200ms for captured keys

/**
 * Learn Wizard that POLLS the backend for captured inputs.
 * 
 * The backend uses pygame to detect XInput/gamepad inputs.
 * Frontend polls /learn-wizard/status to get captured keys.
 */
export function useLearnWizard({ voiceEnabled = true } = {}) {
    const [isActive, setIsActive] = useState(false);
    const [currentControl, setCurrentControl] = useState(null);
    const [displayName, setDisplayName] = useState('');
    const [currentIndex, setCurrentIndex] = useState(0);
    const [totalControls, setTotalControls] = useState(0);
    const [captures, setCaptures] = useState({});
    const [isComplete, setIsComplete] = useState(false);
    const [chuckPrompt, setChuckPrompt] = useState('');
    const [error, setError] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [lastDetectedKey, setLastDetectedKey] = useState(null);
    const [detectedMode, setDetectedMode] = useState(null);

    const mountedRef = useRef(false);
    const lastSpokenRef = useRef('');
    const speakTimeoutRef = useRef(null);
    const pollIntervalRef = useRef(null);
    const lastIndexRef = useRef(-1);

    useEffect(() => {
        mountedRef.current = true;
        return () => {
            mountedRef.current = false;
            if (speakTimeoutRef.current) clearTimeout(speakTimeoutRef.current);
            if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
        };
    }, []);

    // Debounced speech
    const speakOnce = useCallback((prompt) => {
        if (!voiceEnabled || !prompt) return;
        if (prompt.toLowerCase() === lastSpokenRef.current.toLowerCase()) return;

        if (speakTimeoutRef.current) clearTimeout(speakTimeoutRef.current);

        speakTimeoutRef.current = setTimeout(() => {
            lastSpokenRef.current = prompt;
            try { stopSpeaking(); } catch (e) { }
            speak(prompt, { voice_id: CHUCK_VOICE_ID }).catch(() => { });
        }, 150);
    }, [voiceEnabled]);

    /**
     * Poll the backend for wizard status.
     * The backend's pygame listener captures XInput gamepad inputs.
     */
    const pollStatus = useCallback(async () => {
        if (!isActive) return;

        try {
            const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/status`, {
                headers: {
                    'x-scope': 'state',
                    'x-panel': 'controller',
                    'x-device-id': window.AA_DEVICE_ID || 'CAB-0001'
                }
            });

            if (!res.ok) return;

            const data = await res.json();
            console.log('[LearnWizard] Poll response:', data);
            if (!mountedRef.current) return;

            // Check for captured key from backend
            if (data.captured_key && data.captured_key !== lastDetectedKey) {
                console.log('[LearnWizard] Backend captured key:', data.captured_key);
                setLastDetectedKey(data.captured_key);
                setDetectedMode('gamepad'); // Backend uses pygame for gamepad

                // Auto-confirm and advance
                await confirmCapture();
            }

            // Check for completion
            if (data.status === 'complete') {
                setIsComplete(true);
                setCaptures(data.captures || {});
                speakOnce("All done! Click Save.");
            }

            // Check for wizard advancement (from backend auto-advance)
            if (data.current_index !== undefined && data.current_index !== lastIndexRef.current) {
                lastIndexRef.current = data.current_index;
                setCurrentIndex(data.current_index);
                setCurrentControl(data.current_control);
                setDisplayName(data.display_name || '');
                setCaptures(data.captures || {});
                setLastDetectedKey(null);

                // Only speak if we advanced to a new control (not initial load)
                if (data.current_index > 0 && data.status !== 'complete') {
                    const prompt = `Next: ${data.display_name}`;
                    setChuckPrompt(prompt);
                    speakOnce(prompt);
                }
            }

        } catch (err) {
            console.debug('[LearnWizard] Poll error:', err);
        }
    }, [isActive, lastDetectedKey, speakOnce]);

    /**
     * Confirm the captured key and advance to next control
     */
    const confirmCapture = useCallback(async () => {
        try {
            const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/confirm`, {
                method: 'POST',
                headers: {
                    'x-scope': 'state',
                    'x-panel': 'controller',
                    'x-device-id': window.AA_DEVICE_ID || 'CAB-0001'
                }
            });

            if (!res.ok) return;

            const data = await res.json();
            if (!mountedRef.current) return;

            if (data.status === 'complete') {
                setIsComplete(true);
                setCaptures(data.captures || {});
                speakOnce("All done! Click Save.");
            } else {
                setCurrentControl(data.next_control || null);
                setDisplayName(data.display_name || '');
                setCurrentIndex(data.current_index || 0);
                setCaptures(data.captures || {});
                setLastDetectedKey(null);

                const prompt = data.chuck_prompt || `Got it! Next: ${data.display_name}`;
                setChuckPrompt(prompt);
                speakOnce(prompt);
            }
        } catch (err) {
            console.error('[LearnWizard] Confirm failed:', err);
        }
    }, [speakOnce]);

    // Start polling when wizard is active
    useEffect(() => {
        if (isActive && !isComplete) {
            console.log('[LearnWizard] Starting backend polling');
            pollIntervalRef.current = setInterval(pollStatus, POLL_INTERVAL_MS);
            return () => {
                console.log('[LearnWizard] Stopping backend polling');
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
        lastSpokenRef.current = '';
        lastIndexRef.current = -1;
        setCaptures({});
        setLastDetectedKey(null);
        setDetectedMode(null);

        try {
            const params = new URLSearchParams();
            if (options.player) params.set('player', options.player);
            if (options.players) params.set('players', options.players);
            if (options.buttons) params.set('buttons', options.buttons);
            params.set('auto_advance', 'true'); // Backend handles auto-advance now

            const url = `${CONTROLLER_BASE}/learn-wizard/start?${params.toString()}`;
            const res = await fetch(url, {
                method: 'POST',
                headers: {
                    'x-scope': 'state',
                    'x-panel': 'controller',
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
            setCurrentControl(data.current_control || null);
            setDisplayName(data.display_name || '');
            setCurrentIndex(data.current_index || 0);
            setTotalControls(data.total_controls || 0);

            const prompt = data.chuck_prompt || `First: ${data.display_name}. Press it now!`;
            setChuckPrompt(prompt);
            speakOnce(prompt);
        } catch (err) {
            console.error('[LearnWizard] Start failed:', err);
            if (mountedRef.current) {
                setError(err.message);
                setIsActive(false);
            }
        } finally {
            if (mountedRef.current) setIsLoading(false);
        }
    }, [speakOnce]);

    const stopWizard = useCallback(async () => {
        try {
            await fetch(`${CONTROLLER_BASE}/learn-wizard/stop`, {
                method: 'POST',
                headers: { 'x-scope': 'state', 'x-panel': 'controller' }
            });
        } catch (err) { }

        setIsActive(false);
        setIsComplete(false);
        setCurrentControl(null);
        setDisplayName('');
        setCaptures({});
        setChuckPrompt('');
        setError(null);
        setLastDetectedKey(null);
        setDetectedMode(null);
    }, []);

    const skipControl = useCallback(async () => {
        try {
            const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/skip`, {
                method: 'POST',
                headers: { 'x-scope': 'state', 'x-panel': 'controller' }
            });

            const data = await res.json();
            if (!mountedRef.current) return;

            if (data.status === 'complete') {
                setIsComplete(true);
                setCaptures(data.captures || {});
                speakOnce("All done! Click Save.");
            } else {
                setCurrentControl(data.next_control || null);
                setDisplayName(data.display_name || '');
                setCurrentIndex(prev => prev + 1);
                setLastDetectedKey(null);
                speakOnce(data.chuck_prompt || `Next: ${data.display_name}`);
            }
            setChuckPrompt(data.chuck_prompt || '');
        } catch (err) {
            setError(err.message);
        }
    }, [speakOnce]);

    const undoCapture = useCallback(async () => {
        try {
            const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/undo`, {
                method: 'POST',
                headers: { 'x-scope': 'state', 'x-panel': 'controller' }
            });

            const data = await res.json();
            if (!mountedRef.current) return;

            setIsComplete(false);
            setCurrentControl(data.current_control || null);
            setDisplayName(data.display_name || '');
            setCurrentIndex(data.current_index || 0);
            setCaptures(data.captures || {});
            setLastDetectedKey(null);

            const prompt = data.chuck_prompt || `Back to ${data.display_name}`;
            setChuckPrompt(prompt);
            speakOnce(prompt);
        } catch (err) {
            setError(err.message);
        }
    }, [speakOnce]);

    const saveWizard = useCallback(async () => {
        setIsLoading(true);
        try {
            const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/save`, {
                method: 'POST',
                headers: { 'x-scope': 'config', 'x-panel': 'controller' }
            });

            const data = await res.json();
            if (!mountedRef.current) return data;

            setIsActive(false);
            setIsComplete(false);
            speakOnce(data.chuck_prompt || 'Saved!');
            return data;
        } catch (err) {
            setError(err.message);
            throw err;
        } finally {
            setIsLoading(false);
        }
    }, [speakOnce]);

    const progressPercent = totalControls > 0 ? Math.round((currentIndex / totalControls) * 100) : 0;

    return {
        isActive,
        isComplete,
        isLoading,
        currentControl,
        displayName,
        currentIndex,
        totalControls,
        progressPercent,
        captures,
        chuckPrompt,
        error,
        lastDetectedKey,
        detectedMode,
        startWizard,
        stopWizard,
        skipControl,
        undoCapture,
        saveWizard,
    };
}

export default useLearnWizard;
