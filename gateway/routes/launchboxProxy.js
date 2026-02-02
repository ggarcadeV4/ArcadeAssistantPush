import express from 'express';

const router = express.Router();

// ===== SHADER MANAGEMENT ROUTES =====
// These explicit routes ensure required headers are forwarded with defaults
// and provide a stable alias for the backend's "available" endpoint as "catalog".

// GET /shaders/catalog -> backend /api/launchbox/shaders/available
router.get('/shaders/catalog', async (req, res) => {
  try {
    const backendUrl = (req.app?.locals?.fastapiUrl) || process.env.FASTAPI_URL || 'http://localhost:8888';
    const response = await fetch(`${backendUrl}/api/launchbox/shaders/available`, {
      headers: {
        'x-scope': req.headers['x-scope'] || 'state',
        'x-device-id': req.headers['x-device-id'] || 'unknown',
        'x-panel': req.headers['x-panel'] || 'launchbox'
      }
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
    const backendUrl = (req.app?.locals?.fastapiUrl) || process.env.FASTAPI_URL || 'http://localhost:8888';
    const response = await fetch(`${backendUrl}/api/launchbox/shaders/game/${game_id}`, {
      headers: {
        'x-scope': req.headers['x-scope'] || 'state',
        'x-device-id': req.headers['x-device-id'] || 'unknown',
        'x-panel': req.headers['x-panel'] || 'launchbox'
      }
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
    const backendUrl = (req.app?.locals?.fastapiUrl) || process.env.FASTAPI_URL || 'http://localhost:8888';
    const response = await fetch(`${backendUrl}/api/launchbox/shaders/preview`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-scope': req.headers['x-scope'] || 'state',
        'x-device-id': req.headers['x-device-id'] || 'unknown',
        'x-panel': req.headers['x-panel'] || 'launchbox'
      },
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
    const backendUrl = (req.app?.locals?.fastapiUrl) || process.env.FASTAPI_URL || 'http://localhost:8888';
    const response = await fetch(`${backendUrl}/api/launchbox/shaders/apply`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-scope': req.headers['x-scope'] || 'config',
        'x-device-id': req.headers['x-device-id'] || 'unknown',
        'x-panel': req.headers['x-panel'] || 'launchbox'
      },
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
    const backendUrl = (req.app?.locals?.fastapiUrl) || process.env.FASTAPI_URL || 'http://localhost:8888';

    // Optional emulator filter as query param
    const queryParams = new URLSearchParams();
    if (req.query.emulator) {
      queryParams.append('emulator', req.query.emulator);
    }
    const queryString = queryParams.toString() ? `?${queryParams.toString()}` : '';

    const response = await fetch(`${backendUrl}/api/launchbox/shaders/game/${game_id}${queryString}`, {
      method: 'DELETE',
      headers: {
        'x-scope': req.headers['x-scope'] || 'config',
        'x-device-id': req.headers['x-device-id'] || 'unknown',
        'x-panel': req.headers['x-panel'] || 'launchbox'
      }
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
    const backendUrl = (req.app?.locals?.fastapiUrl) || process.env.FASTAPI_URL || 'http://localhost:8888';
    const response = await fetch(`${backendUrl}/api/launchbox/shaders/revert`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-scope': req.headers['x-scope'] || 'config',
        'x-device-id': req.headers['x-device-id'] || 'unknown',
        'x-panel': req.headers['x-panel'] || 'launchbox'
      },
      body: JSON.stringify(req.body)
    });
    const data = await response.json();
    res.status(response.status).json(data);
  } catch (error) {
    console.error('[Gateway] Shader revert failed:', error);
    res.status(500).json({ error: 'Failed to revert shader change' });
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
    const fastapiUrl = req.app.locals.fastapiUrl || process.env.FASTAPI_URL || 'http://127.0.0.1:8888';
    const targetUrl = `${fastapiUrl}${req.originalUrl}`;

    console.log(`[LaunchBox Proxy] ${req.method} ${req.originalUrl} → ${targetUrl}`);

    // Prepare headers (forward custom headers from frontend)
    const headers = {
      'Content-Type': req.headers['content-type'] || 'application/json',
      'x-panel': req.headers['x-panel'] || 'launchbox',
      'x-corr-id': req.headers['x-corr-id'],
      'x-device-id': req.headers['x-device-id'],
    };

    // Remove undefined headers
    Object.keys(headers).forEach(key => {
      if (!headers[key]) {
        delete headers[key];
      }
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
        hint: 'LaunchBox routes require FastAPI on port 8888'
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
