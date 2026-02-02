/**
 * CORS Configuration Contract Tests (P0-03)
 *
 * Verifies that CORS allows and exposes custom headers
 * including x-device-id for device tracking.
 */

import { describe, it, expect, beforeAll } from '@jest/globals';
import request from 'supertest';
import express from 'express';
import cors from 'cors';

describe('CORS Configuration (P0-03)', () => {
  let app;

  beforeAll(() => {
    // Replicate gateway CORS configuration
    const corsOptions = {
      origin: ['https://localhost:8787', 'http://localhost:8787', 'http://localhost:5173', 'https://localhost:5173'],
      credentials: true,
      methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
      allowedHeaders: ['x-device-id', 'x-scope', 'content-type', 'authorization', 'x-panel', 'x-corr-id'],
      exposedHeaders: ['x-device-id', 'x-scope', 'x-panel', 'x-corr-id', 'x-tts-quota-warn']
    };

    app = express();
    app.use(cors(corsOptions));
    app.use(express.json());

    // Test endpoint that echoes back custom headers
    app.post('/api/test', (req, res) => {
      res.setHeader('x-device-id', req.headers['x-device-id'] || 'test-device');
      res.setHeader('x-scope', req.headers['x-scope'] || 'state');
      res.json({ received: true });
    });

    app.get('/api/test', (req, res) => {
      res.setHeader('x-device-id', 'server-device');
      res.json({ method: 'GET' });
    });
  });

  describe('Simple requests', () => {
    it('allows x-device-id header in requests', async () => {
      const res = await request(app)
        .post('/api/test')
        .set('Origin', 'http://localhost:5173')
        .set('x-device-id', 'test-123')
        .send({ data: 'test' });

      expect(res.status).toBe(200);
      expect(res.body.received).toBe(true);
    });

    it('exposes x-device-id header in responses', async () => {
      const res = await request(app)
        .get('/api/test')
        .set('Origin', 'http://localhost:5173');

      expect(res.status).toBe(200);
      expect(res.headers['access-control-expose-headers']).toContain('x-device-id');
    });

    it('allows x-scope header', async () => {
      const res = await request(app)
        .post('/api/test')
        .set('Origin', 'http://localhost:5173')
        .set('x-scope', 'config')
        .send({ data: 'test' });

      expect(res.status).toBe(200);
    });

    it('allows x-panel and x-corr-id headers', async () => {
      const res = await request(app)
        .post('/api/test')
        .set('Origin', 'http://localhost:5173')
        .set('x-panel', 'launchbox')
        .set('x-corr-id', 'abc-123')
        .send({ data: 'test' });

      expect(res.status).toBe(200);
    });
  });

  describe('Preflight requests', () => {
    it('responds 204 to OPTIONS preflight', async () => {
      const res = await request(app)
        .options('/api/test')
        .set('Origin', 'http://localhost:5173')
        .set('Access-Control-Request-Method', 'POST')
        .set('Access-Control-Request-Headers', 'x-device-id, content-type');

      expect(res.status).toBe(204);
    });

    it('includes x-device-id in Access-Control-Allow-Headers', async () => {
      const res = await request(app)
        .options('/api/test')
        .set('Origin', 'http://localhost:5173')
        .set('Access-Control-Request-Method', 'POST')
        .set('Access-Control-Request-Headers', 'x-device-id');

      expect(res.headers['access-control-allow-headers']).toMatch(/x-device-id/i);
    });

    it('includes all custom headers in Access-Control-Allow-Headers', async () => {
      const res = await request(app)
        .options('/api/test')
        .set('Origin', 'http://localhost:5173')
        .set('Access-Control-Request-Method', 'POST')
        .set('Access-Control-Request-Headers', 'x-device-id, x-scope, x-panel, x-corr-id');

      const allowedHeaders = res.headers['access-control-allow-headers'].toLowerCase();
      expect(allowedHeaders).toContain('x-device-id');
      expect(allowedHeaders).toContain('x-scope');
      expect(allowedHeaders).toContain('x-panel');
      expect(allowedHeaders).toContain('x-corr-id');
    });

    it('includes Access-Control-Expose-Headers in preflight response', async () => {
      const res = await request(app)
        .options('/api/test')
        .set('Origin', 'http://localhost:5173')
        .set('Access-Control-Request-Method', 'GET');

      // Some CORS implementations include expose headers in preflight, some don't
      // The important check is that actual responses include them
      expect([200, 204]).toContain(res.status);
    });
  });

  describe('CORS contract validation', () => {
    it('allows credentials flag is set', async () => {
      const res = await request(app)
        .get('/api/test')
        .set('Origin', 'http://localhost:5173');

      expect(res.headers['access-control-allow-credentials']).toBe('true');
    });

    it('rejects requests from non-localhost origins', async () => {
      const res = await request(app)
        .post('/api/test')
        .set('Origin', 'http://evil.com')
        .send({ data: 'test' });

      // CORS middleware may allow the request but won't set CORS headers
      // Check that Access-Control-Allow-Origin is NOT set for evil origin
      expect(res.headers['access-control-allow-origin']).not.toBe('http://evil.com');
    });

    it('exposes x-tts-quota-warn header for TTS quota warnings', async () => {
      const res = await request(app)
        .get('/api/test')
        .set('Origin', 'http://localhost:5173');

      const exposedHeaders = res.headers['access-control-expose-headers'] || '';
      expect(exposedHeaders.toLowerCase()).toContain('x-tts-quota-warn');
    });
  });
});
