import express from 'express';
import fs from 'fs';
import path from 'path';

const router = express.Router();

function buildForwardHeaders(req, defaults = {}) {
  const forwarded = {
    'x-scope': req.headers['x-scope'],
    'x-device-id': req.headers['x-device-id'],
    'x-panel': req.headers['x-panel'],
    'x-corr-id': req.headers['x-corr-id'],
    'x-user-profile': req.headers['x-user-profile'],
    'x-user-name': req.headers['x-user-name'],
    'x-session-owner': req.headers['x-session-owner'],
  };

  const headers = { ...defaults, ...forwarded };
  Object.keys(headers).forEach((key) => {
    if (headers[key] === undefined || headers[key] === null || headers[key] === '') {
      delete headers[key];
    }
  });
  return headers;
}

// ===== SHADER MANAGEMENT ROUTES =====
// These explicit routes ensure required headers are forwarded with defaults
// and provide a stable alias for the backend's "available" endpoint as "catalog".

// GET /shaders/catalog -> backend /api/launchbox/shaders/available
router.get('/shaders/catalog', async (req, res) => {
  try {
    const backendUrl = (req.app?.locals?.fastapiUrl) || process.env.FASTAPI_URL || 'http://localhost:8000';
    const response = await fetch(`${backendUrl}/api/launchbox/shaders/available`, {
      headers: buildForwardHeaders(req, {
        'x-scope': 'state',
        'x-device-id': 'unknown',
        'x-panel': 'launchbox'
      })
    });
    const data = await response.json();
    res.status(response.status).json(data);
  } catch (error) {
    console.error('[Gateway] Shader catalog fetch failed:', error);
    res.status(500).json({ error: 'Failed to fetch shader catalog' });
  }
});

// GET /shaders/game/:game_id
router.get('/shaders/game/:game_id', async (req, res) => {
  try {
    const { game_id } = req.params;
    const backendUrl = (req.app?.locals?.fastapiUrl) || process.env.FASTAPI_URL || 'http://localhost:8000';
    const response = await fetch(`${backendUrl}/api/launchbox/shaders/game/${game_id}`, {
      headers: buildForwardHeaders(req, {
        'x-scope': 'state',
        'x-device-id': 'unknown',
        'x-panel': 'launchbox'
      })
    });
    const data = await response.json();
    res.status(response.status).json(data);
  } catch (error) {
    console.error(`[Gateway] Shader fetch for ${req.params.game_id} failed:`, error);
    res.status(500).json({ error: 'Failed to fetch game shader' });
  }
});

// POST /shaders/preview
router.post('/shaders/preview', async (req, res) => {
  try {
    const backendUrl = (req.app?.locals?.fastapiUrl) || process.env.FASTAPI_URL || 'http://localhost:8000';
    const response = await fetch(`${backendUrl}/api/launchbox/shaders/preview`, {
      method: 'POST',
      headers: buildForwardHeaders(req, {
        'Content-Type': 'application/json',
        'x-scope': 'state',
        'x-device-id': 'unknown',
        'x-panel': 'launchbox'
      }),
      body: JSON.stringify(req.body)
    });
    const data = await response.json();
    res.status(response.status).json(data);
  } catch (error) {
    console.error('[Gateway] Shader preview failed:', error);
    res.status(500).json({ error: 'Failed to preview shader change' });
  }
});

// POST /shaders/apply
router.post('/shaders/apply', async (req, res) => {
  try {
    const backendUrl = (req.app?.locals?.fastapiUrl) || process.env.FASTAPI_URL || 'http://localhost:8000';
    const response = await fetch(`${backendUrl}/api/launchbox/shaders/apply`, {
      method: 'POST',
      headers: buildForwardHeaders(req, {
        'Content-Type': 'application/json',
        'x-scope': 'config',
        'x-device-id': 'unknown',
        'x-panel': 'launchbox'
      }),
      body: JSON.stringify(req.body)
    });
    const data = await response.json();
    res.status(response.status).json(data);
  } catch (error) {
    console.error('[Gateway] Shader apply failed:', error);
    res.status(500).json({ error: 'Failed to apply shader change' });
  }
});

// DELETE /shaders/game/:game_id
router.delete('/shaders/game/:game_id', async (req, res) => {
  try {
    const { game_id } = req.params;
    const backendUrl = (req.app?.locals?.fastapiUrl) || process.env.FASTAPI_URL || 'http://localhost:8000';

    // Optional emulator filter as query param
    const queryParams = new URLSearchParams();
    if (req.query.emulator) {
      queryParams.append('emulator', req.query.emulator);
    }
    const queryString = queryParams.toString() ? `?${queryParams.toString()}` : '';

    const response = await fetch(`${backendUrl}/api/launchbox/shaders/game/${game_id}${queryString}`, {
      method: 'DELETE',
      headers: buildForwardHeaders(req, {
        'x-scope': 'config',
        'x-device-id': 'unknown',
        'x-panel': 'launchbox'
      })
    });
    const data = await response.json();
    res.status(response.status).json(data);
  } catch (error) {
    console.error(`[Gateway] Shader delete for ${req.params.game_id} failed:`, error);
    res.status(500).json({ error: 'Failed to delete shader binding' });
  }
});

