<#
.SYNOPSIS
    Sync-GameLibrary.ps1 - Playnite Game Library Hydration + LED Cinema Logic Tagging
.DESCRIPTION
    Scans ROM directories on the Golden Drive (A:\) and injects games into
    Playnite's database with [LED:*] Cinema Logic tags for the aa-blinky Gem.
    Part of: Phase 3 "Gem Architecture" - Arcade Assistant
.PARAMETER DryRun
    If set, only shows what would be done without modifying the database.
.PARAMETER DriveRoot
    Override the drive root (default: $env:AA_DRIVE_ROOT or A:\)
.EXAMPLE
    .\Sync-GameLibrary.ps1 -DryRun
    .\Sync-GameLibrary.ps1
#>

[CmdletBinding()]
param(
    [switch]$DryRun,
    [string]$DriveRoot
)

if (-not $DriveRoot) {
    if ($env:AA_DRIVE_ROOT) {
        $DriveRoot = $env:AA_DRIVE_ROOT
    } else {
        $DriveRoot = "A:\"
    }
}

$ErrorActionPreference = "Stop"

# ============================================================================
# CONFIGURATION
# ============================================================================

$PlayniteRoot = Join-Path $DriveRoot "Playnite"
$PlayniteDB = Join-Path (Join-Path $PlayniteRoot "library") "games.db"
$RomsRoot = Join-Path $DriveRoot "Roms"
$ConsoleROMs = Join-Path $DriveRoot "Console ROMs"
$EmulatorsRoot = Join-Path $DriveRoot "Emulators"
$GenreProfiles = Join-Path (Join-Path (Join-Path (Join-Path $DriveRoot "Arcade Assistant Local") "config") "mappings") "genre_profiles.json"

# ============================================================================
# CINEMA LOGIC: Two-Pass Genre Mapping
# ============================================================================
# catver.ini format: "romname=Genre / Subgenre"
#
# Pass 1 - Exact sub-genre strings (highest priority, catches specific categories)
# Pass 2 - Keyword fallback (catches remaining games by keyword)

# Pass 1: Exact catver.ini sub-genre strings
$ExactGenreMap = [ordered]@{
    # --- LIGHTGUN ---
    "Shooter / Gun"                        = "LED:LIGHTGUN"
    "Shooter / Gallery"                    = "LED:LIGHTGUN"
    "Shooter / Gallery * Mature *"         = "LED:LIGHTGUN"
    "Electromechanical / Lightgun Shooter" = "LED:LIGHTGUN"
    "TTL * Shooter / Gun"                  = "LED:LIGHTGUN"
    "TTL * Shooter / Gallery"              = "LED:LIGHTGUN"
    "Whac-A-Mole / Gun"                    = "LED:LIGHTGUN"
    "Utilities / Light Gun"                = "LED:LIGHTGUN"
    "Sports / Shooting Gallery"            = "LED:LIGHTGUN"
    # --- BEATEMUP ---
    "Fighter / 2.5D"                       = "LED:BEATEMUP"
    "Fighter / Vertical"                   = "LED:BEATEMUP"
    "Platform / Fighter Scrolling"         = "LED:BEATEMUP"
    "Platform / Fighter"                   = "LED:BEATEMUP"
    "Electromechanical / Beat Up"          = "LED:BEATEMUP"
    "Maze / Fighter"                       = "LED:BEATEMUP"
    # --- FIGHTING (Versus-style) ---
    "Fighter / Versus"                     = "LED:FIGHTING"
    "Fighter / Versus Co-op"               = "LED:FIGHTING"
    "Fighter / Versus * Mature *"          = "LED:FIGHTING"
    "Fighter / 2D"                         = "LED:FIGHTING"
    "Fighter / 3D"                         = "LED:FIGHTING"
    "Fighter / Field"                      = "LED:FIGHTING"
    "Fighter / Medieval Tournament"        = "LED:FIGHTING"
    "Fighter / Headbutted"                 = "LED:FIGHTING"
    "Fighter / Misc."                      = "LED:FIGHTING"
    "Fighter / Compilation"                = "LED:FIGHTING"
    "Medal Game / Fighter"                 = "LED:FIGHTING"
    "Whac-A-Mole / Fighter"                = "LED:FIGHTING"
}

