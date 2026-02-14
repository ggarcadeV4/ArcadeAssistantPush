## Overview

**Goal:** finish the Controller Chuck ⇄ Console Wizard cascade work (including MAME validation) while preparing LED Blinky for a production-grade “configuration center” refresh. The cascade must remain debt-free, feed the shared baseline, and line up with Phase 4 (LED Blinky Completion) in the project plan. LED Blinky’s roadmap will treat Controller Chuck’s Mapping Dictionary as the single source of truth, the new cascade runner as the delivery pipeline, and Console Wizard as a downstream consumer.

- Controller Chuck now emits encoder snapshots into `state/controller/baseline.json`.
- Console Wizard will consume the same baseline to hydrate handheld mappings.
- LED Blinky must read cascade status, expose manual triggers, and stay in sync with the encoder/handheld updates without bypassing validation or sanctioned paths.

### Latest Implementation Notes (2025-11-24)

- Added `backend/services/led_mapping_service.py`, a sanctioned-path aware helper that loads Controller Chuck's `config/mappings/controls.json`, resolves logical buttons to physical LED channels, and serializes preview/apply payloads with backups + audit metadata.
- Introduced `backend/routers/led.py` with `POST /api/local/led/profile/preview` and `POST /api/local/led/profile/apply`, enforcing `x-scope=config`, dry-run defaults, and `logs/changes.jsonl` logging for every call. The legacy `/led/profile/apply` stub in `led_blinky.py` has been retired in favor of the new workflow.
- Preview responses now return the resolved hardware channels (via `LedChannel` records), so the frontend can display the logical→physical mapping before writes. Apply uses the same preview payload, validates missing buttons, writes to `configs/ledblinky/profiles/*.json` only when sanctioned, and captures backups under `/backups/YYYYMMDD/`.
- Gateway now owns LED routing: `gateway/routes/led.js` proxies `/api/local/led/*`, injects headers (`x-device-id`, `x-panel: led_blinky`, scopes), and blocks direct `http://localhost:8000/led` calls. `frontend/src/services/ledBlinkyClient.js` uses those gateway endpoints exclusively.
- LED Blinky UI now respects Preview→Apply→Backup→Log (Animation Designer buttons call the new preview/apply helpers). Test All/Clear/Random/Wave and the Hardware tab's All On/Off/Chase/Rainbow buttons call `/api/local/led/test`, so every visible control goes through PreviewApplyBackupLog. Dead buttons (Export, Save Pattern, Game Selection, etc.) are disabled with tooltips so production never shows inert actions.

## Step-by-Step Sessions

### Session 1: Backend Real-Time Control (2–3 hours)

- Verify backend stack on Windows host (`AA_DEV_ALLOW_BOOTSTRAP=1`) and ensure `/api/health`, `/api/controller/cascade/status`, and LED endpoints respond.
- Implement LED WebSocket/hardware service refinements:
  - Harden `LEDWebSocketManager` auto-reconnect semantics.
  - Expose a `/led/hardware/status` endpoint reflecting device availability + recent command history.
  - Add integration tests covering LED runner success/failure (mocking subprocess + HID).
- Validate the cascade runner end-to-end (Chuck → MAME → LED) on real hardware, capturing logs for baseline auditing.

### Session 2: Frontend Live Console (2–4 hours)

- Wire LED Blinky panel into the baseline/cascade APIs:
  - Poll `/api/controller/cascade/status` to show LED readiness, last job id, and retry action.
  - Display profile metadata (filename, scope, key-count) and offer preview before apply.
  - Integrate real-time hardware feed (port activity, connection logs) with graceful degradation when backend offline.
- Add manual “Cascade Now” / “Retry Failed” controls that call the controller cascade endpoint, keeping `x-scope`/`x-panel` headers intact.
- Smoke-test against mock + real LED hardware.

### Session 3: Edge Polish & Innovations (2–3 hours)

- Adaptive pattern support: allow preset groups (e.g., “Arcade Night / Kid Mode”) that map to stored profiles and call the cascade runner with preconfigured metadata.
- Implement ROM-aware filtering: optional LaunchBox-driven profile suggestions for active cabinets/playlists.
- Cover edge scenarios:
  - Device disconnect mid-cascade.
  - CLI output overflow (`mame -listxml` large XML) – ensure truncation + user messaging.
  - Oversized profile payloads or locked config files – emit actionable errors and retry guidance.

## Optimizations

- Maintain the modular cascade runner registry (`RunnerSpec`) so LED/MAME stay prioritized; expand to async futures (e.g., `asyncio.gather`) once Windows CLI steps are safe to parallelize.
- Cache manifest/sanctioned path checks per request to avoid redundant disk scans.
- Use incremental baseline updates instead of rewriting large mapping blobs.

## Innovations

- Family / “Arcade Night” presets: curated LED + MAME + RetroArch profiles selectable from the UI with clear preview of affected ROMs.
- Bus sync: optional LaunchBox/ScoreKeeper hooks that broadcast the active session/game to LED Blinky for context-aware lighting.
- Conversational assistant tweaks (Chuck/Wiz) that reference cascade status (“LED lights synced 2m ago; want me to retry?”).

## Edge Cases

- Hardware disconnects or HID permission issues – auto-retry with exponential backoff and clear UI messaging.
- High-frequency cascades (multiple panels firing) – queue requests to avoid conflicting writes; expose status in baseline history.
- Large LED profiles or malformed JSON – validate server-side with diff previews before writing.
- CLI timeouts, locked `.ini`/`.cfg` files, or missing executables – fail fast with actionable errors logged to `logs/changes.jsonl`.

## Verification

- End-to-end Windows regression:
  - Start backend, run `/api/local/controller/cascade/apply`, confirm MAME/LED status `completed`.
  - Trigger LED profile load + preview + apply via UI and confirm actual hardware response.
  - Run `pytest backend/tests/test_controller_cascade.py` + new LED hardware tests.
- Maintain ≥85 % coverage for new backend modules (cascade runners, LED status endpoints) with mocks covering timeout/error branches.
- Manual QA checklist: WebSocket reconnect, cascade retry, preset application, UI fallback when backend/LED unavailable.
