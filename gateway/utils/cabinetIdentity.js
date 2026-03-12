import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export function resolveDriveRoot(input) {
  const base = path.resolve(__dirname, '..', '..');
  if (!input) return base;
  const isWinPath = /^[A-Za-z]:[\\/]/.test(input);
  if (path.isAbsolute(input) || isWinPath) return input;
  return path.resolve(base, input);
}

function readJson(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return {};
  }
}

export function loadCabinetIdentity(driveRootInput = process.env.AA_DRIVE_ROOT, env = process.env) {
  const driveRoot = resolveDriveRoot(driveRootInput);
  const deviceIdPath = path.join(driveRoot, '.aa', 'device_id.txt');
  const cabinetManifestPath = path.join(driveRoot, '.aa', 'cabinet_manifest.json');

  let deviceId = '';
  let source = 'unresolved';

  if (fs.existsSync(deviceIdPath)) {
    deviceId = (fs.readFileSync(deviceIdPath, 'utf8') || '').trim();
    if (deviceId) source = 'device_id_txt';
  }

  const manifest = fs.existsSync(cabinetManifestPath) ? readJson(cabinetManifestPath) : {};
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
      device_id_txt: fs.existsSync(deviceIdPath),
      cabinet_manifest_json: fs.existsSync(cabinetManifestPath),
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
