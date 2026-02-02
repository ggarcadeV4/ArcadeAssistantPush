# Pegasus Frontend Integration Plan
## Arcadia Cabinet - AI-Powered Arcade Experience

**Created**: 2025-12-09
**Status**: Planning Phase
**Estimated Total Effort**: 12-18 hours across multiple sessions

---

## Executive Summary

Migrate from RetroFE to Pegasus as the primary game frontend for Arcadia cabinets, leveraging existing LaunchBox artwork and the Arcade Assistant AI-powered backend.

### Why Pegasus?
- ✅ Modern, beautiful, video-ready
- ✅ Open source, free, no licensing costs
- ✅ Less common = unique visual differentiator
- ✅ Works perfectly with AA backend
- ✅ Native Steam support for customer expansion
- ✅ Portable installation on A: drive

---

## Phase 1: Foundation (Session 1-2)
**Estimated Time: 3-4 hours**

### 1.1 Download & Install Pegasus
- [ ] Download Pegasus from https://pegasus-frontend.org
- [ ] Extract to `A:\Tools\Pegasus\`
- [ ] Create `portable.txt` in Pegasus folder (enables portable mode)
- [ ] Verify Pegasus launches standalone

### 1.2 Directory Structure
```
A:\Tools\Pegasus\
├── pegasus-fe.exe
├── portable.txt           ← Empty file, enables portable mode
├── config\                ← Settings (auto-created)
├── themes\                ← Download themes here
└── metadata\              ← We'll generate collection metadata here
    ├── arcade_mame\
    │   └── metadata.pegasus.txt
    ├── nintendo_nes\
    │   └── metadata.pegasus.txt
    └── (one folder per collection)
```

### 1.3 Create Pegasus Path Constants
- [ ] Add to `backend/constants/paths.py`:
  ```python
  class Pegasus:
      ROOT = _DRIVE_ROOT / "Tools" / "Pegasus"
      EXECUTABLE = ROOT / "pegasus-fe.exe"
      METADATA = ROOT / "metadata"
      THEMES = ROOT / "themes"
  ```

### 1.4 Update AA Backend for Pegasus
- [ ] Add Pegasus launch endpoint to launchbox.py (or new router)
- [ ] Create `scripts/aa_launch_pegasus.bat` (launch bridge)
- [ ] Test manual game launch through AA backend

---

## Phase 2: Metadata Generation (Session 2-3)
**Estimated Time: 3-4 hours**

### 2.1 Create Collection Generator Script
- [ ] New file: `scripts/generate_pegasus_metadata.py`
- [ ] Read from `A:\.aa\launchbox_games.json` (10,111 games)
- [ ] Generate `metadata.pegasus.txt` per platform
- [ ] Include:
  - Game titles, files, descriptions
  - Asset paths pointing to LaunchBox Images
  - Launch commands via AA backend
  - Genres, release years, player counts

### 2.2 Metadata Format Reference
```ini
# metadata.pegasus.txt

collection: Arcade MAME
shortname: arcade_mame
launch: A:\Arcade Assistant Local\scripts\aa_launch_pegasus.bat "{file.basename}" "Arcade MAME"

game: Pac-Man
file: pacman.zip
developer: Namco
release: 1980
players: 1-2
genre: Maze
description: The iconic maze chase game...
assets.boxFront: A:\LaunchBox\Images\Arcade MAME\Box - Front
assets.logo: A:\LaunchBox\Images\Arcade MAME\Clear Logo
assets.marquee: A:\LaunchBox\Images\Arcade MAME\Arcade - Marquee
assets.video: A:\LaunchBox\Videos\Arcade MAME
```

### 2.3 Test Generation
- [ ] Run generator for one platform (NES - smaller)
- [ ] Launch Pegasus, verify games appear
- [ ] Verify artwork displays correctly
- [ ] Test launching a game through AA backend

### 2.4 Generate All Platforms
- [ ] Run full generation (50 platforms)
- [ ] Verify Main collection listing
- [ ] Spot-check various platforms

---

## Phase 3: Launch Bridge & AI Integration (Session 3-4)
**Estimated Time: 3-4 hours**

### 3.1 Create Pegasus Launch Bridge
- [ ] `scripts/aa_launch_pegasus.bat`:
  ```batch
  @echo off
  set "GAME_FILE=%~1"
  set "COLLECTION=%~2"
  curl -s -X POST "http://localhost:8787/api/launchbox/launch-by-title" ^
    -H "Content-Type: application/json" ^
    -H "x-panel: pegasus" ^
    -d "{\"title\": \"%GAME_FILE%\", \"collection\": \"%COLLECTION%\"}"
  ```

### 3.2 Backend Endpoint Updates
- [ ] Accept `x-panel: pegasus` header
- [ ] Log Pegasus launches for analytics
- [ ] Trigger LED patterns on game select
- [ ] Trigger Marquee updates on game select

### 3.3 Voice Control Integration
- [ ] Verify LoRa can launch games (should work via existing API)
- [ ] Test: "Hey LoRa, play Pac-Man"
- [ ] Verify game launches through Pegasus or directly

### 3.4 Game Browse Events (Optional Enhancement)
- [ ] Pegasus doesn't have browse hooks
- [ ] Consider: Hotkey overlay as alternative for "what game is this?"
- [ ] Document limitation

---

## Phase 4: Theme Selection & Customization (Session 4-5)
**Estimated Time: 2-3 hours**

### 4.1 Research & Select Theme
- [ ] Browse: https://pegasus-frontend.org/tools/
- [ ] Look for arcade-friendly themes:
  - gameOS
  - Neoretro
  - EasyLaunch
  - Minimis
- [ ] Download chosen theme(s) to `A:\Tools\Pegasus\themes\`

### 4.2 Theme Configuration
- [ ] Set default theme in Pegasus settings
- [ ] Configure colors/branding if needed
- [ ] Test on various collections

### 4.3 Theme Customization (If Needed)
- [ ] Basic QML edits for colors
- [ ] Custom logo/branding
- [ ] Video background (attract mode)

---

## Phase 5: Marquee Service (Session 5-6)
**Estimated Time: 3-4 hours**

### 5.1 Marquee Display Service
- [ ] Create web-based marquee viewer
- [ ] Fullscreen browser on marquee monitor
- [ ] WebSocket connection to AA backend
- [ ] Receives "game changed" events

### 5.2 Marquee Content Flow
```
Game selected in Pegasus
         ↓
