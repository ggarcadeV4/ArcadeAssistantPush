# Codex Task: Wii U Games Won't Launch from LoRa Panel

## Problem
Wii U games launch correctly from **native LaunchBox** but fail from the **LoRa panel**. When launched from LoRa, Cemu opens to its blank game list (no game loaded, no fullscreen). The ROM path and `-f -g` flags are not reaching Cemu.

## What We Already Fixed (Still Not Working)
We added emulator-level `CommandLine` support:
- `backend/models/emulator_config.py` — added `command_line` field to `EmulatorDefinition`
- `backend/services/emulator_detector.py` — parser reads `CommandLine` from XML
- `backend/services/launcher.py` line ~720 — `_build_emulator_command()` now falls back to emulator-level flags when `mapping.command_line` is empty

**This fix was verified to compile but the game still doesn't launch properly.** This suggests the game is NOT reaching `_build_emulator_command()` at all.

## Root Cause Hypothesis
The launch chain priority is (see `launcher.py` line 148-158):
1. `plugin` → `_launch_via_plugin()` (C# plugin bridge, port 9999)
2. `detected_emulator` → `_launch_via_detected_emulator()`
3. `direct` → `_launch_direct()` (only if enabled)
4. `launchbox` → `_launch_via_launchbox()`

**The game is likely launching via the plugin bridge**, which calls `plugin_client.launch_game(game.id)`. If the plugin handles the launch, our `_build_emulator_command()` fix is never reached. The plugin may be starting Cemu without the proper arguments.

**Alternatively**, if the plugin is offline, `_launch_via_detected_emulator()` is called, which at line 686-688 calls `_build_emulator_command()` then `_execute_emulator()`. The fix should work in that path. Add logging to determine which path is actually taken.

## Key Files
| File | What It Does |
|------|-------------|
| `backend/services/launcher.py` | Main launch chain, `_build_emulator_command()` at ~line 716 |
| `backend/services/emulator_detector.py` | Parses `Emulators.xml`, builds `EmulatorDefinition` objects |
| `backend/models/emulator_config.py` | `EmulatorDefinition` and `PlatformEmulatorMapping` models |

## LaunchBox XML Data
**Emulators.xml** has two Cemu entries:
- `Cemu` at `..\\Emulators\\Cemu\\Cemu.exe` (ID: `3be9f6a8-...`) — CommandLine: `-f -g`
- `Cemu-Controller` at `Emulators\\cemu_1.26.2\\Cemu.exe` (ID: `725377cc-...`) — CommandLine: `-f -g`

**EmulatorPlatform** mappings for `Nintendo Wii U`:
- Non-default → emulator `3be9f6a8` (Cemu), CommandLine: empty
- **Default** → emulator `725377cc` (Cemu-Controller), CommandLine: empty

ROM paths use `.rpx` format: `..\\Console ROMs\\Ninendo WiiU\\<game>\\code\\<file>.rpx`

## Debugging Steps
1. Add `logger.info(f"WiiU launch path: method={method_name}")` in `_try_launch_method()` (line ~516)
2. If plugin path: check `plugin_client.launch_game()` response for Wii U games
3. If detected_emulator path: add logging in `_build_emulator_command()` to print the final command
4. Verify the cached `configs/emulator_paths.json` was regenerated with `command_line` field (it was deleted, should auto-regenerate)
5. Check if the `.rpx` ROM path resolves correctly through `_get_rom_path()` → `Path` resolution

## Expected Correct Command
```
A:/LaunchBox/Emulators/cemu_1.26.2/Cemu.exe -f -g "A:/Console ROMs/Ninendo WiiU/Nintendo Land (USA)/code/Lunch.rpx"
```

## Acceptance Criteria
- [ ] Wii U games launch fullscreen with the correct game loaded from the LoRa panel
- [ ] Add launch-path logging so we can debug similar issues in the future
