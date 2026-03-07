import { env, ensureConfigured, clamp } from '../config/env.js';
import { errors, toJson } from '../lib/errors.js';
import anthropicChat, { chat as streamAnthropic } from '../adapters/anthropic.js';
import openaiChat, { chat as streamOpenAI } from '../adapters/openai.js';
import geminiChat from '../adapters/gemini.js';
import { sendTelemetry } from '../services/supabase_client.js';


// Function-style registration per spec
export default function registerAIRoutes(app) {
  // Primary unified AI chat endpoint
  app.post('/api/ai/chat', async (req, res) => {
    try {
      // x-scope is preferred but not required (legacy clients may omit it)
      const scope = req.header('x-scope') || 'state';

      let { provider = env.AI_DEFAULT_PROVIDER, messages, message, systemPrompt, temperature, max_tokens, timeout_ms, metadata, tools, system } = req.body || {};

      // Support legacy clients that send { message: "text" } instead of { messages: [...] }
      if (!Array.isArray(messages) || messages.length === 0) {
        const singleMsg = message || (typeof req.body?.prompt === 'string' ? req.body.prompt : null);
        if (singleMsg && typeof singleMsg === 'string') {
          messages = [{ role: 'user', content: singleMsg }];
          // Also pick up systemPrompt if system wasn't set
          if (!system && systemPrompt) system = systemPrompt;
        } else {
          throw errors.badRequest('messages[] or message required');
        }
      }

      // Golden Drive: Auto-fallback to Gemini when Claude/GPT not configured
      // This allows cabinets to use Gemini as primary brain via Supabase secrets
      if ((provider === 'claude' || provider === 'anthropic') && !process.env.ANTHROPIC_API_KEY) {
        console.log('[AI] Claude key not in local .env, using Supabase proxy (Gemini fallback available)');
      }

      if (!ensureConfigured(provider)) {
        // Try Gemini as fallback
        console.log(`[AI] Provider ${provider} not configured, attempting Gemini fallback`);
        provider = 'gemini';
        if (!ensureConfigured(provider)) throw errors.notConfigured(provider);
      }

      const input = { messages, temperature, max_tokens, timeout_ms, metadata, tools, system };
      let out;
      const startTime = Date.now();
      if (provider === 'gpt' || provider === 'openai') {
        out = await openaiChat(input);
      } else if (provider === 'gemini' || provider === 'google') {
        out = await geminiChat(input);
      } else {
        // Default to anthropic (Claude)
        out = await anthropicChat(input);
      }
      const latencyMs = Date.now() - startTime;

      // Send AI telemetry (fire-and-forget)
      const cabinetId = req.headers['x-device-id'] || process.env.AA_DEVICE_ID;
      if (cabinetId) {
        sendTelemetry(cabinetId, 'INFO', 'AI_CALL', `${provider} chat: ${latencyMs}ms`, {
          provider,
          model: out.model || out.message?.model || 'unknown',
          latency_ms: latencyMs,
          input_tokens: out.usage?.prompt_tokens || out.usage?.input_tokens || null,
          output_tokens: out.usage?.completion_tokens || out.usage?.output_tokens || null
        }, req.body.panel || 'api').catch(() => { });
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
      const scope = req.header('x-scope') || 'state'; // default if missing
      const body = req.body || {};
      let { messages, temperature, max_tokens, timeout_ms, metadata } = body;

      if (!Array.isArray(messages)) {
        const prompt = typeof body.prompt === 'string' ? body.prompt : undefined;
        const system = typeof body.system === 'string' ? body.system : undefined;
        if (prompt && prompt.trim().length > 0) {
          messages = [];
          if (system && system.trim().length > 0) {
            messages.push({ role: 'system', content: system.trim() });
          }
          messages.push({ role: 'user', content: prompt.trim() });
        }
      }

      if (!Array.isArray(messages) || messages.length === 0) {
        throw errors.badRequest('messages[] required');
      }
      if (!ensureConfigured('claude')) throw errors.notConfigured('claude');

      const effectiveTimeout = clamp(parseInt(timeout_ms || env.AI_TIMEOUT_MS, 10), 3000, env.AI_TIMEOUT_MS_MAX);
      const startTime = Date.now();
      const out = await anthropicChat({ messages, temperature, max_tokens, timeout_ms: effectiveTimeout, metadata });
      const latencyMs = Date.now() - startTime;

      // Send AI telemetry (fire-and-forget)
      const cabinetId = req.headers['x-device-id'] || process.env.AA_DEVICE_ID;
      const modelUsed = process.env.ANTHROPIC_MODEL || 'claude-3-7-sonnet-latest';
      if (cabinetId) {
        sendTelemetry(cabinetId, 'INFO', 'AI_CALL', `anthropic ${modelUsed}: ${latencyMs}ms`, {
          provider: 'anthropic',
          model: modelUsed,
          latency_ms: latencyMs,
          input_tokens: out.usage?.prompt_tokens || null,
          output_tokens: out.usage?.completion_tokens || null
        }, 'legacy_api').catch(() => { });
      }

      return res.status(200).json({
        response: out.message?.content || '',
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
