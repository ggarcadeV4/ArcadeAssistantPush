# Metadata Independence Migration Plan

> **Purpose**: Remove dependency on LaunchBox metadata and create a self-owned game library format.
> 
> **Status**: PLANNING
> 
> **Created**: 2025-12-07
> 
> **Why**: LaunchBox is proprietary software. To distribute Arcade Assistant commercially or publicly, we need to own our metadata format.

---

## Executive Summary

The current architecture already has a JSON cache layer that decouples the frontend from LaunchBox. The migration involves:

1. Renaming components from "LaunchBox" to a neutral name
2. Making the JSON cache the authoritative data source (not a cache)
3. Replacing the LaunchBox XML parser with alternative metadata importers
4. Updating all references throughout the codebase

**Estimated effort**: 2-3 focused sessions

---

## Current Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     CURRENT DATA FLOW                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  LaunchBox XML ──► launchbox_parser.py ──► JSON Cache ──► API   │
│  (proprietary)         (coupling)           (decoupled)         │
│                                                                 │
│  Frontend only sees JSON. Adapters only see Game model.         │
│  The coupling is ONLY in the parser/importer layer.             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Target Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     TARGET DATA FLOW                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐                                           │
│  │ Import Sources   │                                           │
│  │ ─────────────────│                                           │
│  │ • ScreenScraper  │                                           │
│  │ • ROM Scanner    │ ──► game_library.json ──► API ──► Panel   │
│  │ • Manual Editor  │      (authoritative)                      │
│  │ • Legacy LB XML  │                                           │
│  └──────────────────┘                                           │
│                                                                 │
│  No runtime dependency on any external metadata source.         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Rename Components (Non-Breaking)

### Goal
Rename "LaunchBox" references to a neutral name while maintaining functionality.

### Proposed New Names

| Current | New |
|---------|-----|
| LaunchBox LoRa | **Game Library** or **Arcade Library** |
| `LaunchBoxPanel.jsx` | `GameLibraryPanel.jsx` |
| `/api/launchbox/*` | `/api/library/*` (keep old routes as aliases) |
| `launchbox_json_cache.py` | `game_library.py` |
| `launchbox_games.json` | `game_library.json` |

### Files to Rename/Update

#### Backend (Python)
- [ ] `backend/routers/launchbox.py` → `backend/routers/game_library.py`
- [ ] `backend/routers/launchbox_cache.py` → `backend/routers/library_cache.py`
- [ ] `backend/services/launchbox_parser.py` → `backend/services/legacy_lb_importer.py` (mark deprecated)
- [ ] `backend/services/launchbox_json_cache.py` → `backend/services/game_library.py`
- [ ] `backend/models/game.py` → Keep as-is (already neutral)

#### Frontend (JavaScript/React)
- [ ] `frontend/src/panels/launchbox/` → `frontend/src/panels/game-library/`
- [ ] `LaunchBoxPanel.jsx` → `GameLibraryPanel.jsx`
- [ ] Update all imports and references
- [ ] Update route in `App.jsx`

#### Gateway (Node.js)
- [ ] `gateway/routes/launchboxProxy.js` → Add `/api/library/*` aliases
- [ ] Keep `/api/launchbox/*` working (backward compatible)

#### Config Files
- [ ] `A:\.aa\launchbox_games.json` → `A:\.aa\game_library.json`
- [ ] Update config references in `launchers.json`

---

## Phase 2: Define Self-Owned Schema

### Game Library Schema (v1.0)

```json
{
  "$schema": "https://arcade-assistant.local/schemas/game-library-v1.json",
  "version": "1.0",
  "last_updated": "2025-12-07T12:00:00Z",
  "metadata_sources": ["screenscraper", "manual"],
  "games": [
    {
      "id": "uuid-v4",
      "title": "Street Fighter II: Champion Edition",
      "sort_title": "Street Fighter II Champion Edition",
      "platform": "Arcade",
      "genre": "Fighting",
      "year": 1992,
      "developer": "Capcom",
      "publisher": "Capcom",
      "players": "2",
      "rom": {
        "path": "A:/ROMs/MAME/sf2ce.zip",
        "crc": "abc123",
        "verified": true
      },
      "artwork": {
        "box_front": "A:/Artwork/Arcade/sf2ce/box.png",
        "screenshot": "A:/Artwork/Arcade/sf2ce/screen.png",
        "clear_logo": "A:/Artwork/Arcade/sf2ce/logo.png",
        "marquee": "A:/Artwork/Arcade/sf2ce/marquee.png"
      },
      "emulator_hints": {
        "preferred": "mame",
        "profile": null
      },
      "tags": ["classic", "capcom", "fighting"],
      "custom": {}
    }
  ]
}
```

### Migration from Current Format

