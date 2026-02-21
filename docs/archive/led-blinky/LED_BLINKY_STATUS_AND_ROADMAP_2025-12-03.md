# LED Blinky - Status & Enhancement Roadmap
**Date:** December 3, 2025  
**Session:** Morning optimization and ScoreKeeper Sam integration

---

## Current Status Summary

### ✅ What's Working

**1. Per-Game LED Lighting (FULLY FUNCTIONAL)**
- Automatic LED profile application on game launch
- Game → LED profile bindings stored in `A:\configs\ledblinky\game_profiles.json`
- Auto-applies before emulator launches (line 1780 in `backend/routers/launchbox.py`)
- Logging of LED launch events to `A:\state\scorekeeper\led_launches.jsonl`

**2. Configuration Management**
- LED profile creation/editing (`A:\configs\ledblinky\profiles\*.json`)
- LED channel mapping (`A:\configs\ledblinky\led_channels.json`)
- Game profile bindings (`A:\configs\ledblinky\game_profiles.json`)
- All changes include backup, dry-run, and logging

**3. LaunchBox Integration**
- LED Blinky can search ALL LaunchBox games (line 1038 in `LEDBlinkyPanel.jsx`)
- Uses `/api/launchbox` endpoint for game data
- Reads from same XML files as LaunchBox LoRa
- Supports ALL platforms in LaunchBox (Arcade, NES, SNES, Steam, PC, etc.)

**4. API Endpoints Available**
- `POST /api/local/led/profile/apply` - Apply LED profile
- `POST /api/local/led/channels/apply` - Update LED channel mapping
- `POST /api/local/led/game-profile/apply` - Bind game to LED profile
- `GET /api/local/led/game-profile?game_id=X` - Get game's LED binding
- `DELETE /api/local/led/game-profile?game_id=X` - Remove LED binding
- `GET /api/local/led/game-profiles` - List all game bindings

---

## User Concerns & Questions

### 1. Steam Game LED Support
**Question:** "Can LED Blinky work with Steam games?"

**Answer:** YES, but with conditions:
- ✅ Steam games MUST be added to LaunchBox first
- ✅ Once in LaunchBox, they appear in LED Blinky's game search
- ✅ Can bind LED profiles to Steam games just like any other game
- ✅ LEDs auto-apply when launched via LaunchBox

