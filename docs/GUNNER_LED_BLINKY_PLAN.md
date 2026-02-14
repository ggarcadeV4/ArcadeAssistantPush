# Gunner & LED Blinky Integration Plan

## Shared Objectives
- Keep Vicky’s profile/voice selections as the source of truth for every agent.
- Reuse LaunchBox metadata (platforms, ROM ids) so all downstream services agree on naming.
- Surface status + diagnostics inside each panel so camera-ready demos show “online/ready”.

---

## LED Blinky Coverage (≈2,500 games)

### Current References
- `docs/NORTHSTAR_CONTROLLER_CHUCK_WIZARD_LED_BLINKY_CASCADE.md`
- LaunchBox parser services (`backend/services/launchbox_parser.py`)
- Existing LED profiles under `config/led-blinky/` (needs audit)

### Workstreams
1. **Library Snapshot**
   - Export canonical game list from LaunchBox (`/api/launchbox/games?limit=20000`).
   - Normalize titles/platforms (same helper Dewey uses).
   - Store snapshot in `state/led_blinky/library.json` with checksum + timestamp.

2. **Profile Inventory**
   - Crawl LED Blinky config directory and build index of available profiles.
   - Track mismatch types: missing game, stale path, duplicate, etc.
   - Save to `state/led_blinky/profile_index.json`.

3. **Diff + Auto-Generation**
   - Script `scripts/led_blinky_sync.py` compares LaunchBox list vs profile index.
   - For missing entries, scaffold template JSON (per platform) with button colors.
   - Optionally pull button layouts from Controller Chuck baseline so LED colors match physical wiring.

4. **Cascade Hook**
   - When Controller Chuck applies a mapping, call `update_led_blinky_profile(baseline)` so LED layouts stay aligned (per Northstar doc).
   - LED Blinky panel shows last cascade time, total games covered, and a “Rebuild Profiles” button that reruns the sync script.

5. **UI/UX (LED Blinky Panel)**
   - Dashboard cards: Coverage %, Last Sync, Active Theme.
   - Search input to preview a game’s LEDs (load from `state/led_blinky/profile_index.json`).
   - Status toast if LED Blinky executable/service isn’t reachable.

6. **Verification**
   - Automated test: sample 20 random LaunchBox titles and confirm LED profile exists + pins populated.
   - Manual smoke: trigger cascade after changing a controller pin, ensure LED layout updates.

---

## Gunner (Light Guns)

### Current References
- `docs/A_DRIVE_INTENT_MAP.md` (light gun paths)
- Backend routers (`backend/routers/gunner.py`)
- Voice cards in Vicky panel (`key: 'lightguns'`)

### Workstreams
1. **Profile Source of Truth**
   - Reuse Vicky’s profile to track preferred calibration (distance, brightness, player order).
   - Persist gun-specific settings under `profile.preferences.lightguns`.
   - Dewey/Gunner panels show current owner and last calibration timestamp.

2. **Calibration Pipeline**
   - Backend endpoint `POST /api/lightguns/calibrate` orchestrates:
     1. Detect connected guns (Sinden/Gun4IR).
     2. Launch calibration helper or push config via vendor CLI.
     3. Log output to `logs/lightguns/calibration.jsonl`.
   - Gunner panel buttons call this endpoint and show live progress (spinner + console tail).

3. **Per-Game Overrides**
   - Use LaunchBox metadata to flag games that require custom gun modes (dual wield, offscreen reload).
   - Store overrides in `config/lightguns/game_overrides.json`.
   - When LaunchBox LoRa launches a gun game, consult this file and push the override before booting the emulator.

4. **LED + Gunner Coordination**
   - When a gun game launches, LED Blinky should automatically highlight P1/P2 trigger buttons.
   - Hook into the same cascade job so gun layouts share the controller baseline (button labels, colors).

5. **Diagnostics**
   - Gunner panel gets a “Sensors” card showing:
     - Gun detected (Yes/No), firmware version, COM port.
     - Recent calibration status (timestamp + success/failed).
     - Button test (show live trigger presses via WebSocket).
   - Provide downloadable report (`/api/lightguns/report`) for support/debugging.

6. **Voice Integration**
   - Vicky/Gunner voice card lets the user preview the gunner persona voice.
   - Dewey can route “calibrate my light guns” intents by calling Gunner’s API and narrating the progress using the same voice.

---

## Suggested Next Steps
1. Finish Vicky’s profile + voice selection work (per VICKY_VOICE_PLAN.md).
2. Build the LED Blinky library snapshot + profile index scripts (Workstreams 1–2 above).
3. Hook Controller Chuck’s “Apply” action to trigger the LED cascade helper.
4. Flesh out Gunner’s calibration endpoint + panel diagnostics with real data.

Document progress in each panel’s README so we keep the customer journey aligned. When all four (Vicky, LoRa, Dewey, Sam) are camera-ready, schedule a dedicated session to polish LED Blinky + Gunner concurrently since they share hardware dependencies.
