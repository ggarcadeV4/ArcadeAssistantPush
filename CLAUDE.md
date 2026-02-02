# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Core Development
- **Start development stack**: `npm run dev` (starts gateway + backend concurrently)
- **Frontend only**: `npm run dev:frontend` (Vite dev server)
- **Gateway only**: `npm run dev:gateway` (Node.js Express server)
- **Backend only**: `npm run dev:backend` (FastAPI with uvicorn)

### Building & Testing
- **Build frontend**: `npm run build:frontend`
- **Install all dependencies**: `npm run install:all` (root, frontend, and backend)
- **Test**: `npm test` (Jest with experimental VM modules)
- **Watch tests**: `npm run test:watch`
- **Lint frontend**: `cd frontend && npm run lint` (requires ESLint configuration)

### Health Checks
- **Gateway health**: `npm run test:health` (curl localhost:8787/api/health)
- **Backend health**: `npm run test:fastapi` (curl localhost:8888/health)

### Agent System Commands
- **Validate agent environment**: `node cloud_code/claude_boot.js` or `python cloud_code/claude_boot.py`
- **Check agent compliance**: Review logs in `/logs/agent_boot/` for validation results

## Architecture Overview

### Three-Tier Architecture
1. **Frontend** (React + Vite): UI panels and components at localhost:8787
2. **Gateway** (Node.js + Express): BFF layer with routing, AI integration, config management
3. **Backend** (FastAPI + Python): Local file operations, emulator integration

### A: Drive Reference
- **Complete A: Drive Map**: See `A_DRIVE_MAP.md` for comprehensive directory structure, file inventory, and integration notes
- **LaunchBox Root**: `A:\LaunchBox` (NOT `A:\Arcade Assistant\LaunchBox`)
- **Platform XMLs**: `A:\LaunchBox\Data\Platforms\` (53 files containing complete game metadata)
- **MAME ROMs**: `A:\Roms\MAME\` (14,233 .zip files)
- **BIOS Files**: `A:\Bios\system\` (586 files)
- **Critical Finding**: CLI_Launcher.exe NOT FOUND at expected ThirdParty location (alternative launch methods required)

### Key Architectural Patterns

**Request Flow**: Frontend → Gateway (localhost:8787) → Backend (localhost:8888)

**AI Integration**: Gateway handles AI chat via `/api/ai/chat` with Anthropic/OpenAI adapters, includes backoff retry logic and SSE support

**Config Management**: Safe config editing pipeline with preview/apply/revert workflow, automatic backups to `/backups/YYYYMMDD`, and whitelist-based validation

**Panel System**: Modular React panels in `frontend/src/panels/` with shared Panel Kit (`_kit/`) providing reusable components like `PanelShell`, `DiffPreview`, `ApplyBar`, and `useAIAction` hook

**Security Headers**: All gateway requests use `x-scope` headers for operation scoping (state/config), `x-device-id` for tracking

### Data Flow & State Management
- **WebSocket Manager**: LED Blinky uses dedicated WebSocket class for device communication
- **Audio WebSocket**: Real-time audio streaming at `ws://localhost:8787/ws/audio` for voice recording (see Voice & Audio Integration section)
- **AI Client**: Frontend service with 429 retry logic and device ID headers
- **Config Backups**: Automatic timestamped backups with JSONL changelog in `/logs/changes.jsonl`
- **Session Logging**: Rolling session log maintained in `README.md` with mandatory closure entries

## Key Technologies & Dependencies

### Frontend Stack
- React 18 + Vite
- React Router for navigation
- ESLint for code quality (configuration needed)
- Custom CSS with design system (CSS custom properties)

### Gateway Stack
- Express.js with CORS locked to localhost
- WebSocket support via 'ws' library
- AI adapters for Anthropic/OpenAI APIs
- Config management with backup/restore capabilities

