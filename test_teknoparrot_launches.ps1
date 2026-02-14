# TeknoParrot Launch Test Script (PowerShell)
# Tests multiple Taito Type X games to verify profile alias mappings work correctly

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "TeknoParrot Launch Verification Script" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

$BACKEND_URL = "http://localhost:8888"

# Test games - diverse selection to verify different profile types
$TEST_GAMES = @(
    "Akai Katana Shin",
    "BlazBlue: Central Fiction",
    "Street Fighter V",
    "Raiden IV",
    "Ikaruga"
)

Write-Host "Step 1: Checking backend health..." -ForegroundColor Blue
try {
    $health = Invoke-RestMethod -Uri "$BACKEND_URL/health" -Method Get -ErrorAction Stop
    Write-Host "✓ Backend is running" -ForegroundColor Green
    Write-Host ($health | ConvertTo-Json)
} catch {
    Write-Host "✗ Backend is not responding!" -ForegroundColor Red
    Write-Host "Please start the backend with: python backend/app.py" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

Write-Host "Step 2: Fetching Taito Type X games from LaunchBox..." -ForegroundColor Blue
try {
    $gamesResponse = Invoke-RestMethod -Uri "$BACKEND_URL/api/launchbox/games?platform=Taito%20Type%20X&limit=100" -Method Get
    $gameCount = $gamesResponse.games.Count

    if ($gameCount -eq 0) {
        Write-Host "✗ No Taito Type X games found!" -ForegroundColor Red
        exit 1
    }

    Write-Host "✓ Found $gameCount Taito Type X games" -ForegroundColor Green
} catch {
    Write-Host "✗ Failed to fetch games: $_" -ForegroundColor Red
    exit 1
}
Write-Host ""

Write-Host "Step 3: Testing launch resolution for selected games..." -ForegroundColor Blue
Write-Host "This will show the command that would be executed (dry-run mode)" -ForegroundColor Gray
Write-Host ""

$successCount = 0
$failCount = 0

foreach ($gameTitle in $TEST_GAMES) {
    Write-Host "Testing: $gameTitle" -ForegroundColor Yellow

    # Find the game ID
    $game = $gamesResponse.games | Where-Object { $_.title -eq $gameTitle } | Select-Object -First 1

    if (-not $game) {
        Write-Host "  ✗ Game not found in LaunchBox" -ForegroundColor Red
        $failCount++
        Write-Host ""
        continue
    }

    Write-Host "  Game ID: $($game.id)"

    # Test the launch endpoint
    try {
        $launchResponse = Invoke-RestMethod -Uri "$BACKEND_URL/api/launchbox/launch/$($game.id)" `
            -Method Post `
            -ContentType "application/json" `
            -ErrorAction Stop

        if ($launchResponse.success) {
            Write-Host "  ✓ Launch resolved successfully" -ForegroundColor Green
            Write-Host "  Method: $($launchResponse.method)"

            if ($launchResponse.exe -and $launchResponse.args) {
                $cmd = "$($launchResponse.exe) $($launchResponse.args -join ' ')"
                if ($cmd.Length -gt 200) {
                    $cmd = $cmd.Substring(0, 200) + "..."
                }
                Write-Host "  Command: $cmd"
            }

            $successCount++
        } else {
            Write-Host "  ✗ Launch failed" -ForegroundColor Red
            Write-Host "  Error: $($launchResponse.message)"
            $failCount++
        }
    } catch {
        Write-Host "  ✗ Launch request failed: $_" -ForegroundColor Red
        $failCount++
    }

    Write-Host ""
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Test Summary" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Total Tests: $($TEST_GAMES.Count)"
Write-Host "Successful: $successCount" -ForegroundColor Green
Write-Host "Failed: $failCount" -ForegroundColor Red
Write-Host ""

if ($failCount -eq 0) {
    Write-Host "🎉 All tests passed!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Open LaunchBox LoRa panel in browser (http://localhost:8787)"
    Write-Host "2. Filter by platform: Taito Type X"
    Write-Host "3. Click any game to launch it"
    Write-Host "4. TeknoParrot should open with the correct profile loaded"
} else {
    Write-Host "⚠ Some tests failed. Check the errors above." -ForegroundColor Yellow
    exit 1
}
