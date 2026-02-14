/**
 * Drive path constants (frontend mirror of backend constants).
 * Used for display purposes only - never used for actual file access.
 * All file operations go through Gateway → Backend.
 *
 * IMPORTANT: No hardcoded drive letters. These are label placeholders only.
 * Actual paths come from backend via AA_DRIVE_ROOT environment variable.
 */

// Placeholder paths for display only - fetch real paths from backend
export const LAUNCHBOX_PATHS = {
  ROOT: '<AA_DRIVE_ROOT>\\LaunchBox',
  PLATFORMS_DIR: '<AA_DRIVE_ROOT>\\LaunchBox\\Data\\Platforms',
  IMAGES_DIR: '<AA_DRIVE_ROOT>\\LaunchBox\\Images',
  LAUNCHBOX_EXE: '<AA_DRIVE_ROOT>\\LaunchBox\\LaunchBox.exe',
  BIGBOX_EXE: '<AA_DRIVE_ROOT>\\LaunchBox\\BigBox.exe',
  MAME_ROMS: '<AA_DRIVE_ROOT>\\Roms\\MAME',
}

export const LAUNCH_METHODS = {
  CLI_LAUNCHER: 'cli_launcher',
  LAUNCHBOX: 'launchbox',
  DIRECT: 'direct',
}

export const API_ENDPOINTS = {
  GAMES: '/api/launchbox/games',
  PLATFORMS: '/api/launchbox/platforms',
  GENRES: '/api/launchbox/genres',
  RANDOM: '/api/launchbox/random',
  RESOLVE: '/api/launchbox/resolve',
  LAUNCH: '/api/launchbox/launch',
  STATS: '/api/launchbox/stats',
  CACHE_STATUS: '/api/launchbox/cache/status',
  CACHE_REVALIDATE: '/api/launchbox/cache/revalidate',
  CACHE_RELOAD: '/api/launchbox/cache/reload',
}

