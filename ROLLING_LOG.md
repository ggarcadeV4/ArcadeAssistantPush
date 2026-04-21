# ROLLING LOG — Arcade Assistant

## 2026-04-13 NIGHT (Antigravity Session — Console Wizard Milestone + Controller Chuck Progress)

**Net Progress**: Console Wizard accepted as a functional product surface. Controller Chuck made major progress on board-identity detection but still needs one final truth-surface reconciliation pass before it is declared done. Session doctrine was sharpened and carried forward.

---

## 2026-04-20 (Codex Session - Phase B Engineering Bay Full Architecture Reality Check)

**Net Progress**: Completed a read-only architecture audit of the six Engineering Bay personas to establish the real shared-vs-siloed state before any Phase B migration work begins.

### What Was Confirmed

- **Correct repo / tree**:
  - Work was performed in `W:\Arcade Assistant Master Build\Arcade Assistant Local`.
  - The active frontend panel tree is primarily `frontend/src/panels/`.
  - Two active persona entry points still live under `frontend/src/components/`:
    - `components/gunner/GunnerPanel.jsx`
    - `components/led-blinky/LEDBlinkyPanelNew.jsx`

- **Frontend transport is shared**:
  - `frontend/src/panels/_kit/EngineeringBaySidebar.jsx` is the active shared chat UI for:
    - Doc
    - Chuck
    - Wiz
    - Blinky
    - Gunner
    - Vicky
  - Shared diagnosis/action infrastructure also includes:
    - `frontend/src/hooks/useDiagnosisMode.js`
    - `frontend/src/panels/controller/DiagnosisToggle.jsx`
    - `frontend/src/panels/controller/ContextChips.jsx`
    - `frontend/src/panels/controller/ExecutionCard.jsx`

- **Backend transport is only partly shared**:
  - `backend/routers/engineering_bay.py` is the shared route entry point for all six personas.
  - But the service layer is not truly unified:
    - `doc`, `wiz`, `blinky`, `gunner`, `vicky` -> `backend/services/engineering_bay/ai.py`
    - `chuck` -> `backend/services/chuck/ai.py`
  - This means Chuck is already partially siloed on the backend.

- **Provider / transport normalization findings**:
  - The shared Engineering Bay backend still calls Gemini directly through REST in `backend/services/engineering_bay/ai.py`.
  - It still reads `GEMINI_API_KEY` / `GOOGLE_API_KEY` from environment.
  - It does not use `SecureAIClient`.
  - The active frontend shared sidebar does not parse Gemini-native response shapes. It receives normalized `{ reply, persona, isDiagnosisMode }` and works from plain text.

