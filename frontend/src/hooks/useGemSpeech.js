/**
 * useGemSpeech — Gem Architecture shared speech hook.
 *
 * Provides MediaRecorder → WebSocket → server-side Whisper STT with
 * optional Voice Activity Detection (VAD) for auto-stop on silence.
 *
 * Guardrails enforced:
 *  - Proxy-only: all traffic routes through the local gateway /ws/audio
 *  - Stateless: reads ProfileContext for identity, stores no API keys
 *  - Non-blocking: getUserMedia + MediaRecorder are fully async
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useProfileContext } from '../context/ProfileContext'

// ---------------------------------------------------------------------------
// Utilities (moved from VoicePanel)
// ---------------------------------------------------------------------------

const GATEWAY = typeof window !== 'undefined'
    ? (window.location.port === '5173' ? 'http://localhost:8787' : window.location.origin)
    : 'http://localhost:8787'

function arrayBufferToBase64(buffer) {
    let binary = ''
    const bytes = new Uint8Array(buffer)
    for (let i = 0; i < bytes.byteLength; i += 1) {
        binary += String.fromCharCode(bytes[i])
    }
    if (typeof window !== 'undefined' && typeof window.btoa === 'function') {
        return window.btoa(binary)
    }
    if (typeof Buffer !== 'undefined') {
        return Buffer.from(binary, 'binary').toString('base64')
    }
    throw new Error('No base64 encoder available')
}

function pickRecorderOptions() {
    if (typeof window === 'undefined' || typeof window.MediaRecorder === 'undefined') {
        return undefined
    }
    const preferred = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
    const supported = preferred.find(
        type => typeof window.MediaRecorder.isTypeSupported === 'function' && window.MediaRecorder.isTypeSupported(type)
    )
    return supported ? { mimeType: supported } : undefined
}

// ---------------------------------------------------------------------------
// VAD constants
// ---------------------------------------------------------------------------

const VAD_SILENCE_THRESHOLD = 5     // volume 0-100
const VAD_SILENCE_DURATION = 1500   // ms of silence before auto-stop
const VAD_CHECK_INTERVAL = 100      // ms between volume checks

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * @param {Object}  options
 * @param {boolean} [options.autoStopEnabled=true]  — VAD auto-stop on silence
 * @param {(text: string) => void} [options.onTranscript] — fired with final transcript
 * @param {string}  [options.panelName='unknown']   — identifies the calling panel
 */