AA Backend notified (via launch or separate event)
         ↓
Marquee service receives WebSocket event
         ↓
Displays: Video → Static Image → Video (loop)
```

### 5.3 Asset Resolution
- [ ] Map game to marquee assets
- [ ] Fallback to platform marquee if game-specific missing
- [ ] Fallback to generic Arcadia marquee if all missing

---

## Phase 6: Testing & Polish (Session 6-7)
**Estimated Time: 2-3 hours**

### 6.1 End-to-End Testing
- [ ] Launch Pegasus on boot (startup script)
- [ ] Navigate collections
- [ ] Launch games across platforms:
  - [ ] MAME arcade games
  - [ ] Console emulators (NES, SNES, Genesis)
  - [ ] TeknoParrot games
  - [ ] Steam games (if configured)
- [ ] Voice commands
- [ ] LED patterns
- [ ] Marquee updates
- [ ] Pause menu overlay

### 6.2 Performance Testing
- [ ] Startup time
- [ ] Collection load time
- [ ] Video playback smoothness
- [ ] Memory usage

### 6.3 Edge Cases
- [ ] Games with special characters in names
- [ ] Very long game titles
- [ ] Missing artwork
- [ ] Failed launches

---

## Phase 7: Content Display Manager Updates (Session 7)
**Estimated Time: 1-2 hours**

### 7.1 Update Frontend UI
- [ ] Rename/refactor RetroFE references to Pegasus
- [ ] Update collection generation buttons
- [ ] Update paths display
- [ ] Add Pegasus theme selector (optional)

### 7.2 Update Backend Endpoints
- [ ] `/api/content/pegasus/generate` - Generate metadata
- [ ] `/api/content/pegasus/generate-all` - Generate all
- [ ] `/api/content/pegasus/themes` - List available themes

---

## Phase 8: Customer Expansion Features (Future)
**Estimated Time: 4-6 hours**

### 8.1 Steam Integration
- [ ] "Link Steam Account" in AA web UI
- [ ] Import customer's Steam library
- [ ] Auto-generate Pegasus metadata for Steam games
- [ ] Controller profile suggestions

### 8.2 Easy Game Add
- [ ] "Add Your Own Game" form in AA web UI
- [ ] ROM file upload (with legal notice)
- [ ] Artwork fetching from online sources
- [ ] Auto-add to Pegasus metadata

### 8.3 ROM Management
- [ ] File browser for customer's ROMs
- [ ] Drag & drop import
- [ ] Auto-scraping integration

---

## Files to Create/Modify

### New Files
| File | Purpose |
|------|---------|
| `scripts/generate_pegasus_metadata.py` | Convert launchbox_games.json → Pegasus format |
| `scripts/aa_launch_pegasus.bat` | Launch bridge for Pegasus → AA backend |
| `backend/routers/pegasus.py` | Pegasus-specific endpoints (optional) |
| `frontend/src/panels/launchbox/PegasusManager.jsx` | UI for Pegasus management (optional) |

### Modified Files
| File | Changes |
|------|---------|
| `backend/constants/paths.py` | Add Pegasus paths |
| `backend/routers/launchbox.py` | Accept x-panel: pegasus |
| `frontend/src/panels/launchbox/ContentDisplayManager.jsx` | Update for Pegasus |
| `start-arcade-assistant.bat` | Optionally launch Pegasus |

---

## Success Criteria

### Minimum Viable Integration
- [ ] Pegasus launches and shows all 50 collections
- [ ] Games launch correctly through AA backend
- [ ] Artwork displays from LaunchBox paths
- [ ] Voice control works ("Hey LoRa, play...")

### Full Integration
- [ ] LED patterns trigger on game select
- [ ] Marquee updates dynamically
- [ ] Hotkey overlay works over Pegasus
- [ ] Theme looks polished and unique

### Production Ready
- [ ] Tested on actual cabinet hardware
- [ ] Startup/shutdown scripts work
- [ ] Customer can add Steam games
- [ ] Documentation complete

---

## Rollback Plan

If Pegasus doesn't work out:
1. RetroFE is still installed at `A:\Tools\RetroFE\`
2. LaunchBox/BigBox is still the source of truth
3. All AA backend work is frontend-agnostic

**Nothing is permanent until you ship cabinets.**

---

## Notes & Decisions Log

### 2025-12-09
- Decided to migrate from RetroFE to Pegasus
- Reasons: Modern, beautiful, less common, AI-integration friendly
- Maintaining LaunchBox as curator/scraper (data source)
- AA backend remains frontend-agnostic

---

## Resources

- **Pegasus Website**: https://pegasus-frontend.org
- **Pegasus Docs**: https://pegasus-frontend.org/docs/
- **Pegasus Themes**: https://pegasus-frontend.org/tools/
- **Metadata Format**: https://pegasus-frontend.org/docs/user-guide/meta-files/
- **Pegasus Discord**: Active community for questions

---

*This document will be updated as we progress through sessions.*
