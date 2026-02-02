## Daily Slice – Gunner Panel (2025-11-29)

### Summary
- Simplified the Lightguns panel to rely solely on the shared `/ws/audio` ➜ `/api/ai/chat` pipeline; no custom voice stack remains.
- Wired every calibration control (`Start`, `Skip Step`, `Save`, `Load`, `Test Accuracy`) through the existing `gunnerClient` helpers so all traffic flows via `/api/local/gunner/*`.
- Added a compact push-to-talk component plus transcript-to-command handler so calibration shortcuts respond to voice and text equally.

### CLI Verification
1. **Backend & Gateway health**
   ```bash
   npm run test:health
   ```
2. **Smoke the full stack (ensures gateway ⇄ backend ⇄ frontend wiring)**
   ```bash
   npm run smoke:stack:no-start
   ```
3. **Frontend lint/build sanity**
   ```bash
   cd frontend
   npm run build
   ```
4. **Backend Gunner tests**
   ```bash
   cd backend
   pytest -q tests/test_gunner_service.py
   ```

> After running the above, open the Lightguns panel (via `npm run dev` or `start-gui.bat`) to click through Start/Skip/Save/Test and confirm the chat/mic routes responses through Gunner.

### Session Notes
- Mic clicks now call `stopSpeaking()` before any recording starts, so ongoing Gunner TTS is cut off immediately when you press the button.
