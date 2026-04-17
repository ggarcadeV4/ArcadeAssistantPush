# Arcade Assistant Ã¢â‚¬â€ Project README
**Last Updated:** 2026-04-13 NIGHT | **Build:** Console Wizard mic hardening + Controller Chuck status semantics pass | **Branch:** `master` | **Commit:** `WIP (uncommitted)`

> **For AI Agents:** Read `ROLLING_LOG.md` first for net-progress history. Read `ARCHITECTURE.md` for backend deep-dives. This README is the quick-reference entry point.

---

## What Is Arcade Assistant?

A **self-hosted AI control hub** for a physical arcade cabinet. It runs locally on a Windows PC (A: drive) and provides:
- A React frontend served via a Node.js gateway
- A FastAPI Python backend
- 9 specialized AI personas, each with their own panel, chat sidebar, and hardware hooks
- Hardware integrations: LED-Wiz boards (3x), encoder boards, LaunchBox, light guns

---

## Quick Start

```powershell
# From A:\Arcade Assistant Local\
.\start-aa.bat

# Or manually:
# Terminal 1 Ã¢â‚¬â€ Gateway (Node)
cd gateway && node server.js

# Terminal 2 Ã¢â‚¬â€ Backend (Python)
cd backend && python app.py

# Terminal 3 Ã¢â‚¬â€ Frontend (Vite dev server)
cd frontend && npm run dev
```

**Access:** `http://127.0.0.1:8787`

---

## Infrastructure

| Component | Location | Port | Notes |
|-----------|----------|------|-------|
| Gateway (Node.js) | `gateway/server.js` | 8787 | Serves frontend static, proxies to backend |
| Backend (FastAPI) | `backend/app.py` | 8000 | AI, LED, scoring, hotkey APIs |
| Frontend (Vite/React) | `frontend/` | 5173 (dev) | Built to `dist/` for prod |
| Supabase | Cloud | Ã¢â‚¬â€ | Ref: `zlkhsxacfyxsctqpvbsh` (**Arcade Assistant only**) |

> Ã¢Å¡Â Ã¯Â¸Â **NEVER** use Supabase ref `hjxzbicsjzyzalwilmlj` Ã¢â‚¬â€ that is the G&G Website project.

---

---

## Daily Slice — 2026-04-13 NIGHT

### Console Wizard — Functional Milestone ✅

Console Wizard now behaves like a real product surface. Work completed today:

- **Diagnostic Mode** — Felt excellent in live runtime. DIAG integrity and voice de-dupe were improved. A DIAG greeting is now posted into the visible chat history so mode transitions are explicit to the user.
- **Unified chat path** — Typed and mic flows now land in the same visible sidebar conversation via a `wizSendRef` bridge from `EngineeringBaySidebar.sendMessage`. Previously mic transcripts routed to a separate, hidden path.
- **Mic capture hardened** — `EngineeringBaySidebar` now accepts an optional `micHandlers` prop (`{ isRecording, onToggle }`). When present, the sidebar mic button delegates entirely to the panel's own capture stack. Console Wizard uses this to bypass the brittle shared Web Speech path and route directly through `getUserMedia` + `MediaRecorder` + `/ws/audio`.
- **WS lazy connect** — The `/ws/audio` WebSocket now opens on first mic press, not on panel mount. Prevents early gateway rejection during dev startup.
- **Silence detection** — Web Audio API `AnalyserNode` RMS polling auto-stops recording after 1.5s of silence (with a 1.5s lead-in), so the user only presses mic once per utterance.
- **Visible failure feedback** — All mic/WS failure modes surface an explicit `⚠️` message in chat instead of silently resetting state.

**Remaining Wizard work (polish, not rescue):**
- Controller-configuration UI edge cases need sharpening
- Speech/transcript latency could be tightened

**Files touched:** `EngineeringBaySidebar.jsx`, `ConsoleWizardPanel.jsx`

---

### Controller Chuck — Major Progress, Not Yet Finished

Chuck made significant gains today but requires one final reconciliation pass before it can be declared done.

**What landed:**
- Status semantics improved — "NO BOARD" / "NO SIGNAL" replace misleading "OFFLINE" labels
- SCAN now refreshes backend detection before refetch
- Focused PlayerCard overflow is substantially better (minor tuning may remain)
- Canonical board lane progressively hardened:
  - XInput-spoofed arcade-encoder detection cases added
  - Discovery widened with WMI / device-scanner supplementation
  - Existing Pacto-style grouped XInput topology logic wired into the canonical lane

**What remains:**
- GUI truth vs AI truth are not yet fully reconciled around logical board identity
- Chuck still needs one final pass to unify board identity across: visible GUI card, AI response, and DIAG entry sequencing
- Prior Chuck logic was not wasted — the issue is that fragmented/backend intelligence is not fully surfacing in the live panel

**Status: Close but not finished. Truth-surface reconciliation pass is the next and final Chuck task.**

---

### Session Doctrine (Carry Forward)

- One panel at a time
- Codex pre-audit first → narrow implementation → runtime verification
- Finish by panel promise and canonical path, not by random symptom chasing

### Tomorrow's First Move

1. Fresh thread
2. Focus only on Controller Chuck
3. Task: final truth-surface reconciliation pass
   - Logical board identity unified across GUI card + AI response + DIAG sequencing
   - Slight focused-card tuning only if still needed after identity is resolved

---

## Daily Slice — 2026-04-12 NIGHT

### What landed tonight

Narrow transport-layer recovery for the F9 / Dewey summon path. No architectural changes, no new features, no panel rewrites.

#### F9 Hotkey WebSocket Path Repaired
- Root cause: the Electron-side WebSocket client in `frontend/electron/main.cjs` was broken. The client connecting `main.cjs` to the backend `/ws/hotkey` endpoint was not attaching with a valid device identity.
- Fix: corrected the connection path and device identity handshake in `main.cjs`.
- Result: Electron now connects successfully and the backend hotkey manager receives F9 events from the Electron process.

#### Dewey Overlay Routing Validated
- After the transport fix, Dewey overlay connected and summoned on F9 press.
- User told Dewey the controller was not working → Dewey routed correctly to Controller Wizard.

#### Live Launch Confirmed
- User launched a game from the recovered Dewey summon flow.
- Launch succeeded.

### Scope discipline
- This was a **narrow** fix — only the WebSocket client in `frontend/electron/main.cjs`.
- Backend hotkey router, hotkey manager, frontend panel logic, and LaunchBox plumbing were **not changed**.

### Known remaining follow-ups
| Item | Notes |
|------|-------|
| Shift+F9 global shortcut registration | ⚠️ OS-level shortcut conflict still unresolved |
| Electron console window polish | 🔶 Deferred — not customer-ready |
| PS3 multi-launch cascade | 🔶 Separate backend fix, not tonight |
| LaunchBox duplicate PS3 record cleanup | 🔶 LaunchBox data hygiene, separate task |

---

## Daily Slice — 2026-04-11

### What landed today

We completed a major infrastructure-stabilization sequence across Arcade Assistant:

#### Campaign 1 — Gateway Enclosure
- Removed direct frontend backend-bypass behavior.
- Removed direct frontend Supabase browser-client usage from active runtime paths.
- Reconciled backend port drift to the canonical `:8000` contract.
- Added the missing backend websocket termination point for `/api/local/hardware/ws/encoder-events`.
- Removed dead legacy Gunner panel code and cleaned stale backend-port guidance.

#### Campaign 2 — Identity & Device-ID Standardization
- Centralized frontend device identity through `frontend/src/utils/identity.js`.
- Eliminated synthetic frontend device-id fallbacks such as `CAB-0001`, `cabinet-001`, `demo_001`, `controller_chuck`, and `unknown-device`.
- Removed unsanctioned localStorage-based device identity resolution.
- Standardized `x-device-id`, `x-panel`, and `x-scope` header usage across frontend runtime paths.
- Verified `playerTrackingClient.js` scope header (`x-scope: 'local'`) as correct and intentional.

