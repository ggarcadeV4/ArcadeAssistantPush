/**
 * ledBlinkyClient: API client for LED Blinky operations
 * Routes: /led/*
 */

const BASE = '/api/local/led'
const PANEL_KEY = 'led-blinky'

const generateCorrelationId = () => {
  try {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID()
    }
  } catch { }
  return `corr-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`
}

export const resolveDeviceId = () => {
  if (typeof window === 'undefined') {
    return 'CAB-0001'
  }
  return window.AA_DEVICE_ID ?? window.__DEVICE_ID__ ?? 'CAB-0001'
}

const resolveOrigin = () => {
  if (typeof window === 'undefined' || !window.location) {
    return 'http://localhost:8787'
  }
  if (window.location.port === '5173') {
    return 'http://localhost:8787'
  }
  return window.location.origin
}

const commonHeaders = ({ panel = PANEL_KEY, scope, json = true, corrId } = {}) => {
  const headers = {
    'x-device-id': resolveDeviceId(),
    'x-panel': panel,
    'x-corr-id': corrId || generateCorrelationId()
  }

  if (scope) {
    headers['x-scope'] = scope
  }

  if (json) {
    headers['Content-Type'] = 'application/json'
  }

  return headers
}

export const buildGatewayWebSocketUrl = (path = `${BASE}/ws`) => {
  const origin = resolveOrigin()
  const httpUrl = new URL(path, origin)
  httpUrl.searchParams.set('device', resolveDeviceId())
  httpUrl.searchParams.set('panel', PANEL_KEY)

  const wsUrl = httpUrl.toString().replace(/^http/, 'ws')
  return wsUrl
}

export async function testLED({ effect, durationMs = 1000, color = '#00E5FF' }) {
  const res = await fetch(`${BASE}/test`, {
    method: 'POST',
    headers: commonHeaders({ scope: 'state' }),
    body: JSON.stringify({ effect, durationMs, color })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Test failed' }))
  return await res.json()
}

/**
 * Test all LEDs - runs a brief pulse pattern across all channels.
 * Used for camera demos and clone validation.
 * @param {Object} options
 * @param {number} [options.durationMs=2000] - Duration of test in milliseconds
 * @returns {Promise<Object>} Test result with status
 */
export async function testAllLEDs({ durationMs = 2000 } = {}) {
  const res = await fetch(`${BASE}/test/all`, {
    method: 'POST',
    headers: commonHeaders({ scope: 'state' }),
    body: JSON.stringify({ duration_ms: durationMs })
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'Test all LEDs failed' }))
    throw err
  }
  return await res.json()
}

