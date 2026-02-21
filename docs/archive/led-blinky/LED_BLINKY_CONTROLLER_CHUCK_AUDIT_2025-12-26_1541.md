# 12/26/2025 at 3:41 PM. Audit for LED blinky and controller chuck integration/button mapping issues

## Scope and intent
- Goal: verify controller and LED integration endpoints, confirm mapping flows, and identify
  mismatches that block planned behavior.
- Panels reviewed:
  - Controller Panel (interface/controller check): `frontend/src/panels/controller/ControllerPanel.jsx`
  - Controller Chuck Panel (legacy Chuck UI): `frontend/src/panels/controller/ControllerChuckPanel.jsx`
  - LED Blinky Panel: `frontend/src/components/LEDBlinkyPanel.jsx`
- Backend and gateway reviewed:
  - Controller router: `backend/routers/controller.py`
  - Controller AI router: `backend/routers/controller_ai.py`
  - Devices router: `backend/routers/devices.py`
  - Diagnostics router: `backend/routers/diagnostics.py`
  - Hardware router: `backend/routers/hardware.py`
  - LED router: `backend/routers/led.py`
  - LED Blinky router (profiles): `backend/routers/led_blinky.py`
  - LaunchBox router: `backend/routers/launchbox.py`
  - Marquee router: `backend/routers/marquee.py`
  - Autoconfig router: `backend/routers/autoconfig.py`
  - Scope validation: `backend/services/policies.py`
  - Gateway LED proxy: `gateway/routes/led.js`
- Line reference format: `path:line` (1-based).

## Intent and data flow summary
- Controller mapping is stored in `config/mappings/controls.json`, exposed via
  `/api/local/controller/*` endpoints. Controller Panel and Controller Chuck both
  read, preview, and apply mapping updates via those endpoints.
- LED profiles and channel wiring resolve logical button names from the controller
  mapping. LED profiles are stored in `configs/ledblinky/profiles/*.json`. Game
  bindings are stored in `configs/ledblinky/game_profiles.json`.
- Game display uses the marquee preview/now-playing endpoints. LED updates are
  triggered only when a game is launched or when a profile is explicitly applied
  through the LED panel.

## Endpoint mapping (intent check)

### Controller Panel (interface/controller check)
- GET `/api/local/controller/mapping`
  - Frontend call: `frontend/src/panels/controller/ControllerPanel.jsx:680`
  - Backend route: `backend/routers/controller.py:2217`
  - Router mount: `backend/app.py:496`
- POST `/api/local/controller/mapping/preview`
  - Frontend call: `frontend/src/panels/controller/ControllerPanel.jsx:980`
  - Backend route: `backend/routers/controller.py:2300`
- POST `/api/local/controller/mapping/apply`
  - Frontend calls: `frontend/src/panels/controller/ControllerPanel.jsx:1006`,
    `frontend/src/panels/controller/ControllerPanel.jsx:1594`
  - Backend route: `backend/routers/controller.py:2386`
- POST `/api/local/controller/mapping/reset`
  - Frontend call: `frontend/src/panels/controller/ControllerPanel.jsx:1034`
  - Backend route: `backend/routers/controller.py:2581`
- POST `/api/local/controller/mapping/set`
  - Frontend call: `frontend/src/panels/controller/ControllerPanel.jsx:1087`
  - Backend route: `backend/routers/controller.py:1557`
- POST `/api/local/controller/encoder-mode`
  - Frontend call: `frontend/src/panels/controller/ControllerPanel.jsx:1145`
  - Backend route: `backend/routers/controller.py:1719`
- GET `/api/local/controller/devices`
  - Frontend call: `frontend/src/panels/controller/ControllerPanel.jsx:770`
  - Backend routes (duplicate): `backend/routers/controller.py:714`,
    `backend/routers/controller.py:3083`
- GET `/api/local/controller/health`
  - Frontend call: `frontend/src/panels/controller/ControllerPanel.jsx:795`
  - Backend route: `backend/routers/controller.py:3186`
- SSE `/api/controller/ai/events`
  - Frontend call: `frontend/src/hooks/useControllerEvents.js:28`
  - Backend route: `backend/routers/controller_ai.py:62`
  - Router mount: `backend/app.py:500`
- GET `/api/local/devices/snapshot`
  - Frontend call: `frontend/src/services/deviceClient.js:4`
  - Backend route: `backend/routers/devices.py:26`
  - Router mount: `backend/app.py:483`
- POST `/api/local/devices/classify`
  - Frontend call: `frontend/src/services/deviceClient.js:13`
  - Backend route: `backend/routers/devices.py:52`
