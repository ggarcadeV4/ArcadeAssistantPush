# SoundBug: ScoreKeeper Sam Mic Button Debug Session
**Date:** 2025-12-05 (Evening Session)
**Developer:** Claude Code (Opus 4.5)
**Issue:** Windows "ding" error sound when using microphone button

---

## The Bug Report

User reported an annoying Windows error "ding" sound that plays when clicking the microphone button in ScoreKeeper Sam's chat panel. The sound is:
- Audible (not visual)
- A Windows system sound (like "invalid operation")
- Happening somewhere in the recording process

### Previous Debug Work (Before This Session)
Prior sessions had already determined:
- Ding is inside `beginRecording()` or `endRecording()`, not from button click
- Added `type="button"` to mic and EXECUTE buttons
- Added `wsUnmountedRef` to prevent WebSocket reconnect after unmount
- Added `isRealUnmountRef` to prevent StrictMode from killing mic stream
- Added `e.preventDefault()` and `e.stopPropagation()` to toggleMic

---

## Session Timeline

### Step 1: Read Current Code State
Read `ScoreKeeperPanel.jsx` to understand the current mic implementation:
- `beginRecording()` - starts mic, creates MediaRecorder, sends to WebSocket
- `endRecording()` - stops recorder, sends stop signal, waits for transcription
- `toggleMic()` - switches between start/stop based on `isRecording` state

### Step 2: Add Granular Debug Logging
Added numbered DEBUG statements to pinpoint exact location:

```javascript
// In beginRecording():
console.log('[DEBUG 1] beginRecording: START')
console.log('[DEBUG 2] About to call stopSpeaking()')
// ... stopSpeaking() ...
console.log('[DEBUG 3] After stopSpeaking()')
console.log('[DEBUG 4] Browser checks passed')
console.log('[DEBUG 5] Checking stream validity')
console.log('[DEBUG 6] Need new stream - about to call getUserMedia')
console.log('[DEBUG 7] getUserMedia returned')
console.log('[DEBUG 8] About to pick recorder options')
console.log('[DEBUG 9] About to create MediaRecorder')
console.log('[DEBUG 10] MediaRecorder created')
console.log('[DEBUG 11] About to check WebSocket')
console.log('[DEBUG 12] WebSocket state:', ws?.readyState)
console.log('[DEBUG 13] About to send start_recording to WebSocket')
console.log('[DEBUG 14] WebSocket send completed')
console.log('[DEBUG 15] About to call recorder.start(250)')
console.log('[DEBUG 16] recorder.start() completed')
console.log('[DEBUG 17] beginRecording COMPLETE')

// In endRecording():
console.log('[DEBUG END-1]') through console.log('[DEBUG END-14]')
```

### Step 3: Make stopSpeaking() Safer
Modified `frontend/src/services/ttsClient.js` to wrap in try-catch:

```javascript
// BEFORE:
export function stopSpeaking() {
  if (currentAudio) {
    currentAudio.pause()
    currentAudio.currentTime = 0
    currentAudio = null
  }
}

// AFTER:
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

### Step 4: User Reports Ding Still Happening
User confirmed ding happens "immediately" when clicking mic.
Asked user which DEBUG number appears before ding.

### Step 5: Test stopSpeaking() in Isolation
Commented out `stopSpeaking()` call in beginRecording:
```javascript
// stopSpeaking()  // TEMPORARILY DISABLED
```
**Result:** User says ding STILL happens. stopSpeaking is NOT the cause.

### Step 6: Test Button Click Only
Made toggleMic do nothing but log and return:
```javascript
const toggleMic = useCallback((e) => {
  console.log('[DEBUG 0] toggleMic ENTRY')
  e?.preventDefault?.()
  e?.stopPropagation?.()
  console.log('[DEBUG 0.6] TESTING: Returning early')
  return  // <-- EARLY RETURN - do nothing
  // ... rest of code never runs
})
```
**Result:** NO DING. Button click itself is not the cause.

### Step 7: Test getUserMedia Only
```javascript
const toggleMic = useCallback(async (e) => {
  e?.preventDefault?.()
  e?.stopPropagation?.()

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  stream.getTracks().forEach(t => t.stop())
  return
})
```
**Result:** NO DING. getUserMedia is not the cause.

### Step 8: Test getUserMedia + MediaRecorder
```javascript
const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
const options = pickRecorderOptions()
const recorder = new MediaRecorder(stream, options)
stream.getTracks().forEach(t => t.stop())
return
```
**Result:** NO DING. MediaRecorder creation is not the cause.

### Step 9: Test + WebSocket Send
```javascript
// ... getUserMedia + MediaRecorder ...
const ws = voiceWsRef.current
if (ws && ws.readyState === 1) {
  ws.send(JSON.stringify({ type: 'start_recording' }))
}
// cleanup and return
```
**Result:** NO DING. WebSocket send is not the cause.

### Step 10: Test + recorder.start()
```javascript
// ... all above ...
recorder.start(250)
setTimeout(() => {
  recorder.stop()
  stream.getTracks().forEach(t => t.stop())
}, 500)
return
```
**Result:** NO DING. recorder.start() is not the cause.

### Step 11: Test + React State Updates
```javascript
// ... all above ...
setIsRecording(true)
setIsTranscribing(false)
// cleanup
```
**Result:** NO DING. State updates are not the cause.

### Step 12: User Clarifies Timing
User said: "It's with the microphone. It's after I give permission to the microphone. Hit the microphone again, it starts."

**Key insight:** Ding happens on SECOND click, not first!

This suggested the **stream reuse logic** was the problem.

### Step 13: Disable Stream Reuse
Changed from reusing existing stream to always getting fresh:

```javascript
// BEFORE: Tried to reuse
let stream = mediaStreamRef.current
if (!stream || !stream.active || ...) {
  stream = await getUserMedia()
} else {
  console.log('Reusing hot stream')
}

