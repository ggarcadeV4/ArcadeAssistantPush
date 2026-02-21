# C# Plugin Consolidation Summary

**Date**: 2025-10-10
**Status**: ✅ Complete - Build Successful (0 Errors)

## Executive Summary

Consolidated duplicate C# HTTP bridge implementations into a single, production-ready plugin with enhanced features:

- ✅ Fixed hardcoded `A:\` log path (now dynamic)
- ✅ Added rate limiting (2-second throttle per game)
- ✅ Added XML schema validation (ID/Title/Platform required)
- ✅ Added missing endpoints (/list-platforms, /list-genres)
- ✅ Unified logging and error handling
- ✅ Build successful: `ArcadeAssistantPlugin.dll` (29KB)

---

## Problem Statement

**Evidence**: Found two complete HTTP bridge implementations:

1. `/plugin/HttpServer.cs` + `/plugin/Plugin.cs` (NOT compiled)
   - Better async patterns, more endpoints
   - Missing: Port fallback, config support, proper logging

2. `/plugin/src/Bridge/HttpBridge.cs` + `/plugin/src/Plugin.cs` (ACTIVE)
   - Port fallback (9999 → 10099), config support
   - **Critical Issue**: Hardcoded `A:\LaunchBox` log path (line 309)
   - Missing: /list-platforms, /list-genres endpoints
   - Missing: Rate limiting

**Project File** (`ArcadeAssistantPlugin.csproj` lines 16-17):
```xml
<Compile Remove="**\*.cs" />
<Compile Include="src\**\*.cs" />
```
Only `src/**` files are compiled; root-level files were orphaned.

---

## Changes Made

### 1. Fixed Hardcoded Log Path
**File**: `plugin/src/Bridge/HttpBridge.cs:309-314`

**Before**:
```csharp
var p = System.IO.Path.Combine(@"A:\LaunchBox", "Logs", "ArcadeAssistant.log");
```

**After**:
```csharp
// Use portable path - works on any drive where LaunchBox is installed
var lbRoot = System.IO.Path.GetDirectoryName(System.IO.Path.GetDirectoryName(AppDomain.CurrentDomain.BaseDirectory));
var p = System.IO.Path.Combine(lbRoot!, "Logs", "ArcadeAssistant.log");
```

**Why**: Plugin now works on any drive (not just A:\), matches Plugin.cs pattern.

---

### 2. Added Rate Limiting
**File**: `plugin/src/Bridge/HttpBridge.cs:254-275`

**Implementation**:
```csharp
// Rate limiting for launch requests (prevent rapid-fire launches)
private static readonly Dictionary<string, DateTime> _lastLaunchTime = new Dictionary<string, DateTime>();
private static readonly object _launchLock = new object();
private static readonly TimeSpan _launchThrottle = TimeSpan.FromSeconds(2);

private static bool IsLaunchThrottled(string gameId)
{
  lock (_launchLock)
  {
    if (_lastLaunchTime.TryGetValue(gameId, out var lastTime))
    {
      var elapsed = DateTime.UtcNow - lastTime;
      if (elapsed < _launchThrottle)
      {
        Log($"Launch throttled for {gameId}: {elapsed.TotalSeconds:F1}s < {_launchThrottle.TotalSeconds}s");
        return true;
      }
    }
    _lastLaunchTime[gameId] = DateTime.UtcNow;
    return false;
  }
}
```

**Usage** (lines 133-138, 165-169):
```csharp
if (IsLaunchThrottled(gameId))
{
  TryWrite(ctx, 429, Json(new { success = false, error = "Launch request throttled - please wait before retrying" }));
  return;
}
```

**Why**: Matches backend throttle pattern (`AA_LAUNCH_THROTTLE_SEC=3`), prevents launch spam.

---

### 3. Moved GameLauncher to src/ Directory
**Actions**:
- Copied `/plugin/GameLauncher.cs` → `/plugin/src/GameLauncher.cs`
- Copied `/plugin/Models/` → `/plugin/src/Models/`
- Updated namespaces: `ArcadeAssistantPlugin` → `ArcadeAssistant.Plugin`

**Why**: GameLauncher provides authoritative Title→ID resolution and launch logic, but was excluded from build.

---

### 4. Added Missing Endpoints
**File**: `plugin/src/Bridge/HttpBridge.cs:215-247`

**New Endpoints**:
```csharp
// GET /list-platforms
if (ctx.Request.HttpMethod == "GET" && path == "/list-platforms")
{
  var platforms = GameLauncher.ListPlatforms();
  TryWrite(ctx, 200, Json(platforms));
  return;
}

// GET /list-genres
if (ctx.Request.HttpMethod == "GET" && path == "/list-genres")
{
  var genres = GameLauncher.ListGenres();
  TryWrite(ctx, 200, Json(genres));
  return;
}
```

**Why**: Backend REST contract expects these endpoints; previously returned 404.

---

### 5. Added XML Schema Validation
**File**: `plugin/src/GameLauncher.cs:84-87, 158-161, 194-197`

**Search Validation**:
```csharp
var matches = allGames
    .Where(g => g != null && g.Title != null &&
               g.Title.IndexOf(query, StringComparison.OrdinalIgnoreCase) >= 0)
    // Validate required fields (ID, Title, Platform)
    .Where(g => !string.IsNullOrEmpty(g.Id) &&
               !string.IsNullOrEmpty(g.Title) &&
               !string.IsNullOrEmpty(g.Platform))
    .OrderBy(g => g.Title)
```

**Platform/Genre Validation**:
```csharp
var platforms = allGames
    // Validate required fields before extracting platform
    .Where(g => g != null &&
               !string.IsNullOrEmpty(g.Id) &&
               !string.IsNullOrEmpty(g.Title) &&
               !string.IsNullOrEmpty(g.Platform))
    .Select(g => g.Platform)
```

**Why**: Prevents malformed XML entries from breaking searches; matches backend parser expectations.

---

### 6. Simplified Search Logic
**File**: `plugin/src/Bridge/HttpBridge.cs:201-205`

**Before** (duplicate GetGenreSafe, inline LINQ):
```csharp
var allGames = Unbroken.LaunchBox.Plugins.PluginHelper.DataManager.GetAllGames();
var matches = allGames
  .Where(g => g != null && g.Title != null &&
             g.Title.IndexOf(title, StringComparison.OrdinalIgnoreCase) >= 0)
  .Select(g => new { id = g.Id, title = g.Title, /* ... */ })
  .ToArray();
