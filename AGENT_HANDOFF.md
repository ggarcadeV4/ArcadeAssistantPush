# 🤝 Agent Handoff Log

> **Purpose**: Running communication log between the **Dev Machine AI** (upstairs) and the **Basement AI** (arcade cabinet). Updated on every `git push` and `git pull` to keep both agents synchronized.
>
> **Protocol**: Before doing ANY work, read this entire file. After completing work, append a new entry. Never delete entries — this is append-only.

---

## Current System State

### Playnite Extension: `scripts/playnite/extension/`
| File | Purpose | Last Updated |
|------|---------|-------------|
| `script.psm1` | Core extension — emulators, game wiring, LED tags, Dewey F9 HUD | 2026-02-16 |
| `extension.yaml` | Playnite extension manifest | 2026-02-16 |
| `dewey-overlay.html` | Dewey AI chat overlay UI (F9 triggered) | 2026-02-16 |

### Emulators Configured (8 total)
| Emulator | Install Dir | Input Type | Platforms |
|----------|------------|------------|-----------|
| RetroArch | `A:\Emulators\RetroArch` | Gamepad | NES, SNES, Genesis, GBA, N64, PS1, Saturn, PSP, NDS |
| MAME | `A:\Emulators\MAME` | Lightgun | Arcade |
| MAME Gamepad | `A:\Emulators\MAME Gamepad` | Control Panel | Arcade |
| Dolphin Tri-Force | `A:\Emulators\Dolphin Tri-Force` | Gamepad | Nintendo GameCube |
| Sega Model 2 | `A:\Emulators\Sega Model 2` | Lightgun | Sega Model 2 |
| Super Model | `A:\Emulators\Super Model` | Lightgun | Sega Model 3 |
| TeknoParrot | `A:\Emulators\TeknoParrot` | Lightgun | Modern Arcade |
| TeknoParrot Gamepad | `A:\Emulators\TeknoParrot Gamepad` | Gamepad | Modern Arcade |

### A: Drive Prerequisites (NOT in Git)
These must exist on the local A: drive for the extension to work:
- [ ] `A:\Emulators\RetroArch\retroarch.exe` + cores
- [ ] `A:\Emulators\MAME\mame.exe`
- [ ] `A:\Emulators\MAME\catver.ini` (for Cinema Logic LED tags)
- [ ] `A:\Emulators\MAME Gamepad\mame.exe`
- [ ] `A:\Emulators\Dolphin Tri-Force\Dolphin.exe`
- [ ] `A:\Emulators\Sega Model 2\EMULATOR.EXE`
- [ ] `A:\Emulators\Super Model\Supermodel.bak.exe`
- [ ] `A:\Emulators\TeknoParrot\TeknoParrotUi.exe`
- [ ] `A:\Emulators\TeknoParrot Gamepad\TeknoParrotUi.exe`
- [ ] `A:\Playnite\Playnite.DesktopApp.exe`
- [ ] ROMs/BIOS in platform-appropriate directories

### Deployment Steps (after `git pull`)
1. Copy extension files to Playnite:
   ```powershell
   Copy-Item "scripts\playnite\extension\*" "A:\Playnite\Extensions\ArcadeAssistant\" -Force
   ```
2. Restart Playnite — extension auto-runs on startup
3. Verify via `A:\Playnite\arcade_debug.log`

---

## Handoff Entries

### [2026-02-16 21:00] DEV-AI → BASEMENT-AI

**What was done:**
- Built complete Playnite extension with 4-step startup pipeline:
  1. `Setup-ArcadeEmulators` — 8 emulators with per-name idempotency
  2. `Wire-GameActions` — auto-links games to emulator profiles
  3. `Apply-CinemaLogicTags` — parses `catver.ini`, applies 10 LED tag categories to MAME games
  4. `Start-DeweyHotkey` — F9 global hotkey toggles AI chat overlay
- Cinema Logic tags: 284 MAME games tagged across 10 LED categories
- Dewey F9 HUD: self-contained background watcher (Win32 RegisterHotKey), borderless Edge browser overlay
- `OnApplicationStopped` cleanup for F9 watcher process

**Known issues:**
- Dewey overlay shows "Backend offline" unless Python backend is running at `localhost:8000`
- 171 games on specialty platforms (Pinball FX, Daphne, Singe, Hikaru) still unmatched — need emulator configs when hardware is available
- MAME games (21,096) have short codenames — need `mame.xml` DAT file for clean display names

**What BASEMENT-AI should do on first pull:**
1. Run deployment step above (copy extension files)
2. Verify A: drive prerequisites checklist
3. Restart Playnite, check `arcade_debug.log` for: `=== EMULATOR SETUP COMPLETE ===`
4. Press F9 to test Dewey overlay
5. Report back any missing emulator directories or platform mismatches

**Open items for either agent:**
- [ ] Deploy script (`deploy.ps1`) for one-click setup
- [ ] Play Now button (random game launcher)
- [ ] SNES tag update to `[LED:RETRO]`
- [ ] MAME clean name resolution via `mame.xml`

---
