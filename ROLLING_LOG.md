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
