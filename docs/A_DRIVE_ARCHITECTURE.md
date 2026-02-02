# A: Drive Architecture for Arcade Assistant

## Overview

This document defines the mandated file structure and paths for Arcade Assistant when deployed to the A: drive. All paths are **hardwired** into the application logic to ensure consistent, predictable behavior across sessions.

## Detection & Activation

### Environment Variable
```bash
AA_DRIVE_ROOT=A:\
```

### Activation Logic
When `process.env.AA_DRIVE_ROOT === 'A:\\'`:
- ✅ Enable LaunchBox XML integration
- ✅ Enable emulator configuration management
- ✅ Activate hardware paths for LED Blinky, Light Guns
- ✅ Load platform-specific configs

When **not** on A: drive:
- ⚠️ Use mock data for all panels
- ⚠️ Display warning: "Arcade Assistant designed for A: drive deployment"

## Mandated Directory Structure

```
A:\
├── Arcade Assistant\
│   ├── LaunchBox\                    # LaunchBox installation root
│   │   ├── Data\
│   │   │   ├── LaunchBox.xml         # Master game collection
│   │   │   ├── Platforms\
│   │   │   │   ├── Arcade.xml        # Platform-specific metadata
│   │   │   │   ├── Nintendo Entertainment System.xml
│   │   │   │   └── [Platform].xml
│   │   │   └── Playlists\
│   │   │       ├── Favorites.xml
│   │   │       └── [Playlist].xml
│   │   ├── ThirdParty\
│   │   │   └── CLI_Launcher\         # CLI Launcher plugin for automation
│   │   └── Metadata\
│   ├── Emulators\
│   │   ├── MAME\
│   │   │   ├── mame.exe
│   │   │   └── roms\
│   │   ├── Retroarch\
│   │   │   ├── retroarch.exe
│   │   │   └── config\
│   │   └── [EmulatorName]\
│   ├── ROMs\
│   │   ├── Arcade\
│   │   ├── NES\
│   │   ├── SNES\
│   │   └── [Platform]\
│   ├── Configs\                       # Arcade Assistant configs
│   │   ├── emulators\
│   │   │   ├── mame.json
│   │   │   └── [emulator].json
│   │   ├── hardware\
│   │   │   ├── led-blinky.json
│   │   │   └── light-guns.json
│   │   └── voice\
│   ├── State\                         # Runtime state
│   │   ├── session.json
│   │   ├── recent-games.json
│   │   └── user-profiles.json
│   └── Logs\                          # System logs
│       ├── aa-access.log
│       └── launchbox-launches.log
└── [Other A: drive content]
```

## File Path Constants

### LaunchBox Integration
```javascript
// backend/constants/paths.js
const A_DRIVE_ROOT = process.env.AA_DRIVE_ROOT || 'A:\\'

const LAUNCHBOX_PATHS = {
  ROOT: `${A_DRIVE_ROOT}Arcade Assistant\\LaunchBox`,
  DATA: `${A_DRIVE_ROOT}Arcade Assistant\\LaunchBox\\Data`,
  MASTER_XML: `${A_DRIVE_ROOT}Arcade Assistant\\LaunchBox\\Data\\LaunchBox.xml`,
  PLATFORMS: `${A_DRIVE_ROOT}Arcade Assistant\\LaunchBox\\Data\\Platforms`,
  PLAYLISTS: `${A_DRIVE_ROOT}Arcade Assistant\\LaunchBox\\Data\\Playlists`,
  CLI_LAUNCHER: `${A_DRIVE_ROOT}Arcade Assistant\\LaunchBox\\ThirdParty\\CLI_Launcher\\CLI_Launcher.exe`
}

const EMULATOR_PATHS = {
  ROOT: `${A_DRIVE_ROOT}Arcade Assistant\\Emulators`,
  MAME: `${A_DRIVE_ROOT}Arcade Assistant\\Emulators\\MAME\\mame.exe`,
  RETROARCH: `${A_DRIVE_ROOT}Arcade Assistant\\Emulators\\Retroarch\\retroarch.exe`
}

const AA_PATHS = {
  CONFIGS: `${A_DRIVE_ROOT}Arcade Assistant\\Configs`,
  STATE: `${A_DRIVE_ROOT}Arcade Assistant\\State`,
  LOGS: `${A_DRIVE_ROOT}Arcade Assistant\\Logs`
}
```

## Backend Integration Contract

### LaunchBox XML Parser Service
**File:** `backend/services/launchbox_parser.py`

**Responsibilities:**
1. Parse `LaunchBox.xml` on startup (when on A: drive)
2. Load platform XMLs from `/Data/Platforms/*.xml`
3. Cache game metadata in memory
4. Expose API endpoints for game queries