### Backend Stack
- FastAPI with automatic OpenAPI docs (available at `http://localhost:8888/docs`)
- Uvicorn ASGI server
- Pydantic for data validation
- Python-dotenv for environment management

### System Requirements
- **Node.js**: >=18.0.0
- **Python**: >=3.10.0

## Environment Configuration

Required environment variables (see `.env.example`):
- `ANTHROPIC_API_KEY` or `CLAUDE_API_KEY` for AI features
- `OPENAI_API_KEY` for GPT integration
- `ELEVENLABS_API_KEY` for text-to-speech voice synthesis
- `AA_DRIVE_ROOT` for local operations root path
- `PORT=8787` for gateway

### Backend Port Configuration
⚠️ **Important**: Backend port varies by launch method:
- Via `npm run dev:backend` (package.json script): **Port 8000**
- Via `python backend/app.py` (direct execution): **Port 8888**
- Set `FASTAPI_URL` in `.env` to match your launch method
- Default `.env.example` uses `http://localhost:8888`

## Development Guidelines

### Panel Development
- Use Panel Kit components for consistent UI/UX
- Follow the established pattern: `PanelShell` wrapper, `DiffPreview` for config changes, `ApplyBar` for actions
- LED panels use CSS classes instead of inline styles for performance
- All panels should implement accessibility features (ARIA labels, keyboard navigation)

### Code Organization
- Frontend components in `frontend/src/components/`
- Panel-specific code in `frontend/src/panels/[panel-name]/`
- Gateway routes in `gateway/routes/`
- Backend routers in `backend/routers/`
- Shared utilities in respective `utils/` directories

### Security & Configuration
- Never commit secrets; use `.env` with `.env.example` template
- All file operations must go through Gateway → Backend with proper scoping
- Config changes require preview before apply, with automatic backup creation
- Only write to sanctioned paths (`/configs`, `/state`, `/backups`, `/logs`, `/emulators`)

### Performance Optimization
- LED Blinky panel: Use CSS classes instead of inline styles (1,600+ style objects caused render bottleneck)
- WebSocket managers should be extracted outside components to prevent recreation
- Use React.memo, useCallback, and useMemo for expensive operations
- Button configurations should be memoized with useMemo

## Agent Orchestration System

### Required Agent Validation
Before any task execution, agents must validate their environment using `cloud_code/claude_boot.js` or `claude_boot.py`. Required files:
- `docs/PROMETHEA_GUI_STYLE_GUIDE.md` - GUI layout constraints
- `agents/AGENT_CALL_MATRIX.md` - Task-specific agent delegation
- `docs/CLOUD_STARTUP.md` - Startup behavior contract

### Agent Call Matrix Compliance
All tasks must follow the AGENT_CALL_MATRIX.md requirements:
- **Panel Design**: Requires Promethea (layout) + Hera (implementation)
- **Hardware Integration**: Requires Argus + relevant specialists
- **Performance**: Requires Aether (React) or Pythia (Python)
- **Cloud Operations**: Requires Hermes + Janus (security)
- **Discovery/Navigation**: Requires Lexicon
- **System Auditing**: Requires Oracle

### Agent Communication Flow
1. Check task type against AGENT_CALL_MATRIX.md
2. Invoke required agents in correct sequence
3. Log all agent calls to `/logs/agent_calls/{date}_calls.log`
4. Validate outputs comply with agent boundaries

## Cloud Infrastructure (Supabase)

### Supabase Integration Pattern
Cloud backbone for licensing, telemetry, commands, and updates following a **local-first** architecture:
- Configuration edits remain local
- Cloud used for coordination, sync, and licensing only
- All implementation details in `docs/SUPABASE_GUARDRAILS.md`

### Core Tables
- `devices` - One row per licensed cabinet (serial, owner_id, status, version, last_seen)
- `commands` - Command queue for remote actions (patches, resets, diagnostics)
- `telemetry` - Logs sent from cabinets (level, code, message)
- `scores` - Optional tournament/leaderboard data

