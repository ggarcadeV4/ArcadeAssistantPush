import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const DEFAULT_REL = path.join('docs', 'config', 'operational_sequence_manifest.yaml')

// Lazy-load YAML parser (optional dependency)
let YAML = null
try {
  const yamlModule = await import('yaml')
  YAML = yamlModule.default
} catch {
  // YAML not installed - JSON manifests will still work
}

export function defaultManifestPath() {
  return path.resolve(__dirname, '..', '..', DEFAULT_REL)
}

export async function loadManifest(manifestPath = defaultManifestPath()) {
  if (!fs.existsSync(manifestPath)) {
    throw new Error(`Manifest file not found: ${manifestPath}`)
  }
  const raw = fs.readFileSync(manifestPath, 'utf-8')
  const ext = path.extname(manifestPath).toLowerCase()

  let data
  if (ext === '.yml' || ext === '.yaml') {
    if (!YAML) {
      throw new Error('YAML parser not installed. Run: npm install yaml')
    }
    data = YAML.parse(raw) || {}
  } else {
    // Assume JSON for .json or other extensions
    data = JSON.parse(raw)
  }

  if (data && typeof data === 'object' && !Array.isArray(data)) return data
  throw new Error('Manifest root must be a mapping')
}

export function validateManifest(data) {
  const errors = []

  if (!Object.prototype.hasOwnProperty.call(data, 'global_invariants')) {
    errors.push('Missing required key: global_invariants')
  } else if (!Array.isArray(data.global_invariants) || !data.global_invariants.every((x) => typeof x === 'string')) {
    errors.push('global_invariants must be a list of strings')
  }
  
  // Required invariant presence
  if (Array.isArray(data.global_invariants)) {
    const have = new Set(data.global_invariants)
    const required = [
      'AA_DRIVE_ROOT must exist and be validated before any route registration.',
      'Gateway performs no direct file I/O; all writes proxy to FastAPI /config/*.',
      'All writes follow Preview  Apply  Restore.',
      'When /.aa/manifest.json has sanctioned_paths=[], all writes are rejected (read-only mode).',
      "CORS with credentials must enumerate origins (no '*'); allow headers: x-device-id, x-scope, content-type, authorization.",
      'Missing/disabled AI keys return 501 NOT_CONFIGURED (never 500).',
      'Structured logs include request_id, x-device-id, x-panel, and backup_path when applicable.',
      'Threads/tasks are joined/cancelled on shutdown; no orphaned workers.',
      'Frontend panels are isolated with ErrorBoundaries; errors log to /logs/frontend_errors.jsonl.',
    ]
    for (const req of required) {
      if (!have.has(req)) errors.push(`Missing required invariant: ${req}`)
    }
  }

  if (!Object.prototype.hasOwnProperty.call(data, 'paths')) {
    errors.push('Missing required key: paths')
  } else if (typeof data.paths !== 'object' || Array.isArray(data.paths)) {
    errors.push('paths must be a mapping')
  } else {
    for (const [k, v] of Object.entries(data.paths)) {
      if (typeof k !== 'string') {
        errors.push('paths keys must be strings')
        break
      }
      if (!(typeof v === 'string' || Array.isArray(v))) {
        errors.push(`paths[${k}] must be string or list`)
      }
      if (Array.isArray(v) && !v.every((x) => typeof x === 'string')) {
        errors.push(`paths[${k}] list must contain strings`)
      }
    }
  }

  if (!Object.prototype.hasOwnProperty.call(data, 'startup_sequence')) {
    errors.push('Missing required key: startup_sequence')
  } else {
    const ss = data.startup_sequence
    if (Array.isArray(ss)) {
      ss.forEach((step, i) => {
        if (!(typeof step === 'object' || typeof step === 'string')) {
          errors.push(`startup_sequence[${i}] must be mapping or string`)
        }
      })
    } else if (ss && typeof ss === 'object' && !Array.isArray(ss)) {
      const order = ss.order
      if (!Array.isArray(order) || !order.every((x) => typeof x === 'string')) {
        errors.push('startup_sequence.order must be a list of strings')
      }
      for (const phase of ['backend:init', 'gateway:init', 'frontend:init']) {
        if (phase in ss) {
          const steps = ss[phase]
          if (!(Array.isArray(steps) && steps.every((x) => typeof x === 'string'))) {
            errors.push(`startup_sequence.${phase} must be a list of strings if present`)
          }
        }
      }
    } else {
      errors.push('startup_sequence must be a list or mapping')
    }
  }

  return errors
}

