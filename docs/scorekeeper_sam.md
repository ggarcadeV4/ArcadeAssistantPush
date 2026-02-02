# ScoreKeeper Sam - Score Data Sources Analysis

**Analysis Date:** 2025-12-06
**Scope:** Read-only analysis of Sam's score data flow

---

## 1. Current Score Data Sources

### Frontend Functions (scorekeeperClient.js)

| Function | Backend Endpoint | Data Source |
|----------|-----------------|-------------|
| `getLeaderboard()` | `GET /api/launchbox/scores/leaderboard` → `GET /api/local/scorekeeper/leaderboard` | `state/scorekeeper/scores.jsonl` |
| `getByGame()` | `GET /api/launchbox/scores/by-game` → `GET /api/local/scorekeeper/by-game` | **NOT IMPLEMENTED** (endpoint missing in backend) |
| `submitScoreViaPlugin()` | `POST /api/launchbox/scores/submit` → `POST /api/local/scorekeeper/submit` | Writes to `state/scorekeeper/scores.jsonl` + Supabase mirror |
| `resolveGameByTitle()` | `POST /api/launchbox/resolve` | LaunchBox game metadata (title → GameID lookup) |

### Backend Endpoints (scorekeeper.py)

**Core Endpoints:**
- `GET /api/local/scorekeeper/leaderboard` (line 525)
  - **Reads from:** `state/scorekeeper/scores.jsonl` (JSONL append-only log)
  - **Returns:** Top scores sorted by value, filterable by game name
  - **Data format:** Each line is a JSON object with `{timestamp, game, player, score, ...}`

- `POST /api/local/scorekeeper/submit/apply` (line 606)
  - **Writes to:** `state/scorekeeper/scores.jsonl` (append mode)
  - **Mirrors to:** Supabase `scores` table (best-effort, non-blocking)
  - **Creates:** Scorekeeper snapshot backup before write