**API Endpoints to Create:**
```
GET  /api/launchbox/games              # List all games (with filters)
GET  /api/launchbox/games/:id          # Get game details
POST /api/launchbox/launch/:id         # Launch game via CLI Launcher
GET  /api/launchbox/platforms          # List available platforms
GET  /api/launchbox/playlists          # List available playlists
GET  /api/launchbox/stats              # Get library statistics
POST /api/launchbox/random             # Get random game (with filters)
```

### Data Model (from XML)
```python
class Game:
    id: str                    # <ID> - UUID
    title: str                 # <Title>
    platform: str              # <Platform>
    developer: str             # <Developer>
    publisher: str             # <Publisher>
    genre: str                 # <Genre>
    series: str                # <Series>
    year: int                  # <ReleaseDate> (parsed)
    max_players: int           # <MaxPlayers>
    play_mode: str             # <PlayMode>
    database_id: int           # <DatabaseID>
    application_path: str      # <ApplicationPath> - emulator
    rom_path: str              # <RomPath> - game file
    command_line: str          # <CommandLine> - launch parameters
```

### XML Parsing Strategy

**Libraries:**
- Python: `xml.etree.ElementTree` (built-in)
- Validation: `lxml` (if needed for schema validation)

**Caching Strategy:**
1. Parse all XMLs on app startup
2. Store in-memory dictionary: `{ game_id: Game }`
3. Build indexes: by platform, by genre, by year
4. Lazy-load platform XMLs when needed

**Performance:**
- Expected game count: ~500-1000 games
- Parsing time: <2 seconds on A: drive
- Memory footprint: ~5-10 MB

## Launch Integration

### CLI Launcher Command Pattern
```bash
# Launch by game ID
A:\Arcade Assistant\LaunchBox\ThirdParty\CLI_Launcher\CLI_Launcher.exe launch_by_id "{game_uuid}"

# Launch with timed exit (optional)
CLI_Launcher.exe launch_by_id "{game_uuid}" -t=60

# Navigate to platform
CLI_Launcher.exe platform "Arcade"

# Navigate to playlist
CLI_Launcher.exe playlist "Favorites"
```

### Backend Launch Handler
**File:** `backend/routers/launchbox.py`

```python
@router.post("/api/launchbox/launch/{game_id}")
async def launch_game(game_id: str):
    # 1. Validate game exists in cache
    # 2. Build CLI Launcher command
    # 3. Execute subprocess
    # 4. Update play count/last played in State
    # 5. Return success response
```

## Migration Checklist

### Pre-Migration (Current State)
- [ ] All panels use mock data
- [ ] UI features fully functional (filter, sort, random)
- [ ] Backend stubs created with TODOs
- [ ] Architecture documented

### During Migration to A: Drive
- [ ] Copy Arcade Assistant to `A:\Arcade Assistant\`
- [ ] Install LaunchBox to `A:\Arcade Assistant\LaunchBox\`
- [ ] Install emulators to `A:\Arcade Assistant\Emulators\`
- [ ] Set `AA_DRIVE_ROOT=A:\` in `.env`
- [ ] Create `/Configs`, `/State`, `/Logs` directories
- [ ] Run backend XML parser validation

### Post-Migration Validation
- [ ] Verify XML files parse successfully
- [ ] Test game launch via CLI Launcher
- [ ] Confirm filter/sort uses real data
- [ ] Validate random game selector
- [ ] Check play count tracking
- [ ] Test all panel integrations

## Data Synchronization

### State Files (Auto-Updated)
```
/State/recent-games.json      # Updated on game launch
/State/session.json           # Updated on session changes
/State/play-stats.json        # Updated on game exit
```

### Backup Strategy
```
/Backups/YYYYMMDD/
├── LaunchBox.xml.bak
├── Platforms/
└── State/
```

## Error Handling

### Missing A: Drive
```javascript
// Frontend detection
if (!isOnADrive) {
  showWarning("Arcade Assistant requires A: drive. Using demo mode.")
}

// Backend fallback
if (!os.path.exists(A_DRIVE_ROOT):
    logger.warning("A: drive not detected. Using mock data.")
    return MOCK_GAME_DATA
```

### Corrupted XML
- Log error to `A:\Arcade Assistant\Logs\xml-errors.log`
- Fall back to last known good cache
- Display user notification: "LaunchBox data needs repair"

### CLI Launcher Failure
- Retry once with 2-second delay
- Log failure reason
- Display toast: "Failed to launch game. Check emulator config."

## Future Enhancements

1. **Playlist Auto-Creation**
   - Generate playlists by genre, decade, play count
   - Save to `/Data/Playlists/`

2. **Play Statistics Dashboard**
   - Track: total playtime, favorite genres, most played games
   - Store in `/State/analytics.json`

3. **Cloud Backup (Optional)**
   - Sync state files to Firebase
   - Enable cross-device statistics

4. **Voice Commands**
   - "Launch [game name]"
   - "Show me fighting games from the 90s"
   - Integration with Voice Panel (Vicky)

---

**Document Version:** 1.0
**Last Updated:** 2025-09-30
**Status:** Ready for A: Drive Migration