#### Campaign 3 — Path Determinism & Root Unification
- Aligned `.env` and `.aa/manifest.json` to the same `AA_DRIVE_ROOT` value.
- Unified sanctioned-path bootstrap defaults through `backend/constants/sanctioned_paths.py`.
- Replaced inline drive-root fallbacks in backend services with canonical `get_drive_root()` helper from `backend/constants/drive_root.py`.
- Gateway now uses `requireDriveRoot()` and `resolveDriveRoot()` utilities from `gateway/utils/driveDetection.js`.
- Removed hardcoded `A:\` / `W:\` runtime literals from active backend and gateway paths.
- Classified remaining `process.cwd()` shims in 4 gateway adapter/utility files as acceptable compatibility shims (deferred to Gateway Pass 2).

#### Safety Model Hardening
- Hardened 5 mutation surfaces to support preview, dry-run, backup, and request-aware JSONL audit logging:
  - `/api/local/config/restore`
  - `/api/local/profile/primary`
  - `/api/local/controller/cascade/apply`
  - `/api/local/controller/mapping/set`
  - `/api/scores/reset/{rom_name}`

### Contracts established today
- **Golden Drive Contract**: All modules must use `backend.constants.drive_root` or `gateway.utils.driveDetection` helpers. Hardcoded drive literals are prohibited in runtime code.
- **Gateway Mediation**: All frontend-to-backend communication must flow through the Node Gateway.
- **Identity Source**: Frontend identity is strictly mediated through `frontend/src/utils/identity.js`.

### Deferred / Known Backlog
- 4 `process.cwd()` gateway adapter shims remain (Gateway Pass 2).
- LaunchBox LoRa GUI regression (light guns / American Laser Games titles reappearing in AA GUI) — intentionally deferred; direct LaunchBox access functional.

---

## 2026-04-10 — LoRa Platform Routing Complete ✅ MILESTONE

**LaunchBox LoRa is the first completed panel in Arcade Assistant V1.** Every platform on the cabinet now launches directly through its correct emulator.

### Platform Status
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

### Key Fixes Applied
- `launchers.json` — All hardcoded `A:\` paths replaced with `${AA_DRIVE_ROOT}` — unblocked PS3, Model 2, Wii U, Hypseus
- RetroArch adapter — Sony PSP removed from `INSTANCE_REGISTRY`; PPSSPP standalone now handles PSP
- Dolphin adapter — `launchers.json` block added; adapter reads manifest first
- Cemu adapter — reads exe from `launchers.json` directly, bypasses broken `emulator_paths.json` first-match
- `emulator_paths.json` — stale `A:\LaunchBox` reference replaced with W drive path
- `arcade_launcher_agent.py` — Processes now launch fully detached (`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`) with DEVNULL stdio; fixes Supermodel OpenGL startup
- `launcher.py` — `has_registered_adapter` check added; `skip_agent=True` prevents port 9123 failures from blocking launches
- **Bezel drift fixed permanently** — Root cause: `LaunchBox\Emulators\RetroArch\RetroArch-Controller\retroarch.cfg` had GameCube overlay hardcoded globally. All three RetroArch instances now have overlays stripped and `config_save_on_exit = "false"`
- **CRT shader applied globally** — `crt-easymode.slangp` active on all three RetroArch instances
- `retroarch_adapter.py` — Runtime base config isolation: clean config generated per launch, `--appendconfig` applies platform override; prevents bezel carryover
- Frontend — gun games, Nintendo Switch, Nintendo DS, Dev2 hidden from LoRa sidebar
- PS2 library cleaned to 44 confirmed working titles

### Architecture Reminders
- ⚠️ NEVER change `config_save_on_exit` in any RetroArch cfg — intentionally `"false"`
- Three RetroArch instances: Standard, Gamepad, RetroArch-Controller (LaunchBox tree) — all must stay in sync
- Launcher Agent on port 9123 — required for no_pipe adapter launches (Model 3, etc.)

---

## 2026-03-20 — Security Hardening + Pre-Duplication Validation

### Security (Pillar 2 — Local Physical Security)
- DPAPI vault implemented: `secrets_loader.py` + `encrypt_secrets.py` deployed at repo root
- Tier 1 secrets (SUPABASE_URL, SUPABASE_ANON_KEY, AA_PROVISIONING_TOKEN, AA_SERVICE_TOKEN) moved to DPAPI-encrypted `.aa/credentials.dat`
- `app.py` patched to load vault before router init
- `health.py` updated to report vault status
- `clean_for_clone.bat` extended with Step 9 security scrub — removes all AI agent docs, dev tooling, and loose test files from golden image
- `pywin32>=306` added to requirements.txt

### Pre-Existing Bug Fixes
- `backend/requirements.txt` — duplicate supabase dependency removed (kept `supabase==2.23.2`)
- `backend/app.py` — duplicate doc_diagnostics import removed
- `backend/app.py` — `dur_init_blinky` unassigned reference fixed with safe `0.0` default

### Startup + Gateway Fixes
- `start-aa.bat` — `AA_UPDATES_ENABLED=0` added
- `gateway/config/env.js` — default AI provider corrected from 'claude' to 'gemini'
- `clean_for_clone.bat` — `:RemoveTree` quoting fixed (paths with spaces now handled correctly)

### AHK Script Remediation
- 21 files corrected: `D:\` → `A:\`
- Sinden Lightgun launch blocks removed from all affected scripts
- `SINGE2.backup-$(date +%Y%m%d-%H%M%S)\` deleted (broken Linux-named backup directory)
- `Marbella Vice - Sinden.ahk` renamed to `Marbella Vice.ahk` (script was already clean — filename only was misleading)
- `Lethal Enforcers RC2021-04-07.ahk` Sinden bezel references removed
- Final state: 0 `D:\` refs, 0 Sinden refs across all 302 AHK files

### Identity Reconciliation
- `.aa` state reconciled across both drive roots
- All four identity values now match: UUID `e9478fe3-bbba-48b2-9d2f-22d446b5a8bc`
- `cabinet_manifest.json` created in repo-local `.aa`

### Supabase Validation
- Project `zlkhsxacfyxsctqpvbsh` confirmed healthy
- All 5 Edge Functions deployed and secrets confirmed
- MAC allowlist: cabinet approved
- RLS status: fully hardened — anon writes blocked
- Pillar 1 (JWT auth) scheduled for next session after basement validation

### Known Open Items (Post-Duplication)
- Pillar 1: Per-cabinet JWT authentication
- Pillar 3: OTA bundle signing
- Heartbeat/telemetry blocked until JWT implemented
- DPAPI vault initialization (operator manual step)
- `BASEMENT_BRIEFING.md` added to repo root

### Drive Status
- Golden image: READY TO DUPLICATE
- Basement validation: PENDING

---

## Session Update (2026-03-18)

This session focused on two live-cabinet reliability areas on the A: drive: bezel / artwork display across RetroArch and MAME, and the current Daphne / Hypseus direct-launch path for Dragon's Lair. The work mixed deep read-only audits with a few targeted corrections where the runtime state was already clearly wrong.

### A-Drive Bezel / Overlay Audit
- Audited all three RetroArch installs on `A:\` and verified global overlay state, per-core overrides, and overlay asset locations.
- Confirmed bezel assets already exist locally, including large `ArcadeBezels` and `GameBezels` packs under `A:\Emulators\RetroArch\overlays\`.
- Verified that `A:\Emulators\RetroArch\overlays\ArcadeBezels\` is populated with per-game CFG/PNG pairs rather than being empty.
- Audited LaunchBox image, ThirdScreen, and overlay-related folders to separate actual bezel sources from unrelated artwork caches.
- Confirmed the main LaunchBox emulator XML does not contain direct bezel / overlay / third-screen wiring for the paths reviewed.

### RetroArch / MAME Runtime Corrections
- Added `scripts/wire_mame_bezels.py` to map RetroArch per-game MAME configs to matching `ArcadeBezels` CFGs, with dry-run mode, sibling `.bezel_backup` creation, and a report written to `logs/bezel_wiring_report.txt`.
- Ran the script in dry-run only and measured the current match rate before any bulk write: `4595` MAME CFGs scanned, `3015` matches, `1580` unmatched.
- Corrected the wrong core-level overlay pointers for Sega 32X and Master System in RetroArch and verified the TurboGrafx-16 core-level pointer already targeted the correct overlay CFG.
- Normalized global RetroArch overlay visibility settings on the primary, gamepad, and gun-build installs so overlay enablement, opacity, and scale are explicitly set for bezel display.
- Switched the primary RetroArch instance from exclusive fullscreen to borderless windowed fullscreen to preserve Windows overlay rendering.
- Enabled native MAME artwork toggles in both `A:\Emulators\MAME\mame.ini` and `A:\Emulators\MAME Gamepad\mame.ini` by setting `use_backdrops`, `use_overlays`, `use_bezels`, `use_cpanels`, and `use_marquees` to `1`.

### Daphne / Hypseus Diagnostics
- Audited `backend/services/launcher.py` and confirmed the only launcher-side Daphne / Hypseus direct branch lives inside `_launch_direct()`, before the generic adapter loop.
- Traced Dragon's Lair end to end from LaunchBox XML and confirmed the main `Daphne` platform record points to `..\Roms\SINGE-HYPSEUS\Dragons Lair.ahk`.
- Verified the self-healing remediation chain is already wired through `game_lifecycle.py`, but also confirmed the local `.env` currently has no `GEMINI_API_KEY` or `GOOGLE_API_KEY`, which blocks live Gemini-based remediation.
- Confirmed `game_lifecycle.py` is already passing the `tracked.emulator` value into `attempt_remediation()`, so emulator context is not the missing link there.

### Targeted Launcher Fix
- Identified the exact Dragon's Lair direct-launch failure: the hardcoded Daphne map in `backend/services/launcher.py` handled `"dragon's lair hd"` but not the AHK stem `"dragons lair"`.
- Added the missing Daphne map key `"dragons lair": ("lair", r"A:\Roms\DAPHNE\vldp\lair\lair.txt")` so the hardcoded Hypseus path can resolve that title instead of raising and falling through.
- Added explicit warning logging when a launch method returns a non-success result, so future fallback to later methods is visible in logs instead of appearing silent.
- Created a backup of `backend/services/launcher.py` before the patch as `backend/services/launcher.py.daphne_backup`.

### Audit Scope Notes
- Most of the bezel and artwork work today was performed directly against live A: drive emulator/config state rather than inside this repository.
- The only repo-local code changes from this slice were the new MAME bezel wiring script, the `launcher.py` Dragon's Lair mapping / logging patch, and this README update.

---

## Session Update (2026-03-17)

This session focused on cabinet launch reliability from the LaunchBox LoRa panel. The main outcome was hardening the shared backend launch spine so platform-specific launch behavior no longer falls through to generic LaunchBox fallback when a direct path is actually required.

### Daphne / Laserdisc Launch Spine
- Added a dedicated `SINGE2` direct-launch path in `backend/services/launcher.py`.
- Corrected `SINGE2` dispatch so it keys off `ApplicationPath` containing `\SINGE2\` instead of a nonexistent `platform_key == "singe2"` value.
- Injected `SDL_VIDEODRIVER=windows` into the `SINGE2` subprocess environment to avoid the known render-driver failure on backend-launched Singe titles.
- Added a dedicated `SINGE-HYPSEUS` block so Daphne entries routed through `\SINGE-HYPSEUS\` no longer fall through to `LaunchBox.exe`.
- Added dedicated American Laser Games handling so Gun Build `.ahk` launchers resolve correctly through AutoHotkey and `.cue` outliers fail gracefully with a clear backend message.
- Added `sdq` and `tq` alias keys to the Daphne Hypseus map so `Super Don Quix-ote` and `Thayer's Quest` work even when LaunchBox points directly at framefiles instead of `.ahk` stems.

### Gun Platform Routing
- Fixed gun-platform detection to happen before `normalize_key()` strips `Gun Games` from platform names.
- Added Gun Build RetroArch override support so RetroArch-backed gun platforms route to `A:\Gun Build\Emulators\RetroArch\retroarch.exe` instead of the default gamepad RetroArch instance.
- Added graceful backend failure for currently unsupported direct gun platforms instead of silent LaunchBox fallback.
- Added a Gun Build-safe NES core path by wiring `NES Gun Games` to `fceumm` and adding the missing core mapping in `config/launchers.json`.
- Verified `Duck Hunt` and `Baby Boomer` launching through the Gun Build RetroArch path from LoRa after the core-routing fix.

### Sega Model 2 / Model 3
- Fixed Sega Model 2 command construction so the emulator receives the ROM driver name instead of a full ZIP path.
- Validated Sega Model 3 / Supermodel launch behavior against the local Supermodel runtime and README.
- Aligned both detected-emulator and direct Supermodel paths around the working contract: launch from the emulator directory and pass the absolute ROM ZIP path on the command line.
- Re-verified live backend command output for `Dirt Devils`, `Virtua Fighter 3`, and `Sega Rally 2` after the Model 3 corrections.

### Verification
- Repeated targeted `py_compile` checks passed for the launcher and adapter files touched during the session.
- Repeated live backend launch probes were run through `http://127.0.0.1:8000/api/launchbox/launch/...` to confirm command construction after each fix.
- Confirmed working live launch paths from LoRa for representative titles across the repaired slices, including `Asterix - Mansion of the Gods`, `Dragon Trainer`, `Duck Hunt`, and `Baby Boomer`.

---

## Session Update (2026-03-16)

This session focused on persona stabilization, duplication-readiness cleanup, and runtime-path verification across the assistant roster. Several panels that previously relied on frontend-only prompts, dead routes, placeholder cabinet IDs, or half-wired flows now follow the backend/state architecture more cleanly.

### Dewey
- Externalized Dewey's main system prompt into `prompts/dewey.prompt` and added `prompts/dewey_knowledge.md`.
- Added backend chat route `POST /api/local/dewey/chat` in `backend/routers/dewey.py` so the main Dewey panel no longer calls the AI provider directly from the browser.
- Updated `frontend/src/panels/dewey/DeweyPanel.jsx` to stream from the backend route while preserving gallery parsing, lore search, routing chips, trivia mode, and handoff behavior.
- Added real LaunchBox-backed "Your Collection" trivia generation via `get_collection_sample()` and `POST /api/local/dewey/trivia/collection` in `backend/routers/dewey.py`.
- Updated `frontend/src/panels/dewey/trivia/TriviaExperience.jsx` so only the `collection` category uses the new endpoint and shows a friendly library-unavailable message when LaunchBox cache is not available.
- Hardened Dewey device identity usage by replacing direct fallback headers with guarded `window.AA_DEVICE_ID` resolution, corrected the knowledge doc route reference, and added a TODO note on Dewey's hardcoded frontend voice override in `ttsClient.js`.

### Vicky
- Fixed the opt-in / consent gate in `frontend/src/panels/voice/VoicePanel.jsx` so it now checks both stored consent and the saved primary profile.
- Fixed the Vicky sidebar header icon encoding by replacing garbled literals with escaped Unicode values.
- Repaired the Save & Broadcast path in `VoicePanel.jsx`; the payload now includes `display_name`, `initials`, `player_position`, `controller_assignment`, `custom_vocabulary`, and `consent_active`, and the frontend logs broadcast completion.
- Extended `backend/routers/profile.py` so `primary_user.json` now persists the extra Vicky fields instead of dropping them.
- Standardized Vicky cabinet identity fallbacks in the Voice panel and `frontend/src/services/profileClient.js`, and kept the Vicky ElevenLabs restoration as an explicit TODO note in `ttsClient.js`.

### Controller Chuck
- Fixed the dead SCAN route in `frontend/src/panels/controller/ControllerChuckPanel.jsx` to use the real hardware endpoint `/api/local/hardware/arcade/boards`.
- Fixed the dead DETECT flow in `frontend/src/hooks/useInputDetection.js` to use the real start / latest / stop input-detection routes.
- Corrected the PacDrive board identity mismatch in `config/mappings/controls.json` so Chuck no longer identifies an Xbox 360 VID/PID as the cabinet encoder board.
- Added production-fleet TODO markers for dormant `CAB-0001` usage in Chuck helper files.
- Repaired the active mapping flow: successful input capture now sets `hasPending`, preview/apply payloads now match the backend mapping schema, `MappingOverlay.jsx` is mounted into the active Chuck panel, and the panel reloads mapping after save.

### Gunner
- Confirmed and preserved the real scan path: `handleScan()` now uses `gunnerClient.listDevices()` rather than a stub.
- Added `prompts/gunner_knowledge.md` so Gunner no longer runs without its knowledge file.
- Standardized Gunner cabinet identity fallback handling in `frontend/src/services/gunnerClient.js`.
- Flagged placeholder MAC/fleet display values in `frontend/src/components/gunner/GunnerHeader.jsx`.
- Added visible in-UI amber notices and console warnings to the currently unwired modular Gunner tabs: `CalibrationTab.jsx`, `ProfilesTab.jsx`, and `RetroModesTab.jsx`.

