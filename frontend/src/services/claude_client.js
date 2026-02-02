/**
 * @service: Claude API Client (Frontend)
 * @role: Wrapper for Claude API calls via Gateway
 * @depends_on: Gateway /api/local/claude endpoints
 */

const API_BASE = '/api/local';

export async function call_claude(prompt, system) {
  const messages = [];
  if (typeof system === 'string' && system.trim().length > 0) {
    messages.push({ role: 'system', content: system.trim() });
  }
  messages.push({ role: 'user', content: String(prompt ?? '') });

  const response = await fetch(`${API_BASE}/claude/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-scope': 'state'
    },
    body: JSON.stringify({ messages })
  });

  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const msg = result?.message || result?.error || result?.detail || 'Unknown error';
    const err = new Error(`AI request failed (${response.status}): ${msg}`);
    err.status = response.status;
    err.body = result;
    throw err;
  }

  const text =
    (result?.message && typeof result.message.content === 'string' && result.message.content) ||
    (typeof result?.output_text === 'string' ? result.output_text : '') ||
    (typeof result?.response === 'string' ? result.response : '');
  return text;
}

export async function test_claude_connection() {
  try {
    const response = await fetch(`${API_BASE}/claude/test`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return await response.json();

  } catch (error) {
    return {
      status: 'Error',
      message: error.message
    };
  }
}
