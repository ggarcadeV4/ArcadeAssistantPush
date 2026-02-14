import { Readable } from 'node:stream';
import express from 'express';
import { fetchWithRetry } from '../lib/http.js';

const router = express.Router();

function buildHeaders(req, defaults = {}) {
  const headers = {
    'content-type': 'application/json',
    'x-scope': req.headers['x-scope'] || 'state',
    'x-device-id': req.headers['x-device-id'],
    'x-panel': req.headers['x-panel'] || 'controller',
    ...defaults
  };

  Object.keys(headers).forEach((key) => {
    if (!headers[key]) delete headers[key];
  });
  return headers;
}

router.get('/ai/events', async (req, res) => {
  try {
    const fastapi = req.app.locals.fastapiUrl;
    const controller = new AbortController();
    req.on('close', () => controller.abort());

    const headers = buildHeaders(req, { 'content-type': undefined, accept: 'text/event-stream' });
    const response = await fetch(`${fastapi}/api/ai/controller/events`, {
      method: 'GET',
      headers,
      signal: controller.signal
    });

    response.headers.forEach((value, key) => {
      res.setHeader(key, value);
    });
    res.status(response.status);

    if (!response.body) {
      res.end();
      return;
    }

    const stream = Readable.fromWeb(response.body);
    stream.on('error', (error) => {
      console.error('[Controller AI] SSE stream error:', error);
      try {
        res.end();
      } catch (_) {}
    });
    stream.pipe(res);
  } catch (error) {
    console.error('[Controller AI] SSE proxy failed:', error);
    if (!res.headersSent) {
      res.status(502).json({
        success: false,
        error: 'controller_ai_unavailable',
        message: error.message
      });
    }
  }
});

router.post('/ai/chat', async (req, res) => {
  try {
    const fastapi = req.app.locals.fastapiUrl;
    const response = await fetchWithRetry(`${fastapi}/api/ai/controller/chat`, {
      method: 'POST',
      headers: buildHeaders(req),
      body: JSON.stringify(req.body || {})
    });

    const body = await response.json();
    res.status(response.status).json(body);
  } catch (error) {
    console.error('[Controller AI] chat proxy failed:', error);
    res.status(502).json({
      success: false,
      error: 'controller_ai_unavailable',
      message: error.message
    });
  }
});

router.get('/ai/health', async (req, res) => {
  try {
    const fastapi = req.app.locals.fastapiUrl;
    const response = await fetchWithRetry(`${fastapi}/api/ai/controller/health`, {
      method: 'GET',
      headers: buildHeaders(req, { 'x-scope': 'state' })
    });

    if (!response.ok) {
      return res.status(response.status).json(await response.json());
    }

    const body = await response.json();
    body.success = true;
    res.json(body);
  } catch (error) {
    console.error('[Controller AI] health check failed:', error);
    res.status(502).json({
      success: false,
      error: 'controller_ai_unavailable',
      message: error.message
    });
  }
});

export default router;