### LaunchBox LoRa / ScoreKeeper Sam / LED Blinky
- Updated LoRa chat identity in `frontend/src/panels/launchbox/LaunchBoxPanel.jsx` to use the cabinet UUID path instead of a browser-local cloned session ID.
- Replaced Sam-related `demo_001` cabinet defaults in `useAIAction.ts` and `scorekeeperClient.js`, and flagged dormant `CAB-0001` defaults in `gateway/gems/aa-sam/index.js`.
- Added the missing gateway scorekeeper route so MAME hiscore Supabase mirroring no longer posts to a dead endpoint.
- Wired `backend/services/game_lifecycle.py` so LEDBlinky is notified on the common game lifecycle path for both launch and exit.

### Audit / Verification Work
- Completed read-only runtime audits for LoRa, ScoreKeeper Sam, LED Blinky, Controller Chuck, Gunner, Dewey, and Vicky.
- Verified actual request paths, prompt locations, storage locations, duplication blockers, and places where frontend assumptions diverged from real backend behavior.
- Used those audits to close several small but important duplication risks: hardcoded cabinet IDs, dead panel routes, stale prompt/knowledge references, and schema gaps between frontend payloads and persisted state.

### Validation
- Frontend builds passed after the panel and client changes.
- Targeted backend syntax checks passed for the scoped Python files touched during the session, including `backend/services/game_lifecycle.py` and `backend/routers/profile.py`.

---

## Persona Roster

| # | Persona | Panel File | EB Sidebar | TTS |
|---|---------|-----------|------------|-----|
| 1 | **Dewey** (Arcade Historian) | `panels/dewey/` | N/A (custom) | Ã¢Å“â€¦ ElevenLabs |
| 2 | **LaunchBox LoRa** | `panels/launchbox/` | Ã°Å¸â€Â¶ Stub | Ã¢Å“â€¦ ElevenLabs |
| 3 | **ScoreKeeper Sam** | `panels/scorekeeper/` | N/A | Ã¢Å“â€¦ ElevenLabs |
| 4 | **Controller Chuck** | `panels/controller/` | Ã¢Å“â€¦ Standardized | Ã¢Å“â€¦ ElevenLabs |
| 5 | **LED Blinky** | `components/led-blinky/` | Ã¢Å“â€¦ Standardized | Ã¢Å“â€¦ ElevenLabs |
| 6 | **Gunner** | `components/gunner/` | Ã¢Å“â€¦ Standardized | Ã¢Å“â€¦ ElevenLabs |
| 7 | **Console Wizard** | `panels/console-wizard/` | Ã¢Å“â€¦ Standardized | Ã¢Å“â€¦ ElevenLabs |
| 8 | **Vicky** (Voice) | `panels/voice/` | Ã¢Å“â€¦ Standardized | Ã¢Å“â€¦ ElevenLabs |
| 9 | **Doc** (Diagnostics) | `panels/system-health/` | Ã¢Å“â€¦ Standardized | Ã¢Å“â€¦ ElevenLabs |

Route: `http://127.0.0.1:8787/assistants?agent=chuck` (replace `chuck` with persona ID)

---

## Controller Chuck Ã¢â‚¬â€ Current State (as of 2026-03-03)

The most actively developed panel. Status: **Diagnosis Mode Phase 1 + Standardized Sidebar + Gemini AI.**

### Implemented
- **4P / 2P mode switcher** Ã¢â‚¬â€ identical compact card sizing in both modes
- **FLIP focus animation** Ã¢â‚¬â€ click any player card, it springs from its exact grid corner to the panel center (`getBoundingClientRect()` + CSS vars `--flip-x/y/w`, spring easing `cubic-bezier(0.34, 1.56, 0.64, 1)`)
- **Premium return animation** Ã¢â‚¬â€ card breathes out to scale(1.52) then dissolves back to its grid corner
- **Directional arrow overlay + Button click-to-map** Ã¢â‚¬â€ SVG arrows, cyan pulse while waiting for cabinet input
- **Mapping confirmation animations** Ã¢â‚¬â€ physical press Ã¢â€ â€™ `latestInput` Ã¢â€ â€™ white flash Ã¢â€ â€™ green ring burst Ã¢â€ â€™ `Ã¢Å“â€œ GPIO XX` badge
- **Top strip** Ã¢â‚¬â€ SCAN + DETECT buttons visible in both 2P and 4P modes

### Diagnosis Mode (Phase 1 Ã¢â‚¬â€ 2026-03-02)
Diagnosis Mode is a context-aware, config-writing co-pilot mode. Toggle the amber pill in the Chuck sidebar header to activate.

**Frontend:**
| File | Role |
|------|------|
| `hooks/useDiagnosisMode.js` | Shared hook Ã¢â‚¬â€ toggle, TTS greeting, 30s context refresh, 5-min soft-lock |
| `chuckContextAssembler.js` | 3-tier context payload (<1500 tokens, Chuck-only) |
| `chuckChips.js` | 6 suggestion chips |
| `DiagnosisToggle.jsx/.css` | Amber pill toggle with animated thumb |
| `ContextChips.jsx/.css` | Horizontal scrollable amber chip bar |
| `MicButton.jsx/.css` | Push-to-talk, 0.7 confidence threshold, ripple rings |
| `ChuckSidebar.jsx` | Full chat panel Ã¢â‚¬â€ assembles all components |
| `chuck-sidebar.css` | Amber left-border pulse in Diagnosis Mode |
| `chuck-layout.css` | Flex layout: player grid + sidebar side-by-side |

**Backend:**
| File | Role |
|------|------|
| `services/controller_bridge.py` | `ControllerBridge` Ã¢â‚¬â€ sole GPIO merge authority, 5-step atomic commit, 4 conflict types, sacred law validation, rollback |
| `routers/controller.py` | `POST /api/profiles/mapping-override` Ã¢â‚¬â€ 2-phase proposal+commit |
| `services/chuck/ai.py` | `remediate_controller_config()` Ã¢â‚¬â€ Gemini 2.0 Flash AI tool |

**Sacred Button Law (immutable):**
```
P1/P2: Top row Ã¢â€ â€™ 1, 2, 3, 7  |  Bottom row Ã¢â€ â€™ 4, 5, 6, 8
P3/P4: Top row Ã¢â€ â€™ 1, 2         |  Bottom row Ã¢â€ â€™ 3, 4
```
This is the Rosetta Stone for all 45+ emulator configs. `ControllerBridge` hard-blocks any deviation.

### Pending / Next
- Assign correct ElevenLabs voice ID for Chuck (`CHUCK_VOICE_ID` in `.env`)
- Diagnosis Mode Phase 2: Supabase tables (`controller_mappings`, `encoder_devices`, `controller_mappings_history`)
- Cascade diff UI inside the Diagnosis Mode sidebar
- Wire real hardware data into `chuckContextAssembler.js`

### Key Files
```
frontend/src/panels/controller/
  Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ ControllerChuckPanel.jsx     Ã¢â€ Â Main component (FLIP, state machine, PlayerCard)
  Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ ChuckSidebar.jsx             Ã¢â€ Â Chat panel + Diagnosis Mode
  Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ controller-chuck.css         Ã¢â€ Â All animations, 2P/4P layout
  Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ chuck-sidebar.css            Ã¢â€ Â Sidebar styles (amber in diag mode)
  Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ chuck-layout.css             Ã¢â€ Â Flex layout wrapper
  Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ DiagnosisToggle.jsx/.css     Ã¢â€ Â Amber pill toggle
  Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ ContextChips.jsx/.css        Ã¢â€ Â Suggestion chips
  Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ MicButton.jsx/.css           Ã¢â€ Â Push-to-talk
  Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ chuckContextAssembler.js     Ã¢â€ Â 3-tier context builder
  Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ chuckChips.js                Ã¢â€ Â Chip definitions

backend/
  Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ services/controller_bridge.py   Ã¢â€ Â GPIO merge authority
  Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ routers/controller.py           Ã¢â€ Â mapping-override endpoint
  Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ services/chuck/ai.py            Ã¢â€ Â remediate_controller_config tool
```

---

## LED System

- **Stack**: Python ctypes driver (`ledwiz_direct.py`) speaks directly to Windows HID Ã¢â‚¬â€ **no node-hid, no LEDBlinky dependency for color control**
- **LEDBlinky.exe**: Still used for per-game profiles via subprocess call
- **PWM Safety**: All values clamped 0Ã¢â‚¬â€œ48 (49Ã¢â‚¬â€œ129 triggers strobe/crash modes)
- **Boards**: 3Ãƒâ€” LED-Wiz units auto-discovered on startup
- **Gamma**: 2.5 correction + Electric Ice color balance (Red 65%, Blue 75%, Green 100%)

---

## Marquee System (Third Screen)

The marquee display shows game artwork/videos on a secondary monitor (the physical cabinet marquee). Two implementations exist:

| Component | Type | File | Notes |
|-----------|------|------|-------|
| Python Watcher | Standalone tkinter app | `scripts/marquee_display.py` | Borderless fullscreen on secondary monitor, file-watches `.aa/state/marquee_current.json` |
| React Display | Browser route | `frontend/src/panels/marquee/MarqueeDisplayV2.jsx` | Route: `/marquee-v2`, launched via button in Content Display Manager |
| Preview Hook | Batch script | `scripts/aa_marquee_preview.bat` | Called by Pegasus on game scroll |
| Backend API | FastAPI router | `backend/routers/marquee.py` | Config, media resolution, message queue, now-playing |

**Auto-Launch:** `start-aa.bat` on the A: drive launches `marquee_display.py` automatically via `AA_MARQUEE_ENABLED` env var.

> ⚠️ **TEMPORARILY DISABLED (2026-03-16):** `AA_MARQUEE_ENABLED=0` in `start-aa.bat` on A: drive.
> The Python marquee display opens a borderless, topmost, fullscreen black window on the secondary monitor.
> On a dev machine with a regular second monitor, this blacks out the screen with no close button.
> **RE-ENABLE before drive duplication for live cabinet hardware** — the cabinet will have a dedicated marquee display.
> Future improvement: add GUI toggle in Content Display Manager to enable/disable at runtime.

---

## Supabase Edge Functions

| Function | JWT Verify | Purpose |
|----------|-----------|---------| 
| `anthropic-proxy` | OFF | Claude API proxy |
| `elevenlabs-proxy` | OFF | TTS proxy |
| `openai-proxy` | OFF | GPT proxy |
| `gemini-proxy` | OFF | Gemini proxy |
| `admin-gateway` | ON | Admin operations |

---

## Known Issues / Open Items

| Issue | Priority | Notes |
|-------|----------|-------|
| LED Blinky panel + RAG KB | High | Primary target -- arbiter built, needs frontend + sidebar |
| Gunner Phase 2 | Medium | Calibration tab, profiles tab, retro modes |
| Doc (Diagnostics) panel | Medium | Full system diagnostic panel |
| B6/B7 Wake Word & TTS Dropping | Medium | Voice panel fixes |
| Handoff Protocol URL standard | Medium | Inter-panel communication |
| Diagnosis Mode Phase 2 (Supabase tables) | Medium | `controller_mappings`, `encoder_devices`, `controller_mappings_history` |
| Marquee auto-launch disabled (dev) | Low | `AA_MARQUEE_ENABLED=0` in A: `start-aa.bat` — re-enable before duplication |
| F9 Overlay Z-Index | Backlog | Electron `setAlwaysOnTop` |
| LaunchBox LoRa deep build | Backlog | Most complex panel -- future session |

### Recently Closed Blockers (2026-03-12)
| Blocker | Fix | File |
|---------|-----|------|
| Gateway stale `index.html` | `sendSpaShell()` re-reads per request, `no-store` + `X-AA-SPA-Build` | `gateway/server.js` |
| `blinky/__init__.py` eager imports | Pure `__getattr__` lazy exports via `importlib` | `blinky/__init__.py` |
| Dewey News Chat verification | Resolved by SPA shell fix | `gateway/server.js` |
| TTS echo on Dewey exit | Verified working after stale-cache fix | `main.cjs` |

### Previously Closed (2026-03-05)
| Blocker | Fix | File |
|---------|-----|------|
| B2 -- HttpBridge outbound | `NotifyBackendGameStart()` fire-and-forget POST | `HttpBridge.cs` |
| B4 -- Voice Hardware Unlock | `_sync_led_state()` + Supabase fleet mirroring | `voice/service.py` |
| B5 -- Genre LED Animation | `GENRE_ANIMATION_MAP` (8 genre codes) | `game_lifecycle.py` |
| Console Wizard RAG KB | `wiz_knowledge.md` (500+ lines) + enhanced prompt | `prompts/` |
| LED Priority Arbiter | Circuit breaker (VOICE>GAME>ATTRACT>IDLE) + throttle | `led_priority_arbiter.py` |

