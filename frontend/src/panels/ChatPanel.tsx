import React, { useState } from 'react'
import { streamChat } from '../lib/sseClient'
import { sentenceBoundaryAccumulator } from '../lib/earlyTts'

export default function ChatPanel() {
  const [text, setText] = useState("")
  const [stream, setStream] = useState("")
  const [loading, setLoading] = useState(false)

  async function runStream() {
    setStream("")
    setLoading(true)
    const pump = sentenceBoundaryAccumulator(async (first) => {
      try {
        await fetch('/api/voice/tts', {
          method: 'POST',
          headers: { 'content-type': 'application/json', 'x-device-id': 'CAB-001', 'x-panel': 'voice' },
          body: JSON.stringify({ text: first })
        })
      } catch {}
    })

    try {
      await streamChat((chunk) => {
        pump(chunk)
        setStream((s) => s + chunk)
      })
    } catch (e) {
      console.error('SSE error', e)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <h2 className="mb-2">Chat (SSE Demo)</h2>
      <textarea className="w-full p-2 border rounded" value={text} onChange={(e)=>setText(e.target.value)} placeholder="Ask something..." />
      <div className="actions mt-2">
        <button className="btn btn-primary" onClick={runStream} disabled={loading}>{loading ? 'Streaming...' : 'Ask'}</button>
      </div>
      <pre className="mt-3 whitespace-pre-wrap">{stream}</pre>
    </div>
  )
}

