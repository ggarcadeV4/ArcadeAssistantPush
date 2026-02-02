/**
 * Drive Detection Utilities (Golden Drive Contract)
 * 
 * IMPORTANT: No hardcoded drive letters. Uses AA_DRIVE_ROOT environment variable.
 * If AA_DRIVE_ROOT is not set, functions return explicit errors.
 */
import fs from 'fs'
import path from 'path'

export function warnIfManifestMissing(manifestPath) {
  const isProd = process.env.NODE_ENV === 'production'
  try {
    if (!fs.existsSync(manifestPath)) {
      const msg = `Drive manifest missing at ${manifestPath}`
      if (isProd) {
        throw new Error(msg)
      } else {
        console.warn(msg, '(dev only: proceeding)')
      }
    }
  } catch (e) {
    if (isProd) throw e
    console.warn('Manifest check warning:', e?.message || e)
  }
}

/**
 * Get drive root from AA_DRIVE_ROOT environment variable.
 * Returns null if not set (no hardcoded fallback).
 */
export function getDriveRoot() {
  const raw = process.env.AA_DRIVE_ROOT || ''
  if (!raw.trim()) {
    return null
  }
  return raw.replace(/[\\/]+$/, '')  // Normalize trailing slashes
}

/**
 * Get drive root, throwing error if not set.
 */
export function requireDriveRoot() {
  const root = getDriveRoot()
  if (!root) {
    throw new Error('AA_DRIVE_ROOT environment variable is not set')
  }
  return root
}

/**
 * Check if drive root is configured.
 * Note: Drive letter checking is deprecated - any drive should work.
 */
export function isDriveRootSet() {
  return !!getDriveRoot()
}

/**
 * Legacy compatibility - checks if on A: drive.
 * @deprecated Use isDriveRootSet() instead. Drive letter should not matter.
 */
export function isOnADrive() {
  const driveRoot = getDriveRoot() || ''
  const upper = driveRoot.toUpperCase()
  return upper.startsWith('A:') || upper.startsWith('/MNT/A')
}

/**
 * Get drive root with fallback for backward compatibility.
 * Prefer getDriveRoot() or requireDriveRoot() for new code.
 */
export function getADriveRoot() {
  const root = getDriveRoot()
  if (!root) {
    console.warn('[driveDetection] AA_DRIVE_ROOT not set - using cwd')
    return process.cwd()
  }
  return root
}

export function getLaunchBoxPaths() {
  const root = getADriveRoot()
  const ROOT = path.join(root, 'LaunchBox')
  const DATA = path.join(ROOT, 'Data')
  return {
    ROOT,
    DATA,
    MASTER_XML: path.join(DATA, 'LaunchBox.xml'),
    PLATFORMS: path.join(DATA, 'Platforms'),
    PLAYLISTS: path.join(DATA, 'Playlists'),
    CLI_LAUNCHER: path.join(ROOT, 'ThirdParty', 'CLI_Launcher', 'CLI_Launcher.exe')
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

// Legacy alias
export const validateADrivePaths = validateDrivePaths

export function getDriveStatus() {
  const driveRootSet = isDriveRootSet()
  const validation = driveRootSet ? validateDrivePaths() : { valid: false, missing: ['AA_DRIVE_ROOT not set'] }
  const driveRoot = getADriveRoot()
  return {
    isDriveRootSet: driveRootSet,
    isOnADrive: isOnADrive(),  // Legacy
    driveRoot,
    pathsValid: validation.valid,
    missingPaths: validation.missing,
    mode: driveRootSet && validation.valid ? 'production' : 'demo',
    message: driveRootSet && validation.valid
      ? `Drive root detected and validated: ${driveRoot}`
      : driveRootSet
        ? 'Drive root set but paths invalid'
        : 'AA_DRIVE_ROOT not set - using demo mode'
  }
}

