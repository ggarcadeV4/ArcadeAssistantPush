// gateway/routes/config.js
// Endpoints:
//  POST /api/local/config/preview  (x-scope: config) -> {changed, preview, wrote:false}
//  POST /api/local/config/apply    (x-scope: config) -> {changed, backupPath, wrote:true}
//  GET  /api/local/config/backups  (x-scope: config) -> {backups: string[]}
//  POST /api/local/config/revert   (x-scope: config) -> {restoredFrom}
// Guardrails: per-panel whitelist, dated backups /backups/YYYYMMDD, JSONL changelog, x-device-id logging.

// Pure proxy - no local file operations
// All config/backup operations delegated to FastAPI backend

// Removed all local directory operations - gateway is pure proxy
// All backup management handled by FastAPI backend

function requireScopeConfig(req, res) {
  const scope = req.header('x-scope')
  if (scope !== 'config') {
    res.status(400).json({ code:'BAD_REQUEST', message:'x-scope=config required' })
    return false
  }
  return true
}

export default function registerConfigRoutes(app) {
  const fwd = async (path, req, body, scopeOverride) => {
    const url = `${process.env.FASTAPI_URL}${path}`
    const headers = {
      'content-type': 'application/json',
      'x-scope': scopeOverride || (req.headers['x-scope'] || 'config'),
      'x-device-id': req.headers['x-device-id'] || ''
    }
    return fetch(url, { method: 'POST', headers, body: JSON.stringify(body) })
  }

  // Proxy: Preview (no write at gateway)
  app.post('/api/local/config/preview', async (req, res) => {
    try {
      const r = await fwd('/config/preview', req, req.body)
      res.status(r.status).send(await r.text())
    } catch (e) {
      res.status(502).json({ code:'BAD_GATEWAY', message: String(e?.message || e) })
    }
  })

  // Proxy: Apply (writes handled by FastAPI)
  app.post('/api/local/config/apply', async (req, res) => {
    try {
      const r = await fwd('/config/apply', req, req.body)
      res.status(r.status).send(await r.text())
    } catch (e) {
      res.status(502).json({ code:'BAD_GATEWAY', message: String(e?.message || e) })
    }
  })

  // Proxy: List backups (handled by FastAPI)
  app.get('/api/local/config/backups', async (req, res) => {
    try {
      const url = `${process.env.FASTAPI_URL}/config/backups?${new URLSearchParams(req.query).toString()}`
      const headers = {
        'x-scope': req.headers['x-scope'] || 'config',
        'x-device-id': req.headers['x-device-id'] || ''
      }
      const r = await fetch(url, { method: 'GET', headers })
      res.status(r.status).send(await r.text())
    } catch (e) {
      res.status(502).json({ code:'BAD_GATEWAY', message: String(e?.message || e) })
    }
  })

  // Proxy: Restore (handled by FastAPI)
  app.post('/api/local/config/revert', async (req, res) => {
    try {
      const r = await fwd('/config/restore', req, req.body, 'backup')
      res.status(r.status).send(await r.text())
    } catch (e) {
      res.status(502).json({ code:'BAD_GATEWAY', message: String(e?.message || e) })
    }
  })
}
