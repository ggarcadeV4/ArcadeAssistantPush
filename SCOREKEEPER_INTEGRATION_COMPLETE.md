# ScoreKeeper Sam Integration - COMPLETE ✅

## Overview

Complete integration between LaunchBox LoRa, Vicky Voice, and ScoreKeeper Sam for tournament management, player tracking, and "house honesty" leaderboards.

## Architecture

```
┌─────────────────┐
│  Vicky Voice    │ Creates sessions with player rosters
│   (Frontend)    │ "Start tournament with Dad, Mom, Sister, and me"
└────────┬────────┘
         │ POST /api/sessions/create
         ▼
┌─────────────────┐
│ Session Manager │ Tracks active sessions, player rosters
│   (Backend)     │ Stores: session_id, owner, players[]
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ LaunchBox LoRa  │ Launches games with player context
│   (Frontend)    │ Sends: x-user-profile, x-session-owner
└────────┬────────┘
         │ POST /api/launchbox/launch/{game_id}
         ▼
┌─────────────────┐
│  Launch Logger  │ Logs every game launch with player info
│   (Backend)     │ Writes to: state/scorekeeper/launches.jsonl
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Leaderboard Svc │ Analyzes launch logs
│   (Backend)     │ Builds rankings, stats, comparisons
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ScoreKeeper Sam │ Answers leaderboard questions
│   (Frontend)    │ "Who's #1 at Street Fighter?"
└─────────────────┘
```

## Data Flow

### 1. Session Creation (Vicky Voice → Session Manager)

**User says:** "Start a tournament with Dad, Mom, Sister, and me"

**Flow:**
```
Vicky Voice
  ↓ POST /api/sessions/create
  {
    "owner_id": "dallas",
    "owner_name": "Dallas",
    "players": [
      {"id": "dad", "name": "Dad", "position": 1},
      {"id": "mom", "name": "Mom", "position": 2},
      {"id": "sister", "name": "Sister", "position": 3},
      {"id": "dallas", "name": "Dallas", "position": 4}
    ]
  }
  ↓
Session Manager
  ↓ Creates session
  ↓ Saves to: state/scorekeeper/sessions.json
  ↓ Returns session_id: "abc-123"
  ↓
Vicky Voice
  ↓ Stores session_id in state
  ↓ Tells user: "Tournament created! Dallas is session owner."
```

### 2. Game Launch (LaunchBox LoRa → Launch Logger)

**User says:** "Launch Street Fighter"

**Flow:**
```
LaunchBox LoRa
  ↓ POST /api/launchbox/launch/{game_id}
  Headers: {
    "x-user-profile": "dad",
    "x-user-name": "Dad",
    "x-session-owner": "dallas"
  }
  ↓
Backend Launch Handler
  ↓ Launches game
  ↓ Calls _log_launch_event()
  ↓
Launch Logger
  ↓ Appends to: state/scorekeeper/launches.jsonl
  {
    "timestamp": "2025-12-03T10:00:00Z",
    "game_id": "abc-123",
    "title": "Street Fighter II",
    "platform": "Arcade",
    "player_id": "dad",
    "player_name": "Dad",
    "session_owner": "dallas",
    "success": true
  }
```

### 3. Leaderboard Query (ScoreKeeper Sam → Leaderboard Service)

**User asks:** "Who's #1 at Street Fighter?"

**Flow:**
```
ScoreKeeper Sam
  ↓ GET /scorekeeper/leaderboard/game?title=Street Fighter
  ↓
Leaderboard Service
  ↓ Reads: state/scorekeeper/launches.jsonl
  ↓ Filters for "Street Fighter" games
  ↓ Counts by player_id
  ↓ Sorts by play_count
  ↓ Returns leaderboard
  [
    {"player_id": "dad", "play_count": 45, "rank": 1},
    {"player_id": "mom", "play_count": 23, "rank": 2}
  ]
  ↓
ScoreKeeper Sam
  ↓ Formats response
  ↓ Tells user: "Dad is #1 with 45 plays! Mom is second with 23."
```

## File Structure

