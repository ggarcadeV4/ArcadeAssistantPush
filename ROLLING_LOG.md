# ROLLING LOG — Arcade Assistant

## 2026-03-01 | Controller Chuck UX Sprint — FLIP Animations, Focus Mode, Mapping Confirmation
**Net Progress**: Deep UX refinement session on `ControllerChuckPanel.jsx` and `controller-chuck.css`. Overhauled the entire interactive mapping experience from static layout to a cinematic, animation-driven system. All changes build-verified (234 modules, 0 errors). Commits: `586db64`, `a5fcd5e`, `bb3a81f`, `92039ff`, `64513cb`, `ac64c9c`.

**Key Wins:**
- **FLIP Focus Animation**: Click any player card → it springs from its exact grid position to the dead center of the panel using React `getBoundingClientRect()` + CSS custom properties `--flip-x/y/w`. Direction-aware: P1 comes from bottom-left, P2 from bottom-right, P3 from top-left, P4 from top-right. Spring easing: `cubic-bezier(0.34, 1.56, 0.64, 1)`.
- **Premium Return Animation**: Card "breathes out" to scale(1.52) → arcs back to its original grid corner with a blur+fade dissolve. Uses `returningPlayer` state machine so `position:absolute` is held during exit. `onAnimationEnd` clears state cleanly.
- **2P/4P Layout Unification**: Rooted the bug that made 2P mode look completely different from 4P — the `chuck-main` needed `justify-content: center; gap: 14px` (same as 4P). Matching compact card sizing (44px buttons, 66px joystick, `max-height: 180px`). Center logo hidden in 2P. Player row content-sized in both modes.
- **Mapping Confirmation Animation System**: Click a button/direction in the UI → cyan pulse starts. Physical cabinet press fires `latestInput` from `useInputDetection`. `PlayerCard` `useEffect` catches it while waiting, fires `confirmedButton`/`confirmedDir` states, auto-clears after 1.8s. Confirmation: white flash → scale(1.35) green ring burst on button; white → green settled glow on arrow; `✓ GPIO XX` badge slides up and fades out.
- **Top Strip (SCAN + DETECT) both modes**: Confirmed visible in 2P and 4P via `justify-content: center` fix.
- **Container size fix during FLIP animation**: `width: var(--flip-w)` locks card dimensions during `position: static → absolute` transition.
- **Directional arrows** (already done prior): flow-toward-center waiting animation, 12px triangle paths with `data-dir` attributes.

**Files Modified:**
- `frontend/src/panels/controller/ControllerChuckPanel.jsx` — FLIP handler (`mainRef`, `handleFocus`, `focusOrigin`, `returningPlayer`), PlayerCard refactor (cardRef, confirmStates, useEffect listener), ArcadeButton + JoystickGraphic confirmed props, latestInput threading
- `frontend/src/panels/controller/controller-chuck.css` — `@keyframes flip-to-center`, `@keyframes return-to-grid`, `@keyframes btn-confirmed`, `@keyframes dir-confirmed`, `@keyframes badge-pop`, 2P layout unification blocks, `focus-returning` class

**Architecture Notes:**
- `returnPlayer` state machine: `activePlayer=null` triggers return → card stays `position:absolute` via `.focus-returning` → `onAnimationEnd` clears → normal grid layout resumes. Critical for avoiding position snap.
- `latestInput` threading: lives in main component (from `useInputDetection`), passed as prop to each `PlayerCard`. Each card independently watches for it while in a waiting state. Avoids lifting mapping state to parent.
- 4P/2P CSS parity: All compact sizing in `chuck-main[data-mode]` selectors. The `chuck-shell[data-mode="4p"] .chuck-main { justify-content: center }` rule (line ~1545) is the canonical anchor — 2P now mirrors it.

**Commits**: `586db64` FLIP origin animation | `a5fcd5e` premium return animation | `bb3a81f` 2P layout unification | `92039ff` 2P vertical centering | `64513cb` 2P top strip fix (justify-content root cause) | `ac64c9c` mapping confirmation system
**Next**: Microphone support in Chuck's chat sidebar. Then cascade to Vicky Voice panel.

---

## 🔬 FEATURE SPEC IN PROGRESS: Diagnosis Mode — AI-Driven Profile Configuration
*Introduced: 2026-03-01 | Status: Pre-architecture | DO NOT CODE until questions below are resolved.*