**Current Limitation:**
- ❌ No native Steam integration (doesn't detect Steam launches outside LaunchBox)
- ❌ Must launch Steam games through LaunchBox for LED automation

### 2. Cross-Panel Communication
**Question:** "Do LoRa and Blinky talk to each other?"

**Answer:** They share data but don't directly communicate:
- Both read from LaunchBox XML files independently
- Both use `/api/launchbox` backend endpoints
- LED Blinky can search and bind ANY game that LoRa can see
- Integration happens via shared backend, not direct panel-to-panel

### 3. Configuration File Management
**Question:** "Can LED Blinky change configuration files?"

**Answer:** YES, multiple types:
- ✅ LED profiles (`configs/ledblinky/profiles/*.json`)
- ✅ Channel mappings (`configs/ledblinky/led_channels.json`)
- ✅ Game bindings (`configs/ledblinky/game_profiles.json`)
- ✅ LEDBlinky software configs
- All with backup, dry-run, and logging

---

## Enhancement Roadmap

### Priority 1: Steam Native Integration (Optional)
**Goal:** Detect and apply LED profiles for Steam games launched outside LaunchBox

**Requirements:**
1. Steam process monitor
2. Steam game ID detection
3. LED profile binding for Steam IDs
4. Auto-apply on Steam launch detection

**Estimated Effort:** 3-4 hours  
**User Decision:** Use LaunchBox workaround OR build native integration?

### Priority 2: UI Improvements
**Goal:** Make game binding more intuitive

**Enhancements:**
1. **Platform Filter in Game Search**
   - Currently searches all platforms
   - Add dropdown to filter by platform (Arcade, NES, Steam, etc.)
   - Makes finding Steam games easier

2. **Quick Bind Interface**
   - "Bind this game to purple" voice command
   - One-click binding from game list
   - Visual confirmation of bound games

3. **Binding Status Indicators**
   - Show which games have LED bindings
   - Display current LED profile for each game
   - Quick edit/remove bindings

**Estimated Effort:** 2-3 hours

### Priority 3: LED Profile Library
**Goal:** Pre-built LED profiles for common use cases

**Profiles to Create:**
1. **Color Themes**
   - Purple (all buttons purple)
   - Red (all buttons red)
   - Blue (all buttons blue)
   - Rainbow (gradient across buttons)

2. **Genre-Based**
   - Fighting (6-button layout)
   - Platformer (jump + action)
   - Shooter (rapid fire indicators)
   - Racing (gas/brake colors)

3. **Game-Specific**
   - Street Fighter (Capcom colors)
   - Pac-Man (yellow/ghost colors)
   - Mortal Kombat (blood red)

**Estimated Effort:** 1-2 hours (profile creation)

### Priority 4: Voice Integration with Vicky
**Goal:** "Hey Vicky, set Street Fighter to purple LEDs"

**Requirements:**
1. Voice command parsing for LED requests
2. Game name resolution
3. Profile selection/creation
4. Binding confirmation

**Estimated Effort:** 2-3 hours

### Priority 5: ScoreKeeper Sam Integration
**Goal:** LED feedback for leaderboard status

**Features:**
1. **Champion Indicator**
   - Flash gold LEDs when #1 player launches their best game
   - "You're the champion at Street Fighter!"

2. **Rank-Based Colors**
   - Gold for #1
   - Silver for #2
   - Bronze for #3
   - Standard for others

3. **Achievement Celebrations**
   - Special LED pattern on new high score
   - Rainbow flash on beating house record

**Estimated Effort:** 3-4 hours

---

## Technical Architecture

### File Locations
```
A:\
├── configs/
│   └── ledblinky/
│       ├── led_channels.json          # Physical LED wiring
│       ├── game_profiles.json         # Game → Profile bindings
│       └── profiles/                  # LED color profiles
│           ├── Purple.json
│           ├── Red.json
│           └── ...
│
├── state/
│   └── scorekeeper/
│       └── led_launches.jsonl         # LED launch event log
│
└── logs/
    └── led_changes.jsonl              # LED config change log
```

### Code Locations
```
Backend:
- backend/routers/led.py               # LED API endpoints
- backend/routers/led_blinky.py        # Legacy LED endpoints
- backend/services/led_game_profiles.py # Game binding storage
- backend/services/led_mapping_service.py # Profile management
- backend/routers/launchbox.py:1780    # Auto-apply on launch

Frontend:
- frontend/src/components/LEDBlinkyPanel.jsx # Main UI
- frontend/src/services/ledBlinkyClient.js   # API client
- frontend/src/panels/led-blinky/ChatBox.jsx # Voice interface
```

### Data Flow
```
User launches game via LoRa
  ↓
Backend: launch_game() called
  ↓
Backend: _apply_led_profile_binding_for_launch()
  ↓
Check: Does game have LED binding?
  ↓ (if yes)
Load LED profile from configs/ledblinky/profiles/
  ↓
Apply to LED hardware
  ↓
Log to state/scorekeeper/led_launches.jsonl
  ↓
Game launches with correct LED colors
```

---

## Quick Start for Next Session

### To Bind a Steam Game to Purple LEDs:

**Prerequisites:**
1. Steam game is in LaunchBox (on A: drive)
2. "Purple" LED profile exists in `A:\configs\ledblinky\profiles\Purple.json`

**Steps:**
1. Open LED Blinky panel
2. Search for the Steam game (it should appear)
3. Select the game
4. Choose "Purple" profile
5. Click "Apply" to bind
6. Launch via LoRa → LEDs turn purple!

**If game doesn't appear:**
- Check if LaunchBox LoRa can see it
- Verify game is in LaunchBox XML files
- Check platform filter in LED Blinky search

### To Create a Purple LED Profile:

**Via API:**
```bash
POST /api/local/led/profile/apply
{
  "profile_name": "Purple",
  "scope": "global",
  "buttons": {
    "p1.button1": {"color": "#800080"},
    "p1.button2": {"color": "#800080"},
    "p1.button3": {"color": "#800080"},
    "p1.button4": {"color": "#800080"},
    "p1.button5": {"color": "#800080"},
    "p1.button6": {"color": "#800080"}
  }
}
```

**Via UI:**
1. Open LED Blinky panel
2. Click "Create Profile"
3. Name it "Purple"
4. Set all buttons to #800080 (purple hex color)
5. Save

---

## Known Issues & Limitations

### 1. No Native Steam Detection
- **Issue:** Can't detect Steam games launched outside LaunchBox
- **Workaround:** Launch Steam games through LaunchBox
- **Fix:** Build Steam process monitor (3-4 hours)

### 2. Platform Filter May Not Show Steam
- **Issue:** UI might filter out non-arcade platforms
- **Workaround:** Use "All Platforms" or search by name
- **Fix:** Add explicit platform dropdown (1 hour)

### 3. No Pre-Built Profiles
- **Issue:** Users must create profiles from scratch
- **Workaround:** Create manually via UI or API
- **Fix:** Ship with common color profiles (1 hour)

---

## Testing Checklist

### Verify LED Blinky Functionality:

**1. Game Search**
```bash
# Test LaunchBox game search
GET /api/launchbox/games?q=Street%20Fighter
# Should return games including Steam titles if in LaunchBox
```

**2. LED Profile Binding**
```bash
# Get current binding for a game
GET /api/local/led/game-profile?game_id={game_id}

# Bind game to profile
POST /api/local/led/game-profile/apply
{
  "game_id": "{game_id}",
  "profile_name": "Purple"
}
```

**3. Auto-Apply on Launch**
```bash
# Launch a game with LED binding
POST /api/launchbox/launch/{game_id}
# Check logs: A:\state\scorekeeper\led_launches.jsonl
# Verify LED profile was applied
```

**4. Configuration Backup**
```bash
# After any LED config change, verify backup exists
ls A:\backups\{YYYYMMDD}/configs/ledblinky/
```

---

## Questions for Next Session

1. **Steam Integration Priority?**
   - Use LaunchBox workaround (immediate, no dev needed)
   - Build native Steam integration (3-4 hours dev)

2. **Profile Library?**
   - Which color profiles do you want pre-built?
   - Any game-specific profiles needed?

3. **UI Enhancements?**
   - Platform filter in game search?
   - Quick bind interface?
   - Visual binding indicators?

4. **ScoreKeeper Integration?**
   - LED feedback for leaderboard rankings?
   - Champion indicators?
   - Achievement celebrations?

---

## Session Summary (Dec 3, 2025)

**Completed Today:**
1. ✅ Verified LED Blinky per-game lighting is fully functional
2. ✅ Confirmed LaunchBox integration works for ALL platforms
3. ✅ Documented Steam game support (via LaunchBox)
4. ✅ Identified enhancement opportunities
5. ✅ Created this roadmap document

**Key Findings:**
- LED Blinky CAN work with Steam games (if in LaunchBox)
- Auto-apply on launch is already implemented
- Configuration management is robust and safe
- Main limitation is native Steam detection

**Next Steps:**
- Decide on Steam integration approach
- Create common LED profiles (Purple, Red, Blue, etc.)
- Consider UI enhancements for easier binding
- Explore ScoreKeeper Sam integration for LED feedback

---

**For Next AI/Session:**
Read this document first to understand LED Blinky's current state and user concerns. Focus on the Enhancement Roadmap section for next priorities.

**User's Main Concern:**
"I want to bind my Steam games to LED profiles (like purple LEDs). Is this possible and how do I do it?"

**Answer:**
Yes! Steam games in LaunchBox can be bound to LED profiles. The system is ready - just needs the game in LaunchBox and a profile created.
