import React, { useEffect, useState } from 'react'

// Legacy component - SystemHealthPanel now uses /api/local/health/* endpoints.
export default function SystemHealth() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

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

  // Determine manifest presence from backend health payload
  const manifestExists =
    data?.fastapi?.details?.manifest_exists === true ||
    (Array.isArray(data?.fastapi?.details?.sanctioned_paths) &&
      data.fastapi.details.sanctioned_paths.length > 0)
  const sttReady = !!data?.fastapi?.details?.stt_configured
  const tts = data?.fastapi?.details?.tts_usage
  const llmProvider = data?.fastapi?.details?.llm_provider || 'unconfigured'
  const sttProvider = data?.fastapi?.details?.stt_provider || 'unconfigured'
  const fmtProvider = (p) => {
    const m = {
      anthropic: 'Anthropic',
      openai: 'OpenAI',
      deepgram: 'Deepgram',
      whisper_local: 'Whisper Local',
      unconfigured: 'Not Configured'
    }
    const key = String(p || '').toLowerCase()
    if (m[key]) return m[key]
    return String(p || '').replace(/[_-]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  }

  return (
    <div className="container">
      <h2 className="mb-2">System Health</h2>
      <p className="text-sm mb-2">Live status for the Gateway and FastAPI backend.</p>
      <div className="card">
        {loading && <div>Loading...</div>}
        {error && <div className="text-sm text-error">Error: {error}</div>}
        {data && (
          <div>
            <div className="mb-2"><strong>Gateway</strong></div>
            <div className="text-sm mb-2">Uptime: {Math.round(data.gateway.uptime)}s | Node: {data.gateway.version}</div>
            <div className="mb-2"><strong>FastAPI</strong> — {data.fastapi.connected ? 'Connected' : 'Not Connected'}</div>
            {/* Manifest presence indicator (green/red tile) */}
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div className={`p-3 rounded ${manifestExists ? 'bg-green-900/30 border border-green-600' : 'bg-red-900/30 border border-red-600'}`}>
                <div className="text-sm opacity-80">Manifest</div>
                <div className="text-lg font-semibold">
                  {manifestExists ? 'Present ' : 'Missing '}
                </div>
              </div>
              <div className={`p-3 rounded ${sttReady ? 'bg-green-900/30 border border-green-600' : 'bg-yellow-900/30 border border-yellow-600'}`}>
                <div className="text-sm opacity-80">STT Provider</div>
                <div className="text-lg font-semibold">{sttReady ? `${fmtProvider(sttProvider)} ` : 'Not Configured '}</div>
              </div>
              <div className={`p-3 rounded ${llmProvider !== 'unconfigured' ? 'bg-green-900/30 border border-green-600' : 'bg-yellow-900/30 border border-yellow-600'}`}>
                <div className="text-sm opacity-80">LLM Provider</div>
                <div className="text-lg font-semibold">
                  {llmProvider !== 'unconfigured' ? `${fmtProvider(llmProvider)} ` : 'Not Configured '}
                </div>
              </div>
              {tts && (
                <div className="p-3 rounded bg-blue-900/30 border border-blue-600 col-span-2">
                  <div className="text-sm opacity-80">TTS Usage</div>
                  <div className="text-sm">{JSON.stringify(tts)}</div>
                </div>
              )}
            </div>
            {data.fastapi.details && (
              <div className="code mb-2">{JSON.stringify(data.fastapi.details, null, 2)}</div>
            )}
            <button className="btn btn-primary" onClick={load}>Refresh</button>
          </div>
        )}
      </div>
    </div>
  )
}
