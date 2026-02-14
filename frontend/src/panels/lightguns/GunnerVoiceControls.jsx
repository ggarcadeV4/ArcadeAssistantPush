import React, { useCallback, useEffect, useRef, useState } from 'react'
import { stopSpeaking } from '../../services/ttsClient'

const MAX_RECORD_MS = 15000
const SILENCE_THRESHOLD = -50 // dB - audio below this is considered silence
const SILENCE_DURATION = 350 // ms - stop after 0.35 seconds of silence

const arrayBufferToBase64 = (buffer) => {
  let binary = ''
  const bytes = new Uint8Array(buffer)
  for (let i = 0; i < bytes.byteLength; i += 1) {
    binary += String.fromCharCode(bytes[i])
  }
  if (typeof window !== 'undefined' && window.btoa) {
    return window.btoa(binary)
  }
  return Buffer.from(binary, 'binary').toString('base64')
}

const pickRecorderOptions = () => {
  if (typeof window === 'undefined' || typeof window.MediaRecorder === 'undefined') {
    return undefined
  }
  const preferred = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
  const supported = preferred.find(type => typeof window.MediaRecorder.isTypeSupported === 'function' && window.MediaRecorder.isTypeSupported(type))
  return supported ? { mimeType: supported } : undefined
}

const getWsUrl = () => {
  if (typeof window === 'undefined') {
    return null
  }
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const port = Number(window.location.port)
  const isVite = port >= 5173 && port <= 5179
  const host = isVite ? 'localhost:8787' : window.location.host
  return `${proto}://${host}/ws/audio`
}

