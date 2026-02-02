export function normalizeError(err) {
  // Default 500 shape per spec
  const fallback = {
    status: 500,
    body: { code: 'PROVIDER_ERROR', message: 'Upstream error' }
  };

  if (!err) return fallback;

  // Timeout handling
  if (err.name === 'AbortError' || /timeout/i.test(err.message || '')) {
    return { status: 500, body: { code: 'PROVIDER_ERROR', message: 'Upstream error', request_id: undefined } };
  }

  // Upstream HTTP error forwarding (if we attached a structured body)
  if (err.__http) {
    const { status = 500, body } = err.__http;
    return { status, body: body || fallback.body };
  }

  // Generic
  return fallback;
}

export function httpError(status, body) {
  const e = new Error(body?.message || 'HTTP error');
  e.__http = { status, body };
  return e;
}

