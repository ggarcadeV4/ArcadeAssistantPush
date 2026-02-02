import express from 'express';

const router = express.Router();

function getFastapiBase(req) {
  const base = req.app?.locals?.fastapiUrl || process.env.FASTAPI_URL;
  if (!base) {
    throw new Error('FastAPI URL not configured on gateway');
  }
  return base;
}

function forwardHeaders(req, { contentType } = {}) {
  const headers = {
    'x-device-id': req.headers['x-device-id'] || 'cabinet-001',
    'x-panel': req.headers['x-panel'] || 'launchbox',
    'x-scope': req.headers['x-scope'] || 'state',
  };
  if (req.headers['x-corr-id']) {
    headers['x-corr-id'] = req.headers['x-corr-id'];
  }
  if (contentType) {
    headers['Content-Type'] = contentType;
  }
  return headers;
}

router.get('/games', async (req, res) => {
  try {
    const fastapiBase = getFastapiBase(req);
    const qs = new URLSearchParams(req.query).toString();
    const url = `${fastapiBase}/api/local/launchbox/games${qs ? `?${qs}` : ''}`;
    const response = await fetch(url, {
      headers: forwardHeaders(req),
    });
    const payload = await response.json();
    res.status(response.status).json(payload);
  } catch (err) {
    console.error('[LaunchBox Local] /games proxy failed:', err);
    res.status(502).json({ error: 'launchbox_proxy_failed', detail: String(err?.message || err) });
  }
});

router.get('/random', async (req, res) => {
  try {
    const fastapiBase = getFastapiBase(req);
    const qs = new URLSearchParams(req.query).toString();
    const url = `${fastapiBase}/api/local/launchbox/random${qs ? `?${qs}` : ''}`;
    const response = await fetch(url, {
      headers: forwardHeaders(req),
    });
    const payload = await response.json();
    res.status(response.status).json(payload);
  } catch (err) {
    console.error('[LaunchBox Local] /random proxy failed:', err);
    res.status(502).json({ error: 'launchbox_proxy_failed', detail: String(err?.message || err) });
  }
});

router.post('/play', async (req, res) => {
  try {
    const fastapiBase = getFastapiBase(req);
    // Side-effect operation — do NOT use fetchWithRetry (spawns emulator)
    const response = await fetch(`${fastapiBase}/api/local/launchbox/play`, {
      method: 'POST',
      headers: forwardHeaders(req, { contentType: 'application/json' }),
      body: JSON.stringify(req.body || {}),
    });
    const payload = await response.json();
    res.status(response.status).json(payload);
  } catch (err) {
    console.error('[LaunchBox Local] /play proxy failed:', err);
    res.status(502).json({ error: 'launchbox_proxy_failed', detail: String(err?.message || err) });
  }
});

export default router;