// AFTER: Always fresh
if (mediaStreamRef.current) {
  mediaStreamRef.current.getTracks().forEach(t => t.stop())
  mediaStreamRef.current = null
}
const stream = await getUserMedia()
```

### Step 14: User Clarifies Further
User said: "It seems like it's only happening when record is going on."

**Key insight:** Ding happens DURING recording, not on click!

This pointed to the `ondataavailable` callback sending audio chunks.

### Step 15: Disable Chunk Sending
```javascript
recorder.ondataavailable = async (event) => {
  if (!event.data || event.data.size === 0) return
  console.log('[DEBUG CHUNK] Got chunk, size:', event.data.size)
  // DISABLED: emitAudioChunk(...)
}
```
**Result:** NO DING! Chat says "no audio recorded" (expected).

**FOUND IT:** Sending audio chunks causes the ding!

### Step 16: Try setTimeout Wrapper
```javascript
recorder.ondataavailable = async (event) => {
  // ...
  setTimeout(() => {
    emitAudioChunk(chunk, seq)
  }, 0)
}
```
**Result:** DING STILL HAPPENS. Decoupling from audio thread doesn't help.

### Step 17: Try ArrayBuffer Conversion
```javascript
recorder.ondataavailable = async (event) => {
  const arrayBuffer = await event.data.arrayBuffer()
  emitAudioChunk(arrayBuffer, seq)
}
```
User tested but also noticed Whisper transcribed "goodbye" when they said nothing.

### Step 18: THE REVELATION

User asked: "Okay, you're working on Loco Host 8787. Is that correct?"

Then discovered: **They were running a different .bat file** - NOT the main npm run dev stack!

When accessing localhost:8787:
```
GET http://localhost:8787/assets/index-a831f65a.css net::ERR_CONNECTION_REFUSED
WebSocket connection to 'ws://localhost:8787/ws/hotkey' failed
```

**THE GATEWAY WASN'T EVEN RUNNING!**

### Step 19: Start Correct Dev Stack
User ran `npm run dev` which starts:
- Gateway on localhost:8787
- Backend on localhost:8888

### Step 20: Test on Correct Setup
User typed "hello" in chat and got:
```
Chat error: Failed to fetch. Please check console for details.
```
This is a separate issue (likely missing API key).

**Microphone testing on correct setup was NOT completed.**

---

## Summary of Findings

### What We Proved (on the wrong setup):
1. Button click alone - NOT the cause
2. stopSpeaking() - NOT the cause
3. getUserMedia() - NOT the cause
4. MediaRecorder creation - NOT the cause
5. WebSocket send of control message - NOT the cause
6. recorder.start() - NOT the cause
7. React state updates - NOT the cause
8. **Sending audio chunks - CAUSES THE DING** (on wrong setup)

### What We Discovered:
- User was running a different development environment entirely
- The ding may have been specific to that other setup
- We never confirmed the bug exists on the correct localhost:8787 setup

### Code Changes Made (Still in Place):
1. **ttsClient.js**: Safer stopSpeaking() with try-catch
2. **ScoreKeeperPanel.jsx**:
   - Disabled stream reuse (always get fresh stream)
   - ArrayBuffer conversion for chunks
   - Extensive debug logging throughout

---

## Files Modified

| File | Line Count | Changes |
|------|------------|---------|
| `frontend/src/panels/scorekeeper/ScoreKeeperPanel.jsx` | ~2100 lines | Debug logging, stream handling, chunk conversion |
| `frontend/src/services/ttsClient.js` | ~248 lines | Safer stopSpeaking() |

---

## Console Output Examples

### From Wrong Setup (what we were debugging):
```
[DEBUG] Mic button clicked - isRecording: false
[DEBUG 1] beginRecording: START
[DEBUG 2] About to call stopSpeaking()
[DEBUG 3] After stopSpeaking()
[DEBUG 4] Browser checks passed, entering try block
[DEBUG 5] Checking stream validity
[DEBUG 6] Need new stream - about to call getUserMedia
[DEBUG 7] getUserMedia returned
[DEBUG 8] About to pick recorder options
[DEBUG 9] About to create MediaRecorder
[DEBUG 10] MediaRecorder created
[DEBUG 11] About to check WebSocket
[DEBUG 12] WebSocket state: 1 (1 = OPEN)
[DEBUG 13] About to send start_recording to WebSocket
[DEBUG 14] WebSocket send completed
[DEBUG 15] About to call recorder.start(250)
[DEBUG 16] recorder.start() completed
[DEBUG 17] beginRecording COMPLETE - recording active
```

### From Correct Setup (gateway not running):
```
GET http://localhost:8787/assets/index-a831f65a.css net::ERR_CONNECTION_REFUSED
WebSocket connection to 'ws://localhost:8787/ws/hotkey' failed
```

---

## Lessons Learned

1. **Always verify the dev environment first** - We spent hours debugging on wrong setup
2. **Isolation testing is effective** - The binary search approach found the chunk sending
3. **User feedback is valuable** - "It happens on second click" and "during recording" were key insights
4. **Document everything** - This session log captures the full context

---

## Next Steps (For Future Session)

1. [ ] Ensure `npm run dev` is running (gateway + backend)
2. [ ] Access `http://localhost:8787` (NOT localhost:5173)
3. [ ] Test microphone on correct setup
4. [ ] Determine if ding bug exists there too
5. [ ] If yes, the chunk sending fix should help
6. [ ] If no, clean up debug code and close issue
7. [ ] Fix "Chat error: Failed to fetch" (check API keys)
8. [ ] Address Whisper hallucination on silence

