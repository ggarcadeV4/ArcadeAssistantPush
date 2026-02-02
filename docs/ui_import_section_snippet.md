# LaunchBox LoRa Panel – ImportSection snippet

Example React snippet for a small Import Missing UI in the LaunchBox LoRa panel source.

```jsx
import React, { useState } from 'react'

export default function ImportSection({ defaultPlatform, defaultFolder, onRefresh }) {
  const [platform, setPlatform] = useState(defaultPlatform || 'Arcade')
  const [folder, setFolder] = useState(defaultFolder || (platform === 'Arcade' ? 'A:\\Console ROMs\\MAME' : 'A:\\Console ROMs\\PlayStation 2'))
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  async function runImport() {
    setBusy(true); setMsg('')
    try {
      const res = await fetch('/api/launchbox/import/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ platform, folder })
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setMsg(`Imported ${data.added}, skipped ${data.skipped}`)
      await fetch('/api/launchbox/cache/revalidate', { method: 'POST' })
      onRefresh && onRefresh()
    } catch (e) {
      setMsg(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="import-section">
      <h4>📥 Import Missing</h4>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <select value={platform} onChange={e => setPlatform(e.target.value)} disabled={busy}>
          <option>Arcade</option>
          <option>Sony PlayStation 2</option>
        </select>
        <input value={folder} onChange={e => setFolder(e.target.value)} disabled={busy} style={{ width: 420 }} />
        <button onClick={runImport} disabled={busy}>Import</button>
      </div>
      {msg ? <div className="import-msg">{msg}</div> : null}
    </div>
  )
}
```

Notes
- Do not add to built `frontend/dist/*`; integrate into the actual panel source (e.g., `frontend/src/panels/launchbox/LaunchBoxPanel.jsx`).
- Default folders:
  - Arcade → `A:\Console ROMs\MAME`
  - PS2 → `A:\Console ROMs\PlayStation 2`

