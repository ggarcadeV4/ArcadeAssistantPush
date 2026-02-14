# Vicky + Scorekeeper Session Plan

_Last updated: 2025-11-15 (auto noted)_

## Intent

Document the agreed sequence so we can resume seamlessly if this session is interrupted.

## Focus Areas

1. **Profile Schema Extension**
   - Expand `/api/profile` contract (backend + frontend clients) to persist `preferences.voiceAssignments`, vocabulary, and session presets per `docs/VICKY_VOICE_PLAN.md`.
   - Include tests/validation so extra fields survive preview/apply, and changelog entries retain the new payload.
2. **Vicky Voice Panel Wiring**
   - Teach `VoicePanel` to edit the new profile fields: voice cards should write to `preferences.voiceAssignments`, vocabulary textarea maps to `preferences.vocabulary`, and preset actions update `players`.
   - Ensure preview/apply round-trips work with the richer schema.
3. **Scorekeeper Sam Voice Hook**
   - After Vicky stores assignments, let Sam read `profile.preferences.voiceAssignments.sam`.
   - Add a simple selector + `ttsClient.speak` preview so Sam feels "camera ready" once data exists.

## If We Get Cut Short

- Partial progress in Step 1: capture current schema diff (`backend/routers/profile.py`, `frontend/src/services/profileClient.js`) and stage tests, even if Vicky/Sam updates wait.
- Partial progress in Step 2: leave TODO comment referencing this file so future session knows which UI block still needs persistence.
- Partial progress in Step 3: acceptable to keep Sam voice UI hidden behind feature flag until Vicky emits assignments.

## Next Actions

1. Modify backend `UserProfile` model + serializers to accept `preferences` object (with voice/vocab/presets) and update preview/apply outputs.
2. Mirror typings in `profileClient` + any consuming hooks.
3. Enhance `VoicePanel` to read/write the richer profile.
4. Wire Scorekeeper Sam voice UI once profile assignments flow end-to-end.