- `GET /api/local/scorekeeper/highscores/{game_id}` (line 1306)
  - **Reads from:** `A:\LaunchBox\Data\HighScores.json` (LaunchBox's built-in high score file)
  - **Returns:** Top scores for a specific LaunchBox game ID
  - **Data structure:** `{Games: [{Id, Title, Scores: [{Player, Score, Timestamp}]}]}`

**Advanced Leaderboard Endpoints (lines 1557-1658):**
- `GET /leaderboard/game/{game_id}` - Get leaderboard by exact game ID
- `GET /leaderboard/game?title=...` - Fuzzy match game by title
- `GET /leaderboard/house` - House stats (most played games, most active players)
- `GET /leaderboard/versus/{p1}/{p2}` - Compare two players
- `GET /tendencies/{player_name}` - Player's play history and favorites

**Advanced Leaderboard Data Source:**
- All leaderboard endpoints use `LeaderboardService` (backend/services/leaderboard.py)
- `LeaderboardService` reads from a **launches JSONL file** (not scores.jsonl)
- This tracks "who played what game" (launch events), NOT individual scores
- Used for questions like "Who plays Street Fighter most?" (play count, not high score)

---

## 2. LaunchBox Metadata Usage

**What LaunchBox Provides to Sam:**

1. **Game Identity Information** (via `/api/launchbox/resolve`):
   - Game title → LaunchBox GameID mapping
   - Platform, genre metadata
   - Used for: Fuzzy search ("Who has the high score in Street Fighter?")

2. **Built-in High Scores** (via `/highscores/{game_id}` endpoint):
   - **File:** `A:\LaunchBox\Data\HighScores.json`
   - **Contains:** LaunchBox's native high score tracking (if games write to it)
   - **Structure:** Game ID → List of {Player, Score, Timestamp} entries
   - **Limitation:** Only populated if LaunchBox plugins/games write scores to this file

**What LaunchBox Does NOT Provide:**

- **Per-player session scores:** Sam's JSONL files (`scores.jsonl`, launch logs) are separate from LaunchBox
- **Live score updates:** `HighScores.json` is static unless updated by LaunchBox plugins/emulators
- **Tournament tracking:** All tournament/bracket data lives in `state/scorekeeper/tournaments/*.json`

**Key Finding:**
Sam has **two separate score tracking systems**:
1. **LaunchBox HighScores.json** (read-only, via `/highscores/{game_id}`)
2. **Local JSONL files** (`state/scorekeeper/scores.jsonl` + Supabase mirror)

These systems do NOT sync automatically. Scores submitted via Sam's panel go to JSONL, NOT to LaunchBox's HighScores.json.

---

## 3. Answer to Core Question

**Can Scorekeeper Sam get live scores directly from LaunchBox metadata itself, without any additional files, plugins, or backend tables?**

**NO - not with the current code.**

**Explanation:**

1. **What LaunchBox metadata provides:**
   - LaunchBox metadata (platform XMLs in `A:\LaunchBox\Data\Platforms\`) contains game titles, platforms, genres, ROM paths
   - It does NOT contain individual player scores or high scores

2. **Where Sam's live scores actually come from:**
   - **Primary:** `state/scorekeeper/scores.jsonl` (local JSONL append-only log)
   - **Mirror:** Supabase `scores` table (cloud backup, best-effort sync)
   - **Optional:** `A:\LaunchBox\Data\HighScores.json` (if LaunchBox games/plugins populate it)

3. **What would be required for true "live scores from LaunchBox":**
   - A LaunchBox plugin or emulator integration that writes scores to `HighScores.json` after each game session
   - OR: A backend service that monitors emulator save states/score files and parses them into Sam's JSONL
   - OR: Direct emulator integration (e.g., MAME hi score files, RetroArch achievements) with a parser service

**Current State:**
Sam can READ LaunchBox's `HighScores.json` via the `/highscores/{game_id}` endpoint, but this file is only populated if external tools (LaunchBox plugins, emulator integrations) write to it. Sam's primary score tracking is independent, living in `state/scorekeeper/scores.jsonl`.

---

## 4. What "Live Scores from LaunchBox" Would Require (Conceptual)

To make Sam fully LaunchBox-native for score tracking:

1. **LaunchBox Plugin Integration:**
   - A LaunchBox C# plugin that listens for game exit events
   - Parses emulator-specific score files (MAME `.hi` files, RetroArch achievements, etc.)
   - Writes parsed scores to `A:\LaunchBox\Data\HighScores.json`
   - Sam's existing `/highscores/{game_id}` endpoint would then work for live data

2. **Emulator Score File Parsers:**
   - Backend service that monitors emulator-specific score locations:
     - MAME: `hi/` directory with `.hi` score files
     - RetroArch: Achievement/save state parsing
     - PCSX2: Memory card score parsing
   - Periodic polling or filesystem watching for new score data
   - Conversion to Sam's JSONL format or HighScores.json format

3. **Unified Score Aggregation:**
   - A backend worker that merges:
     - LaunchBox `HighScores.json` (if available)
     - Sam's local `scores.jsonl` (manual submissions)
     - Emulator-native score files (parsed)
   - Exposes a unified `/leaderboard` endpoint combining all sources

4. **Real-Time Event Bus:**
   - Integration with the existing bus events system (`bus_events.py`)
   - Emulators broadcast score updates on game exit
   - Sam subscribes to score events and updates JSONL in real-time

**Key Constraint:**
All of the above require **external integration work** beyond reading LaunchBox metadata. LaunchBox's XML metadata files do not contain score data - scores must come from runtime game sessions or external tracking systems.

---

## Files Inspected

- `frontend/src/services/scorekeeperClient.js` - Frontend API client
- `frontend/src/panels/scorekeeper/ScoreKeeperPanel.jsx` - Sam's UI component
- `backend/routers/scorekeeper.py` - Backend score/tournament endpoints
- `backend/services/leaderboard.py` - Launch log analysis service
- `gateway/routes/launchboxScores.js` - Gateway proxy to backend

---

## Missing Implementation

**CRITICAL:** The `GET /api/launchbox/scores/by-game` endpoint is called by the frontend (`scorekeeperClient.js:47`) but is NOT implemented in the backend. The gateway proxies to `/api/local/scorekeeper/by-game`, but this route does not exist in `scorekeeper.py`. This will cause 404 errors when `getByGame()` is called.

**Recommendation:** Either remove the `getByGame()` call from the frontend, or implement the missing backend endpoint that filters `scores.jsonl` by game ID.

---

## 5. Can Sam Answer "Who's Better at GAME X?"

**YES - In principle, Sam can already answer this question with existing data.**

### Data Available Per Score Entry

**scores.jsonl format** (lines 572-584 in scorekeeper.py):
```json
{
  "timestamp": "2025-12-06T12:34:56.789Z",
  "game": "Street Fighter II",
  "player": "Dad",
  "score": 45000,
  "player_userId": "user_abc123",
  "player_source": "profile",
  "publicLeaderboardEligible": true
}
```

**autosubmit format** (lines 1450-1459 in scorekeeper.py):
```json
{
  "game_id": "12345-abcd",
  "game_title": "Street Fighter II",
  "player": "Dad",
  "score": 45000,
  "timestamp": "2025-12-06T12:34:56.789Z",
  "session_id": "session_xyz",
  "tournament_id": null,
  "source": "launchbox_autosubmit"
}
```

**HighScores.json format** (lines 1363-1368 in scorekeeper.py):
```json
{
  "Games": [
    {
      "Id": "12345-abcd",
      "Title": "Street Fighter II",
      "Scores": [
        {"Player": "Dad", "Score": 45000, "Timestamp": "2025-12-06"}
      ]
    }
  ]
}
```

### Backend Logic Already Present

**Per-game score aggregation:**
- `GET /api/local/scorekeeper/leaderboard?game={game_name}` (line 525-556)
  - Reads all scores from `scores.jsonl`
  - Filters by `game` field if provided
  - Sorts by `score` descending
  - Returns top N scores with player names
  - **This already groups scores per game and ranks players**

- `GET /api/local/scorekeeper/highscores/{game_id}` (line 1306-1404)
  - Reads LaunchBox `HighScores.json`
  - Filters by `game_id`
  - Returns sorted list with `{player, score, rank}`
  - **This also provides per-game, per-player rankings**

- `/autosubmit` leaderboard rank calculation (lines 1489-1513)
  - Filters `scores.jsonl` by `game_id`
  - Sorts all scores descending
  - Computes rank for submitted score
  - **Demonstrates the code already knows how to rank players per game**

**Player comparison:**
- `GET /leaderboard/versus/{p1}/{p2}?game_id={id}` (lines 1642-1658)
  - Uses `LeaderboardService` to compare two players
  - Can filter by specific game
  - Returns who has more plays (not scores, but infrastructure exists)

### What's Needed for "Who's Better?"

**Already have:**
- ✅ Per-player scores tagged with `player` field
- ✅ Per-game scores tagged with `game` or `game_id` field
- ✅ Backend endpoint that filters by game and sorts by score
- ✅ Logic to compute rankings per game

**Missing for complete "who's better" feature:**
- ❌ AI/UX wiring to call `GET /leaderboard?game={name}` when user asks
- ❌ Natural language query parsing ("Who's better at Street Fighter?" → extract game name)
- ❌ Response formatting in Sam's voice ("Dad is crushing it with 45,000 points, Mom's at 38,000!")

### Conclusion

**Sam can answer "who's better at GAME X" WITHOUT touching emulator or LaunchBox metadata code.** All required data exists in `scores.jsonl`, and the backend endpoint at `GET /api/local/scorekeeper/leaderboard?game={name}` already filters, sorts, and ranks players per game. The only work needed is frontend/AI wiring to:

1. Parse user's natural language question to extract game name
2. Call the existing `/leaderboard?game={name}` endpoint
3. Format the response in Sam's referee persona

No emulator integration, no LaunchBox metadata parsing, no new backend logic required for the core "who's better?" question.
