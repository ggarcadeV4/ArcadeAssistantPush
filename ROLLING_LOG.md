# Master Rolling Log

## Net Progress
- **2026-02-13**: Established the "Mandatory Rolling Log" protocol across `AGENTS.md` and all sub-agent files (`GEMINI.md`, `CLAUDE.md`, etc.), creating the `/logs` directory and enforcing daily logging and master roll updates.
- **Read-Only API**: Configured Supabase `read_only_llm` schema and views. Saving JWT to `.env.production`. Git Sync infrastructure finalized with "Classic" PAT and Mission Control protocols (Auto-Handoff) enforced.
- **2026-02-15/16 (Valentine's Day Session)**: Playnite Emulator Wiring — full automation pipeline built and proven.
  - **Ingestion Pipeline**: Built `OnApplicationStarted` extension that reads `pending_import.json` manifests and bulk-imports games via `$PlayniteApi.Database.Games.Add()` with `BufferedUpdate()`. **2,387 games** now in library across 17 platforms.
  - **Emulator Auto-Config** (`Setup-ArcadeEmulators`): Creates 5 emulators (RetroArch 8-core, MAME, Dolphin Tri-Force, Sega Model 2, Super Model) with `CustomEmulatorProfile` objects on first startup. All paths use `{EmulatorDir}` for Golden Drive portability. Key fix: `CustomProfiles` property is null by default after `New-Object Emulator` — must explicitly initialize `ObservableCollection`.
  - **Game Launch Wiring** (`Wire-GameActions`): Scans all games without `GameActions`, builds platform→emulator/profile map, creates `GameAction(Type=Emulator)` with correct `EmulatorId`/`EmulatorProfileId`. **1,960 games wired** to their emulators in one pass.
  - **Event Handlers**: Fixed `OnGameStarted`/`OnGameStopped` parameter binding (`param($eventArgs)` was missing).
  - **Key Learnings**: `$__logger` does NOT work in Playnite PowerShell script extensions — use file-based debug logging (`arcade_debug.log`). LiteDB collection name is `Emulator` (singular), not `Emulators`.
  - **Open Items**: 171 games unmatched (missing emulator profiles for their platforms). Cinema Logic tag injection, Dewey Liaison F9 HUD, Basement Shield scripts, Play Now button remain for next session.
- **2026-02-17 (Late Night)**: Command Center Dashboard — UI code complete, build verified, browser deployment blocked by cache.
  - **Assistants.jsx Rewrite**: Replaced empty `personas` grid with `CommandCenterGrid` (9-agent glassmorphism cards, `AgentCard` component, character pop-out hover effects, inner glows, pill buttons). All existing `?agent=` routing preserved.
  - **index.css**: ~440 lines of Command Center CSS (glassmorphism, Rajdhani font, Lora special panel, responsive breakpoints). Fixed `@import` position to top of file.
  - **Frontend Build**: `npm install` (291 pkgs) + `npx vite build` (v4.5.14, 225 modules, 1.80s) completed clean. Dist hashes: `Assistants-93ad8b5a.js`, `index-97209d6a.css`.
  - **Blocker**: Browser aggressively caches old JS bundles. Need full cache clear or incognito window to see new build. Gateway restart via `start-aa.bat` requires `.env` vars and is slow due to `Test-NetConnection`.
  - **Next**: Clear browser cache → verify grid renders → save 9 character PNGs to `frontend/public/characters/` → rebuild → verify pop-out effects.
- **2026-02-17 (Evening)**: ScoreKeeper Sam Redesign + LED Blinky Fix — shipped to production A: drive.
  - **ScoreKeeper Sam**: Full CSS rewrite (glassmorphism, neon-obsidian, medal effects), JSX restructure with `activeView` toggle (highscores/tournament), leaderboard-first default, quick score footer, personal stats sidebar.
  - **LED Blinky Crash Fix**: `showToast` was defined at line 648 but referenced in `useCallback` dependency array at line 538 → TDZ `ReferenceError`. Moved `showToast` to top of component. Panel loads cleanly.
  - **Infrastructure**: `start-aa.bat` now opens `/` (old-school dashboard) by default. Added dark bg to `.feature-hero` for transparent PNG fix. Build+deploy pipeline via robocopy to `A:\Arcade Assistant Local\frontend\dist`.
  - **Decision**: Old frontend at `/` stays as default (better UX with dual buttons per card, Chuck preserved). New `/assistants` grid available for future expansion.
  - **Open**: Sam voice (STT/TTS) non-functional in new chat sidebar — needs wiring. Tournament mode UI refinement. Live hardware test on basement cab pending.
- **2026-02-20 (Evening)**: LED Blinky Panel Refactor — 5 phases complete, 5500→510 line rewrite.
  - **Phase 1 — Core Panel**: Rewrote `LEDBlinkyPanel.jsx` → `LEDBlinkyPanelNew.jsx` (510 lines). Created `ButtonVisualizer.jsx` (CSS-based, 4 modes), `UserProfileSelector.jsx`, `LEDBlinkyPanel.css` (dark neon arcade aesthetic). Single-view architecture, no tabs.
  - **Phase 2 — State Machine**: Extracted `useLEDPanelState.js` hook — idle/active/calibration/design modes with transitions, animation presets, and mode-aware button click dispatch.
  - **Phase 3 — Calibration Wizard**: Integrated existing `useLEDCalibrationWizard` (blink-click-map) + `useLEDCalibrationSession` (AI global helpers) into panel state. Progress bar, skip button, mapped/skipped counters.
  - **Phase 4 — Design Mode**: Created `useDesignMode.js` (brush/paint/fill/clear + localStorage profiles) + `ColorPalette.jsx` (12 arcade swatches with glow, profile dropdown). `resolvedColors` merges custom colors over idle defaults.
  - **Phase 5 — Voice Commands**: Added 10 `LED_THEMES` (sunset through neon) + `apply_theme` command to `commandExecutor.js`. Extended `useBlinkyChat.js` system prompt with theme vocabulary, creative interpretation mapping, player-specific targeting.
  - **Build**: 227 modules, 0 errors, vite v4.5.14.
  - **Next**: Phase 6 (Gemini function calling), chat escape hatch (R-20), live hardware verification.

- **2026-02-20 (Late Night)**: LED Blinky Chat UI + Gem Architecture  diagnosis and partial deployment.
  - **Chat UI Refactor**: New slide-in chat drawer + large pulsing mic button implemented in `LEDBlinkyPanelNew.jsx` + `LEDBlinkyPanel.css` on dev (C:) repo. Mic button has `mic-pulse` animation when recording. Drawer shows full message history with AI/user bubbles, typing indicator, auto-scroll.  WARNING: UI change NOT yet synced to A: drive.
  - **Chat Error Diagnosed**: Traced to deprecated model `claude-3-5-haiku-20241022` returning HTTP 404. Fixed to `claude-3-5-haiku-latest` in `gateway/adapters/anthropic.js` + `gateway/routes/launchboxAI.js`. Both synced to A: drive.
  - **Gem Architecture Clarified**: Supabase Edge Functions (`anthropic-proxy`, `gemini-proxy`) are the AI proxy layer. API keys live in Supabase secrets. `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `PORT`, `FASTAPI_URL`, `AA_DRIVE_ROOT` all come from `A:\Arcade Assistant Local\.env` injected at boot. C: = dev repo, A: = golden drive production. Gateway must ALWAYS boot from A:.
  - **Provider Switch**: `useBlinkyChat.js` changed `provider: 'claude'` to `provider: 'gemini'`. Gemini adapter defaults to `gemini-2.0-flash`. Synced to A:, frontend rebuilt successfully (4.41s, 0 errors).
  - **Open**: New chat UI JSX/CSS not synced to A: drive. Blinky Gemini chat not yet confirmed. ElevenLabs TTS for Blinky voice not wired. C: to A: sync still manual.