### The Concept
A mode-switch on each panel's chat sidebar that shifts the AI from **Standard Mode** (free conversation) to **Diagnosis Mode** (context-aware, action-capable co-pilot). In Diagnosis Mode, the AI knows the current user, current game, current hardware state, and has **write access to config files and user profiles** via tool-use/function-calling.

**The killer use case:** *"Hey Chuck, on Street Fighter 2 for my profile, I want Button 4 to be Punch."* → Chuck writes a per-user, per-game override that persists permanently. Next time that profile loads → Button 4 = Punch.

**Panels that will need this:** Controller Chuck (first), LED Blinky, Console Wizard, Gunner.

---

### Pre-Architecture Planning Questions
*These must be answered before any code is written. Think of this as the design spec gate.*

**1. Microphone Interaction Model: Push-to-Talk vs. Always-On?**
- Does the user press a button each time they want to speak (push-to-talk)? Or is the mic always listening in Diagnosis Mode?
- Push-to-talk: cleaner, fewer false triggers, requires deliberate action.
- Always-on: more natural, but arcade environments have background noise (button clicks, cabinet audio). Need a wake word ("Hey Chuck") or noise filter?
- *Decision needed: Which model fits the physical arcade cabinet use case better?*

**2. TTS (Text-to-Speech) Policy in Diagnosis Mode**
- Does Chuck speak *every* response, or only confirmations and alerts?
- Does Chuck speak over itself if the user interrupts mid-sentence?
- Volume: should Diagnosis Mode auto-raise volume vs. Standard Mode?
- Do we need an interrupt command ("Stop" / "Cancel")?
- *Decision needed: Full TTS, confirmation-only TTS, or user-controlled toggle?*

**3. Wake Word / Activation Boundary**
- In a physical arcade cabinet environment with speakers on, always-on listening risks false triggers from game audio.
- Options: (a) Physical mic button, (b) Wake word ("Hey Chuck"), (c) Silence detection + timeout-gated listening, (d) Diagnosis Mode itself is the activation boundary.
- *Decision needed: How do we gate when Chuck is actually "listening" vs passive?*

**4. Profile Config Schema Design**
- Hardware mapping = `{ userId, playerId, controlKey, gpioPin }` (done today — GPIO level)
- Game overrides = `{ userId, gameId, controlKey, actionLabel }` (new layer — software/semantic level)
- These are *two separate layers* that need to be merged at runtime. Where does merge happen: frontend state, backend, LaunchBox plugin, or Supabase materialized view?
- *Decision needed: Schema structure and merge strategy.*

**5. Tool-Use / Function-Calling Implementation**
- Which AI model handles Diagnosis Mode? Gemini (current), Claude, or OpenAI?
- Does our current proxy edge function support tool schemas (function definitions)?
- Tools needed at minimum: `updateProfileMapping()`, `readCurrentMapping()`, `listAvailableActions()`, `undoLastChange()`
- *Decision needed: Model + proxy extension plan for tool-use.*

**6. Context Injection Scope**
- What data gets injected into the system prompt in Diagnosis Mode?
- Proposed: `{ activeUser, currentGame, gpioMapping (current), profileOverrides (current), boardStatus, detectedBoard }`
- Does the game context come from LaunchBox (via the HttpBridge plugin we already have)? Or manual selection?
- *Decision needed: What is the full context payload and where does each piece come from?*

**7. Conflict Resolution: Hardware vs Profile Override**
- Hardware layer: Button 4 = GPIO 14 (physical wire).
- Profile layer: Button 4 = Punch on SF2 (semantic intent).
- System layer: SF2 config file maps Punch = GPIO 14.
- Who owns the truth? What happens if there's a conflict (e.g., button remapped hardware but profile override still points old GPIO)?
- *Decision needed: Layered priority model (hardware → system → profile) and conflict audit plan.*

**8. Error Handling: AI Misunderstanding a Command**
- Chuck might misinterpret: "make button 4 punch" → maps the wrong button or wrong game.
- Need a confirmation step before write: "I'll set Button 4 to Punch on Street Fighter 2 for [username]. Confirm?"
- Need an undo: "Actually, cancel that" or "Undo last change."
- *Decision needed: Mandatory confirm-before-write? Or optimistic write with undo?*

**9. Rollout Order Across Panels**
- If we build this correctly the first time in Chuck, the pattern (mode switch + context injection + tool-use) should be reusable across all panels.
- Proposed order: Chuck → LED Blinky → Console Wizard → Gunner.
- Do all panels share one `useDiagnosisMode()` hook, or are they all standalone?
- *Decision needed: Shared hook architecture vs. panel-specific implementations.*

