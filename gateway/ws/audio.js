import { Blob } from 'buffer'
import { promises as fs } from 'fs'
import path from 'path'

const WHISPER_API_URL = process.env.WHISPER_API_URL || 'https://api.openai.com/v1/audio/transcriptions'
const WHISPER_MODEL = process.env.WHISPER_MODEL || 'whisper-1'
const MAX_RECORD_MS = Number(process.env.STT_MAX_MS || 15000)
const MAX_AUDIO_BYTES = Number(process.env.STT_MAX_AUDIO_BYTES || 2 * 1024 * 1024)
const LATE_CHUNK_GRACE_MS = Number(process.env.STT_LATE_CHUNK_GRACE_MS || 1200)
const STT_DRAIN_MS = Number(process.env.STT_DRAIN_MS || 150)
const STT_MIN_CHUNKS = Number(process.env.STT_MIN_CHUNKS || 6)
// STT_SAVE_DEBUG is DISABLED in gateway (Golden Drive contract: gateway must not write to disk).
// If STT debug audio is needed, implement saving in backend via /api/local/voice/save-debug endpoint.
const STT_SAVE_DEBUG = false  // Disabled - gateway must not write files
const STT_DEBUG_DIR = null  // Not used

const sessions = new Map() // connectionId -> { chunks: Buffer[], bytes: number, startedAt: number, recording: boolean }
const CONTROL_CHAR_REGEX = /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g

export function setupAudioWebSocket(wss) {
  console.log('[Audio WS] Setting up audio WebSocket handler...')

  wss.on('connection', (ws, req) => {
    // Log every connection attempt for debugging
    console.log('[Audio WS] Connection attempt received:', {
      url: req.url,
      host: req.headers.host,
      origin: req.headers.origin,
      wsKey: req.headers['sec-websocket-key']?.slice(0, 8) + '...'
    })

    // Wrap entire handler in try-catch to prevent connection failures
    try {
      const host = req.headers.host || 'localhost'
      const url = new URL(req.url, `http://${host}`)

      if (url.pathname !== '/ws/audio') {
        console.log(`[Audio WS] Ignoring non-audio path: ${url.pathname}`)
        return
      }

      const connectionId = req.headers['sec-websocket-key'] || `${Date.now()}-${Math.random().toString(16).slice(2)}`
      console.log(`[Audio WS] ✅ Audio client connected: ${connectionId}`)

      ws.on('message', async (raw, isBinary) => {
        console.log('[Audio WS] ⚡ MESSAGE RECEIVED - isBinary:', isBinary, 'type:', typeof raw, 'length:', raw?.length)
        try {
          if (isBinary) {
            appendChunk(connectionId, Buffer.isBuffer(raw) ? raw : Buffer.from(raw), ws)
            return
          }

          const payload = typeof raw === 'string' ? raw : raw.toString()
          const preview = payload.replace(CONTROL_CHAR_REGEX, '?').substring(0, 100)
          console.log('[Audio WS] Payload preview:', preview)

          const data = JSON.parse(payload)
          console.log('[Audio WS] Successfully parsed JSON, type:', data.type)
          await handleControlMessage(connectionId, data, ws)
        } catch (err) {
          if (!isBinary) {
            console.error('Audio WebSocket message error:', err)
            safeSend(ws, { type: 'error', message: err?.message || 'Invalid message format' })
            return
          }
          console.warn('[Audio WS] Binary payload could not be parsed as JSON, treating as audio chunk')
          appendChunk(connectionId, Buffer.isBuffer(raw) ? raw : Buffer.from(raw), ws)
        }
      })

      ws.on('close', (code, reason) => {
        console.log(`[Audio WS] Client disconnected (${connectionId}): ${code} ${reason}`)
        cleanupSession(connectionId)
      })

      ws.on('error', (err) => {
        console.error('Audio WebSocket error:', err)
        cleanupSession(connectionId)
      })

      safeSend(ws, {
        type: 'connected',
        message: 'Audio WebSocket ready',
        supported_formats: ['audio/webm', 'audio/wav'],
        max_chunk_size: 8192
      })
    } catch (err) {
      console.error('[Audio WS] Connection handler error:', err)
      // Try to send error to client before closing
      try {
        safeSend(ws, { type: 'error', message: 'Server error during connection setup' })
      } catch { }
      // Don't close the socket here - let the client retry
    }
  })

  console.log('Audio WebSocket server configured')
}

