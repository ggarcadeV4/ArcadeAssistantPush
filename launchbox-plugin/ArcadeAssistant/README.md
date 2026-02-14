# Arcade Assistant LaunchBox HTTP Plugin

A LaunchBox plugin that provides an HTTP API for launching games from WSL, Linux, or external applications. This solves the critical issue of launching Windows games from WSL environments where direct execution is not possible.

## Features

- **HTTP API Server** - Runs on `http://127.0.0.1:31337/`
- **Secure** - Localhost-only connections
- **Game Launching** - Launch any LaunchBox game by ID
- **Health Monitoring** - Check server status and uptime
- **CORS Support** - Works with web applications on localhost
- **Automatic Startup** - Starts with LaunchBox automatically
- **Comprehensive Logging** - All operations logged for debugging

## Requirements

- **LaunchBox** 11.0 or later
- **.NET Framework 4.8**
- **Windows 10/11**
- **Visual Studio 2019/2022** or **MSBuild** (for compilation)

## Installation

### Option 1: Build from Source

1. **Clone or download this repository**

2. **Open Command Prompt as Administrator** and navigate to the plugin directory:
   ```cmd
   cd "C:\path\to\launchbox-plugin\ArcadeAssistant"
   ```

3. **Run the build script**:
   ```cmd
   build.bat
   ```

   This will:
   - Compile the plugin
   - Deploy it to `A:\LaunchBox\Plugins\ArcadeAssistant\`
   - Verify the installation

### Option 2: Manual Build with Visual Studio

1. **Open** `ArcadeAssistantPlugin.csproj` in Visual Studio
2. **Update** the LaunchBox SDK reference path if needed (in project properties)
3. **Build** the solution (Build → Build Solution)
4. **Copy** the output files to `A:\LaunchBox\Plugins\ArcadeAssistant\`

### Option 3: Direct Compilation

If you don't have Visual Studio, use the C# compiler directly:

```cmd
csc /target:library /reference:"A:\LaunchBox\Core\Unbroken.LaunchBox.Plugins.dll" /reference:System.dll /reference:System.Core.dll /reference:System.Web.Extensions.dll /reference:System.Windows.Forms.dll /out:ArcadeAssistantPlugin.dll ArcadeAssistantPlugin.cs LaunchServer.cs Properties\AssemblyInfo.cs
```

Then copy `ArcadeAssistantPlugin.dll` to `A:\LaunchBox\Plugins\ArcadeAssistant\`

## Usage

### Starting the Plugin

1. **Start LaunchBox** - The plugin loads automatically
2. **Verify** the plugin is running by checking: `http://127.0.0.1:31337/health`
3. The server will show in LaunchBox logs as "Arcade Assistant Plugin initialized"

### API Endpoints

#### GET /health
Check if the server is running and healthy.

**Request:**
```bash
curl http://127.0.0.1:31337/health
```

**Response:**
```json
{
  "available": true,
  "version": "1.0.0",
  "uptime_seconds": 3600,
  "request_count": 42
}
```

#### POST /launch
Launch a game by its LaunchBox ID.

**Request:**
```bash
curl -X POST http://127.0.0.1:31337/launch \
  -H "Content-Type: application/json" \
  -d '{"game_id": "12345678-1234-1234-1234-123456789abc"}'
```

**Success Response:**
```json
{
  "launched": true,
  "game_title": "Street Fighter II",
  "platform": "Arcade",
  "timestamp": "2025-01-15 14:30:00"
}
```

**Error Response:**
```json
{
  "launched": false,
  "error": "Game with ID '...' not found"
}
```

#### GET /status
Get detailed server status information.

**Response:**
```json
{
  "available": true,
  "version": "1.0.0",
  "uptime_seconds": 3600,
  "request_count": 42,
  "timestamp": "2025-01-15 14:30:00"
}
```

#### GET /games
Get a sample of games (first 10) for testing.

**Response:**
```json
{
  "total": 14233,
  "sample": [
    {
      "id": "12345678-1234-1234-1234-123456789abc",
      "title": "Street Fighter II",
      "platform": "Arcade",
      "year": 1991
    }
  ]
}
```

### Using from WSL

From WSL or Linux, you can call the API using curl, wget, or any HTTP client:

```bash
# Check health
curl http://127.0.0.1:31337/health

# Launch a game
curl -X POST http://127.0.0.1:31337/launch \
  -H "Content-Type: application/json" \
  -d '{"game_id": "YOUR-GAME-ID-HERE"}'

# Get sample games to find IDs
curl http://127.0.0.1:31337/games
```

### Integration with Arcade Assistant

The Arcade Assistant backend automatically detects and uses this plugin when available:

