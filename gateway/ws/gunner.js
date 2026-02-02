import { WebSocket } from 'ws'
import { randomUUID } from 'crypto'

const WS_PATH = '/api/local/gunner/ws'

const buildBackendUrl = () => {
  const target = process.env.FASTAPI_URL
  if (!target) return null
  try {
    const url = new URL(target)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.pathname = WS_PATH
    url.search = ''
    url.hash = ''
    return url.toString()
  } catch (err) {
    console.error('[Gunner WS] Invalid FASTAPI_URL:', err)
    return null
  }
}

export const setupGunnerWebSocket = (wss) => {
  const backendBase = buildBackendUrl()
  if (!backendBase) {
    console.warn('[Gunner WS] FASTAPI_URL not configured; WebSocket bridge disabled')
    return
  }

  wss.on('connection', (client, req) => {
    const url = new URL(req.url, `http://${req.headers.host}`)
    if (url.pathname !== WS_PATH) {
      return
    }

    const corrId = url.searchParams.get('corr_id') || randomUUID()
    const deviceId = url.searchParams.get('device') || req.headers['x-device-id'] || 'unknown'
    const backendUrl = new URL(backendBase)
    backendUrl.search = url.search

    const bridge = new WebSocket(backendUrl.toString(), {
      headers: {
        'x-device-id': deviceId,
        'x-panel': 'gunner',
        'x-corr-id': corrId,
        'x-scope': req.headers['x-scope'] || 'state'
      }
    })

    const safeClose = (code, reason) => {
      try {
        if (client.readyState === WebSocket.OPEN) {
          client.close(code, reason)
        }
      } catch {}
      try {
        if (bridge.readyState === WebSocket.OPEN) {
          bridge.close(code, reason)
        }
      } catch {}
    }

    bridge.on('open', () => {
      if (client.readyState === WebSocket.OPEN) {
        client.send(JSON.stringify({ type: 'gateway_notice', status: 'gunner_proxy_connected' }))
      }
    })

    bridge.on('message', (data, isBinary) => {
      if (client.readyState === WebSocket.OPEN) {
        client.send(data, { binary: isBinary })
      }
    })

    bridge.on('close', (code, reason) => {
      safeClose(code, reason?.toString() || 'backend_closed')
    })

    bridge.on('error', (err) => {
      console.error('[Gunner WS] Backend error:', err)
      if (client.readyState === WebSocket.OPEN) {
        client.send(JSON.stringify({ type: 'gateway_error', message: err?.message || 'backend_error' }))
      }
      safeClose(1011, 'backend_error')
    })

    client.on('message', (data, isBinary) => {
      if (bridge.readyState === WebSocket.OPEN) {
        bridge.send(data, { binary: isBinary })
      }
    })

    client.on('close', (code, reason) => {
      safeClose(code, reason?.toString() || 'client_closed')
    })

    client.on('error', (err) => {
      console.error('[Gunner WS] Client error:', err)
      safeClose(1011, 'client_error')
    })
  })

  console.log('[Gunner WS] Gateway WebSocket bridge ready')
}