### Storage Buckets
- `updates/<semver>` - Patch bundles for cabinet updates
- `assets/` - Cabinet assets (marquee art, screenshots)

### Client Implementation Rules
- All Supabase code in `services/supabase_client.py` (Python) or `preload/supabase.js` (Electron)
- **Panels must NOT call Supabase directly** - route through agent functions
- Use per-device JWTs with limited scope (never embed service role keys)
- Heartbeat every 5 minutes to update `last_seen`
- Batch telemetry inserts (not chatty)
- Subscribe to commands (NEW status only)

### Security Requirements
- Row-Level Security (RLS) enforced: devices see only their own data
- Edge Functions hold service role keys (`register_device.ts`, `send_command.ts`, `sign_url.ts`)
- Signed URLs expire per session
- Admin operations bypass via Ops Console only

### Cabinet Responsibilities
1. Register on first boot → stores JWT locally
2. Heartbeat: every 5 min update `last_seen`
3. Telemetry: batch and insert logs
4. Subscribe to commands → validate payload → apply locally (safe-write + rollback) → update status + result

## Critical Operational Rules

### Config Management Protocol
**NEVER directly edit configs** - Always use the preview/apply/revert workflow:
1. Call preview endpoint with `x-scope` header (config/state/backup)
2. Display diff to user for approval
3. Call apply endpoint with automatic backup creation
4. Log change to `/logs/changes.jsonl` with backup path
5. Provide explicit rollback command with backup_path

### Sanctioned Write Paths
Only write to these directories:
- `/configs` - Configuration files
- `/state` - Application state
- `/backups/YYYYMMDD` - Automatic backups
- `/logs` - System logs
- `/emulators/*` - Emulator-specific configs

### Security Headers
All gateway requests must include:
- `x-scope: state|config|backup` - Operation scoping
- `x-device-id: {uuid}` - Device tracking for analytics

## Panel Development Patterns

### Panel Kit Usage
Use standardized Panel Kit components from `frontend/src/panels/_kit/`:
- `PanelShell` - Standard panel wrapper with header/footer, supports `icon`, `subtitle`, and `headerActions` props
- `DiffPreview` - Config change visualization
- `ApplyBar` - Action buttons with confirmation
- `useAIAction` - Hook for AI integration with retry logic

### PanelShell Enhanced Props (Added 2025-09-29)
```tsx
<PanelShell
  title="Panel Name"              // Required: Panel title (white text)
  subtitle="Description"          // Optional: Subtitle below title (light gray)
  icon={<img src="/avatar.png" />} // Optional: Icon/avatar next to title
  headerActions={<button>...</button>} // Optional: Custom buttons in header
  status="online"                 // Optional: online|degraded|offline
>
  {children}
</PanelShell>
```

### Chat Sidebar Pattern (LED Blinky & Voice Panel)
Standardized approach for slide-in chat panels:
```jsx
// Toggle button in header
<button onClick={() => setChatOpen(true)}>💬 Chat with AI</button>

// Chat sidebar with conditional render
{chatOpen && (
  <div className="panel-chat-sidebar" role="dialog">
    {/* Fixed positioning: position: fixed; right: 0; top: 0; z-index: 1000+ */}
    <div className="chat-header">
      <img src="/avatar.jpeg" className="chat-avatar" />
      <h3>Character Name</h3>
      <button onClick={() => setChatOpen(false)}>×</button>
    </div>
    <div className="chat-messages">{/* messages */}</div>
    <div className="chat-input-container">{/* input + send */}</div>
  </div>
)}
```

**Key Points:**
- Use conditional rendering (`{chatOpen && ...}`) not CSS animations
- Fixed positioning for proper overlay behavior
- High z-index (1000+) to appear above all content
- Follow LED Blinky pattern (`frontend/src/components/LEDBlinkyPanel.jsx:530-620`)

