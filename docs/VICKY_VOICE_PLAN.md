# Voice Vicky Production Plan

## Goals
1. Make Voice/Vicky the single source of truth for user identity, consent, vocabulary, and agent voice selections.
2. Expose the saved profile to every panel (LoRa, Dewey, Sam, Chuck, LED, Gunner) without duplicating forms.
3. Ensure the mic/WS pipeline stays reliable so spoken input routes cleanly to other agents.

---

## Work Breakdown

### 1. Profile Editor
- [ ] Wire the name/initials/color inputs to `profile` state.
- [ ] Hook the “Save Profile” button to `previewProfile`/`applyProfile`.
- [ ] Surface errors + success toast so the user knows the profile persisted.
- [ ] Confirm Scorekeeper Sam/others read the updated profile automatically.

### 2. Consent Overlay
- [ ] Bind the three checkboxes (network/leaderboard/contact) to `consent`.
- [ ] Use `previewConsent` → `applyConsent` to store the selection.
- [ ] Hide the overlay when `consent.accepted === true`.
- [ ] Show a reminder banner in panels that depend on consent if it’s missing.

### 3. Voice Profile Cards
- [ ] Add “Preview Voice” buttons that call `speak` with the correct profile.
- [ ] Let the user choose a voice per agent (LoRa, Dewey, Sam, Chuck, LED, Gunner, Doc).
- [ ] Persist voice assignments to `profile.preferences.voiceAssignments` (or similar).
- [ ] Emit an event/bus update so other panels re-render with the selected voice.

### 4. Vocabulary & Slang
- [ ] Store the vocab textarea contents in `profile.preferences.vocabulary`.
- [ ] Expose quick-add commands (e.g., “cabinet = machine”) as chips so users can toggle them.
- [ ] Provide a reset/clear option.

### 5. Sessions & Controller Presets
- [ ] Save the `players` array (who is on which controller) in the shared profile.
- [ ] Expose quick actions (“Apply Dad + Kid Y”) that update the saved preset and notify Controller Chuck/Wizard.
- [ ] Show a dropdown in Chuck/Wizard to pick from those presets.

### 6. Mic & Transcription UX
- [ ] Keep the current MediaRecorder/WebSocket flow but show real-time hints (e.g., “Listening… tap again to stop”).
- [ ] Display STT errors inline (permissions, WebSocket issues).
- [ ] Allow one-click “Send transcript to LoRa/Dewey” buttons directly from Vicky.

### 7. UI Polish / Accessibility
- [ ] Add a “current user” badge at the top (name, initials, color).
- [ ] Provide keyboard focus states for every interactive element.
- [ ] Respect `prefers-reduced-motion` (disable mic animations when needed).
- [ ] Add tooltips/help text describing what each section controls.

---

## Validation Checklist
- [ ] Saving profile updates the backend and LoRa/Dewey immediately reflect the new name.
- [ ] Consent overlay stays hidden once accepted and comes back if consent is revoked.
- [ ] Each agent card plays its TTS preview and the selection persists after reload.
- [ ] Vocabulary entries show up in other panels (e.g., Dewey) where appropriate.
- [ ] Controller presets propagate to Controller Chuck/Wizard.
- [ ] Mic button starts/stops recording, shows warnings on failure, and transcription appears in chat.
- [ ] QA pass on Chrome/Edge + at least one kiosk browser.

---

## Next Session
1. Implement Section 1 (Profile editor) + Section 2 (Consent overlay).
2. Rebuild frontend and verify profile data flows to Scorekeeper Sam.
3. Iterate through remaining sections in follow-up sessions.
