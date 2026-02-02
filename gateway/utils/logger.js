// Simple redaction helpers for console telemetry
const EMAIL_RE = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi;
const PHONE_RE = /\+?\d[\d\s().-]{6,}\d/g;
const IPV4_RE = /\b(?:\d{1,3}\.){3}\d{1,3}\b/g;

export function redactString(s) {
  return String(s)
    .replace(EMAIL_RE, '***')
    .replace(PHONE_RE, '***')
    .replace(IPV4_RE, '***');
}

export function logAIEvent({ provider, request_id, latency_ms, usage }) {
  try {
    const safe = {
      t: new Date().toISOString(),
      provider: provider,
      request_id: request_id || undefined,
      latency_ms: latency_ms,
      usage: usage ? {
        prompt_tokens: usage.prompt_tokens,
        completion_tokens: usage.completion_tokens,
        total_tokens: usage.total_tokens
      } : undefined
    };
    // Redact any stray strings just in case
    const line = JSON.stringify(safe, (_k, v) => typeof v === 'string' ? redactString(v) : v);
    console.log('[ai]', line);
  } catch { /* no-op */ }
}

