/**
 * deweySearchClient: Calls the gateway's Dewey Historian search endpoint
 * for internet-backed arcade lore retrieval.
 */

import { getGatewayUrl } from './gateway'
import { buildStandardHeaders } from '../utils/identity'
const GATEWAY = getGatewayUrl()

export async function searchArcadeLore(query) {
  if (!query || typeof query !== 'string' || query.trim().length === 0) {
    return { items: [] }
  }

  const res = await fetch(`${GATEWAY}/api/dewey/search`, {
    method: 'POST',
    headers: buildStandardHeaders({
      panel: 'dewey',
      scope: 'state',
      extraHeaders: { 'content-type': 'application/json' }
    }),
    body: JSON.stringify({ query: query.trim() })
  })

  if (!res.ok) {
    console.warn('[Dewey Search] Request failed:', res.status)
    return { items: [] }
  }

  return res.json()
}
