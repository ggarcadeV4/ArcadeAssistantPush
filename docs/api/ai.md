# AI Chat API

Path: POST /api/ai/chat

Headers
- Content-Type: application/json
- x-scope: state (required)

Request Body
{
  "provider": "claude" | "gpt",         // default "claude"
  "messages": [
    { "role": "system" | "user" | "assistant", "content": "..." }
  ],
  "temperature": 0.0,
  "max_tokens": 1024,
  "timeout_ms": 20000,
  "metadata": { "panel": "led-blinky", "requestId": "..." }
}

Response 200 (normalized)
{
  "id": "chat_01H...",
  "provider": "claude",
  "created": 1738000000,
  "message": { "role": "assistant", "content": "..." },
  "usage": { "prompt_tokens": 123, "completion_tokens": 456, "total_tokens": 579 }
}

Errors (JSON)
- 400 { "code":"BAD_REQUEST", "message":"...", "details": { ... } }
- 401 { "code":"UNAUTHORIZED", "message":"Missing or invalid credentials" }
- 429 { "code":"RATE_LIMITED", "message":"...", "retry_after_ms": 5000 }
- 500 { "code":"PROVIDER_ERROR", "message":"Upstream error", "request_id":"rqd_..." }
- 501 { "code":"NOT_CONFIGURED", "message":"Provider not configured" }

Rate limits & timeouts
- Per-request timeout_ms is clamped to [3000, AI_TIMEOUT_MS_MAX].
- Exponential backoff on 429 (base AI_RETRY_BASE_MS, up to AI_RETRY_MAX_ATTEMPTS).

Redaction policy
- Never log API keys, Authorization headers, or full prompts.
- Redact email/phone/IP with *** in traces.
- Keep request_id, provider, latency, token counts.

Streaming (optional)
- GET /api/ai/chat/stream (SSE) — currently returns 501 Not Implemented.

