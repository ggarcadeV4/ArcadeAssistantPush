const BASE = '/api/local/gunner'
const PANEL_ID = 'gunner'

const generateCorrelationId = () => {
  try {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID()
    }
  } catch {}
  return `gunner-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
}

const warnDeviceIdFallback = () => {
  console.warn(
    '[Gunner] window.AA_DEVICE_ID not available, ' +
    'falling back to CAB-0001. Cabinet identity may not be unique.'
  )
  return 'CAB-0001'
}

const resolveDeviceId = () => {
  if (typeof window === 'undefined') {
    return warnDeviceIdFallback()
  }
  const deviceId = window.AA_DEVICE_ID || window.__DEVICE_ID__
  return deviceId || warnDeviceIdFallback()
}

const buildHeaders = ({ scope = 'state', json = true } = {}) => {
  const headers = {
    'x-device-id': resolveDeviceId(),
    'x-panel': PANEL_ID,
    'x-scope': scope,
    'x-corr-id': generateCorrelationId()
  }
  if (json) {
    headers['Content-Type'] = 'application/json'
  }
  return headers
}

const handleResponse = async (res) => {
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `Gunner request failed (${res.status})`)
  }
  const contentType = res.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return res.json()
  }
  return res.text()
}

export const listDevices = async () => {
  const res = await fetch(`${BASE}/devices`, {
    method: 'GET',
    headers: buildHeaders({ scope: 'state', json: false })
  })
  return handleResponse(res)
}

export const captureCalibrationPoint = async ({ deviceId, x, y }) => {
  const res = await fetch(`${BASE}/calibrate/point`, {
    method: 'POST',
    headers: buildHeaders({ scope: 'state' }),
    body: JSON.stringify({ device_id: deviceId, x, y })
  })
  return handleResponse(res)
}

export const submitCalibration = async (payload) => {
  const res = await fetch(`${BASE}/calibrate`, {
    method: 'POST',
    headers: buildHeaders({ scope: 'state' }),
    body: JSON.stringify(payload)
  })
  return handleResponse(res)
}

export const streamCalibration = async (payload, { onEvent, signal } = {}) => {
  const controller = new AbortController()
  if (signal) {
    signal.addEventListener('abort', () => controller.abort(), { once: true })
  }

  const res = await fetch(`${BASE}/calibrate/stream`, {
    method: 'POST',
    headers: {
      ...buildHeaders({ scope: 'state' }),
      Accept: 'text/event-stream'
    },
    body: JSON.stringify(payload),
    signal: controller.signal
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || 'Calibration stream failed')
  }

  const reader = res.body?.getReader()
  if (!reader) {
    throw new Error('Calibration stream reader unavailable')
  }

  const decoder = new TextDecoder()
  let buffer = ''
  const dispatchEvents = () => {
    const events = buffer.split('\n\n')
    buffer = events.pop() || ''
    events.forEach((eventChunk) => {
      const lines = eventChunk.split('\n')
      for (const line of lines) {
        if (line.startsWith('data:')) {
          const payload = line.slice(5).trim()
          if (!payload) continue
          try {
            const parsed = JSON.parse(payload)
            onEvent?.(parsed)
          } catch (err) {
            console.warn('Failed to parse calibration SSE payload', err)
          }
        }
      }
    })
  }

  const pump = () =>
    reader.read().then(({ done, value }) => {
      if (done) {
        if (buffer.length) {
          dispatchEvents()
        }
        return
      }
      buffer += decoder.decode(value, { stream: true })
      dispatchEvents()
      return pump()
    })

  pump().catch((err) => {
    if (err.name !== 'AbortError') {
      console.error('Calibration stream error:', err)
    }
  })

  return () => controller.abort()
}

export const listProfiles = async ({ userId }) => {
  const params = new URLSearchParams({ user_id: userId })
  const res = await fetch(`${BASE}/profiles?${params.toString()}`, {
    method: 'GET',
    headers: buildHeaders({ scope: 'state', json: false })
  })
  return handleResponse(res)
}

export const loadProfile = async ({ userId, game }) => {
  const res = await fetch(`${BASE}/profile/load`, {
    method: 'POST',
    headers: buildHeaders({ scope: 'state' }),
    body: JSON.stringify({ user_id: userId, game })
  })
  return handleResponse(res)
}

export const saveProfile = async ({ userId, game, points }) => {
  const res = await fetch(`${BASE}/profile/save`, {
    method: 'POST',
    headers: buildHeaders({ scope: 'state' }),
    body: JSON.stringify({ user_id: userId, game, points })
  })
  return handleResponse(res)
}

export const applyLegacyProfile = async ({ profile, dryRun = false }) => {
  const res = await fetch(`${BASE}/profile/apply`, {
    method: 'POST',
    headers: buildHeaders({ scope: 'state' }),
    body: JSON.stringify({ profile, dry_run: dryRun })
  })
  return handleResponse(res)
}

export const applyTendencies = async ({ profileId, handedness, sensitivity }) => {
  const res = await fetch(`${BASE}/tendencies/apply`, {
    method: 'POST',
    headers: buildHeaders({ scope: 'state' }),
    body: JSON.stringify({
      profile_id: profileId,
      handedness,
      sensitivity
    })
  })
  return handleResponse(res)
}

export const runPanelTest = async () => {
  const res = await fetch(`${BASE}/test`, {
    method: 'POST',
    headers: buildHeaders({ scope: 'state' })
  })
  return handleResponse(res)
}