export function validateCorsOptions(options) {
  const errors = []
  if (!options || typeof options !== 'object') {
    return ['CORS options must be an object']
  }
  const origin = options.origin
  const hasWildcardOrigin = origin === '*' || (Array.isArray(origin) && origin.includes('*'))
  if (hasWildcardOrigin) {
    errors.push('CORS origin must not use *')
  }
  if (!options.credentials) {
    errors.push('CORS must enable credentials')
  }
  const allowedHeaders = options.allowedHeaders
  if (!Array.isArray(allowedHeaders)) {
    errors.push('CORS allowedHeaders must be an array')
  } else {
    const lower = new Set(allowedHeaders.map((h) => String(h).toLowerCase()))
    const required = ['x-device-id', 'x-scope', 'content-type', 'authorization']
    for (const h of required) {
      if (!lower.has(h)) {
        errors.push(`CORS allowedHeaders missing required header: ${h}`)
      }
    }
    if (lower.has('*')) {
      errors.push('CORS allowedHeaders must not include *')
    }
  }
  return errors
}

export function installNoLocalWritesGuard() {
  // Enforce invariant: Gateway performs no direct file I/O (writes)
  const dangerous = [
    'writeFile', 'writeFileSync', 'appendFile', 'appendFileSync',
    'rename', 'renameSync', 'rm', 'rmSync', 'rmdir', 'rmdirSync',
    'mkdir', 'mkdirSync', 'copyFile', 'copyFileSync', 'truncate', 'truncateSync',
    'createWriteStream', 'utimes', 'utimesSync'
  ]
  const original = {}
  for (const fn of dangerous) {
    if (typeof fs[fn] === 'function') {
      original[fn] = fs[fn]
      fs[fn] = (...args) => {
        const msg = `Gateway local write blocked by policy (${fn}). Use FastAPI /config/*`
        if (fn.endsWith('Sync')) {
          throw Object.assign(new Error(msg), { code: 78 })
        }
        const cb = typeof args[args.length - 1] === 'function' ? args.pop() : null
        const err = Object.assign(new Error(msg), { code: 78 })
        if (cb) return queueMicrotask(() => cb(err))
        throw err
      }
    }
  }
  return () => {
    for (const [fn, impl] of Object.entries(original)) {
      fs[fn] = impl
    }
  }
}

export function preflightNoLocalWritesInConfig() {
  const errors = []
  const projectRoot = path.resolve(__dirname, '..', '..')
  const serverFile = path.join(projectRoot, 'gateway', 'server.js')
  const configFile = path.join(projectRoot, 'gateway', 'routes', 'config.js')
  // If server does not import/register config routes, skip
  try {
    if (fs.existsSync(serverFile)) {
      const s = fs.readFileSync(serverFile, 'utf-8')
      if (!s.includes('routes/config.js')) return errors
    }
  } catch {}
  if (!fs.existsSync(configFile)) return errors
  try {
    const text = fs.readFileSync(configFile, 'utf-8')
    // If the route layer references fs write APIs directly, block
    const bannedFs = [
      'writeFile', 'writeFileSync', 'appendFile', 'appendFileSync',
      'rename', 'renameSync', 'rm', 'rmSync', 'rmdir', 'rmdirSync',
      'mkdir', 'mkdirSync', 'copyFile', 'copyFileSync', 'truncate', 'truncateSync',
      'createWriteStream', 'utimes', 'utimesSync', 'unlink', 'unlinkSync',
    ]
    for (const token of bannedFs) {
      const rx = new RegExp(`\bfs\.${token}\b`, 'm')
      if (rx.test(text)) {
        errors.push(`Forbidden local write API 'fs.${token}' used in gateway/routes/config.js`)    
      }
    }
    // If the route uses safeWrite, that implies local write behavior within gateway — block
    if (/\bsafeWrite\s*\(/.test(text)) {
      errors.push(`Local write helper 'safeWrite(...)' used in gateway/routes/config.js`)    
    }
  } catch (e) {
    errors.push(`Failed to scan config routes: ${e?.message || e}`)
  }
  return errors
}
