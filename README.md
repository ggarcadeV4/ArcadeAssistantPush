# Arcade Assistant â€” Project README
**Last Updated:** 2026-03-10 | **Build:** ScoreKeeper Sam Universal Score Tracking Foundation + Dewey/LaunchBox Prior Work | **Branch:** `master` | **Commit:** `WIP (uncommitted)`

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
# Terminal 1 â€” Gateway (Node)
cd gateway && node server.js

# Terminal 2 â€” Backend (Python)
cd backend && python app.py

# Terminal 3 â€” Frontend (Vite dev server)
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
| Supabase | Cloud | â€” | Ref: `zlkhsxacfyxsctqpvbsh` (**Arcade Assistant only**) |

> âš ï¸ **NEVER** use Supabase ref `hjxzbicsjzyzalwilmlj` â€” that is the G&G Website project.

---

## Persona Roster

| # | Persona | Panel File | EB Sidebar | TTS |
|---|---------|-----------|------------|-----|
| 1 | **Dewey** (Arcade Historian) | `panels/dewey/` | N/A (custom) | âœ… ElevenLabs |
| 2 | **LaunchBox LoRa** | `panels/launchbox/` | ðŸ”¶ Stub | âœ… ElevenLabs |
| 3 | **ScoreKeeper Sam** | `panels/scorekeeper/` | N/A | âœ… ElevenLabs |
| 4 | **Controller Chuck** | `panels/controller/` | âœ… Standardized | âœ… ElevenLabs |
| 5 | **LED Blinky** | `components/led-blinky/` | âœ… Standardized | âœ… ElevenLabs |
| 6 | **Gunner** | `components/gunner/` | âœ… Standardized | âœ… ElevenLabs |
| 7 | **Console Wizard** | `panels/console-wizard/` | âœ… Standardized | âœ… ElevenLabs |
| 8 | **Vicky** (Voice) | `panels/voice/` | âœ… Standardized | âœ… ElevenLabs |
| 9 | **Doc** (Diagnostics) | `panels/system-health/` | âœ… Standardized | âœ… ElevenLabs |

Route: `http://127.0.0.1:8787/assistants?agent=chuck` (replace `chuck` with persona ID)

---

## Controller Chuck â€” Current State (as of 2026-03-03)

The most actively developed panel. Status: **Diagnosis Mode Phase 1 + Standardized Sidebar + Gemini AI.**

### Implemented
- **4P / 2P mode switcher** â€” identical compact card sizing in both modes
- **FLIP focus animation** â€” click any player card, it springs from its exact grid corner to the panel center (`getBoundingClientRect()` + CSS vars `--flip-x/y/w`, spring easing `cubic-bezier(0.34, 1.56, 0.64, 1)`)
- **Premium return animation** â€” card breathes out to scale(1.52) then dissolves back to its grid corner
- **Directional arrow overlay + Button click-to-map** â€” SVG arrows, cyan pulse while waiting for cabinet input
- **Mapping confirmation animations** â€” physical press â†’ `latestInput` â†’ white flash â†’ green ring burst â†’ `âœ“ GPIO XX` badge
- **Top strip** â€” SCAN + DETECT buttons visible in both 2P and 4P modes

### Diagnosis Mode (Phase 1 â€” 2026-03-02)
Diagnosis Mode is a context-aware, config-writing co-pilot mode. Toggle the amber pill in the Chuck sidebar header to activate.

**Frontend:**
| File | Role |
|------|------|
| `hooks/useDiagnosisMode.js` | Shared hook â€” toggle, TTS greeting, 30s context refresh, 5-min soft-lock |
| `chuckContextAssembler.js` | 3-tier context payload (<1500 tokens, Chuck-only) |
| `chuckChips.js` | 6 suggestion chips |
| `DiagnosisToggle.jsx/.css` | Amber pill toggle with animated thumb |
| `ContextChips.jsx/.css` | Horizontal scrollable amber chip bar |
| `MicButton.jsx/.css` | Push-to-talk, 0.7 confidence threshold, ripple rings |
| `ChuckSidebar.jsx` | Full chat panel â€” assembles all components |
| `chuck-sidebar.css` | Amber left-border pulse in Diagnosis Mode |
| `chuck-layout.css` | Flex layout: player grid + sidebar side-by-side |

**Backend:**
| File | Role |
|------|------|
| `services/controller_bridge.py` | `ControllerBridge` â€” sole GPIO merge authority, 5-step atomic commit, 4 conflict types, sacred law validation, rollback |
| `routers/controller.py` | `POST /api/profiles/mapping-override` â€” 2-phase proposal+commit |
| `services/chuck/ai.py` | `remediate_controller_config()` â€” Gemini 2.0 Flash AI tool |

