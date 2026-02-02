export default function registerFrontendLog(app) {
  app.post('/api/frontend/log', async (req, res) => {
    try {
      const r = await fetch(`${process.env.FASTAPI_URL}/frontend/log`, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'x-device-id': req.headers['x-device-id'] || '',
          'x-panel': req.headers['x-panel'] || 'global'
        },
        body: JSON.stringify(req.body || {})
      });
      const text = await r.text();
      res.status(r.status).send(text);
    } catch (e) {
      res.status(502).json({ code: 'BAD_GATEWAY', message: String(e?.message || e) });
    }
  });
}

