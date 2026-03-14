# ROLLING LOG — Arcade Assistant

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
