// Load environment variables FIRST before any other imports
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config({ path: path.resolve(path.dirname(__dirname), '.env') });
console.log('[DEBUG] Loaded FASTAPI_URL:', process.env.FASTAPI_URL);

import express from 'express';
import https from 'https';
import http from 'http';
import { WebSocketServer } from 'ws';
import fs from 'fs';
import cors from 'cors';

import { validateEnvironment, initializeApp } from './startup_manager.js';
import { loadCabinetIdentity } from './utils/cabinetIdentity.js';
import { warnIfManifestMissing } from './utils/driveDetection.js';
import { loadManifest, validateManifest, validateCorsOptions, installNoLocalWritesGuard, preflightNoLocalWritesInConfig } from './policies/manifestValidator.js';
import { setupGracefulShutdown } from './shutdown_manager.js';

import healthRoutes from './routes/health.js';
import localProxyRoutes from './routes/localProxy.js';
import consoleWizardProxyRoutes from './routes/consoleWizardProxy.js';
import consoleProxyRoutes from './routes/consoleProxy.js';
import launchboxProxyRoutes from './routes/launchboxProxy.js';
import launchboxAIRoutes from './routes/launchboxAI.js';
import launchboxScoresRoutes from './routes/launchboxScores.js';
import profileRoutes from './routes/profile.js';
import registerAIRoutes from './routes/ai.js';
import registerFrontendLog from './routes/frontend.js';
import aiHealthRoutes from './routes/aiHealth.js';
import ttsRoutes from './routes/tts.js';
import { setupAudioWebSocket } from './ws/audio.js';
import { setupLEDWebSocket } from './ws/led.js';
import { setupGunnerWebSocket } from './ws/gunner.js';
import { initializeHotkeyBridge } from './ws/hotkey.js';
import ledRoutes from './routes/led.js';
import gunnerRoutes from './routes/gunner.js';
import healthProxyRoutes from './routes/healthProxy.js';
import supabaseRoutes from './routes/supabase.js';
import themeAssetsProxyRoutes from './routes/themeAssetsProxy.js';
import scorekeeperBroadcastRoutes from './routes/scorekeeperBroadcast.js';
import { setupScorekeeperWebSocket } from './ws/scorekeeper.js';
import sessionBroadcastRoutes from './routes/sessionBroadcast.js';
import { setupSessionWebSocket } from './ws/session.js';
import cabinetRoutes from './routes/cabinet.js';
import deweySearchRoutes from './routes/deweySearch.js';

function extractSpaBuildId(indexHtml) {
  const jsMatch = indexHtml.match(/\/assets\/index-([a-f0-9]{8})\.js/i);
  if (jsMatch?.[1]) return jsMatch[1];
  const cssMatch = indexHtml.match(/\/assets\/index-([a-f0-9]{8})\.css/i);
  if (cssMatch?.[1]) return cssMatch[1];
  return 'unknown';
}

function applySpaShellHeaders(res, buildId) {
  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
  res.setHeader('Pragma', 'no-cache');
  res.setHeader('Expires', '0');
  res.setHeader('Surrogate-Control', 'no-store');
  res.setHeader('X-AA-SPA-Build', buildId);
}

function injectRuntimeBootstrap(indexHtml, identity, buildId) {
  const script = `<script>window.AA_DEVICE_ID=${JSON.stringify(identity.deviceId || '')};window.__DEVICE_ID__=window.AA_DEVICE_ID;window.__AA_DEVICE_BOOT__=${JSON.stringify({
    deviceId: identity.deviceId || '',
    deviceName: identity.deviceName || 'Arcade Cabinet',
    deviceSerial: identity.deviceSerial || 'UNPROVISIONED',
    source: identity.source || 'unresolved',
    spaBuild: buildId,
  })};window.__AA_SPA_BUILD__=${JSON.stringify(buildId)};</script>`;

  if (indexHtml.includes('</head>')) {
    return indexHtml.replace('</head>', `${script}</head>`);
  }
  if (indexHtml.includes('<body')) {
    return indexHtml.replace(/<body([^>]*)>/i, `<body$1>${script}`);
  }
  return `${script}${indexHtml}`;
}