// POST /shaders/revert
router.post('/shaders/revert', async (req, res) => {
  try {
    const backendUrl = (req.app?.locals?.fastapiUrl) || process.env.FASTAPI_URL || 'http://localhost:8000';
    const response = await fetch(`${backendUrl}/api/launchbox/shaders/revert`, {
      method: 'POST',
      headers: buildForwardHeaders(req, {
        'Content-Type': 'application/json',
        'x-scope': 'config',
        'x-device-id': 'unknown',
        'x-panel': 'launchbox'
      }),
      body: JSON.stringify(req.body)
    });
    const data = await response.json();
    res.status(response.status).json(data);
  } catch (error) {
    console.error('[Gateway] Shader revert failed:', error);
    res.status(500).json({ error: 'Failed to revert shader change' });
  }
});

// =============================================================================
// IMAGE UUID RESOLVER
// =============================================================================
// Resolves LaunchBox game UUIDs to actual image file paths
// Frontend requests: /api/launchbox/image/{uuid}
// Actual files: A:/LaunchBox/Images/{ImageType}/{Platform}/{Title}.png

// (imports at top of file)

/**
 * GET /image/:uuid
 * Proxies LaunchBox game artwork resolution to FastAPI.
 */
router.get('/image/:uuid', async (req, res) => {
  const { uuid } = req.params;
  console.log(`[Image Resolver] Proxying image lookup for game: ${uuid}`);

  try {
    const backendUrl = (req.app?.locals?.fastapiUrl) || process.env.FASTAPI_URL || 'http://localhost:8000';
    const backendImageUrl = new URL(`/api/launchbox/image/${uuid}`, backendUrl);
    for (const [key, value] of Object.entries(req.query || {})) {
      if (Array.isArray(value)) {
        value.forEach((item) => backendImageUrl.searchParams.append(key, String(item)));
      } else if (value !== undefined && value !== null) {
        backendImageUrl.searchParams.set(key, String(value));
      }
    }

    const imageResponse = await fetch(backendImageUrl.toString(), {
      headers: buildForwardHeaders(req, {
        'x-scope': 'state',
        'x-device-id': 'unknown',
        'x-panel': 'launchbox'
      })
    });

    if (!imageResponse.ok) {
      const contentType = imageResponse.headers.get('content-type') || 'application/json';
      const body = contentType.includes('application/json')
        ? await imageResponse.text()
        : await imageResponse.text();
      res.status(imageResponse.status);
      res.setHeader('Content-Type', contentType);
      return res.send(body);
    }

    const contentType = imageResponse.headers.get('content-type') || 'application/octet-stream';
    const cacheControl = imageResponse.headers.get('cache-control');
    const gameTitle = imageResponse.headers.get('x-game-title');
    const region = imageResponse.headers.get('x-region');
    if (cacheControl) res.setHeader('Cache-Control', cacheControl);
    if (gameTitle) res.setHeader('X-Game-Title', gameTitle);
    if (region) res.setHeader('X-Region', region);
    res.setHeader('Content-Type', contentType);
    const buffer = Buffer.from(await imageResponse.arrayBuffer());
    return res.status(imageResponse.status).send(buffer);

  } catch (err) {
    console.error(`[Image Resolver] Error for ${uuid}:`, err);
    return res.status(500).json({ error: 'resolver_error', message: err.message });
  }
});

/**
 * LaunchBox LoRa Proxy Route
 * Forwards /api/launchbox/* requests to FastAPI backend
 *
 * Created: 2025-10-06
 * Purpose: Bridge frontend LaunchBox panel to FastAPI game library endpoints
 */

router.use('/', async (req, res) => {
  try {
    const fastapiUrl = req.app.locals.fastapiUrl || process.env.FASTAPI_URL || 'http://127.0.0.1:8000';
    const targetUrl = `${fastapiUrl}${req.originalUrl}`;

    console.log(`[LaunchBox Proxy] ${req.method} ${req.originalUrl} → ${targetUrl}`);

    // Prepare headers (forward custom headers from frontend)
    const headers = buildForwardHeaders(req, {
      'Content-Type': req.headers['content-type'] || 'application/json',
      'x-panel': req.headers['x-panel'] || 'launchbox',
    });

    // Prepare request options
    const requestOptions = {
      method: req.method,
      headers
    };

    // Add body for POST/PUT/PATCH requests
    if (['POST', 'PUT', 'PATCH'].includes(req.method.toUpperCase()) && req.body) {
      requestOptions.body = JSON.stringify(req.body);
      headers['Content-Type'] = 'application/json';
    }

    // Make request to FastAPI
    const response = await fetch(targetUrl, requestOptions);

    // Copy response headers
    const responseHeaders = {};
    response.headers.forEach((value, key) => {
      responseHeaders[key] = value;
    });

    // Set response headers
    Object.entries(responseHeaders).forEach(([key, value]) => {
      res.setHeader(key, value);
    });

    // Set status and send response
    res.status(response.status);

    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      // Handle JSON responses
      const jsonData = await response.json();
      res.json(jsonData);
    } else if (contentType && contentType.startsWith('image/')) {
      // Handle image responses as binary (don't corrupt with text conversion)
      const buffer = Buffer.from(await response.arrayBuffer());
      res.send(buffer);
    } else {
      // Handle text responses
      const textData = await response.text();
      res.send(textData);
    }

  } catch (err) {
    // Import startup state helper dynamically to avoid circular deps
    const { logBackendError } = await import('../startup_manager.js');
    logBackendError('LaunchBox Proxy', err);

    if (err?.cause?.code === 'ECONNREFUSED' || err.code === 'ECONNREFUSED') {
      res.status(503).json({
        error: 'FastAPI unavailable',
        message: 'Backend not running. Start with: npm run dev:backend',
        hint: 'LaunchBox routes require FastAPI on port 8000'
      });
    } else {
      res.status(500).json({
        error: 'Proxy error',
        message: err.message
      });
    }
  }
});

export default router;