### Voice Integration Protocol
For microphone/voice features:
- Use Echo agent for voice logic implementation
- Implement graceful `getUserMedia` failure handling
- Sync mic state with toolbar using `<StatusChip>`
- All voice state must propagate through system

### Hardware Device Integration
For USB/HID device handling:
- Use Argus agent for hardware monitoring
- Implement non-blocking device detection
- Broadcast all hardware changes to Debug Panel
- Provide fallbacks for missing hardware

## AI Integration Architecture

### Gateway AI Endpoints
- `POST /api/ai/chat` - Unified chat with Claude/GPT adapters
- Automatic 429 retry with exponential backoff
- SSE support for streaming responses
- Device ID tracking for usage analytics

### Frontend AI Client
- Located at `frontend/src/services/aiClient.js`
- Includes 429 retry logic and device headers
- Handles provider switching (Claude ↔ GPT)
- Supports both request/response and streaming modes

## Voice & Audio Integration

### Text-to-Speech (ElevenLabs)
Gateway provides TTS endpoints at `/api/voice/*`:
- `POST /api/voice/tts` - Convert text to speech audio
  - Supports voice_id selection (default: Adam voice)
  - Returns audio/mpeg stream
  - Max text length: 2500 characters
  - Timeout: 30 seconds
- `GET /api/voice/voices` - List available ElevenLabs voices
- Configuration in `gateway/routes/tts.js`

### Audio WebSocket Protocol
Real-time audio streaming at `ws://localhost:8787/ws/audio`:

**Connection Flow:**
```javascript
const ws = new WebSocket('ws://localhost:8787/ws/audio');

// Server sends on connect:
{ type: 'connected', supported_formats: ['audio/webm', 'audio/wav'], max_chunk_size: 8192 }
```

**Message Types:**
- Client → Server:
  - `start_recording` - Begin audio capture
  - `audio_chunk` - Send audio data (base64 encoded, with sequence number)
  - `stop_recording` - End capture and process
  - `ping` - Keep-alive check
- Server → Client:
  - `recording_started` - Confirmation with timestamp
  - `chunk_received` - Acknowledgment with buffer size
  - `recording_completed` - Final status with chunk count
  - `pong` - Keep-alive response
  - `error` - Error messages

**Implementation Notes:**
- Audio chunks buffered server-side during recording
- STT (speech-to-text) processing marked as TODO in `gateway/ws/audio.js`
- WebSocket manager should be extracted outside React components to prevent recreation
- Implement graceful error handling for connection failures

## Code Quality Requirements

### Frontend Standards
- React 18 with modern hooks patterns
- ESLint compliance (configuration needed: `cd frontend && npx eslint --init`)
- Accessibility features (ARIA labels, keyboard navigation)
- CSS custom properties for theming
- Performance: memoization for expensive operations

### Backend Standards
- FastAPI with Pydantic validation
- All paths resolved under `AA_DRIVE_ROOT`
- Environment variables via python-dotenv
- Automatic OpenAPI documentation at `/docs` endpoint
- Interactive API testing available at `http://localhost:8888/docs` (Swagger UI)
- Alternative docs at `http://localhost:8888/redoc` (ReDoc format)

### Testing Requirements
- Jest unit tests with experimental VM modules
- Config operation tests: preview, apply, rollback
- Hardware integration mocking
- AI adapter contract testing

## Character Avatar System

### Avatar Integration Pattern (Established 2025-09-29)
The Voice Panel implements a complete 9-character avatar system. Follow this pattern for avatar integration:

**Asset Management:**
```bash
frontend/public/
  ├── {character}-avatar.jpeg  # Character portraits (48px circular)
  ├── {character}-mic.png      # Custom icons if needed
```

**Component Pattern:**
```jsx
const profiles = [
  { key: 'character', avatar: '/character-avatar.jpeg', name: 'Character Name', desc: 'Voice Type' }
]

// Conditional rendering for image vs emoji
{profile.avatar.startsWith('/') ? (
  <img src={profile.avatar} alt={profile.name} className="avatar-img" />
) : (
  <div className="avatar-emoji">{profile.avatar}</div>
)}
```

