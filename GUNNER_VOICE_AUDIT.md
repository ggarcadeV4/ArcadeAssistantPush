# Gunner Voice Functionality Audit

**Panel:** LightGunsPanel (Gunner)  
**File:** `frontend/src/panels/lightguns/LightGunsPanel.jsx`  
**Date:** 2025-11-26

## Overview
Gunner has two voice modes:
1. **Voice Assist Mode** - Continuous listening for calibration commands
2. **Chat Mic Mode** - One-shot voice messages to AI chat

## Current Issues

### 1. Voice Commands Not Triggering Actions
**Symptoms:**
- User says "start calibration" but nothing happens
- Commands logged to console but not executing
- Loose pattern matching added but still failing

**Root Cause:**
- `handleVoiceCommand` function is defined AFTER the WebSocket `useEffect` that references it
- This creates a stale closure where the WebSocket always uses the initial version of `handleVoiceCommand`
- When the function updates (due to dependency changes), the WebSocket doesn't see the new version

**Evidence:**
```javascript
// Line ~1050: handleVoiceCommand defined
const handleVoiceCommand = useCallback((transcript) => {
  // ... command logic
}, [voiceAssistEnabled, calibrationResult, handleStartCalib, ...])

// Line ~1070: WebSocket useEffect references handleVoiceCommand
useEffect(() => {
  const ws = new WebSocket(...)
  ws.onmessage = (ev) => {
    if (voiceAssistEnabled) {
      handleVoiceCommand(msg.text)  // ← Uses stale closure!
    }
  }
}, []) // ← Empty deps means it never updates!
```

### 2. Feedback Loop Prevention
**Status:** ✅ FIXED (500ms delay added)
- Added 500ms delay before starting recording to prevent TTS pickup
- Working as intended

### 3. Voice Assist Auto-Resume Logic
**Status:** ⚠️ COMPLEX
- Uses global flag `window.__gunnerResumeVoiceAssist` to track state
- Inline recording restart code duplicates `beginRecording` logic
- Could be simplified

### 4. WebSocket Connection Timing
**Status:** ✅ WORKING
- Correctly detects Vite dev mode (ports 5173-5179)
- Routes to gateway at 8787
- Connection established successfully

## Recommended Fixes

### Priority 1: Fix Stale Closure (CRITICAL)
**Problem:** WebSocket doesn't see updated `handleVoiceCommand`

**Solution A - Add handleVoiceCommand to deps:**
```javascript
useEffect(() => {
  const ws = new WebSocket(...)
  ws.onmessage = (ev) => {
    if (voiceAssistEnabled) {
      handleVoiceCommand(msg.text)
    }
  }
  return () => ws.close()
}, [handleVoiceCommand, voiceAssistEnabled]) // ← Add deps
```
**Downside:** WebSocket reconnects on every state change

**Solution B - Use ref pattern (RECOMMENDED):**
```javascript
const handleVoiceCommandRef = useRef(handleVoiceCommand)

useEffect(() => {
  handleVoiceCommandRef.current = handleVoiceCommand
}, [handleVoiceCommand])

useEffect(() => {
  const ws = new WebSocket(...)
  ws.onmessage = (ev) => {
    if (voiceAssistEnabled) {
      handleVoiceCommandRef.current(msg.text) // ← Always uses latest
    }
  }
  return () => ws.close()
}, []) // ← Keep empty deps
```
**Advantage:** WebSocket stays connected, always uses latest function

### Priority 2: Simplify Voice Assist Resume
**Current:** Inline code duplicates recording logic  
**Better:** Extract to reusable function

```javascript
const startContinuousListening = useCallback(() => {
  setTimeout(() => {
    if (voiceAssistEnabled && !isRecording) {
      beginRecording()
    }
  }, 500)
}, [voiceAssistEnabled, isRecording, beginRecording])

// Use in multiple places:
// 1. After transcription in Voice Assist mode
// 2. After resuming from one-shot chat mic
```

### Priority 3: Add Voice Command Debugging
**Add visual feedback:**
```javascript
const handleVoiceCommand = useCallback((transcript) => {
  // Show command in UI for debugging
  setLastTranscript(transcript)
  
  // Add visual indicator that command was received
  setChatMessages(m => [...m, { 
    type: 'system', 
    text: `🎤 Heard: "${transcript}"` 
  }])
  
  // ... rest of command logic
}, [...])
```

## Testing Checklist

### Voice Assist Mode
- [ ] Toggle Voice Assist ON → should start recording automatically
- [ ] Say "start calibration" → should trigger `handleStartCalib()`
- [ ] Say "save profile" → should trigger `handleSaveProfile()`
- [ ] Say "reset" → should trigger `handleReset()`
- [ ] After command → should auto-restart recording for next command
- [ ] Toggle Voice Assist OFF → should stop recording

### Chat Mic Mode
- [ ] Click mic button → should start recording
- [ ] Speak message → should transcribe and send to AI chat
- [ ] Click mic again → should stop recording
- [ ] If Voice Assist was ON → should resume after chat message

### Feedback Prevention
- [ ] TTS plays → mic should not pick it up (500ms delay working)
- [ ] No echo/loop when Gunner speaks

## Code Quality Notes

### Good Practices
✅ Uses reducer pattern for calibration state machine  
✅ Proper cleanup in useEffect returns  
✅ Voice Activity Detection for auto-stop  
✅ Separate concerns (Voice Assist vs Chat Mic)

### Areas for Improvement
⚠️ Large component (1279 lines) - consider splitting  
⚠️ Multiple voice-related refs - could be consolidated  
⚠️ Inline styles mixed with CSS classes  
⚠️ Global flag for resume logic (`window.__gunnerResumeVoiceAssist`)

## Fixes Applied

### ✅ Fixed Stale Closure Issue
**Implementation:** Solution B (ref pattern)
- Added `handleVoiceCommandRef` to store latest command handler
- Updated ref whenever `handleVoiceCommand` changes
- WebSocket now uses `handleVoiceCommandRef.current` to always access latest version
- WebSocket stays connected (no reconnects on state changes)

### ✅ Added Visual Feedback
- Changed chat message from `type: 'user'` to `type: 'system'`
- Added `🎤 Heard: "${transcript}"` prefix for clarity
- User can now see exactly what Gunner heard

## Next Steps

1. ✅ ~~Implement Solution B (ref pattern)~~ - DONE
2. ✅ ~~Add visual feedback for received commands~~ - DONE
3. **Test voice commands** with backend running
4. **Simplify resume logic** with extracted function (optional)
5. **Consider refactoring** voice logic into custom hook (future)

## Related Files
- `frontend/src/services/ttsClient.js` - TTS speak function
- `gateway/ws/audio.js` - WebSocket audio handler
- `backend/routers/voice.py` - Voice transcription backend
