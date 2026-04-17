import React, { useCallback, useEffect, useRef, useState } from 'react'
import { stopSpeaking } from '../../services/ttsClient'
import { buildGatewayWsIdentityUrl, generateCorrelationId } from '../../utils/network'

// Helper functions for voice recording
// (arrayBufferToBase64 removed - sending binary directly)

const pickRecorderOptions = () => {
  if (typeof window === 'undefined' || typeof window.MediaRecorder === 'undefined') {
    return undefined
  }
  const preferred = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
  const supported = preferred.find(
    type => typeof window.MediaRecorder.isTypeSupported === 'function' && window.MediaRecorder.isTypeSupported(type)
  )
  return supported ? { mimeType: supported } : undefined
}

export default function DocVoiceControls({ onTranscript, ensureChatOpen }) {
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [warning, setWarning] = useState('')
  const [lastTranscript, setLastTranscript] = useState('')

  const wsRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const mediaStreamRef = useRef(null)
  const chunkSequenceRef = useRef(0)
  const audioContextRef = useRef(null)
  const analyserRef = useRef(null)
  const vadIntervalRef = useRef(null)
  const speechDetectedRef = useRef(false)
  const maxTimerRef = useRef(null)
  const endRecordingRef = useRef(null) // Ref to avoid stale closure in timers
  // Backstop so recordings never linger too long
  const MAX_DURATION_MS = 8000
  const START_VAD_DELAY_MS = 200

  // Initialize audio stream on mount (reused)
  useEffect(() => {
    const initStream = async () => {
      if (typeof navigator !== 'undefined' && navigator.mediaDevices) {
        try {
          // Warm up the microphone stream once with Echo Cancellation
          const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true
            }
          })
          mediaStreamRef.current = stream
          console.log('[Doc Voice] Microphone stream initialized (hot) with Echo Cancellation.')
        } catch (err) {
          console.warn('[Doc Voice] Failed to pre-warm microphone:', err)
        }
      }
    }
    initStream()

    return () => {
      // Final cleanup on unmount
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach(track => {
          try { track.stop() } catch { }
        })
        mediaStreamRef.current = null
      }
    }
  }, [])

  const cleanupStream = useCallback(() => {
    // Only stop the recorder, KEEP the stream tracks alive for reuse
    if (mediaRecorderRef.current) {
      if (mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop()
      }
      mediaRecorderRef.current = null
    }
    // mediaStreamRef tracks are NOT stopped here anymore to allow reuse
  }, [])

  const cleanupVAD = useCallback(() => {
    if (vadIntervalRef.current) {
      clearInterval(vadIntervalRef.current)
      vadIntervalRef.current = null
    }
    if (audioContextRef.current) {
      try {
        audioContextRef.current.close()
      } catch { }
      audioContextRef.current = null
    }
    analyserRef.current = null
  }, [])

  const sendWsMessage = useCallback(
    (payload, warnOnFailure = false) => {
      const ws = wsRef.current
      console.log('[Doc Voice] sendWsMessage called:', {
        hasWs: !!ws,
        readyState: ws?.readyState,
        payloadType: payload?.type
      })

      if (ws && ws.readyState === 1) {
        try {
          console.log('[Doc Voice] Sending WebSocket message:', payload)
          ws.send(JSON.stringify(payload))
          return true
        } catch (err) {
          console.error('[Doc Voice] Failed to send payload', err)
        }
      } else {
        console.error('[Doc Voice] Cannot send - WebSocket not ready. State:', ws?.readyState)
      }

      if (warnOnFailure) {
        setWarning('Voice service unavailable. Refresh to reconnect.')
      }
      return false
    },
    []
  )

  const requestStartRecording = useCallback(
    () => sendWsMessage({ type: 'start_recording' }, true),
    [sendWsMessage]
  )
  const requestStopRecording = useCallback(() => sendWsMessage({ type: 'stop_recording' }), [sendWsMessage])
  const emitAudioChunk = useCallback(
    (chunk, sequence) => {
      const ws = wsRef.current
      if (ws && ws.readyState === 1) {
        try {
          ws.send(chunk) // Send binary blob directly
          return true
        } catch (err) {
          console.error('[Doc Voice] Failed to send audio chunk', err)
        }
      }
      return false
    },
    []
  )

  const endRecording = useCallback(
    (options = {}) => {
      const { skipSignal = false } = options
      console.log('[Doc Voice] endRecording called, skipSignal:', skipSignal)
      // Clear the max-duration timer if active
      if (maxTimerRef.current) {
        clearTimeout(maxTimerRef.current)
        maxTimerRef.current = null
      }
      // Clear VAD interval immediately to prevent multiple calls
      if (vadIntervalRef.current) {
        clearInterval(vadIntervalRef.current)
        vadIntervalRef.current = null
      }
      const recorder = mediaRecorderRef.current
      if (recorder && recorder.state !== 'inactive') {
        try {
          recorder.stop()
        } catch (err) {
          console.error('[Doc Voice] Failed to stop recorder', err)
        }
      }
      mediaRecorderRef.current = null
      cleanupStream()
      cleanupVAD()
      if (!skipSignal) {
        requestStopRecording()
        // Let the user know we are sending audio to be transcribed
        setWarning('Thinking...')
        setIsTranscribing(true) // Lock UI
      }
      setIsRecording(false)
    },
    [cleanupStream, cleanupVAD, requestStopRecording]
  )

  // Keep ref updated so timers/VAD always have current endRecording
  useEffect(() => {
    endRecordingRef.current = endRecording
  }, [endRecording])

  const startVAD = useCallback(
    async () => {
      // Use mediaStreamRef instead of passed stream to avoid stale closure
      const stream = mediaStreamRef.current
      if (!stream || !stream.active) {
        console.error('[Doc Voice] VAD: No active stream available')
        return
      }

      try {
        const AudioContext = window.AudioContext || window.webkitAudioContext
        if (!AudioContext) {
          console.error('[Doc Voice] VAD: AudioContext not available')
          return
        }
        const audioContext = new AudioContext()

        // Resume AudioContext if suspended (browser autoplay policy)
        if (audioContext.state === 'suspended') {
          await audioContext.resume()
          console.log('[Doc Voice] AudioContext resumed for VAD')
        }

        const analyser = audioContext.createAnalyser()
        const microphone = audioContext.createMediaStreamSource(stream)

        analyser.fftSize = 512
        analyser.smoothingTimeConstant = 0.8
        microphone.connect(analyser)

        audioContextRef.current = audioContext
        analyserRef.current = analyser

        const bufferLength = analyser.frequencyBinCount
        const dataArray = new Uint8Array(bufferLength)
        const SPEECH_THRESHOLD = 3    // Volume level that counts as speech
        const SILENCE_DURATION = 800  // ~0.8s of silence after speech triggers stop
        let silenceStart = null
        let logCounter = 0

        console.log('[Doc Voice] VAD started, monitoring audio levels...')

        vadIntervalRef.current = setInterval(() => {
          // Check if we should still be running
          if (!mediaRecorderRef.current || mediaRecorderRef.current.state !== 'recording') {
            console.log('[Doc Voice] VAD: Recording stopped, clearing interval')
            if (vadIntervalRef.current) {
              clearInterval(vadIntervalRef.current)
              vadIntervalRef.current = null
            }
            return
          }

          analyser.getByteFrequencyData(dataArray)
          const average = dataArray.reduce((sum, value) => sum + value, 0) / bufferLength
          const volume = Math.round((average / 255) * 100)

          // Log every ~2 seconds to verify VAD is running
          logCounter++
          if (logCounter % 10 === 0) {
            console.log(`[Doc Voice] VAD check - volume: ${volume}, speechDetected: ${speechDetectedRef.current}`)
          }

          if (volume >= SPEECH_THRESHOLD) {
            // User is speaking
            if (!speechDetectedRef.current) {
              console.log('[Doc Voice] Speech detected, volume:', volume)
            }
            speechDetectedRef.current = true
            silenceStart = null
          } else if (speechDetectedRef.current) {
            // Volume dropped below speech threshold after we heard speech = silence
            if (silenceStart === null) {
              silenceStart = Date.now()
              console.log('[Doc Voice] Silence started, waiting for duration...')
            } else if (Date.now() - silenceStart >= SILENCE_DURATION) {
              console.log('[Doc Voice] VAD detected silence - auto-stopping and sending to transcription')
              // Use ref to get current endRecording function (avoids stale closure)
              if (endRecordingRef.current) {
                endRecordingRef.current()
              }
            }
          }
          // If no speech detected yet, just keep waiting (no silenceStart reset needed)
        }, 200)
      } catch (err) {
        console.error('[Doc Voice] Unable to start VAD', err)
      }
    },
    [] // No deps needed - uses refs for everything
  )

  const handleTranscript = useCallback(
    text => {
      const trimmed = (text || '').trim()
      if (!trimmed) return
      setLastTranscript(trimmed)
      setWarning('')
      ensureChatOpen?.()
      onTranscript?.(trimmed)
    },
    [ensureChatOpen, onTranscript]
  )

  const beginRecording = useCallback(async () => {
    setWarning('')

    // Stop any TTS playback when user clicks mic (interrupt Doc)
    stopSpeaking()
    console.log('[Doc Voice] 🔇 Stopped TTS playback')

    // Check WebSocket state BEFORE trying to record
    const ws = wsRef.current
    console.log('[Doc Voice] 🎤 MIC BUTTON CLICKED')
    console.log('[Doc Voice] WebSocket exists?', !!ws)
    console.log('[Doc Voice] WebSocket readyState:', ws?.readyState)
    console.log('[Doc Voice] ReadyState meaning:',
      ws?.readyState === 0 ? 'CONNECTING' :
        ws?.readyState === 1 ? 'OPEN' :
          ws?.readyState === 2 ? 'CLOSING' :
            ws?.readyState === 3 ? 'CLOSED' : 'UNKNOWN'
    )

    if (!navigator?.mediaDevices?.getUserMedia) {
      setWarning('Microphone access is not supported.')
      return
    }
    if (typeof window === 'undefined' || typeof window.MediaRecorder === 'undefined') {
      setWarning('MediaRecorder API is not available.')
      return
    }
    try {
      // Reuse existing stream if valid, or acquire new one with Echo Cancellation
      let stream = mediaStreamRef.current
      if (!stream || !stream.active || stream.getAudioTracks().length === 0 || stream.getAudioTracks()[0].readyState === 'ended') {
        console.log('[Doc Voice] Acquiring new microphone stream with Echo Cancellation...')
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true
          }
        })
        mediaStreamRef.current = stream
      } else {
        console.log('[Doc Voice] Reusing hot microphone stream.')
      }

      const options = pickRecorderOptions()
      const recorder = options ? new MediaRecorder(stream, options) : new MediaRecorder(stream)
      mediaRecorderRef.current = recorder
      chunkSequenceRef.current = 0

      recorder.ondataavailable = async event => {
        if (!event.data || event.data.size === 0) {
          console.log('[Doc Voice] Empty audio chunk received')
          return
        }
        console.log('[Doc Voice] Audio chunk received, size:', event.data.size)
        try {
          const chunk = event.data // Send Blob directly
          chunkSequenceRef.current += 1
          console.log('[Doc Voice] Sending chunk', chunkSequenceRef.current, 'to WebSocket')
          const ok = emitAudioChunk(chunk, chunkSequenceRef.current)
          if (!ok) {
            console.error('[Doc Voice] Failed to send chunk - WebSocket not ready')
            setWarning('Voice service unavailable. Please refresh.')
            endRecording({ skipSignal: true })
          }
        } catch (err) {
          console.error('[Doc Voice] Failed to process audio chunk', err)
          setWarning('Failed to process microphone audio.')
        }
      }

      recorder.onerror = event => {
        console.error('[Doc Voice] MediaRecorder error', event?.error)
        setWarning('Microphone error occurred.')
        endRecording({ skipSignal: true })
      }

      recorder.onstop = cleanupStream

      const started = requestStartRecording()
      if (!started) {
        console.error('[Doc Voice] Failed to send start_recording signal')
        endRecording({ skipSignal: true })
        return
      }

      console.log('[Doc Voice] Starting MediaRecorder, state:', recorder.state)
      try {
        recorder.start(250)
        console.log('[Doc Voice] MediaRecorder started successfully')
      } catch (err) {
        console.error('[Doc Voice] Failed to start MediaRecorder:', err)
        setWarning('Failed to start recording. Please try again.')
        endRecording({ skipSignal: true })
        return
      }

      speechDetectedRef.current = false
      setIsRecording(true)
      setIsTranscribing(false)
      setWarning('Listening...')

      // Start voice activity detection for auto-stop after silence
      setTimeout(() => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
          startVAD() // Uses mediaStreamRef internally
        }
      }, START_VAD_DELAY_MS)

      // Hard backstop: auto-stop after max duration even if VAD never triggers
      maxTimerRef.current = setTimeout(() => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
          console.log('[Doc Voice] Max duration reached - auto-stopping')
          // Use ref to avoid stale closure
          if (endRecordingRef.current) {
            endRecordingRef.current()
          }
        }
      }, MAX_DURATION_MS)
    } catch (err) {
      console.error('[Doc Voice] Unable to access microphone', err)
      setWarning('Microphone permission denied or unavailable.')
      endRecording({ skipSignal: true })
    }
  }, [cleanupStream, emitAudioChunk, endRecording, requestStartRecording, startVAD])

  const toggleMic = useCallback(() => {
    if (isRecording) {
      endRecording()
    } else {
      beginRecording()
    }
  }, [beginRecording, endRecording, isRecording])

  useEffect(() => {
    const wsUrl = buildGatewayWsIdentityUrl('/ws/audio', {
      panel: 'system-health',
      corrId: generateCorrelationId('system-health-audio')
    })

    console.log('[Doc Voice] Connecting to WebSocket:', wsUrl)
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      console.log('[Doc Voice] ✅ WebSocket CONNECTED, readyState:', ws.readyState)
    }

    ws.onerror = (error) => {
      console.error('[Doc Voice] ❌ WebSocket ERROR:', error)
      setWarning('WebSocket connection failed. Check if gateway is running.')
    }

    ws.onclose = (event) => {
      console.log('[Doc Voice] 🔌 WebSocket CLOSED:', event.code, event.reason)
    }

    ws.onmessage = event => {
      try {
        const msg = JSON.parse(event.data)
        if (msg?.code === 'AUDIO_TOO_LONG') {
          setWarning('Recording too long. Try a shorter request.')
          setIsRecording(false)
        } else if (msg?.code === 'NOT_CONFIGURED') {
          setWarning('Speech-to-text not configured. Add an API key in settings.')
        } else if (msg?.type === 'transcription') {
          setIsRecording(false)
          setIsTranscribing(false) // Unlock UI
          cleanupVAD()
          const transcript = typeof msg.text === 'string' ? msg.text : ''
          if (transcript.trim()) {
            setWarning('')
            handleTranscript(transcript)
          }
        } else if (msg?.message) {
          setWarning(msg.message)
        }
      } catch (err) {
        console.error('[Doc Voice] Failed to parse message', err)
      }
    }

    ws.onerror = () => {
      setWarning('Voice channel error. Refresh to reconnect.')
    }

    return () => {
      console.log('[Doc Voice] 🧹 Cleanup: closing WebSocket')
      ws.close()
      cleanupStream()
      cleanupVAD()
    }
  }, []) // Empty dependency array - only run once on mount

  return (
    <div className="doc-voice-controls">
      <button
        className={`doc-voice-button ${isRecording ? 'recording' : ''} ${isTranscribing ? 'transcribing' : ''}`}
        onClick={toggleMic}
        disabled={isTranscribing}
        aria-label={isTranscribing ? 'Transcribing...' : isRecording ? 'Stop voice input' : 'Start voice input'}
        title={isTranscribing ? 'Thinking...' : isRecording ? 'Stop listening' : 'Ask Doc with your voice'}
      >
        {isTranscribing ? '⏳' : isRecording ? 'REC' : 'MIC'}
      </button>
      <div className="doc-voice-readout">
        {isRecording && <span className="doc-voice-status">Listening...</span>}
        {!isRecording && lastTranscript && (
          <span className="doc-voice-last">
            Last: "
            {lastTranscript.slice(0, 40)}
            {lastTranscript.length > 40 ? '...' : ''}"
          </span>
        )}
        {warning && <span className="doc-voice-warning">{warning}</span>}
      </div>
    </div>
  )
}