**CSS Standards:**
```css
.avatar-img {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid rgba(0, 229, 255, 0.4);
  box-shadow: 0 0 12px rgba(200, 255, 0, 0.3);
}
```

### 9 Arcade Assistant Characters
1. **Vicky** (Voice Assistant) - Pink AI with headset
2. **LoRa** (LaunchBox) - Blue/pink rocket robot
3. **Dewey** (AI Assistant) - Cyan holographic robot
4. **Sam** (Scorekeeper) - Referee robot with trophies
5. **Wiz** (Arcade Interface) - Wizard with joystick staff
6. **Chuck** (Controller Wizard) - Green robot with controller
7. **LED Blinky** (Lighting) - Purple robot with LED wires
8. **Gunner** (Light Guns) - Cowboy robot with light gun
9. **Doc** (System Health) - Doctor robot with clipboard

## UI Consistency Standards

### Uniform Component Styling (Lesson from Voice Panel)
**Do:** Apply consistent styling to similar components regardless of state
```css
.component {
  border: 2px solid #c8ff00;  /* Always same border */
  background: rgba(200, 255, 0, 0.05);  /* Always same background */
}
```

**Don't:** Use dynamic classes based on data state for visual prominence
```css
/* Avoid this pattern */
.component.active { border-color: #c8ff00; }
.component { border-color: rgba(0, 229, 255, 0.2); }  /* Creates inconsistency */
```

**Why:** Let content indicate state (dropdown values, text), not visual styling. Creates cleaner, more professional appearance.

### Text Color Standards
- **Panel Titles**: `color: #ffffff` (white, not grayed out)
- **Subtitles**: `color: #d1d5db` (light gray)
- **Body Text**: `color: #e0e0e0` (slightly lighter gray)
- **Muted Text**: `color: #888` (darker gray for less important info)

## LaunchBox LoRa Panel Patterns (Added 2025-09-30)

### Filter/Sort Pattern for Large Datasets
Use `useMemo` to prevent re-filtering on every render:
```jsx
const filteredAndSortedGames = useMemo(() => {
  let filtered = [...allGames]

  // Apply filters
  if (genreFilter !== 'All') {
    filtered = filtered.filter(g => g.genre === genreFilter)
  }
  if (yearFilter !== 'All') {
    const decadeStart = parseInt(yearFilter.substring(0, 4))
    filtered = filtered.filter(g => g.year >= decadeStart && g.year < decadeStart + 10)
  }

  // Apply sorting
  filtered.sort((a, b) => {
    switch (sortBy) {
      case 'lastPlayed': return b.lastPlayed - a.lastPlayed
      case 'playCount': return b.playCount - a.playCount
      case 'title': return a.title.localeCompare(b.title)
      case 'year': return b.year - a.year
      default: return 0
    }
  })

  return filtered
}, [allGames, genreFilter, yearFilter, sortBy])
```

### Visual Polish Essentials
Use subtle motion and lighting so premium panels stay performant:
- Run a slow pulse on the panel-bg-grid background layer
- Add lightweight card hover transitions (translateY + scale + shadow)
- Keep a single shimmering overlay for emphasis when needed
- Style genre badges with gradients for quick scanning
Avoid stacking heavy animations; clarity beats spectacle when screens are busy.

### A: Drive Architecture Pattern

