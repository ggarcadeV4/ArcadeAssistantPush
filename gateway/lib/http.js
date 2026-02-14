import { env } from '../config/env.js';

function parseRetryAfterMsFromHeaders(headers) {
  // Prefer explicit ms header if available
  const ms = headers.get('retry-after-ms');
  if (ms && !Number.isNaN(Number(ms))) return Number(ms);
  const ra = headers.get('retry-after');
  if (ra && !Number.isNaN(Number(ra))) return Number(ra) * 1000;
  return undefined;
}

export async function fetchWithRetry(url, init = {}, { attempts, baseMs, timeoutMs } = {}) {
  const max = attempts ?? env.AI_RETRY_MAX_ATTEMPTS;
  const base = baseMs ?? env.AI_RETRY_BASE_MS;
  let lastErr; let retryAfterMs;
  for (let i = 0; i <= max; i++) {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), timeoutMs ?? env.AI_TIMEOUT_MS);
    try {
      const res = await fetch(url, { ...init, signal: ac.signal });
      clearTimeout(t);
      if (res.status === 429) {
        // Prefer upstream hint if supplied
        retryAfterMs = parseRetryAfterMsFromHeaders(res.headers);
        if (i < max) {
          await sleep(retryAfterMs ?? backoff(i, base));
          continue;
        }
      }
      return res;
    } catch (e) {
      lastErr = e;
      clearTimeout(t);
      if (i < max) {
        await sleep(backoff(i, base));
        continue;
      }
    }
  }
  throw lastErr || new Error('Network error');
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const backoff = (i, base) => Math.min(10000, Math.round(base * Math.pow(2, i)));
