# 📦 LaunchBox Plugin Integration Guide

**Status:** Authoritative
**Purpose:** Document LaunchBox plugin architecture and HTTP integration
**Location:** /docs/LAUNCHBOX_PLUGIN_INTEGRATION.md
**Last Updated:** 2025-10-12

---

## 🎮 Plugin Architecture Overview

### Plugin Location (Production)
```
A:\LaunchBox\Plugins\ArcadeAssistant\
├── ArcadeAssistantPlugin.dll     # Main plugin DLL
├── ArcadeAssistant.deps.json     # Dependencies manifest
├── Microsoft.AspNetCore.*.dll    # ASP.NET Core runtime
└── Newtonsoft.Json.dll          # JSON serialization
```

### HTTP API Server
- **Port:** 9999 (localhost only)
- **Protocol:** HTTP/REST with JSON
- **Startup:** Auto-starts with LaunchBox
- **Shutdown:** Stops when LaunchBox closes

---

## 🔌 Plugin HTTP Endpoints

### Health Check
```http
GET http://127.0.0.1:9999/health
```
**Response:**
```json
{
  "plugin": "ArcadeAssistant",
  "version": "1.0.0",
  "status": "healthy",
  "launchbox_connected": true
}
```

### Game Search
```http
GET http://127.0.0.1:9999/search-game?title={query}
```
**Response:**
```json
[
  {
    "id": "uuid-string",
    "GameId": "uuid-string",
    "title": "Street Fighter II",
    "platform": "Arcade",
    "genre": "Fighting",
    "year": 1991,
    "developer": "Capcom",
    "publisher": "Capcom"
  }
]
```

### Launch Game
```http
POST http://127.0.0.1:9999/launch-game
Content-Type: application/json

{
  "GameId": "uuid-string"
}
```
**Response:**
```json
{
  "success": true,
  "message": "Game launched successfully",
  "method": "LaunchBox"
}
```

### List Platforms
```http
GET http://127.0.0.1:9999/list-platforms
```
**Response:**
```json
["Arcade", "Nintendo Entertainment System", "Sega Genesis", ...]
```

### List Genres
```http
GET http://127.0.0.1:9999/list-genres
```
**Response:**
```json
["Action", "Adventure", "Fighting", "Puzzle", ...]
```

---

## 🔄 Integration Flow

### Request Path
```
Frontend Panel
    ↓ (fetch)
Gateway (8787)
    ↓ (proxy)
Backend (8000/8888)
    ↓ (HTTP)
Plugin (9999)
    ↓ (LaunchBox API)
LaunchBox.exe
    ↓
Emulator Launch
```

### Launch Fallback Chain
1. **Plugin Bridge** (primary) - via HTTP to plugin at :9999
2. **LaunchBox.exe** (fallback) - direct process spawn
3. **Direct Emulator** (disabled) - requires `AA_ALLOW_DIRECT_EMULATOR=true`

---

## 🛠️ Development Setup

### Prerequisites
1. LaunchBox installed at `A:\LaunchBox`
2. Plugin DLLs copied to `A:\LaunchBox\Plugins\ArcadeAssistant\`
3. LaunchBox running (plugin auto-starts)

### Testing Plugin Connection
```bash
# Health check
curl -s http://127.0.0.1:9999/health | jq

# Search for games
curl -s "http://127.0.0.1:9999/search-game?title=Street%20Fighter" | jq

# Launch game (POST)
curl -X POST http://127.0.0.1:9999/launch-game \
  -H "Content-Type: application/json" \
  -d '{"GameId": "test-uuid"}'
```

### Backend Integration Test
```bash
# Via backend resolver
curl -s "http://localhost:8000/api/launchbox/resolve?title=Pac-Man"

# Launch via backend
curl -X POST http://localhost:8000/api/launchbox/launch/{game-id}
```

---

## 📋 Environment Configuration

### Required .env Settings
```bash
# LaunchBox paths
LAUNCHBOX_ROOT=A:\LaunchBox
AA_DRIVE_ROOT=A:\

# Backend URL (varies by launch method)
FASTAPI_URL=http://localhost:8000  # npm run dev:backend
# or
FASTAPI_URL=http://localhost:8888  # python backend/app.py

# Plugin control
AA_ALLOW_DIRECT_EMULATOR=false  # Keep disabled for plugin-first approach
```

### WSL vs Windows Native
- **Windows Native:** Plugin works directly at localhost:9999
- **WSL:** May need port forwarding or `127.0.0.1` instead of `localhost`

---

## 🔍 Troubleshooting

### Plugin Not Responding
1. Check LaunchBox is running
2. Verify plugin DLLs in correct location
3. Check Windows Firewall for port 9999
4. Review LaunchBox logs for plugin errors

### Connection Issues from WSL
```bash
# Test from WSL
curl -v http://127.0.0.1:9999/health

# If fails, check Windows IP
ip route | grep default
# Use that IP instead of localhost
```

### Backend Can't Reach Plugin
1. Ensure backend uses `127.0.0.1` not `localhost`
2. Check both processes run at same privilege level
3. Verify no proxy settings interfering

---

## 📦 Plugin Build & Deployment

### Building Plugin (C#/.NET)
```bash
cd LaunchBoxPlugin/
dotnet build -c Release
```

### Deployment Steps
1. Stop LaunchBox completely
2. Copy Release DLLs to `A:\LaunchBox\Plugins\ArcadeAssistant\`
3. Restart LaunchBox
4. Verify at http://127.0.0.1:9999/health

### Version Management
- Increment version in plugin assembly
- Update version in health endpoint response
- Tag git repo with matching version

---

## 🔒 Security Considerations

### Network Binding
- Plugin binds to `127.0.0.1:9999` ONLY
- No external network access allowed
- Firewall should block external connections

### Authentication
- Currently none (localhost only)
- Future: Could add API key if needed
- All requests assumed trusted (local only)

### Data Validation
- Plugin validates all GameId formats
- Sanitizes search queries
- Returns structured errors for invalid requests

---

## 📊 Monitoring & Logs

### Plugin Logs
- Location: `A:\LaunchBox\Logs\Plugins\ArcadeAssistant\`
- Rotation: Daily
- Level: Info by default

### Health Monitoring
```python
# Backend health check
def check_plugin_health():
    try:
        response = requests.get("http://127.0.0.1:9999/health", timeout=2)
        return response.status_code == 200
    except:
        return False
```

### Metrics to Track
- Plugin uptime
- Request count by endpoint
- Launch success rate
- Average response time

---

## 🚀 Future Enhancements

### Planned Features
- [ ] WebSocket support for real-time updates
- [ ] Batch operations (launch multiple games)
- [ ] Statistics endpoint
- [ ] Favorites management
- [ ] Recent games tracking

### Performance Optimizations
- [ ] Connection pooling in backend client
- [ ] Response caching for searches
- [ ] Async launch operations
- [ ] Compression for large responses

---

## 📚 Related Documentation
- `docs/launchbox_plugin_restore.md` - Plugin restore guide
- `backend/services/launchbox_plugin_client.py` - Python client implementation
- `A_DRIVE_MAP.md` - Complete A: drive structure
- `LAUNCHBOX_IMPLEMENTATION_SUMMARY.md` - Frontend implementation notes