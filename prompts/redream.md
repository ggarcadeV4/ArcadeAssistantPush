## CONTROLLER_CONFIG
Redream in Arcade Assistant uses the `redream` adapter type and stores all input configuration in the global `redream.cfg` file located alongside the executable.

Registered executable name in the codebase:
- `redream.exe`

Executable path on this cabinet:
- `A:/LaunchBox/Emulators/redream.x86_64-windows-v1.5.0/redream.exe`

Input philosophy:
- Redream uses the SDL2 controller database for automatic configuration ("sane defaults").
- XInput is heavily preferred for Windows environments.
- There are no native per-game controller mapping profiles; `redream.cfg` is the single authoritative source.

Arcade Assistant controller mapping names confirmed by `emulator_registry.py` and `backend/profiles/console_wizard/redream.json`:
- D-Pad: `port0_dpad_up`, `port0_dpad_down`, `port0_dpad_left`, `port0_dpad_right`
- Face buttons: `port0_a`, `port0_b`, `port0_x`, `port0_y`
- Triggers: `port0_ltrig`, `port0_rtrig`
- Start: `port0_start`
- Menu (select equivalent): `menu`

Console Wizard profile facts:
- Emulator type: `redream`
- Display name: `Redream`
- Supported players: 4
- Standard layout: 6 buttons (A/B/X/Y/L-trigger/R-trigger), directional inputs, start, analog stick
- Input system: SDL
- Profile system: 8 profiles (profile0-7), 4 ports (input0-3)
- Profile format: `profile0: hwid:keyboard3` with `+button_name:key_or_button` syntax

Critical analog trigger warning:
- The Dreamcast has analog triggers (L and R). These MUST be mapped to analog axes in XInput, not digital buttons.
- Games like Shenmue use variable throttle on the triggers. Digital-only mapping will cause gameplay failures.

Arcade stick 6-button layout for Dreamcast:
- Top row (left to right): X, Y, L (analog trigger)
- Bottom row (left to right): A, B, R (analog trigger)

## GUN_CONFIG
Redream natively supports Light Gun emulation by mapping the Dreamcast virtual gun peripheral to mouse/pointer coordinates.

Gun configuration:
- The peripheral must be explicitly changed from "Controller" to "Light Gun" for the specific port (usually Port A) in Redream's Input menu.
- Native single-player mouse tracking works well out of the box.

Gun platform routing:
- `Dreamcast Gun Games` is a distinct platform in `emulator_paths.json` — gun games route through this label.
- There is no separate gun build directory for Redream (unlike Model 2). Both panel and gun share the same executable.

Multi-gun limitations:
- Complex two-player light gun setups often conflict with Redream's raw input handling.
- If standard mouse tracking fails for dual guns, DemulShooter may be required as an external orchestrator, but this is outside Redream's intrinsic capabilities.

## LAUNCH_PROTOCOL
Arcade Assistant runtime launch behavior comes from `backend/services/adapters/redream_adapter.py`.

Canonical direct-launch contract:
- Redream accepts the absolute path to the game image directly as a positional argument.
- Supported image formats: `.gdi` (preferred), `.chd` (highly recommended for compression), `.cdi` (legacy/homebrew).

Runtime pattern:
```text
redream.exe [flags] "C:\Path\To\Rom.chd"
```

The adapter resolves ROM paths from the game object and supports `--fullscreen`, `--aspect`, and similar flags via the launcher config.

Display routing:
- Fullscreen state is driven by `redream.cfg` (`fullscreen=1`). Do not force fullscreen via external window hooks — this bypasses Redream's internal SDL2 window management.

Renderer specification:
- Driven by `redream.cfg` (`video_api=vulkan` or `video_api=opengl`).
- Changes to the renderer backend require a complete emulator restart to apply cleanly. Do not hot-swap.

Feature gate:
- Env gate: `AA_ALLOW_DIRECT_REDREAM`
- Launcher config gate: `allow_direct_redream`

