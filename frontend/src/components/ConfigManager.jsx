import React, { useEffect, useState } from 'react'

export default function ConfigManager() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/health')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setData(json)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="container">
      <h2 className="mb-2">Config Manager</h2>
      <p className="text-sm mb-2">Inspect current sanctioned paths and backup/dry-run defaults.</p>
      <div className="card">
        {loading && <div>Loading...</div>}
        {error && <div className="text-sm text-error">Error: {error}</div>}
        {data?.fastapi?.details && (
          <div>
            <div className="mb-2"><strong>Sanctioned Paths</strong></div>
            <div className="code mb-2">{JSON.stringify(data.fastapi.details.sanctioned_paths, null, 2)}</div>
            <div className="mb-2"><strong>Backup on Write</strong>: {String(data.fastapi.details.backup_on_write)}</div>
            <div className="mb-2"><strong>Dry Run Default</strong>: {String(data.fastapi.details.dry_run_default)}</div>
            <button className="btn btn-primary" onClick={load}>Reload</button>
          </div>
        )}
        {data && !data.fastapi?.details && (
          <div className="text-sm text-gray-400">
            No config data available. Backend may not be running or health endpoint returned unexpected format.
          </div>
        )}
      </div>
    </div>
  )
}
