/**
 * deweySearchClient: Calls the gateway's Dewey Historian search endpoint
 * for internet-backed arcade lore retrieval.
 */

import { getGatewayUrl } from './gateway'
const GATEWAY = getGatewayUrl()

export async function searchArcadeLore(query) {
  if (!query || typeof query !== 'string' || query.trim().length === 0) {
    return { items: [] }
  }

  const res = await fetch(`${GATEWAY}/api/dewey/search`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-panel': 'dewey',
      'x-scope': 'state'
    },
    body: JSON.stringify({ query: query.trim() })
  })

  if (!res.ok) {
    console.warn('[Dewey Search] Request failed:', res.status)
    return { items: [] }
  }

  return res.json()
}
