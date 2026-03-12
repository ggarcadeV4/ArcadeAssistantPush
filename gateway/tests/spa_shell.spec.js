import fs from 'fs';
import os from 'os';
import path from 'path';
import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from '@jest/globals';

import { createServer, extractSpaBuildId } from '../server.js';

const ORIGINAL_ENV = { ...process.env };

function makeManifest(root) {
  const aaRoot = path.join(root, '.aa');
  fs.mkdirSync(aaRoot, { recursive: true });
  fs.writeFileSync(path.join(aaRoot, 'manifest.json'), JSON.stringify({
    manifest_version: '1.0',
    drive_root: root,
    sanctioned_paths: ['.aa', '.aa/logs', '.aa/state', 'config/mappings', 'configs/console_wizard', 'logs']
  }, null, 2));
  fs.writeFileSync(path.join(aaRoot, 'device_id.txt'), 'test-device-id\n');
  fs.writeFileSync(path.join(aaRoot, 'cabinet_manifest.json'), JSON.stringify({
    device_id: 'test-device-id',
    device_name: 'Arcade Cabinet',
    device_serial: 'UNPROVISIONED'
  }, null, 2));
}

describe('Gateway SPA shell boot contract', () => {
  let server;
  let driveRoot;

  beforeAll(async () => {
    driveRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'aa-gateway-'));
    makeManifest(driveRoot);

    process.env.AA_DRIVE_ROOT = driveRoot;
    process.env.AA_BACKUP_ON_WRITE = 'true';
    process.env.AA_DRY_RUN_DEFAULT = 'false';
    process.env.FASTAPI_URL = 'http://127.0.0.1:65534';
    process.env.PORT = '0';
    process.env.NODE_ENV = 'production';

    server = await createServer();
  });

  afterAll(async () => {
    if (server) {
      await new Promise((resolve) => server.close(resolve));
    }
    for (const key of Object.keys(process.env)) {
      if (!(key in ORIGINAL_ENV)) delete process.env[key];
    }
    Object.assign(process.env, ORIGINAL_ENV);
  });

  it('serves index.html with no-store headers, build hash, and injected device identity', async () => {
    const indexHtml = fs.readFileSync(path.join(process.cwd(), 'frontend', 'dist', 'index.html'), 'utf8');
    const buildId = extractSpaBuildId(indexHtml);

    const res = await request(server).get('/index.html');

    expect(res.status).toBe(200);
    expect(res.headers['cache-control']).toContain('no-store');
    expect(res.headers['x-aa-spa-build']).toBe(buildId);
    expect(res.text).toContain('window.AA_DEVICE_ID="test-device-id"');
    expect(res.text).toContain('window.__DEVICE_ID__=window.AA_DEVICE_ID');
    expect(res.text).toContain(`window.__AA_SPA_BUILD__="${buildId}"`);
  });
});

