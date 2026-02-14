# FastAPI Backend Configuration Report

## Executive Summary
The FastAPI backend is properly configured with dual port support (8888 direct, 8000 via npm), CORS enabled for the gateway, all LaunchBox routes registered, and intelligent A: drive detection with automatic mock data fallback.

## 1. Port Configuration

### Direct Python Execution
- **Command**: `python backend/app.py`
- **Port**: **8888**
- **Location**: `/mnt/c/Users/Dad's PC/Desktop/Arcade Assistant Local/backend/app.py:137`
- **Code**: `port=8888`

### NPM Script Execution
- **Command**: `npm run dev:backend`
- **Port**: **8000**
- **Location**: `/mnt/c/Users/Dad's PC/Desktop/Arcade Assistant Local/package.json:10`
- **Script**: `python3 -m uvicorn backend.app:app --reload --port 8000`

### Important Note
The `.env` file must have `FASTAPI_URL` set correctly based on launch method:
- For direct execution: `FASTAPI_URL=http://localhost:8888`
- For npm script: `FASTAPI_URL=http://localhost:8000`

## 2. Route Registration

### Health Endpoint ✅
- **Route**: `/health`
- **Router File**: `/backend/routers/health.py`
- **Registration**: `/backend/app.py:114`
- **Full Path**: `GET http://localhost:8888/health`
- **Response**: Returns drive status, manifest existence, sanctioned paths, and emulator list

### LaunchBox Routes ✅
- **Prefix**: `/api/launchbox`
- **Router File**: `/backend/routers/launchbox.py`
- **Registration**: `/backend/app.py:121`
- **Activation Date**: 2025-10-06
- **Endpoints**:
  - `GET /api/launchbox/games` - List/filter games with pagination
  - `GET /api/launchbox/games/{id}` - Get specific game details
  - `GET /api/launchbox/platforms` - List all platforms
  - `GET /api/launchbox/genres` - List all genres
  - `GET /api/launchbox/random` - Get random game (with filters)
  - `POST /api/launchbox/launch/{id}` - Launch game
  - `GET /api/launchbox/stats` - Cache statistics
  - `GET /api/launchbox/image/{id}` - Serve game images
  - `GET /api/launchbox/plugin-status` - C# plugin bridge status
  - `GET /api/launchbox/images/stats` - Image scanner stats
  - `POST /api/launchbox/images/refresh` - Force refresh image cache

### Other Registered Routes
- `/config` - Config operations (`/backend/app.py:115`)
- `/docs/session_log` - Session logging (`/backend/app.py:116`)
- `/mame` - MAME emulator operations (`/backend/app.py:117`)
- `/retroarch` - RetroArch operations (`/backend/app.py:118`)
- `/screen` - Screen capture (`/backend/app.py:119`)
- `/claude` - Claude API integration (`/backend/app.py:120`)

## 3. CORS Configuration ✅

### Settings
- **Enabled**: Yes
- **Location**: `/backend/app.py:105-111`
- **Allowed Origins**:
  - `http://localhost:8787` ✅ (Gateway port)
  - `https://localhost:8787` ✅ (HTTPS variant)
- **Allow Credentials**: `True`
- **Allow Methods**: `["GET", "POST", "PUT", "DELETE"]`
- **Allow Headers**: `["*"]` (All headers permitted)

This configuration correctly allows the gateway (running on port 8787) to make requests to the backend.

## 4. LaunchBox Integration

### Startup Sequence
1. **Environment Loading** (`/backend/app.py:14-25`)
2. **Environment Validation** (`/backend/startup_manager.py:32-68`)
3. **App State Initialization** (`/backend/startup_manager.py:70-110`)
4. **LaunchBox Cache Initialization** (`/backend/app.py:46-48`)
5. **Optional Cache Pre-warming** (`/backend/app.py:50-62`)

### A: Drive Detection

#### Detection Logic
- **File**: `/backend/constants/a_drive_paths.py:43-46`
- **Function**: `is_on_a_drive()`
- **Checks For**:
  - Windows path starting with `A:`
  - WSL path starting with `/MNT/A`

#### When A: Drive IS Detected
- **Skips Manifest Validation**: `/backend/startup_manager.py:46-49`
  - Warning: "A: drive detected - skipping manifest.json validation"
- **Uses Empty Manifest**: `/backend/startup_manager.py:78`
- **Parses Real XML Files**: From `A:\LaunchBox\Data\Platforms\*.xml`
- **Expected Games**: ~14,000+ from 53 platform XML files