**Sacred Button Law (immutable):**
```
P1/P2: Top row â†’ 1, 2, 3, 7  |  Bottom row â†’ 4, 5, 6, 8
P3/P4: Top row â†’ 1, 2         |  Bottom row â†’ 3, 4
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
  â”œâ”€â”€ ControllerChuckPanel.jsx     â† Main component (FLIP, state machine, PlayerCard)
  â”œâ”€â”€ ChuckSidebar.jsx             â† Chat panel + Diagnosis Mode
  â”œâ”€â”€ controller-chuck.css         â† All animations, 2P/4P layout
  â”œâ”€â”€ chuck-sidebar.css            â† Sidebar styles (amber in diag mode)
  â”œâ”€â”€ chuck-layout.css             â† Flex layout wrapper
  â”œâ”€â”€ DiagnosisToggle.jsx/.css     â† Amber pill toggle
  â”œâ”€â”€ ContextChips.jsx/.css        â† Suggestion chips
  â”œâ”€â”€ MicButton.jsx/.css           â† Push-to-talk
  â”œâ”€â”€ chuckContextAssembler.js     â† 3-tier context builder
  â””â”€â”€ chuckChips.js                â† Chip definitions

backend/
  â”œâ”€â”€ services/controller_bridge.py   â† GPIO merge authority
  â”œâ”€â”€ routers/controller.py           â† mapping-override endpoint
  â””â”€â”€ services/chuck/ai.py            â† remediate_controller_config tool
```

---

## LED System

- **Stack**: Python ctypes driver (`ledwiz_direct.py`) speaks directly to Windows HID â€” **no node-hid, no LEDBlinky dependency for color control**
- **LEDBlinky.exe**: Still used for per-game profiles via subprocess call
- **PWM Safety**: All values clamped 0â€“48 (49â€“129 triggers strobe/crash modes)
- **Boards**: 3Ã— LED-Wiz units auto-discovered on startup
- **Gamma**: 2.5 correction + Electric Ice color balance (Red 65%, Blue 75%, Green 100%)

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
| Gateway stale `index.html` | ðŸ”´ Blocker | `express.static()` serves old `index.html` after rebuild â€” blocks ALL frontend changes |
| LED Blinky panel + RAG KB | ðŸ”´ Next Session | Primary target â€” arbiter built, needs frontend + sidebar |
| Dewey News Chat verification | ðŸŸ¡ Blocked | New chat sidebar written but unreachable due to stale serving |
| TTS echo on Dewey exit | ðŸŸ¡ Blocked | Jules fix cherry-picked but unverifiable |
| Gunner Phase 2 | ðŸŸ¡ After LED Blinky | Calibration tab, profiles tab, retro modes |
| Doc (Diagnostics) panel | ðŸŸ¡ After Gunner | Full system diagnostic panel |
| B6/B7 Wake Word & TTS Dropping | ðŸŸ¡ Medium | Voice panel fixes |
| Handoff Protocol URL standard | ðŸŸ¡ Medium | Inter-panel communication |
| Diagnosis Mode Phase 2 (Supabase tables) | ðŸŸ¡ Medium | `controller_mappings`, `encoder_devices`, `controller_mappings_history` |
| `blinky/__init__.py` lazy exports | ðŸŸ¡ Medium | Eagerly parses XML + HID on import â†’ blocking |
| F9 Overlay Z-Index | ðŸŸ¢ Backlog | Electron `setAlwaysOnTop` |
| LaunchBox LoRa deep build | ðŸŸ¢ Backlog | Most complex panel â€” future session |

### Recently Closed Blockers (2026-03-05)
| Blocker | Fix | File |
|---------|-----|------|
| B2 â€” HttpBridge outbound | `NotifyBackendGameStart()` fire-and-forget POST | `HttpBridge.cs` |
| B4 â€” Voice Hardware Unlock | `_sync_led_state()` + Supabase fleet mirroring | `voice/service.py` |
| B5 â€” Genre LED Animation | `GENRE_ANIMATION_MAP` (8 genre codes) | `game_lifecycle.py` |
| Console Wizard RAG KB | `wiz_knowledge.md` (500+ lines) + enhanced prompt | `prompts/` |
| LED Priority Arbiter | Circuit breaker (VOICE>GAME>ATTRACT>IDLE) + throttle | `led_priority_arbiter.py` |

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

> âš ï¸ A: drive is a USB drive â€” large `git commit` operations can take 5+ minutes. This is normal.

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
  - All three parsers verified: Badlands (daphne.exe) ✅, Conan (Singe.exe) ✅, Rollercoaster (Hypseus.exe) ✅.

- **ScoreKeeper Sam Master Plan** (Antigravity + User):
  - Archived universal score tracking plan with 4-phase rollout.
  - Key principle: "every session gets an explicit outcome" (trustworthy-first).
  - Codex delivered Phases 1-2 code-complete — 5 days ahead of schedule.

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

---
*Arcade Assistant - Built for G&G Arcade, one commit at a time.*
```
