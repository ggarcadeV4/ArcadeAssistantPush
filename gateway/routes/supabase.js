import express from 'express';

const router = express.Router();

function getFastapiBase(req) {
  const base = req.app?.locals?.fastapiUrl || process.env.FASTAPI_URL || 'http://127.0.0.1:8000';
  return base;
}

router.get('/health', async (req, res) => {
  try {
    const base = getFastapiBase(req);
    const url = new URL('/api/supabase/health', base).toString();
    const r = await fetch(url);
    const txt = await r.text();
    res.status(r.status);
    try { res.json(JSON.parse(txt)); } catch { res.send(txt); }
  } catch (err) {
    res.status(502).json({ error: 'gateway_supabase_health_failed', detail: err?.message || String(err) });
  }
});

router.get('/status', async (req, res) => {
  try {
    const base = getFastapiBase(req);
    const url = new URL('/api/supabase/status', base).toString();
    const r = await fetch(url);
    const txt = await r.text();
    res.status(r.status);
    try { res.json(JSON.parse(txt)); } catch { res.send(txt); }
  } catch (err) {
    res.status(502).json({ error: 'gateway_supabase_status_failed', detail: err?.message || String(err) });
  }
});

export default router;

