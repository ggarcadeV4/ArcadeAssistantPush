/**
 * LED Command Executor
 * Executes LED calibration commands parsed from AI responses
 */

import {
  startLEDCalibration,
  assignLEDCalibration,
  flashLEDCalibration,
  stopLEDCalibration,
  applyLEDProfile,
  escapeLEDCalibration
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

/**
 * Predefined LED lighting themes
 * Each theme maps logical buttons to hex colors
 */
const LED_THEMES = {
  sunset: { 'p1.button1': '#FF4500', 'p1.button2': '#FF6347', 'p1.button3': '#FF7F50', 'p1.button4': '#FFA500', 'p1.button5': '#FFD700', 'p1.button6': '#FFFF00', 'p2.button1': '#FF4500', 'p2.button2': '#FF6347', 'p2.button3': '#FF7F50', 'p2.button4': '#FFA500', 'p2.button5': '#FFD700', 'p2.button6': '#FFFF00' },
  ocean: { 'p1.button1': '#001F3F', 'p1.button2': '#003366', 'p1.button3': '#006699', 'p1.button4': '#0099CC', 'p1.button5': '#00CCFF', 'p1.button6': '#66FFFF', 'p2.button1': '#001F3F', 'p2.button2': '#003366', 'p2.button3': '#006699', 'p2.button4': '#0099CC', 'p2.button5': '#00CCFF', 'p2.button6': '#66FFFF' },
  cyberpunk: { 'p1.button1': '#FF00FF', 'p1.button2': '#FF1493', 'p1.button3': '#00FFFF', 'p1.button4': '#FF00FF', 'p1.button5': '#00FFFF', 'p1.button6': '#FF1493', 'p2.button1': '#FF00FF', 'p2.button2': '#FF1493', 'p2.button3': '#00FFFF', 'p2.button4': '#FF00FF', 'p2.button5': '#00FFFF', 'p2.button6': '#FF1493' },
  christmas: { 'p1.button1': '#FF0000', 'p1.button2': '#00FF00', 'p1.button3': '#FF0000', 'p1.button4': '#00FF00', 'p1.button5': '#FF0000', 'p1.button6': '#00FF00', 'p2.button1': '#00FF00', 'p2.button2': '#FF0000', 'p2.button3': '#00FF00', 'p2.button4': '#FF0000', 'p2.button5': '#00FF00', 'p2.button6': '#FF0000' },
  fire_and_ice: { 'p1.button1': '#FF0000', 'p1.button2': '#FF4500', 'p1.button3': '#FF6600', 'p1.button4': '#FF0000', 'p1.button5': '#FF4500', 'p1.button6': '#FF6600', 'p2.button1': '#0000FF', 'p2.button2': '#0099FF', 'p2.button3': '#00CCFF', 'p2.button4': '#0000FF', 'p2.button5': '#0099FF', 'p2.button6': '#00CCFF' },
  retro: { 'p1.button1': '#FF0000', 'p1.button2': '#FFFF00', 'p1.button3': '#00FF00', 'p1.button4': '#00FFFF', 'p1.button5': '#0000FF', 'p1.button6': '#FF00FF', 'p2.button1': '#FF0000', 'p2.button2': '#FFFF00', 'p2.button3': '#00FF00', 'p2.button4': '#00FFFF', 'p2.button5': '#0000FF', 'p2.button6': '#FF00FF' },
  neon: { 'p1.button1': '#39FF14', 'p1.button2': '#FF073A', 'p1.button3': '#FF6EC7', 'p1.button4': '#FFFF00', 'p1.button5': '#00FFFF', 'p1.button6': '#FF00FF', 'p2.button1': '#39FF14', 'p2.button2': '#FF073A', 'p2.button3': '#FF6EC7', 'p2.button4': '#FFFF00', 'p2.button5': '#00FFFF', 'p2.button6': '#FF00FF' },
  forest: { 'p1.button1': '#006400', 'p1.button2': '#228B22', 'p1.button3': '#32CD32', 'p1.button4': '#8B4513', 'p1.button5': '#228B22', 'p1.button6': '#006400', 'p2.button1': '#006400', 'p2.button2': '#228B22', 'p2.button3': '#32CD32', 'p2.button4': '#8B4513', 'p2.button5': '#228B22', 'p2.button6': '#006400' },
  vaporwave: { 'p1.button1': '#FF71CE', 'p1.button2': '#01CDFE', 'p1.button3': '#05FFA1', 'p1.button4': '#B967FF', 'p1.button5': '#FFFB96', 'p1.button6': '#FF71CE', 'p2.button1': '#01CDFE', 'p2.button2': '#05FFA1', 'p2.button3': '#B967FF', 'p2.button4': '#FFFB96', 'p2.button5': '#FF71CE', 'p2.button6': '#01CDFE' },
  electric: { 'p1.button1': '#00FFFF', 'p1.button2': '#00BFFF', 'p1.button3': '#1E90FF', 'p1.button4': '#FFFFFF', 'p1.button5': '#00BFFF', 'p1.button6': '#00FFFF', 'p2.button1': '#00FFFF', 'p2.button2': '#00BFFF', 'p2.button3': '#1E90FF', 'p2.button4': '#FFFFFF', 'p2.button5': '#00BFFF', 'p2.button6': '#00FFFF' }
}

/**
 * Parse a color value - accepts hex codes or color names
 * @param {string} color - Color name or hex code
 * @returns {string} - Hex color code
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
        const { theme_name } = command
        const themeColors = LED_THEMES[theme_name]
        if (!themeColors) {
          const available = Object.keys(LED_THEMES).join(', ')
          showToast?.(`Unknown theme: ${theme_name}. Available: ${available}`, 'warning')
          return { status: 'error', reason: 'unknown_theme' }
        }

        // Build button mapping from theme
        const buttonMapping = {}
        for (const [btn, hex] of Object.entries(themeColors)) {
          buttonMapping[btn] = { color: hex }
        }

        const result = await applyLEDProfile({
          scope: 'theme',
          profile_name: theme_name,
          buttons: buttonMapping
        })
        showToast?.(`Applied theme: ${theme_name}`, 'success')
        console.log('[CommandExecutor] Theme applied:', theme_name, result)

        return { status: 'success', result, theme: theme_name }
      }

      case 'calibration_escape_hatch': {
        if (!calibrationToken) {
          showToast?.('No active calibration session', 'warning')
          return { status: 'skipped', reason: 'no_calibration' }
        }

        const { action: escapeAction, custom_name } = command
        const escapePayload = {
          token: calibrationToken,
          action: escapeAction,
          ...(custom_name && { custom_name })
        }

        try {
          const result = await escapeLEDCalibration(escapePayload)
          console.log('[CommandExecutor] Calibration escape result:', result)

          if (escapeAction === 'skip') {
            showToast?.('Skipped port', 'info')
          } else if (escapeAction === 'assign_custom' && custom_name) {
            showToast?.(`Assigned: ${custom_name}`, 'success')
          }

          return { status: 'success', escape_action: escapeAction, ...result }
        } catch (err) {
          console.error('[CommandExecutor] Escape hatch failed:', err)
          showToast?.('Escape hatch failed', 'error')
          return { status: 'error', reason: 'escape_failed', error: err }
        }
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
