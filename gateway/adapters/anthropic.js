import { env } from '../config/env.js';
import { fetchWithRetry } from '../lib/http.js';
import { errors } from '../lib/errors.js';
import fs from 'fs';
import path from 'path';
import { sendTelemetry } from '../services/supabase_client.js';

// Helper function to read cabinet ID
function readCabinetId() {
  try {
    const driveRoot = process.env.AA_DRIVE_ROOT;
    if (!driveRoot) {
      console.warn('[anthropic] AA_DRIVE_ROOT not set, using cwd');
    }
    const deviceIdPath = path.join(driveRoot || process.cwd(), '.aa', 'device_id.txt');
    return fs.readFileSync(deviceIdPath, 'utf-8').trim();
  } catch (e) {
    console.warn('Warning: Could not read cabinet_id:', e.message);
    return 'unknown-cabinet';
  }
}





export default async function anthropicChat({ messages, temperature, max_tokens, timeout_ms, tools }) {
  // Supabase Edge Function URL
  const API = `${process.env.SUPABASE_URL}/functions/v1/anthropic-proxy`;

  // Check for Supabase configuration instead of direct API key
  if (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) {
    throw errors.notConfigured('Supabase Edge Functions (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required)');
  }

  // Map messages to Anthropic format
  const sys = messages.find(m => m.role === 'system')?.content;
  const userAssistant = messages
    .filter(m => m.role !== 'system')
    .map(m => ({ role: m.role, content: m.content }));

  const body = {
    model: process.env.ANTHROPIC_MODEL || 'claude-3-5-haiku-latest',
    messages: userAssistant,
    system: sys,
    temperature: temperature ?? 0,
    max_tokens: max_tokens ?? env.AI_MAX_TOKENS,

  };

  // Add tools if provided
  if (tools && tools.length > 0) {
    body.tools = tools;
  }

  const startTime = Date.now();
  const res = await fetchWithRetry(API, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
    },
    body: JSON.stringify(body),
  }, { timeoutMs: clampTimeout(timeout_ms) });

  if (!res.ok) {
    const txt = await safeText(res);
    if (res.status === 401) throw errors.unauthorized();
    if (res.status === 429) {
      const ra = res.headers.get('retry-after');
      const raMsHeader = res.headers.get('retry-after-ms');
      const retryAfterMs = raMsHeader && !Number.isNaN(Number(raMsHeader))
        ? Number(raMsHeader)
        : (ra && !Number.isNaN(Number(ra)) ? Number(ra) * 1000 : undefined);
      throw errors.rateLimited('Anthropic rate limited', retryAfterMs);
    }
    throw errors.providerError(`Anthropic ${res.status}: ${txt?.slice(0, 200)}`);
  }

  const data = await res.json();

  // Extract text content
  const contentBlock = data.content?.find?.(c => c.type === 'text');
  const text = contentBlock?.text ?? '';

  // Extract tool uses
  const toolUses = data.content?.filter?.(c => c.type === 'tool_use') || [];

  const usage = data.usage || {}; // { input_tokens, output_tokens }
  const latencyMs = Date.now() - startTime;
  const modelUsed = body.model;

  // Send AI telemetry (fire-and-forget)
  const cabinetId = readCabinetId();
  sendTelemetry(cabinetId, 'INFO', 'AI_CALL', `anthropic ${modelUsed}: ${latencyMs}ms`, {
    provider: 'anthropic',
    model: modelUsed,
    latency_ms: latencyMs,
    input_tokens: usage.input_tokens || null,
    output_tokens: usage.output_tokens || null
  }, 'adapter').catch(() => { });

  return {
    id: data.id,
    provider: 'anthropic',
    model: modelUsed,
    created: Math.floor(Date.now() / 1000),
    message: { role: 'assistant', content: text },
    tool_uses: toolUses.length > 0 ? toolUses : undefined,
    stop_reason: data.stop_reason,
    usage: {
      prompt_tokens: usage.input_tokens ?? 0,
      completion_tokens: usage.output_tokens ?? 0,
      total_tokens: (usage.input_tokens ?? 0) + (usage.output_tokens ?? 0)
    }
  };
}

// Back-compat wrapper for code paths expecting { id, content, usage }
export async function chatWithClaude({ messages, temperature, max_tokens, timeoutMs }) {
  const r = await anthropicChat({ messages, temperature, max_tokens, timeout_ms: timeoutMs });
  return { id: r.id, content: r.message?.content || '', usage: r.usage, stop_reason: undefined };
}

// Minimal streaming shim: emits word chunks via onToken, built on top of non-streaming API.
export async function chat({ prompt, messages, stream = false, onToken, temperature, max_tokens, timeout_ms, tools }) {
  // Build minimal messages array if only prompt provided
  if (!messages && prompt) {
    messages = [{ role: 'user', content: String(prompt) }];
  }

  // Streaming path: call Supabase Edge Function with stream=true
  if (stream && typeof onToken === 'function') {
    // Supabase Edge Function URL
    const API = `${process.env.SUPABASE_URL}/functions/v1/anthropic-proxy`;

    if (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) {
      throw errors.notConfigured('Supabase Edge Functions');
    }
    const body = {
      model: process.env.ANTHROPIC_MODEL || 'claude-3-7-sonnet-latest',
      max_tokens: max_tokens ?? env.AI_MAX_TOKENS,
      temperature: temperature ?? 0,
      messages,
      stream: true,

    };

    const r = await fetch(API, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
      },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw errors.providerError(`Supabase Edge Function ${r.status}`);

    // Server-sent events stream parsing
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const line = chunk.split('\n').find(l => l.startsWith('data: '));
        if (!line) continue;
        if (line.trim() === 'data: [DONE]') continue;
        try {
          const payload = JSON.parse(line.slice(6));
          const delta = payload?.delta?.text ||
            payload?.content?.[0]?.text ||
            payload?.message?.content?.[0]?.text || '';
          if (delta) {
            try { onToken(delta); } catch { }
          }
        } catch { /* ignore parse errors */ }
      }
    }
    return { text: undefined };
  }

  // Non-streaming path: reuse existing chat
  const result = await anthropicChat({ messages, temperature, max_tokens, timeout_ms, tools });
  const text = result?.message?.content || '';
  return { text, usage: result?.usage };
}

async function safeText(res) { try { return await res.text(); } catch { return ''; } }

function clampTimeout(v) {
  const n = parseInt(v ?? env.AI_TIMEOUT_MS, 10);
  return Math.max(3000, Math.min(env.AI_TIMEOUT_MS_MAX ?? 60000, isNaN(n) ? env.AI_TIMEOUT_MS : n));
}
