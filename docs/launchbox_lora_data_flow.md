# LaunchBox LoRa Data Flow Documentation

> **Purpose**: Map LoRa's data requirements for a future JSON cache refactor.  
> **Created**: 2025-12-07 | **Status**: Discovery Complete

---

## Section 1 – Current LoRa Data Flow

### Frontend → Backend Flow

```
LaunchBoxPanel.jsx
    ↓
    fetch(`/api/launchbox/games?platform=X&limit=20000`)
    fetch(`/api/launchbox/platforms`)
    fetch(`/api/launchbox/genres`)
    fetch(`/api/launchbox/stats`)
    ↓
Gateway (port 8787)
    ↓ proxies to
FastAPI Backend (port 8888)
    ↓
launchbox.py router → LaunchBoxParser → XML files + ImageScanner
```

### API Endpoints Used by LoRa

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/launchbox/games` | GET | Game list with filters |
| `/api/launchbox/platforms` | GET | Platform dropdown |
| `/api/launchbox/genres` | GET | Genre dropdown |
| `/api/launchbox/stats` | GET | Cache statistics |
| `/api/launchbox/image/{id}` | GET | Game artwork (serves file) |
| `/api/launchbox/launch/{id}` | POST | Launch game |
| `/api/launchbox/random` | GET | Random game suggestion |

### Fields Used by GameCard Component

**From `/api/launchbox/games` response:**

| Field | Type | Used For |
|-------|------|----------|
| `id` | string | Image URL, launch action |
| `title` | string | Display name |
| `platform` | string | Meta info display |
| `genre` | string | Genre badge |
| `year` | int | Year display |
| `lastPlayed` | datetime | "Last played" meta |
| `sessionTime` | string | Session duration meta |
| `playCount` | int | Play count meta |

**Image Retrieval:**
- Frontend calls: `${GATEWAY}/api/launchbox/image/${game.id}`
- Backend looks up game by ID, returns first available from:
  1. `clear_logo_path` (preferred)
  2. `box_front_path`
  3. `screenshot_path`

### Backend Data Sources

**LaunchBoxParser** (`backend/services/launchbox_parser.py`):
- Parses XML files from `A:\LaunchBox\Data\Platforms\*.xml`
- Extracts: `ID`, `Title`, `Platform`, `Genre`, `Developer`, `Publisher`, `ReleaseDate`, `ApplicationPath`
- Attaches image paths via **ImageScanner**

**ImageScanner** (`backend/services/image_scanner.py`):
- Pre-scans `A:\LaunchBox\Images\{Platform}\{ImageType}\*`
- Uses fuzzy matching to handle filename sanitization mismatches
- Returns paths for: `clear_logo`, `box_front`, `screenshot`

**Game Model** (`backend/models/game.py`):
```python
class Game:
    id: str                    # LaunchBox ID
    title: str                 # Game title
    platform: str              # Platform name
    genre: Optional[str]       # Primary genre
    developer: Optional[str]
    publisher: Optional[str]
    year: Optional[int]
    rom_path: Optional[str]    # Path to ROM
    application_path: Optional[str]
    box_front_path: Optional[str]      # ← Image path
    screenshot_path: Optional[str]     # ← Image path
    clear_logo_path: Optional[str]     # ← Image path
    categories: Optional[List[str]]
    play_count: int = 0
    last_played: Optional[datetime]
