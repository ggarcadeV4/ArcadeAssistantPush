export function resolveDeviceId() {
  if (typeof window === 'undefined') {
    return ''
  }

  const runtimeDeviceId =
    typeof window.AA_DEVICE_ID === 'string' ? window.AA_DEVICE_ID.trim() : ''
  if (runtimeDeviceId) {
    return runtimeDeviceId
  }

  const devDeviceId =
    typeof import.meta.env?.VITE_AA_DEVICE_ID === 'string'
      ? import.meta.env.VITE_AA_DEVICE_ID.trim()
      : ''
  if (devDeviceId) {
    return devDeviceId
  }

  const compatibilityDeviceId =
    typeof window.__DEVICE_ID__ === 'string' ? window.__DEVICE_ID__.trim() : ''
  return compatibilityDeviceId || ''
}

export function buildStandardHeaders({ panel = 'global', scope = 'state', extraHeaders = {} } = {}) {
  return {
    'x-device-id': resolveDeviceId(),
    'x-panel': panel,
    'x-scope': scope,
    ...(extraHeaders || {})
  }
}