- **Tooling reality**:
  - No active persona-specific backend function/tool registration was found in `engineering_bay/ai.py`.
  - The only attached model-side tool in the shared service is Gemini-native `google_search`, used only for uncertainty retry grounding.
  - The active execution model is prompt-driven fenced action blocks, not registered tool calling.
  - `EngineeringBaySidebar.jsx` extracts:
    - assistant text
    - optional fenced ```action JSON
  - `ExecutionCard.jsx` then gates the write action behind explicit user confirmation.

- **Legacy / parallel AI paths still exist**:
  - `frontend/src/panels/led-blinky/useBlinkyChat.js` still contains Gemini-native tool schemas for Blinky.
  - `frontend/src/hooks/useGunnerChat.js` still contains Gemini-native tool schemas for Gunner.
  - `frontend/src/panels/console-wizard/WizSidebar.jsx` and `backend/services/wiz/ai.py` remain as a parallel Wiz-specific path.
  - `frontend/src/panels/voice/VoicePanel.jsx` also contains separate non-Engineering-Bay AI paths for voice transcript chat and lighting-command SSE handling.

### Important Contradictions to Prior Assumptions

- Engineering Bay is **not** a single clean shared backend service. Chuck already diverges.
- The active shared frontend path is **not** provider-shape-coupled to Gemini. It consumes normalized text.
- The active shared service does **not** have rich backend function-calling definitions for each persona. Most current "tooling" is prompt-defined action-block behavior instead.

### Prompt / Persona Boundary Evidence

Prompt files contain explicit domain walls that strongly suggest prompt authors have already been compensating for shared-service semantic bleed:

- `prompts/doc.prompt`
  - "I'm a doctor, not a MAME config expert."
- `prompts/controller_chuck.prompt`
  - "GUN WALL"
  - Chuck does not touch Blinky / Wiz territory
- `prompts/gunner.prompt`
  - "CONTROLLER WALL"
  - explicit refusal of joystick / encoder / button mapping questions
- `prompts/controller_wizard.prompt`, `prompts/blinky.prompt`, and `prompts/vicky.prompt`
  - all contain redirect rules that reinforce persona boundaries

This is meaningful architectural evidence, not cosmetic prompt flavor.

### Execution / Action Contract Reality

- The real active execution contract is:
  - backend returns `reply` text
  - `EngineeringBaySidebar.jsx` parses optional fenced action JSON from the text
  - `ExecutionCard.jsx` renders the confirmation gate
  - the UI posts to `action.endpoint` only after explicit user confirmation
- This action-block convention is a core part of the current Engineering Bay system and should be treated as such in future refactor estimates.

### Drift Found

- Several prompts declare repair endpoints that were not found as matching backend routes during this audit:
  - `/api/doc/repair`
  - `/api/local/led/repair`
  - `/api/local/lightguns/repair`
  - `/api/voice/repair`
- This means there is prompt-contract drift between persona instructions and the backend route surface.

### Files Audited

- `frontend/src/panels/_kit/EngineeringBaySidebar.jsx`
- `frontend/src/hooks/useDiagnosisMode.js`
- `frontend/src/panels/system-health/SystemHealthPanel.jsx`
- `frontend/src/panels/system-health/docContextAssembler.js`
- `frontend/src/panels/controller/ControllerChuckPanel.jsx`
- `frontend/src/panels/controller/chuckContextAssembler.js`
- `frontend/src/panels/console-wizard/ConsoleWizardPanel.jsx`
- `frontend/src/panels/console-wizard/WizSidebar.jsx`
- `frontend/src/panels/console-wizard/wizContextAssembler.js`
- `frontend/src/components/led-blinky/LEDBlinkyPanelNew.jsx`
- `frontend/src/components/gunner/GunnerPanel.jsx`
- `frontend/src/panels/voice/VoicePanel.jsx`
- `backend/routers/engineering_bay.py`
- `backend/services/engineering_bay/ai.py`
- `backend/services/chuck/ai.py`
- `backend/services/wiz/ai.py`
- `prompts/doc.prompt`
- `prompts/controller_chuck.prompt`
- `prompts/controller_wizard.prompt`
- `prompts/blinky.prompt`
- `prompts/gunner.prompt`
- `prompts/vicky.prompt`

### Carry-Forward Rules

1. Treat shared frontend transport and shared backend service as separate questions. They are not the same thing in the current codebase.
2. Treat Chuck as already partially siloed when planning Phase B.
3. Preserve the evidence that the active frontend Engineering Bay UI is already provider-agnostic at the response-shape layer.
4. Preserve `EngineeringBaySidebar.jsx`, `useDiagnosisMode.js`, and `ExecutionCard.jsx` as major blast-radius files if full siloing is considered.
5. Before any action-path migration work, reconcile prompt-declared repair endpoints against real backend routes.

---

### Console Wizard — Accepted as Functional ✅

**What was done:**

- **Mic capture hardened**: `EngineeringBaySidebar` gained an optional `micHandlers` prop (`{ isRecording, onToggle }`). When provided, the sidebar's mic button delegates to the panel's own capture stack rather than the shared Web Speech path. Console Wizard injects its `isRecording` / `toggleMic` pair here, bypassing the Web Speech API that was dropping mic state immediately under Electron's permission model.
- **Capture path**: `getUserMedia` → `MediaRecorder` → `/ws/audio` WebSocket. The WebSocket now connects lazily on first mic press (not on panel mount), preventing early gateway rejection during dev startup.
- **Silence detection**: Web Audio API `AnalyserNode` RMS polling auto-stops recording after 1.5 s of silence (1.5 s lead-in). User presses mic once per utterance — no second press required.
- **Unified chat path**: Mic transcripts now route into `EngineeringBaySidebar`'s canonical `sendMessage` via a `wizSendRef` bridge (`onSendRef` prop). Typed and voice chat land in the same visible conversation.
- **DIAG greeting visible**: `useDiagnosisMode` `onGreeting` callback now posts the spoken DIAG greeting into the chat history so mode transitions are explicit in the UI.
- **Visible failures**: All mic / WS failure modes surface an explicit `⚠️` system message in chat rather than silently resetting state.
- **De-dupe guard**: `externalMicRecording` flag added to the sidebar's auto-listen effect so the Web Speech auto-listen path cannot overlap with an active external `MediaRecorder` session.

**Runtime verdict**: Diagnostic Mode felt excellent in live testing. Regular chat path is unified. Remaining Wizard work is polish (UI edge cases, transcript latency), not rescue.

**Files modified:**
- `frontend/src/panels/_kit/EngineeringBaySidebar.jsx` — `micHandlers`, `onSendRef`, `externalMicRecording` de-dupe guard, `onGreeting` callback wiring
- `frontend/src/panels/console-wizard/ConsoleWizardPanel.jsx` — lazy WS connect, `getUserMedia`-first mic, silence detection, `wizSendRef` bridge, DIAG greeting, cleanup on unmount

---

### Controller Chuck — Close, Not Finished

**What landed:**
- Status semantics corrected: "NO BOARD" / "NO SIGNAL" replace the misleading "OFFLINE" label
- SCAN now triggers a backend detection refresh before refetch
- Focused PlayerCard overflow substantially improved
- Canonical board lane hardened progressively:
  - XInput-spoofed arcade-encoder cases added to detection
  - Discovery widened with WMI / device-scanner supplementation
  - Existing Pacto-style grouped XInput topology logic wired into the canonical lane

**Remaining gap:**
- GUI truth vs AI truth are not yet fully reconciled around logical board identity
- Chuck needs one final pass to unify board identity across the visible GUI card, the AI response, and DIAG entry sequencing
- Prior detection logic was not wasted — the intelligence exists in the backend; it is not fully surfacing in the live panel

**Status: Truth-surface reconciliation pass is the next and final Chuck task.**

---

### Session Doctrine (Carry Forward)

1. One panel at a time
2. Codex pre-audit first → narrow implementation → runtime verification
3. Finish by panel promise and canonical path, not by random symptom chasing

---

### Tomorrow's First Move

1. Fresh thread
2. Focus only on Controller Chuck
3. Task: final truth-surface reconciliation pass
   - Logical board identity unified across visible GUI + AI response + DIAG sequencing
   - Focused-card tuning only if still needed once identity is resolved

---

## 2026-04-12 NIGHT (Antigravity Session — F9 / Dewey Summon Path Recovery)

**Net Progress**: Repaired the broken F9 summon path so that Dewey can be called from inside LaunchBox / Big Box. The fix was a narrow transport-layer correction in `frontend/electron/main.cjs` — specifically the WebSocket client that carries hotkey events from the Electron shell to the backend. The summon path now connects with correct device identity, receives hotkey events, and routes Dewey correctly. Game launch from the recovered summon flow was confirmed live by the user. No broad redesign was performed.

**What Was Repaired:**

- **Electron hotkey WebSocket client (`frontend/electron/main.cjs`)** — The client that connects `main.cjs` to the backend `/ws/hotkey` endpoint was broken. The fix corrected the WebSocket connection path and ensured the Electron process attaches with a proper device identity so the backend can identify the source of hotkey presses. Dewey overlay now receives F9 events reliably.
- **Dewey overlay connection** — After the transport fix, the Dewey overlay connected successfully. The backend hotkey manager received the F9 event and triggered the overlay summon as expected.

**Live Validation Completed:**

- F9 key pressed → backend hotkey WebSocket received the event → Dewey overlay summoned. ✅
- User told Dewey "controller wasn't working" → Dewey routed the user correctly to Controller Wizard. ✅
- User launched a game from the recovered summon flow → launch succeeded. ✅

**Scope of Change:**
This was a narrow transport/client fix, not an architectural change. No backend routes, no frontend panel logic, no persona prompts, and no LaunchBox plumbing were modified. The hotkey router and hotkey manager on the backend side were already correct; only the Electron-side WebSocket client was broken.

**Known Remaining Follow-ups (Not Fixed Tonight):**

| Item | Status |
|------|--------|
| Shift+F9 global shortcut registration | ⚠️ Still failing — OS-level shortcut registration conflict not resolved |
| Electron console window polish | 🔶 Deferred — customer-facing console window cleanup not done |
| PS3 backend multi-launch cascade | 🔶 Pending — separate fix, unrelated to tonight's work |
| LaunchBox-side duplicate PS3 record cleanup | 🔶 Separate task — LaunchBox data hygiene, not AA code |

**Key File:**
- `frontend/electron/main.cjs` — WebSocket hotkey client corrected (device identity + connection path)

---

## 2026-04-12 — RESET NOTE — Session Paused, GitHub Backup Withheld

> **⛔ DO NOT BACK THIS STATE UP TO GITHUB**
> **⛔ DO NOT TREAT CURRENT CODE AS APPROVED**
> **⛔ NEXT WORK MUST BEGIN FROM A RESET MINDSET**

### Why This Note Exists

The 2026-04-12 session sequence attempted a deep midline audit followed by a LED Blinky panel restoration. The audit was thorough and produced 5 campaign reports. The restoration work improved some code paths but introduced regressions and left the LED Blinky panel in a partially restored state that does not match the user's intended design. The codebase is not ready for GitHub backup or shipping.

### Session Play-by-Play

**Phase 1 — Read-Only Midline Audit (Campaigns 1–5)**
- Campaign 1: Frontend routing and gateway mediation — verified intact.
- Campaign 2: Identity flows — verified consistent.
- Campaign 3: WebSocket and real-time paths — verified working.
- Campaign 4: Backend router and service layer — verified stable.
- Campaign 5: Cross-panel integration — verified LED hooks, game bindings, and connection state machine are robust.
- **Conclusion**: Infrastructure and backend were determined to be solid. Frontend panel rendering was identified as the regression area.

**Phase 2 — LED Blinky Panel Regression Audit**
- Identified that the user's original ~5,400-line tabbed LED panel (`LEDBlinkyPanel.jsx`) had been replaced by a simplified, flattened component (`LEDBlinkyPanelNew.jsx`) during a prior stability pass.
- 6 tab components were orphaned on disk but disconnected from the render path: `GameProfilesTab`, `RealtimeControlTab`, `HardwareTab`, `LEDLayoutTab`, `CalibrationTab`, and an inline Design mode.
- Backend hooks (`useLEDPanelState`, `useLEDConnection`, `useLEDGameBindings`) were confirmed stable and untouched.

**Phase 3 — LED Blinky Panel Restoration Attempt**
- Rewrote `LEDBlinkyPanelNew.jsx` as a tab orchestrator to re-integrate orphaned tab components.
- Added ~25 bridge state variables and ~20 handler functions to map hook outputs to legacy tab prop signatures.
- Added tab bar CSS to `LEDBlinkyPanel.css`.
- Added `EngineeringBaySidebar` chat drawer (Blinky AI persona).
- The chat drawer was attempted 3 times with different CSS patterns (generic `eb-chat-*`, then `blinky-drawer` matching Chuck's pattern).

**Phase 4 — Session Paused by User**
- User reported the panel was only partially restored.
- The AI chat sidebar was visible but not interactive — the user could not find a way to start a conversation with Blinky.
- The tab bar and full tabbed layout were not confirmed working from the user's perspective.
- The restoration did not match the user's intended design.

### Specific Regressions — Must Be Restored

1. **LED Blinky panel is incomplete**
   - The designed LED panel was not truly restored.
   - It is partially restored at best.
   - The AI chat sidebar has no functional chat entry point — the user cannot engage Blinky.
   - The intended panel behavior, layout, and tab architecture are not back to the user's expectation.
   - Files touched: `LEDBlinkyPanelNew.jsx`, `LEDBlinkyPanel.css`.

2. **LaunchBox LoRa voice regression**
   - LoRa's voice is using a fallback/default voice instead of the intended ElevenLabs voice that was previously configured and working.
   - This voice regression predates the LED work but was surfaced during this session.
   - Must be investigated and restored.

3. **General process drift**
   - The work was not methodical enough panel-by-panel.
   - Some changes improved code paths while breaking intended panel behavior.
   - The purpose of a "finish pass" is defeated if the intended UX, personality, and layout are lost.

### What Is Solid (Do Not Re-Break)

- **Infrastructure (Campaigns 1–3)**: Gateway enclosure, identity standardization, path determinism — all verified intact on 2026-04-11 and re-confirmed on 2026-04-12.
- **Backend hooks**: `useLEDPanelState`, `useLEDConnection`, `useLEDGameBindings` — stable, untouched during the restoration.
- **All non-LED panels**: Gunner, Chuck, Doc, Dewey, Wiz, Voice, Scorekeeper — not touched during this session.
- **LoRa platform routing**: All platforms still launching correctly.

### Guardrails for Next Session

1. **Do not push to GitHub** until the user explicitly approves the state.
2. **Do not treat current code as approved** — it is work-in-progress with known regressions.
3. **Next work must begin from a reset mindset** — re-read the current file state, not assumptions from this session.
4. **Future workflow must be**: intention → Anti-Gravity plan → execution → panel-specific verification (user confirms in browser) → move on.
5. **One panel at a time** — do not batch panel work across multiple panels in a single pass.
6. **Verify before declaring done** — a panel is not "restored" until the user confirms it works in the GUI.

---

## 2026-04-11 (Antigravity Session — Infrastructure Stabilization: Campaigns 1–3)

**Net Progress**: Completed a 3-campaign infrastructure-stabilization sequence. Campaign 1 enclosed all frontend traffic through the Node Gateway, eliminating direct backend bypasses and direct Supabase browser-client usage. Campaign 2 centralized frontend device identity through `frontend/src/utils/identity.js`, eliminating synthetic fallback IDs and unsanctioned localStorage resolution. Campaign 3 aligned `.env` and `.aa/manifest.json` root paths, unified sanctioned-path bootstrap defaults, and replaced inline drive-root fallbacks with canonical helpers. Additionally hardened 5 mutation surfaces with preview/dry-run/audit-log support.

**Key Wins:**
- **Campaign 1 — Gateway Enclosure**: Removed direct frontend→backend `:8000` bypasses, removed direct Supabase browser-client (`@supabase/supabase-js`) from active runtime paths, reconciled backend port drift to canonical `:8000`, added missing `/api/local/hardware/ws/encoder-events` websocket endpoint, removed dead legacy Gunner panel code.
- **Campaign 2 — Identity Standardization**: Created `frontend/src/utils/identity.js` as single identity source, eliminated `CAB-0001`/`cabinet-001`/`demo_001`/`controller_chuck`/`unknown-device` fallbacks, removed `localStorage`-based device identity resolution, standardized `x-device-id`/`x-panel`/`x-scope` headers.
- **Campaign 3 — Path Determinism**: Aligned `.env` and `.aa/manifest.json` `AA_DRIVE_ROOT` values, created `backend/constants/sanctioned_paths.py` for shared path defaults, replaced inline `os.getenv("AA_DRIVE_ROOT")` fallbacks with `get_drive_root()` from `backend/constants/drive_root.py` across 40+ backend files, gateway uses `requireDriveRoot()`/`resolveDriveRoot()` from `gateway/utils/driveDetection.js`, removed hardcoded `A:\`/`W:\` runtime literals.
- **Safety Hardening**: 5 mutation surfaces (`/api/local/config/restore`, `/api/local/profile/primary`, `/api/local/controller/cascade/apply`, `/api/local/controller/mapping/set`, `/api/scores/reset/{rom_name}`) now support preview, dry-run, backup, and request-aware JSONL audit logging.

**Contracts Established:**
- **Golden Drive Contract**: All modules must use `backend.constants.drive_root` or `gateway.utils.driveDetection` helpers. Hardcoded drive literals prohibited.
- **Gateway Mediation**: All frontend→backend communication flows through the Node Gateway.
- **Identity Source**: Frontend identity strictly mediated through `frontend/src/utils/identity.js`.

**Files Created:**
- `backend/constants/sanctioned_paths.py` — NEW (shared sanctioned-path defaults)
- `backend/constants/drive_root.py` — NEW (canonical `get_drive_root()` helper)

**Files Modified (Campaign 3 — partial list, 40+ backend files updated):**
- `backend/services/wiz/ai.py`, `backend/services/engineering_bay/ai.py`, `backend/services/chuck/ai.py` — drive root import
- `backend/services/dewey/trivia_scheduler.py`, `backend/services/dewey/trivia_generator.py` — drive root import
- `backend/startup_manager.py`, `backend/policies/manifest_validator.py` — unified sanctioned paths
- `backend/routers/dewey.py`, `backend/routers/scorekeeper.py`, `backend/routers/marquee.py` — drive root import
- `README.md`, `ROLLING_LOG.md` — daily slice documentation

**Deferred:**
- 4 `process.cwd()` gateway adapter shims (Gateway Pass 2).
- LaunchBox LoRa GUI regression (light guns / American Laser Games titles reappearing) — deferred; direct LaunchBox access functional.

**State of Union — What's Next:**
1. ⚡ **Full system boot-test** — Verify deterministic path and gateway enclosure under real startup
2. ⚡ **Gateway Pass 2** — Replace 4 remaining `process.cwd()` shims in gateway adapters
3. 🔶 **Runtime regression handling** — Use boot-test regressions as anchor for next task

---

## 2026-04-10 (Antigravity Session — LoRa Platform Routing Complete ✅ MILESTONE)

**Net Progress**: Full LoRa validation pass. Every platform on the cabinet now launches correctly through its designated emulator. All critical routing bugs fixed across launchers.json, RetroArch, Dolphin, Cemu, and Supermodel. Bezel drift resolved permanently. CRT-Easymode shader applied globally. LoRa declared the **first completed panel in AA V1**.

**Platform Routing — Final Status:**

| Platform | Status | Emulator |
|----------|--------|----------|
| Arcade MAME | ✅ Working | MAME direct |
| Atari 2600 | ✅ Working | RetroArch (stella) |
| Sega Dreamcast | ✅ Working | Redream standalone |
| Sony PlayStation 2 | ✅ Working | PCSX2 (44 confirmed titles) |
| Sony PlayStation 3 | ✅ Working | RPCS3 standalone |
| Sega Model 2 | ✅ Working | Model 2 Emulator |
| Sega Model 3 | ✅ Working | Supermodel standalone |
| Sony PSP | ✅ Working | PPSSPP standalone |
| Nintendo GameCube / Wii | ✅ Working | Dolphin standalone |
| Nintendo Wii U | ✅ Working | Cemu standalone |
| Pinball FX2 / FX3 | ✅ Working | Direct app launch |
| Full RetroArch stack | ✅ Working | NES/SNES/Genesis/GBA/PS1/etc. |

Cut from LoRa by design (LaunchBox direct only): Daphne/laser disc, all gun platforms (~15), Nintendo Switch (legal), Nintendo DS, Dev2.

**Key Fixes Applied:**
- **launchers.json — Hardcoded A:\\ paths removed**: All emulator exe paths now use `${AA_DRIVE_ROOT}`. Unblocked PS3, Model 2, Wii U, and Hypseus which were silently failing on W drive.
- **RetroArch adapter — PSP routing fixed**: Removed Sony PSP and Sony PSP Minis from `INSTANCE_REGISTRY`. PPSSPP standalone adapter now handles PSP correctly.
- **Dolphin adapter — GameCube/Wii fixed**: Added dolphin block to `launchers.json` pointing to `LaunchBox\Emulators\dolphin-2412-x64\Dolphin-x64\Dolphin.exe`. Adapter reads manifest first.
- **Cemu adapter — Wii U fixed**: Updated to read exe from `launchers.json` directly, bypassing broken `emulator_paths.json` first-match logic.
- **emulator_paths.json — Stale A:\\ path cleared**: One remaining `A:\LaunchBox` reference replaced with correct W drive path.
- **Launcher Agent — Model 3 / no_pipe adapters**: Updated `arcade_launcher_agent.py` to launch processes fully detached (`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`) with DEVNULL stdio. Fixed Supermodel's OpenGL startup environment.
- **Agent bypass for registered adapters**: `launcher.py` now computes `has_registered_adapter` before the adapter loop and passes `skip_agent=True`. Prevents port 9123 connection failures from blocking launches.
- **Bezel drift — Fixed permanently**: Root cause was `LaunchBox\Emulators\RetroArch\RetroArch-Controller\retroarch.cfg` with a GameCube overlay hardcoded at global level. All three RetroArch instances now have `input_overlay = ""`, `input_overlay_enable = "false"`, `config_save_on_exit = "false"`, `video_shader_preset_save_reference_enable = "false"`.
- **CRT shader — Applied globally**: `crt-easymode.slangp` applied to all three RetroArch instances (Standard, Gamepad, RetroArch-Controller). Clean scanlines on every retro platform.
- **retroarch_adapter.py — Runtime base config isolation**: Each RetroArch launch now generates a clean runtime base config with overlays stripped before applying platform override via `--appendconfig`. Prevents future bezel carryover between sessions.
- **Frontend — Gun games and dead platforms hidden**: `LORA_HIDDEN_PLATFORM_KEYS` updated to hide all gun game platforms, Nintendo Switch, Nintendo DS, Pinball (direct), Dev2.
- **PS2 library — Cleaned to 44 confirmed titles**: 44 unresolvable ROM paths removed from the GUI.

**⚠️ CRITICAL RULES FOR NEXT AGENT:**
- NEVER change `config_save_on_exit` in any RetroArch cfg — it's set to `"false"` intentionally
- Three RetroArch instances exist: Standard, Gamepad, and RetroArch-Controller (LaunchBox tree) — all three must stay in sync
- Launcher Agent runs on port 9123 — required for no_pipe adapter launches (Model 3, etc.)
- `AA_DRIVE_ROOT` must always point to `W:\Arcade Assistant Master Build`
- Launch AA ONLY from: `W:\Arcade Assistant Master Build\Arcade Assistant Local\start-aa.bat`

**Next Session Priority Order:**
1. ⚡ **Blinky Chat Interface** — 6 coherence disconnections from 04-07-2026 audit (missing LED repair route, two-API calibration problem, shared chat store, command executor, live LED context assembler, `blinky_knowledge.md` to create)
2. 🔶 **Chuck / Wizard Chat Interfaces** — `stash@{1}` exists with WIP modal work — audit before touching
3. 🔶 **Gunner** — audit first, status unknown
4. 🌱 **Doc** — untouched panel, needs knowledge pass
5. 🌱 **Sam** — 2-3 sessions, pipeline hooks confirmed wired

**PAT Warning**: "Antigravity Push v2" expires ~April 25, 2026 — rotate within 2 weeks.

---

## 2026-03-19 (Antigravity Session — Gun Platform Routing, AHK Bulk Fix, LoRa Hardening)

**Net Progress**: Fixed Pinball FX2/FX3 launch block. Built and verified the entire Gun Platform Routing system (16 platforms → Gun Build emulators). Bulk-fixed 213 AHK scripts (D:\→A:\, Sinden removal). Suppressed Sinden hardware warnings. Wired 4 Retro Shooter VID/PIDs. Removed 5 unstable platforms from LoRa GUI. Fixed PS3 AHK routing bypass bug.

**Key Wins:**
- **Pinball FX2/FX3 Unblocked**: `'pinball fx'` was incorrectly in `unsupportedKeywords` array in `LaunchBoxPanel.jsx` L416. Removed. Both platforms launch from LoRa.
- **GUN_PLATFORM_MAP (16 platforms)**: Added to `launcher.py` at L1160. Maps raw platform names (before `normalize_key()` strips "gun games") to Gun Build emulator paths via `EmulatorPaths` in `a_drive_paths.py`. Covers NES, SNES, Master System, Wii, PS2, PS3, PC, TeknoParrot, Naomi, Atomiswave, Dreamcast, Saturn, Model 2, Model 3, PCSX2.
- **AHK Wrapper Detection (dual-path)**: Two AHK intercept points in `launcher.py`:
  1. L1329 — when adapter resolves AND `gun_exe_override` fires, checks if `ApplicationPath` ends in `.ahk` → overrides to AutoHotkey
  2. L1498 — fallback block when no adapter resolves, same `.ahk` detection
  This fixed PS3 Gun Games routing `rpcs3.exe .ahk` → `AutoHotkeyU32.exe .ahk`.
- **NES Gun Core Hard-Wire**: NES Gun Games → nestopia_libretro.dll (with fceumm fallback). Mesen core not on disk.
- **Bulk AHK Fix (213 files)**: Python line-by-line parser replaced all `D:\Gun Build\` → `A:\Gun Build\` and removed Sinden Lightgun.exe startup/cleanup blocks from 210 scripts. SINGE2 scripts (13) intentionally untouched — they need Sinden. PowerShell regex approach hit catastrophic backtracking; switched to Python.
- **Sinden Suppression**: `gunner_hardware.py` — generic "No light gun devices detected" warning and USB enumeration error downgraded from `logger.warning`/`logger.error` to `logger.debug`. Sinden detection still runs, just fails silently.
- **Retro Shooter VID/PIDs**: 4 Retro Shooter entries added to `KNOWN_DEVICES` in `gunner_hardware.py` (L42-68) as PRIMARY gun type. Sinden/AimTrak/Gun4IR marked secondary.
- **LoRa GUI Exclusions**: Added `excludedPlatforms` exact-match array to `isSupportedPlatform()` in `LaunchBoxPanel.jsx`. Removed: Saturn Gun Games, Model 3 Gun Games, PS2 Gun Games, PCSX2 Gun Games, Flash Games.
- **Display Driver Forensics**: Full forensic sweep confirmed display driver failure was NOT caused by AA or emulators. Windows Event Logs and hardware state analyzed. Driver reinstall resolved the issue.

**Files Modified:**
- `frontend/src/panels/launchbox/LaunchBoxPanel.jsx` — Pinball FX unblock + excludedPlatforms array
- `backend/services/launcher.py` — GUN_PLATFORM_MAP (L1160), gun_exe_override (L1325-1340), AHK detection (L1329+L1498), NES core hard-wire
- `backend/services/gunner_hardware.py` — Sinden suppression (L214/L223), 4 Retro Shooter VID/PIDs (L42-68)
- `A:\Gun Build\Roms\**\*.ahk` (213 files) — D:\→A:\ drive letter fix, Sinden block removal

**Verified Launches:**
| Platform | Game | Result |
|----------|------|--------|
| NES Gun Games | Duck Hunt | ✅ nestopia core |
| SNES Gun Games | Battle Clash | ✅ Snes9x via AHK |
| TeknoParrot Gun Games | Action Deka | ✅ AHK |
| PS3 Gun Games | Child of Eden | ✅ AHK (fixed from rpcs3.exe) |
| Master System Gun Games | — | ✅ routed |
| Atomiswave / Dreamcast / Naomi / Wii / Model 2 | — | ✅ routed |

**⚠️ GOTCHAS FOR NEXT AGENT:**
- SINGE2 scripts (13 files in `A:\Gun Build\Roms\SINGE2\`) still reference Sinden `Lightgun.exe` on A:\. If Retro Shooter replaces Sinden entirely, these need a separate pass.
- Air Twister (PC Gun Games) crashed in 2.2s — likely a game content issue, not routing.
- Gun platform routing requires `is_gun_platform` flag, which checks for "gun" AND "games" in raw platform name.

**State of Union — What's Next:**
1. ⚡ **SINGE2 AHK scripts** — 13 files still need Sinden cleanup if Retro Shooter replaces it
2. ⚡ **Air Twister debug** — PC Gun Games crash (2.2s exit)
3. 🔶 **Live hardware validation (H1–H9)** — Carried forward
4. 🌱 **Golden drive sanitization** — Carried forward

---

## 2026-03-18 (Antigravity Session — Self-Healing System Activation, Phases 0D–0H)

**Net Progress**: Fully activated the dormant AI-powered self-healing launch system (Phase 4). Five sub-phases completed: Gemini proxy creation, proxy rewiring, live verification, PID tracking fix, crash detection fix, and remediation visibility. The system now autonomously detects game crashes (<10s exit), queries Gemini for a fix, applies JIT CLI flags, and logs everything to `remediation.jsonl`.

**Key Wins:**
- **Phase 0D — Gemini Proxy Edge Function**: Created `gemini-proxy` Supabase edge function mirroring the `elevenlabs-proxy`/`anthropic-proxy` pattern. Rewired `launch_remediation.py` to call the proxy instead of hitting the Gemini API directly. `GEMINI_API_KEY` now lives only in Supabase secrets.
- **Phase 0E — Live Verification (failed → diagnosed)**: Attempted live test with Daphne game. Discovered the system was structurally sound but PID tracking silently failed.
- **Phase 0F — PID Tracking Fix (5-break chain)**: Found 5 sequential breaks in PID propagation:
  1. `launcher.py:_launch_direct()` discarded PID from `trap_result`
  2. `game.py:LaunchResponse` had no `pid` field
  3. `launcher.py:_try_launch_method()` didn't pass PID to response
  4. `launchbox.py` relied only on unreliable `_best_effort_find_pid()`
  5. `launchbox.py` `plugin_first` fallback path had **zero PID tracking** code
  All 5 fixed. Also added `PYTHONUNBUFFERED=1` to `start_backend.ps1` — solved hidden output buffering issue.
- **Phase 0G — Crash Detection Chain**: PID tracking confirmed working but `attempt_remediation()` never fired. Root cause: wrench emoji `🔧` in `logger.info()` threw `'charmap' codec can't encode character '\U0001f527'` on Windows. The exception was silently caught. Fixed by replacing emoji with ASCII `[FIX]`.
- **Phase 0H — Remediation Visibility**: Added 13 `[GEMINI]` print statements across all code paths in `launch_remediation.py`. Created `_log_remediation_result()` function writing persistent JSONL records to `A:\.aa\logs\remediation.jsonl`. Added confidence threshold print. All JSONL writes wrapped in try/except for safety.
- **Final Smoke Test — FULL SUCCESS**: Pac-Man launched, killed at 5s. Gemini responded with `{"fix_type": "cli_flag", "fix_value": "-verbose", "confidence": 0.6}`. Fix applied. `remediation.jsonl` created with full record.
- **Phase 0 Cleanup**: Removed all 11 `[0G]` temporary diagnostic prints from `game_lifecycle.py`. Added "Self-Healing Launch System (Phase 4)" section to `README.md`. All 5 Python files pass `py_compile`.

