// Use gateway port 8787 in dev mode, or current origin in production
import { getGatewayUrl } from './gateway'
const GATEWAY = getGatewayUrl()

function getProfileDeviceId() {
  return window.AA_DEVICE_ID || (() => {
    console.warn('[Vicky] window.AA_DEVICE_ID not available, ' +
      'falling back to CAB-001. Cabinet identity may not be unique.')
    return 'CAB-001'
  })()
}

export async function getProfile() {
  const r = await fetch(`${GATEWAY}/api/local/profile`, { headers: { 'content-type': 'application/json', 'x-panel': 'voice' } })
  if (!r.ok) throw await r.json().catch(() => ({ error: 'profile_get_failed' }))
  return r.json()
}

export async function getPrimaryProfile() {
  const r = await fetch(`${GATEWAY}/api/local/profile/primary`, { headers: { 'content-type': 'application/json', 'x-panel': 'voice' } })
  if (!r.ok) throw await r.json().catch(() => ({ error: 'profile_primary_get_failed' }))
  return r.json()
}

export async function previewProfile(profile) {
  const r = await fetch(`${GATEWAY}/api/local/profile/preview`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-panel': 'voice',
      'x-scope': 'state'
    },
    body: JSON.stringify(profile)
  })
  if (!r.ok) throw await r.json().catch(() => ({ error: 'profile_preview_failed' }))
  return r.json()
}

export async function applyProfile(profile, { deviceId, panel = 'voice' } = {}) {
  const resolvedDeviceId = deviceId || getProfileDeviceId()
  const r = await fetch(`${GATEWAY}/api/local/profile/apply`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-scope': 'state',
      'x-device-id': resolvedDeviceId,
      'x-panel': panel
    },
    body: JSON.stringify(profile)
  })
  if (!r.ok) throw await r.json().catch(() => ({ error: 'profile_apply_failed' }))
  return r.json()
}

export async function getConsent() {
  const r = await fetch(`${GATEWAY}/api/local/consent`, { headers: { 'content-type': 'application/json', 'x-panel': 'voice' } })
  if (!r.ok) throw await r.json().catch(() => ({ error: 'consent_get_failed' }))
  return r.json()
}

export async function previewConsent(consent) {
  const r = await fetch(`${GATEWAY}/api/local/consent/preview`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-panel': 'voice',
      'x-scope': 'state'
    },
    body: JSON.stringify(consent)
  })
  if (!r.ok) throw await r.json().catch(() => ({ error: 'consent_preview_failed' }))
  return r.json()
}

export async function applyConsent(consent, { deviceId, panel = 'voice' } = {}) {
  const resolvedDeviceId = deviceId || getProfileDeviceId()
  const r = await fetch(`${GATEWAY}/api/local/consent/apply`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-scope': 'state',
      'x-device-id': resolvedDeviceId,
      'x-panel': panel
    },
    body: JSON.stringify(consent)
  })
  if (!r.ok) throw await r.json().catch(() => ({ error: 'consent_apply_failed' }))
  return r.json()
}