- GET `/api/local/controller/diagnostics/next-event`
  - Frontend call: `frontend/src/services/deviceClient.js:126`
  - Backend route: `backend/routers/diagnostics.py:12`
  - Backing implementation: `backend/routers/controller.py:861`
- Click-to-map input detection:
  - POST `/api/local/controller/input-detect/start`: `frontend/src/hooks/useCaptureMode.js:64`
  - GET `/api/local/controller/input-detect`: `frontend/src/hooks/useCaptureMode.js:221`
  - POST `/api/local/controller/input-detect/clear`: `frontend/src/hooks/useCaptureMode.js:236`
  - Backend routes: `backend/routers/controller.py:3565`,
    `backend/routers/controller.py:3528`, `backend/routers/controller.py:3550`
- Wiring wizard:
  - Frontend: `frontend/src/services/deviceClient.js:55`
  - Backend routes: `backend/routers/controller.py:3282`,
    `backend/routers/controller.py:3304`, `backend/routers/controller.py:3314`,
    `backend/routers/controller.py:3332`, `backend/routers/controller.py:3343`
- Learn wizard:
  - Frontend: `frontend/src/services/deviceClient.js:146`,
    `frontend/src/services/deviceClient.js:163`
  - Backend routes: `backend/routers/controller.py:972`,
    `backend/routers/controller.py:1141`, `backend/routers/controller.py:1191`,
    `backend/routers/controller.py:1314`, `backend/routers/controller.py:1348`

### Controller Chuck Panel (legacy Chuck UI)
- API base: `/api/local/controller`
  - Frontend constant: `frontend/src/panels/controller/ControllerChuckPanel.jsx:19`
  - Backend router mount: `backend/app.py:496`
- Mapping read/preview/apply/reset:
  - Frontend calls: `frontend/src/panels/controller/ControllerChuckPanel.jsx:1872`,
    `frontend/src/panels/controller/ControllerChuckPanel.jsx:1933`,
    `frontend/src/panels/controller/ControllerChuckPanel.jsx:1968`,
    `frontend/src/panels/controller/ControllerChuckPanel.jsx:2021`
  - Backend routes: `backend/routers/controller.py:2217`,
    `backend/routers/controller.py:2300`, `backend/routers/controller.py:2386`,
    `backend/routers/controller.py:2581`
- MAME config preview/apply:
  - Frontend calls: `frontend/src/panels/controller/ControllerChuckPanel.jsx:2128`,
    `frontend/src/panels/controller/ControllerChuckPanel.jsx:2154`
  - Backend routes: `backend/routers/controller.py:2876`,
    `backend/routers/controller.py:2933`
- Device detection and health:
  - Frontend calls: `frontend/src/panels/controller/ControllerChuckPanel.jsx:1574`,
    `frontend/src/panels/controller/ControllerChuckPanel.jsx:1606`
  - Backend routes: `backend/routers/controller.py:714`,
    `backend/routers/controller.py:3083`, `backend/routers/controller.py:3186`
- Autoconfig detect/mirror:
  - Frontend calls: `frontend/src/panels/controller/ControllerChuckPanel.jsx:2213`,
    `frontend/src/panels/controller/ControllerChuckPanel.jsx:2238`
  - Backend routes: `backend/routers/autoconfig.py:61`,
    `backend/routers/autoconfig.py:153`
  - Feature flag default: `backend/routers/autoconfig.py:36`
- Hardware info endpoints (expected backend path):
  - Backend mount path: `backend/app.py:497`
  - Backend endpoints: `backend/routers/hardware.py:133`,
    `backend/routers/hardware.py:223`

### LED Blinky panel
- API base and gateway WS helper:
  - `/api/local/led` base: `frontend/src/services/ledBlinkyClient.js:6`
  - WS URL builder: `frontend/src/services/ledBlinkyClient.js:50`
- Status:
  - Frontend call: `frontend/src/services/ledBlinkyClient.js:113`
  - Gateway proxy: `gateway/routes/led.js:268`
  - Backend status: `backend/routers/led.py:859`
- Profile preview/apply:
  - Frontend calls: `frontend/src/services/ledBlinkyClient.js:71`,
    `frontend/src/services/ledBlinkyClient.js:82`
  - Backend routes: `backend/routers/led.py:618`,
    `backend/routers/led.py:638`
- Game profile binding preview/apply:
  - Frontend calls: `frontend/src/services/ledBlinkyClient.js:217`,
    `frontend/src/services/ledBlinkyClient.js:228`
  - Backend routes: `backend/routers/led.py:931`,
    `backend/routers/led.py:945`
