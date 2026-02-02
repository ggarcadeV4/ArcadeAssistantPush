import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

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
      console.log(`⏳ [${context}] Waiting for backend to start...`);
    }
    startupState.backendErrorCount++;
    return; // Suppress the full stack trace
  }

  // After grace period or for non-connection errors, log normally
  console.error(`[${context}] Error:`, err?.message || err);
}

function resolveDriveRoot(input) {
  // Allow relative AA_DRIVE_ROOT by resolving from project root (gateway/..)
  const base = path.resolve(__dirname, '..');

  if (!input) return base;

  // Normalize WSL-style paths to Windows when running on Windows
  // Example: /mnt/c/LaunchBox -> C:\\LaunchBox
  if (process.platform === 'win32' && input.startsWith('/mnt/')) {
    const parts = input.split('/');
    if (parts.length >= 3) {
      const driveLetter = (parts[2] || '').toUpperCase();
      const rest = parts.slice(3).join('\\');
      if (driveLetter && /^[A-Z]$/.test(driveLetter)) {
        input = `${driveLetter}:\\${rest}`;
      }
    }
  }

  // Handle Windows paths (C:\\...) and absolute POSIX paths
  const isWinPath = /^[A-Za-z]:[\\\/]/.test(input);
  const isAbsolute = path.isAbsolute(input) || isWinPath;

  return isAbsolute ? input : path.resolve(base, input);
}

export async function validateEnvironment() {
  const required = [
    'PORT',
    'FASTAPI_URL',
    'AA_DRIVE_ROOT'
  ];

  const missing = required.filter(env => !process.env[env]);

  if (missing.length > 0) {
    throw new Error(`Missing required environment variables: ${missing.join(', ')}`);
  }

  // Optional AI provider keys - log warning if missing but don't block boot
  const optional = ['CLAUDE_API_KEY', 'ANTHROPIC_API_KEY', 'ELEVENLABS_API_KEY', 'OPENAI_API_KEY'];
  const missingOptional = optional.filter(env => !process.env[env]);
  if (missingOptional.length > 0) {
    console.log(`⚠️  Optional AI provider keys not configured: ${missingOptional.join(', ')}`);
    console.log('   AI chat and TTS features will be unavailable until keys are added to .env');
  }

  // Validate AA_DRIVE_ROOT exists (warn only, don't block startup)
  const driveRoot = resolveDriveRoot(process.env.AA_DRIVE_ROOT);
  if (!fs.existsSync(driveRoot)) {
    console.warn(`⚠️  Drive root does not exist: ${driveRoot}`);
    console.warn('   Some features may not work correctly without access to the drive.');
  }

  // Validate manifest.json exists and is valid
  const manifestPath = path.join(driveRoot, '.aa', 'manifest.json');
  if (!fs.existsSync(manifestPath)) {
    throw new Error(`Missing manifest.json at: ${manifestPath}`);
  }

  try {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    if (!manifest.sanctioned_paths || !Array.isArray(manifest.sanctioned_paths)) {
      throw new Error('manifest.json missing valid sanctioned_paths array');
    }
  } catch (err) {
    throw new Error(`Invalid manifest.json: ${err.message}`);
  }

  console.log('✅ Environment validation passed');
}

export async function initializeApp(app) {
  // Store FastAPI URL in app locals
  app.locals.fastapiUrl = process.env.FASTAPI_URL || 'http://127.0.0.1:8888';
  console.log('[DEBUG] Using FastAPI URL:', app.locals.fastapiUrl);

  // Store other config
  app.locals.driveRoot = resolveDriveRoot(process.env.AA_DRIVE_ROOT);
  app.locals.isDevelopment = process.env.NODE_ENV === 'development';

  // Test FastAPI connection
  try {
    const response = await fetch(`${process.env.FASTAPI_URL}/health`);
    if (!response.ok) {
      throw new Error(`FastAPI health check failed: ${response.status}`);
    }
    startupState.backendReady = true;
    console.log('✅ FastAPI connection verified');
  } catch (err) {
    console.log(`⚠️ FastAPI not available yet (this is normal during startup)`);
    console.log('   Gateway will start anyway and connect when backend is ready');

    // Start background polling for backend availability
    pollForBackend(app.locals.fastapiUrl);
  }

  console.log('✅ Gateway app initialized');
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
        console.log(`✅ Backend connected (suppressed ${suppressedCount} startup errors)`);
      } else {
        if (attempt < maxAttempts) pollForBackend(fastapiUrl, attempt + 1);
      }
    } catch {
      if (attempt < maxAttempts) pollForBackend(fastapiUrl, attempt + 1);
    }
  }, delayMs);
}
