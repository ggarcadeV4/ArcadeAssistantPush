# CODEX: Direct Instructions for Voice Transcription Fix

## Execute These Steps in Order

### Step 1: Check if start_recording/stop_recording messages are being sent

**File**: `frontend/src/panels/launchbox/LaunchBoxPanel.jsx`

**Line 399**: Verify `startRecording` function is sending the message correctly
**Line 429**: Verify `stopRecording` function is sending the message correctly

**Expected browser console output**:
- `[LaunchBox Voice] Sending message: start_recording`
- `[LaunchBox Voice] Sending message: audio_chunk` (multiple)
- `[LaunchBox Voice] Sending message: stop_recording`

**If missing**: The frontend is not sending start/stop messages. Check MediaRecorder setup.

### Step 2: Add logging to verify session is created

**File**: `gateway/ws/audio.js`

**Line 84-92**: Add this log to `startRecording` function:
```javascript
function startRecording(connectionId, ws) {
  console.log('[Audio WS] 🟢 CREATE SESSION for:', connectionId)  // ADD THIS
  sessions.set(connectionId, {
    chunks: [],
    bytes: 0,
    startedAt: Date.now(),
    recording: true
  })
  console.log('[Audio WS] 🟢 SESSION CREATED, active sessions:', sessions.size)  // ADD THIS
  safeSend(ws, { type: 'recording_started', timestamp: Date.now() })
}
```

**Line 94-109**: Add this log to `appendChunk` function:
```javascript
function appendChunk(connectionId, chunk, ws) {
  const session = sessions.get(connectionId)
  console.log('[Audio WS] 📦 appendChunk called, session exists:', !!session, 'recording:', session?.recording)  // ADD THIS
  if (!session || !session.recording || !Buffer.isBuffer(chunk)) return

  session.chunks.push(chunk)
  session.bytes += chunk.length
  console.log('[Audio WS] 📦 Chunk added, total chunks:', session.chunks.length, 'total bytes:', session.bytes)  // ADD THIS

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
}
```

### Step 3: Check if OPENAI_API_KEY is set

**File**: `.env`

Verify this line exists and has a valid key:
```
OPENAI_API_KEY=sk-...
```

If missing, transcription will fail with "STT not configured" error.

### Step 4: Test the full flow

1. Kill existing node processes: `taskkill.exe //F //IM node.exe`
2. Rebuild frontend: `npm run build:frontend`
3. Start servers: `start-gui.bat`
4. Open browser: `http://localhost:8787`
5. Navigate to LaunchBox panel
6. Click microphone and speak
7. Watch **Gateway Server** terminal for these logs in order:

**Expected log sequence**:
```
[Audio WS] ⚡ MESSAGE RECEIVED - isBinary: false type: object length: 26
[Audio WS] Payload preview: {"type":"start_recording"}
[Audio WS] Successfully parsed JSON, type: start_recording
[Audio WS] Received message type: start_recording
[Audio WS] Starting recording for connection: [id]
[Audio WS] 🟢 CREATE SESSION for: [id]
[Audio WS] 🟢 SESSION CREATED, active sessions: 1

[Audio WS] ⚡ MESSAGE RECEIVED - isBinary: false type: object length: 5640
[Audio WS] Payload preview: {"type":"audio_chunk","chunk":"Q8OBA...
[Audio WS] Successfully parsed JSON, type: audio_chunk
[Audio WS] Received message type: audio_chunk
[Audio WS] 📦 appendChunk called, session exists: true, recording: true
[Audio WS] 📦 Chunk added, total chunks: 1, total bytes: 4096

... (more chunks) ...

[Audio WS] ⚡ MESSAGE RECEIVED - isBinary: false type: object length: 25
[Audio WS] Payload preview: {"type":"stop_recording"}
[Audio WS] Successfully parsed JSON, type: stop_recording
[Audio WS] Received message type: stop_recording
[Audio WS] Stopping recording for connection: [id]
[Audio WS] Stop recording called for connection: [id]
[Audio WS] Session has 24 chunks, total bytes: 98304
[Audio WS] Calling Whisper API with 98304 bytes of audio...
[Audio WS] Transcription successful: [transcribed text]
```

### Step 5: Identify where the chain breaks

**If you see 🟢 SESSION CREATED but no 📦 appendChunk logs**:
- Problem: `audio_chunk` messages not calling `appendChunk`
- Fix: Check line 69-73 in `audio.js`, verify `data.chunk` or `data.data` exists

**If you see 📦 appendChunk logs but session.chunks.length is 0**:
- Problem: Chunks not being added to array
- Fix: Check if `Buffer.from(encoded, 'base64')` is working (line 72)

**If you see "No audio data received"**:
- Problem: Session was deleted or never created before `stop_recording`
- Fix: Check timing - session might timeout, or `start_recording` never called

**If you see "STT not configured"**:
- Problem: No OpenAI API key
- Fix: Set `OPENAI_API_KEY` in `.env`

**If you see Whisper API error**:
- Problem: API call failed
- Fix: Check error message - might be invalid audio format, rate limit, or bad key

**If transcription succeeds but doesn't appear in UI**:
- Problem: Frontend not handling the response
- Fix: Check `LaunchBoxPanel.jsx` line 460-478, verify `processVoiceCommand` is called

### Step 6: Most Likely Fix Needed

Based on the current logs showing only `audio_chunk` messages, the issue is probably:

**Frontend is not sending `start_recording` message**

**Check**: `frontend/src/panels/launchbox/LaunchBoxPanel.jsx` line 399-427

Look for this pattern:
```javascript
const startRecording = useCallback(() => {
  console.log('[LaunchBox Voice] Starting recording...')

  // THIS LINE MUST BE HERE AND MUST RUN BEFORE MediaRecorder.start()
  if (!sendVoiceMessage({ type: 'start_recording' })) {
    console.error('[LaunchBox Voice] Failed to send start_recording message')
    return
  }

  setIsRecording(true)
  // ... MediaRecorder setup
}, [sendVoiceMessage])
```

**If `start_recording` is not being sent**: The session is never created, so `appendChunk` fails silently because `session` is undefined.

**Fix**: Ensure `sendVoiceMessage({ type: 'start_recording' })` is called BEFORE `MediaRecorder.start()`

### Step 7: Quick Validation

After adding the logging from Step 2, restart the gateway and test ONE recording. Then paste the FULL Gateway Server terminal output here. I'll tell you exactly which line is failing.

## Summary: What to Look For

1. ✅ Browser sends: `start_recording` → `audio_chunk` (x many) → `stop_recording`
2. ✅ Server creates session on `start_recording`
3. ✅ Server adds chunks to session on `audio_chunk`
4. ✅ Server finds session with chunks on `stop_recording`
5. ✅ Server calls Whisper API
6. ✅ Server gets transcription text
7. ✅ Server sends transcription to frontend
8. ✅ Frontend receives and displays transcription

**Current status**: We confirmed #1 has `audio_chunk` messages, but we haven't seen logs for `start_recording` or `stop_recording`. This suggests the frontend is only sending chunks without the start/stop bookends, which means the session is never created, which means chunks are silently ignored.

**Most likely one-line fix**: Add `sendVoiceMessage({ type: 'start_recording' })` at the start of the `startRecording` callback in LaunchBoxPanel.jsx line 399.