#### When A: Drive IS NOT Detected
- **Loads Mock Data**: `/backend/services/launchbox_parser.py:517-540`
- **Mock Games Count**: 15 games
- **Mock Platforms**:
  - Arcade
  - NES
  - SNES
  - Sega Genesis
- **Mock Genres**: Fighting, Maze, Platform, Shooter, Adventure, Action, Puzzle

### XML Parsing Strategy
- **Primary Source**: Platform XMLs in `A:\LaunchBox\Data\Platforms\`
- **NOT Using**: Master XML (`LaunchBox.xml`) - file doesn't exist
- **Parser Service**: `/backend/services/launchbox_parser.py`
- **Cache Strategy**:
  - In-memory cache for fast filtering
  - Disk cache at `/backend/cache/launchbox_parser_cache.json`
  - Lazy loading (parses on first request)
  - Cache max age: 7 days

### Launch Methods Fallback Chain
1. **C# Plugin Bridge** (primary - if available)
2. **LaunchBox.exe** (fallback - if plugin unavailable)
3. **Direct MAME execution** (last resort for arcade games)

Note: `CLI_Launcher.exe` not found at expected location, using alternatives.

## 5. Interactive API Documentation

### Swagger UI
- **URL**: `http://localhost:8888/docs` (or port 8000 if using npm script)
- **Features**: Interactive API testing with request/response examples

### ReDoc
- **URL**: `http://localhost:8888/redoc`
- **Features**: Alternative documentation format

## 6. Verification Commands

### Test Backend Health
```bash
# Direct execution (port 8888)
curl -s http://localhost:8888/health | jq .

# NPM script (port 8000)
curl -s http://localhost:8000/health | jq .
```

### Test LaunchBox Endpoints
```bash
# Get cache stats
curl -s http://localhost:8888/api/launchbox/stats | jq .

# List first 5 games
curl -s "http://localhost:8888/api/launchbox/games?limit=5" | jq .

# Get all platforms
curl -s http://localhost:8888/api/launchbox/platforms | jq .

# Get random game
curl -s http://localhost:8888/api/launchbox/random | jq .
```

## 7. Common Issues & Solutions

### Issue: 404 on LaunchBox routes
**Cause**: Backend not running or wrong port in URL
**Solution**:
1. Ensure backend is running (`npm run dev:backend` or `python backend/app.py`)
2. Use correct port (8000 for npm, 8888 for direct)

### Issue: Mock data instead of real games
**Cause**: A: drive not detected
**Solution**:
1. Set `AA_DRIVE_ROOT=A:\` in `.env` file
2. Ensure LaunchBox is at `A:\LaunchBox` (not in subfolder)
3. Restart backend after changing environment variable

### Issue: CORS errors in browser
**Cause**: Incorrect origin or missing headers
**Solution**: Gateway is correctly whitelisted at `localhost:8787`

### Issue: Empty game list
**Cause**: XML parsing failed or cache not initialized
**Solution**:
1. Check `/api/launchbox/stats` endpoint for status
2. Look for errors in backend console
3. Try `/api/launchbox/images/refresh` to force cache rebuild

## 8. File Navigation Map

### Core Files
- **Main App**: `/backend/app.py` - FastAPI application entry point
- **Startup Manager**: `/backend/startup_manager.py` - Environment validation
- **A: Drive Constants**: `/backend/constants/a_drive_paths.py` - Path definitions

### LaunchBox Integration
- **Router**: `/backend/routers/launchbox.py` - API endpoints
- **Parser Service**: `/backend/services/launchbox_parser.py` - XML parsing & caching
- **Launcher Service**: `/backend/services/launcher.py` - Game launching logic
- **Plugin Client**: `/backend/services/launchbox_plugin_client.py` - C# bridge
- **Image Scanner**: `/backend/services/image_scanner.py` - Image discovery

### Models
- **Game Model**: `/backend/models/game.py` - Pydantic models for games

## Conclusion

The FastAPI backend is fully configured and operational with:
- ✅ Dual port support (8888/8000)
- ✅ CORS properly configured for gateway access
- ✅ All routes registered including `/health` and `/api/launchbox/*`
- ✅ Intelligent A: drive detection with automatic fallback
- ✅ Comprehensive LaunchBox integration with caching
- ✅ Multiple launch method fallbacks

The system gracefully handles both production (A: drive) and development (mock data) scenarios.