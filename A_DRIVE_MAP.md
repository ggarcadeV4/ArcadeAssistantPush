# A: Drive Map – Arcade Cabinet Content Reference

**Generated:** 2025-10-05 14:30:00 UTC
**Purpose:** Comprehensive directory structure and file inventory for arcade cabinet A: drive
**Target Audience:** AI assistants (Claude, ChatGPT, Codex), developers, system administrators

---

## Executive Summary

The A: drive (`A:\` or `/mnt/a/` in WSL) contains the complete arcade cabinet software stack including:
- **14,233 MAME ROM files** (.zip archives)
- **586 system BIOS files** (various formats)
- **53 platform XML databases** (LaunchBox metadata)
- **11 emulator installations** (MAME, RetroArch, Dolphin, PCSX2, TeknoParrot, etc.)
- **3.7 GB installation packages** (dependencies, codecs, runtimes)
- **Light gun game collection** (15+ gun-specific platforms)

**Critical Paths:**
- LaunchBox Executable: `A:\LaunchBox\LaunchBox.exe`
- BigBox Executable: `A:\LaunchBox\BigBox.exe`
- Platform XML Data: `A:\LaunchBox\Data\Platforms\*.xml`
- MAME Roms: `A:\Roms\MAME\*.zip`
- BIOS Files: `A:\Bios\system\*`

**⚠️ NOTE:** CLI_Launcher.exe was not found in expected ThirdParty directory. May require manual location or installation.

---

## Directory Structure Overview

```
A:\
├── _INSTALL\              # Installation packages and dependencies (3.7 GB)
├── Bios\                  # System BIOS files for emulators (586 files)
├── Console ROMs\          # Console game ROMs organized by platform (26 platforms)
├── Emulators\             # Emulator executables and configs (11 emulators)
├── Gun Build\             # Light gun-specific emulators and ROMs
├── LaunchBox\             # Frontend for game library management
├── Roms\                  # Arcade ROM files organized by system (14 systems)
├── ThirdScreen-v5.0.12\   # Third screen/marquee display plugin
└── Tools\                 # Utilities (controller mappers, scripts, ReShade)
```

---

## 1. A:\_INSTALL\ – Installation Packages (3.7 GB)

**Purpose:** Archived installation files for system dependencies, codecs, and runtimes required for emulators and games.

### Subdirectories

```
_INSTALL\
├── 1 - Launchbox Dependencies\       # Core LaunchBox setup files
│   ├── .Net.Core-SDK-8.0.204-win-x64.exe
│   ├── .Net.Framework.48-x86-x64-allos-enu.exe
│   ├── LaunchBox-13.14-Setup.exe
│   ├── vc_redist.x64.exe             # Visual C++ Redistributable 64-bit
│   └── vc_redist.x86.exe             # Visual C++ Redistributable 32-bit
├── 2 - AutoHotKey\                   # Scripting engine for key remapping
│   └── AutoHotkey_1.1.37.01_setup.exe
├── 3 - RivaTuner\                    # OSD/framerate limiter
│   ├── RivaTunerSetup733.exe
│   └── RTSS_Sinden_overlays_0.01.zip # Sinden light gun overlays
├── 4 - PhysX System Software\        # NVIDIA PhysX for physics simulation
│   └── PhysX_9.21.0713_SystemSoftware.exe
├── 5 - TTX Codecs\                   # Taito Type X video codecs
│   ├── Intel_Indeo\                  # Intel Indeo codec
│   ├── VP6\                          # VP6 video codec
│   └── WMV9\                         # Windows Media Video 9
├── 6 - DirectX\                      # DirectX End-User Runtimes (June 2010)
│   └── DirectX End-User Runtimes (June 2010)\ # 100+ .cab files
└── 10 - Lossless Scaling Config\     # Lossless Scaling settings
    ├── ReadMe.txt
    └── Settings.xml
```

### Key Files

- **LaunchBox-13.14-Setup.exe** – LaunchBox v13.14 installer
- **.Net.Core-SDK-8.0.204-win-x64.exe** – .NET Core SDK 8.0.204
- **.Net.Framework.48** – .NET Framework 4.8 (required for many emulators)
- **vc_redist.x64/x86.exe** – Visual C++ 2015-2022 Redistributable (both architectures)
- **PhysX_9.21.0713** – NVIDIA PhysX 9.21 (required for some Taito Type X games)

### Video Tutorials

- **1 - Video - Gun Drive Setup.mp4** – Light gun setup walkthrough
- **2 - Video - Mapping Gun Games in TeknoParrot.mp4** – TeknoParrot gun game configuration

---

## 2. A:\Bios\ – System BIOS Files (586 files)

**Purpose:** Required BIOS/firmware files for emulators to function correctly.

### Structure

```
Bios\
├── 351ELEC-20211122-BIOS\            # RetroArch BIOS collection
├── system\                           # Main BIOS directory (586 files)
└── libretro_31-01-22.zip             # LibRetro BIOS pack (82.5 MB)
```

### File Types

- **586 total BIOS files** in `system/` directory
- Formats: `.bin`, `.rom`, `.dat`, various console-specific extensions
- Examples:
  - PlayStation BIOS (scph*.bin)
  - Sega Dreamcast boot ROMs
  - Arcade system BIOS (neogeo.zip, etc.)

### Critical BIOS Sets

Based on platform support, expected BIOS includes:
- **PlayStation 1/2**: SCPH-10000.bin, ps2_bios.bin
- **Dreamcast**: dc_boot.bin, dc_flash.bin
- **Neo Geo**: neogeo.zip (MVS/AES BIOS)
- **Atari**: Various Atari console/computer BIOS
- **Sega Saturn**: saturn_bios.bin

**⚠️ Note:** BIOS files are copyright-protected and must be legally obtained from owned hardware.

---

## 3. A:\Console ROMs\ – Console Game Library

**Purpose:** ROM files for console emulation organized by platform.

### Supported Platforms (26 total)

```
Console ROMs\
├── Atari 2600\
├── Atari 7800\
├── Atari Jaguar\
├── Atari Lynx\
├── NEC Turbografx-16\
├── Ninendo WiiU\                     # Typo: "Ninendo" (should be Nintendo)
├── Nintendo 64\
├── Nintendo Entertainment System\
├── Nintendo Game Boy\
├── Nintendo Game Boy Advance\
├── Nintendo Games Cube\
├── PopCap\                           # PopCap casual games
├── Sega 32X\
├── Sega Dreamcast\
├── Sega Game Gear\
├── Sega Genesis\
├── Sony PlayStation Minis\
├── megadrive\                        # Alternate Sega Genesis folder
├── nds\                              # Nintendo DS
├── playstation\                      # Sony PlayStation 1
├── playstation 2\
├── playstation 3\
├── psp\                              # Sony PlayStation Portable
└── snes\                             # Super Nintendo
```

### Platform Notes

- **Duplicate folders:** `Sega Genesis` and `megadrive` (same platform)
- **Size:** Timed out during measurement (very large, likely 100+ GB)
- **Typo:** `Ninendo WiiU` folder name has misspelling
- **Organization:** Mixed naming conventions (full names vs abbreviations)

---

## 4. A:\Emulators\ – Emulator Software (11 emulators)

**Purpose:** Executable emulators and their configuration files for running games.

### Installed Emulators

```
Emulators\
├── Dolphin Tri-Force\               # GameCube/Wii/Triforce arcade emulator
│   ├── Languages\
│   ├── QtPlugins\
│   ├── reshade-shaders\
│   ├── Roms\
│   ├── Sys\
│   └── User\
├── MAME\                            # Arcade emulator (primary)
│   ├── artwork\
│   ├── bgfx\
│   ├── cfg\
│   ├── ctrlr\
│   ├── hash\
│   ├── ini\
│   ├── nvram\
│   ├── plugins\
│   └── roms\
├── MAME Gamepad\                    # MAME with gamepad-specific configs
│   ├── [same structure as MAME]
│   └── hiscore\                     # High score tracking
├── PCSX2\                           # PlayStation 2 emulator
│   ├── bios\
│   ├── cache\
│   ├── cheats\
│   ├── covers\
│   ├── gamesettings\
│   ├── inis\
│   ├── inputprofiles\
│   ├── logs\
│   └── memcards\
├── RetroArch\                       # Multi-system emulator (libretro cores)
├── RetroArch Gamepad\               # RetroArch gamepad-specific build
├── Sega Model 2\                    # Sega Model 2 arcade board emulator
├── Super Model\                     # Sega Model 3 arcade board emulator
├── TeknoParrot\                     # Modern arcade game emulator
├── TeknoParrot Gamepad\
└── TeknoParrot Latest\
```

### Emulator Purposes

| Emulator | Systems Emulated | Key Use Case |
|----------|------------------|--------------|
| **MAME** | Arcade (1970s-2000s) | Classic arcade games (Pac-Man, Street Fighter, etc.) |
| **MAME Gamepad** | Arcade | MAME with gamepad controls instead of joystick |
| **Dolphin Tri-Force** | GameCube, Wii, Triforce | Nintendo consoles + Triforce arcade (F-Zero AX) |
| **PCSX2** | PlayStation 2 | PS2 games |
| **RetroArch** | Multi-platform | Unified frontend for many consoles (NES, SNES, Genesis, etc.) |
| **Sega Model 2** | Sega Model 2 arcade | Virtua Fighter 2, Daytona USA |
| **Super Model** | Sega Model 3 arcade | Virtua Fighter 3, Sega Rally 2 |
| **TeknoParrot** | Modern arcade | Post-2000s arcade games (Initial D, Sega Rally 3) |

### Configuration Notes

- **MAME** has two installations: standard (joystick) and gamepad-optimized
- **TeknoParrot** has three versions: main, gamepad, and "Latest" (likely beta/dev)
- **PCSX2** includes memory card saves in `memcards/` directory
- **Dolphin** includes ReShade shaders for graphical enhancement

**⚠️ Size:** Emulators folder timed out during measurement (likely 50+ GB due to TeknoParrot game files)

---

## 5. A:\Gun Build\ – Light Gun Emulator Setup

**Purpose:** Dedicated light gun game emulators and ROMs (Sinden/Gun4IR compatible).

### Structure

```
Gun Build\
├── Emulators\                       # Light gun-optimized emulators
├── Roms\                            # Light gun-specific ROM files
└── Tools\                           # Gun calibration and testing tools
```

### Light Gun Systems

Based on LaunchBox platform XMLs, the following gun game platforms are supported:
- American Laser Games
- Atomiswave Gun Games
- Daphne (LaserDisc games)
- Dreamcast Gun Games
- Flash Gun Games
- Genesis Gun Games
- MAME Gun Games
- Master System Gun Games
- Model 2 Gun Games
- Model 3 Gun Games
- NES Gun Games
- Naomi Gun Games
- PC Gun Games
- PS2 Gun Games
- PS3 Gun Games
- PSX Gun Games
- SNES Gun Games
- Saturn Gun Games
- TeknoParrot Gun Games
- Wii Gun Games

**Total Gun Platforms:** 20+ dedicated light gun game categories

---

## 6. A:\LaunchBox\ – Game Library Frontend

**Purpose:** Unified game library manager and launcher for all platforms.

### Critical Files

```
LaunchBox\
├── LaunchBox.exe                    # Main frontend executable
├── BigBox.exe                       # Full-screen mode executable
├── License.xml                      # License file
├── License (7).xml                  # Additional license file
└── Data\
    ├── LaunchBox.xml                # ⚠️ NOT FOUND (expected master database)
    ├── Platforms\                   # Platform metadata (53 XML files)
    │   ├── American Laser Games.xml
    │   ├── Arcade MAME.xml          # 12.9 MB (largest platform file)
    │   ├── Atari 2600.xml           # 3.5 MB
    │   ├── [50 more platform XMLs]
    │   └── Wii Gun Games.xml
    └── Playlists\                   # Custom game collections
```

### Platform XML Files (53 total, 51.7 MB)

**Largest Platforms:**
- **Arcade MAME.xml** – 12.9 MB (largest game collection)
- **Nintendo Game Boy Advance.xml** – 5.3 MB
- **Nintendo Entertainment System.xml** – 4.6 MB
- **Nintendo Game Boy.xml** – 4.2 MB
- **Super Nintendo Entertainment System.xml** – 3.9 MB
- **Sega Genesis.xml** – 3.9 MB
- **Atari 2600.xml** – 3.5 MB

**Platform Categories:**
- **Arcade Systems:** MAME, Model 2, Model 3, Naomi, Atomiswave, TeknoParrot, Taito Type X, Daphne
- **Console Systems:** NES, SNES, Genesis, PlayStation, PlayStation 2, N64, GameCube, Dreamcast, etc.
- **Handheld Systems:** Game Boy, Game Boy Advance, Lynx, Game Gear, PSP, Nintendo DS
- **Light Gun Collections:** 20+ gun-specific platforms (see Gun Build section)
- **Pinball:** Pinball FX2, Pinball FX3

### Directory Structure

```
LaunchBox\
├── Backups\                         # Configuration backups
├── Core\                            # LaunchBox core binaries and language packs
│   ├── LaunchBox.exe
│   ├── BigBox.exe
│   └── [30 language folders]
├── Data\
│   ├── Platforms\                   # 53 platform XML files
│   └── Playlists\                   # User-created playlists
├── Emulators\                       # Emulator integration configs
│   ├── PCSX2\
│   ├── PPSSPPGold\
│   ├── RetroArch\
│   ├── bios\
│   ├── cemu_1.26.2\                # Wii U emulator
│   ├── dolphin-2412-x64\
│   ├── dolphin-emu\
│   ├── redream\                     # Dreamcast emulator
│   ├── rpcs3\                       # PlayStation 3 emulator
│   └── yuzu\                        # Nintendo Switch emulator
├── Games\                           # Game-specific files (saves, configs)
│   ├── Arcade MAME\
│   ├── [50+ platform folders]
│   └── Wii Gun Games\
├── Images\                          # Game artwork (box art, screenshots, etc.)
│   ├── [50+ platform folders]
│   ├── Cache-BB\                    # BigBox image cache
│   ├── Cache-LB\                    # LaunchBox image cache
│   └── Media Packs\
├── LBThemes\                        # LaunchBox UI themes
│   ├── Airy\
│   ├── Default\
│   ├── Neptune\
│   └── Rincewind\
├── Logs\                            # Application logs
├── Manuals\                         # Game manuals (PDFs, scans)
│   └── [50+ platform folders]
├── Metadata\                        # Game metadata cache
├── Music\                           # Platform theme music
│   └── [50+ platform folders]
├── PauseThemes\                     # In-game pause menu themes
├── Plugins\                         # LaunchBox plugins
│   ├── BigPEmu LaunchBox Integration\
│   ├── Dolphin LaunchBox Integration\
│   ├── MAME LaunchBox Integration\
│   ├── PCSX2 LaunchBox Integration\
│   ├── RetroArch LaunchBox Integration\
│   └── ScummVM LaunchBox Integration\
├── Saves\                           # Save game backups
├── Sounds\                          # UI sound effects
│   ├── Classic\
│   ├── Multi-Sound Default\
│   └── [Sci-Fi sound packs]
├── StartupThemes\                   # Startup animation themes
├── Themes\                          # BigBox full-screen themes
│   ├── CriticalZoneV2 - Default\
│   ├── Hypermax Refried\
│   └── Unified\
├── ThirdParty\                      # Third-party utilities
│   ├── 7-Zip\
│   ├── AutoHotkey\
│   ├── CDRDAO\
│   ├── Chromium\
│   ├── DOSBox\
│   ├── FFMPEG\
│   ├── MAME\
│   ├── RetroAchievements\
│   ├── ScummVM\
│   └── VLC\
├── Updates\                         # LaunchBox update files
└── Videos\                          # Game video previews/trailers
    └── [50+ platform folders]
```

### ⚠️ Missing Critical File

**Expected but NOT FOUND:**
- `A:\LaunchBox\Data\LaunchBox.xml` – Master game database

This file should contain the complete game library metadata. Its absence suggests either:
1. Database is stored in a different location (check `Metadata/` folder)
2. LaunchBox uses a different database format (SQLite, JSON)
3. File was moved or corrupted

**Action Required:** Verify LaunchBox database location before activating backend integration.

### CLI_Launcher.exe Location

**Expected Path:** `A:\LaunchBox\ThirdParty\CLI_Launcher\CLI_Launcher.exe`
**Status:** ⚠️ **NOT FOUND**

The CLI_Launcher.exe tool (used for command-line game launching) was not found in the expected ThirdParty directory. Search results returned no matches for:
- `*CLI*`
- `*Launcher*`

**Possible Locations:**
1. Separate installation outside LaunchBox directory
2. Part of LaunchBox core (integrated into main executable)
3. Not yet installed (requires download from LaunchBox forums)

**Action Required:** Locate or install CLI_Launcher.exe before activating game launch functionality.

---

## 7. A:\Roms\ – Arcade ROM Files (14 systems)

**Purpose:** Arcade game ROM files organized by emulator/system.

### Structure

```
Roms\
├── ATOMISWAVE\                      # Sammy Atomiswave arcade system
├── DAPHNE\                          # LaserDisc arcade games (Dragon's Lair, etc.)
├── HIKARU\                          # Sega Hikaru arcade board
├── MAME\                            # Multiple Arcade Machine Emulator ROMs
│   └── *.zip (14,233 files)         # ⚠️ Large collection
├── MODEL2\                          # Sega Model 2 arcade board
├── MODEL3\                          # Sega Model 3 arcade board
├── NAOMI\                           # Sega Naomi arcade system
├── PINBALL-FX2\                     # Pinball FX2 tables
├── PINBALL-FX3\                     # Pinball FX3 tables
├── SINGE-HYPSEUS\                   # Singe 2 LaserDisc games (modern Daphne fork)
├── SINGE2\                          # Singe 2 engine games
├── TEKNOPARROT\                     # Modern arcade games (2000s-2020s)
├── TRI-FORCE\                       # Nintendo Triforce arcade board (GameCube-based)
└── TTX\                             # Taito Type X arcade PC platform
```

### ROM Counts

- **MAME:** 14,233 .zip ROM files (largest collection)
- **Other systems:** Not individually counted (timeout during large directory scans)

### File Formats

- **MAME:** `.zip` archives (CHD files may be stored separately)
- **Daphne/Singe:** `.daphne` folders with video/audio files
- **TeknoParrot:** `.exe` or game-specific formats
- **Taito Type X:** Windows executables and data files

---

## 8. A:\ThirdScreen-v5.0.12\ – Marquee Display Plugin

**Purpose:** LaunchBox plugin for third screen/marquee displays (shows game logos, artwork on separate monitor).

### Structure

```
ThirdScreen-v5.0.12\
└── Plugins\
    ├── ManagePlatformVideoMarquees.dll
    ├── ThirdScreen.dll
    └── ThirdScreenSupportLib.dll
```

### Plugin Files

- **ThirdScreen.dll** – Main plugin library
- **ThirdScreenSupportLib.dll** – Support library
- **ManagePlatformVideoMarquees.dll** – Video marquee manager

**Integration:** Installs into LaunchBox Plugins folder; displays game marquees on third monitor during gameplay.

---

## 9. A:\Tools\ – Utilities and Scripts

**Purpose:** Controller mapping tools, scripts, and system utilities.

### Installed Tools

```
Tools\
├── AHK\                             # AutoHotKey scripts
├── AutoHideMouse\                   # Hide mouse cursor during gameplay
├── Controller Mappings\             # Controller configuration files
├── HidHide\                         # Device hiding utility (prevent double inputs)
├── JoyToKey\                        # Joystick-to-keyboard mapper
├── NoMousy\                         # Alternative mouse hider
├── QuickChangeResolution\           # Resolution switcher for games
├── ReShade\                         # Post-processing shader injector
├── Scripts\                         # Custom scripts (AHK, batch, PowerShell)
├── Teknoparrot Auto Xinput\        # TeknoParrot XInput automation
├── Tur.Game.Controller.Order.1.5\  # Controller order manager
├── Xpadder\                         # Controller-to-keyboard/mouse mapper
├── _PC\                             # PC-specific files
├── _PC Files\
├── x360ce\                          # Xbox 360 Controller Emulator
└── xOutput\                         # DirectInput to XInput wrapper
```

### Tool Categories

**Controller Mapping:**
- **JoyToKey** – Maps joystick/gamepad buttons to keyboard keys
- **Xpadder** – Advanced controller-to-keyboard mapper
- **x360ce** – Emulates Xbox 360 controller for games requiring XInput
- **xOutput** – Converts DirectInput devices to XInput

**Input Management:**
- **HidHide** – Hides devices from games (prevents double input from controller + emulated keyboard)
- **Tur.Game.Controller.Order** – Sets controller detection order
- **Teknoparrot Auto Xinput** – Automates XInput configuration for TeknoParrot

**Display/Mouse:**
- **AutoHideMouse** – Hides mouse cursor during gameplay
- **NoMousy** – Alternative mouse hiding tool
- **QuickChangeResolution** – Switches display resolution per-game

**Graphics:**
- **ReShade** – Injects shaders for visual enhancement (CRT filters, scanlines, etc.)

**Scripting:**
- **AHK** – AutoHotKey script library (key remapping, automation)
- **Scripts** – Custom batch/PowerShell scripts

---

## File Type Summary

| File Type | Primary Location | Approximate Count | Purpose |
|-----------|-----------------|-------------------|---------|
| `.zip` (ROMs) | `Roms\MAME\` | 14,233 | MAME arcade game ROMs |
| `.xml` (Platforms) | `LaunchBox\Data\Platforms\` | 53 | Game metadata databases |
| `.bin` / `.rom` (BIOS) | `Bios\system\` | 586 | Emulator BIOS files |
| `.exe` (Installers) | `_INSTALL\` | 50+ | System dependencies |
| `.dll` (Plugins) | `LaunchBox\Plugins\` | 100+ | LaunchBox plugin libraries |
| `.mp4` (Videos) | `_INSTALL\`, `LaunchBox\Videos\` | 1000+ | Setup tutorials, game trailers |

---

## Total Storage Usage

| Directory | Size | Notes |
|-----------|------|-------|
| `_INSTALL\` | 3.7 GB | Installation packages |
| `Console ROMs\` | **Timed out** | Estimated 100+ GB (large collection) |
| `Emulators\` | **Timed out** | Estimated 50+ GB (TeknoParrot game files) |
| `Bios\` | ~80 MB | BIOS files (libretro pack) |
| `LaunchBox\` | **Not measured** | Estimated 500+ GB (images, videos, games) |
| `Roms\` | **Not measured** | Estimated 200+ GB (14k+ MAME ROMs + others) |
| `Gun Build\` | **Not measured** | Unknown |
| `ThirdScreen\` | <10 MB | Plugin files only |
| `Tools\` | <500 MB | Utilities and scripts |

**Estimated Total:** 1+ TB (exact measurement requires extended scan time)

---

## Critical Warnings & Action Items

### ⚠️ Missing Files

1. **LaunchBox.xml Master Database**
   - **Expected:** `A:\LaunchBox\Data\LaunchBox.xml`
   - **Status:** Not found
   - **Action:** Verify database location or check if LaunchBox uses alternative format

2. **CLI_Launcher.exe**
   - **Expected:** `A:\LaunchBox\ThirdParty\CLI_Launcher\CLI_Launcher.exe`
   - **Status:** Not found
   - **Action:** Download from LaunchBox forums or locate if installed elsewhere
   - **Impact:** Backend game launch functionality will fail without this tool

### ⚠️ Naming Inconsistencies

1. **Console ROMs folder:** `Ninendo WiiU` (typo: should be "Nintendo")
2. **Duplicate folders:** `Sega Genesis` and `megadrive` (same platform, different naming)

### ⚠️ Timeout Issues

Directory scans timed out for:
- `Console ROMs\` (du command)
- `Emulators\` (du command)

**Reason:** Extremely large directories (100+ GB each) exceeded 2-minute timeout limit.

---

## Integration Notes for Backend Development

### LaunchBox Backend Integration (`backend/routers/launchbox.py`)

**Current Implementation Assumptions:**
```python
LAUNCHBOX_ROOT = os.path.join(A_DRIVE_ROOT, 'Arcade Assistant', 'LaunchBox')
MASTER_XML = os.path.join(LAUNCHBOX_DATA, 'LaunchBox.xml')
CLI_LAUNCHER = os.path.join(LAUNCHBOX_ROOT, 'ThirdParty', 'CLI_Launcher', 'CLI_Launcher.exe')
```

**Reality Check:**
- ✅ `LAUNCHBOX_ROOT` should be `A:\LaunchBox` (no "Arcade Assistant" subfolder)
- ❌ `MASTER_XML` path is incorrect (file does not exist at `Data\LaunchBox.xml`)
- ❌ `CLI_LAUNCHER` path is incorrect (file not found in ThirdParty)

**Corrected Paths:**
```python
LAUNCHBOX_ROOT = 'A:\\LaunchBox'  # Direct root, not subfolder
LAUNCHBOX_DATA = 'A:\\LaunchBox\\Data'
PLATFORMS_DIR = 'A:\\LaunchBox\\Data\\Platforms'  # 53 XML files here
MASTER_XML = 'A:\\LaunchBox\\Data\\LaunchBox.xml'  # ⚠️ Verify this exists
CLI_LAUNCHER = '[LOCATION TBD]\\CLI_Launcher.exe'  # ⚠️ Must be located
```

**Alternative Approach:**
Instead of parsing `LaunchBox.xml` (which may not exist), parse individual platform XMLs:
```python
# Parse all platform XMLs
for xml_file in os.listdir(PLATFORMS_DIR):
    if xml_file.endswith('.xml'):
        parse_platform_xml(os.path.join(PLATFORMS_DIR, xml_file))
```

Each platform XML contains complete game metadata (title, developer, genre, year, paths).

### Platform XML Structure

Example from `Arcade MAME.xml`:
```xml
<LaunchBox>
  <Game>
    <ID>uuid</ID>
    <Title>Game Name</Title>
    <Platform>Arcade MAME</Platform>
    <Genre>Genre</Genre>
    <ReleaseDate>1993-01-01T00:00:00</ReleaseDate>
    <Developer>Developer Name</Developer>
    <Publisher>Publisher Name</Publisher>
    <ApplicationPath>A:\Emulators\MAME\mame.exe</ApplicationPath>
    <RomPath>A:\Roms\MAME\gamename.zip</RomPath>
    <!-- More metadata fields -->
  </Game>
  <!-- Thousands more games -->
</LaunchBox>
```

**Backend Strategy:**
1. **On startup:** Parse all 53 platform XMLs in `Data\Platforms\`
2. **Build cache:** Create in-memory game index (GAME_CACHE dict)
3. **Index by:** platform, genre, year for fast filtering
4. **Game launch:** Execute LaunchBox.exe with command-line args (if CLI_Launcher unavailable)

---

## Recommended Next Steps

1. **Locate CLI_Launcher.exe**
   - Search entire A: drive: `find /mnt/a -name "*CLI*.exe" -o -name "*Launcher*.exe"`
   - Check LaunchBox forums for download link
   - Alternative: Use LaunchBox.exe with command-line parameters

2. **Verify LaunchBox Database**
   - Open LaunchBox GUI, check Settings → Database Location
   - Export metadata to confirm XML structure
   - Validate platform XMLs parse correctly

3. **Update Backend Paths**
   - Correct `LAUNCHBOX_ROOT` in `backend/routers/launchbox.py`
   - Change master XML parsing to platform XML parsing
   - Add fallback if CLI_Launcher unavailable

4. **Test Drive Detection**
   - Confirm `is_on_a_drive()` returns `True` when `AA_DRIVE_ROOT=A:\`
   - Validate `parse_launchbox_xml()` successfully reads platform XMLs
   - Test game launch with direct LaunchBox.exe execution

5. **Document Alternative Launch Methods**
   - LaunchBox.exe command-line parameters
   - BigBox.exe automation scripts
   - Direct emulator execution (bypass LaunchBox)

---

## Appendix: Platform XML File List (53 files)

```
American Laser Games.xml               83 KB
Arcade MAME.xml                        12.9 MB  ← Largest platform
Atari 2600.xml                         3.5 MB
Atari 7800.xml                         304 KB
Atari Jaguar.xml                       272 KB
Atari Lynx.xml                         356 KB
Atomiswave Gun Games.xml               29 KB
Daphne.xml                             248 KB
Dreamcast Gun Games.xml                35 KB
Flash Gun Games.xml                    982 KB
Genesis Gun Games.xml                  60 KB
MAME Gun Games.xml                     617 KB
Master System Gun Games.xml            79 KB
Model 2 Gun Games.xml                  43 KB
Model 3 Gun Games.xml                  27 KB
NEC TurboGrafx-16.xml                  550 KB
NES Gun Games.xml                      160 KB
Naomi Gun Games.xml                    53 KB
Nintendo DS.xml                        451 KB
Nintendo Entertainment System.xml      4.6 MB
Nintendo Game Boy Advance.xml          5.3 MB
Nintendo Game Boy.xml                  4.2 MB
Nintendo GameCube.xml                  265 KB
Nintendo Switch.xml                    4 KB
Nintendo Wii U.xml                     118 KB
PC Gun Games.xml                       438 KB
PS2 Gun Games.xml                      94 KB
PS3 Gun Games.xml                      45 KB
PSX Gun Games.xml                      177 KB
Pinball FX2.xml                        236 KB
Pinball FX3.xml                        357 KB
SNES Gun Games.xml                     50 KB
Sammy Atomiswave.xml                   96 KB
Saturn Gun Games.xml                   81 KB
Sega 32X.xml                           171 KB
Sega Dreamcast.xml                     1.7 MB
Sega Genesis.xml                       3.9 MB
Sega Model 2.xml                       156 KB
Sega Model 3.xml                       83 KB
Sega Naomi.xml                         397 KB
Sony PSP Minis.xml                     1.5 MB
Sony PSP.xml                           515 KB
Sony Playstation 2.xml                 469 KB
Sony Playstation 3.xml                 104 KB
Sony Playstation.xml                   409 KB
Super Nintendo Entertainment System.xml 3.9 MB
Taito Type X.xml                       328 KB
TeknoParrot Arcade.xml                 405 KB
TeknoParrot Gun Games.xml              345 KB
Wii Gun Games.xml                      325 KB
```

**Total Lines:** 1,119,932 (combined XML content)
**Total Size:** 51.7 MB (platform metadata only)

---

**End of A: Drive Map**
**Document Version:** 1.0
**Last Updated:** 2025-10-05 14:30:00 UTC