The current JSON cache already contains most fields. Migration is mostly a rename:

| Current Field | New Field |
|--------------|-----------|
| `id` | `id` (keep) |
| `title` | `title` (keep) |
| `platform` | `platform` (keep) |
| `genre` | `genre` (keep) |
| `release_date` / `year` | `year` |
| `application_path` | `rom.path` |
| `box_front_path` | `artwork.box_front` |
| `screenshot_path` | `artwork.screenshot` |
| `clear_logo_path` | `artwork.clear_logo` |

---

## Phase 3: Build Metadata Importers

### 3.1 Legacy LaunchBox Importer (One-Time Migration)

```python
# scripts/import_from_launchbox.py
# Reads LaunchBox XML, outputs game_library.json
# Run once to migrate, then delete LaunchBox dependency
```

**Status**: Already exists as `scripts/build_launchbox_cache.py` - just needs output format update.

### 3.2 ROM Scanner (Automatic Detection)

```python
# scripts/scan_roms.py
# Scans ROM directories, matches against No-Intro DATs
# Creates skeleton entries for unmatched games
```

### 3.3 ScreenScraper Importer (Optional)

```python
# scripts/import_from_screenscraper.py
# Uses ScreenScraper.fr API to fetch metadata and artwork
# Requires free account with API key
```

### 3.4 Manual Editor (Future)

Web UI in panel for adding/editing games manually.

---

## Phase 4: Update API Endpoints

### New Routes (Primary)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/library/games` | List games with filters |
| GET | `/api/library/games/{id}` | Get single game |
| GET | `/api/library/platforms` | List platforms |
| GET | `/api/library/genres` | List genres |
| POST | `/api/library/launch/{id}` | Launch game |
| GET | `/api/library/image/{id}` | Get game artwork |
| GET | `/api/library/cache/status` | Cache status |
| POST | `/api/library/cache/reload` | Reload cache |

### Legacy Routes (Aliases for Backward Compatibility)

| Legacy Path | Alias To |
|-------------|----------|
| `/api/launchbox/*` | `/api/library/*` |

---

## Phase 5: Cleanup

Once migration is complete and tested:

- [ ] Remove `launchbox_parser.py` (or keep as legacy importer only)
- [ ] Remove LaunchBox-specific code paths
- [ ] Update documentation
- [ ] Update panel name in UI
- [ ] Update any hardcoded "LaunchBox" strings

---

## Files Reference

### Files That Need Changes

```
backend/
├── routers/
│   ├── launchbox.py          → game_library.py
│   └── launchbox_cache.py    → library_cache.py
├── services/
│   ├── launchbox_parser.py   → legacy_lb_importer.py (deprecated)
│   ├── launchbox_json_cache.py → game_library.py
│   └── image_scanner.py      → Keep (already neutral)
└── models/
    └── game.py               → Keep (already neutral)

frontend/src/
├── panels/
│   └── launchbox/            → game-library/
│       ├── LaunchBoxPanel.jsx → GameLibraryPanel.jsx
│       └── launchbox.css     → game-library.css
├── constants/
│   └── a_drive_paths.js      → Update API endpoints
└── App.jsx                   → Update route

gateway/
└── routes/
    └── launchboxProxy.js     → Add /api/library/* aliases

scripts/
├── build_launchbox_cache.py  → build_game_library.py
└── (new) import_from_screenscraper.py

configs/
└── teknoparrot-aliases.json  → Keep (platform-specific)

cache/
└── A:\.aa\launchbox_games.json → game_library.json
```

---

## Rollout Strategy

### Phase 1: Parallel Routes (Safe)
1. Add new `/api/library/*` routes that delegate to existing code
2. Keep `/api/launchbox/*` working
3. Test thoroughly

### Phase 2: Frontend Migration
1. Update frontend to use new endpoints
2. Rename components
3. Update UI labels

### Phase 3: Backend Cleanup
1. Remove legacy route aliases
2. Delete deprecated files
3. Final testing

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-12-07 | Migrate away from LaunchBox | IP concerns for commercial distribution |
| 2025-12-07 | Keep JSON as authoritative format | Already decoupled, minimal work |
| 2025-12-07 | Use ScreenScraper as alternative source | Open API, good coverage |

---

## Open Questions

1. **New panel name**: "Game Library", "Arcade Library", "Cabinet Library"?
2. **Artwork storage**: Keep in LaunchBox Images folder or move to `A:\Artwork`?
3. **Priority of importers**: ScreenScraper vs ROM Scanner vs Manual?

---

## Next Steps

1. [ ] Get user approval on this plan
2. [ ] Decide on new naming
3. [ ] Phase 1: Add parallel routes
4. [ ] Phase 2: Migrate frontend
5. [ ] Phase 3: Cleanup legacy code
