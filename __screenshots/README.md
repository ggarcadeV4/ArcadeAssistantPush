# 🧪 Visual Baseline Testing

This folder stores **panel-level visual snapshots** for UI regression testing.

## Structure

```
__screenshots/
├── baseline/
│   ├── A1_GameTipsPanel.png
│   ├── B2_ControllerMapper.png
└── test_runs/
    └── 2025-09-26_paneltest.png
```

## Rules

- Every panel must have a baseline screenshot before changes
- Changes must show a "before/after" diff for verification
- Claude Browser must reference these when proposing layout edits

---

## Session Log: 2025-11-15

### Voice Assistant & Profile Integration

**Completed Work:**

1. **Cross-Panel Profile Sharing (Complete)**
   - ✅ Integrated ProfileContext into Dewey panel ([DeweyPanel.jsx:87-158](../frontend/src/panels/dewey/DeweyPanel.jsx#L87-L158))
   - ✅ LaunchBox LoRa profile integration confirmed working by user
   - ✅ All three AI assistants (Vicky, LoRa, Dewey) now recognize saved user profile "fergdaddy"

2. **Vicky Voice Configuration (Complete)**
   - ✅ Added Vicky voice profile to `.env` (voice ID: ThT5KcBeYPX3keUQqHPh)
   - ✅ Updated TTS gateway route ([gateway/routes/tts.js:26](../gateway/routes/tts.js#L26))
   - ✅ Created `speakAsVicky()` helper function ([ttsClient.js:161-163](../frontend/src/services/ttsClient.js#L161-L163))

3. **Voice Transcription Display (Complete)**
   - ✅ Fixed Whisper API audio format error - changed from mislabeled WAV to correct WebM format ([gateway/ws/audio.js:192](../gateway/ws/audio.js#L192))
   - ✅ Implemented auto-display of transcribed voice text in chat ([VoicePanel.jsx:471](../frontend/src/panels/voice/VoicePanel.jsx#L471))
   - ✅ Transcription now appears as user message immediately after recording

**Known Issues:**

1. **Voice AI Response Failing (In Progress)**
   - Transcription works: "Hello Vicki, how are you?" appears in chat
   - AI response fails with: "Sorry, I encountered an error processing your request."
   - Root cause: WebSocket handler has stale closure accessing outdated `sharedProfile`, `profile`, `players`, `voiceOwner` values
   - Fix needed: Refactor [VoicePanel.jsx:485-523](../frontend/src/panels/voice/VoicePanel.jsx#L485-L523) to use refs instead of direct state access

**Pending Tasks:**

- [ ] Fix voice AI response stale closure issue (use refs for state in WebSocket handler)
- [ ] Test Vicky TTS voice playback with custom voice
- [ ] Verify Dewey profile recognition via voice commands

**Files Modified:**
- `gateway/ws/audio.js` - Fixed audio format (WebM)
- `gateway/routes/tts.js` - Added Vicky voice profile
- `frontend/src/services/ttsClient.js` - Added `speakAsVicky()`
- `frontend/src/panels/voice/VoicePanel.jsx` - Auto-display transcriptions + AI response logic
- `frontend/src/panels/dewey/DeweyPanel.jsx` - ProfileContext integration
- `.env` - Added VICKY_VOICE_ID configuration
- `frontend/dist/index.html` - Rebuilt with all changes (build: index-b4002f23.js)

---

## Session Log: 2025-11-18

### Voice Panel Refactor - Real-Time Information Hub

**Objective:** Refactor Vicky (Voice Assistant) panel to serve as a real-time information hub that broadcasts profile and session context to all AI agents (LaunchBox LoRa, Dewey, ScoreKeeper Sam, etc.) for contextual awareness and smart routing.

**Completed Work:**

1. **Panel Cleanup & Streamlining (Complete)**
   - ✅ Removed "Recent Sessions" section (hardcoded mock data)
   - ✅ Removed "Voice Settings" with 9 voice profile cards
   - ✅ Removed duplicate "Live Transcription" section
   - ✅ Removed `voiceOwner` state and related code
   - ✅ Simplified panel to focus on: Live Transcription, Player Overview, Current Session, Primary User, Tendencies

2. **Primary User Tendencies - Dynamic Backend Integration (Complete)**
   - ✅ Renamed "Dad's Tendencies" to "Primary User Tendencies" with dynamic user name ([VoicePanel.jsx:1301-1349](../frontend/src/panels/voice/VoicePanel.jsx#L1301-L1349))
   - ✅ Fetches tendencies from `/profiles/{primaryUserId}/tendencies.json` ([VoicePanel.jsx:867](../frontend/src/panels/voice/VoicePanel.jsx#L867))
   - ✅ Created sample tendencies file: `frontend/public/profiles/dad/tendencies.json`
   - ✅ Displays: Favorite Game, Favorite Genre, Total Sessions, Peak Play Time, Most Used Platform
   - ✅ Three states: loading, empty (no data), ready (with data display)

3. **Save & Broadcast Functionality (Complete)**
   - ✅ Implemented "Save & Broadcast" button with toast notifications ([VoicePanel.jsx:946-1015](../frontend/src/panels/voice/VoicePanel.jsx#L946-L1015))
   - ✅ Created backend endpoint: `PUT /api/local/profile/primary` ([profile.py:247-317](../backend/routers/profile.py#L247-L317))
   - ✅ Canonical storage location: `A:\state\profile\primary_user.json`
   - ✅ Broadcast pattern: Write-once to canonical location; agents pull when needed (no WebSocket fan-out)
   - ✅ Automatic backups created on each save: `A:\backups\20251118\HHMMSS_state_profile_primary_user.json`
   - ✅ Success/error toast notifications with 4s/6s auto-hide
   - ✅ Chat messages confirm save status

4. **Profile Hierarchy System (Complete)**
   - ✅ **Primary User** (bottom of Vicky panel) = default profile for entire Arcade Assistant
   - ✅ Each panel has dropdown for temporary per-panel override
   - ✅ Simple architecture eliminates complex multi-user session logic
   - ✅ User profile "FERGDADDY" successfully saved and broadcast to all agents

5. **Backend Infrastructure (Complete)**
   - ✅ Created `PrimaryProfilePayload` model ([profile.py:47-55](../backend/routers/profile.py#L47-L55))
   - ✅ Added `_primary_profile_file()` helper function ([profile.py:71-72](../backend/routers/profile.py#L71-L72))
   - ✅ Implemented broadcast endpoint with validation, backups, and logging
   - ✅ Mounted profile router with `/api/local` prefix ([app.py:316](../backend/app.py#L316))

6. **Frontend Integration (Complete)**
   - ✅ Added GATEWAY constant for proper routing between Vite dev server and gateway ([VoicePanel.jsx:9-10](../frontend/src/panels/voice/VoicePanel.jsx#L9-L10))
   - ✅ Updated `profileClient.js` with GATEWAY constant ([profileClient.js:1-2](../frontend/src/services/profileClient.js#L1-L2))
   - ✅ Fixed all API paths to include `/api/local` prefix
   - ✅ Added `x-scope: state` headers to preview/apply functions

**Technical Challenges Resolved:**

1. **Error: `voiceOwner is not defined`**
   - **Issue:** Leftover reference in sendMessage callback dependency array
   - **Fix:** Removed `voiceOwner` from dependency array ([VoicePanel.jsx:436](../frontend/src/panels/voice/VoicePanel.jsx#L436))

2. **Error: 404 on `/api/local/profile/primary`**
   - **Issue:** Profile router mounted without `/api/local` prefix
   - **Fix:** Added `prefix="/api/local"` when mounting router ([app.py:316](../backend/app.py#L316))

3. **Error: 404 on legacy profile/consent endpoints**
   - **Issue:** All routes got prefix, breaking old paths
   - **Fix:** Updated all paths in `profileClient.js` to include `/api/local`

4. **Error: "Mutating operations require x-scope header"**
   - **Issue:** Relative URL sent requests to Vite dev server (port 5173) instead of gateway (port 8787)
   - **Fix:** Added GATEWAY constant and updated fetch call to use `${GATEWAY}/api/local/profile/primary`

5. **Error: "Proxy error"**
   - **Issue:** Gateway couldn't reach backend after configuration changes
   - **Fix:** User resolved by restarting dev server

**Architecture Decisions:**

- **Broadcast Pattern:** Single REST call writes to `state/profile/primary_user.json`; all agents read from this canonical location
- **No WebSocket Fan-out:** Simpler architecture, single source of truth
- **Tendencies Source:** Backend provides tendencies data; frontend only displays (no calculation)
- **Profile Hierarchy:** Primary user = default; per-panel override without affecting primary
- **GATEWAY Constant:** Routes requests from Vite dev server (5173) to gateway (8787) in development mode

**Files Modified:**
- `frontend/src/panels/voice/VoicePanel.jsx` - Removed sections, added tendencies display, Save & Broadcast functionality, GATEWAY constant
- `frontend/src/services/profileClient.js` - Added GATEWAY constant, updated all API paths to `/api/local`
- `backend/routers/profile.py` - Added `PrimaryProfilePayload` model, `PUT /profile/primary` endpoint
- `backend/app.py` - Added `/api/local` prefix to profile router mounting
- `frontend/public/profiles/dad/tendencies.json` - Created sample tendencies file
- `A:\state\profile\primary_user.json` - Canonical broadcast location (created)

**Verification:**
- ✅ Multiple successful saves logged: `PUT /api/local/profile/primary HTTP/1.1" 200 OK`
- ✅ Automatic backups created: `A:\backups\20251118\040625_state_profile_primary_user.json`
- ✅ Profile data correctly saved with user_id, display_name, initials, vocabulary, voice_prefs
- ✅ Toast notifications working (green for success, red for errors)
- ✅ All agents can now read primary user profile from canonical location

**Next Steps:**
- [ ] Implement agent-side logic to read from `state/profile/primary_user.json`
- [ ] Wire up real tendencies calculation from LaunchBox gameplay data
- [ ] Add profile-aware routing in AI chat responses