### Parked Post-V1 Follow-Ups (2026-03-14)
| Item | Priority | Notes |
|------|----------|-------|
| `app.py` double-mount cleanup | Medium | Doc and Gunner routers are each mounted twice; defer cleanup until after V1 |
| Chuck shared-sidebar parity | Medium | Legacy `ChuckSidebar` still has greeting hooks, Supabase chat logging, and legacy mic path not exposed by `EngineeringBaySidebar` |
| Genre tag propagation into lifecycle tracking | High | `aa_launch.py` and `launchbox.py` do not forward `tags` into `track_game_launch()` yet; genre-aware LED mapping will not fire from those launch paths until fixed |

---

## Duplication-Readiness Master Checklist

> This tracks everything needed to clone the A: drive and have it boot on new hardware as a working Arcade Assistant cabinet.

### Code-Complete (Codex -- verified by Antigravity audit 2026-03-12)

| # | Item | Status | Key File(s) |
|---|------|--------|-------------|
| 1 | First-boot identity provisioning (UUID -> `.aa/device_id.txt`) | DONE | `cabinet_identity.py`, `bootstrap_local_cabinet.py` |
| 2 | Cabinet manifest sync (`.aa/cabinet_manifest.json`) | DONE | `cabinet_identity.py` |
| 3 | Controls skeleton bootstrap (`config/mappings/controls.json`) | DONE | `cabinet_identity.py` |
| 4 | Device ID resolution chain (file -> manifest -> env) | DONE | `cabinet_identity.py`, `cabinetIdentity.js` |
| 5 | Startup manager calls `ensure_local_identity()` | DONE | `startup_manager.py` |
| 6 | Provisioning status endpoint | DONE | `system.py` (`GET /api/local/system/provisioning_status`) |
| 7 | `start-aa.bat` serve-only (no build on boot) | DONE | `start-aa.bat` |
| 8 | `start-aa.bat` drive letter auto-detect via `%~d0` | DONE | `start-aa.bat` |
| 9 | SPA shell cache-busting (`no-store`, `X-AA-SPA-Build`) | DONE | `server.js` |
| 10 | SPA shell device ID injection (`window.AA_DEVICE_ID`) | DONE | `server.js`, `cabinetIdentity.js` |
| 11 | `prepare_golden_image.bat` (clean build + hash verify) | DONE | `scripts/prepare_golden_image.bat` |
| 12 | `clean_for_clone.bat` (preserves dist, node_modules, manifest) | DONE | `clean_for_clone.bat` |
| 13 | `.env` label sanitization (DEVICE_NAME -> generic) | DONE | `clean_for_clone.bat` |
| 14 | Blinky lazy imports (no HID/XML at import) | DONE | `blinky/__init__.py` |
| 15 | Electron overlay documented as separate launch | DONE | `frontend/electron/main.cjs` |
| 16 | Provisioning test suite (3 tests) | DONE | `test_cabinet_provisioning.py` |
| 17 | SPA shell contract test | DONE | `spa_shell.spec.js` |
| 18 | TTS proxy-first (Supabase, no direct ElevenLabs key required) | DONE | `.env`, `tts.js` |

### Hardware Validation Required (live cabinet)

| # | Item | Status | Notes |
|---|------|--------|-------|
| H1 | Clone simulation: remove identity -> boot -> verify new UUID + current frontend | PENDING | Core smoke test |
| H2 | LoRa game launch flow (pick game -> launch -> exit) | PENDING | |
| H3 | Daphne/Hypseus real launch | PARTIAL | Road Blaster confirmed via LoRa direct launch. Astron Belt, Dragon's Lair HD still need spot-check. SINGE2 games separate fix. |
| H4 | 8BitDo physical gamepad mapping + cascade | PENDING | Gamepad API + wizard flow |
| H5 | F9 Electron overlay inside Big Box fullscreen | PENDING | |
| H6 | Console Wizard emulator config generation | PENDING | |
| H7 | Vicky Voice + LED priority arbiter live test | PENDING | |
| H8 | ScoreKeeper Sam live session (MAME exit -> score -> leaderboard) | PENDING | |
| H9 | Controller Chuck mapping flow on arcade panel | PENDING | |

### Separate Effort (not Codex)

| # | Item | Status | Notes |
|---|------|--------|-------|
| S1 | Supabase Service Role Key handling on golden image | PENDING | Sanitize, replace, or provision |
| S2 | Device ID mismatch fix (`.env` vs Supabase `00000000-...`) | PENDING | Us or admin portal |
| S3 | ElevenLabs placeholder API key replacement | PENDING | |
| S4 | Drive letter `A:\` auto-detection robustness | DONE | `start-aa.bat` uses `%~d0` |
| S5 | Re-enable marquee auto-launch (`AA_MARQUEE_ENABLED=1`) | PENDING | Disabled 2026-03-16 for dev — re-enable before golden image |

---
## Git / Deployment

```powershell
# Standard commit + push
git add .
git commit -m "Description"
git push origin master
```

**Remote:** `https://github.com/ggarcadeV4/Arcade-Assistant-Basement-Build.git`
**Branch:** `master` (always)

> Ã¢Å¡Â Ã¯Â¸Â A: drive is a USB drive Ã¢â‚¬â€ large `git commit` operations can take 5+ minutes. This is normal.

---

## Session History

See `ROLLING_LOG.md` for a reverse-chronological log of all sessions and net progress.
See `logs/` directory for daily session logs.

### Session Catalog - 2026-03-16 NIGHT (Daphne/Hypseus Laserdisc Fix)

Scope completed in this session focused on getting Daphne laserdisc games launching from LoRa.

Key outcomes:

- **Daphne Launch Fix (4-layer cascade)**:
  - DLL path fix: `.ahk` scripts pointed to bare copy of `hypseus.exe` without DLLs. Redirected to `A:\Emulators\Hypseus\Hypseus Singe\hypseus.exe`.
  - Homedir fix: Added `-homedir "A:\Roms\DAPHNE"` so Hypseus finds ROM zips in `roms/` and framefiles in `framefile/`.
  - Absolute framefile paths: Hypseus resolves `-framefile` relative to its own exe, not `-homedir`. Changed to absolute paths.
  - SDL video driver fix: Subprocess inherits headless SDL context (driver=dummy). Added `SDL_VIDEODRIVER=windows` env override.