**10. Session Summary / Change Commit Flow**
- When user exits Diagnosis Mode, does Chuck summarize what changed? "Session summary: 3 overrides saved — P1 Button 4=Punch (SF2), P1 Button 6=Kick (SF2), P2 Joystick Right=GPIO 12."
- Is there a "commit" step (like a config save button) or are writes immediate?
- *Decision needed: Optimistic real-time writes vs. staged commit model.*

**11. Ambient Noise / False-Fire Prevention**
- Diagnosis Mode in an arcade environment: cabinet speakers, button clicks, fans, background music.
- If using always-on mic, how do we prevent Chuck from triggering on cabinet audio?
- Options: VAD (Voice Activity Detection) threshold tuning, push-to-talk only, noise-gate filter in Web Audio API, confidence scoring on speech transcripts before sending to AI.
- *Decision needed: What noise-handling strategy is acceptable for the cabinet environment?*

---

### Hook Points in Existing Code
*(Identified pre-architecture — DO NOT CODE yet, just reference)*
- `frontend/src/panels/controller/ControllerChuckPanel.jsx` — `handleFocus`, `latestInput`, `mapping` state all relevant
- `backend/routers/` — new route needed: `POST /api/profiles/mapping-override`
- `gateway/server.js` — AI proxy call needs tool-schema support added
- `plugin/src/Plugin.cs` (HttpBridge) — already fires game start/stop events; can provide `currentGame` to context injection
- Supabase `profiles` table — new `mapping_overrides` JSONB column or separate table

---