export function useGemSpeech({ autoStopEnabled = true, onTranscript = null, panelName = 'unknown' } = {}) {
    // ---- State exposed to consumer ----
    const [isRecording, setIsRecording] = useState(false)
    const [wsConnected, setWsConnected] = useState(false)
    const [lastTranscript, setLastTranscript] = useState('')
    const [warning, setWarning] = useState('')

    // ---- ProfileContext (stateless identity) ----
    const { profile: sharedProfile } = useProfileContext()

    // ---- Refs (recording hardware) ----
    const wsRef = useRef(null)
    const mediaRecorderRef = useRef(null)
    const mediaStreamRef = useRef(null)
    const chunkSequenceRef = useRef(0)

    // ---- Refs (VAD) ----
    const audioContextRef = useRef(null)
    const analyserRef = useRef(null)
    const silenceTimerRef = useRef(null)
    const vadCheckIntervalRef = useRef(null)

    // Stable references for options that may change between renders
    const onTranscriptRef = useRef(onTranscript)
    const autoStopRef = useRef(autoStopEnabled)
    const panelNameRef = useRef(panelName)
    useEffect(() => { onTranscriptRef.current = onTranscript }, [onTranscript])
    useEffect(() => { autoStopRef.current = autoStopEnabled }, [autoStopEnabled])
    useEffect(() => { panelNameRef.current = panelName }, [panelName])

    // ====================================================================
    // Cleanup helpers
    // ====================================================================

    const cleanupStream = useCallback(() => {
        if (mediaStreamRef.current) {
            mediaStreamRef.current.getTracks().forEach(track => {
                try { track.stop() } catch { }
            })
            mediaStreamRef.current = null
        }
    }, [])

    const cleanupVAD = useCallback(() => {
        if (silenceTimerRef.current) {
            clearTimeout(silenceTimerRef.current)
            silenceTimerRef.current = null
        }
        if (vadCheckIntervalRef.current) {
            clearInterval(vadCheckIntervalRef.current)
            vadCheckIntervalRef.current = null
        }
        if (audioContextRef.current) {
            try { audioContextRef.current.close() } catch { }
            audioContextRef.current = null
        }
        analyserRef.current = null
    }, [])

    // ====================================================================
    // WebSocket messaging
    // ====================================================================

    const sendWsMessage = useCallback((payload, warnOnFailure = false) => {
        const ws = wsRef.current
        if (ws && ws.readyState === WebSocket.OPEN) {
            try {
                ws.send(JSON.stringify(payload))
                return true
            } catch (err) {
                console.error('[useGemSpeech] Failed to send WS payload', err)
            }
        }
        if (warnOnFailure) {
            setWarning('Voice service unavailable. Please refresh and try again.')
        }
        return false
    }, [])

    const requestStartRecording = useCallback(
        () => sendWsMessage({ type: 'start_recording' }, true),
        [sendWsMessage]
    )

    const requestStopRecording = useCallback(
        (warnOnFailure = false) => sendWsMessage({ type: 'stop_recording' }, warnOnFailure),
        [sendWsMessage]
    )

    const emitAudioChunk = useCallback(
        (base64, sequence) => sendWsMessage({ type: 'audio_chunk', chunk: base64, data: base64, sequence }),
        [sendWsMessage]
    )

    // ====================================================================
    // Voice Activity Detection (VAD)
    // ====================================================================

    const startVAD = useCallback((stream) => {
        if (!autoStopRef.current) return

        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext
            const audioContext = new AudioContext()
            const analyser = audioContext.createAnalyser()
            const microphone = audioContext.createMediaStreamSource(stream)

            analyser.fftSize = 512
            analyser.smoothingTimeConstant = 0.8
            microphone.connect(analyser)

            audioContextRef.current = audioContext
            analyserRef.current = analyser

            const bufferLength = analyser.frequencyBinCount
            const dataArray = new Uint8Array(bufferLength)
            let silenceStart = null

            vadCheckIntervalRef.current = setInterval(() => {
                analyser.getByteFrequencyData(dataArray)
                const average = dataArray.reduce((sum, value) => sum + value, 0) / bufferLength
                const volume = Math.round((average / 255) * 100)

                if (volume < VAD_SILENCE_THRESHOLD) {
                    if (silenceStart === null) {
                        silenceStart = Date.now()
                    } else if (Date.now() - silenceStart >= VAD_SILENCE_DURATION) {
                        console.log('[useGemSpeech] VAD silence detected — auto-stopping')
                        const recorder = mediaRecorderRef.current
                        if (recorder && recorder.state !== 'inactive') {
                            try { recorder.stop() } catch (err) {
                                console.error('[useGemSpeech] Failed to stop MediaRecorder from VAD', err)
                            }
                        }
                        cleanupVAD()
                    }
                } else {
                    silenceStart = null
                }
            }, VAD_CHECK_INTERVAL)
        } catch (err) {
            console.error('[useGemSpeech] Failed to start VAD:', err)
        }
    }, [cleanupVAD])

    // ====================================================================
    // Recording lifecycle
    // ====================================================================

    const stopRecording = useCallback((options = {}) => {
        const { skipSignal = false } = options
        const recorder = mediaRecorderRef.current
        if (recorder && recorder.state !== 'inactive') {
            try { recorder.stop() } catch (err) {
                console.error('[useGemSpeech] Failed to stop MediaRecorder', err)
            }
        }
        mediaRecorderRef.current = null
        cleanupStream()
        cleanupVAD()
        if (!skipSignal) {
            requestStopRecording(true)
        }
        setIsRecording(false)
    }, [cleanupStream, cleanupVAD, requestStopRecording])

    const startRecording = useCallback(async () => {
        setWarning('')
        if (!navigator?.mediaDevices?.getUserMedia) {
            setWarning('Microphone access is not supported in this browser.')
            return
        }
        if (typeof window === 'undefined' || typeof window.MediaRecorder === 'undefined') {
            setWarning('MediaRecorder API is not available in this browser.')
            return
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
            mediaStreamRef.current = stream
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
                    const ok = emitAudioChunk(chunk, chunkSequenceRef.current)
                    if (!ok) {
                        setWarning('Voice service unavailable. Please refresh and try again.')
                        stopRecording({ skipSignal: true })
                    }
                } catch (err) {
                    console.error('[useGemSpeech] Failed to process audio chunk', err)
                    setWarning('Failed to process microphone audio.')
                }
            }

            recorder.onerror = (event) => {
                console.error('[useGemSpeech] MediaRecorder error', event?.error)
                setWarning('Microphone error occurred. Stopping recording.')
                stopRecording()
            }

            recorder.onstop = cleanupStream

            const started = requestStartRecording()
            if (!started) {
                stopRecording({ skipSignal: true })
                return
            }

            recorder.start(250)
            setIsRecording(true)

            // Start VAD for auto-stop
            startVAD(stream)
        } catch (err) {
            console.error('[useGemSpeech] Unable to access microphone', err)
            setWarning('Microphone permission denied or unavailable.')
            stopRecording({ skipSignal: true })
        }
    }, [cleanupStream, emitAudioChunk, requestStartRecording, startVAD, stopRecording])

    const toggleMic = useCallback(() => {
        if (isRecording) {
            stopRecording()
        } else {
            startRecording()
        }
    }, [isRecording, startRecording, stopRecording])

    // ====================================================================
    // Transcript broadcast — pipes to /api/local/profile/primary
    // ====================================================================

    const broadcastTranscript = useCallback(async (text) => {
        try {
            const userId = sharedProfile?.userId || 'guest'
            const displayName = sharedProfile?.displayName || 'Guest'
            await fetch(`${GATEWAY}/api/local/profile/primary`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'x-scope': 'state',
                    'x-panel': panelNameRef.current
                },
                body: JSON.stringify({
                    user_id: userId,
                    display_name: displayName,
                    last_transcript: text,
                    transcript_source: panelNameRef.current,
                    transcript_timestamp: new Date().toISOString()
                })
            })
        } catch (err) {
            console.warn('[useGemSpeech] Transcript broadcast failed:', err)
        }
    }, [sharedProfile?.userId, sharedProfile?.displayName])

    // ====================================================================
    // WebSocket subscription — connects to /ws/audio gateway
    // ====================================================================

    useEffect(() => {
        const isDev = typeof window !== 'undefined' && window.location.port === '5173'
        const proto = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss' : 'ws'
        const wsUrl = isDev
            ? 'ws://localhost:8787/ws/audio'
            : `${proto}://${window.location.host}/ws/audio`

        console.log('[useGemSpeech] Connecting to WebSocket:', wsUrl)
        const ws = new WebSocket(wsUrl)
        wsRef.current = ws

        ws.onopen = () => {
            setWsConnected(true)
        }

        ws.onmessage = (ev) => {
            try {
                const msg = JSON.parse(ev.data)

                if (msg?.code === 'AUDIO_TOO_LONG') {
                    setWarning('Recording too long — try a shorter phrase.')
                    setIsRecording(false)
                }

                if (msg?.type === 'transcription') {
                    setIsRecording(false)
                    if (typeof msg.text === 'string' && msg.text.length > 0) {
                        setLastTranscript(msg.text)
                        setWarning('')

                        // Fire the consumer's callback
                        onTranscriptRef.current?.(msg.text)

                        // Broadcast to session sync endpoint
                        broadcastTranscript(msg.text)
                    } else if (msg.code === 'NOT_CONFIGURED') {
                        setLastTranscript('STT not configured')
                        setWarning('STT not configured. Add an OpenAI key in settings.')
                    } else if (msg.message) {
                        setWarning(msg.message)
                    }
                }
            } catch (error) {
                console.error('[useGemSpeech] Failed to parse WS message', error)
            }
        }

        ws.onerror = () => {
            setWarning('Voice service connection error. Please refresh and try again.')
            setWsConnected(false)
        }

        ws.onclose = () => {
            setIsRecording(false)
            setWsConnected(false)
            setWarning('Voice service disconnected. Refresh to reconnect.')
        }

        return () => {
            try { ws.close() } catch { }
            wsRef.current = null
        }
    }, [broadcastTranscript])

    // ---- Unmount safety: stop any active recording ----
    useEffect(() => {
        return () => {
            const recorder = mediaRecorderRef.current
            if (recorder && recorder.state !== 'inactive') {
                try { recorder.stop() } catch { }
            }
            cleanupStream()
            cleanupVAD()
        }
    }, [cleanupStream, cleanupVAD])

    // ====================================================================
    // Public API
    // ====================================================================

    return {
        isRecording,
        wsConnected,
        lastTranscript,
        warning,
        toggleMic,
        startRecording,
        stopRecording,
    }
}
