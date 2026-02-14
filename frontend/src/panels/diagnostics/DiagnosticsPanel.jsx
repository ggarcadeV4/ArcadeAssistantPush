import { useEffect, useState } from 'react'

export default function DiagnosticsPanel() {
  const [rows, setRows] = useState([])
  useEffect(() => {
    fetch('/api/diagnostics/launches')
      .then(r => r.json())
      .then(setRows)
      .catch(() => setRows([]))
  }, [])
  return (
    <div className="p-4 space-y-2">
      <h2 className="text-xl font-semibold">Recent Launches</h2>
      <div className="text-sm opacity-70">title  platform  method  duration  ended</div>
      <ul className="divide-y divide-white/10">
        {rows.map((r, i) => (
          <li key={i} className="py-2">
            <div className="font-medium">{r.title || r.gameTitle || r.gameId}</div>
            <div className="text-sm opacity-80">
              {(r.platform || '')}  via: {(r.method_used || r.method || '?')}  {(r.durationMs ?? r.duration_ms ?? '')} ms  {(r.endedAt || r.ts || '')}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
