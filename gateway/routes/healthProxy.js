import express from 'express';

const router = express.Router();

function getFastapiBase(req) {
  const base = req.app?.locals?.fastapiUrl || process.env.FASTAPI_URL;
  if (!base) {
    throw new Error('FastAPI URL not configured on gateway');
  }
  return base;
}

function buildHeaders(req, scope = 'state', isPost = false) {
  const headers = {};
  const incomingContentType = req.headers['content-type'];
  if (incomingContentType) {
    headers['content-type'] = incomingContentType;
  } else if (isPost) {
    headers['content-type'] = 'application/json';
  }
  if (req.headers['x-device-id']) headers['x-device-id'] = req.headers['x-device-id'];
  if (req.headers['x-panel']) headers['x-panel'] = req.headers['x-panel'];
  else headers['x-panel'] = 'doc';
  headers['x-scope'] = req.headers['x-scope'] || scope;
  if (req.headers['x-corr-id']) headers['x-corr-id'] = req.headers['x-corr-id'];
  return headers;
}

async function proxyRequest(req, res, path, options = {}) {
  const { method = 'GET', scope = 'state' } = options;
  const upperMethod = method.toUpperCase();
  const isPost = upperMethod !== 'GET';
  try {
    const fastapiBase = getFastapiBase(req);
    const url = new URL(path, fastapiBase).toString();
    const headers = buildHeaders(req, scope, isPost);
    const fetchOptions = { method: upperMethod, headers };
    if (isPost) {
      fetchOptions.body = JSON.stringify(req.body ?? {});
    }
    const response = await fetch(url, fetchOptions);
    const bodyText = await response.text();
    res.status(response.status);
    try {
      res.json(JSON.parse(bodyText));
    } catch {
      res.send(bodyText);
    }
  } catch (err) {
    console.error('[HealthProxy] request failed:', err);
    res.status(502).json({
      error: 'health_proxy_failed',
      detail: err?.message || String(err),
    });
  }
}

router.get('/summary', (req, res) => proxyRequest(req, res, '/health/summary'));
router.get('/performance', (req, res) => proxyRequest(req, res, '/health/performance'));
router.get('/performance/timeseries', (req, res) =>
  proxyRequest(req, res, '/health/performance/timeseries'),
);
router.get('/processes', (req, res) => proxyRequest(req, res, '/health/processes'));
router.get('/hardware', (req, res) => proxyRequest(req, res, '/health/hardware'));
router.get('/alerts/active', (req, res) => proxyRequest(req, res, '/health/alerts/active'));
router.get('/alerts/history', (req, res) => proxyRequest(req, res, '/health/alerts/history'));
router.post('/alerts/:alertId/dismiss', (req, res) =>
  proxyRequest(req, res, `/health/alerts/${req.params.alertId}/dismiss`, { method: 'POST' }),
);
router.post('/actions/optimize', (req, res) =>
  proxyRequest(req, res, '/health/actions/optimize', { method: 'POST' }),
);

export default router;

