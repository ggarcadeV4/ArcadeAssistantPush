# LaunchBox LoRa AI Integration

**Created**: 2025-10-06
**Status**: ✅ Fully Implemented

## Overview

The LaunchBox LoRa panel now has full AI integration with Claude 3.5 Sonnet, including tool-calling capabilities. Users can chat naturally with LoRa to discover games, filter libraries, get recommendations, and launch titles.

## Architecture

### Component Flow:
```
Frontend (LaunchBoxPanel.jsx)
    ↓ Chat Message
Gateway (/api/launchbox/chat)
    ↓ Claude API with Tools
Claude 3.5 Sonnet
    ↓ Tool Calls
Tool Executors (launchbox.js)
    ↓ Backend API Calls
FastAPI (/api/launchbox/*)
    ↓ LaunchBox XML Data
Response → User
```

## Files Created/Modified

### New Files:
1. **`gateway/tools/launchbox.js`** (360 lines)
   - 7 AI tool definitions
   - Tool execution functions
   - FastAPI endpoint wrappers

2. **`gateway/routes/launchboxAI.js`** (262 lines)
   - `/api/launchbox/chat` endpoint
   - Context-aware system prompt builder
   - Tool result processor

### Modified Files:
1. **`gateway/server.js`**
   - Added launchboxAI route import
   - Registered `/api/launchbox/chat` endpoint

2. **`frontend/src/panels/launchbox/LaunchBoxPanel.jsx`**
   - Updated `sendMessage()` to call AI endpoint
   - Added context passing (filters, stats, game count)
   - Improved error handling

## AI Tools Available

### 1. filter_games
**Purpose**: Filter game library by genre, decade, or platform
**Parameters**:
- `genre` (string, optional): e.g., "Fighting", "Maze"
- `decade` (integer, optional): e.g., 1980, 1990
- `platform` (string, optional): e.g., "Arcade", "NES"
- `limit` (integer, optional): Max results (default: 50)

**Example User Query**: "Show me fighting games from the 90s"

### 2. search_games
**Purpose**: Search for games by title (partial match)
**Parameters**:
- `query` (string, required): Search term

**Example User Query**: "Find Street Fighter"

### 3. get_random_game
**Purpose**: Get random game suggestion with optional filters
**Parameters**:
- `genre` (string, optional)
- `platform` (string, optional)

**Example User Query**: "Surprise me with a shooter"

### 4. launch_game
**Purpose**: Launch a game by ID
**Parameters**:
- `game_id` (string, required): UUID from search/filter results

**Example User Query**: "Launch Pac-Man"
*Note: AI will search first to get game_id*

### 5. get_library_stats
**Purpose**: Get library statistics
**Example User Query**: "How many games do I have?"

### 6. get_available_genres
**Purpose**: List all genres in library
**Example User Query**: "What genres are available?"

### 7. get_available_platforms
**Purpose**: List all platforms in library
**Example User Query**: "What platforms do you support?"

## Context Awareness

The AI receives real-time context about the UI state:

```javascript
context: {
  currentFilters: {
    genre: "Fighting",      // Active genre filter
    decade: "1990s",        // Active decade filter
    sortBy: "Last Played"   // Current sort order
  },
  availableGames: 15,       // Games currently displayed
  stats: {
    total_games: 15,
    platforms_count: 4,
    genres_count: 7,
    is_mock_data: true
  }
}
```

This allows the AI to:
- Acknowledge active filters ("I see you're already filtering by Fighting games...")
- Suggest refining searches based on current results
- Know the library size and capabilities

## Testing the Integration

### Prerequisites:
1. **Start all services**:
   ```bash
   # Terminal 1: Backend
   npm run dev:backend

   # Terminal 2: Gateway
   npm run dev:gateway

   # Terminal 3: Frontend
   npm run dev:frontend
   ```

2. **Verify API key is set** in `.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

### Test Queries:

#### Basic Conversation:
```
User: "Hello!"
Expected: Friendly greeting from LoRa

User: "What games do you have?"
Expected: Uses get_library_stats, reports totals
```

#### Filtering:
```
User: "Show me fighting games"
Expected: Uses filter_games with genre="Fighting", lists results

User: "Show me arcade games from the 1980s"
Expected: Uses filter_games with platform="Arcade" and decade=1980
```

#### Search:
```
User: "Find Pac-Man"
Expected: Uses search_games with query="Pac-Man", returns match

User: "Do you have Street Fighter?"
Expected: Searches, reports if found with year/genre
```

#### Recommendations:
```
User: "What should I play?"
Expected: Uses get_random_game, suggests title with reasoning

User: "Surprise me with a maze game"
Expected: Uses get_random_game with genre="Maze"
```

#### Launch (Not Yet Functional - Mock Data):
```
User: "Launch Galaga"
Expected: Searches for Galaga, attempts launch (will fail gracefully in mock mode)
```

#### Discovery:
```
User: "What genres are available?"
Expected: Uses get_available_genres, lists all

User: "What platforms do you support?"
Expected: Uses get_available_platforms, lists all
```

## Debugging

### Check Gateway Logs:
```bash
# Look for these log lines:
[LaunchBox AI] User message: ...
[LaunchBox AI] Context: {...}
[LaunchBox AI] Claude response: {...}
[LaunchBox AI] Tool call: filter_games {...}
```

### Check Frontend Console:
```javascript
// Open DevTools → Console, look for:
[LaunchBox] AI used tools: [...]
AI chat error: ...
```

### Test Direct API Call:
```bash
curl -X POST http://localhost:8787/api/launchbox/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show me fighting games",
    "context": {
      "stats": {"total_games": 15}
    }
  }'
```

## Known Limitations (Mock Mode)

1. **Game launching will fail** - No actual ROMs or emulators configured
2. **Limited dataset** - Only 15 mock games (vs 14k+ on A: drive)
3. **No play history** - `lastPlayed` dates are hardcoded
4. **No images** - Game covers not displayed

These will work when `AA_DRIVE_ROOT=A:\` is set and backend restarts.

## What's Next?

Now that AI is connected, you'll naturally discover missing tools as you use the system:

### Likely Next Tools:
- `get_game_details(game_id)` - Full metadata for a single game
- `get_recent_games(limit)` - Recently played games
- `get_popular_games()` - Most played games
- `get_games_by_year(year)` - All games from specific year
- `get_similar_games(game_id)` - Recommendations based on a game
- `update_favorite(game_id, is_favorite)` - Toggle favorites

### UI Enhancements:
- Visual feedback when AI uses tools (loading spinner, tool badges)
- Auto-apply filters when AI suggests them
- Click game titles in AI responses to see details
- Voice input integration (mic button already present)

## Success Metrics

✅ Chat sidebar functional
✅ AI receives context
✅ Tools execute successfully
✅ Responses are contextual
✅ Error handling graceful
✅ No white screen crashes

## Session Summary

- **Development Time**: ~2 hours
- **Lines of Code**: ~700 (new + modified)
- **Tools Implemented**: 7
- **API Endpoints**: 1 new (`/api/launchbox/chat`)
- **Test Queries**: 10+ categories

Ready for real-world testing! 🎮
