# LaunchBox Plugin - Arcade Assistant Bridge

This C# plugin acts as a bridge between the Arcade Assistant (React/Node/Python) and LaunchBox. It exposes an HTTP API for game search and launching.

## What This Plugin Does

- **Runs inside LaunchBox** as a native plugin
- **Exposes HTTP endpoints** at `http://localhost:9999`
- **Provides game search** via LaunchBox's Plugin API
- **Launches games** using LaunchBox's native launch methods
- **No GUI changes** - just a background service

## Prerequisites

1. **Visual Studio 2022** (Community Edition is free)
   - Download: https://visualstudio.microsoft.com/downloads/
   - During install, select ".NET desktop development" workload

2. **LaunchBox Premium** (required for plugin support)
   - Plugins only work with LaunchBox Premium license

3. **LaunchBox Plugin SDK**
   - Located at: `C:\Program Files\LaunchBox\Unbroken.LaunchBox.Plugins.dll`
   - This gets referenced automatically in the project

## Step-by-Step Compilation Guide

### Step 1: Install Visual Studio

1. Download Visual Studio 2022 Community (free)
2. Run installer
3. Select ".NET desktop development" workload
4. Click Install (takes ~20-30 minutes)

### Step 2: Open the Project

1. Launch Visual Studio 2022
2. Click "Open a project or solution"
3. Navigate to: `Arcade Assistant Local/plugin/`
4. Select `ArcadeAssistantPlugin.csproj`
5. Click Open

### Step 3: Configure LaunchBox References

The project needs to reference LaunchBox DLLs:

1. In Solution Explorer (right side), expand "References"
2. Right-click "References" → "Add Reference"
3. Click "Browse" button (bottom right)
4. Navigate to your LaunchBox installation:
   - Default: `C:\Program Files\LaunchBox\`
5. Select these DLLs:
   - `Unbroken.LaunchBox.Plugins.dll`
   - `System.Text.Json.dll` (if not already referenced)
6. Click "Add" then "OK"

**Note:** If you installed LaunchBox elsewhere, update paths in `ArcadeAssistantPlugin.csproj` (lines 36-40)

### Step 4: Build the Plugin

1. At the top of Visual Studio, set build configuration to **"Release"**
   - Dropdown usually says "Debug" - change it to "Release"
2. Click **Build** menu → **Build Solution** (or press F6)
3. Wait for build to complete (should take 5-10 seconds)
4. Look for "Build succeeded" in the Output window at bottom

**If you get errors:**
- **"Could not find Unbroken.LaunchBox.Plugins"**
  - Check that LaunchBox is installed
  - Verify the path in Step 3 is correct
- **"Could not find System.Text.Json"**
  - Right-click project → Manage NuGet Packages
  - Search for "System.Text.Json"
  - Install it

### Step 5: Find the Compiled DLL

After successful build:

1. Navigate to: `Arcade Assistant Local/plugin/bin/Release/`
2. You should see: `ArcadeAssistantPlugin.dll`
3. Copy this file (we'll deploy it next)

## Deployment to LaunchBox

### Step 1: Create Plugin Folder

1. Navigate to LaunchBox installation:
   - Default: `C:\Program Files\LaunchBox\Plugins\`
2. Create new folder: `ArcadeAssistant\`
   - Full path: `C:\Program Files\LaunchBox\Plugins\ArcadeAssistant\`

### Step 2: Copy Plugin Files

Copy these files to the plugin folder:

```
C:\Program Files\LaunchBox\Plugins\ArcadeAssistant\
├── ArcadeAssistantPlugin.dll  (from bin/Release/)
└── (any dependency DLLs if needed)
```

### Step 3: Restart LaunchBox

1. Close LaunchBox completely
2. Launch LaunchBox
3. Check console output (if visible) for:
   ```
   [Arcade Assistant] Plugin initialized on port 9999
   [HTTP Server] Listening on port 9999
   ```

## Testing the Plugin

### Test 1: Health Check

Open PowerShell or Command Prompt:

```powershell
curl http://localhost:9999/health
```

**Expected response:**
```json
{
  "status": "ok",
  "plugin": "Arcade Assistant Bridge",
  "version": "1.0.0"
}
```

### Test 2: Search Games

```powershell
curl "http://localhost:9999/search-game?title=Pac-Man"
```

**Expected response:**
```json
[
  {
    "id": "game-uuid-here",
    "title": "Pac-Man",
    "platform": "Arcade",
    "developer": "Namco",
    ...
  }
]
```

### Test 3: Launch Game

```powershell
curl -X POST http://localhost:9999/launch-game -H "Content-Type: application/json" -d "{\"gameId\": \"your-game-id-here\"}"
```

**Expected response:**
```json
{
  "success": true,
  "message": "Game launched successfully"
}
```

## Troubleshooting

### Plugin Not Loading

1. **Check LaunchBox license:**
   - Tools → Options → License
   - Must be Premium (plugins don't work with free version)

2. **Check DLL location:**
   - Must be in `LaunchBox\Plugins\ArcadeAssistant\`
   - Not in a subfolder

3. **Check LaunchBox logs:**
   - LaunchBox → Tools → Options → Debugging
   - Enable "Enable Debug Logging"
   - Restart LaunchBox
   - Check logs in `LaunchBox\Logs\`

### Port 9999 Already in Use

If another application is using port 9999:

1. Open `Plugin.cs`
2. Change `private const int PORT = 9999;` to another port (e.g., 10000)
3. Rebuild
4. Update Python backend `launchbox_plugin_client.py` to match

### HTTP Endpoints Not Responding

1. **Check Windows Firewall:**
   - Allow LaunchBox.exe through firewall
   - Port 9999 should allow localhost connections

2. **Verify LaunchBox is running:**
   - Plugin only works while LaunchBox is running

3. **Check for exceptions:**
   - Look at LaunchBox console output
   - Check Windows Event Viewer for .NET errors

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/search-game?title={query}` | Search games by title |
| POST | `/launch-game` | Launch game by ID (JSON body: `{"gameId": "..."}`) |
| GET | `/list-platforms` | Get all platforms |
| GET | `/list-genres` | Get all genres |

## Next Steps

Once the plugin is working:

1. Your Python backend can now use `launchbox_plugin_client.py`
2. Test the full pipeline: React → Node → Python → C# Plugin → LaunchBox
3. Game launches will use LaunchBox's proven launch methods (no more WSL/Windows path issues!)

## Files Created

```
plugin/
├── README.md                          (this file)
├── ArcadeAssistantPlugin.csproj       (VS project file)
├── Plugin.cs                          (Main plugin entry point)
├── HttpServer.cs                      (HTTP API server)
├── GameLauncher.cs                    (LaunchBox API wrapper)
├── Models/
│   ├── GameInfo.cs                   (Game data model)
│   ├── LaunchRequest.cs              (Launch request model)
│   └── SearchRequest.cs              (Search request model)
└── Properties/
    └── AssemblyInfo.cs               (Assembly metadata)
```

## Support

If you encounter issues:

1. Check LaunchBox forums: https://forums.launchbox-app.com/
2. Review LaunchBox Plugin documentation
3. Check Visual Studio build output for specific errors
