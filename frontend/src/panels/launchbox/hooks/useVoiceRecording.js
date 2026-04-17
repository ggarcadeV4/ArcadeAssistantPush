import { useCallback, useEffect, useRef, useState } from 'react'
import { stopSpeaking } from '../../../services/ttsClient'
import { buildGatewayWsIdentityUrl, generateCorrelationId } from '../../../utils/network'

const pickRecorderOptions = () => {
  if (typeof window === 'undefined' || typeof window.MediaRecorder === 'undefined') {
    return undefined
  }
  if (typeof window.MediaRecorder.isTypeSupported !== 'function') {
    return undefined
  }
  const preferred = ['audio/wav', 'audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
  const supported = preferred.find(type => window.MediaRecorder.isTypeSupported(type))
  return supported ? { mimeType: supported } : undefined
}

export default function useVoiceRecording({ addMessage, showToast, onTranscript, setLoraState }) {
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)

  const wsRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const mediaStreamRef = useRef(null)
  const chunkSequenceRef = useRef(0)

  const cleanupVoiceStream = useCallback(() => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => {
        try { track.stop() } catch { }
      })
      mediaStreamRef.current = null
    }
  }, [])

  const sendVoiceMessage = useCallback((payload) => {
    if (typeof WebSocket === 'undefined') {
      console.error('[LaunchBox Voice] WebSocket not supported')
      return false
    }
    const ws = wsRef.current
    if (!ws) {
      console.error('[LaunchBox Voice] WebSocket not initialized')
      return false
    }
    if (ws.readyState !== WebSocket.OPEN) {
      console.error('[LaunchBox Voice] WebSocket not open. State:', ws.readyState, '(0=CONNECTING, 1=OPEN, 2=CLOSING, 3=CLOSED)')
      return false
    }
    try {
      console.log('[LaunchBox Voice] Sending message:', payload.type)
      ws.send(JSON.stringify(payload))
      return true
    } catch (err) {
      console.error('[LaunchBox Voice] Send failed:', err)
      return false
    }
  }, [])

  const stopVoiceRecording = useCallback((options = {}) => {
    const { skipSignal = false, silent = false } = options
    const recorder = mediaRecorderRef.current
    if (recorder && recorder.state !== 'inactive') {
      try { recorder.stop() } catch { }
    }
    mediaRecorderRef.current = null
    cleanupVoiceStream()

    if (!skipSignal) {
      const lastSeq = chunkSequenceRef.current || 0
      sendVoiceMessage({ type: 'stop_recording', lastSequence: lastSeq })
      if (!silent) setIsTranscribing(true)
    }

    setIsRecording(false)
    if (!silent) {
      setLoraState('listening')
    }
  }, [cleanupVoiceStream, sendVoiceMessage, setLoraState])

  const processVoiceCommand = useCallback((transcript) => {
    const sanitized = (transcript || '').trim()
    if (!sanitized) {
      addMessage("I didn't catch that. Try again.", 'assistant')
      return
    }
    onTranscript(sanitized)
  }, [addMessage, onTranscript])

  const startVoiceRecording = useCallback(async () => {
    console.log('[LaunchBox Voice] Start recording called')
    stopSpeaking()

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition

    const waitForWsOpen = async (timeoutMs = 1500) => {
      const ws = wsRef.current
      if (!ws) return false
      if (ws.readyState === WebSocket.OPEN) return true
      const start = Date.now()
      return await new Promise(resolve => {
        const t = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) { clearInterval(t); resolve(true) }
          else if (Date.now() - start > timeoutMs) { clearInterval(t); resolve(false) }
        }, 50)
      })
    }

    if (SpeechRecognition) {
      console.log('[LaunchBox Voice] Using Web Speech API (native pause detection)')
      const recognition = new SpeechRecognition()
      recognition.continuous = false
      recognition.interimResults = false
      recognition.lang = 'en-US'
      recognition.maxAlternatives = 1

      recognition.onstart = () => {
        console.log('[Web Speech API] 🎙️ Recording started')
        setIsRecording(true)
        setLoraState('listening')
      }

      recognition.onresult = (event) => {
        if (!event.results[0].isFinal) return

        const transcript = event.results[0][0].transcript
        console.log('[Web Speech API] ✅ Transcription:', transcript)

        setIsRecording(false)
        setLoraState('processing')
        processVoiceCommand(transcript)
      }

      recognition.onerror = (event) => {
        console.error('[Web Speech API] Error:', event.error)
        setIsRecording(false)
        setLoraState('idle')

        if (event.error === 'no-speech') {
          showToast('No speech detected. Please try again.')
        } else if (event.error === 'aborted') {
          return
        } else {
          showToast(`Speech recognition error: ${event.error}`)
        }
      }

      recognition.onend = () => {
        console.log('[Web Speech API] 🔴 Recording ended')
        setIsRecording(false)
        setLoraState(prev => (prev === 'listening' ? 'idle' : prev))
      }

      try {
        recognition.start()
        mediaRecorderRef.current = { stop: () => recognition.stop() }
      } catch (err) {
        console.error('[Web Speech API] Failed to start:', err)
        showToast('Failed to start speech recognition.')
        setIsRecording(false)
      }
      return
    }

    console.log('[LaunchBox Voice] Web Speech API unavailable, falling back to MediaRecorder')

    if (typeof navigator === 'undefined' || !navigator?.mediaDevices?.getUserMedia) {
      showToast('Microphone access is not supported in this browser.')
      return
    }
    if (typeof window === 'undefined' || typeof window.MediaRecorder === 'undefined') {
      showToast('MediaRecorder API is not available in this browser.')
      return
    }

    try {
      const wsReady = await waitForWsOpen(1500)
      if (!wsReady) {
        showToast('Voice service unavailable. Please refresh and try again.')
        return
      }

      console.log('[LaunchBox Voice] Requesting microphone access...')
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } })
      console.log('[LaunchBox Voice] Microphone access granted')
      mediaStreamRef.current = stream
      const options = pickRecorderOptions()
      const recorder = options ? new MediaRecorder(stream, options) : new MediaRecorder(stream)
      mediaRecorderRef.current = recorder
      chunkSequenceRef.current = 0

      const audioContext = new (window.AudioContext || window.webkitAudioContext)()
      const source = audioContext.createMediaStreamSource(stream)
      const analyser = audioContext.createAnalyser()
      analyser.fftSize = 512
      analyser.smoothingTimeConstant = 0.1
      source.connect(analyser)

      const dataArray = new Uint8Array(analyser.frequencyBinCount)
      let speechDetected = false
      let silenceStart = null

      const SPEECH_GATE = 8
      const SILENCE_THRESHOLD = 6
      const SILENCE_DURATION = 700

      console.log('[Fallback VAD] 🎙️ Waiting for speech (gate:', SPEECH_GATE, '%)')

      const checkAudio = () => {
        if (!mediaRecorderRef.current || mediaRecorderRef.current.state === 'inactive') {
          audioContext.close()
          return
        }

        analyser.getByteFrequencyData(dataArray)
        const average = dataArray.reduce((sum, value) => sum + value, 0) / dataArray.length
        const volumePercent = Math.round((average / 255) * 100)

        if (!speechDetected) {
          if (volumePercent > SPEECH_GATE) {
            speechDetected = true
            console.log('[Fallback VAD] 🗣️ Speech detected, monitoring for pauses...')
          }
        } else if (volumePercent < SILENCE_THRESHOLD) {
          if (silenceStart === null) {
            silenceStart = Date.now()
          } else {
            const silenceDuration = Date.now() - silenceStart
            if (silenceDuration > SILENCE_DURATION) {
              console.log('[Fallback VAD] ✅ AUTO-STOPPING after', silenceDuration, 'ms silence')
              audioContext.close()
              stopVoiceRecording()
              return
            }
          }
        } else {
          silenceStart = null
        }

        requestAnimationFrame(checkAudio)
      }

      checkAudio()

      recorder.ondataavailable = async (event) => {
        if (!event.data || event.data.size === 0) return
        try {
          const ws = wsRef.current
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(event.data)
          }
          chunkSequenceRef.current += 1
        } catch (err) {
          console.error('Failed to process audio chunk', err)
          showToast('Failed to process microphone audio.')
        }
      }

      recorder.onerror = (event) => {
        console.error('MediaRecorder error', event?.error)
        showToast('Microphone error occurred. Stopping recording.')
        audioContext.close()
        stopVoiceRecording()
      }

      if (!sendVoiceMessage({ type: 'start_recording' })) {
        showToast('Voice service unavailable. Refresh and try again.')
        audioContext.close()
        stopVoiceRecording({ skipSignal: true, silent: true })
        return
      }

      recorder.start(250)
      setIsRecording(true)
      setLoraState('listening')
      addMessage('Listening... say "Launch <game>" or "Search for <term>".', 'assistant')
    } catch (err) {
      console.error('Unable to access microphone', err)
      showToast(err?.name === 'NotAllowedError' ? 'Microphone permission denied.' : 'Microphone unavailable.')
      stopVoiceRecording({ skipSignal: true, silent: true })
    }
  }, [addMessage, processVoiceCommand, sendVoiceMessage, setLoraState, showToast, stopVoiceRecording])

  const handleVoiceTranscript = useCallback((payload) => {
    console.log('[LaunchBox Voice] Received transcription payload:', payload)
    setIsRecording(false)
    setIsTranscribing(false)
    setLoraState('idle')

    if (!payload) {
      console.log('[LaunchBox Voice] No payload received')
      return
    }
    if (payload.code === 'NOT_CONFIGURED') {
      addMessage('Voice transcription is not configured. Add an OpenAI key in settings.', 'assistant')
      showToast('STT not configured')
      return
    }
    if (payload.code === 'AUDIO_TOO_LONG') {
      showToast('Recording too long - try a shorter phrase.')
      return
    }

    const text = (payload.text || '').trim()
    console.log('[LaunchBox Voice] Transcribed text:', text)
    if (!text) {
      addMessage("I didn't catch that. Try again.", 'assistant')
      return
    }

    console.log('[LaunchBox Voice] Processing voice command with text:', text)
    processVoiceCommand(text)
  }, [addMessage, processVoiceCommand, setLoraState, showToast])

  useEffect(() => {
    if (typeof window === 'undefined' || typeof WebSocket === 'undefined') {
      return
    }

    const wsUrl = buildGatewayWsIdentityUrl('/ws/audio', {
      panel: 'launchbox',
      corrId: generateCorrelationId('launchbox-audio')
    })

    console.log('[LaunchBox Voice] Connecting to WebSocket:', wsUrl)
    const socket = new WebSocket(wsUrl)
    wsRef.current = socket

    socket.onopen = () => {
      console.log('[LaunchBox Voice] WebSocket connected')
    }

    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        console.log('[LaunchBox Voice] WebSocket message received:', msg)
        if (msg?.code === 'AUDIO_TOO_LONG') {
          showToast('Recording too long - try a shorter phrase.')
          setIsRecording(false)
          setLoraState('idle')
          return
        }
        if (msg?.type === 'transcription') {
          handleVoiceTranscript(msg)
        }
      } catch (err) {
        console.error('[LaunchBox Voice] WebSocket parse error', err)
      }
    }

    socket.onerror = (err) => {
      console.error('[LaunchBox Voice] WebSocket error:', err)
      showToast('Voice service connection error.')
    }

    socket.onclose = (event) => {
      console.log('[LaunchBox Voice] WebSocket closed. Code:', event.code, 'Reason:', event.reason)
      wsRef.current = null
      setIsRecording(false)
      setLoraState('idle')
    }

    return () => {
      try { socket.close() } catch { }
      wsRef.current = null
    }
  }, [handleVoiceTranscript, setLoraState, showToast])

  useEffect(() => {
    return () => {
      stopVoiceRecording({ skipSignal: true, silent: true })
    }
  }, [stopVoiceRecording])

  return {
    isRecording,
    isTranscribing,
    startVoiceRecording,
    stopVoiceRecording
  }
}
