# Voice Assistant Audio Profile Cache Plan
**Status:** Template - Not Yet Started
**Priority:** Low (v2.0 Feature)
**Pattern:** Option C Checkpoint (follows LaunchBox image cache model)

---

## Problem Statement

### Current Issue
- Voice assistant settings reset on every session
- No persistence of preferred voice (ElevenLabs voice_id)
- User must reconfigure audio settings after restart
- No memory of user's speaking patterns or preferences

### Performance Goal
- Cache user's voice preferences to disk
- Remember selected TTS voice
- Store audio calibration settings (mic gain, etc.)
- Enable personalized voice experience

---

## Proposed Architecture

### Cache Structure
```json
{
  "version": "1.0",
  "created_at": "2025-10-08T12:34:56.789Z",
  "tts_preferences": {
    "provider": "elevenlabs",
    "voice_id": "21m00Tcm4TlvDq8ikWAM",
    "voice_name": "Rachel",
    "speed": 1.0,
    "pitch": 1.0
  },
  "stt_preferences": {
    "language": "en-US",
    "continuous": false
  },
  "audio_calibration": {
    "mic_gain": 0.8,
    "noise_gate": -40,
    "last_calibrated": "2025-10-08T10:00:00.000Z"
  }
}
```

### Cache Location
`backend/cache/voice_profile_cache.json`

---

## Implementation Checklist

### Step 1: Create Voice Profile Service
- [ ] Create `backend/services/voice_profile_cache.py`
- [ ] Add cache save/load methods
- [ ] Add per-user profile support (if multi-user)

### Step 2: Integrate with Voice Assistant Panel
- [ ] Load voice preferences on panel initialization
- [ ] Save preferences after user changes settings
- [ ] Add "Reset to Defaults" option

### Step 3: Testing
- [ ] Test TTS voice persistence
- [ ] Test audio calibration settings
- [ ] Test profile switching (if multi-user)

---

## Success Criteria
- Voice assistant remembers user's preferred voice/settings
- Audio calibration persists across sessions
- User experience feels personalized

---

**Status:** Template ready for future implementation (v2.0)
**Estimated Effort:** 15-20 minutes implementation + 10 minutes testing
**Dependencies:** Voice integration must be implemented first
**Note:** Deferred to v2.0 per user preference (voice adds complexity)