- **LoRa Direct Launch Block** (NEW, `launcher.py:1100-1156`):
  - Added `DAPHNE_GAME_MAP` with 15 game entries mapping `.ahk` stems to Hypseus internal names + framefile paths.
  - HD titles (Dragon's Lair, Dragon's Lair II, Space Ace) use `vldp\` paths.
  - Uses `_launch_with_stderr_trap()` matching adjacent MAME block pattern.
  - Passes `SDL_VIDEODRIVER=windows` in subprocess environment.

- **LaunchBox Plugin Port**: Fixed `config.json` port from `10099` to `9999`.

- **Discovery — HD titles are Additional Apps**: Dragon's Lair HD / Space Ace HD / Dragon's Lair II HD are "Additional App" entries (alternate launch) in `Daphne.xml`, not primary `ApplicationPath`. From LoRa, the primary launch uses `SINGE-HYPSEUS\*.ahk` scripts.

- **Discovery — SINGE2 games on Daphne platform**: ~30 SINGE2 games (Altered Carbon, Asterix, Cliffhanger, etc.) are filed under the Daphne platform in LaunchBox. These use `Singe.exe` and are a separate fix path.

Files modified (by Codex, verified by Antigravity):

- `A:\Roms\DAPHNE\*.ahk` (all 15) — exe path, `-homedir`, framefile paths
- `A:\LaunchBox\Data\Emulators.xml` — Hypseus Singe entry added
- `A:\LaunchBox\Plugins\ArcadeAssistant\config.json` — port fix
- `backend/services/launcher.py` — Daphne direct launch block

Validation completed:

- Road Blaster confirmed launching from LoRa with video rendering.
- All 15 framefile paths verified on disk.
- All 15 `.ahk` stems match `DAPHNE_GAME_MAP` keys.

Open follow-ups:

- Spot-check Astron Belt (standard framefile) and Dragon's Lair HD (vldp path).
- SINGE2 platform fix (separate task — different emulator, different error).
- HD title accessibility from LoRa (Additional Apps not exposed).

### Session Catalog - 2026-03-14

Scope completed in this session focused on closing Sprint 1 and Sprint 2 production-consistency work.

Key outcomes:

- **Sprint 1 completed**:
  - Doc diagnostics router upgraded to full 4-endpoint coverage:
    - `GET /api/doc/bio`
    - `GET /api/doc/vitals`
    - `GET /api/doc/alerts`
    - `WS /api/doc/ws/events`
  - `/vitals` now returns the full contract with defensive null-on-failure handling and exported `broadcast_health_event()` support.
  - Doc diagnostics tests passed (`4 passed`).
  - Added `scripts/generate_device_id.py` for idempotent UUID4 generation and persistence.
  - Gunner hardening completed:
    - Empty scan now shows a real empty state instead of fallback mock cards.
    - Backend device objects are mapped into the `DeviceCard` display shape.
    - `MockDetector` now activates only when `ENVIRONMENT=dev` and `AA_USE_MOCK_GUNNER=true`.

- **Sprint 2 completed**:
  - Chuck panel verification confirmed the active panel already renders `EngineeringBaySidebar`; Chat Mode and Diagnosis Mode remain intact, so no Chuck swap was required.
  - LEDBlinky genre-aware animation path completed:
    - Arbiter fire callback now registers from `game_lifecycle.py`, so LED commands are no longer silently dropped.
    - Genre mapping now uses production codes:
      - `LED:FIGHTING -> 3`
      - `LED:RACING -> 4`
      - `LED:SHOOTER -> 2`
      - `LED:SPORTS -> 5`
      - default `-> 1`
    - LED engine now supports `idle_pulse`, `breathe`, and `knight_rider`.
    - `idle_pulse` and `breathe` alias to the existing pulse renderer.
  - `updates.py` Phase 0 TODO stubs were replaced with a full staged update pipeline:
    - check -> download -> verify -> stage -> apply
    - rollback -> snapshot -> restore
    - `AA_UPDATES_ENABLED=0` returns a clean disabled response
    - all operations log to `.aa/logs/updates.log`

Validation completed:

- Frontend build passed (`npm run build:frontend`).
- Doc diagnostics backend tests passed (`4 passed`).

Open follow-ups for next session:

- Dedicated cleanup pass for the Doc/Gunner double-mount in `app.py` after V1.
- Dedicated `EngineeringBaySidebar` parity pass for Chuck legacy-only hooks after V1.
- Fix tag propagation from `aa_launch.py` and `launchbox.py` into `track_game_launch()` before V1 ship.

### Session Catalog - 2026-03-15

Scope completed in this session focused on V1 closeout: marquee completion, score-ops awareness, cabinet identity hardening, and final backend wiring passes.

Key outcomes:

- **Marquee system completed (Sessions A-C)**:
  - Unified marquee config/state contract across backend router, content manager, and desktop renderer via shared `backend/models/marquee_config.py`.
  - Generic `game_start` now pushes marquee game state and generic `game_stop` now returns marquee to idle.
  - Idle display now honors configured `idle_video` and `idle_image` instead of falling straight to black.
  - `scripts/marquee_display.py` now consumes `marquee_preview.json`, respects preview-vs-active-game priority, and restores current content when preview clears.
  - Added polling fallback when watchdog is unavailable.
  - Added single-instance guard (`.aa/marquee.lock`) plus boot launch orchestration from `start-aa.bat`.
  - Replaced the three content manager marquee test stubs with real behavior:
    - `POST /api/content/marquee/test/image`
    - `POST /api/content/marquee/test/video`
    - `POST /api/content/marquee/test/browse`
  - LaunchBox parser cache now stores `video_snap_path` and `marquee_image_path`, and marquee resolution now checks cached paths before filesystem scans.

- **ScoreKeeper Sam operational awareness expanded**:
  - Added `prompts/sam_knowledge.md` so Sam now understands score tracking strategy resolution, review queue flow, MAME hiscore watching, Lua fallback, OCR capture, announcer behavior, and Supabase sync.
  - Replaced the static "PTS TO BEAT" banner in the Sam panel with live top-score data.
  - Added `GET /api/local/scorekeeper/top-score` with Supabase-first lookup and `scores.jsonl` local fallback.

- **Diagnostics and cabinet identity hardening**:
  - Doc diagnostics audit closed with per-device latency support added to `GET /api/doc/bio` and `GET /api/doc/vitals`.
  - `AA_DEVICE_ID` first-boot generation is now idempotent:
    - missing or placeholder `.aa/device_id.txt` generates a fresh UUID4
    - `.env` is updated atomically
    - startup sets `os.environ["AA_DEVICE_ID"]` before downstream services use it

- **Engineering Bay and LED production wiring**:
  - Gunner "SCAN HARDWARE" now calls the real backend device listing path and renders live device results instead of placeholder cards.
  - Chuck now uses the shared `EngineeringBaySidebar`; the dead standalone `ChuckSidebar.jsx` file was removed.
  - PatternResolver initialization in `app.py` now runs as a non-blocking background task instead of being skipped.
  - LED priority arbiter fire callback is now registered, so arbiter output no longer drops silently.
  - Vicky voice acknowledgment now triggers a brief VOICE-priority LED flash through the arbiter.
  - LEDBlinky launch animation selection now resolves by genre instead of always defaulting to static ON.

- **Remote update and rollback pipeline completed**:
  - `update_assistant.py` now supports gated download -> verify -> snapshot -> apply -> rollback handling for Fleet Manager `DOWNLOAD_UPDATE` commands.
  - Rollback snapshots protect cabinet identity/runtime state and restore the critical app directories.
  - All public update entry points respect `AA_UPDATES_ENABLED`.

Validation completed:

- Frontend build passed during panel integration work (`npm run build:frontend`).
- Targeted backend tests passed for:
  - doc diagnostics
  - cabinet identity provisioning
  - marquee/parser syntax checks
  - LED translator coverage
  - update assistant pipeline

Open follow-ups for next session:

- Live second-monitor marquee validation on cabinet hardware (preview, idle video, launch switch, stop-to-idle).
- Live hardware validation remains for H1-H9 items in the duplication-readiness checklist.
- Dedicated cleanup pass for the Doc/Gunner double-mount in `app.py` after V1.
- Tag propagation from `aa_launch.py` and `launchbox.py` into `track_game_launch()` still needs a dedicated pass before final V1 ship.

### Session Catalog - 2026-03-08

Scope completed in this session focused on Dewey overlay and F9 behavior:

- Routed overlay mode directly to Dewey (`/assistants?agent=dewey&mode=overlay`) instead of Home.
- Added stable overlay singleton behavior in Electron to avoid duplicate competing instances.
- Hardened F9 handling with debounce + dual trigger paths:
  - Electron global shortcut path.
  - Backend hotkey WebSocket fallback (`/ws/hotkey`).
- Expanded overlay-allowed process detection to include `BigBox.exe` and `LaunchBox.exe`.
- Added backend auto-bootstrap for Dewey overlay on hotkey events when overlay is not already running.
- Removed legacy `HotkeyOverlay` pause UI mount from app shell to prevent old pause-menu flash conflicts.
- Made hotkey manager idempotent (no duplicate callback registration / duplicate start).
- Added top-right `X` close button in compact Dewey overlay.
- Implemented overlay command protocol:
  - `__overlay_cmd=hide` closes compact Dewey overlay.
  - `__overlay_cmd=expand&target=...` expands overlay to full-screen and opens handoff panel.
- Updated Dewey chip handoff behavior:
  - In overlay mode, chip clicks now expand to full-screen target panel (e.g., Control-a-Wizard) instead of staying compact.

Files touched for this scope:

- `frontend/src/App.jsx`
- `frontend/src/panels/dewey/DeweyPanel.jsx`
- `frontend/electron/main.cjs`
- `backend/routers/hotkey.py`
- `backend/services/hotkey_manager.py`
- `backend/services/activity_guard.py`
- `backend/routers/launchbox.py`

Validation completed:

- Frontend build passed (`npm run build:frontend`).
- Electron script syntax check passed (`node --check frontend/electron/main.cjs`).

Open follow-ups for next session:

- Verify F9 reliability end-to-end in true Big Box fullscreen on basement hardware.
- If fullscreen hook contention remains, add dedicated fallback hotkey/channel for forced Dewey bring-up.
- Final UX polish for compact-vs-fullscreen transitions and close/restore behavior.

### Session Catalog - 2026-03-09 (Night Closeout)

Scope completed in this session focused on Dewey stability, LaunchBox LoRa reliability, and launch-path hardening.

Key outcomes:

- Dewey voice/chat behavior stabilized for live use:
  - Resolved repeated ElevenLabs loop/replay behavior.
  - Improved stop/cancel behavior when closing Dewey contexts.
  - Prioritized microphone interruption so user speech can override long assistant playback.
  - Tuned responses toward shorter, tighter output.
- Dewey handoff UX improved:
  - Chip handoff flow now supports compact-to-fullscreen transition behavior for target panels.
  - Overlay close/exit control flow hardened for better user control.
- LaunchBox LoRa stabilization pass:
  - Added LaunchBox panel error boundary.
  - Removed dead mock data and cleaned text-encoding artifacts.
  - Consolidated duplicate chat send logic into a single voice-aware send path.
  - Expanded sort options and tightened platform launch gating.
  - Added memo component `displayName` metadata and resolved runtime render regressions (including `fetchCacheStatus` reference issue).
- Launcher reliability improvements:
  - LaunchBox app launch path updated to target local LaunchBox executable directly.
  - Added AHK relaunch cooldown guard to avoid duplicate-script instance popups on rapid repeat launch.
  - Implemented selective Daphne migration to Hypseus:
    - For Daphne/Laserdisc `.ahk` wrappers that call `daphne.exe`, backend now routes to `hypseus.exe` directly.
    - Singe-oriented wrappers remain on AHK path to avoid regressions.
  - Verified via diagnostics endpoint:
    - `BadLands` resolves to Hypseus direct launch config.
    - `Cliff Hanger HD` remains on AHK/Singe path as intended.

Key files touched in this scope:

- `frontend/src/panels/dewey/DeweyPanel.jsx`
- `frontend/electron/main.cjs`
- `frontend/src/panels/launchbox/LaunchBoxPanel.jsx`
- `frontend/src/panels/launchbox/LaunchBoxErrorBoundary.jsx`
- `backend/routers/hotkey.py`
- `backend/services/hotkey_manager.py`
- `backend/services/activity_guard.py`
- `backend/routers/launchbox.py`
- `backend/services/adapters/direct_app_adapter.py`

Open follow-ups for next session:

- Validate F9 behavior inside true Big Box fullscreen conditions on basement hardware.
- If needed, extend Hypseus migration to additional wrapper formats after smoke-test confirmation.
- Final LaunchBox LoRa visual polish pass (icon/readability consistency).
- Continue queued panel work: LED Blinky depth pass, Gunner logic audit, and Doc telemetry expansion.

### Session Catalog - 2026-03-10

Scope completed in this session focused on laying the first trustworthy universal score-tracking foundation for ScoreKeeper Sam.

Key outcomes:

- Added a canonical score-tracking service and persistent score-attempt pipeline:
  - Introduced canonical session records for launches coming from Arcade Assistant, LoRa, and LaunchBox/plugin paths.
  - Added score strategy resolution with primary/fallback modes:
    - `mame_hiscore`
    - `mame_lua`
    - `file_parser`
    - `vision`
    - `manual_only`
  - Added persistent `ScoreAttempt` records separate from final leaderboard rows.
  - Added session reuse logic so duplicate launch reports merge into the same active session instead of creating silent orphan sessions.
- Unified launch-path integration:
  - LaunchBox router launches now pass richer session metadata into the lifecycle tracker.
  - AA direct launches now pass source/method metadata into the same tracker.
  - Plugin/native start-stop bridge now feeds the same canonical score pipeline used by AA/LoRa launches.
- Re-enabled MAME watcher startup in backend app lifespan:
  - Hiscore watcher startup is active again.
  - Lua score watcher startup is active again.
- Added review and coverage APIs for Sam:
  - Coverage summary endpoint for tracked vs pending vs unsupported counts.
  - Review queue endpoint for pending/failed score attempts.
  - Review action endpoint for approve/edit/reject/mark-unsupported flows.
- Added ScoreKeeper Sam operator UI:
  - Coverage dashboard block in the Sam panel.
  - Manual review queue block in the Sam panel.
  - Frontend actions for approving or marking attempts unsupported.
- Added initial backend tests for:
  - auto-captured score flow
  - manual review flow
  - duplicate active-session reuse

Key files touched in this scope:

- `backend/services/score_tracking.py`
- `backend/services/game_lifecycle.py`
- `backend/routers/scorekeeper.py`
- `backend/routers/game_lifecycle.py`
- `backend/routers/launchbox.py`
- `backend/routers/aa_launch.py`
- `backend/app.py`
- `backend/tests/test_score_tracking.py`
- `frontend/src/services/scorekeeperClient.js`
- `frontend/src/panels/scorekeeper/ScoreKeeperPanel.jsx`
- `frontend/src/panels/scorekeeper/scorekeeper.css`

Validation completed:

- Backend syntax checks passed on the edited score-tracking files.
- New backend tests passed: `3 passed`.
- Frontend build passed (`npm run build:frontend`).

Open follow-ups for next session:

- Live-verify native LaunchBox/plugin start-stop events against the new Sam pipeline.
- Live-verify MAME exit flow produces exactly one leaderboard update on cabinet hardware.
- Live-verify non-MAME vision captures land in `pending_review` when confidence is low.
- Confirm manual review approval from the Sam panel produces the expected final leaderboard entry without duplicates.
- Expand per-platform strategy overrides after real cabinet validation (Pinball, TeknoParrot, Daphne/Hypseus, Wii U, Steam-native families).

### Session Catalog - 2026-03-10 (Antigravity Lead Architect Contributions)

Scope completed in this session (Antigravity + Codex teamwork) focused on platform launch fixes, Supabase telemetry verification, and strategic planning.

Key outcomes:

- **Pinball FX2/FX3 Launch Fix** (Antigravity analysis + Codex execution):
  - Diagnosed disabled play button root cause: stale browser bundle (hash `912cd317` vs `6d4990f9`).
  - Codex implemented button visibility fix (`always-visible` class, `stopPropagation`) and Steam URI routing.
  - Both FX2 and FX3 now launch successfully from LoRa panel.

- **Supabase Telemetry Verification** (Antigravity):
  - Verified live connectivity to `zlkhsxacfyxsctqpvbsh`.
  - Confirmed tables: `cabinet`, `cabinet_heartbeat`, `cabinet_telemetry`, `cabinet_game_score` (DARIUS scores via `mame_hiscore`), `command_queue`.
  - Found Device ID mismatch: `.env` `1690afb0-...` vs Supabase `00000000-...-000000000001`.
  - ElevenLabs key confirmed as `placeholder-boot-only`.

- **Hypseus .exe Extension Fix** (Antigravity):
  - Diagnosed Rollercoaster AHK failure: `Run, Hypseus` (no `.exe`) vs `hypseus.exe` on disk.
  - Fixed `_parse_daphne_ahk_command` to try appending `.exe` when bare name doesn't exist.
  - All three parsers verified: Badlands (daphne.exe) âœ…, Conan (Singe.exe) âœ…, Rollercoaster (Hypseus.exe) âœ….

- **ScoreKeeper Sam Master Plan** (Antigravity + User):
  - Archived universal score tracking plan with 4-phase rollout.
  - Key principle: "every session gets an explicit outcome" (trustworthy-first).
  - Codex delivered Phases 1-2 code-complete â€” 5 days ahead of schedule.

- **Strategic Planning** (Antigravity + User):
  - Sprint timeline: drive finalization March 15, business infrastructure March 20, go-to-market April 1.
  - Golden drive sanitization: migrate dev artifacts to local environment before wiping A: drive.

Key files touched:

- `backend/services/adapters/direct_app_adapter.py` (Hypseus .exe extension fix)
- `codex-tasks/pinball-play-button-fix.md` (updated Codex handoff)
- `codex-tasks/daphne-live-test.md` (new Codex handoff)

Open follow-ups for next session:

- Live-test Badlands, Conan, Rollercoaster from LoRa (parser verified, needs backend restart + live run).
- Fix Device ID mismatch in `.env` or Supabase.
- Replace ElevenLabs placeholder API key.
- ScoreKeeper Sam live validation (MAME exit, plugin stop, vision capture, review approval).
- Golden drive sanitization script.

### Session Catalog - 2026-03-11 (Antigravity Session â€” ~4 hours)

Scope completed in this session focused on backend bug fixes, frontend gamepad controller configuration interface, and PNG+overlay digital twin system.

Key outcomes:

- **Backend Bug Fixes (App Launch)**:
  - Fixed `ScoreAttemptReviewRequest` NameError in `backend/services/scorekeeper.py` â€” replaced with inline `dict` construction.
  - Fixed `ValueError` in `backend/services/input_detector.py` â€” mapping parser was crashing on multi-word button names (e.g. `BTN_TRIGGER_HAPPY3`).
  - Both fixes required to get backend + gateway services running.

- **Gamepad Controller Configuration Interface (NEW)**:
  - Built a complete new "Controller Setup" tab in the Console Wizard for mapping external gamepad controllers (distinct from existing arcade panel mapper).
  - **4-phase wizard flow**: Detect â†’ Guided Button Mapping (16 steps) â†’ Analog Stick Calibration â†’ Complete.
  - Uses Browser Gamepad API (`navigator.getGamepads()`) for real-time input detection â€” zero backend latency.
  - Interactive profile selection with 5 supported controllers: 8BitDo Pro 2, 8BitDo SN30 Pro, Xbox 360, PS4 DualShock 4, Nintendo Switch Pro.
  - RetroArch config preview and apply integration via existing backend APIs.

- **PNG + SVG Overlay Digital Twin System**:
  - Generated high-quality PNG images for all 5 controller profiles.
  - Built hybrid rendering: PNG background image per profile + transparent SVG hotspot overlays positioned over each button.
  - Hotspots glow amber (active/prompted), cyan (physically pressed), green (successfully mapped).
  - Per-profile hotspot coordinate maps with percentage-based positioning.
  - Profile selection works without hardware â€” users can preview any controller layout immediately.

New files created:

- `frontend/src/panels/console-wizard/ControllerSVG.jsx` â€” Hybrid PNG+overlay digital twin component
- `frontend/src/panels/console-wizard/GamepadSetupOverlay.jsx` â€” 4-phase wizard overlay component
- `frontend/src/panels/console-wizard/gamepad-setup.css` â€” Dark glass styling with tactical HUD aesthetic
- `frontend/public/assets/controllers/8bitdo_pro_2.png` â€” 8BitDo Ultimate controller image
- `frontend/public/assets/controllers/8bitdo_sn30.png` â€” 8BitDo SN30 Pro controller image
- `frontend/public/assets/controllers/xbox_360.png` â€” Xbox 360 controller image
- `frontend/public/assets/controllers/ps4_dualshock.png` â€” PS4 DualShock 4 controller image
- `frontend/public/assets/controllers/switch_pro.png` â€” Nintendo Switch Pro controller image

Files modified:

- `frontend/src/panels/console-wizard/WizNavSidebar.jsx` â€” Added `controller-setup` nav item
- `frontend/src/panels/console-wizard/ConsoleWizardPanel.jsx` â€” Imported and rendered GamepadSetupOverlay
- `backend/services/scorekeeper.py` â€” Fixed NameError (ScoreAttemptReviewRequest)
- `backend/services/input_detector.py` â€” Fixed ValueError (mapping parser)

Backend APIs utilized (no backend changes needed):

- `GET /api/local/console/profiles` â€” loads controller profiles
- `POST /api/local/console/retroarch/config/preview` â€” preview generated config
- `POST /api/local/console/retroarch/config/apply` â€” write config file with backup

Validation completed:

- Backend starts without errors.
- Frontend build passes (`âœ“ built in 4.27s`).
- Controller tab renders in browser with profile selection, PNG preview, and guided wizard.
- All 5 controller PNGs load from `/assets/controllers/`.

Open follow-ups for next session:

- Live-test with physical 8BitDo controller at cabinet: verify Gamepad API detection, wizard mapping, and analog calibration.
- Fine-tune SVG hotspot overlay positions on each controller PNG (coordinates are estimates â€” may need adjustment with real hardware).
- ScoreKeeper Sam live validation (carried forward from previous sessions).
- Live-test Daphne/Hypseus launchers (carried forward).
- Golden drive sanitization script (carried forward).


### Session Catalog - 2026-03-11 (Antigravity Multi-Agent Orchestration Session — ~4 hours)

Scope completed in this session focused on ScoreKeeper Sam pipeline hardening, Controller Wizard preference persistence, and Daphne/Hypseus AHK parser robustness. Multi-agent workflow: Antigravity as Lead Architect/PM, Claude Code for audits, Codex for implementation, GPT for pre-audits.

Key outcomes:

- **ScoreKeeper Sam Pipeline Hardening (6 Fixes)**:
  - Claude Code audit identified 5 critical issues + 7 concerns.
  - Codex implemented: AA launch tracking, crash-exit explicit `failed` outcomes, dual-exit dedup (PID + plugin can't both score), atomic file writes (temp+rename), startup cleanup for stale sessions >24h, Lua watcher fallback when hiscore fails.
  - 5 tests pass.

- **Controller Wizard Preference Capture (NEW)**:
  - Added `GET/POST /api/local/console/gamepad/preferences` endpoints to `console.py`.
  - Frontend `GamepadSetupOverlay.jsx` now auto-saves 16-button mappings + deadzone + calibration on wizard complete.
  - Loads saved preferences on mount to pre-select profile.
  - `RetroArchConfigRequest` model updated with `mappings` and `deadzone` fields.
  - Preferences persist to `A:/.aa/state/controller/gamepad_preferences.json`.

- **Daphne/Hypseus AHK Parser Hardening (5 Fixes)**:
  - GPT pre-audit identified 2 critical, 4 moderate, 3 low risks.
  - Codex implemented: `.exe` fallback for absolute paths, manifest + `shutil.which()` fallback, comma-safe AHK command extraction, structured parse-failure logging, dead `daphne_adapter.py` stub replaced with documented re-export.
  - 5 tests pass in new `test_daphne_hypseus.py`.

- **UI Cleanups**:
  - MAP CONTROLS button removed from Controller Chuck panel (4 touchpoints: import, state, button, overlay render).
  - 8BitDo Pro 2 controller asset replaced with correct compact rounded shape.

Key files touched in this scope:

- `backend/routers/console.py` — Gamepad preference endpoints
- `backend/services/adapters/direct_app_adapter.py` — AHK parser hardening
- `backend/services/adapters/daphne_adapter.py` — Stub cleanup
- `backend/routers/aa_launch.py` — AA launch score tracking
- `backend/services/game_lifecycle.py` — Crash-exit + Lua fallback
- `backend/routers/game_lifecycle.py` — Dual-exit dedup
- `backend/services/score_tracking.py` — Atomic writes + startup cleanup
- `backend/tests/test_score_tracking.py` — Sam pipeline tests
- `backend/tests/test_daphne_hypseus.py` — NEW: AHK parser edge case tests
- `frontend/src/panels/console-wizard/GamepadSetupOverlay.jsx` — Preference load/save
- `frontend/src/panels/controller/ControllerChuckPanel.jsx` — MAP CONTROLS removal
- `frontend/public/assets/controllers/8bitdo_pro_2.png` — Replacement asset

Validation completed:

- Backend syntax checks passed on all modified files.
- Sam pipeline tests: 5 passed.
- Daphne/Hypseus parser tests: 5 passed.

Open follow-ups for next session:

- Device ID mismatch fix (`.env` 1690afb0 vs Supabase 00000000).
- Golden drive sanitization script (strip dev artifacts before duplication).
- SVG hotspot coordinate tuning (controller button overlay positions).
- Live cabinet testing: Sam pipeline, Daphne/Hypseus launchers, gamepad wizard, F9/Dewey overlay.
- Cascade integration: `wizard_mapping.py` reads from `gamepad_preferences.json` to generate configs for 15+ emulators.

### Session Catalog — 2026-03-12 PM (Antigravity Session — Emulator Audit + Dual-Build Pathing + RAG Context Map)

Scope completed in this afternoon session focused on emulator registry audit, dual-build pathing foundation, and RAG context map architecture.

Key outcomes:

- **Emulator Registry Audit**: Inventoried 55 LaunchBox-registered emulators and 28 Gun Build folders. Identified 13 duplicate families — most intentional (per-input-type builds). Flagged 3 real issues: Demul/Demul Arcade identical paths, PCSX2/PCSX2-Controller same exe, "Ryujink" typo.
- **Codex Handoff #1 — Emulator Dual-Build Pathing**:
  - `backend/constants/a_drive_paths.py` — New `EmulatorPaths` class with 68 static accessors (40 panel/gamepad + 28 gun build) + `all_executables()` health check dict.
  - `backend/services/emulator_context.py` — NEW: `infer_input_context()` — "Path IS the Signal" resolver (Gun Build → lightgun, Gamepad/Joystick/Controller → gamepad, else → arcade_panel).
- **Codex Handoff #2 — RAG Context Map**:
  - `backend/services/rag_slicer.py` — NEW: `RAGSlicer` class that extracts persona-specific `## TAG` sections from per-emulator master markdown files. Routing: chuck→CONTROLLER_CONFIG, gunner→GUN_CONFIG, dewey→ROUTING_VOCAB, etc.
  - `prompts/controller_chuck.prompt` — Gun Wall insertion (explicit refusal for light gun topics).
  - `prompts/gunner.prompt` — Controller Wall insertion (explicit refusal for button/joystick topics).
