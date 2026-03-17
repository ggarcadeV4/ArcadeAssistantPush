# Gunner Knowledge Base

## 1. Supported Hardware

Gunner's active `/api/local/gunner/devices` route uses the legacy HID detector in `backend/services/gunner_hardware.py`.

Known USB signatures in that detector:

- Sinden Light Gun: `VID 0x16C0`, `PID 0x0F38`
- AimTrak Light Gun: `VID 0xD209`, `PID 0x1601`
- Gun4IR: `VID 0x2341`, `PID 0x8036`

Detection is signature-based. The detector scans `hid.enumerate()` and only returns devices whose vendor/product IDs match those entries.

Known quirks from the current code:

- The active detector is the legacy `USBDetector`, not the newer multi-gun registry.
- Device IDs returned by the legacy detector are numeric (`1`, `2`, etc.), not stable hardware UUIDs.
- Mock devices can be returned by `MockDetector`, but the active Gunner panel filters them out unless frontend mock hardware is explicitly enabled.
- The prompt text also mentions emulator guidance for MAME, Dolphin, DemulShooter, recoil solenoids, and IR sensor placement. Those are advisory topics, not direct hardware control features.

## 2. Calibration Workflow

Backend calibration endpoints exist in `backend/routers/gunner.py`:

- `POST /api/local/gunner/calibrate/point`
- `POST /api/local/gunner/calibrate`
- `POST /api/local/gunner/calibrate/stream`

Current backend calibration flow:

1. Validate that the target device exists in the current detector results.
2. Accept exactly 9 calibration points for the full calibration workflow.
3. Calculate accuracy from point confidence values.
4. Persist calibration metadata to the local gun profile store.
5. Save a per-user, per-game local profile as backup.

`calibrate/stream` returns server-sent events with:

- processing progress
- partial accuracy
- final accuracy
- selected calibration mode
- suggested adjustments
- optional retro-mode validation results and recommendations

Important limitation:

- The active modular `CalibrationTab` in the mounted Gunner panel is currently local UI state only and does not call these backend endpoints.
- The older `LightGunsPanel.jsx` contains the richer wired calibration flow, but it is preserved for rollback and is not the active mounted panel.

Local storage path for saved profiles and calibration metadata:

- `.aa/state/gun_profiles`

## 3. Profile System

Profile persistence is handled by `backend/services/gunner_config.py`.

Per-game profile files are stored as local JSON under:

- `.aa/state/gun_profiles/{user_id}_{game}.json`

Fields written by `GunnerConfigService.save_profile()`:

- `user_id`
- `game`
- `points`
- `sensitivity`
- `deadzone`
- `offset_x`
- `offset_y`
- `created_at`

Additional metadata written by `GunnerService._save_to_supabase()` despite the method name:

- `device_id`
- `accuracy`
- `metadata`

Important limitation:

- `POST /api/local/gunner/profile/apply` is only a legacy acknowledgement stub.
- There is no real "push profile to gun hardware" path in the current `/gunner` router.

## 4. Device Detection

The active scan route is:

- `GET /api/local/gunner/devices`

It uses `detector_factory()` in `backend/services/gunner_factory.py`.

Factory behavior:

- If `ENVIRONMENT=dev` and `AA_USE_MOCK_GUNNER=true`, the factory returns `MockDetector`.
- Otherwise it attempts to use `USBDetector`.

Legacy detector behavior:

- `USBDetector` requires the Python `hid` module.
- If HID support is available and no matching guns are connected, scan returns an empty list.
- If HID support is unavailable, `USBDetector` raises during initialization and the route fails.

Graceful behavior at the UI layer:

- The active Gunner panel catches scan failures and shows `Scan failed -- check USB connection`.
- If the route returns no devices, the panel shows `No light gun hardware detected`.

Mock mode details:

- `AA_USE_MOCK_GUNNER=true` enables `MockDetector` in development.
- `MockDetector` returns two simulated devices:
  - Sinden Light Gun (Mock)
  - AimTrak Light Gun (Mock)

## 5. Retro Modes

The backend exposes a retro mode registry at:

- `GET /api/local/gunner/modes`

Current enum entries in `backend/services/gunner/modes.py`:

- `time_crisis`
- `house_dead`
- `operation_wolf`
- `point_blank`
- `virtua_cop`
- `duck_hunt`
- `lethal_enforcers`
- `area51`

The `/gunner` router currently publishes descriptive mode metadata for:

- Time Crisis
- House of the Dead
- Point Blank
- Virtua Cop
- Duck Hunt

`GunnerService.calibrate_stream()` can run mode-specific validation and recommendations during streaming calibration if `game_type` matches a retro mode handler.

Important limitation:

- The active modular `RetroModesTab` is placeholder UI only.
- There is no active backend endpoint that applies display filters or fleet optimization settings from that tab.

## 6. Troubleshooting

Common failure modes visible in the current code:

- No supported HID device found:
  - The detector returns an empty list when no matching Sinden, AimTrak, or Gun4IR device is present.
- HID library missing:
  - `USBDetector` cannot initialize without `hid`, and the scan route can fail before returning devices.
- Mock confusion:
  - Backend mock devices may exist, but the active Gunner panel strips `(Mock)` from names and hides mock model labeling unless frontend mock mode is enabled.
- Active UI/backend mismatch:
  - The mounted modular Gunner panel has a real scan path, but calibration, profiles, and retro modes are mostly placeholder UI.
- Legacy profile apply misunderstanding:
  - `/api/local/gunner/profile/apply` is not a hardware sync endpoint. It only acknowledges the request.

Practical guidance from the implemented prompt and services:

- Confirm IR sensor placement before calibration.
- Treat calibration as a physical step-by-step process that requires user action.
- Use saved per-game local profiles as the current source of truth.
- If scanning fails, verify USB connection, HID support, and whether mock mode has been explicitly enabled.
