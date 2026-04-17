/**
 * useBlinkyGameSelection - Frontend debounce for LED game selection
 *
 * Supports both legacy calls:
 *   gameSelected('sf2', 'MAME')
 * and rich game payloads:
 *   gameSelected({ id, title, platform, rom_path, application_path })
 */
import { useState, useRef, useCallback } from 'react'
import { getGatewayUrl } from '../services/gateway'
import { buildStandardHeaders } from '../utils/identity'

const getApiBase = () => {
    if (typeof window === 'undefined' || !window.location) {
        return getGatewayUrl()
    }
    if (window.location.port === '5173') {
        return getGatewayUrl()
    }
    return window.location.origin
}

const FRONTEND_DEBOUNCE_MS = 100

const cleanText = (value) => {
    if (value === null || value === undefined) return ''
    return String(value).trim()
}

const romFromPath = (value) => {
    const text = cleanText(value)
    if (!text) return ''
    const unquoted = text.replace(/^['\"]+|['\"]+$/g, '')
    const normalized = unquoted.replace(/\\/g, '/')
    const fileName = normalized.split('/').pop() || normalized
    const withoutExt = fileName.replace(/\.[^/.]+$/, '')
    return cleanText(withoutExt)
}

const toGamePayload = (gameOrRom, emulator = 'MAME') => {
    if (typeof gameOrRom === 'string' || typeof gameOrRom === 'number') {
        const rom = cleanText(gameOrRom)
        return {
            rom,
            title: rom,
            emulator: cleanText(emulator) || 'MAME'
        }
    }

    const game = (gameOrRom && typeof gameOrRom === 'object') ? gameOrRom : {}
    const emu = cleanText(game.emulator || game.platform || emulator) || 'MAME'
    const rom = romFromPath(
        game.rom ||
        game.rom_path ||
        game.romPath ||
        game.application_path ||
        game.applicationPath
    )

    return {
        rom,
        gameId: cleanText(game.gameId || game.id),
        title: cleanText(game.title || rom),
        emulator: emu
    }
}

export function useBlinkyGameSelection({ onToast = () => { } } = {}) {
    const [isLoading, setIsLoading] = useState(false)
    const [lastSelectedGame, setLastSelectedGame] = useState(null)
    const debounceTimerRef = useRef(null)
    const blinkyBaseUrl = `${getApiBase()}/api/local/blinky`

    const postBlinkyEvent = useCallback(async (eventName, payload) => {
        const response = await fetch(`${blinkyBaseUrl}/${eventName}`, {
            method: 'POST',
            headers: buildStandardHeaders({
                panel: 'led-blinky',
                scope: 'config',
                extraHeaders: { 'Content-Type': 'application/json' }
            }),
            body: JSON.stringify(payload)
        })

        if (!response.ok) {
            throw new Error(`${eventName} failed: ${response.status}`)
        }

        return await response.json().catch(() => ({}))
    }, [blinkyBaseUrl])

    const gameSelected = useCallback((gameOrRom, emulator = 'MAME') => {
        const payload = toGamePayload(gameOrRom, emulator)
        if (!payload.rom && !payload.gameId && !payload.title) {
            return
        }

        if (debounceTimerRef.current) {
            clearTimeout(debounceTimerRef.current)
        }

        debounceTimerRef.current = setTimeout(async () => {
            setIsLoading(true)
            try {
                await postBlinkyEvent('game-selected', payload)
                setLastSelectedGame(payload.title || payload.rom || payload.gameId)
            } catch (err) {
                console.warn('[Blinky] Game selection failed:', err)
            } finally {
                setIsLoading(false)
            }
        }, FRONTEND_DEBOUNCE_MS)
    }, [postBlinkyEvent])

    const gameLaunch = useCallback(async (gameOrRom, emulator = 'MAME') => {
        if (debounceTimerRef.current) {
            clearTimeout(debounceTimerRef.current)
            debounceTimerRef.current = null
        }

        const payload = toGamePayload(gameOrRom, emulator)
        const label = payload.title || payload.rom || payload.gameId || 'game'

        setIsLoading(true)
        try {
            // Best-effort preview right before launch so LoRa voice/text launches
            // have the same LED preview path as hover-driven launches.
            try {
                await postBlinkyEvent('game-selected', payload)
                setLastSelectedGame(label)
            } catch (previewErr) {
                console.warn('[Blinky] Pre-launch preview failed:', previewErr)
            }

            const data = await postBlinkyEvent('game-launch', payload)
            onToast(`LED lighting activated for ${label}`, 'success')
            return data
        } catch (err) {
            onToast(`LED launch failed: ${err.message}`, 'error')
            throw err
        } finally {
            setIsLoading(false)
        }
    }, [onToast, postBlinkyEvent])

    const gameStop = useCallback(async () => {
        setIsLoading(true)
        try {
            const response = await fetch(`${blinkyBaseUrl}/game-stop`, {
                method: 'POST',
                headers: buildStandardHeaders({
                    panel: 'led-blinky',
                    scope: 'config',
                    extraHeaders: { 'Content-Type': 'application/json' }
                })
            })

            if (response.ok) {
                setLastSelectedGame(null)
            }
        } catch (err) {
            console.warn('[Blinky] Game stop failed:', err)
        } finally {
            setIsLoading(false)
        }
    }, [blinkyBaseUrl])

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
