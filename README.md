# Arcade Assistant Ã¢â‚¬â€ Project README
**Last Updated:** 2026-03-12 EVE | **Build:** RAG Emulator Knowledge Pipeline + Dual-Build Pathing + RAG Context Map + Duplication-Readiness | **Branch:** `master` | **Commit:** `WIP (uncommitted)`

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
| H3 | Daphne/Hypseus real launch (BadLands, Rollercoaster, Cliff Hanger) | PENDING | Parser verified, needs live run |
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
---
*Arcade Assistant - Built for G&G Arcade, one commit at a time.*