```python
# backend/services/launchbox_service.py
def launch_game_via_plugin(game_id: str) -> bool:
    """Launch game using HTTP plugin (for WSL environments)"""
    try:
        response = requests.post(
            "http://127.0.0.1:31337/launch",
            json={"game_id": game_id},
            timeout=5
        )
        return response.json().get("launched", False)
    except:
        return False
```

## Architecture

### Plugin Structure

```
ArcadeAssistant/
├── ArcadeAssistantPlugin.cs    # Main plugin class (ISystemEventsPlugin)
├── LaunchServer.cs              # HTTP server implementation
├── Properties/
│   └── AssemblyInfo.cs        # Assembly metadata
├── ArcadeAssistantPlugin.csproj # Visual Studio project
├── build.bat                    # Build script
├── README.md                    # This file
└── .gitignore                  # Git ignore rules
```

### How It Works

1. **Plugin Initialization**: When LaunchBox starts, it loads all plugins from the `Plugins` directory
2. **Event Hook**: The plugin hooks into `LaunchBoxStartupCompleted` event
3. **HTTP Server**: Starts an `HttpListener` on port 31337 (localhost only)
4. **Request Processing**: Handles incoming HTTP requests on a thread pool
5. **Game Launching**: Uses LaunchBox's `PluginHelper.LaunchBoxMainViewModel.PlayGame()` API
6. **Thread Safety**: Launch operations are marshaled to the UI thread

### Security Considerations

- **Localhost Only**: Server only accepts connections from 127.0.0.1
- **GUID Validation**: Game IDs are validated as proper GUIDs
- **Error Handling**: All exceptions are caught and logged
- **No External Dependencies**: Uses only .NET Framework libraries
- **CORS Headers**: Limited to `http://localhost:8787` for web apps

## Troubleshooting

### Plugin Not Loading

1. **Check LaunchBox Version**: Ensure you have LaunchBox 11.0 or later
2. **Verify .NET Framework**: Install .NET Framework 4.8 if missing
3. **Check File Location**: Plugin must be in `LaunchBox\Plugins\ArcadeAssistant\`
4. **Review Logs**: Check LaunchBox logs for errors

### Server Not Starting

1. **Port Conflict**: Ensure port 31337 is not in use:
   ```cmd
   netstat -an | findstr :31337
   ```

2. **Windows Firewall**: The plugin only uses localhost, but check firewall isn't blocking

3. **Permissions**: Run LaunchBox as Administrator if needed

### Games Not Launching

1. **Verify Game ID**: Use `/games` endpoint to get valid game IDs
2. **Check LaunchBox**: Ensure the game launches normally from LaunchBox
3. **Review Logs**: Check debug output in Visual Studio or LaunchBox logs

### Build Errors

1. **MSBuild Not Found**: Install Visual Studio or Build Tools
2. **SDK Missing**: Ensure `Unbroken.LaunchBox.Plugins.dll` path is correct
3. **Target Framework**: Install .NET Framework 4.8 Developer Pack

## Development

### Debug Mode

To debug the plugin:

1. Build in Debug configuration
2. Copy the DLL and PDB files to LaunchBox plugins folder
3. Attach Visual Studio debugger to LaunchBox.exe process
4. Set breakpoints in your code

### Logging

The plugin logs to:
- Visual Studio Output window (when debugging)
- System.Diagnostics.Debug
- Console output (visible in LaunchBox logs)

### Testing

Test the plugin using the included test script or manually:

```powershell
# PowerShell test script
$health = Invoke-RestMethod -Uri "http://127.0.0.1:31337/health"
Write-Host "Server Status: $($health.available)"

$games = Invoke-RestMethod -Uri "http://127.0.0.1:31337/games"
Write-Host "Total Games: $($games.total)"

if ($games.sample.Count -gt 0) {
    $gameId = $games.sample[0].id
    $launch = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:31337/launch" `
        -ContentType "application/json" -Body (@{game_id=$gameId} | ConvertTo-Json)
    Write-Host "Launch Result: $($launch.launched)"
}
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Test thoroughly with LaunchBox
4. Submit a pull request

## License

MIT License - See LICENSE file for details

## Credits

- **Arcade Assistant Team** - Plugin development
- **LaunchBox** - For the excellent frontend and plugin API
- **Community** - For testing and feedback

## Support

For issues, questions, or suggestions:

1. Check this README first
2. Review LaunchBox plugin documentation
3. Open an issue on GitHub
4. Contact Arcade Assistant support

## Version History

### 1.0.0 (2025-01-15)
- Initial release
- HTTP API server on port 31337
- Game launching via POST /launch
- Health check endpoints
- CORS support for localhost
- Comprehensive error handling

## Future Enhancements

- [ ] WebSocket support for real-time status
- [ ] Batch launch operations
- [ ] Game search/filter API
- [ ] Platform-specific launch options
- [ ] Configuration file support
- [ ] Multiple instance detection
- [ ] Launch history tracking
- [ ] Performance metrics