---

## How to Reproduce Testing

```bash
# 1. Start the dev stack
cd "/mnt/a/Arcade Assistant Local"
npm run dev

# 2. Wait for these messages:
#    - "Gateway listening on port 8787"
#    - "Application startup complete"

# 3. Open browser to http://localhost:8787
# 4. Navigate to Assistants > ScoreKeeper Sam
# 5. Open DevTools (F12) > Console
# 6. Click mic button
# 7. Observe console for DEBUG messages
# 8. Listen for Windows ding sound
```

---

## Technical Architecture Reference

```
User clicks mic
       |
       v
toggleMic()
       |
       v
beginRecording()
       |
       +-- stopSpeaking() -----> Stops any TTS audio
       |
       +-- getUserMedia() -----> Gets microphone access
       |
       +-- new MediaRecorder() -> Creates recorder
       |
       +-- ws.send(start) -----> Tells gateway to start session
       |
       +-- recorder.start(250) -> Starts capturing audio
       |
       v
[Every 250ms]
ondataavailable fires
       |
       +-- event.data.arrayBuffer() -> Convert blob
       |
       +-- emitAudioChunk() ---------> Send to WebSocket  <-- DING SOURCE?
       |
       v
Gateway receives chunks (gateway/ws/audio.js)
       |
       +-- appendChunk() -> Buffers audio
       |
       v
[User clicks stop]
       |
       v
endRecording()
       |
       +-- recorder.stop()
       +-- ws.send(stop_recording)
       |
       v
Gateway finalizes
       |
       +-- transcribeWithWhisper() -> Send to OpenAI
       |
       v
Transcription returned via WebSocket
       |
       v
handleSendMessage(transcribedText)
```

---

*End of Session Log*