async function handleControlMessage(connectionId, data, ws) {
  console.log('[Audio WS] Received message type:', data.type)
  switch (data.type) {
    case 'start_recording':
      console.log('[Audio WS] Starting recording for connection:', connectionId)
      startRecording(connectionId, ws)
      break
    case 'stop_recording':
      console.log('[Audio WS] Stopping recording for connection:', connectionId)
      await stopRecording(connectionId, ws, data)
      break
    case 'audio_chunk': {
      const encoded = data.chunk
      if (!encoded) return
      const sequence = Number.isFinite(data.sequence) ? Number(data.sequence) : undefined
      appendChunk(connectionId, Buffer.from(encoded, 'base64'), ws, sequence)
      break
    }
    case 'ping':
      safeSend(ws, { type: 'pong', timestamp: Date.now() })
      break
    default:
      console.log('[Audio WS] Unknown message type:', data.type)
      safeSend(ws, { type: 'error', message: `Unknown message type: ${data.type}` })
  }
}

function startRecording(connectionId, ws) {
  console.log('[Audio WS] dYY� CREATE SESSION for:', connectionId)
  sessions.set(connectionId, {
    chunks: [],
    bytes: 0,
    startedAt: Date.now(),
    recording: true,
    finalizeTimer: null,
    finalizing: false,
    lastSequence: undefined,
    expectedLastSequence: undefined,
    stopReceivedAt: null
  })
  console.log('[Audio WS] dYY� SESSION CREATED, active sessions:', sessions.size)
  safeSend(ws, { type: 'recording_started', timestamp: Date.now() })
}

function appendChunk(connectionId, chunk, ws, sequence) {
  let session = sessions.get(connectionId)
  if (!session) {
    console.warn('[Audio WS] ⚠️ Session missing for chunk - auto-creating session to recover')
    startRecording(connectionId, ws)
    session = sessions.get(connectionId)
  }
  console.log('[Audio WS] dY"� appendChunk called, session exists:', !!session, 'recording:', session?.recording)
  if (!session || session.finalizing || !Buffer.isBuffer(chunk)) return

  if (typeof sequence === 'number') {
    if (session.lastSequence !== undefined && sequence <= session.lastSequence) {
      console.warn('[Audio WS] ⚠️ Out-of-order or duplicate chunk ignored', { connectionId, sequence, lastSequence: session.lastSequence })
      return
    }
    session.lastSequence = sequence
  }

  session.chunks.push(chunk)
  session.bytes += chunk.length
  console.log('[Audio WS] dY"� Chunk added, total chunks:', session.chunks.length, 'total bytes:', session.bytes)

  const elapsed = Date.now() - session.startedAt
  if (elapsed > MAX_RECORD_MS || session.bytes > MAX_AUDIO_BYTES) {
    sessions.delete(connectionId)
    safeSend(ws, { type: 'transcription', status: 413, code: 'AUDIO_TOO_LONG', message: 'Recording too long' })
    return
  }

  safeSend(ws, {
    type: 'chunk_received',
    chunk_count: session.chunks.length,
    buffered_bytes: session.bytes
  })

  if (!session.recording) {
    scheduleFinalize(connectionId, ws)
  }
}

async function stopRecording(connectionId, ws, payload = {}) {
  console.log('[Audio WS] Stop recording called for connection:', connectionId)
  const session = sessions.get(connectionId)
  if (!session) {
    console.log('[Audio WS] Stop recording received but no active session:', connectionId)
    return
  }

  if (!session.recording && session.finalizing) {
    console.log('[Audio WS] Stop already in progress for:', connectionId)
    return
  }

  if (typeof payload.lastSequence === 'number') {
    session.expectedLastSequence = Number(payload.lastSequence)
  }
  session.stopReceivedAt = Date.now()
  session.recording = false
  scheduleFinalize(connectionId, ws, STT_DRAIN_MS)
}