**⚠️ CRITICAL PATH CORRECTIONS (2025-10-05):**
- **Actual LaunchBox Path**: `A:\LaunchBox` (NOT `A:\Arcade Assistant\LaunchBox`)
- **Master XML**: `A:\LaunchBox\Data\LaunchBox.xml` **NOT FOUND** - must parse platform XMLs instead
- **Platform XMLs**: `A:\LaunchBox\Data\Platforms\` (53 files with complete game metadata)
- **CLI_Launcher**: **NOT FOUND** at `ThirdParty\CLI_Launcher\` - alternative launch methods required
- **See `A_DRIVE_MAP.md`** for complete directory structure and integration notes

**Environment Detection:**
```javascript
// Gateway (driveDetection.js)
function isOnADrive() {
  return process.env.AA_DRIVE_ROOT?.toUpperCase().startsWith('A:\\')
}
```
```python
# Backend (launchbox.py)
def is_on_a_drive() -> bool:
    aa_root = os.getenv('AA_DRIVE_ROOT', '')
    return aa_root.upper().startswith('A:\\')
```

**Mock/Production Data Toggle:**
```python
# Initialize cache on startup
GAME_CACHE = parse_launchbox_xml() if is_on_a_drive() else get_mock_games()
```

**LaunchBox XML Parsing (CORRECTED - Parse Platform XMLs):**
```python
# ⚠️ DO NOT use MASTER_XML (file does not exist)
# Instead, parse all platform XMLs in Data/Platforms/

LAUNCHBOX_ROOT = 'A:\\LaunchBox'  # Corrected path (no subfolder)
PLATFORMS_DIR = 'A:\\LaunchBox\\Data\\Platforms'

def parse_launchbox_xml() -> Dict[str, Game]:
    """Parse all 53 platform XML files instead of missing master XML."""
    games = {}

    for xml_file in os.listdir(PLATFORMS_DIR):
        if not xml_file.endswith('.xml'):
            continue

        tree = ET.parse(os.path.join(PLATFORMS_DIR, xml_file))
        root = tree.getroot()

        for game_elem in root.findall('Game'):
            game_id = game_elem.findtext('ID', '').strip()
            games[game_id] = Game(
                id=game_id,
                title=game_elem.findtext('Title', 'Unknown'),
                platform=game_elem.findtext('Platform', 'Unknown'),
                genre=game_elem.findtext('Genre', ''),
                year=int(game_elem.findtext('ReleaseDate', '0')[:4]),
                # ... more fields
            )

    return games
```

### Random Game Selector Pattern
```jsx
const selectRandomGame = useCallback(() => {
  const games = filteredAndSortedGames.length > 0 ? filteredAndSortedGames : allGames
  const randomGame = games[Math.floor(Math.random() * games.length)]
  addMessage(`🎲 Random selection: ${randomGame.title}`, 'assistant')
  launchGame(randomGame)
}, [filteredAndSortedGames, allGames, launchGame])
```

### Performance & Chat Patterns
- Memoize filters with useMemo and handlers with useCallback`n- Prefer CSS classes over inline styles; debounce search/filter inputs
- Virtualize or paginate large result sets to avoid re-render spikes
- Keep WebSocket managers outside components so connections persist
- Chat toolbars combine text input, mic toggle, and send button with disabled states driven by isLoading or empty input

## Dewey AI Assistant Panel Pattern
Dewey remains a standalone layout (no PanelShell) focused on a personable 'friend' experience. Scope CSS under .dewey-panel-wrapper, animate speaking avatars, and surface five quick-action tiles for surprise, favorites, trending, history, and help flows. Persist profiles for guest, dad, mom, 	im, and sarah; swap them via handleUserChange and store preferences for upcoming Supabase integration. Pending work: wire Claude chat responses, add Supabase persistence, and layer in Web Speech for voice. Support both ?agent= and ?chat= query params, and keep Dewey out of the shared personas array so direct URLs load the panel immediately.

## ScoreKeeper Sam Panel Pattern
ScoreKeeper delivers a tournament manager with a compact header, three-column layout (bracket, setup, chat), and standalone styling. Memoize BracketMatch, keep player counts in a PLAYER_COUNTS constant, and reuse callbacks so bracket updates stay snappy. Support 4/8/16/32 player brackets with click-to-advance, live status updates, and chat messages tagged by timestamp. Route via /assistants?agent=historian|scorekeeper|sam.

