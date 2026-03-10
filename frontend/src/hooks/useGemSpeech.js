/**
 * useGemSpeech — Server-side Whisper STT via WebSocket on port 8787
 *
 * Replaces browser-native SpeechRecognition with the gateway's /ws/audio
 * endpoint which streams audio chunks to OpenAI Whisper for transcription.
 *
 * Usage:
 *   const { isRecording, wsConnected, startRecording, stopRecording, transcript, error } = useGemSpeech()
 */
import { useState, useRef, useCallback, useEffect } from 'react'
import { getGatewayWsUrl } from '../services/gateway'

const resolveWsUrl = () => {
  if (typeof window === 'undefined') return getGatewayWsUrl('/ws/audio')
  const isSecure = window.location.protocol === 'https:'
  const host = getGatewayHost()
  const scheme = isSecure ? 'wss' : 'ws'
  return `${scheme}://${host}/ws/audio`
}

const arrayBufferToBase64 = (buffer) => {
  let binary = ''
  const bytes = new Uint8Array(buffer)
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return window.btoa(binary)
}

const pickRecorderOptions = () => {
  if (typeof window === 'undefined' || typeof window.MediaRecorder === 'undefined') return undefined
  const preferred = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
  const supported = preferred.find(type =>
    typeof window.MediaRecorder.isTypeSupported === 'function' && window.MediaRecorder.isTypeSupported(type)
  )
  return supported ? { mimeType: supported } : undefined
}