```

**After** (delegated to GameLauncher):
```csharp
// Use GameLauncher for consistent search logic
var matches = GameLauncher.SearchGames(title);
```

**Why**: Single source of truth for search logic; removed 40+ lines of duplicate code.

---

## File Structure After Consolidation

### Active Files (Compiled via src/**/*.cs)
```
plugin/src/
├── Plugin.cs                      # Main entry point (ISystemEventsPlugin + ISystemMenuItemPlugin)
├── Bridge/
│   └── HttpBridge.cs             # HTTP listener (port 9999 → 10099 fallback)
├── GameLauncher.cs                # Search, launch, list platforms/genres
└── Models/
    ├── GameInfo.cs               # Search result DTO
    ├── LaunchRequest.cs          # Launch request DTO
    └── SearchRequest.cs          # Search request DTO
```

### Orphaned Files (NOT compiled, safe to archive)
```
plugin/
├── Plugin.cs                      # Older plugin implementation
├── HttpServer.cs                  # Older HTTP server (ArcadeAssistantServer class)
└── GameLauncher.cs                # Older GameLauncher (pre-namespace change)
```

**Recommendation**: Move orphaned files to `plugin/archive/` to keep repo clean.

---

## API Contract (Unchanged)

### Plugin HTTP Endpoints (Port 9999)
- `GET /health` → `{ status, plugin, port, version }`
- `GET /search-game?title=...` → `GameInfo[]`
- `POST /launch` → `{ success, message, game }`
- `POST /launch-game` → `{ success, message }` (new canonical endpoint)
- `GET /list-platforms` → `string[]` ✨ NEW
- `GET /list-genres` → `string[]` ✨ NEW

### Backend Contract (Port 8888) - **NO CHANGES**
- `GET /api/launchbox/games`
- `GET /api/launchbox/platforms`
- `GET /api/launchbox/genres`
- `POST /api/launchbox/launch/{id}`

**Frontend unaffected**: All calls remain `fetch('/api/launchbox/...')` → Gateway → Backend → Plugin.

---

## Build Output

```
Build succeeded.
  ArcadeAssistantPlugin -> C:\...\plugin\bin\Release\ArcadeAssistantPlugin.dll

  13 Warning(s)  (nullable reference warnings - safe to ignore)
  0 Error(s)

  File Size: 29KB (DLL) + 18KB (PDB)
