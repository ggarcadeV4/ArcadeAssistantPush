# ScoreKeeper Sam - Mic Button Debug Session
**Date:** 2025-12-05
**Issue:** Windows "ding" error sound when using microphone in ScoreKeeper Sam panel

---

## Problem Description
When clicking the microphone button in ScoreKeeper Sam's chat panel, a Windows error "ding" sound plays. The sound is audible (not visual) and comes from the Windows system sounds.

---

## Initial State (Before Debugging)
The debug summary from previous sessions indicated:
- Ding is an error sound (Windows "invalid operation" sound)
- Ding happens when mic functionality is active
- Ding is inside `beginRecording()` or `endRecording()`, not from button click itself
- Previous fixes applied:
  - `type="button"` on mic button (prevents form submission)
  - `type="button"` on EXECUTE button
  - `wsUnmountedRef` to prevent WebSocket reconnect after unmount
  - `isRealUnmountRef` to prevent StrictMode from killing mic stream

---

## Diagnostic Approach

### Phase 1: Add Granular Debug Logging
Added numbered DEBUG statements throughout `beginRecording()` and `endRecording()` to pinpoint exact location of ding:

**beginRecording debug sequence:**
- `[DEBUG 1]` - START
- `[DEBUG 2]` - About to call stopSpeaking()
- `[DEBUG 3]` - After stopSpeaking()
- `[DEBUG 4]` - Browser checks passed
- `[DEBUG 5]` - Checking stream validity
- `[DEBUG 6/6b]` - Before getUserMedia / reusing stream
- `[DEBUG 7]` - After getUserMedia
- `[DEBUG 8-10]` - Creating MediaRecorder
- `[DEBUG 11-14]` - WebSocket send
- `[DEBUG 15-17]` - recorder.start() and completion

**endRecording debug sequence:**
- `[DEBUG END-1]` through `[DEBUG END-14]`

### Phase 2: Isolation Testing
Tested each component individually by creating a test version of `toggleMic`:

| Component Tested | Ding? | Result |
|-----------------|-------|--------|
| Button click only (no action) | NO | Button is not the cause |
| `stopSpeaking()` | NO | TTS stopping is not the cause |
| `getUserMedia()` | NO | Mic access is not the cause |
| `getUserMedia()` + `MediaRecorder` creation | NO | Recorder creation is not the cause |
| Above + WebSocket send | NO | WS send alone is not the cause |
| Above + `recorder.start(250)` | NO | Starting recorder alone is not the cause |
| Above + React state updates | NO | State updates are not the cause |
| Full `beginRecording()` | YES | Something in the combination causes it |

### Phase 3: Narrowing Down
User clarified: **Ding happens on SECOND click** (when trying to record again), not on first click.

This pointed to **stream reuse logic**. The original code tried to reuse an existing microphone stream:
```javascript
if (!stream || !stream.active || ...) {
  stream = await getUserMedia()  // Get new
} else {
  // Reuse existing
}
```

### Phase 4: Further Isolation
User clarified: **Ding happens DURING recording**, not just on click.

This pointed to the `ondataavailable` callback that sends audio chunks.

| Test | Ding? | Result |
|------|-------|--------|
| Disable chunk sending entirely | NO | **Chunk sending causes the ding** |
| Enable with `setTimeout(..., 0)` wrapper | YES | Decoupling doesn't help |
| Convert Blob to ArrayBuffer before send | ? | Not conclusively tested |

---

## User Error Discovered
During debugging, user realized they were running a **different .bat file** for development, not the main `npm run dev` stack.

When accessing the correct `localhost:8787`:
- Gateway was not running (`ERR_CONNECTION_REFUSED`)
- WebSocket connections failed
- Microphone didn't work at all

After starting `npm run dev`:
- Gateway started on port 8787
- Backend started on port 8888
- Chat returned "Failed to fetch" error (separate issue - likely API key)
- Microphone testing needs to be re-done on correct setup

---

## Code Changes Made