- **Protocol**: Codex handoffs no longer include NotebookLM steps (Codex lacks access).

Open follow-ups for next session:

- Codex executes both handoffs (5 files total, under HITL threshold).
- User has innovative idea for the rack system architecture.
- Build master `.md` knowledge files per emulator for the RAG slicer.
- Live hardware validation (H1–H9) — carried forward.

### Session Catalog — 2026-03-12 (Antigravity Audit Session)

Scope completed in this session focused on verifying Codex's duplication-readiness implementation across 13 files.

Key outcomes:

- **Full Round 2 Audit of Codex's Duplication-Readiness Code (13 files verified)**:
  - Read every line of all 13 files Codex claimed as implemented.
  - Verified first-boot identity provisioning: UUID generation, `.aa/device_id.txt`, `.aa/cabinet_manifest.json` sync, `controls.json` skeleton, device ID resolution chain (file → manifest → env), `os.environ` runtime sync.
  - Verified serve-only boot: `start-aa.bat` no longer builds, auto-detects drive letter via `%~d0`, runs bootstrap, checks `frontend/dist/index.html`.
  - Verified SPA shell cache-busting: `server.js` re-reads `index.html` per request, injects `window.AA_DEVICE_ID`, sets `no-store` + `X-AA-SPA-Build`, uses `index: false` on `express.static`.
  - Verified golden image pipeline: `prepare_golden_image.bat` wipes old dist, runs clean build, extracts + verifies SPA hash.
  - Verified clone-clean script: `clean_for_clone.bat` preserves `frontend/dist`, `gateway/node_modules`, `.aa/manifest.json`; sanitizes `.env` DEVICE_NAME/DEVICE_SERIAL; prompts for backups cleanup.
  - Verified Blinky lazy imports: pure `__getattr__` + `importlib.import_module`, zero hardware access at import time.
  - Verified Electron overlay scope: documented as "launches separately from start-aa.bat", singleton instance lock.
  - Verified test suites: 3 provisioning tests (bootstrap, precedence, endpoint) + SPA shell contract test.

- **Validation Results**:
  - `py_compile`: 6/6 passed (cabinet_identity, startup_manager, system, bootstrap_local_cabinet, test_cabinet_provisioning, blinky/__init__).
  - `node --check`: 2/2 passed (server.js, cabinetIdentity.js).

- **Documentation Updates**:
  - Updated README Known Issues table: closed 4 stale blockers (gateway index.html, blinky lazy exports, Dewey news chat, TTS echo).
  - Added Duplication-Readiness Master Checklist to README: 18 code-complete items, 9 hardware-validation items, 4 separate-effort items.
  - Updated ROLLING_LOG with session entry.

Open follow-ups:

- Live hardware validation (H1–H9 in master checklist).
- Supabase Service Role Key handling on golden image.
- Device ID mismatch fix.
- ElevenLabs placeholder API key replacement.

### Session Catalog — 2026-03-16 Late Night (Antigravity Session — Dewey Chat & News Voice Fix)

Scope completed in this session focused on fixing Dewey's main chat 400/500 errors and the Gaming News chat's echo + missing voice issues.

Key outcomes:

- **Dewey Main Chat — Gemini Migration**:
  - Root cause: A: drive's `dewey.py` was calling `anthropic-proxy` directly via `SecureAIClient.call_anthropic()`, bypassing the gateway entirely.
  - Added `call_gemini()` method to `SecureAIClient` in `drive_a_ai_client.py` to call the `gemini-proxy` edge function with correct message formatting.
  - Replaced `_call_anthropic` and `_extract_anthropic_text` with `_call_gemini` and `_extract_gemini_text` in `dewey.py` for both the `/chat` endpoint and the collection trivia generator.
  - Dewey's main chat now correctly uses Gemini as the AI provider.