```
A:\
├── state/
│   └── scorekeeper/
│       ├── launches.jsonl          # All game launches (Phase 1)
│       ├── sessions.json           # Active sessions (Phase 2)
│       ├── scores.jsonl            # Tournament scores
│       └── tournaments/            # Tournament data
│
├── frontend/
│   ├── public/
│   │   └── profiles/
│   │       ├── dad/
│   │       │   └── tendencies.json # Dad's preferences
│   │       ├── mom/
│   │       │   └── tendencies.json
│   │       └── viki/
│   │           └── tendencies.json
│   │
│   └── src/
│       └── panels/
│           ├── launchbox/
│           │   └── LaunchBoxPanel.jsx  # LoRa (sends player headers)
│           ├── voice/
│           │   └── VoicePanel.jsx      # Vicky (creates sessions)
│           └── scorekeeper/
│               └── ScoreKeeperPanel.jsx # Sam (queries leaderboards)
│
└── backend/
    ├── services/
    │   ├── session_manager.py      # Phase 2: Session tracking
    │   └── leaderboard.py          # Phase 3: Leaderboard analysis
    │
    └── routers/
        ├── launchbox.py            # Phase 1: Launch logging
        ├── sessions.py             # Phase 2: Session API
        └── scorekeeper.py          # Phase 3: Leaderboard API
```

## API Reference

### Session Management

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/sessions/create` | POST | Create new session |
| `/api/sessions/{session_id}` | GET | Get session info |
| `/api/sessions/player/{player_id}` | GET | Get active session for player |
| `/api/sessions/` | GET | List all active sessions |
| `/api/sessions/end` | POST | End a session |
| `/api/sessions/{session_id}/log-game` | POST | Log game to session |

### Leaderboards

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/scorekeeper/leaderboard/player/{player_id}/top-games` | GET | Player's top games |
| `/scorekeeper/leaderboard/game/{game_id}` | GET | Game leaderboard (by ID) |
| `/scorekeeper/leaderboard/game?title=X` | GET | Game leaderboard (by title) |
| `/scorekeeper/leaderboard/house` | GET | House statistics |
| `/scorekeeper/leaderboard/versus/{p1}/{p2}` | GET | Player comparison |

## Usage Examples

### Example 1: Family Tournament Night

**Setup (Vicky Voice):**
```
User: "Start a tournament with Dad, Mom, Sister, and me"
Vicky: "Creating tournament..."
→ POST /api/sessions/create
Vicky: "Tournament created! You're the session owner, Dallas."
```

**Play (LaunchBox LoRa):**
```
Dad: "Launch Street Fighter"
LoRa: "Launching Street Fighter II..."
→ POST /api/launchbox/launch/{game_id}
   Headers: x-user-profile=dad, x-session-owner=dallas
→ Logged to launches.jsonl with session context
```

**Results (ScoreKeeper Sam):**
```
User: "Who won?"
Sam: "Let me check... Dad played 3 matches, Mom played 2.
      Based on play count, Dad is the champion!"
→ GET /scorekeeper/leaderboard/versus/dad/mom
```

### Example 2: House Leaderboard

**Query (ScoreKeeper Sam):**
```
User: "Who's the best at fighting games in this house?"
Sam: "Checking the records..."
→ GET /scorekeeper/leaderboard/house
Sam: "Dad is the fighting game champion with 45 Street Fighter plays!
      Mom is second with 23 plays."
```

### Example 3: Personal Stats

**Query (LaunchBox LoRa or ScoreKeeper Sam):**
```
User: "What are my top games?"
→ GET /scorekeeper/leaderboard/player/dad/top-games?limit=10
Response: [
  {"title": "Street Fighter II", "play_count": 45},
  {"title": "Galaga", "play_count": 32},
  {"title": "Ms. Pac-Man", "play_count": 28}
]
```

## The "Top Billing" Concept

**Session Owner = Primary Addressee**

When Dallas creates a tournament:
- Dallas is the **session owner**
- ScoreKeeper Sam addresses **Dallas** directly
- But tracks scores for **all players** (Dad, Mom, Sister, Dallas)

**Example:**
```
Sam: "Alright Dallas, your tournament is ready!
      Round 1: Dad vs Mom
      Round 2: Sister vs you
      
      Ready to start?"
```

