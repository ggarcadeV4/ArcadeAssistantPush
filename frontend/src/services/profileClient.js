// Use gateway port 8787 in dev mode, or current origin in production
import { getGatewayUrl } from './gateway'
import { buildStandardHeaders, resolveDeviceId } from '../utils/identity'
const GATEWAY = getGatewayUrl()

export async function getProfile() {
  const r = await fetch(`${GATEWAY}/api/local/profile`, {
    headers: buildStandardHeaders({
      panel: 'voice',
      scope: 'state',
      extraHeaders: { 'content-type': 'application/json' }
    })
  })
  if (!r.ok) throw await r.json().catch(() => ({ error: 'profile_get_failed' }))
  return r.json()
}

export async function getPrimaryProfile() {
  const r = await fetch(`${GATEWAY}/api/local/profile/primary`, {
    headers: buildStandardHeaders({
      panel: 'voice',
      scope: 'state',
      extraHeaders: { 'content-type': 'application/json' }
    })
  })
  if (!r.ok) throw await r.json().catch(() => ({ error: 'profile_primary_get_failed' }))
  return r.json()
}

export async function previewProfile(profile) {
  const r = await fetch(`${GATEWAY}/api/local/profile/preview`, {
    method: 'POST',
    headers: buildStandardHeaders({
      panel: 'voice',
      scope: 'state',
      extraHeaders: { 'content-type': 'application/json' }
    }),
    body: JSON.stringify(profile)
  })
  if (!r.ok) throw await r.json().catch(() => ({ error: 'profile_preview_failed' }))
  return r.json()
}

export async function applyProfile(profile, { deviceId, panel = 'voice' } = {}) {
  const resolvedDeviceId = deviceId || resolveDeviceId()
  const r = await fetch(`${GATEWAY}/api/local/profile/apply`, {
    method: 'POST',
    headers: {
      ...buildStandardHeaders({
        panel,
        scope: 'state',
        extraHeaders: { 'content-type': 'application/json' }
      }),
      'x-device-id': resolvedDeviceId
    },
    body: JSON.stringify(profile)
  })
  if (!r.ok) throw await r.json().catch(() => ({ error: 'profile_apply_failed' }))
  return r.json()
}

export async function getConsent() {
  const r = await fetch(`${GATEWAY}/api/local/consent`, {
    headers: buildStandardHeaders({
      panel: 'voice',
      scope: 'state',
      extraHeaders: { 'content-type': 'application/json' }
    })
  })
  if (!r.ok) throw await r.json().catch(() => ({ error: 'consent_get_failed' }))
  return r.json()
}

export async function previewConsent(consent) {
  const r = await fetch(`${GATEWAY}/api/local/consent/preview`, {
    method: 'POST',
    headers: buildStandardHeaders({
      panel: 'voice',
      scope: 'state',
      extraHeaders: { 'content-type': 'application/json' }
    }),
    body: JSON.stringify(consent)
  })
  if (!r.ok) throw await r.json().catch(() => ({ error: 'consent_preview_failed' }))
  return r.json()
}

export async function applyConsent(consent, { deviceId, panel = 'voice' } = {}) {
  const resolvedDeviceId = deviceId || resolveDeviceId()
  const r = await fetch(`${GATEWAY}/api/local/consent/apply`, {
    method: 'POST',
    headers: {
      ...buildStandardHeaders({
        panel,
        scope: 'state',
        extraHeaders: { 'content-type': 'application/json' }
      }),
      'x-device-id': resolvedDeviceId
    },
    body: JSON.stringify(consent)
  })
  if (!r.ok) throw await r.json().catch(() => ({ error: 'consent_apply_failed' }))
  return r.json()
}
