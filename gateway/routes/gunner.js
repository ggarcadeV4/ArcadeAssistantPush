import express from 'express'
import { randomUUID } from 'crypto'
import { Readable } from 'stream'

const router = express.Router()

const PANEL_ID = 'gunner'
const VALID_SCOPES = ['state', 'config', 'backup', 'local']

const ensureCorrelationId = (req, res, next) => {
  if (!req.headers['x-corr-id']) {
    req.headers['x-corr-id'] = randomUUID()
  }
  next()
}

const enforceDeviceHeaders = (req, res, next) => {
  const deviceId = req.headers['x-device-id']
  if (!deviceId) {
    return res.status(400).json({
      error: 'missing_device_id',
      message: 'x-device-id header is required for gunner operations'
    })
  }
  req.headers['x-panel'] = req.headers['x-panel'] || PANEL_ID
  next()
}

const ensureScopeDefault = (req, res, next) => {
  if (!req.headers['x-scope']) {
    req.headers['x-scope'] = 'state'
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
      message: `Mutating operations require x-scope header (${VALID_SCOPES.join('|')})`
    })
  }
  if (!VALID_SCOPES.includes(scope.toLowerCase())) {
    return res.status(400).json({
      error: 'invalid_scope_header',
      message: `x-scope must be one of: ${VALID_SCOPES.join('|')}`
    })
  }
  next()
}

const buildForwardHeaders = (req) => {
  const headers = {
    'Content-Type': req.headers['content-type'],
    'x-scope': req.headers['x-scope'],
    'x-device-id': req.headers['x-device-id'],
    'x-panel': req.headers['x-panel'] || PANEL_ID,
    'x-corr-id': req.headers['x-corr-id'] || randomUUID(),
    Accept: req.headers['accept'],
    Authorization: req.headers['authorization']
  }

  Object.keys(headers).forEach((key) => {
    if (!headers[key]) {
      delete headers[key]
    }
  })

  return headers
}

const streamResponse = (response, res) => {
  res.status(response.status)
  res.setHeader('Content-Type', 'text/event-stream')
  res.setHeader('Cache-Control', 'no-cache')
  res.setHeader('Connection', 'keep-alive')

  const readable = response.body ? Readable.fromWeb(response.body) : null
  if (!readable) {
    return res.end()
  }

  readable.on('data', (chunk) => {
    res.write(chunk)
  })

  readable.on('end', () => {
    res.end()
  })

  readable.on('error', (err) => {
    console.error('Gunner SSE proxy error:', err)
    if (!res.headersSent) {
      res.status(500)
    }
    res.end()
  })
}

const proxyToFastAPI = async (req, res, { stream = false } = {}) => {
  try {
    const fastapiUrl = req.app.locals.fastapiUrl
    if (!fastapiUrl) {
      throw new Error('FastAPI URL not configured')
    }
    const targetUrl = new URL(req.originalUrl, fastapiUrl).toString()
    const headers = buildForwardHeaders(req)
    const controller = new AbortController()

    req.on('close', () => {
      controller.abort()
    })

    const requestOptions = {
      method: req.method,
      headers,
      signal: controller.signal
    }

    if (['POST', 'PUT', 'PATCH'].includes(req.method.toUpperCase()) && req.body) {
      requestOptions.body = JSON.stringify(req.body)
      headers['Content-Type'] = 'application/json'
    }

    const response = await fetch(targetUrl, requestOptions)
    const contentType = response.headers.get('content-type') || ''

    if (stream && contentType.includes('text/event-stream')) {
      return streamResponse(response, res)
    }

    res.status(response.status)
    response.headers.forEach((value, key) => {
      res.setHeader(key, value)
    })

    if (contentType.includes('application/json')) {
      const data = await response.json()
      return res.json(data)
    }

    const text = await response.text()
    return res.send(text)
  } catch (err) {
    if (err.name === 'AbortError') {
      return
    }
    console.error('Gunner proxy error:', err)
    if (err.code === 'ECONNREFUSED') {
      return res.status(503).json({
        error: 'fastapi_unavailable',
        message: 'FastAPI service is not running'
      })
    }
    return res.status(500).json({
      error: 'proxy_error',
      message: err?.message || 'Unknown proxy error'
    })
  }
}

const sharedMiddleware = [ensureCorrelationId, ensureScopeDefault, enforceScopeHeader, enforceDeviceHeaders]

router.get('/devices', sharedMiddleware, (req, res) => proxyToFastAPI(req, res))
router.get('/profiles', sharedMiddleware, (req, res) => proxyToFastAPI(req, res))

router.post('/calibrate', sharedMiddleware, (req, res) => proxyToFastAPI(req, res))
router.post('/calibrate/point', sharedMiddleware, (req, res) => proxyToFastAPI(req, res))
router.post('/calibrate/stream', sharedMiddleware, (req, res) => {
  req.headers['accept'] = req.headers['accept'] || 'text/event-stream'
  req.setTimeout(0)
  return proxyToFastAPI(req, res, { stream: true })
})

router.post('/profile/save', sharedMiddleware, (req, res) => proxyToFastAPI(req, res))
router.post('/profile/load', sharedMiddleware, (req, res) => proxyToFastAPI(req, res))
router.post('/profile/apply', sharedMiddleware, (req, res) => proxyToFastAPI(req, res))

router.post('/tendencies/preview', sharedMiddleware, (req, res) => proxyToFastAPI(req, res))
router.post('/tendencies/apply', sharedMiddleware, (req, res) => proxyToFastAPI(req, res))
router.post('/test', sharedMiddleware, (req, res) => proxyToFastAPI(req, res))

router.use('/', sharedMiddleware, (req, res) => proxyToFastAPI(req, res))

export default router