# Pass 2: Keyword fallback
$KeywordMap = [ordered]@{
    "Racing"      = "LED:RACING"
    "Driving"     = "LED:RACING"
    "Race"        = "LED:RACING"
    "Motorbike"   = "LED:RACING"
    "Shooter"     = "LED:SHOOTER"
    "Shoot"       = "LED:SHOOTER"
    "Run and Gun" = "LED:SHOOTER"
    "Sports"      = "LED:SPORTS"
    "Wrestling"   = "LED:SPORTS"
    "Baseball"    = "LED:SPORTS"
    "Basketball"  = "LED:SPORTS"
    "Football"    = "LED:SPORTS"
    "Soccer"      = "LED:SPORTS"
    "Tennis"      = "LED:SPORTS"
    "Hockey"      = "LED:SPORTS"
    "Boxing"      = "LED:SPORTS"
    "Bowling"     = "LED:SPORTS"
    "Golf"        = "LED:SPORTS"
    "Track"       = "LED:SPORTS"
    "Platform"    = "LED:PLATFORMER"
    "Platformer"  = "LED:PLATFORMER"
    "Puzzle"      = "LED:PUZZLE"
    "Maze"        = "LED:MAZE"
    "Trackball"   = "LED:TRACKBALL"
}

# ROM platforms to scan
$Platforms = @(
    @{ Name = "Arcade"; Path = (Join-Path $RomsRoot "MAME"); Extensions = @(".zip", ".7z"); Emulator = "MAME" },
    @{ Name = "NES"; Path = (Join-Path $ConsoleROMs "NES"); Extensions = @(".nes", ".zip"); Emulator = "RetroArch" },
    @{ Name = "SNES"; Path = (Join-Path $ConsoleROMs "SNES"); Extensions = @(".sfc", ".smc", ".zip"); Emulator = "RetroArch" },
    @{ Name = "Sega Genesis"; Path = (Join-Path $ConsoleROMs "Sega Genesis"); Extensions = @(".md", ".bin", ".zip"); Emulator = "RetroArch" },
    @{ Name = "Game Boy Advance"; Path = (Join-Path $ConsoleROMs "Game Boy Advance"); Extensions = @(".gba", ".zip"); Emulator = "RetroArch" },
    @{ Name = "Atari 2600"; Path = (Join-Path $ConsoleROMs "Atari 2600"); Extensions = @(".a26", ".bin", ".zip"); Emulator = "RetroArch" },
    @{ Name = "Atari 7800"; Path = (Join-Path $ConsoleROMs "Atari 7800"); Extensions = @(".a78", ".bin", ".zip"); Emulator = "RetroArch" }
)

# ============================================================================
# GENRE DETECTION
# ============================================================================

function Get-MAMEGenre {
    param([string]$RomName)

    $catverPaths = @(
        (Join-Path (Join-Path $EmulatorsRoot "MAME") "catver.ini"),
        (Join-Path (Join-Path (Join-Path $EmulatorsRoot "MAME") "dats") "catver.ini"),
        (Join-Path (Join-Path $EmulatorsRoot "MAME Gamepad") "catver.ini")
    )

    foreach ($catver in $catverPaths) {
        if (Test-Path $catver) {
            $found = Select-String -Path $catver -Pattern "^${RomName}=" | Select-Object -First 1
            if ($found) {
                $genre = ($found.Line -split "=", 2)[1].Trim()
                return $genre
            }
        }
    }

    # Try LaunchBox XML
    $lbPlatformXml = Join-Path (Join-Path (Join-Path (Join-Path $DriveRoot "LaunchBox") "Data") "Platforms") "Arcade.xml"
    if (Test-Path $lbPlatformXml) {
        try {
            [xml]$xml = Get-Content $lbPlatformXml -Raw
            $game = $xml.LaunchBox.Game | Where-Object {
                $_.ApplicationPath -match "$RomName\.(zip|7z)$"
            } | Select-Object -First 1
            if ($game -and $game.Genre) {
                return $game.Genre
            }
        } catch {
            # LaunchBox XML parsing failed, continue
        }
    }

    return "Unknown"
}

