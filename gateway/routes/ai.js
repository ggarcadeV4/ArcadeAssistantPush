import { env, ensureConfigured, clamp } from '../config/env.js';
import { errors, toJson } from '../lib/errors.js';
import anthropicChat, { chat as streamAnthropic } from '../adapters/anthropic.js';
import openaiChat, { chat as streamOpenAI } from '../adapters/openai.js';
import geminiChat from '../adapters/gemini.js';
import { sendTelemetry } from '../services/supabase_client.js';

function normalizeProvider(provider) {
  const p = String(provider || '').toLowerCase().trim();
  if (p === 'openai') return 'gpt';
  if (p === 'google') return 'gemini';
  if (p === 'anthropic') return 'claude';
  return p || 'claude';
}

function normalizeLegacyMessages(body = {}) {
  if (Array.isArray(body.messages) && body.messages.length > 0) {
    return body.messages;
  }

  const out = [];
  const sys = [
    body.system,
    body.systemPrompt,
    body.system_prompt
  ].find((v) => typeof v === 'string' && v.trim().length > 0);

  if (sys) {
    out.push({ role: 'system', content: sys.trim() });
  }

  if (Array.isArray(body.history)) {
    for (const item of body.history) {
      if (!item || typeof item !== 'object') continue;
      const role = item.role === 'assistant' ? 'assistant' : 'user';
      const content = typeof item.content === 'string'
        ? item.content
        : (typeof item.message === 'string' ? item.message : '');
      if (content.trim()) {
        out.push({ role, content: content.trim() });
      }
    }
  }

  const promptLike = [
    body.message,
    body.prompt,
    body.input
  ].find((v) => typeof v === 'string' && v.trim().length > 0);

  if (promptLike) {
    out.push({ role: 'user', content: promptLike.trim() });
  }

  return out;
}

function responseText(out = {}) {
  const c = out?.message?.content;
  if (typeof c === 'string') return c;
  if (Array.isArray(c)) {
    return c
      .map((item) => item?.text || item?.content || '')
      .filter(Boolean)
      .join('\n')
      .trim();
  }
  return '';
}

async function executeChat(provider, input) {
  if (provider === 'gpt') {
    return openaiChat(input);
  }
  if (provider === 'gemini') {
    return geminiChat(input);
  }
  return anthropicChat(input);
}

function shouldFallbackToGemini(provider, err) {
  if (provider !== 'claude') return false;
  const message = String(err?.message || '');
  const code = String(err?.code || '');
  return /model.*not\s*found/i.test(message) || /anthropic 404/i.test(message) || code === 'PROVIDER_ERROR';
}

