import fs from 'fs';
import path from 'path';
import { resolveDriveRoot } from './driveDetection.js';

export function resolveDriveRootInput(input) {
  return resolveDriveRoot(input, { allowProjectFallback: false });
}

function readJson(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return {};
  }
}

export function loadCabinetIdentity(driveRootInput = process.env.AA_DRIVE_ROOT, env = process.env) {
  const driveRoot = resolveDriveRootInput(driveRootInput);
  const deviceIdPath = driveRoot ? path.join(driveRoot, '.aa', 'device_id.txt') : null;
  const cabinetManifestPath = driveRoot ? path.join(driveRoot, '.aa', 'cabinet_manifest.json') : null;

  let deviceId = '';
  let source = 'unresolved';

  if (deviceIdPath && fs.existsSync(deviceIdPath)) {
    deviceId = (fs.readFileSync(deviceIdPath, 'utf8') || '').trim();
    if (deviceId) source = 'device_id_txt';
  }

  const manifest = cabinetManifestPath && fs.existsSync(cabinetManifestPath) ? readJson(cabinetManifestPath) : {};
  if (!deviceId) {
    deviceId = String(manifest.device_id || manifest.id || '').trim();
    if (deviceId) source = 'cabinet_manifest';
  }

  if (!deviceId) {
    deviceId = String(env.AA_DEVICE_ID || '').trim();
    if (deviceId) source = 'env';
  }

  const hostname = env.COMPUTERNAME || env.HOSTNAME || 'Arcade Cabinet';
  const deviceName = String(manifest.device_name || manifest.name || env.DEVICE_NAME || hostname || 'Arcade Cabinet').trim() || 'Arcade Cabinet';
  const deviceSerial = String(manifest.device_serial || manifest.serial || env.DEVICE_SERIAL || env.AA_SERIAL_NUMBER || 'UNPROVISIONED').trim() || 'UNPROVISIONED';

  return {
    deviceId,
    deviceName,
    deviceSerial,
    source,
    driveRoot,
    filesPresent: {
      device_id_txt: Boolean(deviceIdPath && fs.existsSync(deviceIdPath)),
      cabinet_manifest_json: Boolean(cabinetManifestPath && fs.existsSync(cabinetManifestPath)),
    },
  };
}

export function resolveRequestDeviceId(req) {
  return String(
    req.headers['x-device-id']
      || req.app?.locals?.cabinetIdentity?.deviceId
      || process.env.AA_DEVICE_ID
      || ''
  ).trim();
}
