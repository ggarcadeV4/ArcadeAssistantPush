import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { getDriveRoot, getManifestPath, getRuntimePaths, warnIfManifestMissing } from './utils/driveDetection.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Startup state tracking - used to suppress noisy logs during backend startup
export const startupState = {
  backendReady: false,
  startedAt: Date.now(),
  gracePeriodMs: 30000,  // 30 seconds grace period for startup noise suppression
  lastBackendError: null,
  backendErrorCount: 0
};

// Helper to check if we're still in startup grace period
export function inStartupGracePeriod() {
  return !startupState.backendReady && (Date.now() - startupState.startedAt) < startupState.gracePeriodMs;
}

// Helper to log backend connection errors (suppresses duplicates during startup)
export function logBackendError(context, err) {
  const isEconnRefused = err?.cause?.code === 'ECONNREFUSED' || err?.code === 'ECONNREFUSED';

  if (inStartupGracePeriod() && isEconnRefused) {
    // During startup, only log the first ECONNREFUSED and then suppress
    if (startupState.backendErrorCount === 0) {
      console.log(`â³ [${context}] Waiting for backend to start...`);
    }
    startupState.backendErrorCount++;
    return; // Suppress the full stack trace
  }

  // After grace period or for non-connection errors, log normally
  console.error(`[${context}] Error:`, err?.message || err);
}

export async function validateEnvironment() {
  const required = [
    'PORT',
    'FASTAPI_URL'
  ];

  const missing = required.filter(env => !process.env[env]);

  if (missing.length > 0) {
    throw new Error(`Missing required environment variables: ${missing.join(', ')}`);
  }

  // Optional AI provider keys - log warning if missing but don't block boot
  const optional = ['CLAUDE_API_KEY', 'ANTHROPIC_API_KEY', 'ELEVENLABS_API_KEY', 'OPENAI_API_KEY'];
  const missingOptional = optional.filter(env => !process.env[env]);
  if (missingOptional.length > 0) {
    console.log(`âš ï¸  Optional AI provider keys not configured: ${missingOptional.join(', ')}`);
    console.log('   AI chat and TTS features will be unavailable until keys are added to .env');
  }

  // Validate AA_DRIVE_ROOT exists (warn only, don't block startup)
  const driveRoot = getDriveRoot();
  if (!driveRoot) {
    console.warn('⚠️  AA_DRIVE_ROOT is not set; gateway will continue in demo/read-only mode until configured.');
    return;
  }

  if (!fs.existsSync(driveRoot)) {
    console.warn(`âš ï¸  Configured root does not exist: ${driveRoot}`);
    console.warn('   Some features may not work correctly without access to the drive.');
    return;
  }

  // Validate manifest.json exists and is valid
  const manifestPath = getManifestPath(driveRoot);
  if (!fs.existsSync(manifestPath)) {
    warnIfManifestMissing(driveRoot);
    return;
  }

  try {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    if (!manifest.sanctioned_paths || !Array.isArray(manifest.sanctioned_paths)) {
      throw new Error('manifest.json missing valid sanctioned_paths array');
    }
  } catch (err) {
    throw new Error(`Invalid manifest.json: ${err.message}`);
  }

  console.log('âœ… Environment validation passed');
}

export async function initializeApp(app) {
  // Store FastAPI URL in app locals
  app.locals.fastapiUrl = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';
  console.log('[DEBUG] Using FastAPI URL:', app.locals.fastapiUrl);

  // Store other config
  app.locals.driveRoot = getDriveRoot();
  app.locals.runtimePaths = getRuntimePaths(app.locals.driveRoot);
  app.locals.isDevelopment = process.env.NODE_ENV === 'development';
  if (!app.locals.driveRoot) {
    console.warn('⚠️  Gateway initialized without AA_DRIVE_ROOT; cabinet file-backed features stay in demo/read-only mode.');
  }

  // Test FastAPI connection
  try {
    const response = await fetch(`${process.env.FASTAPI_URL}/health`);
    if (!response.ok) {
      throw new Error(`FastAPI health check failed: ${response.status}`);
    }
    startupState.backendReady = true;
    console.log('âœ… FastAPI connection verified');
  } catch (err) {
    console.log(`âš ï¸ FastAPI not available yet (this is normal during startup)`);
    console.log('   Gateway will start anyway and connect when backend is ready');

    // Start background polling for backend availability
    pollForBackend(app.locals.fastapiUrl);
  }

  console.log('âœ… Gateway app initialized');
}

// Background poll for backend to come online (non-blocking)
function pollForBackend(fastapiUrl, attempt = 0) {
  if (startupState.backendReady) return;

  const maxAttempts = 60; // Give up after ~60 seconds
  const delayMs = Math.min(1000 * Math.pow(1.2, attempt), 5000); // Exponential backoff, max 5s

  setTimeout(async () => {
    try {
      const response = await fetch(`${fastapiUrl}/health`);
      if (response.ok) {
        startupState.backendReady = true;
        const suppressedCount = startupState.backendErrorCount;
        console.log(`âœ… Backend connected (suppressed ${suppressedCount} startup errors)`);
      } else {
        if (attempt < maxAttempts) pollForBackend(fastapiUrl, attempt + 1);
      }
    } catch {
      if (attempt < maxAttempts) pollForBackend(fastapiUrl, attempt + 1);
    }
  }, delayMs);
}
