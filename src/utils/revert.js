// src/utils/revert.js (ESM)
// List and restore backups created by safeWrite().

import fs from 'fs'
import path from 'path'

function must(p) { if (!fs.existsSync(p)) throw new Error(`Path not found: ${p}`) }

export function listBackups(filePath, backupDir, limit = 10) {
  must(filePath)
  const dir = backupDir ?? path.dirname(filePath); must(dir)
  const base = path.basename(filePath)
  const entries = fs.readdirSync(dir)
    .filter(n => n.startsWith(base + '.') && n.endsWith('.bak'))
    .map(n => ({ n, p: path.join(dir, n) }))
    .map(x => ({ ...x, t: fs.statSync(x.p).mtimeMs }))
    .sort((a, b) => b.t - a.t)
    .slice(0, Math.max(0, limit))
  return entries.map(e => e.p)
}

export function revertLatest(filePath, backupDir) {
  const [latest] = listBackups(filePath, backupDir, 1)
  if (!latest) throw new Error(`No backups found for ${filePath}`)

  const dir = path.dirname(filePath)
  const base = path.basename(filePath)
  const tmp = path.join(dir, `${base}.revert.${process.pid}.${Date.now()}.tmp`)

  const data = fs.readFileSync(latest, 'utf8')
  fs.writeFileSync(tmp, data, 'utf8')
  try {
    try { fs.renameSync(tmp, filePath) }
    catch (e) { if (e && e.code === 'EEXIST') { fs.unlinkSync(filePath); fs.renameSync(tmp, filePath) } else { throw e } }
  } finally {
    if (fs.existsSync(tmp)) { try { fs.unlinkSync(tmp) } catch { /* ignore */ } }
  }
  return { restoredFrom: latest }
}

