import { getGatewayWsUrl } from '../services/gateway'
import { resolveDeviceId } from './identity'

const normalizePrefix = (value = 'ws') => {
  const normalized = String(value || 'ws')
    .trim()
    .replace(/[^a-z0-9_-]+/gi, '-')
    .replace(/^-+|-+$/g, '')
  return normalized || 'ws'
}

export function generateCorrelationId(prefix = 'ws') {
  const normalizedPrefix = normalizePrefix(prefix)
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return `${normalizedPrefix}-${crypto.randomUUID()}`
    }
  } catch {}

  return `${normalizedPrefix}-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`
}

export function buildGatewayWsIdentityUrl(path, { deviceId, panel = '', corrId } = {}) {
  const url = new URL(getGatewayWsUrl(path))
  const resolvedDeviceId = typeof deviceId === 'string' ? deviceId.trim() : resolveDeviceId()
  const resolvedPanel = typeof panel === 'string' ? panel.trim() : ''
  const resolvedCorrId =
    typeof corrId === 'string' && corrId.trim()
      ? corrId.trim()
      : generateCorrelationId(resolvedPanel || 'ws')

  if (resolvedDeviceId) {
    url.searchParams.set('device', resolvedDeviceId)
  } else {
    url.searchParams.delete('device')
  }

  if (resolvedPanel) {
    url.searchParams.set('panel', resolvedPanel)
  } else {
    url.searchParams.delete('panel')
  }

  url.searchParams.set('corr_id', resolvedCorrId)
  return url.toString()
}
