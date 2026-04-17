# LaunchBox LoRa Redesign — Preservation Contract

**Date:** April 17, 2026
**Source:** Distilled from the Codex functionality inventory of `frontend/src/panels/launchbox/LaunchBoxPanel.jsx` (same day)
**Purpose:** This document defines the functional contract the redesign must honor. Any feature, route, or behavior listed here must work in the redesigned panel. Visual treatment is open — functionality is not.

---

## 1. Structural Constraints (Non-Negotiable)

- Must wrap in `PanelShell` from `frontend/src/panels/_kit/`. This is the shared shell used by all nine panels and provides the visual consistency the redesign exists to achieve.
- Must preserve `DiffPreview` inside the shader preview modal. It is imported from the same `_kit/` barrel and cannot be replaced with a custom diff renderer.
- Header composition must support: status chip, header actions region. `PanelShell` expects these slots.

---

## 2. Library Browsing

- Paginated game list powered by `GET /api/launchbox/games` with query params: `page`, `limit=50`, `sort_by`, `sort_order`, `platform`, `genre`, `year_min`, `year_max`, `search`. Results are server-paged — no client-side filtering of the full library.
- Recent games tab (default) and Quick Stats tab, both inside a collapsible subpanel.
- Each game card displays: box art (dynamic via `/api/launchbox/image/:gameId`), title, genre badge, year chip, platform, relative last-played text, session time, play count, and a play button.
- Box art fallback placeholder renders a controller icon and the game's first character when image load fails.
- Quick Stats tab shows total games, platforms, genres, XML files parsed.
- Pagination controls render only when `totalPages > 1`.
- Subpanel can be collapsed to maximize chat/input space and re-expanded.

---

## 3. Search & Filter

- Search input with 300 ms debounce; triggers server-side query via the `search` param.
- Platform filter dropdown (populated from `GET /api/launchbox/platforms`).
- Genre filter dropdown (populated from `GET /api/launchbox/genres`).
- Decade filter dropdown.
- Sort dropdown (Title A-Z, Year Newest).
- Results count visible.
- Changing any filter resets pagination to page 1.
- `Ctrl+F` / `Cmd+F` expands the subpanel if collapsed and focuses the search input.

---

## 4. Game Launch

- Play button on each game card triggers `POST /api/launchbox/launch/:gameId`. Body is empty. Identity/score/profile data travels in headers.
- Random game button — prefers the backend random endpoint, falls back to the currently loaded page if that endpoint fails. Respects the platform filter only.
- Pegasus launch button — fire-and-forget, no confirmation message.
- RetroArch fallback checkbox — opt-in toggle persisted to localStorage; direct-launch status label in the header reflects diagnostic state (enabled / disabled / unknown) from `GET /api/launchbox/diagnostics/dry-run`.
- Library refresh button triggers `POST /api/launchbox/cache/revalidate`, then a games refetch.
- Stale cache badge renders based on `GET /api/launchbox/cache/status` payload.

---

## 5. LoRa Chat

- Right-side chat drawer overlay with scrim; closable by overlay click or close button.
- Bottom chat input (always visible in the panel body) and sidebar chat input inside the drawer — both backed by the same state so they mirror each other.
- Chat profile selector bound to `activeProfile` — dropdown plus optional profile description.
- Enter sends; in-flight state disables the send path.
- Typing indicator bubble during response streaming.
- Voice visualization block renders while recording.
- `!` badge on the chat toggle button when drawer is closed (tied to `!chatOpen`, not unread tracking).
- Toast for transient feedback, bottom-right, auto-dismisses.

---

## 6. Voice Input

- Prefers browser Web Speech API when available; falls back to MediaRecorder + `WS /ws/audio` streaming.
- Fallback mode auto-stops after sustained silence once speech has been detected.
- Handles the following branches distinctly: permission denied, no microphone support, websocket unavailable, `NOT_CONFIGURED`, `AUDIO_TOO_LONG`.
- TTS playback via `ttsClient` (from `services/ttsClient.js`), with rapid-duplicate suppression and non-blocking error handling — failed TTS must never block a launch or chat turn.
- Both header mic button and sidebar mic button toggle the same recording flow.

---

## 7. Shader Preview Modal

- AI-triggered; opens when `shaderModal.open === true`.
- Shows shader, game, and emulator details plus a config diff rendered by `DiffPreview`.
- Apply button triggers `POST /api/launchbox/shaders/apply` with `{ game_id, shader_name, emulator }`.
- Cancel dismisses without commit.
- Fallback text parsing can force-open an otherwise empty modal when AI response text mentions preview readiness.

---

## 8. Cross-Panel Integrations

- **LED Blinky:** game card hover triggers `POST /api/local/blinky/game-selected`; game launch triggers `POST /api/local/blinky/game-launch`. Both sent via the `useBlinkyGameSelection` hook. `gameStop()` exists in the hook but is not called from the panel — leave that surface intact, do not rewire it.
- **Dewey handoff:** on mount, if URL has context and does not carry `nohandoff`, fetches `GET /api/local/dewey/handoff/launchbox` and plays the handoff text via TTS. URL context text is a separate handoff path that must also remain.

---

## 9. Persistence

- `launchbox:device-id` (localStorage) — generated device ID, persisted across sessions.
- RetroArch fallback checkbox state (localStorage).

---

## 10. Loading, Error, and Empty States

- Loading variant replaces the full body with "Loading game library…" until the initial games request settles.
- Error variant replaces the full body with a retry screen, with distinct copy for backend-starting, LaunchBox-missing, and generic load failures.
- Empty results inside a successful response show "No games match your filters. Try adjusting your selection."
- Metadata failures (platforms/genres/stats) log a warning and do not block the panel.

---

## 11. Backend Route Contract (Complete List)

Every route below must continue to be called with identical method, path, and body/header signatures.

- `GET /api/launchbox/cache/status`
- `GET /api/launchbox/plugin-status`
- `GET /api/launchbox/platforms`
- `GET /api/launchbox/genres`
- `GET /api/launchbox/stats`
- `GET /api/launchbox/diagnostics/dry-run`
- `GET /api/launchbox/games` (query-param filters)
- `POST /api/launchbox/cache/revalidate`
- `POST /api/launchbox/launch/:gameId`
- `POST /api/launchbox/shaders/apply`
- `POST /api/local/blinky/game-selected`
- `POST /api/local/blinky/game-launch`
- `GET /api/local/dewey/handoff/launchbox`
- `GET /api/launchbox/image/:gameId` (image src, not fetched directly)
- `WS /ws/audio` (voice fallback)
- `/api/voice/tts` (via `ttsClient`)

---

## 12. Known Debt — Do Not Carry Forward

- `// Mock recent games for display while data loads (TODO: Remove when using real data)` at `LaunchBoxPanel.jsx:971` — remove, do not recreate in the redesign.
- `// TODO: Verify Dewey ElevenLabs voice ID` at `ttsClient.js:500` — out of scope for this redesign; leave as-is.

---

## 13. Verification Criteria

The redesign is functionally complete when:

- Every feature in sections 2–10 is demonstrably working in the browser.
- Every backend route in section 11 is being called with identical method, path, and body/header signatures.
- `PanelShell` wraps the panel.
- `DiffPreview` renders inside the shader modal.
- No regression in Blinky hover lighting, Dewey handoff, or voice fallback.
- Keyboard shortcut `Ctrl+F` / `Cmd+F` still focuses search.
- `npm run build` completes cleanly, and the compiled `dist/` renders in AA with no console errors.

Visual fidelity to Stitch output is a separate acceptance criterion and does not override functional preservation.

---

**End of contract.**
