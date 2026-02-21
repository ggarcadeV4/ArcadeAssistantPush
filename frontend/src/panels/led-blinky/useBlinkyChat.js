import { useState, useCallback, useRef } from 'react'
import { chat as aiChat } from '../../services/aiClient'

/**
 * Gemini Tool Schemas for LED Blinky
 * These are passed as `tools` to the Gemini adapter for native function calling.
 * Gemini returns structured `tool_use` blocks instead of JSON-in-text.
 */
const BLINKY_TOOLS = [
  {
    name: 'set_button_color',
    description: 'Changes the color of specific arcade buttons or groups of buttons.',
    parameters: {
      type: 'object',
      properties: {
        buttons: {
          type: 'array',
          items: { type: 'string' },
          description: "List of logical buttons (e.g., 'p1.button1', 'p2.start') or player groups (e.g., 'player1', 'all')."
        },
        color: {
          type: 'string',
          description: "The hex color code to apply (e.g., '#FF0000' for red)."
        }
      },
      required: ['buttons', 'color']
    }
  },
  {
    name: 'apply_theme',
    description: 'Applies a predefined lighting theme to the entire control panel.',
    parameters: {
      type: 'object',
      properties: {
        theme_name: {
          type: 'string',
          description: "The theme to apply (e.g., 'cyberpunk', 'sunset', 'christmas', 'fire_and_ice')."
        }
      },
      required: ['theme_name']
    }
  },
  {
    name: 'start_calibration',
    description: 'Starts the LED hardware calibration wizard.',
    parameters: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'calibration_escape_hatch',
    description: "Used during calibration when a port blinks but the user cannot click a matching button on the UI. Allows skipping or naming custom hardware.",
    parameters: {
      type: 'object',
      properties: {
        action: {
          type: 'string',
          enum: ['skip', 'assign_custom'],
          description: "Whether to 'skip' the port or 'assign_custom' name to it."
        },
        custom_name: {
          type: 'string',
          description: "If action is 'assign_custom', the name the user gave the hardware (e.g., 'trackball', 'coin door')."
        }
      },
      required: ['action']
    }
  }
]

const SYSTEM_PROMPT = `You are Elodie Blink, the LED lighting assistant for Arcade Assistant cabinets.

Your PRIMARY job is helping users with:
- LED button color customization (changing colors via voice or text commands)
- LED wiring and channel mapping
- LED calibration workflows (starting sessions, assigning channels, flashing LEDs)
- LED diagnostics and troubleshooting
- Managing LED configuration files and game-specific profiles
- Applying predefined lighting themes

HARDWARE CONTROL:
- You CAN control physical LED hardware (LED-Wiz, Pac-LED64, GroovyGameGear, Ultimarc)
- You CAN send RGB color values to physical LED ports
- You CAN flash LEDs for testing and identification
- Works in real mode (actual hardware) or mock mode (testing)

IMPORTANT: You have native function calling tools available. When a user asks you to change colors, apply themes, or start calibration, call the appropriate tool directly. Do NOT embed JSON in your text responses.

SUPPORTED COLOR NAMES:
red, green, blue, yellow, purple, violet, magenta, pink, orange, cyan, white, black, lime, teal, aqua, gold, silver, crimson, coral, turquoise

AVAILABLE THEMES:
sunset, ocean, cyberpunk, christmas, fire_and_ice, retro, neon, forest, vaporwave, electric

CALIBRATION ESCAPE HATCH:
During calibration, if a hardware port blinks but there is no matching button on the UI visualizer (e.g., a coin door light, trackball LED, or spinner ring), the user can say "skip that one" or "that's the trackball." Use the calibration_escape_hatch tool to record it appropriately.

PLAYER BUTTON NAMING:
- Player 1 buttons: p1.button1, p1.button2, ... p1.button8, p1.start
- Player 2 buttons: p2.button1, p2.button2, ... p2.button8, p2.start
- Groups: "player1" (all P1), "player2" (all P2), "all" (everything)

Keep responses concise (2-3 sentences) and actionable. Always respond conversationally alongside any tool calls so TTS can speak your reply.`

export function useBlinkyChat() {
  const historyRef = useRef([])
  const [state, setState] = useState({
    loading: false,
    error: null,
    last: null,
    history: []
  })

  const send = useCallback(async (userText, scope = 'state') => {
    const trimmed = (userText || '').trim()
    if (!trimmed) {
      return null
    }

    console.log('[useBlinkyChat] send() called with:', trimmed)

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

    console.log('[useBlinkyChat] Calling aiChat with Gemini + native tools...')
    try {
      const body = await aiChat({
        provider: 'gemini',
        scope,
        messages: conversation,
        temperature: 0.3,
        max_tokens: 300,
        tools: BLINKY_TOOLS,
        metadata: { panel: 'led-blinky', character: 'blinky' }
      })

      // --- Native Tool Call Parsing ---
      // The Gemini adapter returns a `content` array with typed blocks:
      //   [{ type: 'text', text: '...' }, { type: 'tool_use', name: '...', input: {...} }]
      // When there are no tool calls, the response falls back to body.message.content (string)
      const contentArray = body.content || []
      const toolCalls = contentArray.filter(c => c.type === 'tool_use')
      const textBlock = contentArray.find(c => c.type === 'text')

      // Convert native tool calls → command format for commandExecutor
      const commands = toolCalls.map(tc => ({
        action: tc.name,
        ...tc.input
      }))

      // Text reply for display and TTS
      // Priority: text block from content array > message.content string > fallback
      const textReply = textBlock?.text
        || (typeof body?.message?.content === 'string' ? body.message.content : '')
        || 'Done!'

      if (commands.length > 0) {
        console.log('[useBlinkyChat] Native tool calls:', commands)
      }
      console.log('[useBlinkyChat] Text reply:', textReply.substring(0, 80) + '...')

      const assistantMessage = { role: 'assistant', content: textReply }
      historyRef.current = [...historyRef.current, assistantMessage]
      console.log('[useBlinkyChat] History now has', historyRef.current.length, 'messages')
      setState({
        loading: false,
        error: null,
        last: body,
        history: historyRef.current
      })

      // Return both text reply (for TTS) and commands (for executor)
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