## Directory Structure & File Organization
- rontend/: React + Vite UI; panels in src/panels, shared kit in _kit/`n- gateway/: Express BFF with REST routes (outes/), service adapters (dapters/), and WebSocket handlers (ws/)
- ackend/: FastAPI app with routers, services, and A-drive constants
- Safety-critical directories: configs/, state/, ackups/, logs, emulators/`nSee A_DRIVE_MAP.md and feature READMEs for deeper hierarchies.

## Development Workflow

### Starting Development
1. **Install dependencies**: `npm run install:all`
2. **Set up environment**: Copy `.env.example` to `.env` and configure API keys
3. **Start dev stack**: `npm run dev` (runs gateway + backend concurrently)
4. **Access application**: Navigate to `http://localhost:8787`

### Frontend Development Only
```bash
npm run dev:frontend  # Vite dev server with HMR
```
Frontend runs on port 5173 (Vite default) but proxies to gateway at 8787.

### Backend Development Only
```bash
npm run dev:backend   # FastAPI with auto-reload on port 8000
```
**Note**: Direct Python execution (`python backend/app.py`) uses port 8888. Update `FASTAPI_URL` in `.env` accordingly.

### Testing Workflow
```bash
npm test              # Run all Jest tests
npm run test:watch    # Watch mode for TDD
npm run test:health   # Gateway health check
npm run test:fastapi  # Backend health check
```

### Building for Production
```bash
npm run build:frontend  # Builds to frontend/dist/
```

## Troubleshooting Common Issues

### Port Conflicts
- **Gateway**: Default port 8787 (set via `PORT` in `.env`)
- **Backend**: Port 8000 (npm script) or 8888 (direct Python execution)
- **Frontend dev**: Port 5173 (Vite default)

If ports are in use:
```bash
# Find process using port
lsof -i :8787  # macOS/Linux
netstat -ano | findstr :8787  # Windows

# Kill process
kill -9 <PID>  # macOS/Linux
taskkill /PID <PID> /F  # Windows
```

### Build Failures
1. **ESLint errors**: Run `cd frontend && npm run lint` to see details
2. **Missing dependencies**: Run `npm run install:all`
3. **Python version**: Ensure Python >=3.10.0 (`python --version`)
4. **Node version**: Ensure Node >=18.0.0 (`node --version`)

### WebSocket Connection Issues
- Ensure gateway is running (`npm run test:health` should return 200)
- Check browser console for WebSocket errors
- Verify `ws://localhost:8787/ws/audio` endpoint is accessible
- WebSocket managers should be extracted outside React components (see LED Blinky pattern)

### A: Drive Detection Issues
```javascript
// Test drive detection
const { isOnADrive, getDriveStatus } = require('./gateway/utils/driveDetection.js')
console.log('On A: drive:', isOnADrive())
console.log('Drive status:', getDriveStatus())
```