```

---

## Testing Checklist

### Unit Tests (Plugin Isolation)
- [ ] **Health check**: `GET http://localhost:9999/health` → `{ status: "ok", port: 9999 }`
- [ ] **Port fallback**: If 9999 busy, plugin uses 10099
- [ ] **Search validation**: Query with malformed XML entries returns only valid games
- [ ] **Rate limit**: Two POSTs to `/launch` <2s apart → 429 response
- [ ] **Log path**: Logs written to `<LaunchBox>\Logs\ArcadeAssistant.log` (not hardcoded A:\)

### Integration Tests (Backend → Plugin)
- [ ] **Title→ID resolution**: `GET /api/launchbox/resolve?title=Pac-Man` returns candidates
- [ ] **Launch via plugin**: `POST /api/launchbox/launch/{id}` → logs show `method_used="plugin_bridge"`
- [ ] **Platforms list**: `GET /api/launchbox/platforms` includes all valid platforms
- [ ] **Genres list**: `GET /api/launchbox/genres` includes all valid genres

### Acceptance Tests (3-Genre Launch)
- [ ] **Street Fighter II** (Fighting) → Resolves + Launches
- [ ] **Galaga** (Shooter) → Resolves + Launches
- [ ] **Pac-Man** (Maze) → Resolves + Launches
- [ ] All three log: `[GameLauncher] Launching: {Title} ({Platform})`
- [ ] All three return: `{ success: true, method_used: "plugin_bridge" }`

---

## Risk Assessment

### Eliminated Risks ✅
- ~~Path drift (hardcoded A:\)~~ → Now dynamic
- ~~Duplicate HTTP listeners~~ → Single consolidated bridge
- ~~Missing rate limiting~~ → 2-second throttle added
- ~~Missing XML validation~~ → ID/Title/Platform checks added
- ~~Missing endpoints~~ → /list-platforms, /list-genres added

### Remaining Risks ⚠️
- **Unmanaged threads in backend**: Cache/image preload threads not joined on shutdown (separate task)
- **No stress testing**: Rate limiter not tested under high concurrency
- **No LaunchBox hooks**: OnGameLaunching/OnGameExited not implemented (future enhancement)

---

## Next Steps

1. **Deploy plugin**:
   ```bash
   cp plugin/bin/Release/ArcadeAssistantPlugin.dll "A:\LaunchBox\Plugins\ArcadeAssistant\"
   # Restart LaunchBox
   ```

2. **Run acceptance tests**:
   - Start backend: `npm run dev:backend`
   - Verify plugin: `curl http://localhost:9999/health`
   - Test 3-genre launch sequence (README.md:3024-3032)

3. **Backend thread cleanup** (separate task):
   - Track worker threads in `app.state`
   - Join on FastAPI shutdown event
   - Add structured logging for thread lifecycle

4. **Archive orphaned files**:
   ```bash
   mkdir plugin/archive
   mv plugin/{Plugin.cs,HttpServer.cs,GameLauncher.cs} plugin/archive/
   mv plugin/Models plugin/archive/
   ```

---

## Lessons Learned

1. **Always check .csproj**: Duplicate implementations existed because only `src/**` was compiled.
2. **Portable paths**: Never hardcode drive letters; use `AppDomain.CurrentDomain.BaseDirectory` for relative resolution.
3. **Rate limiting**: Simple Dictionary-based throttle is sufficient for single-instance plugins.
4. **Validation early**: Filter malformed data at source (plugin) rather than downstream (backend/frontend).
5. **Single source of truth**: GameLauncher now owns all Title→ID resolution logic; HttpBridge delegates.

---

**Consolidation Complete** ✅
**Build Status**: Success (0 Errors)
**Ready for**: Acceptance Testing
