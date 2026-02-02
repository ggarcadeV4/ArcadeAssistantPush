# Arcade Assistant LaunchBox Plugin Test Script
# Run this after installing the plugin and starting LaunchBox

Write-Host "================================" -ForegroundColor Cyan
Write-Host "Arcade Assistant Plugin Tester" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

$baseUrl = "http://127.0.0.1:31337"

# Function to make API calls with error handling
function Test-Endpoint {
    param(
        [string]$Endpoint,
        [string]$Method = "GET",
        [object]$Body = $null
    )

    try {
        $uri = "$baseUrl$Endpoint"
        Write-Host "Testing: $Method $uri" -ForegroundColor Yellow

        $params = @{
            Uri = $uri
            Method = $Method
            TimeoutSec = 5
        }

        if ($Body) {
            $params.Body = ($Body | ConvertTo-Json)
            $params.ContentType = "application/json"
        }

        $response = Invoke-RestMethod @params
        Write-Host "Success!" -ForegroundColor Green
        return $response
    }
    catch {
        if ($_.Exception.Message -like "*Unable to connect*") {
            Write-Host "ERROR: Cannot connect to plugin server" -ForegroundColor Red
            Write-Host "  - Is LaunchBox running?" -ForegroundColor Yellow
            Write-Host "  - Is the plugin installed in LaunchBox\Plugins\ArcadeAssistant?" -ForegroundColor Yellow
            Write-Host "  - Check LaunchBox logs for plugin errors" -ForegroundColor Yellow
        }
        else {
            Write-Host "ERROR: $_" -ForegroundColor Red
        }
        return $null
    }
}

# Test 1: Health Check
Write-Host ""
Write-Host "TEST 1: Health Check" -ForegroundColor Cyan
Write-Host "-----------------" -ForegroundColor Cyan

$health = Test-Endpoint -Endpoint "/health"
if ($health) {
    Write-Host "  Plugin Available: $($health.available)" -ForegroundColor $(if($health.available){"Green"}else{"Red"})
    Write-Host "  Version: $($health.version)" -ForegroundColor White
    Write-Host "  Uptime: $($health.uptime_seconds) seconds" -ForegroundColor White
    Write-Host "  Requests: $($health.request_count)" -ForegroundColor White
}

# Test 2: Server Status
Write-Host ""
Write-Host "TEST 2: Server Status" -ForegroundColor Cyan
Write-Host "------------------" -ForegroundColor Cyan

$status = Test-Endpoint -Endpoint "/status"
if ($status) {
    Write-Host "  Server Time: $($status.timestamp)" -ForegroundColor White
    Write-Host "  Available: $($status.available)" -ForegroundColor $(if($status.available){"Green"}else{"Red"})
}

# Test 3: Get Sample Games
Write-Host ""
Write-Host "TEST 3: Get Sample Games" -ForegroundColor Cyan
Write-Host "--------------------" -ForegroundColor Cyan

$games = Test-Endpoint -Endpoint "/games"
if ($games) {
    Write-Host "  Total Games in LaunchBox: $($games.total)" -ForegroundColor Green
    Write-Host "  Sample Games:" -ForegroundColor White

    if ($games.sample -and $games.sample.Count -gt 0) {
        foreach ($game in $games.sample[0..2]) {  # Show first 3 games
            Write-Host "    - $($game.title) ($($game.platform)) [$($game.year)]" -ForegroundColor Gray
            Write-Host "      ID: $($game.id)" -ForegroundColor DarkGray
        }

        # Store first game ID for launch test
        $testGameId = $games.sample[0].id
        $testGameTitle = $games.sample[0].title
    }
    else {
        Write-Host "    No games found in LaunchBox!" -ForegroundColor Red
    }
}

# Test 4: Launch Game (if we found games)
if ($testGameId) {
    Write-Host ""
    Write-Host "TEST 4: Launch Game Test" -ForegroundColor Cyan
    Write-Host "--------------------" -ForegroundColor Cyan

    $confirm = Read-Host "Do you want to test launching '$testGameTitle'? (y/n)"
    if ($confirm -eq 'y') {
        $launch = Test-Endpoint -Endpoint "/launch" -Method "POST" -Body @{game_id = $testGameId}
        if ($launch) {
            if ($launch.launched) {
                Write-Host "  Game launched successfully!" -ForegroundColor Green
                Write-Host "  Title: $($launch.game_title)" -ForegroundColor White
                Write-Host "  Platform: $($launch.platform)" -ForegroundColor White
            }
            else {
                Write-Host "  Launch failed: $($launch.error)" -ForegroundColor Red
            }
        }
    }
    else {
        Write-Host "  Launch test skipped" -ForegroundColor Yellow
    }
}

# Test 5: Invalid Request (Error Handling)
Write-Host ""
Write-Host "TEST 5: Error Handling" -ForegroundColor Cyan
Write-Host "------------------" -ForegroundColor Cyan

$invalid = Test-Endpoint -Endpoint "/launch" -Method "POST" -Body @{game_id = "invalid-id"}
if ($invalid) {
    if ($invalid.error) {
        Write-Host "  Error handling works correctly" -ForegroundColor Green
        Write-Host "  Error message: $($invalid.error)" -ForegroundColor Gray
    }
}

# Summary
Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Test Complete!" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

if ($health -and $health.available) {
    Write-Host ""
    Write-Host "Plugin is working correctly!" -ForegroundColor Green
    Write-Host ""
    Write-Host "You can now use the plugin from WSL or any HTTP client:" -ForegroundColor White
    Write-Host '  curl http://127.0.0.1:31337/health' -ForegroundColor Gray
    Write-Host '  curl -X POST http://127.0.0.1:31337/launch -H "Content-Type: application/json" -d "{\"game_id\":\"...\"}"' -ForegroundColor Gray
}
else {
    Write-Host ""
    Write-Host "Plugin is not responding. Please check:" -ForegroundColor Red
    Write-Host "1. LaunchBox is running" -ForegroundColor Yellow
    Write-Host "2. Plugin is installed in LaunchBox\Plugins\ArcadeAssistant\" -ForegroundColor Yellow
    Write-Host "3. No errors in LaunchBox logs" -ForegroundColor Yellow
    Write-Host "4. Port 31337 is not blocked by firewall" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")