function Get-CinemaTag {
    param([string]$Genre)

    # Pass 1: Exact sub-genre match (highest priority)
    foreach ($key in $ExactGenreMap.Keys) {
        if ($Genre -eq $key) {
            return $ExactGenreMap[$key]
        }
    }

    # Pass 2: Keyword fallback
    foreach ($key in $KeywordMap.Keys) {
        if ($Genre -match [regex]::Escape($key)) {
            return $KeywordMap[$key]
        }
    }

    return "LED:STANDARD"
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  ARCADE ASSISTANT - Sync-GameLibrary.ps1" -ForegroundColor Cyan
Write-Host "  Cinema Logic Auto-Tagger v2 (Two-Pass)" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[CHECK] Drive Root: $DriveRoot" -ForegroundColor Yellow
if ($DryRun) {
    Write-Host "[MODE]  DRY RUN - No changes will be made" -ForegroundColor Magenta
}

# Check Playnite
if (-not (Test-Path $PlayniteRoot)) {
    Write-Host "[WARN]  Playnite not found at $PlayniteRoot" -ForegroundColor Red
    Write-Host "        Install Playnite portable to $PlayniteRoot first." -ForegroundColor Red
    Write-Host "        Will still scan ROMs and generate Cinema Logic tags..." -ForegroundColor Yellow
}

# Check genre profiles
if (Test-Path $GenreProfiles) {
    $profiles = Get-Content $GenreProfiles -Raw | ConvertFrom-Json
    $profileKeys = $profiles.profiles.PSObject.Properties.Name -join ", "
    Write-Host "[OK]    Genre Profiles: $profileKeys" -ForegroundColor Green
} else {
    Write-Host "[WARN]  Genre profiles not found at $GenreProfiles" -ForegroundColor Yellow
}

# Check catver.ini
$catverPath = Join-Path (Join-Path $EmulatorsRoot "MAME") "catver.ini"
if (Test-Path $catverPath) {
    $catverLines = (Get-Content $catverPath | Measure-Object).Count
    Write-Host "[OK]    catver.ini: $catverLines lines" -ForegroundColor Green
} else {
    Write-Host "[WARN]  catver.ini not found - MAME ROMs will get LED:STANDARD" -ForegroundColor Yellow
}

Write-Host ""

# Scan each platform
$totalGames = 0
$totalTagged = 0
$results = @()

foreach ($platform in $Platforms) {
    $platformName = $platform.Name
    $romPath = $platform.Path

    if (-not (Test-Path $romPath)) {
        Write-Host "[SKIP]  $platformName - ROM path not found: $romPath" -ForegroundColor DarkGray
        continue
    }

    $roms = Get-ChildItem $romPath -File | Where-Object {
        $platform.Extensions -contains $_.Extension.ToLower()
    }

    $romCount = @($roms).Count
    Write-Host "[SCAN]  $platformName - $romCount ROMs found at $romPath" -ForegroundColor White

    foreach ($rom in $roms) {
        $romName = [System.IO.Path]::GetFileNameWithoutExtension($rom.Name)
        $totalGames++

        # Get genre and Cinema Logic tag
        if ($platformName -eq "Arcade") {
            $genre = Get-MAMEGenre -RomName $romName
        } else {
            $genre = $platformName
        }
        $cinemaTag = Get-CinemaTag -Genre $genre

        if ($cinemaTag -ne "LED:STANDARD") {
            $totalTagged++
        }

        $results += [PSCustomObject]@{
            Platform  = $platformName
            ROM       = $romName
            Genre     = $genre
            CinemaTag = $cinemaTag
            FullPath  = $rom.FullName
            Emulator  = $platform.Emulator
        }
    }
}

# ============================================================================
# OUTPUT SUMMARY
# ============================================================================

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  RESULTS" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Total ROMs scanned:  $totalGames" -ForegroundColor White
Write-Host "  Cinema Logic tagged: $totalTagged" -ForegroundColor Green
Write-Host "  Standard tagged:     $($totalGames - $totalTagged)" -ForegroundColor DarkGray
Write-Host ""

# Tag distribution
$tagGroups = $results | Group-Object CinemaTag | Sort-Object Count -Descending
Write-Host "  Tag Distribution:" -ForegroundColor Yellow
foreach ($group in $tagGroups) {
    $barLen = [Math]::Min($group.Count, 50)
    $bar = ""
    for ($i = 0; $i -lt $barLen; $i++) { $bar += "#" }
    Write-Host "    [$($group.Name)] $($group.Count) $bar" -ForegroundColor White
}

# Export results for Playnite import
$outputPath = Join-Path (Join-Path (Join-Path $DriveRoot "Arcade Assistant Local") "state") "game_library_sync.json"
if (-not $DryRun) {
    $outputDir = Split-Path $outputPath
    if (-not (Test-Path $outputDir)) {
        New-Item -Path $outputDir -ItemType Directory -Force | Out-Null
    }

    $exportData = @{
        timestamp    = (Get-Date).ToString("o")
        drive_root   = $DriveRoot
        total_games  = $totalGames
        total_tagged = $totalTagged
        platforms    = @($results | Group-Object Platform | ForEach-Object {
                @{
                    name  = $_.Name
                    count = $_.Count
                    games = @($_.Group | ForEach-Object {
                            @{
                                rom        = $_.ROM
                                genre      = $_.Genre
                                cinema_tag = $_.CinemaTag
                                path       = $_.FullPath
                                emulator   = $_.Emulator
                            }
                        })
                }
            })
    }

    $exportData | ConvertTo-Json -Depth 5 | Set-Content $outputPath -Encoding UTF8
    Write-Host "  Results exported to: $outputPath" -ForegroundColor Green
} else {
    Write-Host "  [DRY RUN] Would export to: $outputPath" -ForegroundColor Magenta
}

Write-Host ""
Write-Host "  Done! Ready for Playnite database injection." -ForegroundColor Green
Write-Host ""