## 2026-02-28 | V1 Completion Sprint — Close All Audit Blockers
**Net Progress**: Closed 12+ audit-flagged blockers in a single session. Key wins:
- **LEDBlinky path fix**: Updated all backend references from `A:\Tools\LEDBlinky\` to `A:\LEDBlinky\` (actual install location).
- **HttpBridge IGameEventsPlugin**: Added `IGameEventsPlugin` to LaunchBox plugin — game start/stop events now POST to the Python backend with game_id, platform, title, and timestamps.
- **Voice LED injection**: Refactored `VoiceService` to accept real `LEDHardwareService` and `SupabaseClient` via dependency injection. Uncommented all hardware calls in `_apply_to_led_service()`.
- **Cinema genre themes**: Added `NitroRush` (racing: green/yellow/white) and `TargetLock` (lightgun: red/white) themes to `colors.json`. Updated `CINEMA_TAG_TO_THEME` mapping. Added `_apply_genre_theme()` and `_reset_leds_to_idle()` helpers.
- **Voice command TTS**: Added `tryLightingCommand()` in `VoicePanel.jsx` — lighting commands now fire via SSE and speak responses via `speakAsVicky()`.
- **HID fallback in `_call_ledblinky()`**: If LEDBlinky.exe fails for any reason, the function now falls back to `_apply_genre_theme()` via the Python HID stack.
- **blinky_patterns boot block**: Confirmed the import doesn't error — it silently hangs because `blinky.__init__` eagerly parses XML and enumerates HID. Cleaned up comments with root cause and fix path (lazy exports).
- **Supabase project ref**: Discovered all agent config files pointed to the *website* project (`hjxzbicsjzyzalwilmlj`). Fixed to correct Arcade Assistant ref (`zlkhsxacfyxsctqpvbsh`) across 10 files in both A: and C: workspaces.
- **JWT verification**: Toggled `verify_jwt` OFF for `elevenlabs-proxy` and `openai-proxy` in Supabase dashboard. Health check confirmed 200 OK.
- **Dead code removal**: Deleted two orphaned 241KB monolith files (`LEDBlinkyPanel.jsx`, `LEDBlinkyPanelNew.jsx`). The app uses the refactored 25KB version in `led-blinky/`.
- **doc_diagnostics upgrade**: Copied C: drive version (9KB, 262 lines) over A: drive version (4KB, 133 lines). Added VID/PID scanning, health alerts, WebSocket event stream.
- **Assistants.jsx persona names**: Updated all 9 persona entries to match canonical roster: Dewey, LaunchBox LoRa, ScoreKeeper Sam, Controller Chuck, LED Blinky, Gunner, Console Wizard, Vicky, Doc.

**Struggles & Lessons Learned**:
1. **Wrong Supabase project ref**: The CLI returned empty tables for functions and secrets because every agent config file pointed to the G&G Website project instead of Arcade Assistant. Root cause: the refs were copy-pasted incorrectly when the multi-project setup was created. Fix: visual confirmation via browser dashboard, then bulk update across all agent files.
2. **blinky_patterns import hang**: Not an error — a *silent freeze*. The `__init__.py` eagerly imports `PatternResolver` which reads LEDBlinky XML files and enumerates HID devices synchronously. Previous comments just said "blocking" without explaining why. Fixed by adding clear documentation and noting the fix path (convert to lazy `__getattr__` exports).
3. **git commit on external drive**: A: drive (USB) git commit hung for 5+ minutes during large file delta computation. The commit eventually completed but required patience.

**Commit**: `94e21d4` on `master` (A: drive, 19 files). `118577f` on `v1-persona-split` (C: drive, 4 files).
**Next**: End-to-end test of cinema genre themes during live gameplay. Verify VoicePanel lighting command flow. Consider converting `blinky.__init__` to lazy exports to re-enable `/api/blinky` endpoints.

## 2026-02-15 | Valentine's Day Session
**Net Progress**: Built complete 5-piece Playnite Restore Toolkit (Fix-ArcadePaths, Restore-ArcadeAssistant, Launch-Sanity-Check, Backup-Creator, run_all_remediation.bat). Fixed Score Pipeline (5 breaks). Completed A:\ drive anatomy for Infrastructure as Code. Diagnosed Playnite extension load failure (BadImageFormatException). All pushed to Valentine-s-Day repo commit `6f74194`.
**Next**: Source Golden Backup via Playnite Auto-scan, configure Game Scanners, run overnight metadata scrape.
- 2026-02-21: Fixed CI/CD sync, deployed new Blinky UI with TTS-enabled chat drawer and pulsing mic.

## 2026-02-22 | Gunner Panel Redesign (Phase 1)
**Net Progress**: Full Gunner codebase audit (~5,700 lines). Redesigned Gunner panel from monolithic 946-line `LightGunsPanel.jsx` into 11-file modular architecture in `components/gunner/`. Created: `GunnerPanel.css` (full cyber/neon design system with Orbitron font, scanlines, glitch animations), `GunnerPanel.jsx` (orchestrator), `GunnerHeader.jsx`, `GunnerNav.jsx`, `GunnerAlertBar.jsx`, `DevicesTab.jsx`, `DeviceCard.jsx`, `SensorGrid.jsx`, `ConnectionMatrix.jsx`, `GunnerChatSidebar.jsx`, `useGunnerChat.js` (AI chat hook with Gemini tool schemas). Swapped import in `Assistants.jsx`. Clean build verified (1.81s), `gunner-panel` class confirmed in dist bundle. Initial build served stale cache — fixed with dist wipe + clean rebuild.
**Status**: Awaiting visual confirmation after user machine restart.
**Next**: Visually verify panel renders correctly. Then build Phase 2: Calibration tab, Profiles tab, Retro Modes tab, voice controls integration, live `gunnerClient.js` API wiring.

## 2026-02-23 | Infrastructure & VUI Milestone + Dewey V2.5 Transplant
**Net Progress (AM)**: Fixed consent save 403 (added `.aa/`-prefixed sanctioned paths to manifest). Integrated `httpx` broadcast into `scorekeeper.py` REST endpoints (`apply_score_submit`, `game_autosubmit`) for instantaneous WebSocket leaderboard push. Built Vicky Voice phase indicator bridges (`isSpeaking` state, `currentPhase` badge: 🎤→🧠→🔊→💤). Extracted `useGemSpeech` hook. 237 modules, 0 errors.
**Net Progress (PM)**: Transplanted Dewey Arcade Historian V2.5 design (1,100+ lines Tailwind→vanilla CSS, JSX restructure). Fixed `speechSupported` undefined bug. Diagnosed stale build issue (C: vs A: drive split). Created `scripts/clean-start.ps1` for zombie port cleanup + rebuild + deploy. Implemented WS exponential backoff in `ProfileContext.jsx` and `hotkeyClient.js` (2s→30s cap). Added `[App]` diagnostic banner to `App.jsx`. Root-caused "blue screen" to empty `personas = []` array in `Assistants.jsx` when `/assistants` has no query param.
**Status**: Dewey V2.5 renders correctly via `?chat=dewey`. WS console spam eliminated.
**Next**: Populate `personas[]` array in `Assistants.jsx` so `/assistants` shows agent selection grid. End-to-end consent UI flow test. Gunner Phase 2.
