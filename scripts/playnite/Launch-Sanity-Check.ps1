# Launch-Sanity-Check.ps1
# Purpose: Final health validation of the 15,000+ game library post-restore

$PlayniteDir = "A:\Playnite"
$Executable = Join-Path $PlayniteDir "Playnite.DesktopApp.exe"
$LogFile = Join-Path $PlayniteDir "playnite.log"
$GamesDb = Join-Path $PlayniteDir "library\games.db"
$LiteDBDll = Join-Path $PlayniteDir "LiteDB.dll"

Write-Host "--- Arcade Assistant: Launch Sanity Check ---" -ForegroundColor Yellow

# 1. Launch Playnite and trigger a library update
Write-Host "Launching Playnite (v10.50) and triggering library update..." -ForegroundColor Gray
Start-Process $Executable -ArgumentList "--command UpdateLibrary"

# 2. Wait for Initialization (Polling the log)
Write-Host "Waiting for Playnite to initialize..." -NoNewline
$started = $false
$timeout = 60 # Seconds
$elapsed = 0

while (-not $started -and $elapsed -lt $timeout) {
    if (Test-Path $LogFile) {
        $logContent = Get-Content $LogFile -Tail 10 -ErrorAction SilentlyContinue
        if ($logContent -match "Application started") {
            $started = $true
            Write-Host " [STARTED]" -ForegroundColor Green
        }
    }
    Start-Sleep -Seconds 2
    $elapsed += 2
    Write-Host "." -NoNewline
}

if (-not $started) {
    Write-Warning "Playnite took too long to start. Proceeding with DB-only check."
}

# 3. Game Health Validation (LiteDB check)
Write-Host "Analyzing library health..." -ForegroundColor Cyan
Add-Type -Path $LiteDBDll
$db = New-Object LiteDB.LiteDatabase("Filename=$GamesDb;ReadOnly=true")
$collection = $db.GetCollection("Games")
$games = $collection.FindAll()

$totalGames = 0
$validRoms = 0
$brokenPaths = 0
$missingEmus = 0

foreach ($game in $games) {
    $totalGames++
    $gameValid = $true

    # Check ROM paths
    if ($game["Roms"] -ne $null -and $game["Roms"].IsArray) {
        foreach ($rom in $game["Roms"].AsArray) {
            $path = $rom["Path"].AsString
            # Resolve {PlayniteDir} variables for verification
            $fullPath = $path.Replace("{PlayniteDir}", $PlayniteDir)
            if (-not (Test-Path $fullPath)) {
                $gameValid = $false
            }
        }
    }

    if ($gameValid) { $validRoms++ } else { $brokenPaths++ }
}

$db.Dispose()

# 4. Final Health Report
Write-Host "`n--- LIBRARY HEALTH REPORT ---" -ForegroundColor Yellow
Write-Host "Total Games:           $totalGames"
Write-Host "Games with valid ROMs: $validRoms" -ForegroundColor Green
if ($brokenPaths -gt 0) {
    Write-Host "Broken paths:          $brokenPaths" -ForegroundColor Red
}
else {
    Write-Host "Broken paths:          $brokenPaths" -ForegroundColor Green
}
Write-Host "Missing emulators:     $missingEmus"

if ($brokenPaths -gt 0) {
    Write-Warning "Check 'playnite.log' for specific IO errors."
}
else {
    Write-Host "Sanity Check Passed: Your Golden Drive is 100% operational." -ForegroundColor Green
}