export default function GunnerVoiceControls({ onTranscript, disabled = false }) {
  const [isRecording, setIsRecording] = useState(false)
  const [warning, setWarning] = useState('')
  const [lastTranscript, setLastTranscript] = useState('')
  const [ready, setReady] = useState(false)
  const wsRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const mediaStreamRef = useRef(null)
  const chunkSequenceRef = useRef(0)
  const stopTimerRef = useRef(null)
  const handlerRef = useRef(onTranscript)
  const audioContextRef = useRef(null)
  const analyserRef = useRef(null)
  const silenceTimerRef = useRef(null)
  const lastSoundTimeRef = useRef(Date.now())

  useEffect(() => {
    handlerRef.current = onTranscript
  }, [onTranscript])

  const cleanupMedia = useCallback(() => {
    if (stopTimerRef.current) {
      clearTimeout(stopTimerRef.current)
      stopTimerRef.current = null
    }
    if (silenceTimerRef.current) {
      clearInterval(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
    if (audioContextRef.current) {
      try {
        audioContextRef.current.close()
      } catch {}
      audioContextRef.current = null
    }
    analyserRef.current = null
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => {
        try {
          track.stop()
        } catch {}
      })
      mediaStreamRef.current = null
    }
  }, [])

  const sendWsMessage = useCallback((payload) => {
    const ws = wsRef.current
    if (ws && ws.readyState === 1) {
      try {
        ws.send(JSON.stringify(payload))
        return true
      } catch (err) {
        console.error('[Gunner Voice] Failed to send payload', err)
      }
    }
    return false
  }, [])

  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current
    if (recorder && recorder.state !== 'inactive') {
      try {
        recorder.stop()
      } catch (err) {
        console.error('[Gunner Voice] Failed to stop recorder', err)
      }
    }
    mediaRecorderRef.current = null
    sendWsMessage({ type: 'stop_recording' })
    cleanupMedia()
    setIsRecording(false)
  }, [cleanupMedia, sendWsMessage])

  const startVAD = useCallback((stream) => {
    try {
      const audioContext = new (window.AudioContext || window.webkitAudioContext)()
      const analyser = audioContext.createAnalyser()
      const microphone = audioContext.createMediaStreamSource(stream)

      analyser.fftSize = 512
      analyser.smoothingTimeConstant = 0.8
      microphone.connect(analyser)

      audioContextRef.current = audioContext
      analyserRef.current = analyser
      lastSoundTimeRef.current = Date.now()

      // Check audio level every 100ms
      silenceTimerRef.current = setInterval(() => {
        if (!analyserRef.current) return

        const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount)
        analyserRef.current.getByteFrequencyData(dataArray)

        // Calculate average volume
        const average = dataArray.reduce((sum, value) => sum + value, 0) / dataArray.length

        // Convert to decibels (rough approximation)
        const decibels = average > 0 ? 20 * Math.log10(average / 255) : -Infinity

        if (decibels > SILENCE_THRESHOLD) {
          // Sound detected - reset silence timer
          lastSoundTimeRef.current = Date.now()
        } else {
          // Check if we've been silent long enough
          const silenceDuration = Date.now() - lastSoundTimeRef.current
          if (silenceDuration >= SILENCE_DURATION) {
            console.log('[Gunner Voice] Auto-stopping after', silenceDuration, 'ms of silence')
            stopRecording()
          }
        }
      }, 100)
    } catch (err) {
      console.warn('[Gunner Voice] VAD setup failed, using manual mode:', err)
    }
  }, [stopRecording])

  useEffect(() => {
    if (disabled && isRecording) {
      stopRecording()
    }
  }, [disabled, isRecording, stopRecording])

  useEffect(() => {
    const url = getWsUrl()
    if (!url) return
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setReady(true)
      setWarning('')
    }

    ws.onerror = () => {
      setReady(false)
      setWarning('Voice service unavailable. Refresh to reconnect.')
    }

    ws.onclose = () => {
      setReady(false)
      if (isRecording) {
        stopRecording()
      }
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg?.type === 'transcription') {
          if (typeof msg.text === 'string' && msg.text.trim()) {
            setLastTranscript(msg.text.trim())
            setWarning('')
            handlerRef.current?.(msg.text)
          } else if (msg?.code === 'NOT_CONFIGURED') {
            setWarning('Speech-to-text not configured.')
          } else if (msg?.message) {
            setWarning(msg.message)
          }
        } else if (msg?.message) {
          setWarning(msg.message)
        }
      } catch (err) {
        console.error('[Gunner Voice] Failed to parse WS payload', err)
      }
    }

    return () => {
      try {
        ws.close()
      } catch {}
      wsRef.current = null
    }
  }, [cleanupMedia, stopRecording])

  const beginRecording = useCallback(async () => {
    stopSpeaking()
    if (disabled) {
      return
    }
    if (!ready) {
      setWarning('Voice channel offline.')
      return
    }
    if (!navigator?.mediaDevices?.getUserMedia) {
      setWarning('Microphone access is not available in this browser.')
      return
    }
    stopSpeaking()
    setWarning('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaStreamRef.current = stream

      // Start Voice Activity Detection for auto-stop on silence
      startVAD(stream)

      const options = pickRecorderOptions()
      const recorder = options ? new MediaRecorder(stream, options) : new MediaRecorder(stream)
      mediaRecorderRef.current = recorder
      chunkSequenceRef.current = 0

      recorder.ondataavailable = async (event) => {
        if (!event.data || event.data.size === 0) return
        try {
          const buffer = await event.data.arrayBuffer()
          const chunk = arrayBufferToBase64(buffer)
          chunkSequenceRef.current += 1
          const ok = sendWsMessage({ type: 'audio_chunk', chunk, sequence: chunkSequenceRef.current })
          if (!ok) {
            setWarning('Voice service connection lost.')
            stopRecording()
          }
        } catch (err) {
          console.error('[Gunner Voice] Failed to process audio chunk', err)
          setWarning('Microphone audio failed. Try again.')
        }
      }

      recorder.onerror = () => {
        setWarning('Microphone error. Please retry.')
        stopRecording()
      }

      const started = sendWsMessage({ type: 'start_recording' })
      if (!started) {
        setWarning('Voice service unavailable.')
        stopRecording()
        return
      }

      recorder.start(300)
      setIsRecording(true)
      stopTimerRef.current = setTimeout(() => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
          stopRecording()
        }
      }, MAX_RECORD_MS)
    } catch (err) {
      console.error('[Gunner Voice] Unable to access microphone', err)
      setWarning('Microphone permission denied.')
    }
  }, [disabled, ready, sendWsMessage, stopRecording, startVAD])

  useEffect(() => {
    return () => {
      stopRecording()
    }
  }, [stopRecording])

  const statusMessage = (() => {
    if (isRecording) return 'Listening...'
    if (warning) return warning
    if (lastTranscript) {
      const clipped = lastTranscript.length > 28 ? `${lastTranscript.slice(0, 28)}…` : lastTranscript
      return `Last: "${clipped}"`
    }
    return ready ? 'Voice mic ready' : 'Voice mic offline'
  })()

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <button
        type="button"
        className={`mic-btn ${isRecording ? 'recording' : ''}`}
        onClick={isRecording ? stopRecording : beginRecording}
        disabled={disabled || !ready}
        aria-label={isRecording ? 'Stop recording' : 'Start voice recording'}
        style={{
          background: isRecording ? '#ef4444' : '#444',
          border: `2px solid ${isRecording ? '#ef4444' : '#666'}`,
          borderRadius: '8px',
          padding: '6px 12px',
          cursor: disabled || !ready ? 'not-allowed' : 'pointer',
          color: '#fff',
          fontWeight: 600
        }}
      >
        {isRecording ? 'Stop' : 'Mic'}
      </button>
      <span style={{ fontSize: '12px', color: '#cbd5f5' }}>{statusMessage}</span>
    </div>
  )
}
