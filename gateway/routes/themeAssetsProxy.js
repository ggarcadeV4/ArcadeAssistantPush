import express from 'express';

const router = express.Router();

// Proxy all theme-assets requests to FastAPI
router.use('/', async (req, res) => {
  try {
    const fastapiUrl = req.app.locals.fastapiUrl;
    const pathWithQuery = req.originalUrl.replace('/api/theme-assets', '');
    const targetUrl = `${fastapiUrl}/api/local/theme-assets${pathWithQuery}`;

    // Prepare headers
    const headers = {
      'Content-Type': req.headers['content-type'],
      'x-device-id': req.headers['x-device-id'],
      'x-panel': req.headers['x-panel'],
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
    console.error('Theme assets proxy error:', err);

    if (err.code === 'ECONNREFUSED') {
      res.status(503).json({
        error: 'FastAPI unavailable',
        message: 'Theme assets service is not running'
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
