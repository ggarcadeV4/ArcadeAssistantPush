/**
 * LED Command Executor
 * Executes LED calibration commands parsed from AI responses
 */

import {
  startLEDCalibration,
  assignLEDCalibration,
  flashLEDCalibration,
  stopLEDCalibration,
  applyLEDProfile
} from '../../services/ledBlinkyClient'

/**
 * Color name to hex mapping for natural language color support
 */
const COLOR_NAME_MAP = {
  red: '#FF0000',
  green: '#00FF00',
  blue: '#0000FF',
  yellow: '#FFFF00',
  purple: '#800080',
  violet: '#8B00FF',
  magenta: '#FF00FF',
  pink: '#FFC0CB',
  orange: '#FFA500',
  cyan: '#00FFFF',
  white: '#FFFFFF',
  black: '#000000',
  lime: '#00FF00',
  teal: '#008080',
  aqua: '#00FFFF',
  gold: '#FFD700',
  silver: '#C0C0C0',
  crimson: '#DC143C',
  coral: '#FF7F50',
  turquoise: '#40E0D0'
}

// ─── Theme Vocabulary (creative color interpretations) ────────────
const LED_THEMES = {
  sunset: ['#FF4500', '#FF6347', '#FF8C00', '#FFD700', '#FF69B4', '#DA70D6'],
  ocean: ['#006994', '#0077BE', '#00CED1', '#20B2AA', '#48D1CC', '#7FFFD4'],
  fire: ['#FF0000', '#FF4500', '#FF6600', '#FF8800', '#FFAA00', '#FFD700'],
  ice: ['#E0FFFF', '#B0E0E6', '#87CEEB', '#ADD8E6', '#00BFFF', '#1E90FF'],
  christmas: ['#B22222', '#228B22', '#FF0000', '#00FF00', '#FFD700', '#FFFFFF'],
  halloween: ['#FF6600', '#800080', '#FF4500', '#9400D3', '#FF8C00', '#4B0082'],
  retro: ['#FF0090', '#00FF00', '#0000FF', '#FFFF00', '#FF00FF', '#00FFFF'],
  vaporwave: ['#FF71CE', '#B967FF', '#01CDFE', '#05FFA1', '#FFFB96', '#FF6B6B'],
  forest: ['#228B22', '#006400', '#32CD32', '#8FBC8F', '#90EE90', '#2E8B57'],
  neon: ['#FF00FF', '#00FF00', '#00FFFF', '#FFFF00', '#FF0080', '#8000FF'],
}

/**
 * Parse a color value - accepts hex codes or color names
 * @param { string } color - Color name or hex code
 * @returns { string } - Hex color code
 */
function parseColor(color) {
  if (!color) return '#FFFFFF'
  const trimmed = color.trim().toLowerCase()

  // Already a hex code
  if (trimmed.startsWith('#')) {
    return trimmed.toUpperCase()
  }

  // Look up color name
  return COLOR_NAME_MAP[trimmed] || '#FFFFFF'
}

/**
 * Parse button range like "1-6" or "1,2,3" or single "1"
 * @param {string|Array} buttons - Button specification
 * @param {number} player - Player number (default 1)
 * @returns {Array<string>} - Array of logical button names like ["p1.button1", "p1.button2"]
 */
function parseButtons(buttons, player = 1) {
  if (!buttons) return []

  // Already an array of logical buttons
  if (Array.isArray(buttons)) {
    return buttons.map(b => {
      // If already in "p1.button1" format, return as-is
      if (typeof b === 'string' && b.includes('.')) return b.toLowerCase()
      // Otherwise, convert number to logical button
      return `p${player}.button${b}`
    })
  }

  const buttonStr = String(buttons).trim()

  // Range format: "1-6"
  if (buttonStr.includes('-')) {
    const [start, end] = buttonStr.split('-').map(n => parseInt(n.trim(), 10))
    if (!isNaN(start) && !isNaN(end) && start <= end) {
      const result = []
      for (let i = start; i <= end; i++) {
        result.push(`p${player}.button${i}`)
      }
      return result
    }
  }

  // Comma-separated format: "1,2,3"
  if (buttonStr.includes(',')) {
    return buttonStr.split(',')
      .map(n => parseInt(n.trim(), 10))
      .filter(n => !isNaN(n))
      .map(n => `p${player}.button${n}`)
  }

  // Single button number
  const num = parseInt(buttonStr, 10)
  if (!isNaN(num)) {
    return [`p${player}.button${num}`]
  }

  // Already a logical button format
  if (buttonStr.includes('.')) {
    return [buttonStr.toLowerCase()]
  }

  return []
}