**Files Created:**
- `supabase/functions/gemini-proxy/index.ts` — NEW (Supabase edge function)

**Files Modified:**
- `backend/services/launch_remediation.py` — Proxy rewire, emoji fix, [GEMINI] prints, JSONL logging
- `backend/services/game_lifecycle.py` — Diagnostics added then removed (net: unchanged)
- `backend/services/launcher.py` — PID propagation in MAME + Hypseus paths
- `backend/models/game.py` — `pid: Optional[int]` field on `LaunchResponse`
- `backend/routers/launchbox.py` — PID tracking in all 3 launch code paths
- `start_backend.ps1` — `PYTHONUNBUFFERED=1`
- `README.md` — Self-Healing Launch System documentation

**⚠️ GOTCHAS FOR NEXT AGENT:**
- `logger.info()` in `launch_remediation.py` and `game_lifecycle.py` is **INVISIBLE** in `backend.log`. Only `print()` with `flush=True` works. This is a Windows charmap encoding + log handler issue.
- `remediation.jsonl` is written by the NEW `launch_remediation.py`, NOT the old `remediation.py`.
- The `plugin_first` fallback path in `launchbox.py` (~L3430) is the ACTUAL path used for MAME games via LoRa — not `direct_only` or `forced_method`.
- Emoji characters in `print()`/`logger` calls will crash on Windows (charmap codec). Use ASCII only.

**State of Union — What's Next:**
1. ⚡ **Test with genuinely broken game** — Daphne/Supermodel to see real remediation in action
2. ⚡ **`DISABLE_REMEDIATION=1` env var** — Wire this kill switch into `game_lifecycle.py`
3. 🔶 **Fix logger visibility** — Configure file handler with UTF-8 encoding for `launch_remediation` logger
4. 🔶 **Remediation relaunch** — After JIT fix is applied, the system should auto-relaunch the game
5. 🌱 **Fleet-wide remediation dashboard** — Surface `remediation.jsonl` data in the Doc panel

---

## 2026-03-16 LATE (Antigravity Session — Dewey Chat & News Voice Fix)

**Net Progress**: Fixed Dewey's main chat (400/500 errors from calling anthropic-proxy directly) by migrating to Gemini. Fixed Gaming News chat echo (ref-based guard replaces slow state guard). Added TTS voice output to News Chat via `/api/voice/tts` with Dewey's voice ID. Changed News Chat mic from auto-send to push-to-talk (user reviews transcript before sending).

**Key Wins:**
- **Dewey → Gemini Migration** — Added `call_gemini()` to `SecureAIClient` on A: drive. Switched `dewey.py` chat endpoint + trivia generator from `_call_anthropic` to `_call_gemini`. Dewey now uses `gemini-proxy` edge function.
- **Anthropic Proxy Fix (Defensive)** — `anthropic-proxy` edge function v14 now extracts system messages from `messages[]` and promotes to top-level `system` param. Prevents 400s for any remaining consumers.
- **News Chat Echo Guard** — Replaced React `useState`-based `loading` check with `useRef`-based `sendingRef`. Ref guard is synchronous, so rapid-fire voice sends can't slip past.
- **News Chat TTS** — `useNewsChat.js` now fetches audio from `/api/voice/tts` after each Dewey response. Uses voice ID `t0A4EWIngExKpUqW6AWI`. Plays automatically with `isSpeaking`/`stopSpeaking` controls.
- **Push-to-Talk UX** — Removed `sendMessage(transcript)` auto-fire from mic `onresult`. Now: mic click → speech fills text box → user reviews → user clicks Send. Eliminates garbled partial speech problems.
- **Conversational Prompt** — System prompt updated to prioritize natural greetings over headline-only responses. Added "vary your language" instruction.

