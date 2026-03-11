import express from 'express'
import { randomUUID } from 'crypto'

import { getLedWebSocketStatus, closeLedConnection } from '../ws/led.js'

const router = express.Router()

const LED_PANEL_ID = 'led-blinky'
const VALID_SCOPES = ['config', 'state', 'backup', 'local']

const ensureCorrelationId = (req, res, next) => {
  if (!req.headers['x-corr-id']) {
    req.headers['x-corr-id'] = randomUUID()
  }
  next()
}

const enforceScopeHeader = (req, res, next) => {
  const mutating = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(req.method.toUpperCase())
  if (!mutating) {
    return next()
  }

  const scope = req.headers['x-scope']
  if (!scope) {
    return res.status(400).json({
      error: 'missing_scope_header',
      message: 'Mutating LED operations require x-scope header (config|state|backup)'
    })
  }

  if (!VALID_SCOPES.includes(scope)) {
    return res.status(400).json({
      error: 'invalid_scope_header',
      message: `x-scope must be one of: ${VALID_SCOPES.join('|')}`
    })
  }

  next()
}

const enforceDeviceHeaders = (req, res, next) => {
  const deviceId = req.headers['x-device-id']
  if (!deviceId) {
    return res.status(400).json({
      error: 'missing_device_id',
      message: 'x-device-id header is required for LED operations'
    })
  }

  req.headers['x-panel'] = req.headers['x-panel'] || LED_PANEL_ID
  next()
}

const requireConfigScope = (req, res, next) => {
  if ((req.headers['x-scope'] || '').toLowerCase() !== 'config') {
    return res.status(403).json({
      error: 'forbidden_scope',
      message: 'This operation requires x-scope=config'
    })
  }
  next()
}

const requireScopeValue = (expected) => (req, res, next) => {
  if ((req.headers['x-scope'] || '').toLowerCase() !== expected) {
    return res.status(403).json({
      error: 'forbidden_scope',
      message: `This operation requires x-scope=${expected}`
    })
  }
  next()
}

const buildForwardHeaders = (req) => {
  const headers = {
    'Content-Type': req.headers['content-type'],
    'x-scope': req.headers['x-scope'],
    'x-device-id': req.headers['x-device-id'],
    'x-panel': req.headers['x-panel'] || LED_PANEL_ID,
    'x-corr-id': req.headers['x-corr-id'] || randomUUID(),
    Authorization: req.headers['authorization']
  }

  Object.keys(headers).forEach((key) => {
    if (!headers[key]) {
      delete headers[key]
    }
  })

  return headers
}

const proxyToFastAPI = async (req, res, overridePath = null) => {
  try {
    const fastapiUrl = req.app.locals.fastapiUrl
    if (!fastapiUrl) {
      throw new Error('FastAPI URL not configured')
    }

    const targetUrl = new URL(overridePath || req.originalUrl, fastapiUrl).toString()
    const headers = buildForwardHeaders(req)

    const requestOptions = {
      method: req.method,
      headers
    }

    if (['POST', 'PUT', 'PATCH'].includes(req.method.toUpperCase()) && req.body) {
      requestOptions.body = JSON.stringify(req.body)
      headers['Content-Type'] = 'application/json'
    }

    const response = await fetch(targetUrl, requestOptions)
    const contentType = response.headers.get('content-type')
    res.status(response.status)

    if (contentType && contentType.includes('application/json')) {
      const data = await response.json()
      res.json(data)
    } else {
      const text = await response.text()
      res.send(text)
    }
  } catch (err) {
    console.error('LED proxy error:', err)
    if (err.code === 'ECONNREFUSED') {
      res.status(503).json({
        error: 'fastapi_unavailable',
        message: 'LED service is unavailable'
      })
    } else {
      res.status(500).json({
        error: 'led_proxy_error',
        message: err.message
      })
    }
  }
}

router.use(ensureCorrelationId)

router.get(
  '/channels',
  enforceDeviceHeaders,
  requireScopeValue('state'),
  (req, res) => {
    proxyToFastAPI(req, res)
  }
)

router.post(
  '/channels/preview',
  enforceScopeHeader,
  enforceDeviceHeaders,
  requireConfigScope,
  (req, res) => {
    proxyToFastAPI(req, res)
  }
)

router.post(
  '/channels/apply',
  enforceScopeHeader,
  enforceDeviceHeaders,
  requireConfigScope,
  (req, res) => {
    proxyToFastAPI(req, res)
  }
)

router.delete(
  '/channels/:logical_button',
  enforceScopeHeader,
  enforceDeviceHeaders,
  requireConfigScope,
  (req, res) => {
    proxyToFastAPI(req, res)
  }
)

router.post(
  '/calibrate/start',
  enforceScopeHeader,
  enforceDeviceHeaders,
  requireConfigScope,
  (req, res) => proxyToFastAPI(req, res)
)

router.post(
  '/calibrate/assign',
  enforceScopeHeader,
  enforceDeviceHeaders,
  requireConfigScope,
  (req, res) => proxyToFastAPI(req, res)
)

