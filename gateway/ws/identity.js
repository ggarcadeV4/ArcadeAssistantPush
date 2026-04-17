import { randomUUID } from 'crypto'

const MISSING_DEVICE_CLOSE_CODE = 4401
const MISSING_DEVICE_CLOSE_REASON = 'device query parameter required'

const readHeader = (req, headerName) => {
  const value = req?.headers?.[headerName]
  return Array.isArray(value) ? value[0] : value
}

export const normalizeWebSocketIdentityValue = (value) =>
  typeof value === 'string' ? value.trim() : ''

export const extractWebSocketIdentity = (req, { defaultPanel = '', corrPrefix = 'ws' } = {}) => {
  const host = readHeader(req, 'host') || 'localhost'
  const url = new URL(req.url, `http://${host}`)

  const deviceId = normalizeWebSocketIdentityValue(
    url.searchParams.get('device') || readHeader(req, 'x-device-id')
  )
  const panel =
    normalizeWebSocketIdentityValue(url.searchParams.get('panel') || readHeader(req, 'x-panel')) ||
    normalizeWebSocketIdentityValue(defaultPanel)
  const corrId =
    normalizeWebSocketIdentityValue(url.searchParams.get('corr_id') || readHeader(req, 'x-corr-id')) ||
    `${corrPrefix}-${randomUUID()}`

  return { url, deviceId, panel, corrId }
}

export const attachWebSocketIdentity = (socket, identity, extra = {}) => {
  const metadata = { ...identity, ...extra }
  socket.aaIdentity = metadata
  return metadata
}

export const buildIdentityHeaders = (identity, extraHeaders = {}) => {
  const headers = {
    'x-device-id': identity.deviceId,
    'x-panel': identity.panel,
    'x-corr-id': identity.corrId,
    ...extraHeaders
  }

  Object.keys(headers).forEach((key) => {
    if (!headers[key]) {
      delete headers[key]
    }
  })

  return headers
}

const safeSendJson = (socket, payload) => {
  try {
    const openState = typeof socket.OPEN === 'number' ? socket.OPEN : 1
    if (socket.readyState === openState) {
      socket.send(JSON.stringify(payload))
    }
  } catch (err) {
    console.error('[Gateway WS Identity] Failed to send payload:', err)
  }
}

const useSoftReject = () => {
  const raw = String(process.env.AA_WS_IDENTITY_SOFT_REJECT || '').trim().toLowerCase()
  if (raw) {
    return ['1', 'true', 'yes', 'on'].includes(raw)
  }
  return process.env.NODE_ENV === 'development'
}

export const ensureDeviceIdentity = (socket, identity, { channel } = {}) => {
  if (identity.deviceId) {
    return true
  }

  const message = `${channel || 'websocket'} requires a non-empty device identity`
  if (useSoftReject()) {
    safeSendJson(socket, {
      type: 'error',
      code: 'MISSING_DEVICE_IDENTITY',
      message,
      panel: identity.panel || channel || 'ws',
      corr_id: identity.corrId
    })
  }

  try {
    socket.close(MISSING_DEVICE_CLOSE_CODE, MISSING_DEVICE_CLOSE_REASON)
  } catch {}
  return false
}
