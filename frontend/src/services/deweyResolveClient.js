/**
 * deweyResolveClient: Calls the gateway's deterministic media resolver.
 * 
 * This is called IN PARALLEL with Dewey's chat — it extracts the game
 * subject from the user's raw message using the LaunchBox index (no AI),
 * and returns local media assets.
 * 
 * This replaces the fragile searchArcadeLore-based image pipeline.
 */

import { getGatewayUrl } from './gateway'

const GATEWAY = getGatewayUrl()

function buildResolvePayload(input) {
  if (typeof input === 'string') {
    const message = input.trim()
    return message ? { message } : null
  }

  if (!input || typeof input !== 'object') {
    return null
  }

  const message = typeof input.message === 'string' ? input.message.trim() : ''
  if (!message) return null

  const payload = { message }
  const activeTitle = typeof input.active_title === 'string' ? input.active_title.trim() : ''
  const activePlatform = typeof input.active_platform === 'string' ? input.active_platform.trim() : ''
  const activeVisualIntent = typeof input.active_visual_intent === 'string' ? input.active_visual_intent.trim() : ''

  if (activeTitle) payload.active_title = activeTitle
  if (activePlatform) payload.active_platform = activePlatform
  if (activeVisualIntent) payload.active_visual_intent = activeVisualIntent

  return payload
}

export async function resolveGameMedia(input) {
  const payload = buildResolvePayload(input)
  if (!payload) {
    return { found: false, game: null, images: [], source: 'none' }
  }

  try {
    const res = await fetch(`${GATEWAY}/api/dewey/resolve`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-panel': 'dewey',
        'x-scope': 'state'
      },
      body: JSON.stringify(payload)
    })

    if (!res.ok) {
      console.warn('[Dewey Resolve] Request failed:', res.status)
      return { found: false, game: null, images: [], source: 'none' }
    }

    return res.json()
  } catch (err) {
    console.warn('[Dewey Resolve] Network error:', err?.message || err)
    return { found: false, game: null, images: [], source: 'none' }
  }
}