### 1. Safer `stopSpeaking()` in ttsClient.js
```javascript
// Before: Could throw errors
export function stopSpeaking() {
  if (currentAudio) {
    currentAudio.pause()
    currentAudio.currentTime = 0
    currentAudio = null
  }
}

// After: Wrapped in try-catch with state checks
export function stopSpeaking() {
  if (currentAudio) {
    try {
      const audio = currentAudio
      currentAudio = null
      if (audio.readyState > 0) {
        audio.pause()
        if (audio.currentTime > 0) {
          audio.currentTime = 0
        }
      }
    } catch (err) {
      console.warn('[TTS] Error while stopping audio (non-fatal):', err)
      currentAudio = null
    }
  }
}
```

### 2. Disabled Stream Reuse in beginRecording()
```javascript
// Before: Tried to reuse existing stream
let stream = mediaStreamRef.current
if (!stream || !stream.active || ...) {
  stream = await getUserMedia()
} else {
  // Reuse
}

// After: Always get fresh stream
if (mediaStreamRef.current) {
  mediaStreamRef.current.getTracks().forEach(t => t.stop())
  mediaStreamRef.current = null
}
const stream = await getUserMedia()
```

### 3. Audio Chunk Handling Change
```javascript
// Current state: Converting Blob to ArrayBuffer before sending
recorder.ondataavailable = async (event) => {
  if (!event.data || event.data.size === 0) return
  const seq = chunkSequenceRef.current
  chunkSequenceRef.current += 1
  try {
    const arrayBuffer = await event.data.arrayBuffer()
    emitAudioChunk(arrayBuffer, seq)
  } catch (err) {
    console.error('[Sam Voice] Failed to process audio chunk:', err)
  }
}
```

### 4. Debug Logging (Still Present)
Extensive DEBUG logging remains in `beginRecording()` and `endRecording()` for further diagnosis.

---

## Architecture Reference

```
Frontend (React)     Gateway (Node.js)     Backend (Python)
localhost:5173  -->  localhost:8787   -->  localhost:8888
     |                    |
     |                    +-- /ws/audio (WebSocket for voice)
     |                    +-- /api/ai/chat (AI endpoints)
     |                    +-- /api/voice/tts (Text-to-speech)
     |
     +-- ScoreKeeperPanel.jsx (mic button, recording logic)
```

**Audio Flow:**
1. User clicks mic button
2. `beginRecording()` calls `getUserMedia()` for mic access
3. `MediaRecorder` captures audio in 250ms chunks
4. `ondataavailable` callback sends chunks to WebSocket
5. Gateway (`gateway/ws/audio.js`) buffers chunks
6. On stop, gateway sends to Whisper API for transcription
7. Transcription returned to frontend via WebSocket

---

## Known Issues (Separate from Ding)

1. **Chat "Failed to fetch" error** - AI chat endpoint not working (likely missing API key)
2. **Whisper hallucination** - Transcribes "goodbye" on silence
3. **React key warnings** - Duplicate keys in chat messages (timestamp collision)
4. **Hotkey WebSocket failing** - `/ws/hotkey` connection refused

---

## Next Steps

1. **Re-test microphone on correct setup** (localhost:8787 with gateway running)
2. **Verify if ding still occurs** on production setup
3. **If ding persists**, investigate:
   - Gateway-side audio handling (`gateway/ws/audio.js`)
   - Whether ding comes from server, not browser
   - Windows audio driver interaction
4. **Clean up debug logging** once issue is resolved
5. **Fix chat "Failed to fetch"** - check API keys in `.env`

---

## Files Modified

| File | Changes |
|------|---------|
| `frontend/src/panels/scorekeeper/ScoreKeeperPanel.jsx` | Debug logging, stream reuse fix, chunk handling |
| `frontend/src/services/ttsClient.js` | Safer `stopSpeaking()` function |

---

## How to Test

1. Start dev stack: `npm run dev`
2. Wait for "Gateway listening on port 8787" and "Application startup complete"
3. Open `http://localhost:8787` (NOT localhost:5173)
4. Navigate to ScoreKeeper Sam panel
5. Open browser DevTools (F12) > Console
6. Click mic button
7. Observe:
   - Do DEBUG messages appear?
   - Does WebSocket connect? (`[Sam Voice] WebSocket connected`)
   - Does ding occur?
   - When does ding occur? (on click, during recording, on stop)

---

## Session Notes

- User was initially testing on wrong dev server setup
- The ding may have been from a completely different application/setup
- Need to re-verify issue exists on correct localhost:8787 setup
- Debugging methodology was sound but applied to wrong target
