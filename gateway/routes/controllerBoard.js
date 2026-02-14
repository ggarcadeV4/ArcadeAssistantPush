import express from 'express';

const router = express.Router();

function ensureHeaders(req, res) {
  const deviceId = req.headers['x-device-id'];
  const scope = req.headers['x-scope'];
  const panel = req.headers['x-panel'];

  if (!deviceId) {
    res.status(400).json({ error: 'missing_device_id', message: 'x-device-id header required' });
    return false;
  }

  if (!scope) {
    res.status(400).json({ error: 'missing_scope', message: 'x-scope header required (state|config|backup)' });
    return false;
  }

  if (!panel || panel.toLowerCase() !== 'controller') {
    res.status(403).json({ error: 'invalid_panel', message: "x-panel must be 'controller'" });
    return false;
  }

  return true;
}

router.get('/sanity', async (req, res) => {
  if (!ensureHeaders(req, res)) {
    return;
  }

  try {
    const fastapiUrl = req.app.locals.fastapiUrl || process.env.FASTAPI_URL;
    if (!fastapiUrl) {
      throw new Error('FASTAPI_URL not configured');
    }

    const targetUrl = new URL('/api/local/controller/board/sanity', fastapiUrl).toString();
    const response = await fetch(targetUrl, {
      method: 'GET',
      headers: {
        'accept': 'application/json',
        'x-device-id': req.headers['x-device-id'],
        'x-scope': req.headers['x-scope'],
        'x-panel': req.headers['x-panel'],
        'x-corr-id': req.headers['x-corr-id'],
      },
    });

    response.headers.forEach((value, key) => {
      res.setHeader(key, value);
    });
    const body = await response.text();
    res.status(response.status).send(body);
  } catch (err) {
    console.error('[Controller Board Proxy] sanity route failed:', err);
    res.status(502).json({
      error: 'controller_board_proxy_failed',
      message: err.message,
    });
  }
});

router.post('/repair', async (req, res) => {
  if (!ensureHeaders(req, res)) {
    return;
  }

  try {
    const fastapiUrl = req.app.locals.fastapiUrl || process.env.FASTAPI_URL;
    if (!fastapiUrl) {
      throw new Error('FASTAPI_URL not configured');
    }

    const targetUrl = new URL('/api/local/controller/board/repair', fastapiUrl).toString();
    const response = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        'accept': 'application/json',
        'content-type': 'application/json',
        'x-device-id': req.headers['x-device-id'],
        'x-scope': req.headers['x-scope'],
        'x-panel': req.headers['x-panel'],
        'x-corr-id': req.headers['x-corr-id'],
      },
      body: JSON.stringify(req.body ?? {}),
    });

    response.headers.forEach((value, key) => {
      res.setHeader(key, value);
    });
    const body = await response.text();
    res.status(response.status).send(body);
  } catch (err) {
    console.error('[Controller Board Proxy] repair route failed:', err);
    res.status(502).json({
      error: 'controller_board_repair_proxy_failed',
      message: err.message,
    });
  }
});

router.post('/firmware/preview', async (req, res) => {
  if (!ensureHeaders(req, res)) {
    return;
  }

  try {
    const fastapiUrl = req.app.locals.fastapiUrl || process.env.FASTAPI_URL;
    if (!fastapiUrl) {
      throw new Error('FASTAPI_URL not configured');
    }

    const targetUrl = new URL('/api/local/controller/board/firmware/preview', fastapiUrl).toString();
    const response = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        accept: 'application/json',
        'content-type': 'application/json',
        'x-device-id': req.headers['x-device-id'],
        'x-scope': req.headers['x-scope'],
        'x-panel': req.headers['x-panel'],
        'x-corr-id': req.headers['x-corr-id'],
      },
      body: JSON.stringify(req.body ?? {}),
    });

    response.headers.forEach((value, key) => {
      res.setHeader(key, value);
    });
    const body = await response.text();
    res.status(response.status).send(body);
  } catch (err) {
    console.error('[Controller Board Proxy] firmware preview route failed:', err);
    res.status(502).json({
      error: 'controller_board_firmware_preview_proxy_failed',
      message: err.message,
    });
  }
});

