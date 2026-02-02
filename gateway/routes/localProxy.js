import express from 'express';

const router = express.Router();

// Middleware to enforce x-scope header on mutating operations
const enforceScopeHeader = (req, res, next) => {
  const mutatingMethods = ['POST', 'PUT', 'PATCH', 'DELETE'];

  if (mutatingMethods.includes(req.method.toUpperCase())) {
    const scope = req.headers['x-scope'];

    if (!scope) {
      return res.status(400).json({
        error: 'Missing x-scope header',
        message: 'Mutating operations require x-scope header (config|state|backup)'
      });
    }

    const validScopes = ['config', 'state', 'backup'];
    if (!validScopes.includes(scope)) {
      return res.status(400).json({
        error: 'Invalid x-scope header',
        message: `x-scope must be one of: ${validScopes.join('|')}`
      });
    }
  }

  next();
};

// Proxy all requests to FastAPI
router.use('/', enforceScopeHeader, async (req, res) => {
  try {
    const fastapiUrl = req.app.locals.fastapiUrl;
    if (!fastapiUrl) {
      throw new Error('FastAPI URL not configured on gateway');
    }

    // Special-case mappings for convenience aliases
    let original = req.originalUrl;
    // Proxy /api/local/hotkey/health -> backend /api/hotkey/health
    if (original === '/api/local/hotkey/health') {
      original = '/api/hotkey/health';
    }
    // Proxy /api/local/retroarch/network/enable -> backend /retroarch/network/enable
    if (original === '/api/local/retroarch/network/enable') {
      original = '/retroarch/network/enable';
    }

    const targetUrl = new URL(original, fastapiUrl).toString();

    // Prepare headers (preserve important ones)
    const headers = {
      'Content-Type': req.headers['content-type'],
      'x-scope': req.headers['x-scope'],
      'x-device-id': req.headers['x-device-id'],
      'x-panel': req.headers['x-panel'],
      'x-corr-id': req.headers['x-corr-id'],
      'Authorization': req.headers['authorization']
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
      const jsonData = await response.json();
      res.json(jsonData);
    } else {
      const textData = await response.text();
      res.send(textData);
    }

  } catch (err) {
    // Import startup state helper dynamically to avoid circular deps
    const { logBackendError } = await import('../startup_manager.js');
    logBackendError('Local Proxy', err);

    if (err.code === 'ECONNREFUSED') {
      res.status(503).json({
        error: 'FastAPI unavailable',
        message: 'Local operations service is not running'
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
