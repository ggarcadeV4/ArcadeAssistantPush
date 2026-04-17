import { WebSocket } from 'ws'
import { randomUUID } from 'crypto'
import { buildIdentityHeaders, ensureDeviceIdentity, extractWebSocketIdentity } from './identity.js'

const LED_PANEL_ID = 'led-blinky'
const WS_PATH = '/api/local/led/ws'
const MAX_LOG_ENTRIES = 200

const connectionLog = []
const activeConnections = new Map()

const recordEvent = (event) => {
  const entry = {
    timestamp: new Date().toISOString(),
    ...event
  }
  connectionLog.push(entry)
  if (connectionLog.length > MAX_LOG_ENTRIES) {
    connectionLog.shift()
  }
}

const buildBackendWebSocketUrl = () => {
  const target = process.env.FASTAPI_URL
  if (!target) return ''
  try {
    const url = new URL(target)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.pathname = '/api/local/led/ws'
    url.search = ''
    url.hash = ''
    return url.toString()
  } catch {
    return ''
  }
}

const getHardwareTarget = () => process.env.LED_HARDWARE_WS_URL || buildBackendWebSocketUrl()

const safeSend = (socket, payload) => {
  try {
    const OPEN_STATE = typeof socket.OPEN === 'number' ? socket.OPEN : WebSocket.OPEN
    if (socket.readyState === OPEN_STATE) {
      socket.send(JSON.stringify(payload))
    }
  } catch (err) {
    console.error('[LED WS] Failed to send payload', err)
  }
}

const cleanupConnection = (connectionId, reason = 'unknown') => {
  const entry = activeConnections.get(connectionId)
  if (!entry) return

  const { client, target } = entry
  if (client && client.readyState === WebSocket.OPEN) {
    client.close(1000, 'Gateway cleanup')
  }
  if (target && target.readyState === WebSocket.OPEN) {
    target.close(1000, reason)
  }

  activeConnections.delete(connectionId)
  recordEvent({
    type: 'disconnect',
    connectionId,
    deviceId: entry.deviceId,
    panel: entry.panel,
    source: reason
  })
}

export const closeLedConnection = (connectionId, reason = 'client_requested') => {
  const entry = activeConnections.get(connectionId)
  if (!entry) return false
  recordEvent({
    type: 'close_request',
    connectionId,
    deviceId: entry.deviceId,
    panel: entry.panel,
    reason
  })
  cleanupConnection(connectionId, reason)
  return true
}

export const getLedWebSocketStatus = () => {
  return {
    ws: {
      url: WS_PATH,
      panel: LED_PANEL_ID,
      target: getHardwareTarget() || null
    },
    active_connections: Array.from(activeConnections.values()).map((entry) => ({
      id: entry.id,
      deviceId: entry.deviceId,
      panel: entry.panel,
      connected_at: entry.connectedAt,
      mode: entry.mode,
      status: entry.status
    })),
    log: [...connectionLog],
    updated_at: new Date().toISOString()
  }
}

export const setupLEDWebSocket = (wss) => {
  wss.on('connection', (client, req) => {
    const identity = extractWebSocketIdentity(req, {
      defaultPanel: LED_PANEL_ID,
      corrPrefix: 'led'
    })
    const { url } = identity
    if (url.pathname !== WS_PATH) {
      return
    }

    if (!ensureDeviceIdentity(client, identity, { channel: 'led websocket' })) {
      return
    }

    const connectionId = randomUUID()

    const hardwareTarget = getHardwareTarget()
    const mode = hardwareTarget ? 'proxy' : 'mock'

    const state = {
      id: connectionId,
      client,
      target: null,
      deviceId: identity.deviceId,
      panel: identity.panel,
      connectedAt: new Date().toISOString(),
      mode,
      status: 'connecting',
      corrId: identity.corrId
    }

    activeConnections.set(connectionId, state)
    recordEvent({
      type: 'connect',
      connectionId,
      deviceId: identity.deviceId,
      panel: identity.panel,
      mode
    })

    safeSend(client, {
      type: 'gateway_status',
      connectionId,
      mode,
      device: identity.deviceId,
      panel: identity.panel,
      corr_id: identity.corrId
    })

    if (hardwareTarget) {
      const target = new WebSocket(hardwareTarget, {
        headers: buildIdentityHeaders(identity)
      })

      state.target = target

      target.on('open', () => {
        state.status = 'connected'
        safeSend(client, { type: 'gateway_notice', status: 'proxy_connected' })
        recordEvent({
          type: 'proxy_connected',
          connectionId,
          deviceId: identity.deviceId,
          panel: identity.panel,
          target: hardwareTarget
        })
      })

      target.on('message', (data, isBinary) => {
        if (client.readyState === WebSocket.OPEN) {
          client.send(data, { binary: isBinary })
        }
      })

      target.on('close', (code, reason) => {
        safeSend(client, {
          type: 'gateway_notice',
          status: 'proxy_closed',
          code,
          reason: reason?.toString()
        })
        cleanupConnection(connectionId, 'hardware_closed')
      })

      target.on('error', (err) => {
        console.error('[LED WS] Hardware proxy error:', err)
        safeSend(client, {
          type: 'gateway_error',
          message: err?.message || 'Hardware proxy error'
        })
        cleanupConnection(connectionId, 'hardware_error')
      })
    } else {
      state.status = 'mock'
      safeSend(client, {
        type: 'gateway_notice',
        status: 'mock_mode',
        message: 'LED_HARDWARE_WS_URL not configured; running in mock mode.'
      })
    }

    client.on('message', (data, isBinary) => {
      const entry = activeConnections.get(connectionId)
      if (!entry) return

      if (entry.target && entry.target.readyState === WebSocket.OPEN) {
        entry.target.send(data, { binary: isBinary })
      } else {
        recordEvent({
          type: 'mock_message',
          connectionId,
          payload_preview: data?.toString()?.slice(0, 200)
        })
        safeSend(client, {
          type: 'mock_ack',
          received_bytes: typeof data === 'string' ? data.length : data?.byteLength || 0
        })
      }
    })

    client.on('close', (code, reason) => {
      recordEvent({
        type: 'client_closed',
        connectionId,
        code,
        reason: reason?.toString()
      })
      cleanupConnection(connectionId, 'client_closed')
    })

    client.on('error', (err) => {
      console.error('[LED WS] Client error:', err)
      recordEvent({
        type: 'client_error',
        connectionId,
        message: err?.message || 'Unknown client error'
      })
      cleanupConnection(connectionId, 'client_error')
    })
  })

  console.log('[LED WS] Gateway WebSocket bridge ready')
}
