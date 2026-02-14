/**
 * useBlinkyGameSelection - Frontend debounce for LED game selection
 * 
 * This hook provides network-layer throttling (100ms) before sending
 * game selection events to the backend. The backend then applies its
 * own hardware-layer debounce (250ms) before firing CLI commands.
 * 
 * Why two layers?
 * - Frontend: Protects network stack from scroll spam
 * - Backend: Protects hardware from process spawn spam
 */
import { useState, useRef, useCallback } from 'react'

// API base URL helper
const getApiBase = () => {
    if (typeof window === 'undefined' || !window.location) {
        return 'http://localhost:8787'
    }
    if (window.location.port === '5173') {
        return 'http://localhost:8787'
    }
    return window.location.origin
}

const resolveDeviceId = () => {
    if (typeof window === 'undefined') {
        return 'CAB-0001'
    }
    return window.AA_DEVICE_ID ?? window.__DEVICE_ID__ ?? 'CAB-0001'
}

// Frontend debounce: 100ms
const FRONTEND_DEBOUNCE_MS = 100

/**
 * Hook for debounced game selection LED events
 */
export function useBlinkyGameSelection({ onToast = () => { } } = {}) {
    const [isLoading, setIsLoading] = useState(false)
    const [lastSelectedGame, setLastSelectedGame] = useState(null)
    const debounceTimerRef = useRef(null)

    /**
     * Called when user hovers/scrolls to a game.
     * Debounced at 100ms before network call.
     */
    const gameSelected = useCallback((rom, emulator = 'MAME') => {
        console.log('[Blinky] gameSelected called:', rom, emulator)

        // Clear any pending debounce
        if (debounceTimerRef.current) {
            clearTimeout(debounceTimerRef.current)
        }

        // Start new debounce timer
        debounceTimerRef.current = setTimeout(async () => {
            console.log('[Blinky] Debounce fired, calling API for:', rom)
            setIsLoading(true)
            try {
                const url = `${getApiBase()}/api/local/led/blinky/game-selected`
                console.log('[Blinky] Fetching:', url)
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'x-scope': 'config',
                        'x-panel': 'led-blinky',
                        'x-device-id': resolveDeviceId()
                    },
                    body: JSON.stringify({ rom, emulator })
                })

                console.log('[Blinky] Response status:', response.status)
                if (response.ok) {
                    setLastSelectedGame(rom)
                }
            } catch (err) {
                console.warn('[Blinky] Game selection failed:', err)
            } finally {
                setIsLoading(false)
            }
        }, FRONTEND_DEBOUNCE_MS)
    }, [])

    /**
     * Called when a game is actually launched.
     * No debounce - immediately fires.
     */
    const gameLaunch = useCallback(async (rom, emulator = 'MAME') => {
        // Cancel any pending selection debounce
        if (debounceTimerRef.current) {
            clearTimeout(debounceTimerRef.current)
            debounceTimerRef.current = null
        }

        setIsLoading(true)
        try {
            const response = await fetch(`${getApiBase()}/api/local/led/blinky/game-launch`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-scope': 'config',
                    'x-panel': 'led-blinky',
                    'x-device-id': resolveDeviceId()
                },
                body: JSON.stringify({ rom, emulator })
            })

            if (!response.ok) {
                throw new Error(`Game launch failed: ${response.status}`)
            }

            const data = await response.json()
            onToast(`LED lighting activated for ${rom}`, 'success')
            return data
        } catch (err) {
            onToast(`LED launch failed: ${err.message}`, 'error')
            throw err
        } finally {
            setIsLoading(false)
        }
    }, [onToast])

    /**
     * Called when returning from a game to the frontend.
     */
    const gameStop = useCallback(async () => {
        setIsLoading(true)
        try {
            const response = await fetch(`${getApiBase()}/api/local/led/blinky/game-stop`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-scope': 'config',
                    'x-panel': 'led-blinky',
                    'x-device-id': resolveDeviceId()
                }
            })

            if (response.ok) {
                setLastSelectedGame(null)
            }
        } catch (err) {
            console.warn('[Blinky] Game stop failed:', err)
        } finally {
            setIsLoading(false)
        }
    }, [])

    /**
     * Cleanup pending timers (call on unmount)
     */
    const cleanup = useCallback(() => {
        if (debounceTimerRef.current) {
            clearTimeout(debounceTimerRef.current)
            debounceTimerRef.current = null
        }
    }, [])

    return {
        gameSelected,
        gameLaunch,
        gameStop,
        cleanup,
        isLoading,
        lastSelectedGame,
        FRONTEND_DEBOUNCE_MS
    }
}

export default useBlinkyGameSelection
