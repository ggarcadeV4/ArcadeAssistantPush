/**
 * Drive Detection Utilities (Golden Drive Contract)
 *
 * IMPORTANT: No hardcoded drive letters. Uses AA_DRIVE_ROOT and an optional
 * LAUNCHBOX_ROOT override. No implicit process.cwd() fallback is allowed for
 * primary runtime identity.
 */
import fs from 'fs'
import path from 'path'
import dotenv from 'dotenv'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const PROJECT_ROOT = path.resolve(__dirname, '..', '..')

dotenv.config({ path: path.join(PROJECT_ROOT, '.env') })

function isWindowsAbsolute(input) {
  return /^[A-Za-z]:[\\/]/.test(input)
}

function isWsl() {
  return process.platform === 'linux' && Boolean(process.env.WSL_DISTRO_NAME || process.env.WSL_INTEROP)
}

function windowsToWsl(input) {
  const driveLetter = input[0].toLowerCase()
  const rest = input.slice(2).replace(/\\/g, '/').replace(/^\/+/, '')
  return rest ? `/mnt/${driveLetter}/${rest}` : `/mnt/${driveLetter}`
}

function wslToWindows(input) {
  const driveLetter = input[5].toUpperCase()
  const rest = input.slice(6).replace(/\//g, '\\').replace(/^\\+/, '')
  return rest ? `${driveLetter}:\\${rest}` : `${driveLetter}:\\`
}

function translateRuntimePath(input) {
  const value = String(input || '').trim()
  if (!value) return value

  if (process.platform === 'win32' && value.toLowerCase().startsWith('/mnt/')) {
    return wslToWindows(value)
  }

  if (isWsl() && isWindowsAbsolute(value)) {
    return windowsToWsl(value)
  }

  return value
}

function normalizeRoot(input) {
  const value = String(input || '').trim()
  if (!value) return value

  if (isWindowsAbsolute(value)) {
    const normalized = value.replace(/\//g, '\\')
    const prefix = `${normalized[0].toUpperCase()}:`
    const rest = normalized.slice(2).replace(/^[\\\/]+/, '')
    return rest ? `${prefix}\\${rest}`.replace(/[\\\/]+$/, '') : `${prefix}\\`
  }

  if (/^[A-Za-z]:$/.test(value)) {
    return `${value[0].toUpperCase()}:\\`
  }

  if (value.toLowerCase().startsWith('/mnt/')) {
    return value.replace(/\\/g, '/').replace(/\/+$/, '')
  }

  return value.replace(/[\\\/]+$/, '')
}

export function getProjectRoot() {
  return PROJECT_ROOT
}

export function resolvePathFromBase(input, base = PROJECT_ROOT) {
  const value = String(input || '').trim()
  if (!value) return null

  const translated = translateRuntimePath(value)
  if (path.isAbsolute(translated) || isWindowsAbsolute(translated)) {
    return normalizeRoot(translated)
  }

  return path.resolve(base, translated)
}

export function resolveDriveRoot(input, { allowProjectFallback = false } = {}) {
  const resolved = resolvePathFromBase(input, PROJECT_ROOT)
  if (resolved) {
    return resolved
  }
  return allowProjectFallback ? PROJECT_ROOT : null
}

export function getDriveRoot() {
  return resolveDriveRoot(process.env.AA_DRIVE_ROOT, { allowProjectFallback: false })
}

export function requireDriveRoot() {
  const root = getDriveRoot()
  if (!root) {
    throw new Error('AA_DRIVE_ROOT environment variable is not set')
  }
  return root
}

export function getManifestPath(driveRoot = getDriveRoot()) {
  return driveRoot ? path.join(driveRoot, '.aa', 'manifest.json') : null
}

export function getLaunchBoxRoot(driveRoot = requireDriveRoot()) {
  const override = resolvePathFromBase(process.env.LAUNCHBOX_ROOT, driveRoot || PROJECT_ROOT)
  return override || path.join(driveRoot, 'LaunchBox')
}

export function getRuntimePaths(driveRoot = getDriveRoot()) {
  if (!driveRoot) {
    return {
      driveRoot: null,
      manifestPath: null,
      launchboxRoot: null,
      launchboxImages: null,
      launchboxData: null,
      launchboxPlatforms: null,
      emulatorsRoot: null,
    }
  }

  const launchboxRoot = getLaunchBoxRoot(driveRoot)
  return {
    driveRoot,
    manifestPath: getManifestPath(driveRoot),
    launchboxRoot,
    launchboxImages: path.join(launchboxRoot, 'Images'),
    launchboxData: path.join(launchboxRoot, 'Data'),
    launchboxPlatforms: path.join(launchboxRoot, 'Data', 'Platforms'),
    emulatorsRoot: path.join(driveRoot, 'Emulators'),
  }
}

export function warnIfManifestMissing(driveRoot = getDriveRoot()) {
  const isProd = process.env.NODE_ENV === 'production'
  try {
    const manifestPath = getManifestPath(driveRoot)
    if (!manifestPath) {
      const msg = 'Drive manifest unavailable because AA_DRIVE_ROOT is not set'
      if (isProd) {
        throw new Error(msg)
      }
      console.warn(msg, '(dev only: proceeding)')
      return
    }

    if (!fs.existsSync(manifestPath)) {
      const msg = `Drive manifest missing at ${manifestPath}`
      if (isProd) {
        throw new Error(msg)
      }
      console.warn(msg, '(dev only: proceeding)')
    }
  } catch (e) {
    if (isProd) throw e
    console.warn('Manifest check warning:', e?.message || e)
  }
}

export function isDriveRootSet() {
  return !!getDriveRoot()
}

/**
 * Legacy compatibility helper.
 * @deprecated Root location is no longer tied to a specific drive letter.
 */
export function isOnADrive() {
  return !!getDriveRoot()
}

/**
 * Legacy compatibility helper.
 * Prefer getDriveRoot() for runtime identity. This helper is allowed to use
 * the repo root only as an explicit dev/demo fallback.
 */
export function getADriveRoot() {
  const root = resolveDriveRoot(process.env.AA_DRIVE_ROOT, { allowProjectFallback: true })
  if (!process.env.AA_DRIVE_ROOT?.trim()) {
    console.warn('[driveDetection] AA_DRIVE_ROOT not set - using explicit project-root demo fallback')
  }
  return root
}

export function getLaunchBoxPaths() {
  const runtimePaths = getRuntimePaths(getADriveRoot())
  const ROOT = runtimePaths.launchboxRoot
  const DATA = runtimePaths.launchboxData
  return {
    ROOT,
    DATA,
    MASTER_XML: path.join(DATA, 'LaunchBox.xml'),
    PLATFORMS: runtimePaths.launchboxPlatforms,
    PLAYLISTS: path.join(DATA, 'Playlists'),
    CLI_LAUNCHER: path.join(ROOT, 'ThirdParty', 'CLI_Launcher', 'CLI_Launcher.exe'),
  }
}

export function validateDrivePaths() {
  if (!isDriveRootSet()) {
    return { valid: false, missing: ['AA_DRIVE_ROOT not set'] }
  }
  const paths = getLaunchBoxPaths()
  const missing = []
  const critical = [
    { name: 'LaunchBox Root', path: paths.ROOT },
    { name: 'LaunchBox Data', path: paths.DATA },
    { name: 'Platforms', path: paths.PLATFORMS },
  ]
  for (const { name, path: p } of critical) {
    if (!fs.existsSync(p)) missing.push(`${name}: ${p}`)
  }
  return { valid: missing.length === 0, missing }
}

export const validateADrivePaths = validateDrivePaths

export function getDriveStatus() {
  const driveRoot = getDriveRoot()
  const driveRootSet = Boolean(driveRoot)
  const validation = driveRootSet ? validateDrivePaths() : { valid: false, missing: ['AA_DRIVE_ROOT not set'] }
  return {
    isDriveRootSet: driveRootSet,
    isOnADrive: isOnADrive(),
    driveRoot,
    pathsValid: validation.valid,
    missingPaths: validation.missing,
    mode: driveRootSet && validation.valid ? 'production' : 'demo',
    message: driveRootSet && validation.valid
      ? `Configured root detected and validated: ${driveRoot}`
      : driveRootSet
        ? 'Configured root set but cabinet paths are invalid'
        : 'AA_DRIVE_ROOT not set - demo/read-only mode',
  }
}
