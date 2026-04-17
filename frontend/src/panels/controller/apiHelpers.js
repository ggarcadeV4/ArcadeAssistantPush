import { buildStandardHeaders } from '../../utils/identity';

const CONTROLLER_API = '/api/local/controller';

function resolveUrl(path) {
  if (!path) return path;
  if (/^https?:/i.test(path)) {
    return path;
  }
  if (typeof window !== 'undefined' && window.location?.origin) {
    return `${window.location.origin}${path}`;
  }
  return `http://localhost${path}`;
}

export async function fetchCascadeStatus({ signal } = {}) {
  const response = await fetch(resolveUrl(`${CONTROLLER_API}/cascade/status`), {
    method: 'GET',
    headers: buildStandardHeaders({
      panel: 'controller-chuck',
      scope: 'state',
      extraHeaders: { 'Content-Type': 'application/json' }
    }),
    signal,
  });

  if (!response.ok) {
    const detail = await safeJson(response);
    const message = detail?.detail || `Cascade status failed (${response.status})`;
    throw new Error(message);
  }

  return response.json();
}

export async function fetchBaseline({ signal } = {}) {
  const response = await fetch(resolveUrl(`${CONTROLLER_API}/baseline`), {
    method: 'GET',
    headers: buildStandardHeaders({
      panel: 'controller-chuck',
      scope: 'state',
      extraHeaders: { 'Content-Type': 'application/json' }
    }),
    signal,
  });

  if (!response.ok) {
    const detail = await safeJson(response);
    const message = detail?.detail || `Baseline fetch failed (${response.status})`;
    throw new Error(message);
  }

  return response.json();
}

export async function requestCascade({
  metadata,
  skipEmulators = [],
  skipLed = false,
  baseline,
} = {}) {
  const payload = {
    skip_led: Boolean(skipLed),
    skip_emulators: Array.isArray(skipEmulators) ? skipEmulators : [],
    metadata: metadata || {},
  };

  if (baseline) {
    payload.baseline = baseline;
  }

  const response = await fetch(resolveUrl(`${CONTROLLER_API}/cascade/apply`), {
    method: 'POST',
    headers: buildStandardHeaders({
      panel: 'controller-chuck',
      scope: 'config',
      extraHeaders: { 'Content-Type': 'application/json' }
    }),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const detail = await safeJson(response);
    const message = detail?.detail || `Cascade request failed (${response.status})`;
    throw new Error(message);
  }

  return response.json();
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch (_err) {
    return null;
  }
}

export function getCascadePollInterval() {
  return 20000;
}

export function getCascadePreference(defaultValue = 'ask') {
  if (typeof window === 'undefined') return defaultValue;
  return window.localStorage.getItem('chuckAutoCascade') || defaultValue;
}

export function setCascadePreference(value) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem('chuckAutoCascade', value);
}