- Channel wiring:
  - Frontend call: `frontend/src/services/ledBlinkyClient.js:250`
  - Backend routes: `backend/routers/led.py:405`,
    `backend/routers/led.py:420`, `backend/routers/led.py:437`,
    `backend/routers/led.py:461`
- LaunchBox game search for LED bindings:
  - Frontend call: `frontend/src/services/ledBlinkyClient.js:187`
  - Backend router prefix: `backend/routers/launchbox.py:72`
- LED game binding storage:
  - Store path: `backend/services/led_game_profiles.py:18`
- LED logical button list source:
  - Controls mapping read: `backend/routers/led.py:260`
  - Mapping service docstring: `backend/services/led_mapping_service.py:1`

## Findings and mismatches

### 1) LED status scope mismatch blocks backend runtime status
- Severity: High
- Evidence:
  - Backend requires a non-standard scope:
    - `backend/routers/led.py:859` (`get_led_status`)
    - `backend/routers/led.py:860` (`require_scope(request, "local")`)
  - Scope validator only accepts config|state|backup:
    - `backend/services/policies.py:110`
    - `backend/services/policies.py:114`
  - Gateway forces status requests to x-scope=state:
    - `gateway/routes/led.js:268`
    - `gateway/routes/led.js:269`
  - Frontend client sets x-scope=state for status:
    - `frontend/src/services/ledBlinkyClient.js:113`
    - `frontend/src/services/ledBlinkyClient.js:116`
- Mismatch:
  - Backend demands `local`, but the scope validator rejects `local`, and the gateway
    always uses `state`. This makes `/api/local/led/status` fail at FastAPI even when
    the gateway returns 200 with a backend_error payload.
- Impact:
  - LED Blinky panel can get WS info from gateway, but backend runtime status (engine
    details, device discovery) is missing or flagged as backend_error.

### 2) Controller Panel "Clear P{player}" writes null entries that fail validation
- Severity: High
- Evidence:
  - Frontend writes nulls into pendingChanges:
    - `frontend/src/panels/controller/ControllerPanel.jsx:1619`
  - Those pendingChanges are POSTed directly:
    - `frontend/src/panels/controller/ControllerPanel.jsx:1006`
    - `frontend/src/panels/controller/ControllerPanel.jsx:1594`
  - Backend validation rejects non-object mapping values:
    - `backend/routers/controller.py:694`
    - `backend/routers/controller.py:698`
  - Validation runs in preview/apply:
    - `backend/routers/controller.py:2337`
    - `backend/routers/controller.py:2451`
- Mismatch:
  - Clearing a player produces `{ "pX.buttonY": null }`, but the backend expects each
    mapping entry to be an object with at least `pin` (and optional `type`).
- Impact:
  - Preview/apply fails with validation errors when a player clear is attempted.
  - End users cannot clear a player cleanly through this UI path.

### 3) Controller Chuck Panel hardware endpoints use the wrong prefix
- Severity: High
- Evidence:
  - Frontend uses `/api/local/hardware`:
    - `frontend/src/panels/controller/ControllerChuckPanel.jsx:20`
    - `frontend/src/panels/controller/ControllerChuckPanel.jsx:618`
    - `frontend/src/panels/controller/ControllerChuckPanel.jsx:641`
  - Backend mounts hardware router at `/api/hardware`:
    - `backend/app.py:497`
  - Actual hardware endpoints:
    - `backend/routers/hardware.py:133`
    - `backend/routers/hardware.py:223`
- Mismatch:
  - The panel calls `/api/local/hardware/...`, but the server only serves
    `/api/hardware/...`.
- Impact:
  - Supported board list and troubleshooting hints likely 404 from the Chuck panel.

### 4) Duplicate `/api/local/controller/devices` route definitions
- Severity: Medium
- Evidence:
  - First definition: `backend/routers/controller.py:714`
  - Second definition: `backend/routers/controller.py:3083`
  - Frontend callers:
    - `frontend/src/panels/controller/ControllerPanel.jsx:770`
    - `frontend/src/panels/controller/ControllerChuckPanel.jsx:1574`
- Mismatch:
  - Two handlers share the same path and method but return slightly different shapes
    (different fields such as `warnings` vs `hints`).
- Impact:
  - Response shape depends on which handler is registered last, risking UI drift
    and inconsistent error messaging.

### 5) Game display does not drive LED updates (only launch does)
- Severity: Medium
- Evidence:
  - LED profiles are applied only during launch:
    - `backend/routers/launchbox.py:2291`
    - `backend/routers/launchbox.py:862`
  - Marquee preview (displayed game) is updated independently:
    - `backend/routers/marquee.py:354`
    - `frontend/src/panels/marquee/MarqueeDisplayV2.jsx:63`
  - Now-playing display polls a separate endpoint:
    - `frontend/src/panels/marquee/MarqueeMedia.jsx:36`
