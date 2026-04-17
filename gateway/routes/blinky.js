import express from 'express'
import { randomUUID } from 'crypto'

const router = express.Router()

const BLINKY_PANEL_ID = 'led-blinky'
const VALID_SCOPES = ['config', 'state', 'backup', 'local']

const ensureCorrelationId = (req, _res, next) => {
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
      message: 'Mutating blinky operations require x-scope header (config|state|backup)'
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
      message: 'x-device-id header is required for blinky operations'
    })
  }

  req.headers['x-panel'] = req.headers['x-panel'] || BLINKY_PANEL_ID
  next()
}

const buildForwardHeaders = (req) => {
  const headers = {
    'Content-Type': req.headers['content-type'],
    'x-scope': req.headers['x-scope'],
    'x-device-id': req.headers['x-device-id'],
    'x-panel': req.headers['x-panel'] || BLINKY_PANEL_ID,
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

const proxyToFastAPI = async (req, res) => {
  try {
    const fastapiUrl = req.app.locals.fastapiUrl
    if (!fastapiUrl) {
      throw new Error('FastAPI URL not configured')
    }

    const backendPath = req.originalUrl.replace('/api/local/blinky', '/api/local/led/blinky')
    const targetUrl = new URL(backendPath, fastapiUrl).toString()
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
    console.error('Blinky proxy error:', err)
    if (err.code === 'ECONNREFUSED') {
      res.status(503).json({
        error: 'fastapi_unavailable',
        message: 'Blinky service is unavailable'
      })
    } else {
      res.status(500).json({
        error: 'blinky_proxy_error',
        message: err.message
      })
    }
  }
}

router.use(ensureCorrelationId)
router.use('/', enforceScopeHeader, enforceDeviceHeaders, (req, res) => {
  proxyToFastAPI(req, res)
})

export default router