```

---

## Section 2 – JSON Cache Requirements

### Minimal JSON Schema for Cached Game Record

```jsonc
{
  // Core identifiers (REQUIRED)
  "id": "12345-abcd-6789",
  "title": "Street Fighter II",
  "sort_title": "street fighter ii",
  
  // Metadata (REQUIRED for LoRa UI)
  "platform": "Arcade",
  "year": 1991,
  "genre": "Fighting",
  
  // Artwork paths (REQUIRED for image endpoint)
  "clear_logo_path": "A:\\LaunchBox\\Images\\Arcade\\Clear Logo\\Street Fighter II-01.png",
  "box_front_path": "A:\\LaunchBox\\Images\\Arcade\\Box - Front\\Street Fighter II-01.png",
  "screenshot_path": "A:\\LaunchBox\\Images\\Arcade\\Screenshot - Gameplay\\Street Fighter II-01.png",
  
  // Launch info (REQUIRED for launching)
  "rom_path": "A:\\Roms\\MAME\\sf2.zip",
  "application_path": "A:\\Roms\\MAME\\sf2.zip",
  
  // Optional metadata (future use)
  "developer": "Capcom",
  "publisher": "Capcom",
  "categories": ["Fighting", "Competitive"],
  
  // Play stats (populated at runtime from Supabase, not in cache)
  // "play_count", "last_played", "session_time" - NOT CACHED
}
```

### Field Mapping: Today → Cache

| LoRa Needs | Current Source | Cache Field |
|------------|----------------|-------------|
| `game.id` | XML `<ID>` | `id` |
| `game.title` | XML `<Title>` | `title` |
| `game.platform` | XML `<Platform>` | `platform` |
| `game.genre` | XML `<Genre>` | `genre` |
| `game.year` | XML `<ReleaseDate>` | `year` |
| Image lookup | ImageScanner | `clear_logo_path`, `box_front_path`, `screenshot_path` |
| Launch | XML `<ApplicationPath>` | `rom_path`, `application_path` |

### Play Stats Note

`lastPlayed`, `sessionTime`, `playCount` are **NOT** stored in XML or cache.  
These come from Supabase telemetry (future integration) or are mocked.  
The cache should NOT include these - they're runtime-joined.

---

## Section 3 – Refactor Strategy (High-Level Only)

### Goals
1. Eliminate runtime XML parsing
2. Faster cold startup (JSON load vs XML parse)
3. Maintain 100% LoRa compatibility (same fields, same artwork)

### Proposed Steps

1. **Unify routes under `/api/launchbox`**
   - Remove `/api/local/launchbox/*` confusion
   - Gateway proxies all `/api/launchbox/*` to FastAPI

2. **Create cache builder script**
   - Parses all LaunchBox XML files
   - Runs ImageScanner to attach image paths
   - Writes `launchbox_games_cache.json` under `AA_DRIVE_ROOT/.aa/`

3. **Modify `/api/launchbox/games` to read from JSON**
   - Load `launchbox_games_cache.json` on startup (or lazy-load)
   - Filter/search operates on in-memory list
   - No XML parsing at runtime

4. **Keep `/api/launchbox/image/{id}` unchanged**
   - Still looks up game by ID from cache
   - Still serves file from `clear_logo_path` / `box_front_path` / `screenshot_path`
   - Image paths in cache point to actual files

5. **Provide "Refresh Library" action**
   - Triggers cache builder to re-parse XML → JSON
   - Updates cache file on disk
   - Invalidates in-memory cache

6. **Preserve all artwork fields in cache output**
   - `clear_logo_path`, `box_front_path`, `screenshot_path` MUST be present
   - These are absolute paths to LaunchBox image files
   - ImageScanner already handles fuzzy matching at build time

7. **Add cache metadata**
   - Include `version`, `generated_at`, `game_count`, `platform_count`
   - Enables staleness detection and validation

8. **Optional: Compress cache for storage**
   - JSON can be large (14k+ games)
   - Consider gzip compression or split by platform

---

## Answer: Can LoRa Continue to Work with JSON Cache?

**Yes, with this cache schema.**

The proposed cache includes all fields LoRa currently relies on:
- ✅ `id` - for image URL and launch
- ✅ `title`, `platform`, `genre`, `year` - for display
- ✅ `clear_logo_path`, `box_front_path`, `screenshot_path` - for artwork
- ✅ `rom_path`, `application_path` - for launching

**Not included (intentionally):**
- `play_count`, `last_played`, `session_time` - these are runtime/Supabase data, not XML-sourced

If LoRa needs play stats, they would be joined at query time from Supabase, not stored in the game cache.