router.post('/firmware/apply', async (req, res) => {
  if (!ensureHeaders(req, res)) {
    return;
  }

  try {
    const fastapiUrl = req.app.locals.fastapiUrl || process.env.FASTAPI_URL;
    if (!fastapiUrl) {
      throw new Error('FASTAPI_URL not configured');
    }

    const targetUrl = new URL('/api/local/controller/board/firmware/apply', fastapiUrl).toString();
    const response = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        accept: 'application/json',
        'content-type': 'application/json',
        'x-device-id': req.headers['x-device-id'],
        'x-scope': req.headers['x-scope'],
        'x-panel': req.headers['x-panel'],
        'x-corr-id': req.headers['x-corr-id'],
      },
      body: JSON.stringify(req.body ?? {}),
    });

    response.headers.forEach((value, key) => {
      res.setHeader(key, value);
    });
    const body = await response.text();
    res.status(response.status).send(body);
  } catch (err) {
    console.error('[Controller Board Proxy] firmware apply route failed:', err);
    res.status(502).json({
      error: 'controller_board_firmware_apply_proxy_failed',
      message: err.message,
    });
  }
});

router.post('/mapping/preview', async (req, res) => {
  if (!ensureHeaders(req, res)) {
    return;
  }

  try {
    const fastapiUrl = req.app.locals.fastapiUrl || process.env.FASTAPI_URL;
    if (!fastapiUrl) {
      throw new Error('FASTAPI_URL not configured');
    }

    const targetUrl = new URL('/api/local/controller/board/mapping/preview', fastapiUrl).toString();
    const response = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        accept: 'application/json',
        'content-type': 'application/json',
        'x-device-id': req.headers['x-device-id'],
        'x-scope': req.headers['x-scope'],
        'x-panel': req.headers['x-panel'],
        'x-corr-id': req.headers['x-corr-id'],
      },
      body: JSON.stringify(req.body ?? {}),
    });

    response.headers.forEach((value, key) => {
      res.setHeader(key, value);
    });
    const body = await response.text();
    res.status(response.status).send(body);
  } catch (err) {
    console.error('[Controller Board Proxy] mapping preview failed:', err);
    res.status(502).json({
      error: 'controller_board_mapping_preview_failed',
      message: err.message,
    });
  }
});

router.post('/mapping/recover', async (req, res) => {
  if (!ensureHeaders(req, res)) {
    return;
  }

  try {
    const fastapiUrl = req.app.locals.fastapiUrl || process.env.FASTAPI_URL;
    if (!fastapiUrl) {
      throw new Error('FASTAPI_URL not configured');
    }

    const targetUrl = new URL('/api/local/controller/board/mapping/recover', fastapiUrl).toString();
    const response = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        accept: 'application/json',
        'content-type': 'application/json',
        'x-device-id': req.headers['x-device-id'],
        'x-scope': req.headers['x-scope'],
        'x-panel': req.headers['x-panel'],
        'x-corr-id': req.headers['x-corr-id'],
      },
      body: JSON.stringify(req.body ?? {}),
    });

    response.headers.forEach((value, key) => {
      res.setHeader(key, value);
    });
    const body = await response.text();
    res.status(response.status).send(body);
  } catch (err) {
    console.error('[Controller Board Proxy] mapping recover failed:', err);
    res.status(502).json({
      error: 'controller_board_mapping_recover_failed',
      message: err.message,
    });
  }
});

router.post('/mapping/apply', async (req, res) => {
  if (!ensureHeaders(req, res)) {
    return;
  }

  try {
    const fastapiUrl = req.app.locals.fastapiUrl || process.env.FASTAPI_URL;
    if (!fastapiUrl) {
      throw new Error('FASTAPI_URL not configured');
    }

    const targetUrl = new URL('/api/local/controller/board/mapping/apply', fastapiUrl).toString();
    const response = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        accept: 'application/json',
        'content-type': 'application/json',
        'x-device-id': req.headers['x-device-id'],
        'x-scope': req.headers['x-scope'],
        'x-panel': req.headers['x-panel'],
        'x-corr-id': req.headers['x-corr-id'],
      },
      body: JSON.stringify(req.body ?? {}),
    });

    response.headers.forEach((value, key) => {
      res.setHeader(key, value);
    });
    const body = await response.text();
    res.status(response.status).send(body);
  } catch (err) {
    console.error('[Controller Board Proxy] mapping apply failed:', err);
    res.status(502).json({
      error: 'controller_board_mapping_apply_failed',
      message: err.message,
    });
  }
});

export default router;