export async function previewLEDProfile(profile) {
  const res = await fetch(`${BASE}/profile/preview`, {
    method: 'POST',
    headers: commonHeaders({ scope: 'config' }),
    body: JSON.stringify(profile)
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Preview failed' }))
  return await res.json()
}

export async function applyLEDProfile(profile) {
  const res = await fetch(`${BASE}/profile/apply`, {
    method: 'POST',
    headers: commonHeaders({ scope: 'config' }),
    body: JSON.stringify(profile)
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Apply failed' }))
  return await res.json()
}

export async function listLEDProfiles() {
  const res = await fetch(`${BASE}/profiles`, {
    method: 'GET',
    headers: commonHeaders({ scope: 'state', json: false })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to list profiles' }))
  return await res.json()
}

export async function getLEDProfile(profileName) {
  const res = await fetch(`${BASE}/profiles/${profileName}`, {
    method: 'GET',
    headers: commonHeaders({ scope: 'state', json: false })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Profile not found' }))
  return await res.json()
}

export async function getLEDStatus() {
  const res = await fetch(`${BASE}/status`, {
    method: 'GET',
    headers: commonHeaders({ scope: 'state', json: false })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to load LED status' }))
  return await res.json()
}

export async function refreshLEDHardware() {
  const res = await fetch(`${BASE}/refresh`, {
    method: 'POST',
    headers: commonHeaders({ scope: 'state' })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Hardware refresh failed' }))
  return await res.json()
}

export async function listLEDDevices() {
  const res = await fetch(`${BASE}/devices`, {
    method: 'GET',
    headers: commonHeaders({ scope: 'state', json: false })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to list LED devices' }))
  return await res.json()
}

export async function closeLEDConnection(connectionId) {
  const res = await fetch(`${BASE}/ws`, {
    method: 'POST',
    headers: commonHeaders({ scope: 'state' }),
    body: JSON.stringify({
      action: 'disconnect',
      connectionId
    })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to close LED connection' }))
  return await res.json()
}

export async function runLEDPattern(pattern, params = {}) {
  const res = await fetch(`${BASE}/pattern/run`, {
    method: 'POST',
    headers: commonHeaders({ scope: 'state' }),
    body: JSON.stringify({ pattern, params })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to run pattern' }))
  return await res.json()
}

export async function setLEDBrightness(level) {
  const res = await fetch(`${BASE}/brightness`, {
    method: 'POST',
    headers: commonHeaders({ scope: 'state' }),
    body: JSON.stringify({ level })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to update brightness' }))
  return await res.json()
}

const LAUNCHBOX_BASE = '/api/launchbox'

export async function searchLaunchBoxGames({ query = '', platform = 'All', limit = 40 } = {}) {
  const params = new URLSearchParams()
  if (query) params.set('q', query)
  if (platform && platform.toLowerCase() !== 'all') params.set('platform', platform)
  if (limit) params.set('limit', String(limit))

  const res = await fetch(`${LAUNCHBOX_BASE}/games?${params.toString()}`, {
    method: 'GET',
    headers: commonHeaders({ scope: 'state', json: false })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to load LaunchBox games' }))
  return await res.json()
}

export async function fetchGameProfile(gameId) {
  const params = new URLSearchParams({ game_id: gameId })
  const res = await fetch(`${BASE}/game-profile?${params.toString()}`, {
    method: 'GET',
    headers: commonHeaders({ scope: 'state', json: false })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to load game profile' }))
  return await res.json()
}

export async function fetchAllGameProfiles() {
  const res = await fetch(`${BASE}/game-profiles`, {
    method: 'GET',
    headers: commonHeaders({ scope: 'state', json: false })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to load LED game profiles' }))
  return await res.json()
}

export async function previewGameProfileBinding({ gameId, profileName }) {
  const res = await fetch(`${BASE}/game-profile/preview`, {
    method: 'POST',
    headers: commonHeaders({ scope: 'config' }),
    body: JSON.stringify({ game_id: gameId, profile_name: profileName })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to preview game binding' }))
  return await res.json()
}

export async function applyGameProfileBinding({ gameId, profileName }) {
  const res = await fetch(`${BASE}/game-profile/apply`, {
    method: 'POST',
    headers: commonHeaders({ scope: 'config' }),
    body: JSON.stringify({ game_id: gameId, profile_name: profileName })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to bind LED profile' }))
  return await res.json()
}

export async function deleteGameProfileBinding(gameId) {
  const params = new URLSearchParams({ game_id: gameId })
  const res = await fetch(`${BASE}/game-profile?${params.toString()}`, {
    method: 'DELETE',
    headers: commonHeaders({ scope: 'config', json: false })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to remove LED binding' }))
  return await res.json()
}

export async function listLEDChannelMappings() {
  const res = await fetch(`${BASE}/channels`, {
    method: 'GET',
    headers: commonHeaders({ scope: 'state', json: false })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to load LED channels' }))
  return await res.json()
}

export async function previewLEDChannels(payload) {
  const res = await fetch(`${BASE}/channels/preview`, {
    method: 'POST',
    headers: commonHeaders({ scope: 'config' }),
    body: JSON.stringify(payload)
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'LED channel preview failed' }))
  return await res.json()
}

export async function applyLEDChannels(payload) {
  const res = await fetch(`${BASE}/channels/apply`, {
    method: 'POST',
    headers: commonHeaders({ scope: 'config' }),
    body: JSON.stringify(payload)
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'LED channel apply failed' }))
  return await res.json()
}

export async function deleteLEDChannelMapping(logicalButton, { dryRun } = {}) {
  const params = new URLSearchParams()
  if (typeof dryRun === 'boolean') {
    params.set('dry_run', String(dryRun))
  }
  const query = params.toString()
  const url = query ? `${BASE}/channels/${encodeURIComponent(logicalButton)}?${query}` : `${BASE}/channels/${encodeURIComponent(logicalButton)}`
  const res = await fetch(url, {
    method: 'DELETE',
    headers: commonHeaders({ scope: 'config', json: false })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to delete LED channel' }))
  return await res.json()
}

export const fetchLEDChannelMapping = listLEDChannelMappings
export const previewLEDChannelMapping = previewLEDChannels
export const applyLEDChannelMapping = applyLEDChannels
export const flashLEDChannel = flashLEDCalibration

export async function startLEDCalibration() {
  const res = await fetch(`${BASE}/calibrate/start`, {
    method: 'POST',
    headers: commonHeaders({ scope: 'config' }),
    body: JSON.stringify({})
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to start calibration' }))
  return await res.json()
}

export async function assignLEDCalibration(payload) {
  const res = await fetch(`${BASE}/calibrate/assign`, {
    method: 'POST',
    headers: commonHeaders({ scope: 'config' }),
    body: JSON.stringify(payload)
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to assign calibration' }))
  return await res.json()
}

export async function flashLEDCalibration(payload) {
  const res = await fetch(`${BASE}/calibrate/flash`, {
    method: 'POST',
    headers: commonHeaders({ scope: 'config' }),
    body: JSON.stringify(payload)
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to flash LED' }))
  return await res.json()
}

export async function stopLEDCalibration(payload) {
  const res = await fetch(`${BASE}/calibrate/stop`, {
    method: 'POST',
    headers: commonHeaders({ scope: 'config' }),
    body: JSON.stringify(payload)
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to stop calibration' }))
  return await res.json()
}

export async function getLEDEngineHealth() {
  const res = await fetch(`${BASE}/engine-health`, {
    method: 'GET',
    headers: commonHeaders({ scope: 'state', json: false })
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Failed to load engine health' }))
  return await res.json()
}

export async function runLEDChannelTest({ deviceId, channel, durationMs = 300 }) {
  const payload = {
    device_id: deviceId,
    channel: Number(channel),
    duration_ms: durationMs
  }

  const res = await fetch(`${BASE}/diagnostics/channel-test`, {
    method: 'POST',
    headers: commonHeaders({ scope: 'state' }),
    body: JSON.stringify(payload)
  })

  if (!res.ok) throw await res.json().catch(() => ({ error: 'Channel test failed' }))
  return await res.json()
}
