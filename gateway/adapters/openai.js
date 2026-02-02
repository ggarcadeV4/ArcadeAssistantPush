import { env } from '../config/env.js';
import { fetchWithRetry } from '../lib/http.js';
import { errors } from '../lib/errors.js';

import fs from 'fs';
import path from 'path';

// Helper function to read cabinet ID
function readCabinetId() {
  try {
    const driveRoot = process.env.AA_DRIVE_ROOT;
    if (!driveRoot) {
      console.warn('[openai] AA_DRIVE_ROOT not set, using cwd');
    }
    const deviceIdPath = path.join(driveRoot || process.cwd(), '.aa', 'device_id.txt');
    return fs.readFileSync(deviceIdPath, 'utf-8').trim();
  } catch (e) {
    console.warn('Warning: Could not read cabinet_id:', e.message);
    return 'unknown-cabinet';
  }
}



export default async function openaiChat({ messages, temperature, max_tokens, timeout_ms, tools }) {
  // Supabase Edge Function URL (defined here to ensure env vars are loaded)
  const API = `${process.env.SUPABASE_URL}/functions/v1/openai-proxy`;

  // Check for Supabase configuration
  if (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) {
    throw errors.notConfigured('Supabase Edge Functions (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required)');
  }

  const body = {
    model: process.env.OPENAI_MODEL || 'gpt-4o-mini',
    messages,
    temperature: temperature ?? 0,
    max_tokens: max_tokens ?? env.AI_MAX_TOKENS,
  };

  // Map panel tools to OpenAI function calling format
  if (Array.isArray(tools) && tools.length > 0) {
    body.tools = tools.map(t => ({
      type: 'function',
      function: {
        name: t.name,
        description: t.description,
        parameters: t.input_schema
      }
    }));
    body.tool_choice = 'auto';
  }

  console.log('[DEBUG] Calling API:', API);
  console.log('[DEBUG] Request body:', JSON.stringify(body, null, 2));

  let res;
  try {
    res = await fetchWithRetry(API, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'authorization': `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
      },
      body: JSON.stringify(body),
    }, { timeoutMs: clampTimeout(timeout_ms) });
  } catch (err) {
    console.error('[DEBUG] Fetch failed:', err);
    throw err;
  }

  if (!res.ok) {
    const txt = await safeText(res);
    console.error(`[DEBUG] Supabase Edge Function failed: ${res.status} ${res.statusText}`);
    console.error(`[DEBUG] Response body: ${txt}`);

    if (res.status === 401) throw errors.unauthorized();
    if (res.status === 429) {
      const ra = res.headers.get('retry-after');
      const raMsHeader = res.headers.get('retry-after-ms');
      const retryAfterMs = raMsHeader && !Number.isNaN(Number(raMsHeader))
        ? Number(raMsHeader)
        : (ra && !Number.isNaN(Number(ra)) ? Number(ra) * 1000 : undefined);
      throw errors.rateLimited('OpenAI rate limited', retryAfterMs);
    }
    throw errors.providerError(`Supabase Edge Function ${res.status}: ${txt?.slice(0, 200)}`);
  }

  let data;
  try {
    data = await res.json();
  } catch (e) {
    const txt = await safeText(res);
    console.error('[DEBUG] Failed to parse JSON from Supabase response:', e);
    console.error('[DEBUG] Raw response body:', txt);
    throw errors.providerError('Invalid JSON response from Supabase Edge Function');
  }

  const msg = data.choices?.[0]?.message || { role: 'assistant', content: '' };
  const u = data.usage || {}; // { prompt_tokens, completion_tokens, total_tokens }

  // Parse tool_calls if present
  let toolUses;
  if (msg.tool_calls && Array.isArray(msg.tool_calls) && msg.tool_calls.length > 0) {
    toolUses = msg.tool_calls.map(tc => {
      try {
        return {
          type: 'tool_use',
          id: tc.id,
          name: tc.function?.name,
          input: JSON.parse(tc.function?.arguments || '{}')
        };
      } catch (parseErr) {
        console.error('Failed to parse tool call arguments:', parseErr);
        return {
          type: 'tool_use',
          id: tc.id,
          name: tc.function?.name,
          input: {}
        };
      }
    });
  }

  return {
    id: data.id,
    provider: 'gpt',
    created: Math.floor(Date.now() / 1000),
    message: msg,
    tool_uses: toolUses,
    usage: {
      prompt_tokens: u.prompt_tokens ?? 0,
      completion_tokens: u.completion_tokens ?? 0,
      total_tokens: u.total_tokens ?? ((u.prompt_tokens ?? 0) + (u.completion_tokens ?? 0))
    }
  };
}

// Back-compat wrapper for code paths expecting { id, content, usage }
export async function chatWithOpenAI({ messages, temperature, max_tokens }) {
  const r = await openaiChat({ messages, temperature, max_tokens });
  return { id: r.id, content: r.message?.content || '', usage: r.usage, stop_reason: undefined };
}

// Minimal streaming shim: emits word chunks via onToken, built on top of non-streaming API.
export async function chat({ prompt, messages, stream = false, onToken, temperature, max_tokens, timeout_ms, tools }) {
  // Build messages if only prompt provided
  if (!messages && prompt) {
    messages = [{ role: 'user', content: String(prompt) }];
  }

  // Streaming path: Supabase Edge Function with stream=true
  if (stream && typeof onToken === 'function') {
    try {
      if (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) {
        throw errors.notConfigured('Supabase Edge Functions');
      }
      // Supabase Edge Function URL
      const API = `${process.env.SUPABASE_URL}/functions/v1/openai-proxy`;

      const body = {
        model: process.env.OPENAI_MODEL || 'gpt-4o-mini',
        messages,
        temperature: temperature ?? 0,
        max_tokens: max_tokens ?? env.AI_MAX_TOKENS,
        stream: true,
      };

      const r = await fetch(API, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'authorization': `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
        },
        body: JSON.stringify(body),
      });

      if (!r.ok) {
        const txt = await r.text(); // Read error body
        console.error(`[DEBUG] Streaming Supabase Edge Function failed: ${r.status} ${r.statusText}`);
        console.error(`[DEBUG] Response body: ${txt}`);
        throw errors.providerError(`Supabase Edge Function ${r.status}: ${txt.slice(0, 100)}`);
      }

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
          const line = chunk.startsWith('data: ') ? chunk.slice(6).trim() : null;
          if (!line) continue;
          if (line === '[DONE]') continue;
          try {
            const json = JSON.parse(line);
            const delta = json?.choices?.[0]?.delta?.content || '';
            if (delta) { try { onToken(delta); } catch { } }
          } catch { /* ignore parse errors */ }
        }
      }
      return { text: undefined };
    } catch (err) {
      console.error('[DEBUG] Streaming error:', err);
      throw err;
    }
  }

  // Non-streaming path
  const result = await openaiChat({ messages, temperature, max_tokens, timeout_ms, tools });
  const text = result?.message?.content || '';
  return { text, usage: result?.usage };
}

async function safeText(res) { try { return await res.text(); } catch { return ''; } }

function clampTimeout(v) {
  const n = parseInt(v ?? env.AI_TIMEOUT_MS, 10);
  return Math.max(3000, Math.min(env.AI_TIMEOUT_MS_MAX ?? 60000, isNaN(n) ? env.AI_TIMEOUT_MS : n));
}
