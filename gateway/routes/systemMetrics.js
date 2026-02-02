import express from 'express';

const router = express.Router();

function getFastapiBase(req) {
  const base = req.app?.locals?.fastapiUrl || process.env.FASTAPI_URL;
  if (!base) {
    throw new Error('FastAPI URL not configured on gateway');
  }
  return base;
}

function buildHeaders(req) {
  const headers = {
    'x-device-id': req.headers['x-device-id'] || 'system-health',
    'x-panel': req.headers['x-panel'] || 'system-health',
    'x-scope': req.headers['x-scope'] || 'state'
  };
  if (req.headers['x-corr-id']) {
    headers['x-corr-id'] = req.headers['x-corr-id'];
  }
  return headers;
}

router.get('/metrics', async (req, res) => {
  try {
    const fastapiBase = getFastapiBase(req);
    const url = `${fastapiBase}/api/system/metrics`;
    const response = await fetch(url, { headers: buildHeaders(req) });

    const bodyText = await response.text();
    res.status(response.status);
    try {
      res.json(JSON.parse(bodyText));
    } catch {
      res.send(bodyText);
    }
  } catch (err) {
    console.error('[System Metrics] proxy failed:', err);
    res.status(502).json({
      error: 'system_metrics_proxy_failed',
      detail: String(err?.message || err)
    });
  }
});

export default router;