/**
 * Execute a single LED command
 * @param {Object} command - Command object with 'action' field
 * @param {Object} context - Execution context (calibrationToken, showToast, etc.)
 * @returns {Promise<Object>} - Result of command execution
 */
export async function executeLEDCommand(command, context) {
  const { action } = command
  const { calibrationToken, setCalibrationToken, showToast, loadChannelMappings } = context

  console.log('[CommandExecutor] Executing command:', command)

  try {
    switch (action) {
      case 'start_calibration': {
        if (calibrationToken) {
          showToast?.('Calibration already active', 'warning')
          return { status: 'skipped', reason: 'already_active' }
        }

        const result = await startLEDCalibration()
        const token = result.token
        setCalibrationToken?.(token)
        showToast?.(`Calibration started (token: ${token.substring(0, 8)}...)`, 'success')
        console.log('[CommandExecutor] Calibration started:', token)

        return { status: 'success', result, token }
      }

      case 'assign_channel': {
        if (!calibrationToken) {
          showToast?.('No active calibration session. Start calibration first.', 'error')
          return { status: 'error', reason: 'no_calibration_session' }
        }

        const { logical_button, device_id, channel } = command
        if (!logical_button || !device_id || channel === undefined) {
          showToast?.('Invalid assign_channel command: missing required fields', 'error')
          return { status: 'error', reason: 'missing_fields' }
        }

        const payload = {
          token: calibrationToken,
          logical_button,
          device_id,
          channel: Number(channel),
          dry_run: false
        }

        const result = await assignLEDCalibration(payload)
        showToast?.(`Assigned ${logical_button} → ${device_id} ch${channel}`, 'success')
        console.log('[CommandExecutor] Channel assigned:', result)

        // Reload channel mappings to show the update
        await loadChannelMappings?.()

        return { status: 'success', result }
      }

      case 'flash_channel': {
        if (!calibrationToken) {
          showToast?.('No active calibration session. Start calibration first.', 'error')
          return { status: 'error', reason: 'no_calibration_session' }
        }

        const { device_id, channel, duration_ms } = command
        if (!device_id || channel === undefined) {
          showToast?.('Invalid flash_channel command: missing device_id or channel', 'error')
          return { status: 'error', reason: 'missing_fields' }
        }

        const payload = {
          token: calibrationToken,
          device_id,
          channel: Number(channel),
          duration_ms: duration_ms || 300
        }

        const result = await flashLEDCalibration(payload)
        showToast?.(`Flashing ${device_id} ch${channel}`, 'info')
        console.log('[CommandExecutor] LED flashed:', result)

        return { status: 'success', result }
      }

      case 'flash_button': {
        if (!calibrationToken) {
          showToast?.('No active calibration session. Start calibration first.', 'error')
          return { status: 'error', reason: 'no_calibration_session' }
        }

        const { logical_button, duration_ms } = command
        if (!logical_button) {
          showToast?.('Invalid flash_button command: missing logical_button', 'error')
          return { status: 'error', reason: 'missing_fields' }
        }

        const payload = {
          token: calibrationToken,
          logical_button,
          duration_ms: duration_ms || 300
        }

        const result = await flashLEDCalibration(payload)
        showToast?.(`Flashing ${logical_button}`, 'info')
        console.log('[CommandExecutor] Button flashed:', result)

        return { status: 'success', result }
      }

      case 'stop_calibration': {
        if (!calibrationToken) {
          showToast?.('No active calibration session', 'warning')
          return { status: 'skipped', reason: 'no_active_session' }
        }

        const payload = { token: calibrationToken }
        const result = await stopLEDCalibration(payload)
        setCalibrationToken?.(null)
        showToast?.('Calibration stopped', 'success')
        console.log('[CommandExecutor] Calibration stopped:', result)

        return { status: 'success', result }
      }

      case 'set_button_color': {
        // Extract parameters from command
        const { buttons, color, player = 1, game, profile_name } = command

        // Parse buttons (supports "1-6", "1,2,3", ["p1.button1"], etc.)
        const parsedButtons = parseButtons(buttons, player)
        if (parsedButtons.length === 0) {
          showToast?.('No valid buttons specified for color change', 'error')
          return { status: 'error', reason: 'no_buttons' }
        }

        // Parse color (supports "purple", "#800080", etc.)
        const hexColor = parseColor(color)

        // Build the button mapping payload
        const buttonMapping = {}
        for (const btn of parsedButtons) {
          buttonMapping[btn] = { color: hexColor }
        }

        // Determine profile name and scope
        const resolvedProfileName = profile_name || game || 'default'
        const scope = game ? 'game' : 'default'

        const profilePayload = {
          scope,
          game: game || null,
          profile_name: resolvedProfileName,
          buttons: buttonMapping
        }

        console.log('[CommandExecutor] Setting button colors:', profilePayload)

        const result = await applyLEDProfile(profilePayload)

        const buttonList = parsedButtons.length === 1
          ? parsedButtons[0]
          : `${parsedButtons.length} buttons`
        showToast?.(`Set ${buttonList} to ${color || hexColor}`, 'success')
        console.log('[CommandExecutor] Button colors applied:', result)

        return { status: 'success', result, buttons: parsedButtons, color: hexColor }
      }

      case 'apply_theme': {
        const { theme, player, game } = command
        const themeName = (theme || '').toLowerCase().trim()
        const themeColors = LED_THEMES[themeName]

        if (!themeColors) {
          const available = Object.keys(LED_THEMES).join(', ')
          showToast?.(`Unknown theme "${theme}". Available: ${available}`, 'error')
          return { status: 'error', reason: 'unknown_theme' }
        }

        // Build button mapping — distribute theme colors across buttons
        const buttonMapping = {}
        const players = player ? [player] : [1, 2, 3, 4]

        for (const p of players) {
          const btnCount = p <= 2 ? 8 : 4
          for (let i = 1; i <= btnCount; i++) {
            buttonMapping[`p${p}.button${i}`] = { color: themeColors[(i - 1) % themeColors.length] }
          }
          buttonMapping[`p${p}.start`] = { color: themeColors[0] }
          buttonMapping[`p${p}.coin`] = { color: themeColors[themeColors.length - 1] }
        }

        const resolvedProfileName = game || 'default'
        const scope = game ? 'game' : 'default'

        const profilePayload = {
          scope,
          game: game || null,
          profile_name: resolvedProfileName,
          buttons: buttonMapping
        }

        console.log('[CommandExecutor] Applying theme:', themeName, profilePayload)
        const result = await applyLEDProfile(profilePayload)
        const target = player ? `Player ${player}` : 'All players'
        showToast?.(`${target}: ${themeName} theme applied!`, 'success')

        return { status: 'success', result, theme: themeName }
      }

      default:
        console.warn('[CommandExecutor] Unknown command action:', action)
        showToast?.(`Unknown command: ${action}`, 'warning')
        return { status: 'unknown', action }
    }
  } catch (error) {
    console.error('[CommandExecutor] Command execution failed:', error)
    const errorMsg = error?.error || error?.detail || error?.message || 'Command failed'
    showToast?.(errorMsg, 'error')
    return { status: 'error', error: errorMsg }
  }
}

/**
 * Execute multiple LED commands in sequence
 * @param {Array<Object>} commands - Array of command objects
 * @param {Object} context - Execution context
 * @returns {Promise<Array<Object>>} - Results of all commands
 */
export async function executeLEDCommands(commands, context) {
  if (!commands || commands.length === 0) {
    return []
  }

  const results = []
  for (const command of commands) {
    const result = await executeLEDCommand(command, context)
    results.push(result)

    // Stop on first error
    if (result.status === 'error') {
      console.warn('[CommandExecutor] Stopping batch execution due to error')
      break
    }
  }

  return results
}
