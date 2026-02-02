// src/utils/safeWrite.js (ESM)
// Minimal safe-write with backups + atomic swap.
// Ops: [{ op:'replace'|'insert'|'remove', match, value?, before? }]
// - match: string (regex allowed). validate(text) is called before and after.

import fs from 'fs'
import path from 'path'
import crypto from 'crypto'

export function safeWrite(opts) {
  const { filePath, diff, dryRun } = opts
  let text = opts.originalText ?? fs.readFileSync(filePath, 'utf8')

  if (opts.validate) opts.validate(text)

  const lines = text.split(/\r?\n/)
  let changed = false

  for (const step of diff) {
    const isRegex = step.match.startsWith('^') || step.match.endsWith('$') || /[.*+?^${}()|[\]\\]/.test(step.match)
    const rx = isRegex ? new RegExp(step.match, 'm') : null
    const findIndex = () => (rx ? lines.findIndex(l => rx.test(l)) : lines.findIndex(l => l === step.match))

    if (step.op === 'replace') {
      const i = findIndex()
      if (i >= 0) {
        const parts = (step.value ?? '').split(/\r?\n/)
        lines.splice(i, 1, ...parts)
        changed = true
      }
    } else if (step.op === 'insert') {
      const i = findIndex()
      if (i >= 0) {
        const idx = step.before ? i : i + 1
        const parts = (step.value ?? '').split(/\r?\n/)
        lines.splice(idx, 0, ...parts)
        changed = true
      }
    } else if (step.op === 'remove') {
      const i = findIndex()
      if (i >= 0) {
        lines.splice(i, 1)
        changed = true
      }
    }
  }

  const nextText = lines.join('\n')
  if (opts.validate) opts.validate(nextText)

  if (dryRun || !changed) {
    return { changed, preview: nextText, wrote: false, backupPath: null, tempPath: null }
  }

  const dir = path.dirname(filePath)
  const base = path.basename(filePath)
  const backupDir = opts.backupDir ?? dir
  if (!fs.existsSync(backupDir)) fs.mkdirSync(backupDir, { recursive: true })

  const stamp = new Date().toISOString().replace(/[:.]/g, '-')
  const hash = crypto.createHash('sha1').update(text).digest('hex').slice(0, 8)
  const backupPath = path.join(backupDir, `${base}.${stamp}.${hash}.bak`)
  const tempPath = path.join(dir, `.${base}.${process.pid}.${Date.now()}.tmp`)

  fs.writeFileSync(tempPath, nextText, 'utf8')
  fs.copyFileSync(filePath, backupPath)
  try {
    try {
      fs.renameSync(tempPath, filePath)
    } catch (e) {
      if (e && e.code === 'EEXIST') {
        fs.unlinkSync(filePath)
        fs.renameSync(tempPath, filePath)
      } else {
        throw e
      }
    }
  } finally {
    if (fs.existsSync(tempPath)) {
      try { fs.unlinkSync(tempPath) } catch { /* ignore */ }
    }
  }

  return { changed: true, preview: nextText, wrote: true, backupPath, tempPath: null }
}

export const validators = {
  nonEmpty: (t) => { if (!t || !t.trim()) throw new Error('Validation failed: empty content') },
  iniLooksLike: (t) => { if (!/^[^#\r\n].+?=.+/m.test(t)) throw new Error('Validation failed: not INI-like') }
}

