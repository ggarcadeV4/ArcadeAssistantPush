import { buildStandardHeaders } from '../utils/identity'

const BASE = '/api/local/health'

function buildDocHeaders(options = {}) {
  const scope = options.scope || 'state'
  const headers = buildStandardHeaders({ panel: 'doc', scope })
  const corrId =
    typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random()}`
  headers['x-corr-id'] = corrId
  if (options.includeJson) {
    headers['content-type'] = 'application/json'
  }
  return headers
}

async function handleResponse(res) {
  const text = await res.text()
  let payload = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = text
  }
  if (!res.ok) {
    const message =
      payload?.detail || payload?.error || payload?.message || `Request failed (${res.status})`
    const error = new Error(message)
    if (payload?.code) error.code = payload.code
    throw error
  }
  return payload
}

export async function fetchHealthSummary() {
  const res = await fetch(`${BASE}/summary`, { headers: buildDocHeaders() })
  return handleResponse(res)
}

export async function fetchGatewayHealth() {
  const res = await fetch('/api/health', { headers: buildDocHeaders() })
  return handleResponse(res)
}

export async function fetchHealthPerformance() {
  const res = await fetch(`${BASE}/performance`, { headers: buildDocHeaders() })
  return handleResponse(res)
}

export async function fetchHealthPerformanceTimeseries() {
  const res = await fetch(`${BASE}/performance/timeseries`, { headers: buildDocHeaders() })
  return handleResponse(res)
}

export async function fetchHealthProcesses() {
  const res = await fetch(`${BASE}/processes`, { headers: buildDocHeaders() })
  return handleResponse(res)
}

export async function fetchHealthHardware() {
  const res = await fetch(`${BASE}/hardware`, { headers: buildDocHeaders() })
  return handleResponse(res)
}

export async function fetchHealthAlertsActive() {
  const res = await fetch(`${BASE}/alerts/active`, { headers: buildDocHeaders() })
  return handleResponse(res)
}

export async function fetchHealthAlertsHistory() {
  const res = await fetch(`${BASE}/alerts/history`, { headers: buildDocHeaders() })
  return handleResponse(res)
}

export async function dismissHealthAlert(alertId, reason) {
  const res = await fetch(`${BASE}/alerts/${encodeURIComponent(alertId)}/dismiss`, {
    method: 'POST',
    headers: buildDocHeaders({ scope: 'state', includeJson: true }),
    body: JSON.stringify({ reason: reason || null })
  })
  return handleResponse(res)
}

export async function runOptimizeAction() {
  const res = await fetch(`${BASE}/actions/optimize`, {
    method: 'POST',
    headers: buildDocHeaders({ scope: 'state', includeJson: true }),
    body: JSON.stringify({})
  })
  return handleResponse(res)
}

export const getHealthSummary = fetchHealthSummary
export const getGatewayHealth = fetchGatewayHealth
export const getHealthPerformance = fetchHealthPerformance
export const getHealthPerformanceTimeseries = fetchHealthPerformanceTimeseries
export const getHealthProcesses = fetchHealthProcesses
export const getHealthHardware = fetchHealthHardware
export const getHealthAlertsActive = fetchHealthAlertsActive
export const getHealthAlertsHistory = fetchHealthAlertsHistory

