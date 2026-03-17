# A:\ Drive — Folder Structure & Emulator Mental Model

**Date:** 2026-03-16 | **Purpose:** Reference for Claude, Codex, and Anti-Gravity

---

## CRITICAL CONTEXT

There are **THREE completely separate emulator ecosystems** on this drive. This is the most important thing to understand before touching any LaunchBox configuration.

| Ecosystem | Location | Origin |
|-----------|----------|--------|
| **1 — Pre-existing** | `A:\LaunchBox\Emulators\` | Came with the purchased drive |
| **2 — Gregory's Custom** | `A:\Emulators\` | Added for mass production build |
| **3 — Gun Build** | `A:\Gun Build\` | Dedicated light gun game environment |

---

## A:\ ROOT STRUCTURE

```
A:\
├── .aa\                        — Arcade Assistant runtime state
├── _INSTALL\                   — Installation files
├── Arcade Assistant\           — Previous AA version
├── Arcade Assistant Local\     — ACTIVE codebase (master branch, golden build)
├── Arcade Assistant OLD\       — Legacy backup
├── ArcadeAssistant\            — Another legacy version
├── backups\                    — Backup files
├── Bios\                       — BIOS files for emulators
├── config\                     — Config files
├── configs\                    — Additional configs
├── Console ROMs\               — Console ROM storage
├── Dev\                        — Development files
├── docs\                       — Documentation
├── Emulators\                  — GREGORY'S CUSTOM EMULATORS (see below)
├── Gun Build\                  — DEDICATED GUN GAME BUILD (see below)
├── handoff\                    — Session handoff files
├── LaunchBox\                  — LAUNCHBOX INSTALLATION (see below)
├── LEDBlinky\                  — LEDBlinky installation
├── logs\                       — System logs
├── nonexistent\                — Fallback directory (should not exist on golden)
├── Playnite\                   — Playnite frontend
├── preflight\                  — Preflight check scripts
├── RocketBlinky\               — RocketBlinky installation
├── Roms\                       — ROM storage
├── state\                      — State files
├── ThirdScreen-v5.0.12\        — Third screen software
├── tmp\                        — Temporary files
├── Tools\                      — Utility tools
├── LEDBlinky.atoplug           — LEDBlinky plugin
├── LEDBlinky.mplugin           — LEDBlinky plugin
```

---

## ECOSYSTEM 1 — Pre-existing Emulators

**Path:** `A:\LaunchBox\Emulators\`

These came with the drive purchase. Configured for standard controller gameplay.

```
A:\LaunchBox\Emulators\
├── bios\
├── cemu_1.26.2\                — Wii U emulator
├── dolphin-2412-x64\           — GameCube/Wii (version 2412)
├── dolphin-emu\                — GameCube/Wii (alternate)
├── hlsl\                       — HLSL shaders
├── PCSX2\                      — PlayStation 2 emulator
├── PPSSPPGold\                 — PSP emulator (Gold version)
├── redream.x86_64-windows-v1.5.0\ — Dreamcast emulator
├── RetroArch\                  — RetroArch (standard, controller-focused)
├── rpcs3\                      — PlayStation 3 emulator
├── yuzu\                       — Nintendo Switch emulator
```

**Key executables:**
- `A:\LaunchBox\Emulators\RetroArch\retroarch.exe` — Standard RetroArch
- `A:\LaunchBox\Emulators\PCSX2\pcsx2.exe` — PlayStation 2
- `A:\LaunchBox\Emulators\PPSSPPGold\PPSSPPWindows64.exe` — PSP
- `A:\LaunchBox\Emulators\rpcs3\rpcs3.exe` — PlayStation 3
- `A:\LaunchBox\Emulators\cemu_1.26.2\cemu.exe` — Wii U
- `A:\LaunchBox\Emulators\dolphin-2412-x64\Dolphin.exe` — GameCube/Wii
- `A:\LaunchBox\Emulators\redream.x86_64-windows-v1.5.0\redream.exe` — Dreamcast

---

## ECOSYSTEM 2 — Gregory's Custom Emulators

**Path:** `A:\Emulators\`

Added intentionally for the mass production cabinet build. These are the emulators Gregory specifically chose for this system.

```
A:\Emulators\
├── Dolphin Tri-Force\          — Tri-Force arcade board emulator (Mario Kart, F-Zero GX, etc.)
├── Hypseus\                    — Modern Daphne replacement (laser disc games)
├── MAME\                       — MAME (arcade, standard controls)
├── MAME Gamepad\               — MAME configured for gamepad input
├── RetroArch\                  — RetroArch (Gregory's custom build)
├── RetroArch Gamepad\          — RetroArch configured for gamepad input
├── Sega Model 2\               — Sega Model 2 emulator
├── Super Model\                — Supermodel (Sega Model 3 emulator)
├── TeknoParrot\                — TeknoParrot (arcade PC games)
├── TeknoParrot Gamepad\        — TeknoParrot configured for gamepad
├── TeknoParrot Latest\         — Latest TeknoParrot version
```

**Key executables (paths to verify):**
- `A:\Emulators\MAME\mame64.exe` — Standard MAME
- `A:\Emulators\Hypseus\hypseus.exe` — Daphne replacement
- `A:\Emulators\Sega Model 2\emulator_multicpu.exe` — Model 2
- `A:\Emulators\Super Model\Supermodel.exe` — Model 3
- `A:\Emulators\TeknoParrot\TeknoParrotUi.exe` — TeknoParrot
- `A:\Emulators\RetroArch\retroarch.exe` — Gregory's RetroArch

---

## ECOSYSTEM 3 — Gun Build

**Path:** `A:\Gun Build\`

Dedicated standalone environment for light gun games. This is **completely separate** from both other emulator ecosystems. It has its own RetroArch instance specifically configured for light gun input.

> [!IMPORTANT]
> This is the correct emulator path for **ALL** light gun game platforms.

```
A:\Gun Build\
├── Emulators\
│   └── RetroArch\
│       └── retroarch.exe      — Gun-specific RetroArch build
```

**Critical rule:** Any platform tagged as a "Gun Games" variant in LaunchBox should be pointing to `A:\Gun Build\Emulators\RetroArch\retroarch.exe` — **NOT** to any RetroArch in the other two ecosystems.

---

## LAUNCHBOX STRUCTURE

**Path:** `A:\LaunchBox\`

```
A:\LaunchBox\
├── Backups\                    — LaunchBox backup files
├── Core\                       — LaunchBox core files
├── cores\                      — RetroArch cores
├── Data\                       — PLATFORM AND EMULATOR CONFIGS LIVE HERE
│   ├── Platforms\              — One XML file per platform
│   └── Emulators.xml           — All emulator definitions (single file)
├── Emulators\                  — Pre-existing emulators (Ecosystem 1)
├── Games\                      — Game metadata
├── Images\                     — Box art, screenshots, etc.
├── LBThemes\                   — LaunchBox themes
├── Logs\                       — LaunchBox logs
├── Manuals\                    — Game manuals
├── Metadata\                   — LaunchBox metadata
│   └── Temp\                   — Temp directory (must exist)
├── Music\                      — Game music
├── PauseThemes\                — Pause screen themes
├── Plugins\                    — LaunchBox plugins
├── Saves\                      — Save states
├── Sounds\                     — Sound files
├── StartupThemes\              — Startup themes
├── temp\                       — Temp files
├── Themes\                     — UI themes
├── ThirdParty\                 — Third party components
├── Updates\                    — Update files
├── Videos\                     — Game videos
├── BigBox.exe                  — BigBox frontend
└── LaunchBox.exe               — LaunchBox application
```

---

## EMULATOR ROUTING RULES

When Codex is fixing a LaunchBox platform configuration, use this lookup table to determine the correct emulator path:

| Platform Type | Correct Emulator Location |
|---------------|---------------------------|
| MAME (standard) | `A:\Emulators\MAME\` |
| MAME (gamepad) | `A:\Emulators\MAME Gamepad\` |
| **ANY Gun Game variant** | **`A:\Gun Build\Emulators\RetroArch\`** |
| RetroArch (standard arcade) | `A:\Emulators\RetroArch\` |
| RetroArch (gamepad/console) | `A:\LaunchBox\Emulators\RetroArch\` |
| Daphne / laser disc | `A:\Emulators\Hypseus\` |
| Sega Model 2 | `A:\Emulators\Sega Model 2\` |
| Sega Model 3 | `A:\Emulators\Super Model\` |
| TeknoParrot | `A:\Emulators\TeknoParrot\` or `TeknoParrot Latest\` |
| TeknoParrot (gamepad) | `A:\Emulators\TeknoParrot Gamepad\` |
| PlayStation 2 | `A:\LaunchBox\Emulators\PCSX2\` |
| PlayStation 3 | `A:\LaunchBox\Emulators\rpcs3\` |
| PSP | `A:\LaunchBox\Emulators\PPSSPPGold\` |
| Dreamcast | `A:\LaunchBox\Emulators\redream.x86_64-windows-v1.5.0\` |
| GameCube / Wii | `A:\LaunchBox\Emulators\dolphin-2412-x64\` |
| Wii U | `A:\LaunchBox\Emulators\cemu_1.26.2\` |
| Dolphin Tri-Force | `A:\Emulators\Dolphin Tri-Force\` |

---

## THE A-01 CORRECTION NEEDED

> [!CAUTION]
> Based on this mental model, the Master System Gun Games fix that Codex applied in A-01 was **incorrect**. Codex pointed Master System Gun Games at `A:\LaunchBox\Emulators\RetroArch\retroarch.exe` (standard controller RetroArch). The correct path should be `A:\Gun Build\Emulators\RetroArch\retroarch.exe` (dedicated gun RetroArch).
>
> **A-01 needs to be re-run with the correct emulator path before Anti-Gravity verifies.**

---

## KEY RULES FOR CODEX

1. **Gun Games always use Gun Build** — Any platform with "Gun Games" in its name routes to `A:\Gun Build\Emulators\RetroArch\`
2. **Check `Emulators.xml` for GUIDs** — Platform XML files reference emulator GUIDs, not paths directly. The path lives in `A:\LaunchBox\Data\Emulators.xml`
3. **Verify executable exists** — Before writing any fix, confirm the target `.exe` actually exists at the specified path
4. **Never assume path structure** — Always read the actual file before writing a fix
5. **Platforms folder** — `A:\LaunchBox\Data\Platforms\` contains one XML per platform
6. **`Metadata\Temp` must exist** — `A:\LaunchBox\Metadata\Temp\` directory must be present or Flash Games will crash LaunchBox

---

> [!NOTE]
> This document reflects the actual A:\ drive structure as of **2026-03-16**.
> Update if emulator locations change or new emulators are added.
