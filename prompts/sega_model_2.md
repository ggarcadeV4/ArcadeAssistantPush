## CONTROLLER_CONFIG
Sega Model 2 in Arcade Assistant uses the `model2` adapter type and stores controller bindings in `EMULATOR.INI`.

Registered executable names in the codebase are:
- `EMULATOR.EXE`
- `emulator_multicpu.exe`

Current pathing nuance:
- `config/launchers.json` still points the direct launcher entry at `A:/Emulators/Sega Model 2/EMULATOR.EXE`.
- `configs/emulator_paths.json` and `backend/constants/a_drive_paths.py` prefer `A:/Emulators/Sega Model 2/emulator_multicpu.exe`.
- Treat `emulator_multicpu.exe` as the preferred modern runtime for cabinet guidance unless a legacy setup explicitly depends on `EMULATOR.EXE`.

Arcade Assistant controller mapping names confirmed by `emulator_registry.py` and `backend/profiles/console_wizard/model2.json`:
- Movement: `JoyUp`, `JoyDown`, `JoyLeft`, `JoyRight`
- Actions: `JoyButton1`, `JoyButton2`, `JoyButton3`, `JoyButton4`
- Service inputs for cabinet play: `JoyStart`, `JoyCoin`

Console Wizard profile facts:
- Emulator type: `model2`
- Display name: `Sega Model 2`
- Supported players: 2
- Standard layout: 4 buttons plus directional inputs, start, and coin for each player

Operational warning:
- A known Model 2 stability edge case is a crash or bad input state when more than 3 controller-class devices are enumerated at once.
- XInput double-enumeration is a common trigger. If controller discovery becomes unstable, reduce connected devices first and prefer DirectInput-oriented Model 2 tuning.

## GUN_CONFIG
Arcade Assistant has a separate Model 2 gun installation. Do not mix panel guidance with gun guidance.

Gun build path:
- `A:/Gun Build/Emulators/Sega Model 2/emulator_multicpu.exe`

Panel build path:
- `A:/Emulators/Sega Model 2/emulator_multicpu.exe`

Platform split:
- `Sega Model 2` = standard panel-oriented Model 2 routing
- `Model 2 Gun Games` = gun-specific routing

Gun stack notes validated for this cabinet:
- DemulShooter is the expected companion layer for Model 2 gun workflows.
- Set `UseRawInput=0` when the validated gun workflow requires the classic input path.
- Set `DrawCross=0` when the cabinet is using external gun alignment and does not want emulator-drawn crosshairs.
- Sinden workflows are expected to preserve a 4:3 presentation path where the cabinet profile depends on that geometry.
- Gun calibration data lives in the Model 2 `NVDATA` area; corrupted or stale calibration can often be fixed by restoring or regenerating the affected gun data there.
- If a white-flash Lua helper was previously injected into the setup, remove or disable it when it conflicts with the known-good cabinet gun profile.

## LAUNCH_PROTOCOL
Arcade Assistant runtime launch behavior comes from `backend/services/adapters/model2_adapter.py`.

Canonical direct-launch contract:
- ROM source is expected to resolve to a `.zip` file.
- The CLI argument passed to the emulator is the ROM stem, not the `.zip` filename.
- Arcade Assistant currently launches with `-rom=<stem>`.

Runtime pattern:
```text
emulator_multicpu.exe -rom=<rom_stem>
```

Do not document bare positional ROM launch as the Arcade Assistant contract unless the runtime adapter changes. Current code truth is `-rom=<stem>`.

Executable preference:
- `emulator_multicpu.exe` is the preferred runtime when both executables are present.
- `EMULATOR.EXE` remains relevant because older launcher config still points at it.

Exit guidance:
- Clean operator exit path is `Esc` followed by the emulator's own exit flow.
- Dirty termination can leave Model 2 state dirty; when the next boot shows bad calibration or stuck state, inspect and recover the relevant `NVDATA` files before assuming ROM or input corruption.

## ROUTING_VOCAB
Use these identifiers when reasoning about Sega Model 2 inside Arcade Assistant:

Platform names:
- `Sega Model 2`
- `Model 2 Gun Games`

Adapter and registry identifiers:
- Adapter type: `model2`
- Emulator registry type: `model2`
- Game input router family: arcade encoder system

Direct-launch feature flags:
- Env gate: `AA_ENABLE_ADAPTER_MODEL2`
- Launcher config gate: `allow_direct_model2`

Path selectors:
- Panel accessor: `EmulatorPaths.model2()`
- Gun accessor: `EmulatorPaths.model2_gun()`

Overlay/activity hints:
- Model 2 activity is treated as overlay-safe through the `model2.exe` allowlist entry in `activity_guard.py`.

## TROUBLESHOOTING
Known cabinet fixes and failure patterns for Sega Model 2:

- `ForceManaged=1`
  - Use when the validated cabinet profile needs managed rendering to stabilize presentation or startup on modern systems.

- `XInput=0`
  - Use when XInput causes duplicate devices, phantom inputs, or contributes to the more-than-3-device crash pattern.

- More than 3 input devices
  - Model 2 can become unstable when too many controller-class devices are present.
  - Reduce active devices first before rewriting mappings.

- Bottom-right or corner-biased gun calibration
  - Treat this as a calibration/NVDATA integrity issue first.
  - Recover the relevant gun calibration data before changing the broader routing stack.

- Dirty exit recovery
  - If the emulator was force-closed, inspect `NVDATA` and related state before assuming a broken ROM or adapter.

- Service access
  - `F2` enters the service menu on validated setups.
  - Use `F1` and standard menu navigation to move through diagnostic/service pages when the specific title expects that flow.

## DIP_SWITCHES
Model 2 operator settings are per-game and should be managed through the Service Menu, not by treating a shared data file as a universal DIP profile.

Cabinet guidance:
- Use Service Menu navigation for validated setting changes.
- Prefer `F2` to open service mode, then follow the game's own menu flow.
- Use `F1` and the title's expected directional or confirm inputs where that service flow requires it.

Data integrity warning:
- Do not casually edit or overwrite Model 2 `.dat` or adjacent state files as a shortcut for DIP changes.
- Corrupting per-game data can wipe good operator settings or break calibration state, especially on gun titles.
