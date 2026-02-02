# Test LaunchBox platform launching
$platforms = @(
    "Arcade MAME",
    "Nintendo Entertainment System",
    "Super Nintendo Entertainment System", 
    "Sega Genesis",
    "Sony Playstation",
    "Sony Playstation 2",
    "Atari 2600",
    "Nintendo GameCube",
    "Sega Dreamcast",
    "TeknoParrot Arcade"
)

Write-Host "Testing LaunchBox Platform Launching..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

foreach ($platform in $platforms) {
    Write-Host "Platform: $platform" -ForegroundColor Yellow
    
    # Get one game from this platform
    $encodedPlatform = [System.Web.HttpUtility]::UrlEncode($platform)
    $gamesJson = curl.exe -s -m 5 "http://localhost:8000/api/launchbox/games?platform=$encodedPlatform&limit=1"
    
    if ($gamesJson) {
        $games = $gamesJson | ConvertFrom-Json
        if ($games.Count -gt 0) {
            $game = $games[0]
            Write-Host "  Game: $($game.title)" -ForegroundColor White
            Write-Host "  ID: $($game.id)" -ForegroundColor Gray
            Write-Host "  Path: $($game.application_path)" -ForegroundColor Gray
            
            # Try to launch
            $launchResult = curl.exe -s -m 10 -X POST "http://localhost:8000/api/launchbox/launch/$($game.id)" -H "x-panel: launchbox"
            $result = $launchResult | ConvertFrom-Json
            
            if ($result.success) {
                Write-Host "  ✅ Launch: SUCCESS via $($result.method_used)" -ForegroundColor Green
                Write-Host "  Command: $($result.command)" -ForegroundColor DarkGray
            } else {
                Write-Host "  ❌ Launch: FAILED - $($result.message)" -ForegroundColor Red
            }
        } else {
            Write-Host "  ⚠️  No games found for this platform" -ForegroundColor DarkYellow
        }
    } else {
        Write-Host "  ❌ Failed to fetch games" -ForegroundColor Red
    }
    
    Write-Host ""
}

Write-Host "Test complete!" -ForegroundColor Cyan
