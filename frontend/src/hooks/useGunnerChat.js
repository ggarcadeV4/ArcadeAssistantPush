import { useState, useCallback, useRef } from 'react'
import { chat as aiChat } from '../services/aiClient'

/**
 * Gunner Tool Schemas for Gemini native function calling
 */
const GUNNER_TOOLS = [
    {
        name: 'scan_devices',
        description: 'Scans for connected light gun hardware devices.',
        parameters: {
            type: 'object',
            properties: {}
        }
    },
    {
        name: 'start_calibration',
        description: 'Starts the 9-point calibration wizard for a specific gun.',
        parameters: {
            type: 'object',
            properties: {
                device_id: {
                    type: 'number',
                    description: 'The ID of the gun to calibrate (e.g., 0 for Player 1, 1 for Player 2).'
                },
                mode: {
                    type: 'string',
                    enum: ['standard', 'precision', 'arcade'],
                    description: 'The calibration mode to use.'
                }
            },
            required: ['device_id']
        }
    },
    {
        name: 'load_profile',
        description: 'Loads a saved calibration profile for a specific game.',
        parameters: {
            type: 'object',
            properties: {
                game: {
                    type: 'string',
                    description: "The game to load a profile for (e.g., 'Time Crisis', 'House of the Dead')."
                }
            },
            required: ['game']
        }
    },
    {
        name: 'select_retro_mode',
        description: 'Selects a retro game calibration mode with game-specific settings.',
        parameters: {
            type: 'object',
            properties: {
                mode: {
                    type: 'string',
                    enum: ['time_crisis', 'house_of_the_dead', 'operation_wolf', 'point_blank',
                        'virtua_cop', 'duck_hunt', 'lethal_enforcers', 'area_51'],
                    description: 'The retro game mode to activate.'
                }
            },
            required: ['mode']
        }
    }
]

const SYSTEM_PROMPT = `You are Gunner, the Light Gun Calibration Expert for Arcade Assistant cabinets.

Your PRIMARY job is helping users with:
- Light gun hardware detection and diagnostics
- 9-point calibration workflows (standard, precision, arcade modes)
- Saving and loading calibration profiles per game
- Retro game mode selection and configuration (Time Crisis, House of the Dead, etc.)
- Troubleshooting signal issues, sensor alignment, and connection problems

HARDWARE SUPPORT:
- Sinden Lightgun (USB, IR sensor-based)
- Gun4IR (custom IR builds)
- AimTrak (Ultimarc, USB HID)
- Wiimote + Mayflash DolphinBar

RETRO MODES:
Each retro game has unique requirements:
- Time Crisis: pedal/cover mechanics, off-screen reload detection
- House of the Dead: rapid point acquisition, recoil weighting
- Duck Hunt: single-target precision, timing windows
- Area 51: automatic weapon calibration, rapid fire support
- And more...

IMPORTANT: You have native function calling tools available. When a user asks to scan for devices, start calibration, load profiles, or select game modes, call the appropriate tool directly.

PERSONALITY: You're a no-nonsense tactical hardware expert. Think drill sergeant meets tech support. Keep responses short (2-3 sentences), direct, and actionable. Use military-style brevity when possible.`

/**
 * useGunnerChat — AI chat hook for the Gunner panel
 * Modeled on useBlinkyChat.js pattern
 */
export function useGunnerChat() {
    const historyRef = useRef([])
    const [state, setState] = useState({
        loading: false,
        error: null,
        last: null,
        history: []
    })

    const send = useCallback(async (userText, scope = 'state') => {
        const trimmed = (userText || '').trim()
        if (!trimmed) return null

        const userMessage = { role: 'user', content: trimmed }
        historyRef.current = [...historyRef.current, userMessage]
        setState(s => ({
            ...s,
            loading: true,
            error: null,
            history: historyRef.current
        }))

        const conversation = [
            { role: 'system', content: SYSTEM_PROMPT },
            ...historyRef.current
        ]

        try {
            const body = await aiChat({
                provider: 'gemini',
                scope,
                messages: conversation,
                temperature: 0.3,
                max_tokens: 300,
                tools: GUNNER_TOOLS,
                metadata: { panel: 'gunner', character: 'gunner' }
            })

            const contentArray = body.content || []
            const toolCalls = contentArray.filter(c => c.type === 'tool_use')
            const textBlock = contentArray.find(c => c.type === 'text')

            const commands = toolCalls.map(tc => ({
                action: tc.name,
                ...tc.input
            }))

            const textReply = textBlock?.text
                || (typeof body?.message?.content === 'string' ? body.message.content : '')
                || 'Copy that.'

            const assistantMessage = { role: 'assistant', content: textReply }
            historyRef.current = [...historyRef.current, assistantMessage]
            setState({
                loading: false,
                error: null,
                last: body,
                history: historyRef.current
            })

            return { ...body, commands, textReply }
        } catch (err) {
            setState({
                loading: false,
                error: err,
                last: null,
                history: historyRef.current
            })
            throw err
        }
    }, [])

    return { ...state, send }
}