// Function-style registration per spec
export default function registerAIRoutes(app) {
  // Primary unified AI chat endpoint
  app.post('/api/ai/chat', async (req, res) => {
    try {
      const scope = req.header('x-scope');
      if (scope && scope !== 'state') throw errors.badRequest('x-scope must be "state" when provided');

      const body = req.body || {};
      let {
        provider = env.AI_DEFAULT_PROVIDER,
        temperature,
        max_tokens,
        timeout_ms,
        metadata,
        tools,
        system
      } = body;
      const requestedProvider = normalizeProvider(provider);
      provider = requestedProvider;

      const messages = normalizeLegacyMessages(body);
      if (!Array.isArray(messages) || messages.length === 0) throw errors.badRequest('messages[] required');

      if (!system && typeof body.systemPrompt === 'string' && body.systemPrompt.trim()) {
        system = body.systemPrompt.trim();
      }

      // Golden Drive: Auto-fallback to Gemini when Claude/GPT not configured
      // This allows cabinets to use Gemini as primary brain via Supabase secrets
      if (provider === 'claude' && !process.env.ANTHROPIC_API_KEY) {
        console.log('[AI] Claude key not in local .env, using Supabase proxy (Gemini fallback available)');
      }

      if (!ensureConfigured(provider)) {
        // Try Gemini as fallback
        console.log(`[AI] Provider ${provider} not configured, attempting Gemini fallback`);
        provider = 'gemini';
        if (!ensureConfigured(provider)) throw errors.notConfigured(provider);
      }

      const input = { messages, temperature, max_tokens, timeout_ms, metadata, tools, system };
      let out = null;
      let usedProvider = provider;
      const startTime = Date.now();

      try {
        out = await executeChat(provider, input);
      } catch (err) {
        if (shouldFallbackToGemini(provider, err) && ensureConfigured('gemini')) {
          console.warn(`[AI] ${provider} failed (${err.message}); retrying with gemini`);
          usedProvider = 'gemini';
          out = await executeChat('gemini', input);
        } else {
          throw err;
        }
      }
      const latencyMs = Date.now() - startTime;
      const modelUsed = out.model
        || out.message?.model
        || (usedProvider === 'gemini'
          ? (process.env.GEMINI_MODEL || 'gemini-2.0-flash')
          : usedProvider === 'gpt'
            ? (process.env.OPENAI_MODEL || 'gpt-4o-mini')
            : (process.env.ANTHROPIC_MODEL || 'claude-3-7-sonnet-latest'));

      console.log(`[AI] provider requested=${requestedProvider} used=${usedProvider} model=${modelUsed} latency=${latencyMs}ms`);

      // Send AI telemetry (fire-and-forget)
      const cabinetId = req.headers['x-device-id'] || process.env.AA_DEVICE_ID;
      if (cabinetId) {
        sendTelemetry(cabinetId, 'INFO', 'AI_CALL', `${usedProvider} chat: ${latencyMs}ms`, {
          provider: usedProvider,
          model: modelUsed,
          latency_ms: latencyMs,
          input_tokens: out.usage?.prompt_tokens || out.usage?.input_tokens || null,
          output_tokens: out.usage?.completion_tokens || out.usage?.output_tokens || null
        }, body.panel || 'api').catch(() => { });
      }

      res.status(200).json(out);
    } catch (err) {
      const { status, body } = toJson(err);
      res.status(status).json(body);
    }
  });

  // Legacy alias for backward compatibility: /api/local/claude/chat
  // Returns { response, model, usage } format for older clients
  app.post('/api/local/claude/chat', async (req, res) => {
    try {
      const scope = req.header('x-scope');
      if (scope && scope !== 'state') {
        throw errors.badRequest('x-scope must be "state" when provided');
      }

      const body = req.body || {};
      const { temperature, max_tokens, timeout_ms, metadata } = body;
      const messages = normalizeLegacyMessages(body);

      if (!Array.isArray(messages) || messages.length === 0) {
        throw errors.badRequest('messages[] required');
      }

      const effectiveTimeout = clamp(parseInt(timeout_ms || env.AI_TIMEOUT_MS, 10), 3000, env.AI_TIMEOUT_MS_MAX);
      const startTime = Date.now();
      let out = null;
      let usedProvider = 'claude';

      try {
        if (!ensureConfigured('claude')) throw errors.notConfigured('claude');
        out = await anthropicChat({ messages, temperature, max_tokens, timeout_ms: effectiveTimeout, metadata });
      } catch (err) {
        if (shouldFallbackToGemini('claude', err) && ensureConfigured('gemini')) {
          console.warn(`[AI] legacy claude route failed (${err.message}); retrying with gemini`);
          usedProvider = 'gemini';
          out = await geminiChat({ messages, temperature, max_tokens, timeout_ms: effectiveTimeout, metadata });
        } else if (!ensureConfigured('claude') && ensureConfigured('gemini')) {
          console.warn('[AI] legacy claude route not configured; using gemini');
          usedProvider = 'gemini';
          out = await geminiChat({ messages, temperature, max_tokens, timeout_ms: effectiveTimeout, metadata });
        } else {
          throw err;
        }
      }

      const latencyMs = Date.now() - startTime;

      // Send AI telemetry (fire-and-forget)
      const cabinetId = req.headers['x-device-id'] || process.env.AA_DEVICE_ID;
      const modelUsed = usedProvider === 'gemini'
        ? (process.env.GEMINI_MODEL || 'gemini-2.0-flash')
        : (process.env.ANTHROPIC_MODEL || 'claude-3-7-sonnet-latest');
      if (cabinetId) {
        sendTelemetry(cabinetId, 'INFO', 'AI_CALL', `${usedProvider} ${modelUsed}: ${latencyMs}ms`, {
          provider: usedProvider,
          model: modelUsed,
          latency_ms: latencyMs,
          input_tokens: out.usage?.prompt_tokens || null,
          output_tokens: out.usage?.completion_tokens || null
        }, 'legacy_api').catch(() => { });
      }

      return res.status(200).json({
        response: responseText(out),
        model: modelUsed,
        usage: out.usage || { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 }
      });
    } catch (err) {
      const { status, body } = toJson(err);
      return res.status(status).json(body);
    }
  });

  // SSE endpoint (streams via provider; falls back to 501 when not configured)
  app.get('/api/ai/chat/stream', async (req, res) => {
    const configured = !!(process.env.ANTHROPIC_API_KEY || process.env.OPENAI_API_KEY);
    if (!configured) {
      res.status(501).json({ code: 'NOT_CONFIGURED' });
      return;
    }

    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive'
    });

    const write = (t) => res.write(`data: ${JSON.stringify({ chunk: t })}\n\n`);
    const end = () => { try { res.write('event: end\n'); res.write('data: {}\n\n'); } catch { } try { res.end(); } catch { } };

    // Abort if client disconnects
    req.on('close', () => { try { end(); } catch { } });

    // Safety: cap stream duration
    const killer = setTimeout(() => {
      try { res.write(`data: ${JSON.stringify({ error: 'timeout' })}\n\n`); } catch { }
      end();
    }, Number(process.env.SSE_MAX_MS || 60000));

    try {
      const provider = process.env.ANTHROPIC_API_KEY ? 'anthropic' : 'openai';
      const prompt = (req.query.q ?? '').toString();
      const streamFn = provider === 'anthropic' ? streamAnthropic : streamOpenAI;
      await streamFn({ prompt, stream: true, onToken: write });
      end();
    } catch (e) {
      res.write(`data: ${JSON.stringify({ error: String(e) })}\n\n`);
      end();
    } finally {
      clearTimeout(killer);
    }
  });
}
