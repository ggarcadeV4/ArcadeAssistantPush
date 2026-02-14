// @panel: MarqueeDisplay
// @role: Minimal marquee "Now Playing" text view (v1)
// @data: Reads marquee config + runtime state; no media rendering yet.

import React, { useEffect, useState } from 'react';

const API_BASE = window.location.port === '5173'
  ? 'http://localhost:8787'
  : '';

export default function MarqueeDisplay() {
  const [config, setConfig] = useState(null);
  const [runtime, setRuntime] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [cfgRes, rtRes] = await Promise.all([
          fetch(`${API_BASE}/api/local/marquee/config`).catch(() => null),
          fetch(`${API_BASE}/api/local/state/frontend`).catch(() => null),
        ]);
        const cfg = cfgRes?.ok ? await cfgRes.json() : null;
        const rt = rtRes?.ok ? await rtRes.json() : null;
        if (!cancelled) {
          setConfig(cfg);
          setRuntime(rt);
        }
      } catch (e) {
        if (!cancelled) setError(e.message || 'Failed to load marquee data');
      }
    }
    load();
    const interval = setInterval(load, 5000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  const headline = runtime?.mode === 'in_game'
    ? 'NOW PLAYING'
    : runtime?.mode === 'browse'
      ? 'BROWSING'
      : 'CABINET IDLE';

  const gameTitle = runtime?.game_title || 'No game selected';
  const frontend = (runtime?.frontend || 'unknown').toUpperCase();
  const system = runtime?.system_id || 'Unknown system';
  const player = runtime?.player || null;

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <div style={styles.headline}>{headline}</div>
        <div style={styles.gameTitle}>{runtime?.mode === 'idle' ? 'Welcome to G&G Arcade' : gameTitle}</div>
        {runtime?.mode !== 'idle' && (
          <>
            <div style={styles.meta}>
              <span>Frontend: {frontend}</span>
              <span style={styles.dot}>•</span>
              <span>System: {system}</span>
            </div>
            {player && <div style={styles.player}>Player: {player}</div>}
          </>
        )}
        {error && <div style={styles.error}>Error: {error}</div>}
      </div>
    </div>
  );
}

const styles = {
  container: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'radial-gradient(circle at 20% 20%, rgba(0,255,255,0.08), transparent 25%), radial-gradient(circle at 80% 30%, rgba(255,0,128,0.08), transparent 25%), #05070f',
    color: '#e8f7ff',
    fontFamily: "'Inter', system-ui, sans-serif",
  },
  card: {
    padding: '32px 48px',
    borderRadius: '12px',
    border: '1px solid rgba(0,255,255,0.2)',
    background: 'rgba(10,12,20,0.85)',
    boxShadow: '0 10px 40px rgba(0,0,0,0.45), 0 0 30px rgba(0,255,255,0.08)',
    textAlign: 'center',
    minWidth: '480px',
  },
  headline: {
    fontSize: '14px',
    letterSpacing: '4px',
    color: '#6af7ff',
    marginBottom: '12px',
  },
  gameTitle: {
    fontSize: '28px',
    fontWeight: 800,
    color: '#ffffff',
    textShadow: '0 0 12px rgba(0,255,255,0.35)',
    marginBottom: '10px',
  },
  meta: {
    display: 'flex',
    justifyContent: 'center',
    gap: '10px',
    fontSize: '14px',
    color: 'rgba(232,247,255,0.75)',
  },
  dot: { opacity: 0.5 },
  player: {
    marginTop: '8px',
    fontSize: '14px',
    color: '#9af7c2',
  },
  error: {
    marginTop: '10px',
    color: '#ff6b6b',
    fontSize: '13px',
  },
};
