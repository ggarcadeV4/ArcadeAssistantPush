import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

/**
 * Context for managing controller mappings state
 * 
 * Provides centralized state for:
 * - Current mappings (controlKey -> keycode)
 * - Encoder mode (keyboard, xinput, dinput)
 * - Mapping operations (set, clear, save)
 */
const ControllerMappingContext = createContext(null);

export function ControllerMappingProvider({ children }) {
    // Mappings: { "p1.up": { keycode: "ArrowUp", ... }, ... }
    const [mappings, setMappings] = useState({});

    // Encoder mode: keyboard, xinput, dinput
    const [encoderMode, setEncoderMode] = useState('keyboard');

    // Loading/error states
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastSaveTime, setLastSaveTime] = useState(null);

    // Load mappings from backend on mount
    useEffect(() => {
        const loadMappings = async () => {
            try {
                setIsLoading(true);
                const res = await fetch('/api/local/controller/mapping');
                if (res.ok) {
                    const data = await res.json();
                    setMappings(data?.mapping?.mappings || {});
                    // Load encoder mode if saved
                    if (data?.mapping?.encoder_mode) {
                        setEncoderMode(data.mapping.encoder_mode);
                    }
                }
            } catch (err) {
                console.error('[MappingContext] Failed to load mappings:', err);
                setError(err.message);
            } finally {
                setIsLoading(false);
            }
        };

        loadMappings();
    }, []);

    /**
     * Set mapping for a single control
     * @param {string} controlKey - e.g., "p1.up"
     * @param {string} keycode - e.g., "ArrowUp", "GAMEPAD_BTN_0"
     * @param {string} source - "keyboard" or "gamepad"
     */
    const setControlMapping = useCallback(async (controlKey, keycode, source = 'keyboard') => {
        // Optimistic update
        setMappings(prev => ({
            ...prev,
            [controlKey]: {
                keycode,
                key_name: keycode.replace('KEY_', '').replace('GAMEPAD_', '').toLowerCase(),
                source,
                mapped_at: new Date().toISOString(),
            }
        }));

        // Save to backend
        try {
            const res = await fetch('/api/local/controller/mapping/set', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-scope': 'config',
                    'x-panel': 'controller',
                    'x-device-id': window.AA_DEVICE_ID || 'CAB-0001',
                },
                body: JSON.stringify({ controlKey, keycode, source }),
            });

            if (!res.ok) {
                throw new Error('Failed to save mapping');
            }

            setLastSaveTime(new Date());
            console.log('[MappingContext] Saved mapping:', controlKey, '->', keycode);
        } catch (err) {
            console.error('[MappingContext] Save failed:', err);
            setError(err.message);
            // Rollback on failure
            setMappings(prev => {
                const next = { ...prev };
                delete next[controlKey];
                return next;
            });
        }
    }, []);

    /**
     * Clear mapping for a single control
     */
    const clearControlMapping = useCallback(async (controlKey) => {
        const previous = mappings[controlKey];

        // Optimistic update
        setMappings(prev => {
            const next = { ...prev };
            delete next[controlKey];
            return next;
        });

        // Save to backend
        try {
            const res = await fetch('/api/local/controller/mapping/clear', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-scope': 'config',
                    'x-panel': 'controller',
                },
                body: JSON.stringify({ controlKey }),
            });

            if (!res.ok) {
                throw new Error('Failed to clear mapping');
            }
        } catch (err) {
            console.error('[MappingContext] Clear failed:', err);
            // Rollback
            if (previous) {
                setMappings(prev => ({ ...prev, [controlKey]: previous }));
            }
        }
    }, [mappings]);

    /**
     * Save encoder mode to backend
     */
    const saveEncoderMode = useCallback(async (mode) => {
        setEncoderMode(mode);

        try {
            await fetch('/api/local/controller/encoder-mode', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-scope': 'config',
                    'x-panel': 'controller',
                },
                body: JSON.stringify({ mode }),
            });
        } catch (err) {
            console.error('[MappingContext] Failed to save encoder mode:', err);
        }
    }, []);

    /**
     * Check if a control has a mapping
     */
    const isMapped = useCallback((controlKey) => {
        return !!mappings[controlKey]?.keycode;
    }, [mappings]);

    /**
     * Get the keycode for a control
     */
    const getKeycode = useCallback((controlKey) => {
        return mappings[controlKey]?.keycode || null;
    }, [mappings]);

    /**
     * Get mapping stats
     */
    const getMappingStats = useCallback(() => {
        const allControls = [];
        for (let p = 1; p <= 4; p++) {
            // Joystick
            allControls.push(`p${p}.up`, `p${p}.down`, `p${p}.left`, `p${p}.right`);
            // Buttons (8 for P1/P2, 4 for P3/P4)
            const buttonCount = p <= 2 ? 8 : 4;
            for (let b = 1; b <= buttonCount; b++) {
                allControls.push(`p${p}.button${b}`);
            }
            // System buttons
            allControls.push(`p${p}.start`, `p${p}.coin`);
        }

        const mapped = allControls.filter(c => isMapped(c)).length;
        return {
            total: allControls.length,
            mapped,
            unmapped: allControls.length - mapped,
            percentage: Math.round((mapped / allControls.length) * 100),
        };
    }, [isMapped]);

    /**
     * Check for duplicate keycodes
     */
    const findDuplicateKeycode = useCallback((keycode, excludeControl = null) => {
        for (const [controlKey, mapping] of Object.entries(mappings)) {
            if (controlKey !== excludeControl && mapping.keycode === keycode) {
                return controlKey;
            }
        }
        return null;
    }, [mappings]);

    const value = {
        // State
        mappings,
        encoderMode,
        isLoading,
        error,
        lastSaveTime,

        // Actions
        setControlMapping,
        clearControlMapping,
        setEncoderMode: saveEncoderMode,

        // Helpers
        isMapped,
        getKeycode,
        getMappingStats,
        findDuplicateKeycode,
    };

    return (
        <ControllerMappingContext.Provider value={value}>
            {children}
        </ControllerMappingContext.Provider>
    );
}

/**
 * Hook to access controller mapping context
 */
export function useControllerMapping() {
    const context = useContext(ControllerMappingContext);
    if (!context) {
        throw new Error('useControllerMapping must be used within ControllerMappingProvider');
    }
    return context;
}

export default ControllerMappingContext;
