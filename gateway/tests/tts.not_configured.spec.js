/**
 * TTS Not Configured Contract Tests (P0-04)
 *
 * Verifies that TTS endpoints return 501 NOT_CONFIGURED
 * when ELEVENLABS_API_KEY is not set.
 */

import { describe, it, expect, beforeAll, afterAll } from '@jest/globals';
import request from 'supertest';
import express from 'express';
import ttsRouter from '../routes/tts.js';

describe('TTS Not Configured (P0-04)', () => {
  let app;
  let originalKey;

  beforeAll(() => {
    // Save original key and unset it for tests
    originalKey = process.env.ELEVENLABS_API_KEY;
    delete process.env.ELEVENLABS_API_KEY;

    // Create minimal test app
    app = express();
    app.use(express.json());
    app.use('/api/voice', ttsRouter);
  });

  afterAll(() => {
    // Restore original key
    if (originalKey !== undefined) {
      process.env.ELEVENLABS_API_KEY = originalKey;
    }
  });

  describe('POST /api/voice/tts', () => {
    it('returns 501 NOT_CONFIGURED when ELEVENLABS_API_KEY is unset', async () => {
      const res = await request(app)
        .post('/api/voice/tts')
        .send({ text: 'test message' });

      expect(res.status).toBe(501);
      expect(res.body).toMatchObject({
        code: 'NOT_CONFIGURED',
        service: 'tts'
      });
    });

    it('does not return 500 when key is missing', async () => {
      const res = await request(app)
        .post('/api/voice/tts')
        .send({ text: 'another test' });

      expect(res.status).not.toBe(500);
      expect(res.status).toBe(501);
    });

    it('returns 501 before validating request body', async () => {
      // Send invalid request (no text) - should still get 501, not 400
      const res = await request(app)
        .post('/api/voice/tts')
        .send({});

      expect(res.status).toBe(501);
      expect(res.body.code).toBe('NOT_CONFIGURED');
    });
  });

  describe('GET /api/voice/voices', () => {
    it('returns 501 NOT_CONFIGURED when ELEVENLABS_API_KEY is unset', async () => {
      const res = await request(app).get('/api/voice/voices');

      expect(res.status).toBe(501);
      expect(res.body).toMatchObject({
        code: 'NOT_CONFIGURED',
        service: 'tts'
      });
    });

    it('does not return 500 when key is missing', async () => {
      const res = await request(app).get('/api/voice/voices');

      expect(res.status).not.toBe(500);
      expect(res.status).toBe(501);
    });
  });

  describe('Contract validation', () => {
    it('response payload matches NOT_CONFIGURED contract', async () => {
      const res = await request(app)
        .post('/api/voice/tts')
        .send({ text: 'contract test' });

      // Verify exact contract shape
      expect(res.body).toHaveProperty('code');
      expect(res.body).toHaveProperty('service');
      expect(res.body.code).toBe('NOT_CONFIGURED');
      expect(res.body.service).toBe('tts');

      // Should not have error or message properties (legacy format)
      expect(res.body).not.toHaveProperty('error');
      expect(res.body).not.toHaveProperty('message');
    });
  });
});