**⚠️ GOTCHAS FOR NEXT AGENT:**
- TTS route is mounted at `/api/voice` (NOT `/api/ai`). Full TTS path: `/api/voice/tts`. See `server.js` line 176.
- A: drive has its **own** `dewey.py` and `drive_a_ai_client.py` in `A:\Arcade Assistant Local\backend\`. These have the actual `/chat` endpoint. C: drive versions are different.

**Files Modified:**
- `A:\Arcade Assistant Local\backend\services\drive_a_ai_client.py` — `call_gemini()` method added
- `A:\Arcade Assistant Local\backend\routers\dewey.py` — Chat + trivia switched to Gemini
- `supabase/functions/anthropic-proxy/index.ts` — System message handling (v14)
- `frontend/src/panels/dewey/news/useNewsChat.js` — Echo guard, TTS, push-to-talk, prompt

**State of Union — What's Next:**
1. ⚡ **Full retest after restart** — User will restart Arcade Assistant tomorrow; verify News Chat voice + push-to-talk end-to-end
2. 🔶 **Live hardware validation (H1–H9)** — Carried forward
3. 🔶 **Device ID mismatch fix** — Carried forward
4. 🌱 **ElevenLabs key replacement** — Carried forward

---

## 2026-03-14 LATE (Antigravity Session — Doc Panel Chat & Telemetry)


**Key Wins:**
- **`docContextAssembler.js`** — NEW. Fetches live health data from `/api/local/health/*` and packages it for Doc's AI chat context. 3-tier architecture matching Chuck's pattern.
- **Diagnostic Mode Toggle** — Removed `diagPermanent: true` from `DOC_PERSONA` so Chat ↔ DIAG toggle renders properly.
- **TTS Cutoff on Drawer Close** — Panel-level `useEffect` with `prevChatOpenRef` calls `stopSpeaking()` when drawer closes. Avoids passing `isOpen`/`onClose` to sidebar (which caused CSS conflicts and double close buttons).
- **Telemetry Pipeline Verified** — `psutil 7.2.2` installed, gateway TTS endpoint confirmed (200 OK, 15KB audio), live CPU/memory readings confirmed accurate.

**Files Created:**
- `frontend/src/panels/system-health/docContextAssembler.js` — NEW
- `logs/2026-03-14.md` — NEW

**Files Modified:**
- `frontend/src/panels/system-health/SystemHealthPanel.jsx` — `DOC_PERSONA` fix, `contextAssembler` wired, TTS cutoff added

**State of Union — What's Next:**
1. ⚡ **Test Doc diagnostic mode end-to-end** — Hands-free voice interaction with live health context
2. 🔶 **Replace placeholder FPS/latency/display data** — Requires game-level hooks per emulator
3. 🔶 **Verify contextAssembler on other panels** — Ensure Gunner, Wiz, etc. also have proper context wired

---


## 2026-03-12 EVE (Antigravity Session — RAG Emulator Knowledge Pipeline)

**Net Progress**: First two emulator RAG knowledge files created and verified — Sega Model 2 and Redream (Dreamcast). RAGSlicer infrastructure built by Codex (220 lines, 7 tests, dual-directory lookup, UTF-8 BOM support). Established a repeatable cross-validation pipeline: scan codebase → receive Gem → cross-validate → synthesize tagged `.md` → verify via RAGSlicer. Pipeline proven: Model 2 took ~90min (first-of-kind, included infra build), Redream took ~4min (template reuse).

**Key Wins:**
- **RAGSlicer Infrastructure (Codex)**: `backend/services/rag_slicer.py` (220 lines) — resolves knowledge in order: `.aa/state/knowledge_base/` first, then repo `prompts/`. Exposes `get_section()` and `get_persona_slice()`. `backend/tests/test_rag_slicer.py` — 7 tests, all passing.
- **Sega Model 2 Knowledge File**: `prompts/sega_model_2.md` (130 lines, 6 tagged sections: CONTROLLER_CONFIG, GUN_CONFIG, LAUNCH_PROTOCOL, ROUTING_VOCAB, TROUBLESHOOTING, DIP_SWITCHES). Cross-validation found 4 nuances: dual exe names (EMULATOR.EXE vs emulator_multicpu.exe), gun build path separation, missing Gem details on JoyButton mapping rules, launchers.json vs emulator_paths.json inconsistency.
- **Redream Knowledge File**: `prompts/redream.md` (153 lines, 8 tagged sections: CONTROLLER_CONFIG, GUN_CONFIG, LAUNCH_PROTOCOL, ROUTING_VOCAB, SCORE_TRACKING, VOICE_VOCABULARY, LED_PROFILE, HEALTH_CHECK). Cross-validation found 5 nuances: missing Dreamcast Indies/Gun Games platforms, missing feature gates, save state hotkeys F5/F8, no pause toggle endpoint, Flycast routing boundary.
- **Pipeline Optimization**: For future emulators, Antigravity scans + validates, then hands synthesis off to Codex to preserve context window budget for more cross-validation cycles per session.

**Files Created/Modified:**
- `backend/services/rag_slicer.py` — NEW (Codex)
- `backend/tests/test_rag_slicer.py` — NEW (Codex)
- `prompts/sega_model_2.md` — NEW (Codex + Antigravity cross-validation)
- `prompts/redream.md` — NEW (Antigravity)
- `logs/2026-03-12-model2-rag.md` — NEW (local task summary)

**State of Union — What's Next (Priority Order):**
1. ⚡ **More emulator RAG files** — Pipeline proven; next candidates: MAME (highest ROI), Supermodel, PCSX2, TeknoParrot
2. ⚡ **Codex handoff optimization** — Future emulator writes delegated to Codex to keep Antigravity context lean
3. 🔶 **NotebookLM upload** — Deferred (MCP server unreliable this session). Knowledge files should be uploaded when available
4. 🔶 **Live hardware validation (H1–H9)** — Carried forward
5. 🌱 **Supabase Service Role Key + Device ID mismatch** — Carried forward

---

## 2026-03-12 PM (Antigravity Session — Emulator Audit + Dual-Build Pathing + RAG Context Map)

**Net Progress**: Full emulator registry audit (55 LaunchBox entries, 28 Gun Build folders, 13 duplicate families). Designed and tasked Codex with two foundational architectural changes: (1) Emulator Dual-Build deterministic pathing — `EmulatorPaths` class with 68 named accessors + `emulator_context.py` "Path IS the Signal" resolver, (2) RAG Context Map — `rag_slicer.py` per-emulator section slicer + Gun Wall enforcement in Chuck and Gunner prompts.

**Key Wins:**
- **Emulator Registry Audit**: Inventoried all 55 LaunchBox-registered emulators and all 28 Gun Build folders. Identified 13 duplicate families (RetroArch ×6, Dolphin ×6, MAME ×5, TeknoParrot ×4, PCSX2 ×3, Demul ×3). Flagged 3 issues: Demul/Demul Arcade identical paths, PCSX2/PCSX2-Controller same exe, "Ryujink" typo. Confirmed most duplicates are intentional (panel vs gamepad vs gun input configs).
- **Platform Mapping Analysis**: 267 total platform-to-emulator mappings analyzed. RetroArch dominates (73+56+55 platforms across 3 builds). Every classic console has 3 RetroArch builds mapped.
- **Codex Handoff #1 — Dual-Build Pathing**: `EmulatorPaths` class with `_PANEL_ROOT` and `_GUN_ROOT` trees, 40 panel/gamepad accessors + 28 gun accessors, `all_executables()` health check dict, `validate()` method. New `emulator_context.py` with `infer_input_context()` — `Gun Build\` → lightgun, `Gamepad|Joystick|Controller` → gamepad, else → arcade_panel.
- **Codex Handoff #2 — RAG Context Map**: `RAGSlicer` class for extracting persona-specific `## TAG` sections from per-emulator master markdown files. Routing table: chuck→CONTROLLER_CONFIG, gunner→GUN_CONFIG, dewey→ROUTING_VOCAB, etc. Gun Wall enforcement added to `controller_chuck.prompt` and `gunner.prompt` DIAGNOSIS sections — explicit cross-domain refusal language.
- **Protocol Clarification**: Codex does not have NotebookLM access — all future Codex handoffs omit NotebookLM steps.

**Codex Handoffs Dispatched (awaiting execution):**
1. `backend/constants/a_drive_paths.py` — Append `EmulatorPaths` class (68 accessors)
2. `backend/services/emulator_context.py` — NEW (path-based input context resolver)
3. `backend/services/rag_slicer.py` — NEW (RAG section slicer)
4. `prompts/controller_chuck.prompt` — MODIFY (Gun Wall insertion)
5. `prompts/gunner.prompt` — MODIFY (Controller Wall insertion)

**State of Union — What's Next (Priority Order):**
1. ⚡ **Codex executes Handoff #1 + #2** — 5 files, both under HITL threshold
2. ⚡ **RAG system innovation** — User has an innovative idea for the rack system architecture (next session)
3. 🔶 **Emulator knowledge files** — Build master `.md` per emulator with `## TAG` sections for the RAG slicer
4. 🔶 **Live hardware validation (H1–H9)** — Carried forward
5. 🌱 **Supabase Service Role Key + Device ID mismatch** — Carried forward

---

## 2026-03-12 (Antigravity Session — Codex Duplication-Readiness Audit)

**Net Progress**: Full Round 2 audit of Codex's duplication-readiness implementation. All 13 files verified line-by-line. 6/6 py_compile passed, 2/2 node --check passed. README updated with Duplication-Readiness Master Checklist — 18 code-complete items, 9 hardware-validation items, 4 separate-effort items. Closed 4 stale blockers in Known Issues table.

**Key Wins:**
- **13-File Audit — All Verified**: `cabinet_identity.py`, `startup_manager.py`, `system.py`, `bootstrap_local_cabinet.py`, `start-aa.bat`, `server.js`, `cabinetIdentity.js`, `prepare_golden_image.bat`, `clean_for_clone.bat`, `blinky/__init__.py`, `main.cjs`, `test_cabinet_provisioning.py`, `spa_shell.spec.js`.
- **Identity Chain Verified**: UUID generation on first boot → `.aa/device_id.txt` → `.aa/cabinet_manifest.json` → `os.environ` runtime sync. Resolution: file → manifest → env fallback, consistent across Python and Node.
- **Serve-Only Boot Verified**: `start-aa.bat` uses `%~d0` for drive auto-detect, runs `bootstrap_local_cabinet.py`, checks `frontend/dist/index.html`, no build step.
- **SPA Shell Cache-Busting Verified**: `sendSpaShell()` re-reads `index.html` per request, injects `window.AA_DEVICE_ID`, sets `no-store` + `X-AA-SPA-Build`, `express.static` uses `index: false`.
- **Golden Image Pipeline Verified**: `prepare_golden_image.bat` wipes old dist, runs clean build, extracts + verifies hash. `clean_for_clone.bat` preserves dist/node_modules/manifest, sanitizes `.env` labels.
- **Blinky Lazy Verified**: Pure `__getattr__` via `importlib.import_module` — zero hardware access at import.
- **README Duplication Master Checklist Added**: Comprehensive tracking of what's code-complete (18 items), what needs hardware validation (9 items: H1–H9), and what's separate effort (4 items: S1–S4).
- **4 Stale Blockers Closed**: Gateway stale `index.html`, blinky eager imports, Dewey News Chat, TTS echo on exit.

**Files Modified:**
- `A:\Arcade Assistant Local\README.md` — MODIFIED (header date, closed Known Issues, added Duplication-Readiness Master Checklist, appended session catalog)
- `A:\Arcade Assistant Local\ROLLING_LOG.md` — MODIFIED (new session entry)

**State of Union — What's Next (Priority Order):**
1. **H1: Clone Simulation** — Core smoke test: delete `.aa/device_id.txt` + `.aa/cabinet_manifest.json`, reboot, verify new UUID + current frontend
2. **H2–H9: Live Hardware Validation** — LoRa, Hypseus, Gamepad, F9 overlay, Wiz, Vicky, Sam, Chuck
3. **S1: Supabase Service Role Key** — Decide sanitization strategy for golden image
4. **S2: Device ID Mismatch** — Fix `.env` vs Supabase registration
5. **S3: ElevenLabs Key** — Replace placeholder

---

## 2026-03-11 (Antigravity Session — Multi-Agent Orchestration)

**Net Progress**: ScoreKeeper Sam pipeline hardened (6 fixes, 5 tests). Controller Wizard preference capture implemented (backend + frontend). Daphne/Hypseus AHK parser hardened (5 fixes, 5 tests). Minor UI cleanups (MAP CONTROLS button removal, 8BitDo Pro 2 asset replacement). Multi-agent workflow: Antigravity as Lead Architect, Claude Code for audits, Codex for implementation, GPT for pre-audit.

**Key Wins:**
- **ScoreKeeper Sam Pipeline (6 Fixes)**: AA launch tracking, crash-exit explicit `failed` outcomes, dual-exit dedup (PID + plugin can't both score), atomic file writes (temp+rename), startup cleanup for stale sessions >24h, Lua watcher fallback when hiscore fails. 5 tests pass.
- **Controller Wizard Preference Capture**: Added `GET/POST /api/local/console/gamepad/preferences` backend endpoints. Frontend auto-saves 16-button mappings + deadzone + calibration to `A:/.aa/state/controller/gamepad_preferences.json` on wizard complete. Loads saved preferences on mount for profile pre-selection. `RetroArchConfigRequest` model updated with `mappings` and `deadzone` fields.
- **Daphne/Hypseus Parser Hardening (5 Fixes)**: `.exe` fallback now works for both absolute and relative paths. Manifest + `shutil.which()` fallback for bare executable names. Comma-safe AHK `Run` command extraction. Structured parse-failure debug logging. Dead `daphne_adapter.py` stub replaced with documented re-export. 5 tests pass.
- **MAP CONTROLS Button Removed**: Removed from Controller Chuck's panel (import, state, button, overlay render — 4 clean cuts). Functionality now lives in Controller Wizard.
- **8BitDo Pro 2 Asset Replaced**: Generated correct compact rounded form factor matching real 8BitDo Ultimate shape (not Xbox-style).

**Files Created:**
- `backend/tests/test_daphne_hypseus.py` — NEW (5 test cases for AHK parser edge cases)

**Files Modified:**
- `backend/routers/console.py` — MODIFIED (+107 lines: gamepad preference save/load endpoints)
- `backend/services/adapters/direct_app_adapter.py` — MODIFIED (parser hardening: .exe fallback, manifest fallback, comma-safe extraction, structured logging)
- `backend/services/adapters/daphne_adapter.py` — MODIFIED (stub → documented re-export)
- `backend/routers/aa_launch.py` — MODIFIED (AA launch score tracking integration)
- `backend/services/game_lifecycle.py` — MODIFIED (crash-exit outcomes, Lua fallback)
- `backend/routers/game_lifecycle.py` — MODIFIED (dual-exit dedup)
- `backend/services/score_tracking.py` — MODIFIED (atomic writes, startup cleanup)
- `backend/tests/test_score_tracking.py` — MODIFIED (5 test cases)
- `frontend/src/panels/console-wizard/GamepadSetupOverlay.jsx` — MODIFIED (preference load/save wiring)
- `frontend/src/panels/controller/ControllerChuckPanel.jsx` — MODIFIED (MAP CONTROLS removal)
- `frontend/public/assets/controllers/8bitdo_pro_2.png` — MODIFIED (replacement asset)

**Open Follow-ups:**
- Device ID mismatch fix (`.env` vs Supabase)
- Golden drive sanitization script
- SVG hotspot coordinate tuning
- Live cabinet testing: Sam pipeline, Daphne/Hypseus launchers, gamepad wizard, F9/Dewey overlay

## 2026-03-08/09 | Dewey Stabilization + LaunchBox LoRa Hardening + Hypseus Migration + Panel Extraction

**Net Progress**: Dewey voice/overlay behavior stabilized. LaunchBox LoRa panel received a full code audit (8,860 lines across 4 layers), followed by a 15-item punch list â€” all 15 resolved. Panel decomposed from 2,635 lines to 1,966 lines via hook/component extraction. Hypseus migration path implemented for Daphne launchers. Build verified clean throughout.

**Key Wins:**
- **Dewey Overlay Routing**: Overlay mode now routes directly to Dewey (`/assistants?agent=dewey&mode=overlay`) instead of Home. Singleton behavior in Electron prevents duplicate instances.
- **F9 Hotkey Hardening**: Debounce + dual trigger paths (Electron global shortcut + backend hotkey WebSocket fallback). Overlay-allowed process detection expanded to include `BigBox.exe` and `LaunchBox.exe`.
- **Dewey Voice Stability**: Resolved ElevenLabs loop/replay behavior. Microphone interruption now overrides long assistant playback. Responses tuned shorter.
- **Dewey Handoff UX**: Chip handoff flow supports compact-to-fullscreen transition. Overlay close/exit control flow hardened.
- **LaunchBox LoRa Full Audit** (conducted by AI-Hub agent): Audited all 4 layers â€” `LaunchBoxPanel.jsx` (2,635 lines), `launchbox.py` router (3,978 lines, 111 functions), `launcher.py` service (1,587 lines, 3-tier fallback), `launchbox_parser.py` (660 lines). Identified 15 improvement items.
- **15-Item Punch List â€” All Complete**:
  - #1: `LaunchBoxErrorBoundary.jsx` created (39 lines, `getDerivedStateFromError` + Reload button)
  - #2: Encoding artifacts (`dY"?`) replaced with proper emoji
  - #3: Dead `mockGames` array removed (~50 lines)
  - #9: Duplicate `sendMessage`/`sendMessageWithText` merged into single `sendChatMessage(text, {speakResponse})`
  - #10: `resolveAndLaunch` double-spacing cleaned
  - #11: `isSupportedPlatform` improved â€” now rejects `pinball fx` and `flash` platforms
  - #12: Sort options expanded from 2 to 5 (Title, Year, Platform, Last Played, Most Played)
  - #13: Visual LoRa state indicator added (status pill: Ready/Listening/Thinking/Launching + lock warning + processing hint)
  - #14: `displayName` added to `ChatMessage` and `GameCard` memo components
- **Structural Extraction Pass (Items #4â€“#8)**:
  - `hooks/useVoiceRecording.js` (380 lines) â€” Web Speech API, MediaRecorder, WebSocket, VAD
  - `hooks/useLaunchLock.js` (45 lines) â€” localStorage cross-tab lock
  - `hooks/usePluginHealth.js` (61 lines) â€” Plugin health check with 30s cache
  - `components/LoraChatDrawer.jsx` (110 lines) â€” Sliding chat panel
  - `components/ShaderPreviewModal.jsx` (57 lines) â€” Shader diff viewer dialog
- **Hypseus Migration**: For Daphne/Laserdisc `.ahk` wrappers that call `daphne.exe`, backend now routes to `hypseus.exe` directly. Singe-oriented wrappers remain on AHK path. Verified: BadLands â†’ Hypseus direct, Cliff Hanger HD â†’ AHK/Singe (as intended).
- **AHK Relaunch Guard**: Cooldown guard added to prevent duplicate-script instance popups on rapid repeat launch.

**Files Created:**
- `frontend/src/panels/launchbox/LaunchBoxErrorBoundary.jsx` â€” NEW
- `frontend/src/panels/launchbox/hooks/useVoiceRecording.js` â€” NEW
- `frontend/src/panels/launchbox/hooks/useLaunchLock.js` â€” NEW
- `frontend/src/panels/launchbox/hooks/usePluginHealth.js` â€” NEW
- `frontend/src/panels/launchbox/components/LoraChatDrawer.jsx` â€” NEW
- `frontend/src/panels/launchbox/components/ShaderPreviewModal.jsx` â€” NEW

**Files Modified:**
- `frontend/src/panels/launchbox/LaunchBoxPanel.jsx` â€” MODIFIED (2,635â†’1,966 lines, all extractions wired)
- `frontend/src/panels/launchbox/launchbox.css` â€” MODIFIED (status pill + input row styles)
- `frontend/src/panels/dewey/DeweyPanel.jsx` â€” MODIFIED (voice stability, overlay routing)
- `frontend/electron/main.cjs` â€” MODIFIED (F9 hardening, singleton overlay)
- `backend/routers/hotkey.py` â€” MODIFIED (WebSocket fallback)
- `backend/services/hotkey_manager.py` â€” MODIFIED (idempotent callbacks)
- `backend/services/activity_guard.py` â€” MODIFIED (overlay lifecycle)
- `backend/routers/launchbox.py` â€” MODIFIED (Hypseus routing, AHK guard)
- `backend/services/adapters/direct_app_adapter.py` â€” MODIFIED (Hypseus migration)

**LaunchBox Panel Final Structure:**
```
launchbox/
â”œâ”€â”€ components/
â”‚   â”œâ”€â”€ LoraChatDrawer.jsx          (110 lines)
â”‚   â””â”€â”€ ShaderPreviewModal.jsx      (57 lines)
â”œâ”€â”€ hooks/
â”‚   â”œâ”€â”€ useLaunchLock.js            (45 lines)
â”‚   â”œâ”€â”€ usePluginHealth.js          (61 lines)
â”‚   â””â”€â”€ useVoiceRecording.js        (380 lines)
â”œâ”€â”€ LaunchBoxPanel.jsx              (1,966 lines â€” orchestrator)
â”œâ”€â”€ LaunchBoxErrorBoundary.jsx      (39 lines)
â”œâ”€â”€ launchbox.css                   (2,087 lines)
â””â”€â”€ ContentDisplayManager.jsx
```

**State of Union â€” What's Next (Priority Order):**
1. âš¡ **Validate F9 overlay** â€” End-to-end test inside true Big Box fullscreen on basement hardware
2. âš¡ **Hypseus smoke test** â€” Confirm Daphne titles launch correctly via Hypseus on real hardware
3. ðŸ”¶ **LED Blinky depth pass** â€” Primary queued panel work
4. ðŸ”¶ **Gunner logic audit** â€” Pending after LED Blinky
5. ðŸ”¶ **Doc telemetry expansion** â€” System health panel enrichment
6. ðŸŒ± **LaunchBox LoRa visual polish** â€” Icon/readability consistency pass

---

## 2026-03-07 | Dewey Chat Sidebar + Gateway AI Fallback + Jules Integration

**Net Progress**: Integrated Jules's Dewey fixes (chat button removal + TTS echo cleanup). Discovered persistent browser caching issue that prevents new frontend builds from loading. Rebuilt a complete News Chat sidebar stack (Gemini-backed). Made gateway `/api/ai/chat` lenient for legacy clients and added auto-fallback from Claude to Gemini when provider fails at runtime.

**Key Wins:**
- **Jules Cherry-pick** (`6a93660` â†’ `817e8e7`): Merged Jules's "Remove Chat with Dewey button and fix TTS echo on exit" commit. Deleted 3 dead files (`NewsChatSidebar.jsx`, `.css`, `useNewsChat.js`), cleaned `DeweyPanel.jsx` and `GamingNews.css`. 894 lines removed.
- **News Chat Sidebar V2** (`6a303ec`): Rebuilt complete chat stack â€” `useNewsChat.js` (Gemini via `/api/ai/chat`, Web Speech API mic, auto-send), `NewsChatSidebar.jsx` (slide-in panel), `NewsChatSidebar.css` (dark theme + indigo accents). Wired into `GamingNews.jsx` with `chatOpen` state and `.chat-btn` CSS.
- **Gateway API Shim** (`a3a44f9`): Made `/api/ai/chat` in `gateway/routes/ai.js` lenient â€” `x-scope` header optional, accepts both `message` (string) and `messages[]` (array), picks up `systemPrompt` as fallback for `system`.
- **Auto-Fallback to Gemini** (`22e7f09`): Provider dispatch now wrapped in try-catch. If Claude/GPT fails at runtime (e.g., model 404), auto-retries with Gemini. This protects every panel's chat from provider outages.
- **Field Name Fix** (`5a97547`): News chat system prompt fixed from `.description` to `.summary` (matching actual headline object shape from RSS feeds).

**Struggles & Unresolved:**
- **ðŸ”´ Gateway Serves Stale `index.html`**: The #1 blocker. Despite deleting `dist/`, rebuilding with new content hashes, and restarting the gateway, the browser loads OLD JavaScript bundles. The disk has `index-528fec9f.js` â†’ `Assistants-81fd34ca.js` but the browser loads `index-77e85326.js` â†’ `Assistants-4d0f57a2.js`. Clearing browser cache, incognito, and different browsers did NOT fix it. Root cause is likely in how `express.static()` serves or caches `index.html` in `gateway/server.js`.
- **Cached Claude Request**: The old cached frontend sends `provider: "claude"` but `claude-3-5-haiku-20241022` returns 404. Gateway fallback to Gemini was added but could not be verified end-to-end due to the stale `index.html` issue above.

**Files Created:**
- `frontend/src/panels/dewey/news/useNewsChat.js` â€” NEW (Gemini chat hook + Web Speech mic)
- `frontend/src/panels/dewey/news/NewsChatSidebar.jsx` â€” NEW (slide-in chat panel)
- `frontend/src/panels/dewey/news/NewsChatSidebar.css` â€” NEW (dark theme styling)

**Files Modified:**
- `gateway/routes/ai.js` â€” MODIFIED (lenient params, auto-fallback to Gemini)
- `frontend/src/panels/dewey/news/GamingNews.jsx` â€” MODIFIED (chat button + sidebar wiring)
- `frontend/src/panels/dewey/news/GamingNews.css` â€” MODIFIED (`.chat-btn` styles)
- `frontend/src/panels/dewey/DeweyPanel.jsx` â€” MODIFIED (TTS cleanup on unmount via Jules)

**Commits**: `817e8e7` (Jules cherry-pick) â†’ `6a303ec` (news chat V2) â†’ `6171861` (API fix + mic) â†’ `5a97547` (.summary fix) â†’ `a3a44f9` (lenient API) â†’ `22e7f09` (Gemini fallback)

**State of Union â€” What's Next (Priority Order):**
1. ðŸ”´ **Gateway stale `index.html` investigation** â€” Inspect `express.static()` config in `gateway/server.js`. Determine why the gateway serves an old `index.html` after rebuild + restart. This blocks ALL frontend changes.
2. ðŸŸ¡ **Verify TTS echo fix** â€” Once browser loads new code, confirm `speechSynthesis.cancel()` fires on Dewey unmount.
3. ðŸŸ¡ **Verify News Chat works end-to-end** â€” Once new JS loads, confirm Gemini responds with headline context.
4. ðŸŸ¡ **Verify Gemini auto-fallback** â€” Test that old cached clients get real responses via the fallback path.

---

**Net Progress**: Built comprehensive Controller Chuck RAG knowledge base (`chuck_knowledge.md` â†’ 770+ lines, 16 sections). Integrated a "Gem Second Opinion" from a parallel AI model for deeper troubleshooting protocols. Closed three V1 blockers: B2 (HttpBridge outbound), B4 (Voice Hardware Unlock), B5 (Genre LED Logic). Built Console Wizard RAG knowledge base (`wiz_knowledge.md` â†’ 500+ lines, 16 sections) focused on customer-facing "wow" fix flows. Enhanced Wiz prompt with Rapid Fix Protocol and customer-first rules. Built **LED Priority Arbiter** â€” circuit breaker preventing LED state conflicts between game animations and Vicky voice commands.

**Key Wins:**
- **`chuck_knowledge.md`** (770+ lines, 16 sections): Full RAG knowledge base covering Sacred Numbering, emulator config paths, encoder boards (I-PAC/Brook/Xin-Mo/Zero Delay), input testing tools, recovery procedures, and the Golden Drive onboarding workflow.
- **Gem Integration â€” Cross-Emulator Translation Table**: Full Button 1-8 mapping across MAME (`P1_BUTTON1-8`), RetroArch (`B/A/Y/X/L1/R1/L2/R2`), and TeknoParrot (`<ButtonX>` XML tags).
- **Gem Integration â€” Puppeteer Protocol**: Complete spec: 4 commands (`QUIT_KEY`, `SAVE_STATE`, `LOAD_STATE`, `RUNAHEAD_TOGGLE`), safe shutdown sequence (`SAVE_STATE â†’ 100ms â†’ QUIT_KEY`), zombie recovery (force-kill PID + NVRAM restore from `.aa/backups/`).
- **Gem Integration â€” Field Failure Scenarios ("2 AM Calls")**: 5 real-world failure scenarios with step-by-step resolutions: buttons swapped, Vicky silent, scores not updating, lights stuck, black screen.
- **Gem Integration â€” Hardware Failure Modes**: LED HID pipe simultaneity, INI vs XML corruption, encoder mode shifting, Vulkan/GL shader cross-loading.
- **LED Priority Arbiter** (`led_priority_arbiter.py` â€” 250 lines): Circuit breaker pattern with priority stack (VOICE > GAME > ATTRACT > IDLE). Vicky always overrides game animations, resumes on release. Includes 300ms scroll throttle to prevent HID buffer overflow during rapid LaunchBox browsing. Wired into `game_lifecycle.py` (claim/release on game start/stop) and `voice/service.py` (claim/release around LED writes).
- **B2 Fix (`HttpBridge.cs`)**: Added `NotifyBackendGameStart()` â€” fire-and-forget POST to `localhost:8000/api/game/start` after `PlayGame()`. Bridge now talks outbound.
- **B4 Fix (`voice/service.py`)**: Codebase was 90% done already (real HID calls, DI wiring in `voice.py` router). Added `_sync_led_state()` â€” mirrors LED state to Supabase `led_states` table for fleet visibility.
- **B5 Fix (`game_lifecycle.py`)**: Added `GENRE_ANIMATION_MAP` â€” 8 distinct LEDBlinky animation codes per genre (Fighting=strobe, Racing=chase, Shooter=pulse, etc.) + `get_animation_for_game(tags)` function.

**Files Created/Modified:**
- `prompts/chuck_knowledge.md` â€” MODIFIED (770+ lines, 16 sections, Gem integration)
- `prompts/wiz_knowledge.md` â€” NEW (500+ lines, 16 sections, customer-facing wow flows)
- `prompts/controller_wizard.prompt` â€” MODIFIED (customer-first rules, Rapid Fix Protocol)
- `frontend/src/panels/console-wizard/wizContextAssembler.js` â€” MODIFIED (Chuck sync status, expanded actions)
- `frontend/src/panels/console-wizard/wizChips.js` â€” MODIFIED (6 chips: Fix My Buttons, Sync from Chuck, etc.)
- `plugin/src/Bridge/HttpBridge.cs` â€” MODIFIED (B2: outbound POST + HttpClient)
- `backend/services/game_lifecycle.py` â€” MODIFIED (B5: GENRE_ANIMATION_MAP)
- `backend/services/voice/service.py` â€” MODIFIED (B4: _sync_led_state to Supabase)

**Blocker Scorecard:**
- B2 (HttpBridge outbound POST) â†’ âœ… DONE
- B4 (Voice Hardware Unlock) â†’ âœ… DONE
- B5 (Genre LED Animation Map) â†’ âœ… DONE

**State of Union â€” What's Next (Priority Order):**
1. âš¡ **Console Wizard panel** â€” Next session target
2. âš¡ **LED Blinky news** â€” User has new info to share
3. ðŸ”¶ **B6/B7 Wake Word & TTS Dropping** â€” Voice panel fixes
4. ðŸ”¶ **Handoff Protocol URL standard** â€” Inter-panel communication
5. ðŸŒ± **F9 Overlay Z-Index** â€” Electron `setAlwaysOnTop`
6. ðŸŒ± **Genre differentiation codes** â€” Wire `GENRE_ANIMATION_MAP` into `game_lifecycle` pipeline

### ðŸ§  AGENT NOTES: Panel Chat Sidebar Blueprint (The Proven Recipe)

**This is the canonical pattern for adding a perfect chat window to ANY panel, including Diagnosis Mode. Follow this exactly â€” it is battle-tested on Chuck, Wiz, Vicky, Blinky, Gunner, and Doc.**

#### Step 1 â€” Persona Config Object (in the panel's JSX file)
```js
const PERSONA = {
  id: 'chuck',           // matches backend persona routing
  name: 'Controller Chuck',
  accent: '#FBBF24',     // CSS accent color (amber/green/purple/cyan/red/orange)
  glow: 'rgba(251,191,36,0.3)',
  icon: 'ðŸ•¹ï¸',
  voiceProfile: 'chuck', // maps to CHUCK_VOICE_ID in .env â†’ TTS router
};
```

#### Step 2 â€” Layout Wrapper (panel JSX)
Wrap the panel's main content + sidebar in a flex container:
```jsx
<div className="eb-layout">
  <div className="panel-main-content">...</div>
  <EngineeringBaySidebar persona={PERSONA} contextAssembler={assembler} />
</div>
```
CSS: `.eb-layout { display: flex; height: 100vh; }` â€” panel fills left, sidebar sticks right.

#### Step 3 â€” Context Assembler (new file: `{persona}ContextAssembler.js`)
Parallel-fetches real hardware data for the AI. Must stay **under 1500 tokens**. Three tiers:
- **Tier 1 (always)**: timestamp, hardware status, active session
- **Tier 2 (conditional)**: active profile, current mapping, error states
- **Tier 3 (static)**: domain rules, sacred laws, available tools

#### Step 4 â€” Suggestion Chips (new file: `{persona}Chips.js`)
Array of 4-6 pre-built prompts specific to the persona's domain. Each chip pre-fills and auto-sends.

#### Step 5 â€” Backend Prompt File (`prompts/{persona}.prompt`)
Split with `---DIAGNOSIS---` delimiter:
- **Top half** = Chat Mode (read-only, conversational, suggests escalation)
- **Bottom half** = Diagnosis Mode (config-writing, action blocks, scope-locked)
Exception: Doc is always in diagnosis mode (no delimiter needed).

#### Step 6 â€” Backend AI Service (`services/{persona}/ai.py` or shared `engineering_bay/ai.py`)
- `_resolve_prompt()` reads `isDiagnosisMode` from `extra_context`
- Splits prompt on `---DIAGNOSIS---`, caches both variants
- Uses Gemini 2.5 Flash via `gemini-proxy` edge function

#### Step 7 â€” Shared Components (already built in `panels/_kit/`)
These are **done** â€” just import them:
| Component | File | What it does |
|-----------|------|-------------|
| `EngineeringBaySidebar` | `_kit/EngineeringBaySidebar.jsx` | The entire sidebar: KITT scanner, chat, mic, chips, diagnosis toggle |
| `DiagnosisToggle` | `controller/DiagnosisToggle.jsx` | Amber pill toggle |
| `ContextChips` | `controller/ContextChips.jsx` | Horizontal scrollable chip bar |
| `MicButton` | `controller/MicButton.jsx` | Push-to-talk with Web Speech API |
| `ExecutionCard` | `controller/ExecutionCard.jsx` | `[EXECUTE] [CANCEL]` gate for config writes |
| `useDiagnosisMode` | `hooks/useDiagnosisMode.js` | Toggle lifecycle, TTS greeting, 5-min timeout, context refresh |

#### Persona Color Palette (locked)
| Persona | Accent | CSS var |
|---------|--------|---------|
| Chuck | `#FBBF24` (amber) | `--eb-accent` |
| Wiz | `#22C55E` (green) | `--eb-accent` |
| Vicky | `#A855F7` (purple) | `--eb-accent` |
| Blinky | `#06B6D4` (cyan) | `--eb-accent` |
| Gunner | `#EF4444` (red) | `--eb-accent` |
| Doc | `#F97316` (orange) | `--eb-accent` |

#### DI Wiring (already done in `routers/voice.py` â€” follow this pattern)
```python
def get_voice_service() -> VoiceService:
    from ..services.led_hardware import LEDHardwareService
    led_hw = LEDHardwareService()  # Singleton
    supabase = get_supabase_client()  # Optional
    return VoiceService(led_service=led_hw, supabase_client=supabase)
```

#### TL;DR â€” To add chat + diagnosis to a NEW panel:
1. Create `PERSONA` config object in the panel JSX
2. Wrap in `eb-layout` flex container
3. Import `<EngineeringBaySidebar persona={PERSONA} />`
4. Write `{persona}ContextAssembler.js` (1500 token budget)
5. Write `{persona}Chips.js` (4-6 domain prompts)
6. Write/split `prompts/{persona}.prompt` with `---DIAGNOSIS---`
7. Done. ~50 lines of new code per panel.

---

## 2026-03-04 | Prompt Fix + Voice IDs + TTS Streaming + Jules Workflow Launch

**Net Progress**: Found and fixed the root cause of all 9 personas giving generic responses (double path mismatch in prompt loading). Upgraded to Gemini 2.5 Flash. Configured distinct ElevenLabs voices for all 9 personas. Optimized TTS pipeline with streaming audio. Created V1 Master Execution Plan (10-day sprint). Launched Jules overnight workflow with dedicated repo `Arcade-Assistant-0304-2026`.

**Key Wins:**
- **Prompt Path Fix (Root Cause)**: `AA_DRIVE_ROOT=A:\` resolved to `A:\prompts\` instead of `A:\Arcade Assistant Local\prompts\`. Also `chuck` â†’ `chuck.prompt` but file is `controller_chuck.prompt`. Both fixed via project-relative path + filename mapping.
- **Gemini 2.5 Flash**: Upgraded from 2.0 Flash for better instruction following (configurable via `GEMINI_MODEL` env var).
- **Voice IDs**: Chuck=Bill, Vicky=Rachel, Gunner=Arnold, Doc=Adam, Sam=Callum â€” all in `.env` + TTS router.
- **TTS Streaming**: Backend `StreamingResponse` + frontend `oncanplay` â€” audio plays as data arrives.
- **Jules Repo**: `Arcade-Assistant-0304-2026` created as clean dev repo. Jules completed 7 overnight tasks:
  1. Solid sidebar backgrounds + per-persona accent colors
  2. Scrubbed mojibake from ScoreKeeperPanel
  3. Scrubbed mojibake from VickyVoicePanel + fixed player ordering
  4. Removed hardcoded mock data from Gunner
  5. Fixed Wiz sidebar drawer retraction
  6. Blinky identity: purple accent + solid bg
  7. Gunner theme: purple accent + solid bg

**Commits**: `827c99c` â†’ `d782ea7` â†’ `1d51a0f` â†’ `6904e70` â†’ `144f7c0` (us) | `6227ba4` (Jules)

**Next Session (Day 2)**: ScoreKeeper Sam backend â€” validation, async file watchers, Pydantic score models, WebSocket auto-commentary.

## 2026-03-03 | Sidebar Standardization + TTS Pipeline + Gemini Migration

**Net Progress**: Major multi-agent session with Gemini (architect) + Claude Code (executor). Standardized all chat sidebars to shared `EngineeringBaySidebar` component, fixed Controller Chuck layout, rewired Engineering Bay AI from Anthropic to Gemini, and built a brand-new TTS router bridging frontend to ElevenLabs via Supabase edge function.

**Key Wins:**
- **Sidebar Standardization (Tasks 01â€“05 via Claude Code)**:
  - Task 01: Click-toggle mic fix in `EngineeringBaySidebar.jsx` (replaced push-to-talk)
  - Task 02: Controller Chuck â€” replaced `ChuckSidebar.jsx` with `<EngineeringBaySidebar persona={CHUCK_PERSONA} />`
  - Task 03: Console Wizard â€” replaced custom sidebar with `<EngineeringBaySidebar persona={WIZ_PERSONA} />`
  - Task 04: Gunner â€” replaced custom sidebar with `<EngineeringBaySidebar persona={GUNNER_PERSONA} />`
  - Task 05: Vicky Voice â€” replaced inline sidebar JSX with `<EngineeringBaySidebar persona={VICKY_PERSONA} />`
  - Each persona config includes `voiceProfile` for correct TTS routing
- **Chuck Layout Fix**: Found root cause of off-center player cards â€” `chuck-layout.css` was only imported in orphaned `ChuckSidebar.jsx`, never in `ControllerChuckPanel.jsx`. Added missing import. Also removed 180px height caps on player cards and switched rows to `flex: 1` to fill viewport.
- **Gemini AI Migration**: Rewrote `backend/services/engineering_bay/ai.py` from Anthropic SDK to Gemini REST API via httpx. Uses `GOOGLE_API_KEY` env var, `gemini-2.0-flash` model, `system_instruction` for persona prompts. Added `chuck` and `wiz` to `VALID_PERSONAS` in both router and AI service.
- **TTS Router** (`backend/routers/tts.py` â€” **NEW**): Built the missing `/api/voice/tts` endpoint that the frontend `speak()` function calls. Maps voice profiles to ElevenLabs voice IDs (reads from `.env` vars: `DEWEY_VOICE_ID`, `BLINKY_VOICE_ID`, etc.). Routes through Supabase edge function `elevenlabs-proxy`. Uses `eleven_turbo_v2` model + `optimize_streaming_latency: 3` for faster response.
- **ElevenLabs Payment Fix**: Identified 401 `payment_issue` as root cause of robot voice fallback. User resolved payment; TTS now works.

**Files Created:**
- `backend/routers/tts.py` â€” NEW (TTS router, ElevenLabs via Supabase proxy)

**Files Modified:**
- `backend/services/engineering_bay/ai.py` â€” Rewritten (Anthropic â†’ Gemini REST API)
- `backend/routers/engineering_bay.py` â€” Added chuck, wiz to VALID_PERSONAS
- `backend/app.py` â€” Added tts_router import + registration
- `frontend/src/panels/controller/ControllerChuckPanel.jsx` â€” Added missing `chuck-layout.css` import, CHUCK_PERSONA voiceProfile
- `frontend/src/panels/controller/controller-chuck.css` â€” Removed 180px card caps, flex:1 rows
- `frontend/src/panels/controller/chuck-layout.css` â€” Centering + padding adjustments  
- `frontend/src/panels/_kit/EngineeringBaySidebar.jsx` â€” TTS voice_profile routing
- `frontend/src/panels/console-wizard/ConsoleWizardPanel.jsx` â€” WIZ_PERSONA voiceProfile
- `frontend/src/components/gunner/GunnerPanel.jsx` â€” GUNNER_PERSONA voiceProfile
- `frontend/src/panels/voice/VoicePanel.jsx` â€” VICKY_PERSONA voiceProfile
- `frontend/src/components/led-blinky/LEDBlinkyPanelNew.jsx` â€” BLINKY_PERSONA voiceProfile

**Commits**: `32eab74` layout import fix | `d151af5` persona registration | `a35b76b` Gemini rewrite | `ca5d64b` TTS router | `8929df5` env voice IDs | `da6df1c` turbo model

**State of Union â€” What's Next (Priority Order):**
1. âš¡ **Chuck Voice ID** â€” Need to find/assign the correct ElevenLabs voice ID for Controller Chuck (currently using default Rachel voice). Add `CHUCK_VOICE_ID=<id>` to `.env`.
2. âš¡ **Remaining Voice IDs** â€” Vicky, Gunner, Doc, Sam all using default voice. Need custom voice IDs in `.env`.
3. ðŸ”¶ **Supabase Chat History** â€” Frontend warns `VITE_SUPABASE_URL` missing; `.env` has it but Vite needs it at build time.
4. ðŸŒ± **contextAssembler data feeds** â€” Wire real hardware data into each panel's EB sidebar.
5. ðŸŒ± **ElevenLabs payment monitoring** â€” Consider auto-renew or payment alert to prevent future TTS outages.

---

**Net Progress**: Built the full Engineering Bay sidebar system end-to-end. Generic `EngineeringBaySidebar` component created, unified Claude AI backend, 4 new persona prompts, sticky sidebar applied to all remaining panels (Vicky, Doc, Blinky, Gunner). Build: âœ… 2.94s, 254 modules, 0 errors.

**Key Wins:**
- **`EngineeringBaySidebar.jsx/.css`** (NEW in `panels/_kit/`): Generic sidebar component â€” one component serves all 4 remaining Engineering Bay panels. Colors driven by `--eb-accent` / `--eb-glow` CSS vars per persona. Always-on ambient KITT scanner, Diagnosis toggle, ExecutionCard, ContextChips, MicButton all wired in. Accepts `persona` config prop + optional `contextAssembler`.
- **`POST /api/local/engineering-bay/chat`** (NEW): Unified AI endpoint in `backend/routers/engineering_bay.py`. Accepts `persona` param â€” routes to correct prompt variant automatically. Registered in `backend/app.py`.
- **`backend/services/engineering_bay/ai.py`** (NEW): Unified AI service. Loads per-persona prompt files, splits on `---DIAGNOSIS---`, caches both variants. Doc is always-diagnosis (no delimiter needed).
- **4 Persona Prompts** (NEW): `prompts/vicky.prompt` (purple, TTS domain), `prompts/blinky.prompt` (cyan, LED domain), `prompts/gunner.prompt` (red, light gun domain), `prompts/doc.prompt` (orange, always-SYS, medical persona).
- **VoicePanel.jsx**: Vicky chat converted from hidden slide-out drawer â†’ permanent sticky sidebar via `eb-layout` flex wrapper. Purple `#A855F7` accent.
- **SystemHealthPanel.jsx**: Doc chat converted from hidden slide-out drawer â†’ permanent sticky sidebar. Orange `#F97316` accent. SYS pill always active.
- **LEDBlinkyPanelNew.jsx**: `eb-layout` wrapper added, `<EngineeringBaySidebar persona={BLINKY_PERSONA} />` inserted on the right. Cyan `#06B6D4` accent.
- **GunnerPanel.jsx**: `align-items: flex-start` + sticky inline styles applied to `gunner-content` and `GunnerChatSidebar`. Existing sidebar preserved.
- **WizSidebar.jsx/.css**: Ambient KITT scanner, sticky 100vh, `useDiagnosisMode` import fix.
- **chuck-sidebar.css**: Sticky 100vh applied (matches WIZ layout).

**Files Created:**
- `frontend/src/panels/_kit/EngineeringBaySidebar.jsx` â€” NEW
- `frontend/src/panels/_kit/EngineeringBaySidebar.css` â€” NEW
- `backend/routers/engineering_bay.py` â€” NEW
- `backend/services/engineering_bay/ai.py` â€” NEW
- `backend/services/engineering_bay/__init__.py` â€” NEW
- `prompts/vicky.prompt` â€” NEW
- `prompts/blinky.prompt` â€” NEW
- `prompts/gunner.prompt` â€” NEW
- `prompts/doc.prompt` â€” NEW

**Files Modified:**
- `backend/app.py` â€” +engineering_bay import + include_router
- `frontend/src/panels/voice/VoicePanel.jsx` â€” sticky sidebar
- `frontend/src/panels/system-health/SystemHealthPanel.jsx` â€” sticky sidebar
- `frontend/src/components/led-blinky/LEDBlinkyPanelNew.jsx` â€” eb-layout + EB sidebar
- `frontend/src/components/gunner/GunnerPanel.jsx` â€” sticky inline
- `frontend/src/panels/console-wizard/WizSidebar.jsx/.css` â€” ambient scanner, bug fixes
- `frontend/src/panels/controller/chuck-sidebar.css` â€” sticky 100vh

**State of Union â€” What's Next (Priority Order):**
1. âš¡ **`contextAssembler` data feeds** â€” Wire real hardware data into each panel's EB sidebar so AI can see actual cabinet state. This is the highest-ROI move (Doc gets live CPU/temps, Blinky gets LED controller list, Gunner gets gun enumeration, Vicky gets audio devices).
2. âš¡ **Blinky chat consolidation** â€” Remove footer chat bar + drawer from `LEDBlinkyPanelNew.jsx`. Migrate Gemini native LED tool calls into EB sidebar's `contextAssembler` pipeline so the sidebar CAN execute LED commands.
3. ðŸŒ± **Vicky intent routing** â€” Vicky hears "set buttons red" â†’ routes to Blinky AI via `forwardTranscript` extension.
4. ðŸŒ± **Diagnosis Mode hardware snapshot** â€” Toggle diagnosis mode triggers a fresh hardware snapshot injected as context.
5. ðŸŒ± **ScoreKeeper Sam session loop** â€” Vicky â†’ game start â†’ Sam records.

---

## 2026-03-02 (PM2) | Console Wizard WIZ Sidebar V1 Complete

**Net Progress**: Built Console Wizard WIZ sidebar end-to-end â€” new backend AI service, chat endpoint, green KITT scanner, diagnosis mode with emulator context assembler. **All 6 Engineering Bay Stitch designs complete.** Chuck KITT scanner upgraded to match WIZ intensity. Build: âœ… 2.85s, 0 errors. Git: `981fc59`.

**Key Wins:**
- **`backend/services/wiz/ai.py`** (NEW): Full Wiz AI service, mirrors chuck/ai.py. Hot-swaps `controller_wizard.prompt` on `---DIAGNOSIS---` delimiter. Injects emulator health + controller context. Caches both variants.
- **`POST /api/local/console_wizard/chat`**: New endpoint in `console_wizard.py`. Passes `isDiagnosisMode` flag + runtime context to AI service.
- **`controller_wizard.prompt`**: Split with `---DIAGNOSIS---`. Diagnosis mode now covers all emulator configs (RetroArch, Dolphin, PCSX2, TeknoParrot) + action block format for config fixes.
- **`WizSidebar.jsx/.css`**: Green neon #22C55E chat panel, `SCANNING...` KITT orb, Diagnosis toggle, ExecutionCard wired, action block parser for emulator config fixes.
- **`wizContextAssembler.js`**: Parallel-fetches emulator health + controller list for AI context (< 1500 tokens).
- **`ConsoleWizardPanel.jsx`**: Wired in WizSidebar via `wiz-layout` flex wrapper.
- **Stitch Designs** (project `8940180023178032848`): All 6 Engineering Bay sidebars done â€” CHUCK (amber), WIZ (green), VICKY (purple), BLINKY (cyan), GUNNER (red), DOC (orange).

**Next Steps:**
1. Implement VICKY sidebar (purple #A855F7, voice/TTS domain)
2. Implement BLINKY sidebar (cyan #06B6D4, LED lighting domain)
3. Implement GUNNER sidebar (red #EF4444, light gun domain)
4. Implement DOC sidebar (orange #F97316, always-on SYS pill)

---

## 2026-03-02 (PM) | V1 Guardrails Constitution + Chuck Sidebar Polish Complete

**Net Progress**: Established the canonical **Diagnosis Mode Guardrails Constitution** for all 9 Arcade Assistant personas. Implemented all V1 safety rails for Controller Chuck (ExecutionCard, dual prompt, timeout auto-revert, KITT scanner). Designed Chuck sidebar GUI in Stitch. Build: âœ… 2.93s, 0 errors.

**Key Wins:**
- **Guardrails Constitution** (`diagnosis_mode_guardrails.md`): Canonical spec for Chat vs Diagnosis Mode across all 9 panels. Defines two-tier architecture (Front-of-House = Chat only; Engineering Bay = amber pill). Memory never wiped on toggle â€” only permissions + system prompt swap. UI Execution Card is law for all writes. 5-min idle â†’ full auto-revert (not soft-lock). Doc is System Overlord â€” only agent allowed to auto-trigger and cross panel boundaries.
- **Dual System Prompt** (`prompts/controller_chuck.prompt`): Split with `---DIAGNOSIS---` delimiter. Chat prompt gets read-only + escalation suggestion. Diagnosis prompt gets scope lock, 50/50 rule, action block format, Sacred Button Law reminder.
- **`useDiagnosisMode` Timeout Fix**: 5-min idle now fully exits Diagnosis Mode (no soft-lock). Fires `onTimeout` callback so ChuckSidebar appends a system message. `resumeFromSoftLock` removed entirely.
- **UI Execution Card** (`ExecutionCard.jsx + .css`): New V1 safety gate. Renders amber `[EXECUTE] [CANCEL]` card for every proposed write. Pulsing amber glow during commit. Error surfaces in-card. No write ever commits without a physical EXECUTE tap.
- **Action Block Parser** (`ChuckSidebar.jsx`): Detects ` ```action {...}``` ` blocks in AI replies. Strips code block, renders ExecutionCard. EXECUTE â†’ `POST /api/profiles/mapping-override` with `confirmed_by='user'`. CANCEL â†’ system message.
- **Backend Prompt Hot-Swap** (`services/chuck/ai.py`): `_resolve_prompt` reads `isDiagnosisMode` from `extra_context`. Splits prompt on `---DIAGNOSIS---` delimiter, caches both variants independently. Zero disk re-reads after first load.
- **KITT Scanner** (`chuck-sidebar.css`): Amber orb sweeps left-to-right across dark track â€” replaces generic dot-bounce as Chuck's signature loading animation. Amber bumped to `#FBBF24` (brighter, not murky). All color values unified to `--chuck-amber` CSS variable.
- **Stitch Design**: Created "Chuck AI Sidebar â€” Diagnosis Mode" project (ID: `8940180023178032848`). V1 design: header with DIAG pill + joystick icon, chat bubbles, ExecutionCard UI, context chips, KITT scanner bar, amber input row.
- **Persona Color System**: Defined 6-color palette for Engineering Bay: Chuck=Amber, Blinky=Cyan, Wiz=Green, Vicky=Purple, Gunner=Red, Doc=Orange. Single CSS variable swap per panel.

**Files Modified:**
- `prompts/controller_chuck.prompt` â€” MODIFIED (dual prompt)
- `frontend/src/hooks/useDiagnosisMode.js` â€” MODIFIED (timeout auto-revert, onTimeout)
- `frontend/src/panels/controller/ExecutionCard.jsx` â€” NEW
- `frontend/src/panels/controller/ExecutionCard.css` â€” NEW
- `frontend/src/panels/controller/ChuckSidebar.jsx` â€” MODIFIED (KITT scanner, joystick icon, execute/cancel, softLocked removed)
- `frontend/src/panels/controller/chuck-sidebar.css` â€” MODIFIED (brighter amber, KITT scanner, joystick icon, CSS var unification)
- `backend/services/chuck/ai.py` â€” MODIFIED (_resolve_prompt hot-swaps on isDiagnosisMode)

**Next**: Console Wizard GUI (Stitch first â†’ then implementation). All V1 patterns inherited from Chuck with `#22C55E` green accent.

---

## 2026-03-02 | Diagnosis Mode â€” Phase 1 Implementation Complete (Frontend + Backend)
**Net Progress**: Full Phase 1 implementation of **Diagnosis Mode** for Controller Chuck. 14 files written/modified across frontend and backend. Python syntax check: âœ… 0 errors. File presence check: 9/9 frontend files confirmed on disk.


**Key Wins:**
- **`useDiagnosisMode` Hook** (`hooks/useDiagnosisMode.js`): Shared state manager for toggle lifecycle, contextual greeting (from last 8 messages + hardware state), TTS entry/exit, periodic 30s context refresh, 5-min soft-lock inactivity timeout, and graceful cleanup on unmount. Any future specialist panel registers its own `contextAssembler` and gets Diagnosis Mode for ~50 lines.
- **Chuck Context Assembler** (`chuckContextAssembler.js`): 3-tier context payload fetched on entry and every 30s. Tier 1: always (timestamp, hardware status, session). Tier 2: conditional (active mapping summary, profile name). Tier 3: static (sacred button law, write targets, AI tool availability). Stays under 1500 tokens. Chuck's world only â€” no cross-panel bleed.
- **Chuck Chips** (`chuckChips.js`): 6 suggestion chips (What's my pin status?, Remap a button, Fix pin conflict, Check wiring, Test inputs, Run diagnostics) â€” each pre-fills and sends a prompt.
- **UI Components**: `DiagnosisToggle.jsx/.css` (amber pill with animated thumb + pulse), `ContextChips.jsx/.css` (horizontal scroll amber chip bar with edge fades), `MicButton.jsx/.css` (push-to-talk, Web Speech API, 0.7 confidence threshold, red hot-state + ripple rings).
- **ChuckSidebar** (`ChuckSidebar.jsx` + `chuck-sidebar.css` + `chuck-layout.css`): Full chat panel assembling all components. Amber left-border pulse in Diagnosis Mode. Context injected into every AI call. Soft-lock overlay. PTT auto-stops TTS to prevent feedback.
- **`ControllerBridge`** (`services/controller_bridge.py`): GPIO merge authority (Q4/Q7). `propose_override()` returns non-destructive diff. `commit_override()` is 5-step atomic (validate stale â†’ backup â†’ write â†’ metadata â†’ return). `rollback()` restores from timestamped backup. `validate_sacred_law()` hard-blocks sacred-number deviations. 4 conflict types: `pin_collision`, `player_boundary`, `sacred_law_deviation`, `orphaned_key`.
- **`POST /api/profiles/mapping-override`** (`routers/controller.py`): Two-phase flow â€” `confirmed_by='pending'` returns proposal+diff (no write); `confirmed_by='user'` commits atomically. Returns 409 on unresolvable conflicts.
- **`remediate_controller_config`** (`services/chuck/ai.py`): Q5 AI tool called by Gemini 2.0 Flash during Diagnosis Mode. `auto_commit=False` surfaces proposal for user confirmation; `True` commits unambiguous fixes directly.

**Files Created/Modified:**
- `frontend/src/hooks/useDiagnosisMode.js` â€” NEW
- `frontend/src/panels/controller/chuckContextAssembler.js` â€” NEW
- `frontend/src/panels/controller/chuckChips.js` â€” NEW
- `frontend/src/panels/controller/DiagnosisToggle.jsx + .css` â€” NEW
- `frontend/src/panels/controller/ContextChips.jsx + .css` â€” NEW
- `frontend/src/panels/controller/MicButton.jsx + .css` â€” NEW
- `frontend/src/panels/controller/ChuckSidebar.jsx` â€” NEW
- `frontend/src/panels/controller/chuck-sidebar.css + chuck-layout.css` â€” NEW
- `frontend/src/panels/controller/ControllerChuckPanel.jsx` â€” MODIFIED (ChuckSidebar wired in)
- `backend/services/controller_bridge.py` â€” NEW
- `backend/routers/controller.py` â€” MODIFIED (MappingOverrideRequest + endpoint added)
- `backend/services/chuck/ai.py` â€” MODIFIED (remediate_controller_config tool added)

**Next**: Controller Chuck Diagnosis Mode sidebar GUI polish â†’ Console Wizard panel.

---

## 2026-03-01 | Controller Chuck UX Sprint â€” FLIP Animations, Focus Mode, Mapping Confirmation

**Net Progress**: Deep UX refinement session on `ControllerChuckPanel.jsx` and `controller-chuck.css`. Overhauled the entire interactive mapping experience from static layout to a cinematic, animation-driven system. All changes build-verified (234 modules, 0 errors). Commits: `586db64`, `a5fcd5e`, `bb3a81f`, `92039ff`, `64513cb`, `ac64c9c`.

**Key Wins:**
- **FLIP Focus Animation**: Click any player card â†’ it springs from its exact grid position to the dead center of the panel using React `getBoundingClientRect()` + CSS custom properties `--flip-x/y/w`. Direction-aware: P1 comes from bottom-left, P2 from bottom-right, P3 from top-left, P4 from top-right. Spring easing: `cubic-bezier(0.34, 1.56, 0.64, 1)`.
- **Premium Return Animation**: Card "breathes out" to scale(1.52) â†’ arcs back to its original grid corner with a blur+fade dissolve. Uses `returningPlayer` state machine so `position:absolute` is held during exit. `onAnimationEnd` clears state cleanly.
- **2P/4P Layout Unification**: Rooted the bug that made 2P mode look completely different from 4P â€” the `chuck-main` needed `justify-content: center; gap: 14px` (same as 4P). Matching compact card sizing (44px buttons, 66px joystick, `max-height: 180px`). Center logo hidden in 2P. Player row content-sized in both modes.
- **Mapping Confirmation Animation System**: Click a button/direction in the UI â†’ cyan pulse starts. Physical cabinet press fires `latestInput` from `useInputDetection`. `PlayerCard` `useEffect` catches it while waiting, fires `confirmedButton`/`confirmedDir` states, auto-clears after 1.8s. Confirmation: white flash â†’ scale(1.35) green ring burst on button; white â†’ green settled glow on arrow; `âœ“ GPIO XX` badge slides up and fades out.
- **Top Strip (SCAN + DETECT) both modes**: Confirmed visible in 2P and 4P via `justify-content: center` fix.
- **Container size fix during FLIP animation**: `width: var(--flip-w)` locks card dimensions during `position: static â†’ absolute` transition.
- **Directional arrows** (already done prior): flow-toward-center waiting animation, 12px triangle paths with `data-dir` attributes.

**Files Modified:**
- `frontend/src/panels/controller/ControllerChuckPanel.jsx` â€” FLIP handler (`mainRef`, `handleFocus`, `focusOrigin`, `returningPlayer`), PlayerCard refactor (cardRef, confirmStates, useEffect listener), ArcadeButton + JoystickGraphic confirmed props, latestInput threading
- `frontend/src/panels/controller/controller-chuck.css` â€” `@keyframes flip-to-center`, `@keyframes return-to-grid`, `@keyframes btn-confirmed`, `@keyframes dir-confirmed`, `@keyframes badge-pop`, 2P layout unification blocks, `focus-returning` class

**Architecture Notes:**
- `returnPlayer` state machine: `activePlayer=null` triggers return â†’ card stays `position:absolute` via `.focus-returning` â†’ `onAnimationEnd` clears â†’ normal grid layout resumes. Critical for avoiding position snap.
- `latestInput` threading: lives in main component (from `useInputDetection`), passed as prop to each `PlayerCard`. Each card independently watches for it while in a waiting state. Avoids lifting mapping state to parent.
- 4P/2P CSS parity: All compact sizing in `chuck-main[data-mode]` selectors. The `chuck-shell[data-mode="4p"] .chuck-main { justify-content: center }` rule (line ~1545) is the canonical anchor â€” 2P now mirrors it.

**Commits**: `586db64` FLIP origin animation | `a5fcd5e` premium return animation | `bb3a81f` 2P layout unification | `92039ff` 2P vertical centering | `64513cb` 2P top strip fix (justify-content root cause) | `ac64c9c` mapping confirmation system
**Next**: Microphone support in Chuck's chat sidebar. Then cascade to Vicky Voice panel.

---

## 2026-03-01 | Diagnosis Mode Planning Sprint â€” All 11 Questions Answered & Approved
**Net Progress**: Complete planning session for **Diagnosis Mode** â€” a cross-panel feature that elevates each specialist AI from free conversation to a context-aware, config-writing co-pilot. User ran the 11 design questions across multiple LLMs simultaneously and submitted the best answer per question; all 11 resolved and approved. Full spec in `diagnosis_mode_plan.md`.

**Key Decisions:**
- **Q1**: Two write targets (profile vs cabinet). Chuck shows Decision Gate before writing. 4-layer resolution. Vicky is IdP via `runtime_state.py`.
- **Q2**: Confirmations-only TTS. "Aviation cockpit, not chatty assistant." Instant-interruptible. `chuck_tts.json` per cabinet.
- **Q3**: No wake word. Push-to-talk. Self-declaratory toggle â€” contextual AI greeting from last 8 messages + hardware state.
- **Q4**: GPIO layer + Semantic layer merged in `controller_bridge.py` only. Sacred numbering `1-2-3-7 / 4-5-6-8` = Rosetta Stone for 45+ emulators.
- **Q5**: Gemini 2.0 Flash via existing `gemini-proxy`. `remediate_controller_config` Pydantic tool. Ollama fallback = read-only.
- **Q6**: 3-tier context injection (<1500 tokens). Chuck's world only â€” no cross-panel bleed.
- **Q7**: Hardware truth always wins. 4 conflict types with defined behaviors. Sacred convention = hard commit block. Version history rollback.
- **Q8**: Optimistic per-input (React state) + 5-step atomic confirm-on-commit.
- **Q9**: One shared `useDiagnosisMode()` hook. ~50 lines per new panel after Chuck.
- **Q10**: Soft-lock timeout (5 min default). Diagnosis Mode never persists across cabinet reboot.
- **Q11**: Push-to-talk IS the gate. 4-layer audio pipeline. TTS mic auto-disable prevents feedback loops.

**Next Session**: Begin Phase 1 implementation â€” `useDiagnosisMode()` hook + `ControllerBridge` + Chuck wiring.



---



## 2026-02-28 | V1 Completion Sprint â€” Close All Audit Blockers
**Net Progress**: Closed 12+ audit-flagged blockers in a single session. Key wins:
- **LEDBlinky path fix**: Updated all backend references from `A:\Tools\LEDBlinky\` to `A:\LEDBlinky\` (actual install location).
- **HttpBridge IGameEventsPlugin**: Added `IGameEventsPlugin` to LaunchBox plugin â€” game start/stop events now POST to the Python backend with game_id, platform, title, and timestamps.
- **Voice LED injection**: Refactored `VoiceService` to accept real `LEDHardwareService` and `SupabaseClient` via dependency injection. Uncommented all hardware calls in `_apply_to_led_service()`.
- **Cinema genre themes**: Added `NitroRush` (racing: green/yellow/white) and `TargetLock` (lightgun: red/white) themes to `colors.json`. Updated `CINEMA_TAG_TO_THEME` mapping. Added `_apply_genre_theme()` and `_reset_leds_to_idle()` helpers.
- **Voice command TTS**: Added `tryLightingCommand()` in `VoicePanel.jsx` â€” lighting commands now fire via SSE and speak responses via `speakAsVicky()`.
- **HID fallback in `_call_ledblinky()`**: If LEDBlinky.exe fails for any reason, the function now falls back to `_apply_genre_theme()` via the Python HID stack.
- **blinky_patterns boot block**: Confirmed the import doesn't error â€” it silently hangs because `blinky.__init__` eagerly parses XML and enumerates HID. Cleaned up comments with root cause and fix path (lazy exports).
- **Supabase project ref**: Discovered all agent config files pointed to the *website* project (`hjxzbicsjzyzalwilmlj`). Fixed to correct Arcade Assistant ref (`zlkhsxacfyxsctqpvbsh`) across 10 files in both A: and C: workspaces.
- **JWT verification**: Toggled `verify_jwt` OFF for `elevenlabs-proxy` and `openai-proxy` in Supabase dashboard. Health check confirmed 200 OK.
- **Dead code removal**: Deleted two orphaned 241KB monolith files (`LEDBlinkyPanel.jsx`, `LEDBlinkyPanelNew.jsx`). The app uses the refactored 25KB version in `led-blinky/`.
- **doc_diagnostics upgrade**: Copied C: drive version (9KB, 262 lines) over A: drive version (4KB, 133 lines). Added VID/PID scanning, health alerts, WebSocket event stream.
- **Assistants.jsx persona names**: Updated all 9 persona entries to match canonical roster: Dewey, LaunchBox LoRa, ScoreKeeper Sam, Controller Chuck, LED Blinky, Gunner, Console Wizard, Vicky, Doc.

**Struggles & Lessons Learned**:
1. **Wrong Supabase project ref**: The CLI returned empty tables for functions and secrets because every agent config file pointed to the G&G Website project instead of Arcade Assistant. Root cause: the refs were copy-pasted incorrectly when the multi-project setup was created. Fix: visual confirmation via browser dashboard, then bulk update across all agent files.
2. **blinky_patterns import hang**: Not an error â€” a *silent freeze*. The `__init__.py` eagerly imports `PatternResolver` which reads LEDBlinky XML files and enumerates HID devices synchronously. Previous comments just said "blocking" without explaining why. Fixed by adding clear documentation and noting the fix path (convert to lazy `__getattr__` exports).
3. **git commit on external drive**: A: drive (USB) git commit hung for 5+ minutes during large file delta computation. The commit eventually completed but required patience.

**Commit**: `94e21d4` on `master` (A: drive, 19 files). `118577f` on `v1-persona-split` (C: drive, 4 files).
**Next**: End-to-end test of cinema genre themes during live gameplay. Verify VoicePanel lighting command flow. Consider converting `blinky.__init__` to lazy exports to re-enable `/api/blinky` endpoints.

## 2026-02-15 | Valentine's Day Session
**Net Progress**: Built complete 5-piece Playnite Restore Toolkit (Fix-ArcadePaths, Restore-ArcadeAssistant, Launch-Sanity-Check, Backup-Creator, run_all_remediation.bat). Fixed Score Pipeline (5 breaks). Completed A:\ drive anatomy for Infrastructure as Code. Diagnosed Playnite extension load failure (BadImageFormatException). All pushed to Valentine-s-Day repo commit `6f74194`.
**Next**: Source Golden Backup via Playnite Auto-scan, configure Game Scanners, run overnight metadata scrape.
- 2026-02-21: Fixed CI/CD sync, deployed new Blinky UI with TTS-enabled chat drawer and pulsing mic.

## 2026-02-22 | Gunner Panel Redesign (Phase 1)
**Net Progress**: Full Gunner codebase audit (~5,700 lines). Redesigned Gunner panel from monolithic 946-line `LightGunsPanel.jsx` into 11-file modular architecture in `components/gunner/`. Created: `GunnerPanel.css` (full cyber/neon design system with Orbitron font, scanlines, glitch animations), `GunnerPanel.jsx` (orchestrator), `GunnerHeader.jsx`, `GunnerNav.jsx`, `GunnerAlertBar.jsx`, `DevicesTab.jsx`, `DeviceCard.jsx`, `SensorGrid.jsx`, `ConnectionMatrix.jsx`, `GunnerChatSidebar.jsx`, `useGunnerChat.js` (AI chat hook with Gemini tool schemas). Swapped import in `Assistants.jsx`. Clean build verified (1.81s), `gunner-panel` class confirmed in dist bundle. Initial build served stale cache â€” fixed with dist wipe + clean rebuild.
**Status**: Awaiting visual confirmation after user machine restart.
**Next**: Visually verify panel renders correctly. Then build Phase 2: Calibration tab, Profiles tab, Retro Modes tab, voice controls integration, live `gunnerClient.js` API wiring.

## 2026-02-23 | Infrastructure & VUI Milestone + Dewey V2.5 Transplant
**Net Progress (AM)**: Fixed consent save 403 (added `.aa/`-prefixed sanctioned paths to manifest). Integrated `httpx` broadcast into `scorekeeper.py` REST endpoints (`apply_score_submit`, `game_autosubmit`) for instantaneous WebSocket leaderboard push. Built Vicky Voice phase indicator bridges (`isSpeaking` state, `currentPhase` badge: ðŸŽ¤â†’ðŸ§ â†’ðŸ”Šâ†’ðŸ’¤). Extracted `useGemSpeech` hook. 237 modules, 0 errors.
**Net Progress (PM)**: Transplanted Dewey Arcade Historian V2.5 design (1,100+ lines Tailwindâ†’vanilla CSS, JSX restructure). Fixed `speechSupported` undefined bug. Diagnosed stale build issue (C: vs A: drive split). Created `scripts/clean-start.ps1` for zombie port cleanup + rebuild + deploy. Implemented WS exponential backoff in `ProfileContext.jsx` and `hotkeyClient.js` (2sâ†’30s cap). Added `[App]` diagnostic banner to `App.jsx`. Root-caused "blue screen" to empty `personas = []` array in `Assistants.jsx` when `/assistants` has no query param.
**Status**: Dewey V2.5 renders correctly via `?chat=dewey`. WS console spam eliminated.
**Next**: Populate `personas[]` array in `Assistants.jsx` so `/assistants` shows agent selection grid. End-to-end consent UI flow test. Gunner Phase 2.




## 2025-03-09 — Codebase Easy Wins
- Gateway centralization: 24 files, `gateway.js` created
- ArcadeWizard port bug fixed
- getLiveScore stub added
- Swallowed exceptions logged (5 catch blocks)
- print->logger in 3 backend routers
- Console Wizard refactor plan written for next session
- Pushed: f5f0d3b


## 2026-03-11 — Antigravity Session (~4 hours)

**Net Progress:**
- Fixed 2 backend bugs blocking app launch (NameError in scorekeeper.py, ValueError in input_detector.py)
- Built complete Gamepad Controller Configuration interface (NEW feature)
  - 3 new files: ControllerSVG.jsx, GamepadSetupOverlay.jsx, gamepad-setup.css
  - 2 modified files: WizNavSidebar.jsx, ConsoleWizardPanel.jsx
  - 5 controller PNG assets generated + deployed to /assets/controllers/
  - PNG + SVG overlay hybrid "digital twin" system
  - 4-phase wizard: Detect → Map 16 buttons → Calibrate sticks → Complete
  - Profile selection works without hardware (preview mode)
- Frontend build clean, Controller tab verified in browser
- README updated with full session catalog

**Open:**
- Live-test with physical 8BitDo at cabinet
- Fine-tune hotspot overlay positions per controller
- ScoreKeeper Sam live validation (carried forward)
- Daphne/Hypseus live test (carried forward)

---

## 2026-04-11 | LoRa Stabilization + Launch Integrity Session

**Net Progress**: Focused almost entirely on LaunchBox LoRa. Tightened multi-turn conversation behavior, cleaned up launch phrasing, tested Gemini model upgrades, fixed false-positive launch reporting, investigated a backend drop around Naomi browsing, and added duplicate-launch mitigations. Frontend build passed and targeted backend validation passed.

**Key Wins:**
- **LoRa conversation state hardening** in `gateway/routes/launchboxAI.js`
  - Numeric replies like `1`, `2`, `3` stay attached to the active candidate set.
  - Refinements like `the NES version`, `the arcade version`, `Nintendo version`, `2600 version`, `original`, and year-only follow-ups are now applied against prior results instead of falling back to raw title search.
  - Single-candidate confirmations now create a real ready-to-launch state, so replies like `Yes let's do this` launch the selected title instead of being interpreted as a new search.
  - Added vernacular normalization for common ASR mistakes such as `verses of` -> `versions of`.
  - Tightened title anchoring to reduce franchise drift (for example, `Pac-Man` no longer wants to drift toward `Jr. Pac-Man` during refinement).

- **LoRa panel speech/presentation cleanup** in `frontend/src/panels/launchbox/LaunchBoxPanel.jsx`
  - Preserved numbered disambiguation lists in the rendered chat.
  - Launch announcements now derive friendly platform labels from `game.platform`, so speech can say `arcade version`, `NES version`, `PlayStation 2 version`, etc.

- **Gemini model trials completed**
  - Tested `gemini-2.5-flash-lite`.
  - Tested `gemini-3-flash-preview`.
  - `gemini-3-flash-preview` was not stable enough for this stack and triggered 500-level failures.
  - Final stable recommendation for front-facing LoRa/Dewey remains `gemini-2.5-flash`.
  - Updated model/default callers so deprecated `gemini-2.0-flash` is no longer the silent fallback target.

- **Launch truthfulness fix** in `backend/routers/launchbox.py`
  - Added short-window PID confirmation before panel callers are told a launch succeeded.
  - `launchbox_only` platforms no longer report a successful LoRa-panel launch.
  - If the backend issued a command but could not confirm the process, LoRa now reports that the launch could not be verified instead of pretending the game launched.

- **Backend tests added/updated** in `backend/tests/test_launchbox_router.py`
  - Verified downgrade behavior for unconfirmed direct launches.
  - Verified downgrade behavior for launchbox-only platforms.
  - Existing Type X path remained environment-sensitive, but no clean assertion regression was found.

- **Naomi/backend incident triage**
  - Confirmed backend had dropped during the reported Naomi issue.
  - Restarted backend and rechecked Naomi browse/detail/image endpoints successfully.
  - Naomi browse itself was healthy after restart.
  - Concrete backend-side exception found during startup: file-lock race in `backend/services/hiscore_watcher.py` while replacing `scores.jsonl`.
  - Separate Windows event log showed an earlier `redream.exe` crash, but not a clean Python crash tied directly to Naomi browsing.

- **Duplicate launch mitigation**
  - Investigated repeated GameCube launches and confirmed this was not just UI perception.
  - `gateway/lib/http.js`: retry helper now retries only idempotent methods and will not retry `POST` launch requests.
  - `frontend/src/panels/launchbox/LaunchBoxPanel.jsx`: `launchGame()` now refuses to run when the launch lock is already active, instead of relying only on disabled buttons.
  - Remaining suspicion: GameCube routing can still fan across more than one backend launch path and needs a dedicated cleanup pass.

**Validation:**
- `node --check gateway/routes/launchboxAI.js` passed
- `node --check gateway/lib/http.js` passed
- `python -m py_compile backend/routers/launchbox.py` passed
- targeted pytest checks passed for launch downgrade behavior
- `npm.cmd run build:frontend` passed

**Current State:**
- LoRa panel is materially cleaner, more conversational, and less brittle than at session start.
- Launch reporting is more honest.
- Backend is currently back up and healthy.
- Remaining work is edge-case tightening, not major architecture rewrite.

**Next:**
1. Hard-fix GameCube routing so one request cannot fan across multiple launch paths.
2. Harden `backend/services/hiscore_watcher.py` around file replacement locking.
3. Continue transcript-driven LoRa polish, especially around rare customer phrasing and disambiguation edge cases.
## 2026-04-19 (Codex Session â€” LaunchBox LoRa Redesign Stabilization + Artwork Recovery)

**Net Progress**: LaunchBox LoRa was pulled back into a practical customer-facing state. The redesign was stabilized, artwork was restored, the chat drawer and sidebar layout issues were corrected, and several hard-to-support platform families were deliberately removed from the LoRa surface for expediency.

### What Changed

- **Redesign stabilization**: the LaunchBox LoRa panel was reworked so the shipped UI follows the intended cinematic layout more closely.
- **Search focus fix**: typing into the search field no longer loses focus because refetches do not swap the panel into a blocking loading state.
- **Library browsing fix**: the main game area now behaves like a real browser surface, with working scroll behavior and double-click launch from game tiles.
- **UI cleanup**:
  - removed placeholder nav items (`Store`, `Social`, `Cloud`)
  - removed the Collections block from the left sidebar
  - removed the old jump-to-collections rail affordance
  - kept the sidebar focused on actual platforms
- **Launcher direction change**: the old Pegasus action in this surface was replaced with Big Box launch behavior.
- **Platform-scope cleanup**: LoRa exclusions now include American Laser Games, Daphne, all gun-game platforms, TeknoParrot Arcade, and Taito Type X.

### Artwork Recovery - What Was Tried and What Actually Fixed It

This session is important because the artwork issue had multiple real bugs, but the final failure was not where it first appeared.

**Architecture verified as still correct:**
- LaunchBox XML remained the source of truth.
- `backend/services/launchbox_parser.py` still built the game library correctly.
- `ImageScanner` still owned media-path discovery.
- The LoRa panel still consumed artwork through `/api/launchbox/image/{game_id}`.

**Real fixes that were required:**
- `image_scanner.py`
  - added nested regional folder indexing (`North America`, `World`, `Europe`, etc.)
  - added conservative title-variant matching
  - bumped cache versioning so stale scanner results would not persist
- `gateway/routes/launchboxProxy.js`
  - fixed proxy forwarding so `variant=card` query params actually reached the backend
- `backend/routers/launchbox.py`
  - changed card-art priority so LoRa cards use `box_front` / `screenshot`, not `clear_logo`
  - set placeholder responses to `no-store`
- `frontend/src/panels/launchbox/LaunchBoxPanel.jsx`
  - added `cache_key` to image URLs to break cached placeholder responses

**Critical final root cause:**
- The card fallback layer was covering the image in CSS.
- Real artwork was loading, but the fallback sat on top of it.
- Final fix: corrected z-index ordering in `launchbox.css` so the fallback sits behind the image, while the overlay and title remain above it.

**Lesson to preserve:**
- If artwork breaks again, do not assume the backend resolver is the primary problem.
- Verify the live image URL first.
- Then inspect the rendered card layer stack in the frontend before rewriting artwork-selection logic.

### Layout / Interaction Follow-ups

- **Chat drawer**: changed from `absolute` to `fixed` positioning so it anchors to the viewport rather than the full scrolling panel height.
- **Platform list**: removed the hard `slice(0, 10)` cap so later systems like Dreamcast, Naomi, and Atomiswave appear in the sidebar.
- **Collections removal**: deleting the Collections block shortened the sidebar and reduced visual clutter.

### Verification Used

- repeated `npm run build:frontend`
- multiple full `stop-aa.bat` / `start-aa.bat` recycles
- direct gateway image URL checks
- headless Chrome screenshots against `http://127.0.0.1:8787/assistants?agent=launchbox`
- live API verification that excluded platforms no longer appeared in `/api/launchbox/platforms?exclude_lora_specialized=1`

### Carry-Forward Rules

1. Keep LoRa practical. Do not put difficult one-off launch ecosystems back into this panel unless there is a clear customer reason.
2. Preserve the current artwork architecture: LaunchBox XML -> parser -> `ImageScanner` -> `game_id` image route.
3. For future artwork regressions, verify live route output and frontend layer order before inventing a new media system.
4. If backend exclusions change, keep frontend `isLoRaExcludedPlatform()` in sync so UI behavior and data behavior do not drift apart.

# ROLLING LOG â€” Arcade Assistant

## 2026-04-19 (Codex Session - LaunchBox LoRa Redesign Stabilization + Artwork Recovery)

**Net Progress**: LaunchBox LoRa was pulled back into a practical customer-facing state. The redesign was stabilized, artwork was restored, the chat drawer and sidebar layout issues were corrected, and several hard-to-support platform families were deliberately removed from the LoRa surface for expediency.

### What Changed

- **Redesign stabilization**: the LaunchBox LoRa panel was reworked so the shipped UI follows the intended cinematic layout more closely.
- **Search focus fix**: typing into the search field no longer loses focus because refetches do not swap the panel into a blocking loading state.
- **Library browsing fix**: the main game area now behaves like a real browser surface, with working scroll behavior and double-click launch from game tiles.
- **UI cleanup**:
  - removed placeholder nav items (`Store`, `Social`, `Cloud`)
  - removed the Collections block from the left sidebar
  - removed the old jump-to-collections rail affordance
  - kept the sidebar focused on actual platforms
- **Launcher direction change**: the old Pegasus action in this surface was replaced with Big Box launch behavior.
- **Platform-scope cleanup**: LoRa exclusions now include American Laser Games, Daphne, all gun-game platforms, TeknoParrot Arcade, and Taito Type X.

### Artwork Recovery - What Was Tried and What Actually Fixed It

This session is important because the artwork issue had multiple real bugs, but the final failure was not where it first appeared.

**Architecture verified as still correct:**
- LaunchBox XML remained the source of truth.
- `backend/services/launchbox_parser.py` still built the game library correctly.
- `ImageScanner` still owned media-path discovery.
- The LoRa panel still consumed artwork through `/api/launchbox/image/{game_id}`.

**Real fixes that were required:**
- `image_scanner.py`
  - added nested regional folder indexing (`North America`, `World`, `Europe`, etc.)
  - added conservative title-variant matching
  - bumped cache versioning so stale scanner results would not persist
- `gateway/routes/launchboxProxy.js`
  - fixed proxy forwarding so `variant=card` query params actually reached the backend
- `backend/routers/launchbox.py`
  - changed card-art priority so LoRa cards use `box_front` / `screenshot`, not `clear_logo`
  - set placeholder responses to `no-store`
- `frontend/src/panels/launchbox/LaunchBoxPanel.jsx`
  - added `cache_key` to image URLs to break cached placeholder responses

**Critical final root cause:**
- The card fallback layer was covering the image in CSS.
- Real artwork was loading, but the fallback sat on top of it.
- Final fix: corrected z-index ordering in `launchbox.css` so the fallback sits behind the image, while the overlay and title remain above it.

**Lesson to preserve:**
- If artwork breaks again, do not assume the backend resolver is the primary problem.
- Verify the live image URL first.
- Then inspect the rendered card layer stack in the frontend before rewriting artwork-selection logic.

### Layout / Interaction Follow-ups

- **Chat drawer**: changed from `absolute` to `fixed` positioning so it anchors to the viewport rather than the full scrolling panel height.
- **Platform list**: removed the hard `slice(0, 10)` cap so later systems like Dreamcast, Naomi, and Atomiswave appear in the sidebar.
- **Collections removal**: deleting the Collections block shortened the sidebar and reduced visual clutter.

### Verification Used

- repeated `npm run build:frontend`
- multiple full `stop-aa.bat` / `start-aa.bat` recycles
- direct gateway image URL checks
- headless Chrome screenshots against `http://127.0.0.1:8787/assistants?agent=launchbox`
- live API verification that excluded platforms no longer appeared in `/api/launchbox/platforms?exclude_lora_specialized=1`

### Carry-Forward Rules

1. Keep LoRa practical. Do not put difficult one-off launch ecosystems back into this panel unless there is a clear customer reason.
2. Preserve the current artwork architecture: LaunchBox XML -> parser -> `ImageScanner` -> `game_id` image route.
3. For future artwork regressions, verify live route output and frontend layer order before inventing a new media system.
4. If backend exclusions change, keep frontend `isLoRaExcludedPlatform()` in sync so UI behavior and data behavior do not drift apart.

---

## 2026-04-19 (Codex Session â€” LaunchBox LoRa Redesign Stabilization + Artwork Recovery)

**Net Progress**: LaunchBox LoRa was pulled back into a practical customer-facing state. The redesign was stabilized, artwork was restored, the chat drawer and sidebar layout issues were corrected, and several hard-to-support platform families were deliberately removed from the LoRa surface for expediency.

### What Changed

- **Redesign stabilization**: the LaunchBox LoRa panel was reworked so the shipped UI follows the intended cinematic layout more closely.
- **Search focus fix**: typing into the search field no longer loses focus because refetches do not swap the panel into a blocking loading state.
- **Library browsing fix**: the main game area now behaves like a real browser surface, with working scroll behavior and double-click launch from game tiles.
- **UI cleanup**:
  - removed placeholder nav items (`Store`, `Social`, `Cloud`)
  - removed the Collections block from the left sidebar
  - removed the old jump-to-collections rail affordance
  - kept the sidebar focused on actual platforms
- **Launcher direction change**: the old Pegasus action in this surface was replaced with Big Box launch behavior.
- **Platform-scope cleanup**: LoRa exclusions now include American Laser Games, Daphne, all gun-game platforms, TeknoParrot Arcade, and Taito Type X.

### Artwork Recovery - What Was Tried and What Actually Fixed It

This session is important because the artwork issue had multiple real bugs, but the final failure was not where it first appeared.

**Architecture verified as still correct:**
- LaunchBox XML remained the source of truth.
- `backend/services/launchbox_parser.py` still built the game library correctly.
- `ImageScanner` still owned media-path discovery.
- The LoRa panel still consumed artwork through `/api/launchbox/image/{game_id}`.

**Real fixes that were required:**
- `image_scanner.py`
  - added nested regional folder indexing (`North America`, `World`, `Europe`, etc.)
  - added conservative title-variant matching
  - bumped cache versioning so stale scanner results would not persist
- `gateway/routes/launchboxProxy.js`
  - fixed proxy forwarding so `variant=card` query params actually reached the backend
- `backend/routers/launchbox.py`
  - changed card-art priority so LoRa cards use `box_front` / `screenshot`, not `clear_logo`
  - set placeholder responses to `no-store`
- `frontend/src/panels/launchbox/LaunchBoxPanel.jsx`
  - added `cache_key` to image URLs to break cached placeholder responses

**Critical final root cause:**
- The card fallback layer was covering the image in CSS.
- Real artwork was loading, but the fallback sat on top of it.
- Final fix: corrected z-index ordering in `launchbox.css` so the fallback sits behind the image, while the overlay and title remain above it.

**Lesson to preserve:**
- If artwork breaks again, do not assume the backend resolver is the primary problem.
- Verify the live image URL first.
- Then inspect the rendered card layer stack in the frontend before rewriting artwork-selection logic.

### Layout / Interaction Follow-ups

- **Chat drawer**: changed from `absolute` to `fixed` positioning so it anchors to the viewport rather than the full scrolling panel height.
- **Platform list**: removed the hard `slice(0, 10)` cap so later systems like Dreamcast, Naomi, and Atomiswave appear in the sidebar.
- **Collections removal**: deleting the Collections block shortened the sidebar and reduced visual clutter.

### Verification Used

- repeated `npm run build:frontend`
- multiple full `stop-aa.bat` / `start-aa.bat` recycles
- direct gateway image URL checks
- headless Chrome screenshots against `http://127.0.0.1:8787/assistants?agent=launchbox`
- live API verification that excluded platforms no longer appeared in `/api/launchbox/platforms?exclude_lora_specialized=1`

### Carry-Forward Rules

1. Keep LoRa practical. Do not put difficult one-off launch ecosystems back into this panel unless there is a clear customer reason.
2. Preserve the current artwork architecture: LaunchBox XML -> parser -> `ImageScanner` -> `game_id` image route.
3. For future artwork regressions, verify live route output and frontend layer order before inventing a new media system.
4. If backend exclusions change, keep frontend `isLoRaExcludedPlatform()` in sync so UI behavior and data behavior do not drift apart.

---