- **Anthropic Proxy Defensive Fix**:
  - Fixed the `anthropic-proxy` Supabase edge function (deployed v14) to correctly handle system messages. It now extracts `role: 'system'` messages from the `messages` array and promotes them to the top-level `system` parameter, preventing 400 errors from Anthropic API. This is a defensive fix — Dewey no longer calls this proxy, but other consumers won't break.

- **Gaming News Chat — Echo Prevention**:
  - Root cause: React's state-based `loading` guard was too slow for rapid-fire voice sends, allowing duplicate API calls.
  - Implemented a `sendingRef` (ref-based, not state-based) guard in `useNewsChat.js` that blocks duplicate sends during the same interaction cycle.

- **Gaming News Chat — TTS Integration**:
  - Added Text-to-Speech to the News Chat sidebar using ElevenLabs via the gateway's `/api/voice/tts` endpoint.
  - Uses Dewey's voice ID (`t0A4EWIngExKpUqW6AWI`).
  - Audio plays automatically after each Dewey response.
  - Includes `isSpeaking`, `stopSpeaking`, and `ttsEnabled` toggle.

- **Gaming News Chat — Push-to-Talk UX**:
  - Removed auto-send behavior from voice input. Previously, clicking the mic would auto-fire the transcript as a message, causing garbled partial speech to create confusing exchanges.
  - Now: click mic → speak → transcript fills text box → user reviews → user clicks Send. Clean, predictable flow.

- **System Prompt Improvements**:
  - Updated the News Chat system prompt to prioritize conversational greetings over strictly discussing headlines.
  - Added "Vary your language — don't start every response the same way" instruction to prevent repetitive "Hey there! How's it going?" openers.

Files modified:

- `A:\Arcade Assistant Local\backend\services\drive_a_ai_client.py` — Added `call_gemini()` method
- `A:\Arcade Assistant Local\backend\routers\dewey.py` — Switched chat and trivia to Gemini
- `c:\Users\Dad's PC\Desktop\AI-Hub\supabase\functions\anthropic-proxy\index.ts` — System message handling fix (deployed v14)
- `c:\Users\Dad's PC\Desktop\AI-Hub\frontend\src\panels\dewey\news\useNewsChat.js` — Echo guard, TTS, push-to-talk, prompt improvements

> ⚠️ **IMPORTANT for next agent**: The TTS route in the gateway is mounted at `/api/voice` (NOT `/api/ai`), so TTS calls go to `/api/voice/tts`. This was a bug that was fixed during this session. See `server.js` line 176.