export default function useGemSpeech({ onTranscript, onError } = {}) {
  const [isRecording, setIsRecording] = useState(false)
  const [wsConnected, setWsConnected] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [error, setError] = useState(null)

  const wsRef = useRef(null)
  const recorderRef = useRef(null)
  const streamRef = useRef(null)
  const chunkSeqRef = useRef(0)
  const reconnectRef = useRef(null)
  const backoffRef = useRef(2000)
  const aliveRef = useRef(true)
  const vadRef = useRef(null) // Voice Activity Detection state
  const stopRecordingRef = useRef(null) // ref to stopRecording for VAD callback

  // Connect to the gateway audio WebSocket
  const connect = useCallback(() => {
    if (!aliveRef.current) return
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) return

    const url = resolveWsUrl()
    console.log('[useGemSpeech] Connecting to:', url)

    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        console.log('[useGemSpeech] Connected')
        setWsConnected(true)
        setError(null)
        backoffRef.current = 2000
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'transcription' && msg.text) {
            console.log('[useGemSpeech] Transcript:', msg.text)
            setTranscript(msg.text)
            if (onTranscript) onTranscript(msg.text)
          } else if (msg.type === 'transcription' && msg.code === 'NO_AUDIO') {
            console.log('[useGemSpeech] No audio detected')
          } else if (msg.type === 'error') {
            console.warn('[useGemSpeech] Server error:', msg.message)
            const errMsg = msg.message || 'Transcription error'
            setError(errMsg)
            if (onError) onError(errMsg)
          }
        } catch { /* ignore non-JSON */ }
      }

      ws.onclose = () => {
        setWsConnected(false)
        if (!aliveRef.current) return
        reconnectRef.current = setTimeout(connect, backoffRef.current)
        backoffRef.current = Math.min(backoffRef.current * 2, 30000)
      }

      ws.onerror = () => {
        try { ws.close() } catch { /* ignore */ }
      }
    } catch {
      reconnectRef.current = setTimeout(connect, backoffRef.current)
      backoffRef.current = Math.min(backoffRef.current * 2, 30000)
    }
  }, [onTranscript, onError])

  // Auto-connect on mount
  useEffect(() => {
    aliveRef.current = true
    connect()
    return () => {
      aliveRef.current = false
      if (reconnectRef.current) clearTimeout(reconnectRef.current)
      if (wsRef.current) try { wsRef.current.close() } catch { /* ignore */ }
    }
  }, [connect])

  // Start recording: request mic, start MediaRecorder, stream chunks to WS
  const startRecording = useCallback(async () => {
    if (isRecording) return
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      const msg = 'Voice WebSocket not connected'
      setError(msg)
      if (onError) onError(msg)
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      chunkSeqRef.current = 0

      // Tell gateway to start recording
      wsRef.current.send(JSON.stringify({ type: 'start_recording' }))

      const options = pickRecorderOptions()
      const recorder = new MediaRecorder(stream, options)
      recorderRef.current = recorder

      recorder.ondataavailable = async (e) => {
        if (e.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
          const buf = await e.data.arrayBuffer()
          const b64 = arrayBufferToBase64(buf)
          chunkSeqRef.current++
          wsRef.current.send(JSON.stringify({
            type: 'audio_chunk',
            chunk: b64,
            sequence: chunkSeqRef.current
          }))
        }
      }

      recorder.onstop = () => {
        // Tell gateway to stop and finalize
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({
            type: 'stop_recording',
            lastSequence: chunkSeqRef.current
          }))
        }
      }

      recorder.start(250) // 250ms chunks
      setIsRecording(true)
      setError(null)
      console.log('[useGemSpeech] Recording started')

      // --- Voice Activity Detection (VAD) ---
      // Auto-stop when user stops talking (silence for ~1.5s after speech detected)
      try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)()
        const source = audioCtx.createMediaStreamSource(stream)
        const analyser = audioCtx.createAnalyser()
        analyser.fftSize = 512
        analyser.smoothingTimeConstant = 0.3
        source.connect(analyser)

        const dataArray = new Uint8Array(analyser.frequencyBinCount)
        const SILENCE_THRESHOLD = 15 // RMS below this = silence
        const SILENCE_DURATION_MS = 1500 // auto-stop after this much silence
        const MIN_SPEECH_MS = 500 // must detect speech for at least this long before silence triggers stop
        let speechDetectedAt = 0
        let silenceStartedAt = 0
        let vadActive = true

        const checkVAD = () => {
          if (!vadActive) return
          analyser.getByteTimeDomainData(dataArray)

          // Calculate RMS
          let sum = 0
          for (let i = 0; i < dataArray.length; i++) {
            const v = (dataArray[i] - 128) / 128
            sum += v * v
          }
          const rms = Math.sqrt(sum / dataArray.length) * 100

          const now = Date.now()
          if (rms > SILENCE_THRESHOLD) {
            // Speech detected
            if (!speechDetectedAt) speechDetectedAt = now
            silenceStartedAt = 0
          } else if (speechDetectedAt && (now - speechDetectedAt > MIN_SPEECH_MS)) {
            // Silence after speech
            if (!silenceStartedAt) silenceStartedAt = now
            if (now - silenceStartedAt > SILENCE_DURATION_MS) {
              console.log('[useGemSpeech] VAD: silence detected, auto-stopping')
              vadActive = false
              if (stopRecordingRef.current) stopRecordingRef.current()
              return
            }
          }

          requestAnimationFrame(checkVAD)
        }

        requestAnimationFrame(checkVAD)
        vadRef.current = { audioCtx, vadActive: true, stop: () => { vadActive = false; try { audioCtx.close() } catch {} } }
      } catch (vadErr) {
        console.warn('[useGemSpeech] VAD setup failed (non-critical):', vadErr.message)
      }
    } catch (err) {
      const msg = err.name === 'NotAllowedError'
        ? 'Microphone permission denied. Please allow microphone access.'
        : `Microphone error: ${err.message}`
      setError(msg)
      if (onError) onError(msg)
      setIsRecording(false)
    }
  }, [isRecording, onError])

  // Stop recording
  const stopRecording = useCallback(() => {
    // Clean up VAD
    if (vadRef.current) {
      vadRef.current.stop()
      vadRef.current = null
    }
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop()
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    setIsRecording(false)
    console.log('[useGemSpeech] Recording stopped')
  }, [])

  // Keep stopRecordingRef in sync so VAD callback can call it
  useEffect(() => {
    stopRecordingRef.current = stopRecording
  }, [stopRecording])

  return {
    isRecording,
    wsConnected,
    transcript,
    error,
    startRecording,
    stopRecording
  }
}
