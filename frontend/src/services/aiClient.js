/**
 * aiClient: Unified AI chat client for the gateway
 * Endpoint: POST /api/ai/chat
 */
import { buildStandardHeaders, resolveDeviceId } from '../utils/identity'

const sleep = (ms) => new Promise(r => setTimeout(r, ms))

export async function chat({
  provider = 'claude',
  messages,
  temperature,
  max_tokens,
  timeout_ms,
  metadata,
  scope = 'state',
  deviceId = resolveDeviceId(),
  panel,
  tools
} = {}) {
  if (!Array.isArray(messages) || messages.length === 0) {
    throw new Error('messages[] is required')
  }

  const headers = buildStandardHeaders({
    panel: panel || 'ai',
    scope,
    extraHeaders: {
      'content-type': 'application/json'
    }
  })
  if (typeof deviceId === 'string') {
    headers['x-device-id'] = deviceId
  }

  const doPost = async () => {
    const res = await fetch('/api/ai/chat', {
      method: 'POST',
      headers,
      body: JSON.stringify({ provider, messages, temperature, max_tokens, timeout_ms, metadata, tools })
    })
    const body = await res.json().catch(() => ({}))
    return { ok: res.ok, status: res.status, body }
  }

  // One retry on 429 using server-provided hint
  let { ok, status, body } = await doPost()
  if (!ok && status === 429 && body?.retry_after_ms) {
    await sleep(Math.max(250, Math.min(5000, body.retry_after_ms)))
    ;({ ok, status, body } = await doPost())
  }
  if (!ok) {
    if (body && typeof body === 'object') {
      body.status = status
      throw body
    }
    const error = new Error('AI request failed')
    error.status = status
    throw error
  }
  return body // normalized success shape
}