Check `AA_DRIVE_ROOT` in `.env` is set correctly (e.g., `A:\` or current dev path).

## API Documentation

### Interactive API Docs
- **Backend (FastAPI)**: `http://localhost:8888/docs` (Swagger UI)
- **Backend (ReDoc)**: `http://localhost:8888/redoc` (alternative format)

Both provide interactive API testing with request/response examples.

### Key Endpoints

**Gateway (Node.js):**
- `GET /api/health` - Health check with system status
- `POST /api/ai/chat` - Unified AI chat (Claude/GPT)
- `GET /api/voice/voices` - List available TTS voices
- `POST /api/voice/tts` - Text-to-speech conversion
- `POST /api/local/config/preview` - Preview config changes
- `POST /api/local/config/apply` - Apply config changes
- `POST /api/local/config/revert` - Revert to backup

**Backend (FastAPI):**
- `GET /health` - Backend health check
- `GET /api/launchbox/games` - List/filter LaunchBox games with pagination
- `GET /api/launchbox/games/{id}` - Get game details
- `GET /api/launchbox/platforms` - List all platforms
- `GET /api/launchbox/genres` - List all genres
- `GET /api/launchbox/random` - Get random game (with optional filters)
- `POST /api/launchbox/launch/{id}` - Launch game via fallback chain
- `GET /api/launchbox/stats` - Cache statistics

## Environment Variables Reference

### Required Variables
```bash
# AI Services
ANTHROPIC_API_KEY=sk-ant-...        # Claude API (required for AI chat)
OPENAI_API_KEY=sk-...               # GPT API (optional, for GPT fallback)

# Voice Services
ELEVENLABS_API_KEY=...              # Text-to-speech (optional)

# System Configuration
AA_DRIVE_ROOT=/path/to/arcade       # Root path for local operations
PORT=8787                           # Gateway port (default: 8787)
FASTAPI_URL=http://localhost:8888   # Backend URL (8000 or 8888)

# Optional
NODE_ENV=development                # development | production
LOG_LEVEL=info                      # debug | info | warn | error
```

### Variable Usage by Service
- **Gateway**: Uses all API keys, `PORT`, `AA_DRIVE_ROOT`
- **Backend**: Uses `AA_DRIVE_ROOT`, `FASTAPI_URL` for self-reference
- **Frontend**: Receives config via gateway, no direct env access

## Performance Best Practices

### React Component Optimization
```jsx
// ✅ GOOD: Memoize expensive computations
const filteredData = useMemo(() => {
  return data.filter(item => item.active)
}, [data])

// ✅ GOOD: Memoize callbacks passed to children
const handleClick = useCallback(() => {
  doSomething(value)
}, [value])

// ❌ BAD: Inline styles (creates new object every render)
<div style={{ color: 'red' }} />

// ✅ GOOD: CSS classes
<div className="text-red" />
```

### WebSocket Management
```javascript
// ✅ GOOD: Extract WebSocket manager outside component
const wsManager = new LEDWebSocketManager()

function MyComponent() {
  useEffect(() => {
    wsManager.connect()
    return () => wsManager.disconnect()
  }, [])
}

// ❌ BAD: Create WebSocket inside component (recreates on every render)
function MyComponent() {
  const ws = new WebSocket('ws://localhost:8787')
}
```

### Large Dataset Handling
```jsx
// ✅ GOOD: Filter/sort with useMemo
const filteredGames = useMemo(() => {
  return games.filter(g => g.genre === selectedGenre).sort(...)
}, [games, selectedGenre])

// Consider pagination for 1000+ items
// Consider virtual scrolling (react-window) for 10000+ items
```

---

## LaunchBox LoRa Integration
LaunchBox LoRa spans backend XML parsing, a REST layer, and the React panel.

- **Backend**: parse every platform XML in A:\\LaunchBox\\Data\\Platforms, cache results, and expose filtering, random selection, stats, and launch endpoints. Fall back to LaunchBox.exe (CLI_Launcher missing) and direct MAME for arcade ROMs. Respect AA_DRIVE_ROOT checks before touching disk.
- **Frontend**: fetch games, platforms, genres, and stats on mount; show clear errors when the backend is offline; POST to /api/launchbox/launch/{id} with JSON headers; log the method returned by the API; and always keep 
pm run dev:backend running during testing to avoid HTML fallback responses.
- **Operating Modes**: default mock data (15 games, safe for development) versus full A-drive mode (~14k games) toggled by AA_DRIVE_ROOT. Restart the backend after changing the env var.
- **Validation**: curl /api/launchbox/stats, /api/launchbox/games?limit=5, and /api/launchbox/platforms to confirm responses, then verify 200s in the browser Network tab.

Track future upgrades�virtualized list rendering, Supabase persistence, favorites, advanced search, and voice commands�in LAUNCHBOX_IMPLEMENTATION_SUMMARY.md.
