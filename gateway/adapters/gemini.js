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
            console.warn('[gemini] AA_DRIVE_ROOT not set, using cwd');
        }
        const deviceIdPath = path.join(driveRoot || process.cwd(), '.aa', 'device_id.txt');
        return fs.readFileSync(deviceIdPath, 'utf-8').trim();
    } catch (e) {
        console.warn('Warning: Could not read cabinet_id:', e.message);
        return 'unknown-cabinet';
    }
}

export default async function geminiChat({ messages, temperature, max_tokens, timeout_ms, system, tools }) {
    // Supabase Edge Function URL
    const API = `${process.env.SUPABASE_URL}/functions/v1/gemini-proxy`;

    // Check for Supabase configuration
    if (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) {
        throw errors.notConfigured('Supabase Edge Functions (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required)');
    }

    const body = {
        model: process.env.GEMINI_MODEL || 'gemini-2.0-flash',
        messages,
        temperature: temperature ?? 0.7,
        max_tokens: max_tokens ?? env.AI_MAX_TOKENS,
    };

    // Add system prompt if provided
    if (system) {
        body.system = system;
    }

    // Add tools for function calling (critical for LoRa)
    if (tools && Array.isArray(tools) && tools.length > 0) {
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
            throw errors.rateLimited('Gemini rate limited', retryAfterMs);
        }
        throw errors.providerError(`Gemini ${res.status}: ${txt?.slice(0, 200)}`);
    }

    const data = await res.json();

    // Preserve full content array for tool-use flows
    // The proxy returns Claude-compatible format with type='text' and type='tool_use' blocks
    const content = data.content || [];
    const textBlock = content.find?.(c => c.type === 'text');
    const text = textBlock?.text ?? '';
    const hasToolUse = content.some(c => c.type === 'tool_use');

    const usage = data.usage || {};
    const latencyMs = Date.now() - startTime;
    const modelUsed = body.model;

    // Send AI telemetry (fire-and-forget)
    const cabinetId = readCabinetId();
    sendTelemetry(cabinetId, 'INFO', 'AI_CALL', `gemini ${modelUsed}: ${latencyMs}ms`, {
        provider: 'gemini',
        model: modelUsed,
        latency_ms: latencyMs,
        input_tokens: usage.input_tokens || null,
        output_tokens: usage.output_tokens || null
    }, 'adapter').catch(() => { });

    return {
        id: data.id,
        provider: 'gemini',
        model: modelUsed,
        created: Math.floor(Date.now() / 1000),
        // For tool-use responses, return full content array; otherwise use simple text
        message: hasToolUse
            ? { role: 'assistant', content }
            : { role: 'assistant', content: text },
        content,  // Always expose raw content array for executeToolCallingLoop
        stop_reason: data.stop_reason,
        usage: {
            prompt_tokens: usage.input_tokens ?? 0,
            completion_tokens: usage.output_tokens ?? 0,
            total_tokens: (usage.input_tokens ?? 0) + (usage.output_tokens ?? 0)
        }
    };
}

// Back-compat wrapper for code paths expecting { id, content, usage }
export async function chatWithGemini({ messages, temperature, max_tokens, timeoutMs }) {
    const r = await geminiChat({ messages, temperature, max_tokens, timeout_ms: timeoutMs });
    return { id: r.id, content: r.message?.content || '', usage: r.usage, stop_reason: undefined };
}

// Minimal streaming shim: emits word chunks via onToken, built on top of non-streaming API.
export async function chat({ prompt, messages, stream = false, onToken, temperature, max_tokens, timeout_ms, system }) {
    // Build minimal messages array if only prompt provided
    if (!messages && prompt) {
        messages = [{ role: 'user', content: String(prompt) }];
    }

    // Streaming path: call Supabase Edge Function with stream=true
    if (stream && typeof onToken === 'function') {
        // Supabase Edge Function URL
        const API = `${process.env.SUPABASE_URL}/functions/v1/gemini-proxy`;

        if (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) {
            throw errors.notConfigured('Supabase Edge Functions');
        }
        const body = {
            model: process.env.GEMINI_MODEL || 'gemini-2.0-flash',
            max_tokens: max_tokens ?? env.AI_MAX_TOKENS,
            temperature: temperature ?? 0.7,
            messages,
            stream: true,
        };

        if (system) {
            body.system = system;
        }

        // Forward tools for function calling (streaming mode)
        if (tools && Array.isArray(tools) && tools.length > 0) {
            body.tools = tools;
        }

        const r = await fetch(API, {
            method: 'POST',
            headers: {
                'content-type': 'application/json',
                'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
            },
            body: JSON.stringify(body),
        });
        if (!r.ok) throw errors.providerError(`Supabase Edge Function ${r.status}`);

        // For now, Gemini proxy doesn't support streaming - fall back to non-streaming
        // and emit the full response as a single token
        const data = await r.json();
        const text = data.content?.[0]?.text || '';
        if (text) {
            try { onToken(text); } catch { }
        }
        return { text };
    }

    // Non-streaming path: reuse existing chat
    const result = await geminiChat({ messages, temperature, max_tokens, timeout_ms, system });
    const text = result?.message?.content || '';
    return { text, usage: result?.usage };
}

async function safeText(res) { try { return await res.text(); } catch { return ''; } }

function clampTimeout(v) {
    const n = parseInt(v ?? env.AI_TIMEOUT_MS, 10);
    return Math.max(3000, Math.min(env.AI_TIMEOUT_MS_MAX ?? 60000, isNaN(n) ? env.AI_TIMEOUT_MS : n));
}