- Mismatch:
  - Displayed game (preview/scroll/now-playing) has no LED hook, while launches do.
- Impact:
  - Button lighting changes only after a launch, not while browsing or previewing
    titles. This does not satisfy "light buttons for the currently displayed game."

### 6) LED Learn Wizard UI does not persist wiring or detect trackball
- Severity: Medium
- Evidence:
  - Wizard state and UI:
    - `frontend/src/components/LEDBlinkyPanel.jsx:451`
    - `frontend/src/components/LEDBlinkyPanel.jsx:1933`
  - Trackball device state is declared but never set:
    - `frontend/src/components/LEDBlinkyPanel.jsx:454`
    - No other references beyond reads at `frontend/src/components/LEDBlinkyPanel.jsx:2050`
  - "Save and Exit" only dismisses the wizard and shows a toast:
    - `frontend/src/components/LEDBlinkyPanel.jsx:2137`
    - `frontend/src/components/LEDBlinkyPanel.jsx:2139`
  - Calibration endpoints exist but are not called by the wizard flow:
    - `frontend/src/components/LEDBlinkyPanel.jsx:757`
    - `frontend/src/components/LEDBlinkyPanel.jsx:855`
- Mismatch:
  - The wizard is visually present but does not write LED channel mappings nor
    start calibration. Trackball detection is not wired to any input source.
- Impact:
  - LED Learn Wizard cannot actually map LEDs or save wiring.

### 7) LED profile editor UI only covers P1/P2 button1-4
- Severity: Low
- Evidence:
  - Default mapping form only defines P1/P2 button1-4:
    - `frontend/src/components/LEDBlinkyPanel.jsx:284`
  - UI loops only render those four buttons for P1 and P2:
    - `frontend/src/components/LEDBlinkyPanel.jsx:4328`
    - `frontend/src/components/LEDBlinkyPanel.jsx:4382`
  - LED wiring derives logical buttons from controller mapping:
    - `backend/routers/led.py:260`
- Mismatch:
  - The UI does not expose P3/P4 or buttons 5-8, nor start/coin/joystick directions,
    even though those logical buttons exist in the controller mapping.
- Impact:
  - Additional controls require manual JSON editing or channel wiring UI, which
    makes full-cabinet LED coverage harder.

### 8) Controller autoconfig endpoints are disabled by default
- Severity: Low
- Evidence:
  - Feature flag default false and 501 when disabled:
    - `backend/routers/autoconfig.py:11`
    - `backend/routers/autoconfig.py:36`
    - `backend/routers/autoconfig.py:46`
  - Controller Chuck uses these endpoints:
    - `frontend/src/panels/controller/ControllerChuckPanel.jsx:2213`
    - `frontend/src/panels/controller/ControllerChuckPanel.jsx:2238`
- Mismatch:
  - The UI calls autoconfig endpoints that are disabled unless the env var is set.
- Impact:
  - Auto-detect/mirror fails by default, leading to confusing error flow.

## Notes on LED to controller mapping integration
- LED channel wiring metadata resolves logical buttons from controller mapping:
  - `backend/routers/led.py:260`
- LED mapping service explicitly depends on Chuck controls.json:
  - `backend/services/led_mapping_service.py:1`
- This means any controller mapping gaps or invalid entries directly impact which
  LED buttons are considered "known" vs "unmapped."

## Recommendations (order of impact)
1) Fix LED status scope mismatch
   - Align backend scope expectation with validator and gateway.
   - Options: change `require_scope(request, "local")` to `state`, or allow `local`
     in `backend/services/policies.py` and update gateway to send `local`.
2) Fix Controller Panel clear flow
   - Use `mapping/clear` per control or remove null entries before preview/apply.
3) Correct Controller Chuck hardware prefix
   - Update frontend to `/api/hardware/...` or mount hardware router at `/api/local/hardware`.
4) Remove duplicate `/controller/devices` route
   - Keep one handler and align response shape with UI expectations.
5) Add LED updates for displayed game
   - Apply LED profile on marquee preview or now-playing update, not only on launch.
6) Wire LED Learn Wizard to calibration endpoints
   - Use `startLEDCalibration`, `assignLEDCalibration`, and `applyLEDChannels` during
     wizard steps; add actual trackball detection source.
7) Expand LED profile UI coverage
   - Include P3/P4 and buttons 5-8, plus start/coin/joystick if desired.
8) Surface autoconfig feature flag state in UI
   - Inform the user when autoconfig is disabled and how to enable it.

