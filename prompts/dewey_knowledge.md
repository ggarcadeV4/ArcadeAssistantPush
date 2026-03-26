# Dewey Knowledge Base

## 1. Panel Routing Table

Dewey's handoff chips are driven by the routing logic in `frontend/src/panels/dewey/DeweyPanel.jsx`.

Current routing destinations:

- `controller_chuck` / Control-a-Chuck: arcade panel controls, joystick/button faults, encoder wiring, pin mapping, iPAC/Ultimarc, remaps, stuck buttons.
- `console_wizard` / Control-a-Wizard: gamepads and console-style controllers, Xbox/PlayStation/8BitDo, xinput/dinput, deadzones, trigger setup, controller profiles, RetroArch/controller mapping.
- `interface` / Arcade Interface: UI, HUD, menus, panel layout, overlays, and interface bugs.
- `gunner` / Gunner: light guns, crosshair issues, aiming, Sinden, Gun4IR, calibration.
- `led-blinky` / LED Blinky: LEDs, button lights, RGB scenes, marquee lights, cabinet lighting behavior.
- `launchbox` / LaunchBox LoRa: LaunchBox, ROM/library browsing, game launching, platform wheels, library management.
- `scorekeeper` / ScoreKeeper Sam: scores, leaderboards, tournaments, brackets, rankings, high-score workflows.
- `voice` / Vicky Voice: voice, mic, microphone, speech recognition, listen mode, audio-command issues.
- `system-health` / Doc: lag, slowdowns, freezes, crashes, overheating, CPU, RAM, FPS, performance and health monitoring.

Routing rules:

- If the message clearly refers to console/gamepad controllers and not arcade wiring, prefer `console_wizard`.
- If the message clearly refers to cabinet panel hardware, buttons, joysticks, encoder pins, or wiring, prefer `controller_chuck`.
- Dewey recommends at most 2 helper chips and usually 1 when the intent is clear.
- Dewey still handles general history, recommendations, trivia, and gaming-news conversation directly.

Note on persona roster:

- Dewey's prompt summary also mentions Vicky, LoRa, Control-a-Chuck, Control-a-Wizard, LED Blinky, Gunner, Scorekeeper Sam, Doc, and Wiz.
- The actual chip-routing table in code currently uses the 9 concrete panel IDs listed above, including `interface`.

## 2. Handoff Protocol

The Dewey handoff API lives in `backend/routers/dewey.py`.

Write handoff:

- Endpoint: `POST /api/local/dewey/handoff`
- JSON body:

```json
{
  "target": "launchbox",
  "summary": "User wants a four-player beat-em-up with fast action.",
  "timestamp": "2026-03-15T14:30:00Z"
}
```

Behavior:

- Dewey writes `handoff.json` to `drive_root/handoff/{target}/handoff.json`.
- The saved JSON contains `target`, `summary`, and `timestamp`.

Read handoff:

- Endpoint: `GET /api/local/dewey/handoff/{target}`
- Returns `{ "handoff": null }` when no handoff file exists.
- Returns `{ "handoff": { ... } }` when the file exists and parses cleanly.

Frontend usage:

- Dewey opens panels with a `context` URL parameter for immediate text handoff.
- Target panels such as LaunchBox, Voice, Gunner, and Console Wizard also fetch the JSON handoff endpoint on arrival for richer context.

## 3. Profile System

Shared profile state is owned by `ProfileContext` in `frontend/src/context/ProfileContext.jsx`.

Canonical storage:

- `.aa/state/profile/user.json`
- `.aa/state/profile/primary_user.json`
- `.aa/state/profile/consent.json`

API endpoints:

- `GET /api/local/profile`
- `POST /api/local/profile/preview`
- `POST /api/local/profile/apply`
- `GET /api/local/profile/primary`
- `PUT /api/local/profile/primary`

How Dewey receives profile data:

- `ProfileContext` loads both `/api/local/profile` and `/api/local/profile/primary`.
- It merges them into a shared `profile` object and refreshes when the session WebSocket broadcasts `profile_updated`, `session_started`, or `session_ended`.
- `DeweyPanel.jsx` derives `currentUser` from `sharedProfile`.
- When the user changes Dewey's identity picker, Dewey updates `ProfileContext` locally and persists the primary identity through `PUT /api/local/profile/primary`.

Vicky opt-in flow:

- Vicky is the identity source of truth for cross-panel personalization.
- First use starts in an explicit consent gate: `Accept & Continue` or `Play as Guest`.
- `Play as Guest` keeps the active identity anonymous and avoids profile writes.
- `Accept & Continue` unlocks the profile registration form, but the actual consent record is written only when Vicky saves and broadcasts the profile.
- On successful `Save & Broadcast`, Vicky writes `consent: true` and updates `.aa/state/profile/primary_user.json`.
- Dewey consumes that broadcast through `ProfileContext`, so the active user name and preferences change reactively without Dewey owning consent state directly.

Relevant primary profile fields:

- `user_id`
- `display_name`
- `initials`
- `voice_prefs`
- `vocabulary`
- `training_phrases`

## 4. Trivia Engine

The trivia API and persistence layer live in `backend/routers/dewey.py`.

Core endpoints:

- `GET /api/local/dewey/trivia/questions`
- `POST /api/local/dewey/trivia/collection`
- `GET /api/local/dewey/trivia/stats/{profile_id}`
- `POST /api/local/dewey/trivia/save-stats`
- `GET /api/local/dewey/trivia/fresh`
- `POST /api/local/dewey/trivia/generate`
- `POST /api/local/dewey/trivia/generate-ai`

Primary UI categories shown by Dewey's trivia flow:

1. `arcade`
2. `console`
3. `genre`
4. `decade`
5. `popculture`
6. `collection`
7. `mixed`

Difficulty levels:

1. `easy`
2. `medium`
3. `hard`

Implementation details:

- The base question pool is loaded from `frontend/src/panels/dewey/trivia/triviaDatabase.json`.
- Generated news-based trivia also exists and is managed by the same Dewey router and `backend/services/dewey/trivia_generator.py`.
- Background scheduling and freshness management are handled by `backend/services/dewey/trivia_scheduler.py`.
- Supporting generation helpers live in `backend/services/dewey/service.py` and `backend/services/dewey/trivia_generator.py`.
- Trivia preferences and lifetime stats are persisted into each profile's `tendencies.json`.

## 5. F9 Overlay

The Dewey overlay is tied to the global hotkey system.

- Pressing `F9` triggers the hotkey flow in `backend/routers/hotkey.py`.
- The hotkey router can bootstrap the Electron Dewey sidecar when no overlay connection is active.
- Dewey recognizes overlay mode from the query string: `?mode=overlay`.
- `DeweyPanel.jsx` checks `new URLSearchParams(location.search).get('mode') === 'overlay'`.
- In overlay mode, Dewey can still hand off to full panels, and chip handoffs explicitly expand to the full-size target panel.

## 6. News Architecture

Gaming news is fetched from RSS feeds by `backend/routers/gaming_news.py`.

Source architecture:

- IGN
- GameSpot
- Polygon
- PC Gamer
- Kotaku
- Eurogamer
- Destructoid

Runtime behavior:

- The backend aggregates RSS feeds with `httpx` and `feedparser`.
- Headlines are cached for 12 hours.
- Dewey injects current gaming headlines into AI context only when the user's message looks like a news query.
- The runtime injection block is built from real RSS headlines, including source names and relative recency, so Dewey can answer "what's new in gaming?" with live context instead of stale model knowledge.