**Why this matters:**
- Whoever creates the session gets "top billing"
- Sam talks TO them
- But everyone's scores are tracked individually
- Maintains social hierarchy while being fair

## Integration Points

### LaunchBox LoRa → Session Manager
- Sends `x-session-owner` header with every launch
- Auto-assigns launches to active session
- Tracks which player launched which game

### Vicky Voice → Session Manager
- Creates sessions with player rosters
- Sets session owner ("top billing")
- Manages tournament brackets

### ScoreKeeper Sam → Leaderboard Service
- Queries player rankings
- Answers "who's the best" questions
- Provides house statistics
- Settles disputes with data

## What This Enables

### ✅ Tournament Management
- Track who's playing
- Know who started the tournament
- Manage player rosters
- Session-based scoring

### ✅ House Honesty
- Objective rankings
- No arguments about "who's better"
- Data-driven leaderboards
- Historical tracking

### ✅ Player Insights
- See your own top games
- Compare with others
- Track gaming habits
- Personal statistics

### ✅ Social Features
- Family game nights
- Friend tournaments
- Competitive challenges
- Bragging rights

## Testing

### Test Session Creation
```bash
curl -X POST http://localhost:8000/api/sessions/create \
  -H "Content-Type: application/json" \
  -d '{
    "owner_id": "dallas",
    "owner_name": "Dallas",
    "players": [
      {"id": "dad", "name": "Dad", "position": 1},
      {"id": "mom", "name": "Mom", "position": 2}
    ]
  }'
```

### Test Leaderboard Query
```bash
# Player's top games
curl http://localhost:8000/scorekeeper/leaderboard/player/dad/top-games

# Game leaderboard
curl "http://localhost:8000/scorekeeper/leaderboard/game?title=Street%20Fighter"

# House stats
curl http://localhost:8000/scorekeeper/leaderboard/house
```

### Test Launch with Player Context
```bash
curl -X POST http://localhost:8000/api/launchbox/launch/{game_id} \
  -H "x-user-profile: dad" \
  -H "x-user-name: Dad" \
  -H "x-session-owner: dallas" \
  -H "x-panel: launchbox"
```

## Maintenance

### Cleanup Old Sessions
```bash
curl -X POST http://localhost:8000/api/sessions/cleanup?max_age_hours=24
```

### View Launch Logs
```bash
# Last 10 launches
tail -n 10 A:\state\scorekeeper\launches.jsonl

# Count total launches
wc -l A:\state\scorekeeper\launches.jsonl
```

### Backup Data
```bash
# Backup launches
cp A:\state\scorekeeper\launches.jsonl A:\backups\20251203\

# Backup sessions
cp A:\state\scorekeeper\sessions.json A:\backups\20251203\
```

## Future Enhancements

### Potential Additions
- **Score tracking**: Actual game scores, not just play counts
- **Time tracking**: Session duration, total playtime
- **Achievements**: "First to 100 plays", "Variety champion"
- **Trends**: "You're playing more fighting games this week"
- **Recommendations**: "Based on your history, try..."
- **Challenges**: "Can you beat Dad's record?"

### Integration Opportunities
- **LED Blinky**: Flash LEDs for leaderboard changes
- **Console Wizard**: Suggest controller configs based on top games
- **Dewey**: "Tell me about my gaming habits"

## Summary

**All 4 Phases Complete! ✅**

1. ✅ **Phase 1**: Launch event logging with player tracking
2. ✅ **Phase 2**: Session owner tracking system
3. ✅ **Phase 3**: Leaderboard query endpoints
4. ✅ **Phase 4**: Complete integration documentation

**Total Implementation Time:** ~2 hours
**Confidence Level:** 9/10 across all phases
**Status:** Production ready

**What You Can Do Now:**
- Create tournaments with Vicky Voice
- Track who plays what with LaunchBox LoRa
- Answer "who's the best" with ScoreKeeper Sam
- Maintain house honesty with objective data

---

**Integration Complete!** 🎉
**Date:** December 3, 2025
**Version:** 1.0.0
