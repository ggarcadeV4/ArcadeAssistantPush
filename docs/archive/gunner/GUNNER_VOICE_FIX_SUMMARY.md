# Gunner Voice Fix Summary

**Date:** 2025-11-26  
**Issue:** Voice commands not triggering calibration actions  
**Status:** ✅ FIXED

## Problem
When user said "start calibration" in Voice Assist mode, Gunner would hear the command (visible in console logs) but wouldn't execute the action. The calibration wizard wouldn't start.

## Root Cause
**Stale Closure in WebSocket Handler**

The WebSocket was created once with empty dependencies:
```javascript
useEffect(() => {
  const ws = new WebSocket(...)
  ws.onmessage = (ev) => {
    handleVoiceCommand(msg.text) // ← Always uses INITIAL version
  }
}, []) // ← Empty deps = never updates
```

When `handleVoiceCommand` updated (due to state changes), the WebSocket still referenced the old version from when it was first created.

## Solution
**Ref Pattern to Access Latest Function**

1. Created ref to store latest command handler:
```javascript
const handleVoiceCommandRef = useRef(null)
```

2. Updated ref whenever function changes:
```javascript
useEffect(() => {
  handleVoiceCommandRef.current = handleVoiceCommand
}, [handleVoiceCommand])
```

3. WebSocket uses ref to always get latest version:
```javascript
ws.onmessage = (ev) => {
  if (handleVoiceCommandRef.current) {
    handleVoiceCommandRef.current(msg.text) // ← Always latest!
  }
}
```

## Additional Improvements

### Visual Feedback
Changed chat messages to show what Gunner heard:
```
🎤 Heard: "start calibration"
```

This helps users debug voice recognition issues.

### Loose Pattern Matching (Already Present)
Commands use partial matching:
- "start", "calibrat", "begin" → Start calibration
- "save", "accept", "finish" → Save profile
- "retry", "again", "reset" → Reset calibration

## Testing Instructions

### Prerequisites
1. Backend running on port 8000
2. Gateway running on port 8787
3. Frontend at localhost:8787 (or Vite dev at 5173)

### Test Voice Assist Mode
1. Open Gunner panel (Light Guns)
2. Toggle "Voice Assist" switch ON
3. Wait for "🎤 Listening" indicator
4. Say: **"start calibration"**
   - ✅ Should trigger calibration wizard
   - ✅ Should show `🎤 Heard: "start calibration"` in chat
   - ✅ Gunner should respond with TTS
5. Say: **"save profile"**
   - ✅ Should save calibration data
6. Say: **"reset"**
   - ✅ Should reset calibration state

### Test Chat Mic Mode
1. Toggle Voice Assist OFF
2. Click microphone button in chat
3. Say a question: **"How do I calibrate?"**
   - ✅ Should transcribe and send to AI chat
   - ✅ Should get AI response

## Files Modified
- `frontend/src/panels/lightguns/LightGunsPanel.jsx` - Fixed stale closure, added visual feedback
- `GUNNER_VOICE_AUDIT.md` - Comprehensive audit document
- `GUNNER_VOICE_FIX_SUMMARY.md` - This file

## Related Issues
- Same pattern should be checked in Doc panel (`DocVoiceControls.jsx`)
- Console Wizard may have similar WebSocket closure issues

## Success Criteria
✅ Voice commands trigger actions immediately  
✅ No console errors  
✅ Visual feedback shows what was heard  
✅ TTS responses play without feedback loop  
✅ Continuous listening works (auto-restarts after command)
