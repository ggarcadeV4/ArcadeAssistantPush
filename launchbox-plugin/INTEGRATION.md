# LaunchBox Plugin Integration Guide

## Quick Start

1. **Build the Plugin** (from Windows):
   ```cmd
   cd launchbox-plugin\ArcadeAssistant
   build-simple.bat
   ```

2. **Start LaunchBox** - Plugin loads automatically

3. **Verify** it's running:
   ```bash
   curl http://127.0.0.1:31337/health
   ```

## Backend Integration (Python/FastAPI)

Update `backend/services/launchbox_service.py` to use the HTTP plugin:

```python
import requests
from typing import Optional, Dict, Any

class LaunchBoxService:
    PLUGIN_URL = "http://127.0.0.1:31337"

    def is_plugin_available(self) -> bool:
        """Check if LaunchBox plugin is running"""
        try:
            response = requests.get(f"{self.PLUGIN_URL}/health", timeout=1)
            return response.json().get("available", False)
        except:
            return False

    def launch_game(self, game_id: str) -> Dict[str, Any]:
        """Launch game via HTTP plugin"""
        # Try plugin first (for WSL environments)
        if self.is_plugin_available():
            try:
                response = requests.post(
                    f"{self.PLUGIN_URL}/launch",
                    json={"game_id": game_id},
                    timeout=5
                )
                result = response.json()
                if result.get("launched"):
                    return {
                        "success": True,
                        "method": "http_plugin",
                        "message": f"Launched {result.get('game_title')}"
                    }
            except Exception as e:
                logger.warning(f"Plugin launch failed: {e}")

        # Fallback to other methods
        return self._launch_fallback(game_id)
```

## Frontend Integration (React)

Update `frontend/src/services/launchboxService.js`:

```javascript
class LaunchBoxService {
  async checkPluginStatus() {
    try {
      const response = await fetch('http://127.0.0.1:31337/health');
      const data = await response.json();
      return data.available;
    } catch {
      return false;
    }
  }

  async launchGame(gameId) {
    // Try backend first (it will use plugin if available)
    try {
      const response = await fetch('/api/launchbox/launch/' + gameId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      return await response.json();
    } catch (error) {
      console.error('Launch failed:', error);
      return { success: false, error: error.message };
    }
  }
}
```

## Gateway Integration (Node.js)

Add to `gateway/routes/launchbox.js`:

```javascript
const axios = require('axios');

router.get('/api/launchbox/plugin/status', async (req, res) => {
  try {
    const response = await axios.get('http://127.0.0.1:31337/health');
    res.json(response.data);
  } catch (error) {
    res.status(503).json({ available: false, error: 'Plugin not running' });
  }
});

router.post('/api/launchbox/launch/:id', async (req, res) => {
  const gameId = req.params.id;

  // Try plugin first
  try {
    const response = await axios.post('http://127.0.0.1:31337/launch', {
      game_id: gameId
    });

    if (response.data.launched) {
      return res.json({
        success: true,
        method: 'http_plugin',
        ...response.data
      });
    }
  } catch (error) {
    console.log('Plugin not available, using fallback');
  }

  // Fallback to Python backend
  try {
    const backendResponse = await axios.post(
      `${process.env.FASTAPI_URL}/api/launchbox/launch/${gameId}`
    );
    res.json(backendResponse.data);
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});
```

## Testing the Integration

### From WSL/Linux:
```bash
# Check plugin
curl http://127.0.0.1:31337/health

# Get games
curl http://127.0.0.1:31337/games

# Launch a game
curl -X POST http://127.0.0.1:31337/launch \
  -H "Content-Type: application/json" \
  -d '{"game_id": "YOUR-GAME-ID"}'
```

### From Frontend:
```javascript
// In browser console
fetch('http://127.0.0.1:31337/health')
  .then(r => r.json())
  .then(console.log)
```

## Architecture Benefits

1. **WSL Compatibility**: Solves the core issue of launching Windows games from WSL
2. **Direct Access**: Bypasses file system translation issues
3. **Performance**: Native Windows execution without WSL overhead
4. **Reliability**: Uses LaunchBox's official plugin API
5. **Security**: Localhost-only connections
6. **Fallback Chain**: Backend can try multiple launch methods

## Troubleshooting

### Plugin Not Responding
- Check LaunchBox is running
- Verify plugin DLL is in `A:\LaunchBox\Plugins\ArcadeAssistant\`
- Check Windows Event Viewer for .NET errors
- Try running `build-simple.bat` again

### Games Not Launching
- Verify game ID is correct (use `/games` endpoint)
- Check LaunchBox can launch the game normally
- Review LaunchBox logs
- Ensure game files exist and are accessible

### Port 31337 In Use
```cmd
netstat -ano | findstr :31337
taskkill /PID <PID> /F
```

## Next Steps

1. **Monitoring**: Add health checks to your monitoring system
2. **Logging**: Integrate plugin logs with your logging infrastructure
3. **Caching**: Cache game list for better performance
4. **Queue**: Implement launch queue for multiple requests
5. **WebSocket**: Add real-time status updates