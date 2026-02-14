import React, { useEffect, useRef, useState } from 'react'

export default function MicTest() {
  const canvasRef = useRef(null)
  const [recording, setRecording] = useState(false)
  const [error, setError] = useState(null)
  const streamRef = useRef(null)
  const audioCtxRef = useRef(null)
  const analyserRef = useRef(null)
  const rafRef = useRef(null)

  useEffect(() => {
    return () => stop()
  }, [])

  async function start() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const AudioCtx = window.AudioContext || window.webkitAudioContext
      const ctx = new AudioCtx()
      audioCtxRef.current = ctx
      const source = ctx.createMediaStreamSource(stream)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 1024
      analyserRef.current = analyser
      source.connect(analyser)
      setRecording(true)
      draw()
    } catch (e) {
      setError(e.message)
    }
  }

  function stop() {
    setRecording(false)
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    if (audioCtxRef.current) audioCtxRef.current.close()
    if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop())
  }

  function draw() {
    const canvas = canvasRef.current
    const analyser = analyserRef.current
    if (!canvas || !analyser) return

    const ctx = canvas.getContext('2d')
    const bufferLength = analyser.frequencyBinCount
    const dataArray = new Uint8Array(bufferLength)

    const render = () => {
      analyser.getByteTimeDomainData(dataArray)
      ctx.fillStyle = '#f3f4f6'
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.lineWidth = 2
      ctx.strokeStyle = 'var(--primary-color)'
      ctx.beginPath()

      const sliceWidth = canvas.width / bufferLength
      let x = 0
      for (let i = 0; i < bufferLength; i++) {
        const v = dataArray[i] / 128.0
        const y = (v * canvas.height) / 2
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
        x += sliceWidth
      }
      ctx.lineTo(canvas.width, canvas.height / 2)
      ctx.stroke()

      rafRef.current = requestAnimationFrame(render)
    }

    render()
  }

  return (
    <div className="container">
      <h2 className="mb-2">Microphone Test</h2>
      <p className="text-sm mb-2">Use this tool to verify cabinet mic input and levels.</p>
      {error && <div className="text-sm mb-2" style={{ color: 'var(--error-color)' }}>{error}</div>}
      <div className="card">
        <canvas ref={canvasRef} width={800} height={200} className="audio-visualizer" />
        <div className="mt-2">
          {!recording ? (
            <button className="btn btn-primary" onClick={start}>Start</button>
          ) : (
            <button className="btn btn-danger" onClick={stop}>Stop</button>
          )}
        </div>
      </div>
    </div>
  )
}