> ⚠️ **IMPORTANT for next agent**: The A: drive has its OWN copy of `dewey.py` and `drive_a_ai_client.py` at `A:\Arcade Assistant Local\backend\`. These are NOT the same as the C: drive versions. The A: drive versions have the actual `/chat` endpoint for Dewey. When debugging Dewey chat, check BOTH drives.

Validation:

- Frontend built successfully (`✓ built in 1.80s`)
- Frontend dist + source copied to A: drive
- User confirmed voice output is working
- User confirmed echo behavior is resolved with push-to-talk model

Open follow-ups for next session:

- Full end-to-end retest of Gaming News chat voice after next Arcade Assistant restart
- Live hardware validation (H1–H9) — carried forward
- Device ID mismatch fix — carried forward

### Session Catalog - 2026-03-16 Follow-up (Codex Session - Wiz + Doc Audits and Targeted Fixes)

Scope completed in this follow-up session focused on deep truth audits of Console Wizard (Wiz) and System Health (Doc), followed by tightly scoped fixes only where requested.

Key outcomes:

- **Wiz Deep Audit Completed**:
  - Verified active Wiz frontend, backend, prompt, knowledge, profile, and shared-sidebar wiring.
  - Confirmed active AI path is shared Engineering Bay chat -> Gemini, not the legacy Anthropic Wiz path.
  - Confirmed controller detection is real hardware-backed.
  - Confirmed emulator health checks and config snapshot drift checks are real.
  - Confirmed guided gamepad capture is browser Gamepad API-based, not simulated.
  - Identified open issues: sidebar icon encoding, fleet ID fallback leakage, RetroArch mapping payload not consumed on preview/apply, and modified-health attention visibility.

- **Wiz Targeted Fixes Applied**:
  - `frontend/src/panels/console-wizard/ConsoleWizardPanel.jsx`:
    - Fixed Wiz sidebar icons to `🕹️` and `🎮`.
    - Added guarded `window.AA_DEVICE_ID` fallback with `[Wiz]` warning.
    - Included `modified` in the health attention set and added drift description text.
  - `frontend/src/panels/console-wizard/GamepadSetupOverlay.jsx`:
    - Added guarded `window.AA_DEVICE_ID` fallback with `[Wiz]` warning.
  - `frontend/src/panels/console-wizard/wizContextAssembler.js`:
    - Added guarded `window.AA_DEVICE_ID` fallback with `[Wiz]` warning.
  - `frontend/src/panels/_kit/EngineeringBaySidebar.jsx`:
    - Added panel-aware guarded device ID helper for shared Engineering Bay chat/action requests.
  - `backend/routers/console.py`:
    - Wired incoming `mappings` and `deadzone` through RetroArch preview/apply handlers.
  - `backend/services/retroarch_config_generator.py`:
    - Added support for custom mapping overrides and deadzone override propagation.

- **Doc Deep Audit Completed**:
  - Verified active Doc panel uses `/api/local/health/*` for telemetry and the shared Engineering Bay sidebar for chat.
  - Confirmed active Doc chat backend is Gemini with prompt loaded from `prompts/doc.prompt`.
  - Confirmed the auxiliary `/api/doc/*` diagnostics router exists and the `scan_hardware_bio` import fix is in place.
  - Identified active issues: processes tab payload mismatch, non-standard device ID patterns, LLM provider card mismatch, and UI diagnosis toggle mismatch.

- **Doc Targeted Fixes Applied**:
  - `frontend/src/panels/system-health/SystemHealthPanel.jsx`:
    - Processes tab now reads backend `groups` payload correctly.
    - Added Doc-only sidebar flag to suppress the diagnosis toggle in the UI.
  - `frontend/src/services/systemHealthApi.js`:
    - Replaced localStorage device lookup with guarded `window.AA_DEVICE_ID` fallback using `[Doc]` warning and `doc-panel` fallback.
  - `frontend/src/panels/system-health/docContextAssembler.js`:
    - Replaced unguarded `cabinet-001` fallback with guarded `[Doc]` device ID pattern.
  - `backend/routers/health.py`:
    - Updated Doc health summary `llm_provider` to report `gemini`, matching the active Doc chat backend.
  - `frontend/src/panels/_kit/EngineeringBaySidebar.jsx`:
    - Added support for Doc-only toggle suppression without forcing permanent diagnosis mode behavior.

Validation completed:

- Doc frontend build passed successfully with `npm.cmd run build:frontend`.
- Wiz and Doc source paths were manually traced end-to-end after each change.

Validation blocked by environment:

- Python syntax checks were attempted but blocked by local interpreter issues on this machine:
  - direct Python path returned `Access is denied`
  - the repo `.venv` points at the same blocked base interpreter
  - `uv` fallback also hit machine-level Python access/permission issues

Open follow-ups for next session:

- Wiz:
  - Live cabinet validation of controller detection, guided mapping, and RetroArch output.
  - Guided mapping visual highlight refinement.
  - Visual Diff tab repair remains post-audit follow-up work.
- Doc:
  - Chat drawer/layout restructure remains post-duplication work.
  - Hardware placeholder replacement remains post-duplication work.
  - GPU temperature integration remains post-duplication work and will require a vendor/hardware monitor path beyond `psutil`.

---

### Session Catalog — 2026-03-19 (Antigravity Session — Gun Platform Routing, AHK Bulk Fix, LoRa Hardening)

Scope completed in this session focused on making every gun platform launchable from LoRa, fixing all AHK scripts for the A:\ drive, and hardening the LoRa GUI.

Key outcomes:

- **Pinball FX2/FX3 Unblocked**:
  - `'pinball fx'` was incorrectly in the `unsupportedKeywords` array in `LaunchBoxPanel.jsx`. Removed. Both platforms now launch from LoRa.

- **Gun Platform Routing System Built (16 platforms)**:
  - Added `GUN_PLATFORM_MAP` to `launcher.py` at L1160. Detects raw platform name BEFORE `normalize_key()` strips "gun games".
  - Maps 16 gun platforms to their Gun Build emulator paths via `EmulatorPaths` in `a_drive_paths.py`.
  - Two AHK intercept points: L1329 (adapter-resolved path) and L1498 (fallback path). Any game with `.ahk` ApplicationPath routes to `AutoHotkeyU32.exe` regardless of emulator map entry.
  - NES core hard-wired to `nestopia_libretro.dll` with fceumm fallback (mesen not on disk).
  - Unknown gun platforms fall back to `retroarch_gun()`.

- **Bulk AHK Script Fix (213 files)**:
  - All `.ahk` scripts in `A:\Gun Build\Roms\` had two systemic issues: wrong drive letter (`D:\` → `A:\`) and Sinden Lightgun.exe startup/cleanup blocks.
  - Python line-by-line parser fixed both issues across 213 files in ~3 seconds.
  - SINGE2 scripts (13) intentionally untouched — they need Sinden.
  - AHK backup created at `A:\Gun Build\AHK_BACKUP_20260319\`.
  - Original PowerShell regex approach hit catastrophic backtracking; switched to Python.

- **Sinden Error Suppression + Retro Shooter VID/PIDs**:
  - `gunner_hardware.py`: generic "No light gun devices detected" warning and USB enumeration error downgraded to `logger.debug`.
  - 4 Retro Shooter VID/PIDs added to `KNOWN_DEVICES` as PRIMARY gun type. Sinden/AimTrak/Gun4IR marked secondary.

- **LoRa GUI Platform Exclusions**:
  - Added `excludedPlatforms` exact-match array to `isSupportedPlatform()` alongside existing `unsupportedKeywords`.
  - Removed from LoRa display: Saturn Gun Games, Model 3 Gun Games, PS2 Gun Games, PCSX2 Gun Games, Flash Games.

- **PS3 AHK Routing Fix**:
  - Root cause: when an adapter resolved AND `gun_exe_override` fired, the code at L1325 overrode `exe` to the gun emulator but never checked for `.ahk` wrappers. The AHK detection at L1498 was unreachable.
  - Fix: inserted AHK detection at L1329 — when `ApplicationPath` ends in `.ahk`, overrides to AutoHotkey regardless of gun map entry.
  - Before: `rpcs3.exe Child of Eden.ahk` → After: `AutoHotkeyU32.exe Child of Eden.ahk`.

- **Display Driver Forensics**:
  - Full forensic sweep of Windows Event Logs and hardware state confirmed display driver failure was NOT caused by AA or any emulator. Driver reinstall resolved it.

Verified launches:

| Platform | Game | Result |
|----------|------|--------|
| NES Gun Games | Duck Hunt | ✅ nestopia core via RetroArch |
| SNES Gun Games | Battle Clash | ✅ Snes9x via AHK |
| TeknoParrot Gun Games | Action Deka | ✅ AHK |
| PC Gun Games | Air Twister | ⚠️ AHK launched, game exe crashed 2.2s |
| PS3 Gun Games | Child of Eden | ✅ AHK (fixed from rpcs3.exe) |

Files modified:

- `frontend/src/panels/launchbox/LaunchBoxPanel.jsx` — Pinball FX unblock + `excludedPlatforms` array
- `backend/services/launcher.py` — `GUN_PLATFORM_MAP`, gun_exe_override, dual-path AHK detection, NES core hard-wire
- `backend/services/gunner_hardware.py` — Sinden suppression, 4 Retro Shooter VID/PIDs
- `A:\Gun Build\Roms\**\*.ahk` (213 files) — Drive letter fix, Sinden block removal

Open follow-ups:

- SINGE2 AHK scripts (13 files) still reference Sinden — separate pass needed if Retro Shooter fully replaces Sinden.
- Air Twister (PC Gun Games) crashed in 2.2s — likely game content issue, not routing.
- Live hardware validation (H1–H9) — carried forward.

---

### Session Catalog â€” 2026-03-20 (Codex Session â€” Consent/Profile Flow, Dewey Backendization, Wizard Wiring, Launcher/Marquee Cleanup)

Scope completed in this session focused on restoring missing user/profile flows, moving Dewey AI responsibilities to the backend, closing launcher/content gaps, and finishing the guarded write/mapping paths for Wiz and Chuck.

Key outcomes:

- **Vicky Consent Flow Restored + Profile Broadcast Hardened**:
  - Replaced the bypassed consent state in the active Vicky panel with a first-use opt-in gate.
  - Added explicit guest mode behavior so anonymous sessions do not write profile data.
  - Ensured accepted profiles persist `consent: true` before Save & Broadcast.
  - Verified the shared profile propagation path across all nine panels and restored missing context wiring where needed.
  - Added success/failure broadcast toast behavior and corrected the garbled Unicode sidebar header text.
  - Restored Vicky's fallback ElevenLabs voice ID to `21m00Tcm4TlvDq8ikWAM`.

- **Dewey Chat Path Moved Frontend -> Backend**:
  - Extracted Dewey's browser-side system prompt into `prompts/dewey.prompt`.
  - Added `prompts/dewey_knowledge.md` for routing, handoff, profile, trivia, overlay, and news architecture context.
  - Created backend chat routing so Dewey now answers through `POST /api/local/dewey/chat` instead of direct browser-side Gemini calls.
  - Registered the new Dewey chat router in the FastAPI app and updated the frontend to consume SSE safely with graceful error handling.

- **Dewey "Your Collection" Trivia Now Uses LaunchBox Library Data**:
  - Added per-question AI generation in `backend/services/dewey/trivia_generator.py` based on sampled entries from `launchbox_games.json`.
  - Added `POST /api/local/dewey/trivia/collection` to generate collection-specific questions from cached LaunchBox metadata using `AA_DRIVE_ROOT`.
  - Updated Dewey trivia frontend flow to show a generation loading state and feed the generated question set into the existing session pipeline.
  - Added graceful fallback behavior when the LaunchBox cache is empty or unavailable.

- **Knowledge Base Expansion Completed**:
  - Appended four new encoder families to `prompts/chuck_knowledge.md`:
    - GP-Wiz 49 / GP-Wiz 40
    - Brook Universal Fighting Board (UFB)
    - Ultimarc ServoStik
    - Ultimarc U-Trak / SpinTrak
  - Built out `prompts/wiz_knowledge.md` with:
    - emulator-facing encoder behavior for arcade encoders
    - the 12-emulator controller/config knowledge set Wiz actively monitors

- **Launcher + Gun Platform Loose Ends Closed**:
  - Fixed Nintendo DS launch failure by correcting the platform routing path and adding a working direct fallback.
  - Added `playstation 1` as an alias for the existing `ps1` direct-launch handling so both LaunchBox platform names resolve identically.
  - Improved Daphne/Hypseus fallback behavior so unknown titles attempt a best-effort framefile launch before falling through to LaunchBox.
  - Reviewed SINGE2 AHK launchers, removed obsolete Sinden bootstrap/teardown patterns from active scripts, and added the missing direct-launch support path in `launcher.py`.

- **Marquee Content Path Completed**:
  - Replaced the marquee test/simulation TODO stubs in `content_manager.py` with real calls into `scripts/marquee_display.py`.
  - Added graceful error handling so a missing second monitor or display failure reports cleanly instead of crashing the content manager.
  - Left `AA_MARQUEE_ENABLED=0` unchanged pending live hardware validation.

- **Wiz Config Apply Path Fully Gated Through ExecutionCard**:
  - Audited the Visual Diff pipeline and confirmed preview generation existed, but the final write path was bypassing the shared execution gate.
  - Added backend `POST /api/local/console/apply-config`.
  - Routed Visual Diff apply actions through the Engineering Bay `ExecutionCard` pattern so actual config writes only occur after explicit operator confirmation.
  - Preserved atomic write behavior and returned structured applied/error results to the frontend toast layer.

- **Chuck Visual Wizard Overlay Wired End-to-End**:
  - Finished the guided mapping lifecycle around `wizard_mapping.py`: start session, capture per-control mapping, commit mapping, and cancel session.
  - Rewired the Chuck frontend overlay to use the new `/wizard/*` flow instead of the older learn-wizard path.
  - Confirmed commit still triggers the existing Controller Cascade path after mapping save.
  - Added the amber waiting / green confirmed visual language and real-time progress state to the active overlay.

- **Wiz Guided Mapping Overlay Calibration Pass Applied**:
  - Audited the controller renderer and confirmed it already used per-profile percentage hotspot maps for all five supported controller profiles.
  - Tightened the hotspot calibration by converting rectangular regions to centered percentage geometry and retuning the five profile coordinate sets:
    - 8BitDo Pro 2
    - 8BitDo SN30 Pro
    - Xbox 360
    - Nintendo Switch Pro
    - PS4 DualShock 4
  - Synced Wiz's active/captured/mapped visual states with Chuck's amber pulse and green flash behavior.
  - Added a graceful text-only fallback plus warning if the controller art pack is missing from `frontend/public/assets/controllers/`.

Validation completed during this session:

- `npm.cmd run build:frontend` passed after the frontend tasks.
- Targeted Python compile checks passed for the launcher, content manager, console router, profile/tts routes, Dewey chat/trivia modules, and related backend edits when invoked.
- Scoped git status/diff reviews were used after each targeted change to keep edits isolated.

Environment notes / handoff risks:

- NotebookLM CLI remained unavailable in this environment (`Failed to canonicalize script path`), so notebook write-back and source uploads were not completed from this session.
- The current checkout appears to be missing the expected controller PNG asset pack under `frontend/public/assets/controllers/`; Wiz now degrades safely, but live visual validation should restore/verify those assets.
- Several tasks were compile/build verified but not live runtime-smoke-tested against active local backend/gateway services in this session.

Open follow-ups for next session:

- Run live validation for:
  - Vicky consent accept/guest paths
  - profile Save & Broadcast propagation across all nine panels
  - Dewey backend chat SSE path
  - Dewey collection trivia generation against live LaunchBox cache
  - Wiz guided controller art alignment once the PNG asset pack is confirmed present
  - Chuck wizard commit through Controller Cascade on live cabinet hardware
- Re-enable and hardware-validate marquee content flow before flipping `AA_MARQUEE_ENABLED` back to `1`.
- Restore NotebookLM CLI/tooling so session summaries and architectural deltas can be written back to the second-brain notebooks again.

---

### Session Catalog - 2026-04-11 (LoRa Hardening Sprint - Conversation Memory, Gemini Model Trials, Launch Truth, Runtime Triage)

Scope completed in this session focused on making LaunchBox LoRa behave like a reliable ongoing conversation partner, tightening launch truthfulness, and stabilizing customer-facing model/runtime behavior.

Key outcomes:

- **LoRa Follow-Up Conversation State Hardened**:
  - Numeric follow-ups like `3` now remain attached to the active candidate list instead of dropping back to raw title search.
  - Version/platform refinements such as `the NES version`, `the arcade version`, `Nintendo version`, `2600 version`, `original`, and year-only replies are now interpreted against the prior result set when LoRa is already disambiguating.
  - Multi-result replies are promoted into a real pending-selection state instead of relying on loose conversational wording.
  - Exact-title anchoring was tightened so franchise queries like `Pac-Man` do not drift toward sibling titles like `Jr. Pac-Man` during later refinement.
  - Single-candidate confirmation prompts now arm a true ready-to-launch state, so affirmatives like `Yes`, `Yeah`, `Sure`, and `Let's do this` launch the selected game instead of being parsed as a new search.

- **Voice/Vernacular Normalization Expanded**:
  - Added normalization for ASR-style mishears such as `verses of` -> `versions of`.
  - LoRa is now more tolerant of natural follow-up phrasing after she asks a clarifying question.

- **LoRa Launch Speech Improved**:
  - Launch announcements now derive a friendly spoken version label from `game.platform`, so LoRa can say `arcade version`, `NES version`, `PlayStation 2 version`, etc.
  - Numbered disambiguation choices remain visible in the panel instead of being stripped by the message renderer.

- **Gemini Model Trials Completed**:
  - Tested moving LoRa/Dewey from `gemini-2.0-flash` to `gemini-2.5-flash-lite`, then to `gemini-3-flash-preview`.
  - `gemini-3-flash-preview` produced gateway/runtime instability for this stack, including 500 errors in LoRa flows.
  - Final recommendation and current stable target for customer-facing use is `gemini-2.5-flash`.
  - Code/default fallbacks were updated so the stack no longer silently prefers deprecated `gemini-2.0-flash`.

- **Launch Truthfulness Fixed for LoRa Panel**:
  - Root cause: the panel/gateway could report `Launching ...` as successful when the backend had only issued a command, not confirmed that the emulator process actually stayed alive.
  - Added short-window PID confirmation in `backend/routers/launchbox.py` so LaunchBox/RetroFE/Pegasus panel callers only get a successful launch result when a recent process can be confirmed.
  - `launchbox_only` platforms are no longer reported as successful panel launches.
  - When the command is issued but the process cannot be confirmed, LoRa now reports that the launch could not be verified instead of pretending the game launched.

- **Backend / Runtime Triage**:
  - Investigated a report that browsing Naomi caused the backend to quit.
  - After restart, Naomi list/detail/image endpoints were healthy and reproducible.
  - The only concrete backend-side exception found during startup was a file-lock race in `backend/services/hiscore_watcher.py` when replacing `scores.jsonl`.
  - Windows event logs also showed a separate `redream.exe` crash earlier in the evening, but not a clean Python/uvicorn crash signature tied directly to Naomi browsing.

- **Duplicate Launch Mitigation**:
  - Investigated reports of repeated GameCube launches.
  - Hardened the shared gateway retry helper so it no longer retries non-idempotent HTTP methods; `POST` launch requests will not be retried automatically.
  - Added a runtime guard in `LaunchBoxPanel.jsx` so `launchGame()` refuses to execute when the launch lock is already active, instead of relying only on disabled buttons.
  - Logs still suggest GameCube routing can fan across more than one backend launch path in some cases; that remains a targeted follow-up.

Files modified during this session included:

- `gateway/routes/launchboxAI.js`
- `frontend/src/panels/launchbox/LaunchBoxPanel.jsx`
- `backend/routers/launchbox.py`
- `backend/tests/test_launchbox_router.py`
- `gateway/lib/http.js`
- `.env`
- model/default callers touched during Gemini standardization:
  - `gateway/adapters/gemini.js`
  - `gateway/gems/aa-lora/tool_loop.js`
  - `gateway/routes/aiHealth.js`
  - `backend/routers/dewey.py`
  - `backend/routers/dewey_chat.py`
  - `backend/services/drive_a_ai_client.py`

Validation completed during this session:

- `node --check gateway/routes/launchboxAI.js`
- `node --check gateway/lib/http.js`
- `python -m py_compile backend/routers/launchbox.py`
- targeted pytest checks passed for:
  - unverified direct launch downgrade
  - launchbox-only platform downgrade
- `npm.cmd run build:frontend` passed after frontend edits

Open follow-ups for next session:

- Live LoRa transcript validation for the newest conversation-state fixes using real customer-style phrasing.
- Hard-fix GameCube routing so it uses one explicit emulator path and cannot fan across duplicate launch methods.
- Investigate and harden the `hiscore_watcher.py` file-replace race around `scores.jsonl`.
- Continue transcript-driven LoRa tuning, but this is now edge-case work rather than foundational rewrite work.

---

## Self-Healing Launch System (Phase 4)

Arcade Assistant includes an AI-powered self-healing system for game launches. When a game crashes (exits in under 10 seconds), the system automatically:

1. **Detects the crash** — `GameLifecycleService` monitors tracked PIDs every 2 seconds
2. **Queries Gemini** — sends crash context to the `gemini-proxy` Supabase edge function
3. **Applies a JIT fix** — injects CLI flags or writes ephemeral config tweaks
4. **Retries the launch** — up to 2 attempts before declaring unrecoverable

### Key Files

| File | Purpose |
|------|---------|
| `backend/services/game_lifecycle.py` | PID monitoring, crash detection, triggers remediation |
| `backend/services/launch_remediation.py` | Gemini query, fix parsing, JIT application, JSONL logging |
| `backend/services/remediation.py` | Legacy remediation service (Phase 3) |

### Reading Remediation Logs

Every remediation attempt is logged to:
```
A:\.aa\logs\remediation.jsonl
```
Each line is a JSON object with: `timestamp`, `game_title`, `platform`, `emulator`, `attempt_number`, `gemini_suggestion`, `fix_applied`, `fix_type`, `fix_detail`, `success`, `error`.

### Disabling Remediation

Set in `.env`:
```
DISABLE_REMEDIATION=1
```

### Gemini Proxy Architecture

Gemini API calls route through a Supabase edge function (`gemini-proxy`) so the raw `GEMINI_API_KEY` never touches the local machine. The backend authenticates to the proxy using `SUPABASE_SERVICE_ROLE_KEY`.

---
*Arcade Assistant - Built for G&G Arcade, one commit at a time.*
