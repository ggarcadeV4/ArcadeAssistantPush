# LED Blinky Session Log

## Session 4 – Gateway + Frontend Hardening (2025-??-??)

- **Gateway WebSocket proxy**: Added `gateway/ws/led.js` and wired it up in `gateway/server.js` so every LED socket goes through `/api/local/led/ws`, injecting `x-device-id`, `x-panel=led-blinky`, and correlation headers while keeping connection logs for `/api/local/led/status`.
- **REST routing fixes**: Rebuilt `gateway/routes/led.js` so `/api/local/led/*` enforces scopes (`local|state|config`), correlation ids, and exposes status/devices/ws-disconnect endpoints required by the audit doc.
- **Client helpers**: Updated `frontend/src/services/ledBlinkyClient.js` with correlation-aware `commonHeaders`, `buildGatewayWebSocketUrl`, `getLEDStatus`, `runLEDPattern`, and `setLEDBrightness`, ensuring every fetch call carries the sanctioned headers.
- **LEDBlinkyPanel refactor**:
  - Removed the manual WebSocket URL input; the panel now displays the gateway-issued endpoint and refreshes `/api/local/led/status` whenever the Hardware tab mounts.
  - `LEDWebSocketManager` listens for gateway notices, stores the gateway connection id, and invokes the REST disconnect endpoint on cleanup.
  - Quick Controls (Test All, Clear, Random) and the brightness slider now hit `/api/local/led/test`, `/pattern/run`, and `/brightness` respectively—no direct WebSocket writes.
  - Added a reusable `ComingSoonTag` and disabled every audit-flagged control (Wave, Shared tab, Save/Export, hardware Chase/Rainbow, pattern save/load) with consistent messaging.
  - Preview-before-Apply enforcement: the Apply button stays disabled until a successful preview payload matches the current JSON, preventing accidental writes outside the preview/apply pipeline.
- **Acceptance checks**: Verified that no UI action bypasses the gateway headers/PreviewApply rules and documented the behavior in the implementation summary for easy rollback if needed.

> This log captures the high-level intent so we can trace Session 4 changes quickly if we need to roll back or investigate regressions.

## Session 6 — Game Profiles + Launch Hook (2025-11-24)

- **Game profile store**: Introduced `backend/services/led_game_profiles.py`, a sanctioned JSON store under `configs/ledblinky/game_profiles.json` that only records logical metadata (game id/title/platform, profile name, timestamps). Every write enforces manifest paths, creates a backup, and defers logging to the router so we keep audit coverage.
- **FastAPI endpoints**: Extended `backend/routers/led.py` with `GET /led/game-profile`, `GET /led/game-profiles`, and `POST /led/game-profile/{preview|apply}` (plus DELETE). Preview runs profiles through `LEDMappingService` for Chuck-resolved button/channel summaries; apply requires `x-scope=config`, respects Preview-before-Apply, updates the store, and logs `bind_game_profile` events to `logs/changes.jsonl`.
- **Gateway + client wiring**: `gateway/routes/led.js` now proxies the new routes with the same header enforcement as other LED calls. `frontend/src/services/ledBlinkyClient.js` gained helpers for fetching bindings, previewing, applying, and clearing while reusing the `commonHeaders` generator so every request carries `x-device-id`, `x-panel=led-blinky`, `x-scope`, and `x-corr-id`.
- **Game Profiles tab**: The Game Profiles mode inside `LEDBlinkyPanel.jsx` became fully interactive: search LaunchBox games, view existing bindings, select from the LED Profile Library dropdown, Preview bindings (showing target file, resolved channels, and diffs), and only enable Apply when the latest preview matches the selected (game, profile) pair. Clear Binding issues a DELETE and resets the local cache.
- **Launch pipeline hook**: Updated `backend/routers/launchbox.py` so, right after the inflight launch guard, it checks the store for a bound profile and runs `LEDMappingService.apply` (without blocking the launch on failure). Each auto-apply is logged as `launch_auto_apply` in `logs/changes.jsonl`, setting the stage for future hardware-level LED activation when the emulator starts.

> Session 6 closes the Game Profiles loop: bindings live in sanctioned configs with audit trails, the UI enforces Preview-before-Apply, and LaunchBox applies the chosen profile automatically ahead of the actual game launch.

## Session 7 — Hardware LED Engine (2025-11-24)

- **Engine architecture**: Added `backend/services/led_engine/` with a structured runtime:
  - `state.py` for shared dataclasses, `patterns.py` (solid/pulse/chase/rainbow brightness frames), and `ws_protocol.py` that normalizes gateway WebSocket payloads.
  - `devices.py` + `ledwiz_driver.py` implement a registry of LED devices (real LED-Wiz HID driver plus a mock fallback). The driver batches writes into LED-Wiz packets, throttles updates, and logs HID errors without crashing FastAPI.
  - `engine.py` hosts the asynchronous `LEDEngine` loop that merges queued commands, applies global brightness, tracks active patterns, and streams frames to the registry on a 50ms cadence.
  - `__init__.py` exposes `get_led_engine`, stashing a singleton on FastAPI’s `app.state`.
- **Router integration**: `backend/routers/led.py` now orchestrates everything:
  - `/api/local/led/test`, `/pattern/run`, `/pattern/clear`, `/brightness`, `/devices`, `/status`, and `/led/ws` all issue commands to `LEDEngine`.
  - `/profile/apply` and `/game-profile/apply` still run through `LEDMappingService`/Chuck cascades, but the resolved logical buttons are immediately streamed into the runtime engine (no physical metadata is stored on disk).
  - The WebSocket endpoint validates messages via `ws_protocol.parse_ws_message`, uses `LEDMappingService` to resolve manual button toggles, and feeds solid/pulse/chase/rainbow commands into the engine.
- **Gateway bridge**: `gateway/ws/led.js` now falls back to the backend WebSocket (`/api/local/led/ws`) when `LED_HARDWARE_WS_URL` isn’t set, ensuring the panel always talks to the new engine.

> Session 7 delivers the first production LED engine: Chuck remains the source of truth for logical-to-physical mapping, while the new runtime daemon handles HID writes, pattern rendering, and real-time commands from both REST and WebSocket surfaces without ever persisting hardware metadata.
