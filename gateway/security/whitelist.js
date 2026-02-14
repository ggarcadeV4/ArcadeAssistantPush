// gateway/security/whitelist.js (ESM)
// Drive-letter agnostic whitelist for config edits. All paths must be under AA_DRIVE_ROOT.
import path from 'path'

// Get AA_DRIVE_ROOT and build escaped regex prefix
function getDriveRootRegex() {
  const root = process.env.AA_DRIVE_ROOT
  if (!root) {
    return null // Will cause explicit rejection
  }
  // Escape special regex chars and normalize to backslash
  const normalized = path.win32.normalize(root).replace(/\\$/, '')
  const escaped = normalized.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&')
  return escaped
}

// Relative patterns (appended after AA_DRIVE_ROOT)
// Format: panel -> array of relative path regex patterns
const RELATIVE_PATTERNS = {
  dewey: [
    /^\\Emulators\\MAME\\[^\\]+\.ini$/i,
    /^\\Arcade Assistant\\config\\[^\\]+\.ini$/i,
    /^\\configs\\[^\\]+\.ini$/i,
  ],
  controls: [
    /^\\Emulators\\RetroArch\\config\\[^\\]+\.cfg$/i,
    /^\\configs\\retroarch\\[^\\]+\.cfg$/i,
  ],
  led: [
    /^\\Arcade Assistant\\config\\ledblinky\.json$/i,
    /^\\configs\\ledblinky\.json$/i,
  ],
  'led-blinky': [
    /^\\Arcade Assistant\\config\\ledblinky\.json$/i,
    /^\\configs\\ledblinky\.json$/i,
  ],
  led_blinky: [
    /^\\Arcade Assistant\\config\\ledblinky\.json$/i,
    /^\\configs\\ledblinky\.json$/i,
  ],
}

export function ensureAllowed(panel = '', filePath = '') {
  const rootEscaped = getDriveRootRegex()
  if (!rootEscaped) {
    // AA_DRIVE_ROOT not set - explicit rejection (no silent fallback)
    console.error('[whitelist] AA_DRIVE_ROOT_NOT_SET - rejecting all paths')
    return false
  }

  const patterns = RELATIVE_PATTERNS[String(panel).toLowerCase()] || []
  if (patterns.length === 0) {
    return false
  }

  // Normalize input path to Windows format
  const fp = path.win32.normalize(path.resolve(filePath))

  // Check if path starts with AA_DRIVE_ROOT and matches a relative pattern
  const rootRegex = new RegExp('^' + rootEscaped, 'i')
  if (!rootRegex.test(fp)) {
    // Path is outside AA_DRIVE_ROOT - reject
    return false
  }

  // Extract the relative portion after drive root
  const relativePart = fp.substring(rootEscaped.replace(/\\\\/g, '\\').length)

  return patterns.some((rx) => rx.test(relativePart))
}
