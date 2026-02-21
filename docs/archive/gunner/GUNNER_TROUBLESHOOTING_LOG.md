# Gunner Voice Troubleshooting Log
**Session Date:** 2025-11-26  
**Goal:** Fix Gunner voice commands and TTS responses

---

## Issues Reported
1. **Voice commands not triggering actions** - User says "start calibration" but nothing happens
2. **Cannot hear Gunner's voice** - TTS not playing for command responses
3. **Doc voice transcription also broken** - Similar WebSocket issues

---

## Attempts Made

### 1. ✅ **Initial Diagnosis - Stale Closure in WebSocket**
**Problem:** WebSocket created with empty deps, always used initial version of `handleVoiceCommand`  
**Solution:** Added ref pattern to access latest function  
**Result:** SUCCESS - Fixed function reference issue  
**Files:** `frontend/src/panels/lightguns/LightGunsPanel.jsx`

### 2. ✅ **Added GUNNER_VOICE_ID to Environment**
**Problem:** No voice profile configured for Gunner  
**Solution:** Added `GUNNER_VOICE_ID=5Q0t7uMcjvnagumLfvZi` (Chuck's voice) to `.env`  
**Result:** SUCCESS - TTS now works for Voice Assist toggle  
**Files:** `.env`

### 3. ✅ **Gateway Restart to Load Environment**
**Problem:** Gateway had stale environment variables  
**Solution:** Restarted gateway with `npm start`  
**Result:** SUCCESS - GUNNER_VOICE_ID loaded  

### 4. ✅ **Frontend Rebuild**
**Problem:** Gateway serving old cached build without fixes  
**Solution:** Ran `npm run build:frontend`  
**Result:** SUCCESS - New code deployed  

### 5. ✅ **Access via Gateway Instead of Vite**
**Problem:** Vite dev server at localhost:5173 had proxy issues  
**Solution:** Switched to `http://localhost:8787` (gateway direct)  
**Result:** SUCCESS - WebSocket connects properly  

### 6. ✅ **Added Visual Feedback for Voice Commands**
**Problem:** User couldn't see what was transcribed  
**Solution:** Changed chat message to show `🎤 Heard: "transcript"`  
**Result:** SUCCESS - Better debugging visibility  
**Files:** `frontend/src/panels/lightguns/LightGunsPanel.jsx`

### 7. ✅ **Added Debug Logging to Voice Commands**
**Problem:** Couldn't trace command execution  
**Solution:** Added extensive console.log statements  
**Result:** SUCCESS - Can now see command matching  
**Files:** `frontend/src/panels/lightguns/LightGunsPanel.jsx`

### 8. ⚠️ **Fixed voiceAssistEnabled Stale Closure**
**Problem:** WebSocket checked `voiceAssistEnabled` directly (stale value)  
**Solution:** Added `voiceAssistEnabledRef` and updated it via useEffect  
**Result:** PENDING TEST - Just implemented, needs verification  
**Files:** `frontend/src/panels/lightguns/LightGunsPanel.jsx`

---

## Current Status

### ✅ What's Working
1. **WebSocket Connection** - Successfully connects to `ws://localhost:8787/ws/audio`
2. **Audio Recording** - Microphone captures audio chunks
3. **Transcription** - Backend transcribes speech (tested with Korean and English)
4. **Voice Assist Toggle** - Can turn on/off, hear TTS confirmation
5. **TTS System** - Gunner speaks when toggling Voice Assist
6. **Voice Profile** - GUNNER_VOICE_ID configured and working

### ❌ What's NOT Working
1. **Voice Commands Not Executing** - Commands don't trigger actions (handleStartCalib, etc.)
2. **No Command Debug Logs** - `[Gunner Voice]` logs never appear when speaking
3. **TTS Not Playing for Commands** - Only hear TTS when toggling Voice Assist

### 🔍 Root Cause Analysis
**Primary Issue:** Stale closure in WebSocket `onmessage` handler

The WebSocket is created once with empty dependencies:
```javascript
useEffect(() => {
  const ws = new WebSocket(...)
  ws.onmessage = (ev) => {
    if (voiceAssistEnabled) { // ← STALE VALUE!
      handleVoiceCommand(msg.text) // ← STALE FUNCTION!
    }
  }
}, []) // ← Empty deps = never updates
```

**Fixes Applied:**
1. ✅ Use `handleVoiceCommandRef.current` instead of direct function call
2. ✅ Use `voiceAssistEnabledRef.current` instead of direct boolean check
3. ✅ Update refs via useEffect when values change

---

## Next Steps

### Immediate Testing Required
1. Rebuild frontend: `npm run build:frontend` ✅ DONE
2. Hard refresh browser at `http://localhost:8787`
3. Turn Voice Assist ON
4. Say "start calibration"
5. Check console for new debug logs:
   - `[Gunner] voiceAssistEnabledRef.current: true`
   - `[Gunner] ✅ Voice Assist is ON - routing to command handler`
   - `[Gunner Voice] ===== VOICE COMMAND DEBUG =====`

### If Still Not Working
1. **Check if refs are being set** - Add logs in useEffect that updates refs
2. **Verify WebSocket receives transcriptions** - Already confirmed working
3. **Test with simple command** - Try "help" which just speaks, no state changes
4. **Consider race condition** - Ref might not be set when WebSocket connects

### Alternative Approaches
1. **Recreate WebSocket when voiceAssistEnabled changes** - Add to deps array
2. **Use event emitter pattern** - Decouple WebSocket from React state
3. **Move voice logic to custom hook** - Better separation of concerns

---

## Files Modified

### Core Fixes
- `frontend/src/panels/lightguns/LightGunsPanel.jsx` - Stale closure fixes, debug logging
- `.env` - Added GUNNER_VOICE_ID

### Documentation
- `GUNNER_VOICE_AUDIT.md` - Technical audit of voice system
- `GUNNER_VOICE_FIX_SUMMARY.md` - Fix documentation
- `GUNNER_SESSION_SUMMARY.md` - Session progress summary
- `GUNNER_TROUBLESHOOTING_LOG.md` - This file

---

## Key Learnings

1. **WebSocket closures are tricky** - Empty deps means stale values forever
2. **Refs solve closure issues** - But must be updated via useEffect
3. **Frontend builds are cached** - Always rebuild after code changes
4. **Vite proxy can be problematic** - Direct gateway access more reliable
5. **Debug logging is essential** - Can't fix what you can't see

---

## Success Criteria

Voice commands will be considered working when:
- ✅ User says "start calibration"
- ✅ Console shows `[Gunner Voice] ✅ MATCHED: Start calibration`
- ✅ Calibration wizard starts
- ✅ Gunner speaks: "Starting calibration. Aim at the top-left corner..."
- ✅ Continuous listening resumes after command