function scheduleFinalize(connectionId, ws, delayOverride) {
  const session = sessions.get(connectionId)
  if (!session || session.finalizing) return
  if (session.finalizeTimer) {
    clearTimeout(session.finalizeTimer)
  }
  const delay = typeof delayOverride === 'number'
    ? delayOverride
    : (session.recording ? LATE_CHUNK_GRACE_MS : STT_DRAIN_MS)
  session.finalizeTimer = setTimeout(() => {
    session.finalizeTimer = null
    attemptFinalize(connectionId, ws)
      .catch(err => console.error('[Audio WS] finalizeRecording failed:', err))
  }, delay)
}

async function attemptFinalize(connectionId, ws) {
  const session = sessions.get(connectionId)
  if (!session) return
  if (session.finalizing) return

  if (typeof session.expectedLastSequence === 'number' &&
    typeof session.lastSequence === 'number' &&
    session.lastSequence < session.expectedLastSequence) {
    const waited = session.stopReceivedAt ? Date.now() - session.stopReceivedAt : 0
    if (waited < LATE_CHUNK_GRACE_MS) {
      console.log('[Audio WS] Waiting for remaining chunks', {
        connectionId,
        lastReceived: session.lastSequence,
        expected: session.expectedLastSequence,
        waited
      })
      scheduleFinalize(connectionId, ws, STT_DRAIN_MS)
      return
    }
    console.warn('[Audio WS] Expected more chunks but timeout reached', {
      connectionId,
      lastReceived: session.lastSequence,
      expected: session.expectedLastSequence
    })
  }

  session.finalizing = true
  await finalizeRecording(connectionId, ws)
}

async function finalizeRecording(connectionId, ws) {
  const session = sessions.get(connectionId)
  if (!session) {
    console.log('[Audio WS] finalizeRecording called with no session for:', connectionId)
    return
  }
  sessions.delete(connectionId)

  if (!session.chunks.length) {
    console.log('[Audio WS] No audio data received, chunks:', session?.chunks?.length || 0)
    safeSend(ws, { type: 'transcription', status: 204, code: 'NO_AUDIO', message: 'No audio data received' })
    return
  }

  const chunkCount = session.chunks.length
  console.log('[Audio WS] Session has', chunkCount, 'chunks, total bytes:', session.bytes)
  console.info('[Audio WS] flush_summary', {
    connectionId,
    chunkCount,
    bytes: session.bytes,
    lastSequence: session.lastSequence,
    expectedLastSequence: session.expectedLastSequence,
    contiguous: typeof session.expectedLastSequence === 'number'
      ? session.lastSequence === session.expectedLastSequence
      : true
  })
  if (session.chunks.length < STT_MIN_CHUNKS) {
    console.warn('[Audio WS] Audio chunk count below recommended threshold', {
      connectionId,
      chunkCount: session.chunks.length,
      minChunks: STT_MIN_CHUNKS
    })
  }
  if (typeof session.expectedLastSequence === 'number' && typeof session.lastSequence === 'number' &&
    session.lastSequence !== session.expectedLastSequence) {
    console.warn('[Audio WS] Sequence mismatch at finalize', {
      connectionId,
      lastReceived: session.lastSequence,
      expected: session.expectedLastSequence
    })
  }

  const apiKey = getSttApiKey()
  if (!apiKey) {
    console.log('[Audio WS] No OpenAI API key found')
    safeSend(ws, { type: 'transcription', status: 501, code: 'NOT_CONFIGURED', message: 'STT not configured' })
    return
  }

  const audioBuffer = Buffer.concat(session.chunks)
  console.log('[Audio WS] Calling Whisper API with', audioBuffer.length, 'bytes of audio...')
  if (STT_SAVE_DEBUG) {
    await saveDebugAudio(audioBuffer)
  }

  try {
    const text = await transcribeWithWhisper(audioBuffer, apiKey)
    console.log('[Audio WS] Transcription successful:', text)
    safeSend(ws, {
      type: 'transcription',
      text: text || '',
      duration_ms: Date.now() - session.startedAt
    })
  } catch (err) {
    console.error('[Audio WS] Whisper transcription failed:', err)
    safeSend(ws, {
      type: 'transcription',
      status: 502,
      code: err?.code || 'STT_ERROR',
      message: err?.message || 'Failed to transcribe audio'
    })
  }
}

