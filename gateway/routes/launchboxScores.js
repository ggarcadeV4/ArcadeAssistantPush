import express from 'express'

const router = express.Router()

// Proxy scores endpoints to FastAPI backend instead of LaunchBox plugin
async function proxyToBackend(req, res, path) {
  try {
    const fastapiUrl = req.app.locals.fastapiUrl || 'http://127.0.0.1:8888'
    // Backend mounts scorekeeper under /api/local/scorekeeper
    const url = `${fastapiUrl}/api/local/scorekeeper${path}`

    const headers = {
      'x-device-id': req.headers['x-device-id'] || 'CAB-0001',
      'x-panel': req.headers['x-panel'] || 'scorekeeper',
      'x-scope': req.headers['x-scope'] || 'local',
      'content-type': 'application/json'
    }

    const opts = { method: req.method, headers }
    if (req.method !== 'GET' && req.body) {
      opts.body = JSON.stringify(req.body)
    }

    const response = await fetch(url, opts)
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
    console.error('[scores-proxy] Backend error:', err)
    res.status(503).json({
      success: false,
      error: 'backend_unavailable',
      message: 'Scorekeeper service temporarily unavailable'
    })
  }
}

router.get('/by-game', async (req, res) => {
  const q = req.originalUrl.split('?')[1] || ''
  return proxyToBackend(req, res, `/by-game?${q}`)
})

router.get('/leaderboard', async (req, res) => {
  const q = req.originalUrl.split('?')[1] || ''
  return proxyToBackend(req, res, `/leaderboard?${q}`)
})

router.post('/submit', async (req, res) => {
  return proxyToBackend(req, res, '/submit/apply')
})

router.post('/events/launch-start', async (req, res) => {
  return proxyToBackend(req, res, '/events/launch-start')
})

router.post('/events/launch-end', async (req, res) => {
  return proxyToBackend(req, res, '/events/launch-end')
})

export default router
