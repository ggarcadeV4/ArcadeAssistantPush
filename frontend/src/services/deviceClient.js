const BASE_LOCAL = '/api/local';

export async function fetchDeviceSnapshot() {
  const res = await fetch(`${BASE_LOCAL}/devices/snapshot`);
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail?.detail || 'Failed to fetch device snapshot');
  }
  return res.json();
}

export async function classifyDevice({ deviceId, role, label, panels = [] }) {
  const res = await fetch(`${BASE_LOCAL}/devices/classify`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-scope': 'config',
      'x-panel': 'controller',
      'x-device-id': window.AA_DEVICE_ID || 'CAB-0001'
    },
    body: JSON.stringify({
      device_id: deviceId,
      role,
      label,
      panels
    })
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail?.detail || 'Failed to classify device');
  }
  return res.json();
}

export async function refreshControllerDevices() {
  const res = await fetch(`${BASE_LOCAL}/controller/refresh`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-scope': 'state',
      'x-panel': 'controller',
      'x-device-id': window.AA_DEVICE_ID || 'CAB-0001'
    }
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail?.detail || 'Failed to refresh controller devices');
  }
  return res.json();
}

const CONTROLLER_BASE = `${BASE_LOCAL}/controller`;

export async function startWiringWizard() {
  const res = await fetch(`${CONTROLLER_BASE}/wizard/start`, {
    method: 'POST',
    headers: {
      'x-panel': 'controller',
      'x-device-id': 'controller_panel',
      'x-scope': 'state'
    }
  });
  if (!res.ok) throw new Error('Failed to start wizard');
  return res.json();
}

export async function fetchWizardNextStep() {
  const res = await fetch(`${CONTROLLER_BASE}/wizard/next-step`, {
    method: 'POST',
    headers: {
      'x-panel': 'controller',
      'x-device-id': 'controller_panel',
      'x-scope': 'state'
    }
  });
  if (!res.ok) throw new Error('Failed to fetch wizard step');
  return res.json();
}

export async function captureWizardInput(controlKey, pin, controlType) {
  const res = await fetch(`${CONTROLLER_BASE}/wizard/capture`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-panel': 'controller',
      'x-device-id': 'controller_panel',
      'x-scope': 'state'
    },
    body: JSON.stringify({
      control_key: controlKey,
      pin,
      control_type: controlType
    })
  });
  if (!res.ok) throw new Error('Failed to capture wizard input');
  return res.json();
}

export async function previewWizardMapping() {
  const res = await fetch(`${CONTROLLER_BASE}/wizard/preview`, {
    method: 'POST',
    headers: {
      'x-panel': 'controller',
      'x-device-id': 'controller_panel',
      'x-scope': 'state'
    }
  });
  if (!res.ok) throw new Error('Failed to preview wizard mapping');
  return res.json();
}

export async function applyWizardMapping() {
  const res = await fetch(`${CONTROLLER_BASE}/wizard/apply`, {
    method: 'POST',
    headers: {
      'x-panel': 'controller',
      'x-device-id': 'controller_panel',
      'x-scope': 'config'
    }
  });
  if (!res.ok) throw new Error('Failed to apply wizard mapping');
  return res.json();
}

export async function fetchDiagnosticsEvent() {
  const res = await fetch(`${BASE_LOCAL}/controller/diagnostics/next-event`, {
    headers: {
      'x-panel': 'controller',
      'x-device-id': 'controller_panel',
      'x-scope': 'state'
    }
  });
  if (!res.ok) throw new Error('Failed to fetch diagnostics event');
  return res.json();
}

// ============ Learn Wizard Functions ============
// Voice-guided wizard that captures ANY button press

/**
 * Start the learn wizard.
 * @param {Object} options - Options
 * @param {number} [options.player] - Which player to map (1=P1, 2=P2, omit for both)
 */
export async function startLearnWizard({ player } = {}) {
  let url = `${CONTROLLER_BASE}/learn-wizard/start`;
  if (player) {
    url += `?player=${player}`;
  }
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'x-panel': 'controller',
      'x-device-id': window.AA_DEVICE_ID || 'CAB-0001',
      'x-scope': 'state'
    }
  });
  if (!res.ok) throw new Error('Failed to start learn wizard');
  return res.json();
}

export async function getLearnWizardStatus() {
  const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/status`, {
    headers: {
      'x-panel': 'controller',
      'x-device-id': window.AA_DEVICE_ID || 'CAB-0001',
      'x-scope': 'state'
    }
  });
  if (!res.ok) throw new Error('Failed to get learn wizard status');
  return res.json();
}

export async function confirmLearnWizardCapture() {
  const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/confirm`, {
    method: 'POST',
    headers: {
      'x-panel': 'controller',
      'x-device-id': window.AA_DEVICE_ID || 'CAB-0001',
      'x-scope': 'state'
    }
  });
  if (!res.ok) throw new Error('Failed to confirm capture');
  return res.json();
}

export async function skipLearnWizardControl() {
  const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/skip`, {
    method: 'POST',
    headers: {
      'x-panel': 'controller',
      'x-device-id': window.AA_DEVICE_ID || 'CAB-0001',
      'x-scope': 'state'
    }
  });
  if (!res.ok) throw new Error('Failed to skip control');
  return res.json();
}

export async function saveLearnWizard() {
  const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/save`, {
    method: 'POST',
    headers: {
      'x-panel': 'controller',
      'x-device-id': window.AA_DEVICE_ID || 'CAB-0001',
      'x-scope': 'config'
    }
  });
  if (!res.ok) throw new Error('Failed to save wizard mappings');
  return res.json();
}

export async function stopLearnWizard() {
  const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/stop`, {
    method: 'POST',
    headers: {
      'x-panel': 'controller',
      'x-device-id': window.AA_DEVICE_ID || 'CAB-0001',
      'x-scope': 'state'
    }
  });
  if (!res.ok) throw new Error('Failed to stop wizard');
  return res.json();
}

/**
 * Manually set the keycode for the current control.
 * Use this when auto-detection doesn't work (e.g., encoder in gamepad mode).
 * @param {string} keycode - The keycode to assign (e.g., 'F1', 'UP', 'SPACE')
 */
export async function setLearnWizardKey(keycode) {
  const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/set-key`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-panel': 'controller',
      'x-device-id': window.AA_DEVICE_ID || 'CAB-0001',
      'x-scope': 'state'
    },
    body: JSON.stringify({ keycode })
  });
  if (!res.ok) throw new Error('Failed to set key');
  return res.json();
}

/**
 * Undo the last capture and go back one step.
 */
export async function undoLearnWizardCapture() {
  const res = await fetch(`${CONTROLLER_BASE}/learn-wizard/undo`, {
    method: 'POST',
    headers: {
      'x-panel': 'controller',
      'x-device-id': window.AA_DEVICE_ID || 'CAB-0001',
      'x-scope': 'state'
    }
  });
  if (!res.ok) throw new Error('Failed to undo capture');
  return res.json();
}


// Reset all mappings to default (for demos)
export async function resetMappingToDefault() {
  const res = await fetch(`${CONTROLLER_BASE}/mapping/reset`, {
    method: 'POST',
    headers: {
      'x-panel': 'controller',
      'x-device-id': window.AA_DEVICE_ID || 'CAB-0001',
      'x-scope': 'config'
    }
  });
  if (!res.ok) throw new Error('Failed to reset mappings');
  return res.json();
}