router.post(
  '/calibrate/flash',
  enforceScopeHeader,
  enforceDeviceHeaders,
  requireConfigScope,
  (req, res) => proxyToFastAPI(req, res)
)

router.post(
  '/calibrate/stop',
  enforceScopeHeader,
  enforceDeviceHeaders,
  requireConfigScope,
  (req, res) => proxyToFastAPI(req, res)
)

router.get('/game-profile', enforceDeviceHeaders, (req, res) => {
  proxyToFastAPI(req, res)
})

router.get('/game-profiles', enforceDeviceHeaders, (req, res) => {
  proxyToFastAPI(req, res)
})

router.post('/game-profile/preview', enforceScopeHeader, enforceDeviceHeaders, (req, res) => {
  proxyToFastAPI(req, res)
})

router.post(
  '/game-profile/apply',
  enforceScopeHeader,
  enforceDeviceHeaders,
  requireConfigScope,
  (req, res) => {
    proxyToFastAPI(req, res)
  }
)

router.delete(
  '/game-profile',
  enforceScopeHeader,
  enforceDeviceHeaders,
  requireConfigScope,
  (req, res) => {
    proxyToFastAPI(req, res)
  }
)

router.post('/profile/preview', enforceScopeHeader, enforceDeviceHeaders, (req, res) => {
  proxyToFastAPI(req, res)
})

router.post(
  '/profile/apply',
  enforceScopeHeader,
  enforceDeviceHeaders,
  requireConfigScope,
  (req, res) => {
    proxyToFastAPI(req, res)
  }
)

router.post('/test', enforceScopeHeader, enforceDeviceHeaders, (req, res) => {
  proxyToFastAPI(req, res)
})

router.get('/devices', enforceDeviceHeaders, (req, res) => {
  proxyToFastAPI(req, res)
})

router.get('/status', enforceDeviceHeaders, async (req, res) => {
  req.headers['x-scope'] = req.headers['x-scope'] || 'state'
  const gatewayStatus = getLedWebSocketStatus()
  const payload = {
    service: 'led-blinky',
    ws: gatewayStatus.ws,
    connections: gatewayStatus.active_connections,
    log: gatewayStatus.log,
    updated_at: gatewayStatus.updated_at
  }

  try {
    const fastapiUrl = req.app.locals.fastapiUrl
    if (!fastapiUrl) {
      throw new Error('FastAPI URL not configured')
    }
    const targetUrl = new URL(req.originalUrl, fastapiUrl).toString()
    const headers = buildForwardHeaders(req)
    const response = await fetch(targetUrl, { method: 'GET', headers })
    if (response.ok) {
      const runtimeStatus = await response.json()
      payload.runtime = runtimeStatus
      if (runtimeStatus?.engine) {
        payload.engine = runtimeStatus.engine
      }
    } else {
      payload.backend_error = `fastapi_status_${response.status}`
      payload.backend_error_detail = await response.text()
    }
  } catch (err) {
    payload.backend_error = err?.message || 'led_status_unavailable'
  }

  res.json(payload)
})

router.get('/engine-health', enforceDeviceHeaders, (req, res) => {
  req.headers['x-scope'] = req.headers['x-scope'] || 'state'
  proxyToFastAPI(req, res)
})

router.post(
  '/diagnostics/channel-test',
  enforceScopeHeader,
  enforceDeviceHeaders,
  requireScopeValue('state'),
  (req, res) => proxyToFastAPI(req, res)
)

// -----------------------------------------------------------------------------
// Blinky game events (forwarded to FastAPI)
// -----------------------------------------------------------------------------
router.post(
  '/blinky/game-selected',
  enforceScopeHeader,
  enforceDeviceHeaders,
  (req, res) => proxyToFastAPI(req, res)
)

router.post(
  '/blinky/game-launch',
  enforceScopeHeader,
  enforceDeviceHeaders,
  (req, res) => proxyToFastAPI(req, res)
)

router.get('/ws', enforceDeviceHeaders, (req, res) => {
  const status = getLedWebSocketStatus()
  res.json({
    status: 'ready',
    ws: status.ws,
    connections: status.active_connections
  })
})

router.post('/ws', enforceScopeHeader, enforceDeviceHeaders, (req, res) => {
  const action = req.body?.action
  if (action === 'disconnect') {
    const connectionId = req.body?.connectionId
    if (!connectionId) {
      return res.status(400).json({
        error: 'missing_connection_id',
        message: 'connectionId is required to disconnect a session'
      })
    }
    const closed = closeLedConnection(connectionId, 'api_disconnect')
    if (!closed) {
      return res.status(404).json({
        error: 'connection_not_found',
        message: `No active LED WebSocket found for ${connectionId}`
      })
    }
    return res.json({ status: 'disconnected', connectionId })
  }

  return res.status(400).json({
    error: 'invalid_action',
    message: 'Supported actions: disconnect'
  })
})

router.use('/', enforceScopeHeader, enforceDeviceHeaders, (req, res) => {
  proxyToFastAPI(req, res)
})

export default router
