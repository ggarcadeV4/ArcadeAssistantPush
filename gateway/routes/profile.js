import express from 'express'

const router = express.Router()

function rid() {
  return Math.random().toString(16).slice(2, 10)
}

async function proxy(req, res, path, method = 'GET') {
  try {
    const backendUrl = req.app.locals.fastapiUrl || process.env.FASTAPI_URL || 'http://127.0.0.1:8000';
    const url = `${backendUrl}${path}`
    const headers = { 'content-type': 'application/json' }
    // Forward scope/panel/device headers for auditing/policy
    if (req.headers['x-scope']) headers['x-scope'] = req.headers['x-scope']
    if (req.headers['x-device-id']) headers['x-device-id'] = req.headers['x-device-id']
    if (req.headers['x-panel']) headers['x-panel'] = req.headers['x-panel']
    if (req.headers['x-corr-id']) headers['x-corr-id'] = req.headers['x-corr-id']
    const opts = { method, headers }
    if (method !== 'GET' && req.body) opts.body = JSON.stringify(req.body)
    const r = await fetch(url, opts)
    const text = await r.text()
    if (!r.ok) {
      return res.status(r.status).send(text)
    }
    try { return res.json(JSON.parse(text)) } catch { return res.send(text) }
  } catch (e) {
    const id = req.headers['x-request-id'] || rid()
    console.warn(`[profile-proxy] error id=${id} path=${path} ${e?.message || e}`)
    return res.status(500).json({ error: 'proxy_error' })
  }
}

// Profile
router.get('/profile', (req, res) => proxy(req, res, '/profile', 'GET'))
router.post('/profile/preview', (req, res) => proxy(req, res, '/profile/preview', 'POST'))
router.post('/profile/apply', (req, res) => proxy(req, res, '/profile/apply', 'POST'))

// Consent
router.get('/consent', (req, res) => proxy(req, res, '/consent', 'GET'))
router.post('/consent/preview', (req, res) => proxy(req, res, '/consent/preview', 'POST'))
router.post('/consent/apply', (req, res) => proxy(req, res, '/consent/apply', 'POST'))

export default router