async function createServer() {
  try {
    try {
      const aaRoot = process.env.AA_DRIVE_ROOT || process.cwd();
      const manifestPath = path.join(aaRoot, '.aa', 'manifest.json');
      warnIfManifestMissing(manifestPath);
    } catch {
      // best-effort warning only
    }

    try {
      try {
        const manifest = await loadManifest();
        const mErrors = validateManifest(manifest);
        if (mErrors.length) {
          console.warn('Manifest validation warnings:', mErrors);
        }
      } catch (e) {
        console.warn('Manifest load warning:', e?.message || e);
      }

      const ioErrors = preflightNoLocalWritesInConfig();
      if (ioErrors.length) {
        console.error('Config proxy rule violation (local writes detected):', ioErrors);
        process.exit(78);
      }
    } catch (e) {
      console.error('Startup guard error:', e?.message || e);
      process.exit(78);
    }

    await validateEnvironment();

    const app = express();
    await initializeApp(app);
    app.locals.cabinetIdentity = loadCabinetIdentity(app.locals.driveRoot);

    app.disable('x-powered-by');
    app.set('trust proxy', 1);
    app.set('etag', false);

    installNoLocalWritesGuard();

    const defaultOrigins = [
      'https://localhost:8787',
      'http://localhost:8787',
      'http://localhost:5173',
      'https://localhost:5173',
      'https://127.0.0.1:8787',
      'http://127.0.0.1:8787',
      'http://127.0.0.1:5173',
      'https://127.0.0.1:5173'
    ];
    const flintEnv = [process.env.FLINT_CONSOLE_ORIGIN, process.env.FLINT_CONSOLE_ORIGINS]
      .filter(Boolean)
      .join(',');
    const flintOrigins = flintEnv
      .split(',')
      .map((origin) => origin.trim())
      .filter(Boolean);
    const corsOptions = {
      origin: Array.from(new Set([...defaultOrigins, ...flintOrigins])),
      credentials: true,
      methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
      allowedHeaders: ['x-device-id', 'x-scope', 'content-type', 'authorization', 'x-panel', 'x-corr-id', 'x-user-profile', 'x-user-name', 'cache-control', 'x-session-owner'],
      exposedHeaders: ['x-device-id', 'x-scope', 'x-panel', 'x-corr-id', 'x-tts-quota-warn', 'x-aa-spa-build']
    };
    const corsErrors = validateCorsOptions(corsOptions);
    if (corsErrors.length) {
      console.error('CORS policy errors:', corsErrors);
      process.exit(78);
    }
    app.use(cors(corsOptions));

    app.use(express.json({ limit: '10mb' }));
    app.use(express.urlencoded({ extended: true, limit: '10mb' }));

    app.use('/api/health', healthRoutes);
    registerAIRoutes(app);
    registerFrontendLog(app);
    app.use('/api/ai/health', aiHealthRoutes);
    console.log('[INFO] Using FastAPI for /api/local/* via proxy');
    app.use('/api/local/led', ledRoutes);
    app.use('/api/local/gunner', gunnerRoutes);
    app.use('/api/local/health', healthProxyRoutes);
    app.use('/api/supabase', supabaseRoutes);
    app.use('/api/local', localProxyRoutes);
    app.use('/api/console_wizard', consoleWizardProxyRoutes);
    app.use('/api/console', consoleProxyRoutes);
    app.use('/api/voice', ttsRoutes);
    app.use('/api/content', localProxyRoutes);
    app.use('/api/pegasus', localProxyRoutes);
    app.use('/api/theme-assets', themeAssetsProxyRoutes);
    app.use('/api/launchbox', launchboxAIRoutes);
    app.use('/api/launchbox/scores', launchboxScoresRoutes);
    app.use('/api/scorekeeper', scorekeeperBroadcastRoutes);
    app.use('/api/session', sessionBroadcastRoutes);
    app.use('/api/scores', localProxyRoutes);
    app.use('/api', profileRoutes);
    app.use('/api/launchbox', launchboxProxyRoutes);
    app.use('/api/cabinet', cabinetRoutes);
    app.use('/api/dewey/search', deweySearchRoutes);

    const launchboxImages = path.join(
      process.env.AA_DRIVE_ROOT || 'A:\\',
      'LaunchBox',
      'Images'
    );
    if (fs.existsSync(launchboxImages)) {
      console.log('[INFO] Serving LaunchBox images at /api/launchbox/image from:', launchboxImages);
      app.use('/api/launchbox/image', express.static(launchboxImages, {
        maxAge: '1d',
        immutable: true
      }));
    }

    const frontendDist = path.join(__dirname, '..', 'frontend', 'dist');
    const indexPath = path.join(frontendDist, 'index.html');
    const isProduction = process.env.NODE_ENV === 'production';

    const sendSpaShell = (res) => {
      if (!fs.existsSync(indexPath)) {
        res.status(404).json({
          error: 'Frontend not built',
          message: 'Run scripts/prepare_golden_image.bat before cabinet boot or cloning'
        });
        return;
      }

      const indexHtml = fs.readFileSync(indexPath, 'utf8');
      const buildId = extractSpaBuildId(indexHtml);
      const identity = loadCabinetIdentity(app.locals.driveRoot);
      app.locals.cabinetIdentity = identity;
      const hydratedHtml = injectRuntimeBootstrap(indexHtml, identity, buildId);
      applySpaShellHeaders(res, buildId);
      res.type('html');
      res.send(hydratedHtml);
    };

    if (fs.existsSync(frontendDist)) {
      try {
        const indexHtml = fs.readFileSync(indexPath, 'utf8');
        const jsEntry = indexHtml.match(/\/assets\/index-[a-f0-9]{8}\.js/i)?.[0] || 'none';
        const cssEntry = indexHtml.match(/\/assets\/index-[a-f0-9]{8}\.css/i)?.[0] || 'none';
        const buildId = extractSpaBuildId(indexHtml);
        console.log('[Gateway SPA] Serving dist from:', frontendDist);
        console.log('[Gateway SPA] index path:', indexPath);
        console.log('[Gateway SPA] build:', buildId, '| entries:', jsEntry, '|', cssEntry);
      } catch (err) {
        console.warn('[Gateway SPA] Failed to inspect index.html:', err?.message || err);
      }

      app.get(['/index.html'], (req, res) => sendSpaShell(res));

      app.use(express.static(frontendDist, {
        index: false,
        etag: false,
        lastModified: false,
        setHeaders: (res, filePath) => {
          const fileName = path.basename(filePath);
          const extension = path.extname(filePath).toLowerCase();
          const normalizedPath = filePath.replace(/\\/g, '/');
          const isHashedAsset = /\/assets\/.+\.[a-f0-9]{8}\.(js|css)$/.test(normalizedPath);

          if (fileName === 'index.html') {
            applySpaShellHeaders(res, 'static-index');
            return;
          }

          if (!isProduction) {
            res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
            res.setHeader('Pragma', 'no-cache');
            res.setHeader('Expires', '0');
            return;
          }

          if (isHashedAsset) {
            res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
            return;
          }

          if (extension === '.js' || extension === '.css' || extension === '.map') {
            res.setHeader('Cache-Control', 'public, max-age=300, must-revalidate');
          }
        }
      }));
    }

    app.get('/healthz', (req, res) => {
      res.status(200).json({ status: 'ok' });
    });

    app.get('*', (req, res) => {
      sendSpaShell(res);
    });

    app.use((err, req, res, next) => {
      console.error('Gateway error:', err);
      res.status(500).json({
        error: 'Internal server error',
        message: process.env.NODE_ENV === 'development' ? err.message : 'An error occurred'
      });
    });

    const port = process.env.PORT || 8787;
    let server;

    try {
      const certDir = path.join(__dirname, 'certs');
      const keyPath = path.join(certDir, 'dev.key');
      const certPath = path.join(certDir, 'dev.crt');

      if (fs.existsSync(keyPath) && fs.existsSync(certPath)) {
        const httpsOptions = {
          key: fs.readFileSync(keyPath),
          cert: fs.readFileSync(certPath)
        };

        server = https.createServer(httpsOptions, app);
        console.log('[OK] Using HTTPS with dev certificates');
      } else {
        throw new Error('Dev certificates not found');
      }
    } catch (certError) {
      console.log('[WARN] HTTPS certs not found, falling back to HTTP');
      console.log('[INFO] To enable HTTPS, create dev certificates in gateway/certs/');
      console.log('   openssl req -x509 -newkey rsa:4096 -keyout dev.key -out dev.crt -days 365 -nodes');

      server = http.createServer(app);
    }

    const wss = new WebSocketServer({ server });
    setupAudioWebSocket(wss);
    setupLEDWebSocket(wss);
    setupGunnerWebSocket(wss);
    setupScorekeeperWebSocket(wss);
    setupSessionWebSocket(wss);
    initializeHotkeyBridge(wss);
    wss.on('connection', (ws, req) => {
      try {
        const host = req.headers.host || 'localhost';
        const url = new URL(req.url, `http://${host}`);
        const allowedPaths = new Set(['/ws/audio', '/api/local/led/ws', '/api/local/gunner/ws', '/ws/hotkey', '/scorekeeper/ws', '/ws/session']);
        if (!allowedPaths.has(url.pathname)) {
          console.log(`[Gateway WS] Rejecting unsupported path: ${url.pathname}`);
          ws.close(4404, 'Unsupported WebSocket path');
        }
      } catch (err) {
        console.error('[Gateway WS] Validation handler error:', err);
      }
    });

    const host = process.env.AA_HOST || '127.0.0.1';
    server.listen(port, host, () => {
      const protocol = server instanceof https.Server ? 'https' : 'http';
      console.log('[INFO] Gateway running on ' + protocol + '://' + host + ':' + port);
      console.log('[INFO] FastAPI proxy: ' + app.locals.fastapiUrl);
      console.log('[INFO] Cabinet identity source: ' + (app.locals.cabinetIdentity?.source || 'unresolved'));
      console.log('[OK] Ready for requests');
    });

    setupGracefulShutdown(server, wss);

    return server;

  } catch (error) {
    console.error('[ERROR] Failed to start gateway:', error);
    process.exit(1);
  }
}

const isDirectRun = process.argv[1] && path.resolve(process.argv[1]) === __filename;
if (isDirectRun) {
  createServer();
}

export { createServer, extractSpaBuildId, injectRuntimeBootstrap };