Save state hotkeys (from `backend/routers/emulator.py`):
- F5 = save state
- F8 = load state
- No pause toggle endpoint currently exists for Redream in the codebase.

## ROUTING_VOCAB
Use these identifiers when reasoning about Redream/Dreamcast inside Arcade Assistant:

Platform names:
- `Sega Dreamcast` (primary)
- `Dreamcast` (alias, normalizes to `sega dreamcast` via `platform_names.py`)
- `Sega Dreamcast Indies` (homebrew/indie titles)
- `Dreamcast Gun Games` (gun-specific routing)

Adapter and registry identifiers:
- Adapter type: `redream`
- Emulator registry type: `redream`
- Config file: `redream.cfg`
- Config format: `cfg`
- Game input router family: console system

Direct-launch feature flags:
- Env gate: `AA_ALLOW_DIRECT_REDREAM`
- Launcher config gate: `allow_direct_redream`

Overlay/activity hints:
- Redream activity is treated as overlay-safe through the `redream.exe` allowlist entry in `activity_guard.py`.

Routing boundary with Flycast:
- Redream handles `Sega Dreamcast` (console titles).
- Flycast handles `Sega Naomi` and `Sammy Atomiswave` (arcade Dreamcast hardware).
- Flycast may also serve as fallback for Dreamcast console titles if Redream is unavailable.

## SCORE_TRACKING
Save state management:
- Saved internally as `.asav` files inside the `saves/` directory alongside the executable.
- Free tier: single save state slot. Premium tier: multiple slots.
- Arcade Assistant triggers save/load via F5/F8 hotkeys through the emulator router.

VMU (Virtual Memory Unit) management:
- Redream uses four globally shared VMU files: `vmu0.bin` through `vmu3.bin` in the root directory.
- It does NOT support per-game VMUs natively. All games share the same virtual memory cards.

Memory hooking / achievements:
- Redream is closed-source and standalone. It does NOT support RetroAchievements or libretro memory-hooking score trackers.
- Do not attempt to inject external achievement DLLs — this violates the emulator's closed runtime.

## VOICE_VOCABULARY
Recognized voice trigger phrases for Dreamcast via Redream:
- "Play Dreamcast"
- "Start Dreamcast"
- "Launch Re-dream"
- "Play [Game Title] on Dreamcast" (e.g., "Play Crazy Taxi on Dreamcast")
- "Open Red-ream emulator"
- "Boot Sega Dream cast"

Acoustic/phonetic variations to handle:
- "Dream cast" (two words)
- "Sega Dream cast"
- "Red ream"
- "Ree-dream"

## LED_PROFILE
Dreamcast face button LED colors:
- A Button: Red
- B Button: Blue
- X Button: Yellow
- Y Button: Green

Ambient / system color:
- Orange (NTSC-U/NTSC-J swirl region) or Blue (PAL swirl region).
- White is a safe fallback representing the console shell.

## HEALTH_CHECK
Process name: `redream.exe`
Log location: `redream.log` (generated in the same working directory as the executable).

Common crash and fault patterns:

- Thin vs. Thick driver clashes:
  - Visual artifacts (missing geometry, phantom lines) are almost always Vulkan ("thin driver") shader compiler issues.
  - Fix: Change `video_api` in `redream.cfg` from `vulkan` to `opengl` ("thick driver"). Sacrifices a few frames for maximum stability.
  - Requires a full emulator restart after the change.

- Corrupt media:
  - Bad `.cdi` rips (missing audio tracks, bad sectors) cause hard crashes on load.
  - Recommend `.chd` or Redump-verified `.gdi` files.

- Config corruption:
  - If `redream.cfg` becomes malformed due to abrupt power loss during a write cycle, the emulator may fail to launch.
  - Deleting `redream.cfg` forces the emulator to safely regenerate sane defaults on next boot.