function cleanupSession(connectionId) {
  const session = sessions.get(connectionId)
  if (session?.finalizeTimer) {
    clearTimeout(session.finalizeTimer)
  }
  sessions.delete(connectionId)
}

async function saveDebugAudio(buffer) {
  // Gateway must not write files (Golden Drive contract).
  // This function is now a no-op. STT_SAVE_DEBUG is always false.
  // If debug audio is needed, route through backend /api/local/voice/save-debug endpoint.
  console.log('[Audio WS] saveDebugAudio called but disabled (gateway cannot write files)')
}

function safeSend(ws, payload) {
  try {
    const OPEN_STATE = typeof ws.OPEN === 'number' ? ws.OPEN : 1
    if (ws.readyState === OPEN_STATE) {
      ws.send(JSON.stringify(payload))
    }
  } catch (err) {
    console.error('Failed to send WS payload', err)
  }
}

function getSttApiKey() {
  // Prefer Supabase service role key (routes through Edge Function)
  // Fallback to direct OpenAI key for local development
  return process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.WHISPER_API_KEY || process.env.OPENAI_API_KEY || ''
}

async function transcribeWithWhisper(audioBuffer, apiKey) {
  const formData = new FormData()

  // Frontend sends WebM audio chunks - Whisper API supports webm format
  const blob = new Blob([audioBuffer], { type: 'audio/webm' })
  formData.append('file', blob, 'audio.webm')
  formData.append('model', WHISPER_MODEL)
  formData.append('language', 'en')

  // Route through Supabase Edge Function if configured, otherwise direct OpenAI
  const forceDirect = ['1', 'true', 'yes', 'on'].includes(String(process.env.STT_FORCE_DIRECT || '').trim().toLowerCase())
  const useSupabase = !forceDirect && !!(process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY)

  const url = useSupabase
    ? `${process.env.SUPABASE_URL}/functions/v1/openai-proxy`
    : WHISPER_API_URL

  console.log('[Audio WS] Sending to Whisper:', {
    bufferSize: audioBuffer.length,
    blobType: blob.type,
    fileName: 'audio.webm',
    routeVia: useSupabase ? 'Supabase openai-proxy' : 'Direct OpenAI',
    url
  })

  // For Supabase proxy, we need to send JSON with the audio as base64
  // For direct OpenAI, we send multipart/form-data
  let res
  if (useSupabase) {
    // Convert audio to base64 for JSON transport
    const base64Audio = audioBuffer.toString('base64')
    res = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        endpoint: '/v1/audio/transcriptions',
        file: base64Audio,
        filename: 'audio.webm',
        model: WHISPER_MODEL,
        language: 'en'
      })
    })
  } else {
    res = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`
      },
      body: formData
    })
  }

  if (!res.ok) {
    const errText = await safeText(res)
    console.error('[Audio WS] Whisper API error:', {
      status: res.status,
      statusText: res.statusText,
      error: errText
    })
    const error = new Error(`Whisper ${res.status}: ${errText || 'Unknown error'}`)
    error.code = res.status === 401 ? 'NOT_AUTHORIZED' : 'STT_ERROR'
    throw error
  }

  const data = await res.json()
  return data?.text?.trim() || ''
}


async function safeText(res) {
  try {
    return await res.text()
  } catch {
    return ''
  }
}
