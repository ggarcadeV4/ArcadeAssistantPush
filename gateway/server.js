// Load environment variables FIRST before any other imports
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load environment variables from root directory
dotenv.config({ path: path.resolve(path.dirname(__dirname), '.env') });
console.log('[DEBUG] Loaded FASTAPI_URL:', process.env.FASTAPI_URL);

// Now import everything else after env vars are loaded
import express from 'express';
import https from 'https';
import http from 'http';
import { WebSocketServer } from 'ws';
import fs from 'fs';
import cors from 'cors';

import { validateEnvironment, initializeApp } from './startup_manager.js';
import { warnIfManifestMissing } from './utils/driveDetection.js';
import { loadManifest, validateManifest, validateCorsOptions, installNoLocalWritesGuard, preflightNoLocalWritesInConfig } from './policies/manifestValidator.js'
import { setupGracefulShutdown } from './shutdown_manager.js';

// Import route handlers
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
import { initializeHotkeyBridge, hotkeyBridge } from './ws/hotkey.js';
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

async function createServer() {
  try {
    // Dev-only: warn if /.aa/manifest.json missing under AA_DRIVE_ROOT
    try {
      const aaRoot = process.env.AA_DRIVE_ROOT || process.cwd()
      const manifestPath = path.join(aaRoot, '.aa', 'manifest.json')
      warnIfManifestMissing(manifestPath)
    } catch { }
    // Validate IO guardrails; manifest issues log warnings but don't block gateway
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

    // Validate environment and initialize app
    await validateEnvironment();

    const app = express();
    await initializeApp(app);

    // Security middleware
    app.disable('x-powered-by');
    app.set('trust proxy', 1);
    app.set('etag', false);

    // Enforce no local writes at gateway layer
    installNoLocalWritesGuard();

    // CORS - locked to localhost (dev allowlist includes Vite)
    // Include both localhost and 127.0.0.1 to prevent CORS identity crisis
    const defaultOrigins = [
      'https://localhost:8787',
      'http://localhost:8787',
      'http://localhost:5173',
      'https://localhost:5173',
      // 127.0.0.1 variants (same machine, different hostname)
      'https://127.0.0.1:8787',
      'http://127.0.0.1:8787',
      'http://127.0.0.1:5173',
      'https://127.0.0.1:5173'
    ]
    const flintEnv = [process.env.FLINT_CONSOLE_ORIGIN, process.env.FLINT_CONSOLE_ORIGINS]
      .filter(Boolean)
      .join(',')
    const flintOrigins = flintEnv
      .split(',')
      .map((origin) => origin.trim())
      .filter(Boolean)
    const corsOptions = {
      origin: Array.from(new Set([...defaultOrigins, ...flintOrigins])),
      credentials: true,
      methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
      // Required headers: x-device-id, x-scope, content-type, authorization
      allowedHeaders: ['x-device-id', 'x-scope', 'content-type', 'authorization', 'x-panel', 'x-corr-id', 'x-user-profile', 'x-user-name', 'cache-control', 'x-session-owner'],
      // Expose custom headers to client
      exposedHeaders: ['x-device-id', 'x-scope', 'x-panel', 'x-corr-id', 'x-tts-quota-warn']
    }
    const corsErrors = validateCorsOptions(corsOptions)
    if (corsErrors.length) {
      console.error('CORS policy errors:', corsErrors)
      process.exit(78)
    }
    app.use(cors(corsOptions));

    // Body parsing
    app.use(express.json({ limit: '10mb' }));
    app.use(express.urlencoded({ extended: true, limit: '10mb' }));

    // API routes (MUST be registered BEFORE static files to prevent SPA fallback from catching them)
    app.use('/api/health', healthRoutes);
    // Register AI + Frontend log + Config routes BEFORE local proxy so aliases take precedence
    registerAIRoutes(app);
    registerFrontendLog(app);
    app.use('/api/ai/health', aiHealthRoutes);
    // Do not register local config routes; proxy all /api/local/* to FastAPI
    // This enforces the invariant: Gateway performs no direct file I/O
    console.log('[INFO] Using FastAPI for /api/local/* via proxy');
    app.use('/api/local/led', ledRoutes);
    app.use('/api/local/gunner', gunnerRoutes);
    app.use('/api/local/health', healthProxyRoutes);
    app.use('/api/supabase', supabaseRoutes);
    app.use('/api/local', localProxyRoutes);
    app.use('/api/console_wizard', consoleWizardProxyRoutes);
    app.use('/api/console', consoleProxyRoutes);
    app.use('/api/voice', ttsRoutes);
    // Content & Display Manager routes (proxy to FastAPI)
    app.use('/api/content', localProxyRoutes);
    // Pegasus frontend integration (proxy to FastAPI)
    app.use('/api/pegasus', localProxyRoutes);
    // Theme asset management (proxy to FastAPI)
    app.use('/api/theme-assets', themeAssetsProxyRoutes);
    // LaunchBox LoRa routes (added 2025-10-06)
    app.use('/api/launchbox', launchboxAIRoutes);  // AI chat endpoint
    app.use('/api/launchbox/scores', launchboxScoresRoutes);  // Scores/telemetry proxy to plugin
    app.use('/api/scorekeeper', scorekeeperBroadcastRoutes);  // WebSocket broadcast endpoint
    app.use('/api/session', sessionBroadcastRoutes);  // Session/user WebSocket broadcast endpoint
    app.use('/api/scores', localProxyRoutes);  // Score reset/backup API (proxied to FastAPI)
    app.use('/api', profileRoutes); // /api/profile/* and /api/consent/*
    app.use('/api/launchbox', launchboxProxyRoutes);  // Data proxy
    app.use('/api/cabinet', cabinetRoutes);  // Cabinet config + Wiring Wizard (Phase 5.5)
    app.use('/api/dewey/search', deweySearchRoutes);  // Dewey Historian internet-backed lore search

    // Serve LaunchBox images (for frontend image requests)
    // Frontend requests: /api/launchbox/image/{uuid}
    const launchboxImages = 'A:/LaunchBox/Images';
    if (fs.existsSync(launchboxImages)) {
      console.log('[INFO] Serving LaunchBox images at /api/launchbox/image from:', launchboxImages);
      app.use('/api/launchbox/image', express.static(launchboxImages, {
        maxAge: '1d',  // Cache for 24 hours (images rarely change)
        immutable: true
      }));
    }

    // Serve frontend static files (AFTER API routes)
    const frontendDist = path.join(__dirname, '..', 'frontend', 'dist');
    const indexPath = path.join(frontendDist, 'index.html');
    const isProduction = process.env.NODE_ENV === 'production';

    const sendSpaShell = (res) => {
      if (!fs.existsSync(indexPath)) {
        res.status(404).json({
          error: 'Frontend not built',
          message: 'Run npm run build:frontend first'
        });
        return;
      }

      // Prevent caching/revalidation of SPA shell to avoid stale hashed asset refs.
      res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
      res.setHeader('Pragma', 'no-cache');
      res.setHeader('Expires', '0');
      res.setHeader('Surrogate-Control', 'no-store');
      const html = fs.readFileSync(indexPath, 'utf8');
      res.type('html');
      res.send(html);
    };

    if (fs.existsSync(frontendDist)) {
      try {
        const indexHtml = fs.readFileSync(indexPath, 'utf8');
        const jsEntry = indexHtml.match(/\/assets\/index-[a-f0-9]{8}\.js/i)?.[0] || 'none';
        const cssEntry = indexHtml.match(/\/assets\/index-[a-f0-9]{8}\.css/i)?.[0] || 'none';
        console.log('[Gateway SPA] Serving dist from:', frontendDist);
        console.log('[Gateway SPA] index path:', indexPath);
        console.log('[Gateway SPA] index entries:', jsEntry, '|', cssEntry);
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
            res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
            res.setHeader('Pragma', 'no-cache');
            res.setHeader('Expires', '0');
            res.setHeader('Surrogate-Control', 'no-store');
            return;
          }

          // Dev ergonomics: avoid stale bundles while iterating locally.
          if (!isProduction) {
            res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
            res.setHeader('Pragma', 'no-cache');
            res.setHeader('Expires', '0');
            return;
          }

          // Production: cache immutable hashed bundles aggressively.
          if (isHashedAsset) {
            res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
            return;
          }

          // Production fallback for other static files.
          if (extension === '.js' || extension === '.css' || extension === '.map') {
            res.setHeader('Cache-Control', 'public, max-age=300, must-revalidate');
          }
        }
      }));
    }

    // Health endpoint
    app.get("/healthz", (req, res) => {
      res.status(200).json({ status: "ok" });
    });

    // Frontend fallback (SPA)
    app.get('*', (req, res) => {
      sendSpaShell(res);
    });

    // Error handling
    app.use((err, req, res, next) => {
      console.error('Gateway error:', err);
      res.status(500).json({
        error: 'Internal server error',
        message: process.env.NODE_ENV === 'development' ? err.message : 'An error occurred'
      });
    });

    // Try HTTPS first, fallback to HTTP
    const port = process.env.PORT || 8787;
    let server;

    try {
      // Attempt to load HTTPS certificates
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

    // Setup WebSocket server
    const wss = new WebSocketServer({ server });
    setupAudioWebSocket(wss);
    setupLEDWebSocket(wss);
    setupGunnerWebSocket(wss);
    setupScorekeeperWebSocket(wss);
    setupSessionWebSocket(wss);
    initializeHotkeyBridge(wss);
    wss.on('connection', (ws, req) => {
      try {
        const host = req.headers.host || 'localhost'
        const url = new URL(req.url, `http://${host}`)
        const allowedPaths = new Set(['/ws/audio', '/api/local/led/ws', '/api/local/gunner/ws', '/ws/hotkey', '/scorekeeper/ws', '/ws/session'])
        if (!allowedPaths.has(url.pathname)) {
          console.log(`[Gateway WS] Rejecting unsupported path: ${url.pathname}`)
          ws.close(4404, 'Unsupported WebSocket path')
        }
      } catch (err) {
        console.error('[Gateway WS] Validation handler error:', err)
        // Don't close - let specific handlers decide
      }
    })

    // Start server - bind to localhost by default for security
    // Allow override via AA_HOST env var (e.g., "0.0.0.0" for network access)
    const host = process.env.AA_HOST || '127.0.0.1';
    server.listen(port, host, () => {
      const protocol = server instanceof https.Server ? 'https' : 'http';
      console.log('[INFO] Gateway running on ' + protocol + '://' + host + ':' + port);
      console.log('[INFO] FastAPI proxy: ' + app.locals.fastapiUrl);
      console.log('[OK] Ready for requests');
    });

    // Setup graceful shutdown
    setupGracefulShutdown(server, wss);

    return server;

  } catch (error) {
    console.error('[ERROR] Failed to start gateway:', error);
    process.exit(1);
  }
}

// Start the server
const isDirectRun = process.argv[1] && path.resolve(process.argv[1]) === __filename;
if (isDirectRun) {
  createServer();
}

export { createServer };
