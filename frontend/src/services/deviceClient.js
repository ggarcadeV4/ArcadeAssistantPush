import { buildStandardHeaders } from '../utils/identity'

const BASE_LOCAL = '/api/local'
const CONTROLLER_BASE = `${BASE_LOCAL}/controller`

const controllerHeaders = (scope = 'state', json = false) =>
  buildStandardHeaders({
    panel: 'controller',
    scope,
    extraHeaders: json ? { 'Content-Type': 'application/json' } : {}
  })

export async function fetchDeviceSnapshot() {
  const res = await fetch(`${BASE_LOCAL}/devices/snapshot`, {
    headers: controllerHeaders('state')
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail?.detail || 'Failed to fetch device snapshot')
  }
  return res.json()
}

export async function classifyDevice({ deviceId, role, label, panels = [] }) {
  const res = await fetch(`${BASE_LOCAL}/devices/classify`, {
    method: 'POST',
    headers: controllerHeaders('config', true),
    body: JSON.stringify({
      device_id: deviceId,
      role,
      label,
      panels
    })
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail?.detail || 'Failed to classify device')
  }
  return res.json()
}

export async function refreshControllerDevices() {
  const res = await fetch(`${BASE_LOCAL}/controller/refresh`, {
    method: 'POST',
    headers: controllerHeaders('state', true)
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail?.detail || 'Failed to refresh controller devices')
  }
  return res.json()
}

export async function startWiringWizard() {
  const res = await fetch(`${CONTROLLER_BASE}/wizard/start`, {
    method: 'POST',
    headers: controllerHeaders('state')
  })
  if (!res.ok) throw new Error('Failed to start wizard')
  return res.json()
}

export async function fetchWizardNextStep() {
  const res = await fetch(`${CONTROLLER_BASE}/wizard/next-step`, {
    method: 'POST',
    headers: controllerHeaders('state')
  })
  if (!res.ok) throw new Error('Failed to fetch wizard step')
  return res.json()
}

export async function captureWizardInput(controlKey, pin, controlType) {
  const res = await fetch(`${CONTROLLER_BASE}/wizard/capture`, {
    method: 'POST',
    headers: controllerHeaders('state', true),
    body: JSON.stringify({
      control_key: controlKey,
      pin,
      control_type: controlType
    })
  })
  if (!res.ok) throw new Error('Failed to capture wizard input')
  return res.json()
}

export async function previewWizardMapping() {
  const res = await fetch(`${CONTROLLER_BASE}/wizard/preview`, {
    method: 'POST',
    headers: controllerHeaders('state')
  })
  if (!res.ok) throw new Error('Failed to preview wizard mapping')
  return res.json()
}

export async function applyWizardMapping() {
  const res = await fetch(`${CONTROLLER_BASE}/wizard/apply`, {
    method: 'POST',
    headers: controllerHeaders('config')
  })
  if (!res.ok) throw new Error('Failed to apply wizard mapping')
  return res.json()
}

export async function fetchDiagnosticsEvent() {
  const res = await fetch(`${BASE_LOCAL}/controller/diagnostics/next-event`, {
    headers: controllerHeaders('state')
  })
  if (!res.ok) throw new Error('Failed to fetch diagnostics event')
  return res.json()
}

export async function startLearnWizard({ player } = {}) {
  let url = `${CONTROLLER_BASE}/learn-wizard/start`
  if (player) {
    url += `?player=${player}`
  }
  const res = await fetch(url, {
    method: 'POST',
    headers: controllerHeaders('state')
  })
  if (!res.ok) throw new Error('Failed to start learn wizard')
  return res.json()
}

export async function getLearnWizardStatus() {
  const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/status`, {
    headers: controllerHeaders('state')
  })
  if (!res.ok) throw new Error('Failed to get learn wizard status')
  return res.json()
}

export async function confirmLearnWizardCapture() {
  const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/confirm`, {
    method: 'POST',
    headers: controllerHeaders('state')
  })
  if (!res.ok) throw new Error('Failed to confirm capture')
  return res.json()
}

export async function skipLearnWizardControl() {
  const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/skip`, {
    method: 'POST',
    headers: controllerHeaders('state')
  })
  if (!res.ok) throw new Error('Failed to skip control')
  return res.json()
}

export async function saveLearnWizard() {
  const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/save`, {
    method: 'POST',
    headers: controllerHeaders('config')
  })
  if (!res.ok) throw new Error('Failed to save wizard mappings')
  return res.json()
}

export async function stopLearnWizard() {
  const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/stop`, {
    method: 'POST',
    headers: controllerHeaders('state')
  })
  if (!res.ok) throw new Error('Failed to stop wizard')
  return res.json()
}

export async function setLearnWizardKey(keycode) {
  const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/set-key`, {
    method: 'POST',
    headers: controllerHeaders('state', true),
    body: JSON.stringify({ keycode })
  })
  if (!res.ok) throw new Error('Failed to set key')
  return res.json()
}

export async function undoLearnWizardCapture() {
  const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/undo`, {
    method: 'POST',
    headers: controllerHeaders('state')
  })
  if (!res.ok) throw new Error('Failed to undo capture')
  return res.json()
}

export async function resetMappingToDefault() {
  const res = await fetch(`${CONTROLLER_BASE}/mapping/reset`, {
    method: 'POST',
    headers: controllerHeaders('config')
  })
  if (!res.ok) throw new Error('Failed to reset mappings')
  return res.json()
}
