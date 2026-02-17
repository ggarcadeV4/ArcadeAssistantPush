# ============================================================
#  Generate-Manifests.ps1
#  Scans A:\Console ROMs and A:\Roms for all platforms,
#  generates pending_import.json for Playnite's import pipeline.
#  
#  Usage: Run this script, then restart Playnite.
#  The extension reads pending_import.json on startup and imports.
#
#  This script travels with Git for use on both dev and basement.
# ============================================================

param(
    [string]$PlaynitePath = "A:\Playnite",
    [string]$ConsoleRomRoot = "A:\Console ROMs",
    [string]$ArcadeRomRoot = "A:\Roms"
)

# --- Platform Definitions ---
# Each entry: DirName (folder on disk), Platform (Playnite platform name), Extensions, Tags, RomRoot
$platforms = @(
    # === Console ROMs ===
    @{ Dir="Nintendo Entertainment System"; Plat="Nintendo Entertainment System"; Ext=@("nes","zip","7z"); Tags=@("[LED:RETRO]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="Nintendo Game Boy"; Plat="Nintendo Game Boy"; Ext=@("gb","gbc","zip","7z"); Tags=@("[LED:RETRO]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="Nintendo Game Boy Advance"; Plat="Nintendo Game Boy Advance"; Ext=@("gba","zip","7z"); Tags=@("[LED:RETRO]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="Nintendo 64"; Plat="Nintendo 64"; Ext=@("n64","z64","v64","zip","7z"); Tags=@("[LED:CONSOLE]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="snes"; Plat="Super Nintendo Entertainment System"; Ext=@("sfc","smc","zip","7z"); Tags=@("[LED:RETRO]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="megadrive"; Plat="Sega Mega Drive/Genesis"; Ext=@("md","bin","gen","zip","7z"); Tags=@("[LED:RETRO]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="Sega Genesis"; Plat="Sega Genesis"; Ext=@("md","bin","gen","smd","zip","7z"); Tags=@("[LED:RETRO]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="Sega Dreamcast"; Plat="Sega Dreamcast"; Ext=@("cdi","gdi","chd","zip","7z"); Tags=@("[LED:CONSOLE]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="Sega Game Gear"; Plat="Sega Game Gear"; Ext=@("gg","zip","7z"); Tags=@("[LED:RETRO]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="Sega 32X"; Plat="Sega 32X"; Ext=@("32x","zip","7z"); Tags=@("[LED:RETRO]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="Atari 2600"; Plat="Atari 2600"; Ext=@("a26","bin","zip","7z"); Tags=@("[LED:RETRO]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="Atari 7800"; Plat="Atari 7800"; Ext=@("a78","bin","zip","7z"); Tags=@("[LED:RETRO]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="Atari Jaguar"; Plat="Atari Jaguar"; Ext=@("j64","jag","zip","7z"); Tags=@("[LED:CONSOLE]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="Atari Lynx"; Plat="Atari Lynx"; Ext=@("lnx","zip","7z"); Tags=@("[LED:RETRO]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="NEC Turbografx-16"; Plat="NEC TurboGrafx-16"; Ext=@("pce","zip","7z"); Tags=@("[LED:RETRO]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="playstation"; Plat="Sony PlayStation"; Ext=@("bin","cue","img","mdf","pbp","chd","zip","7z"); Tags=@("[LED:CONSOLE]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="playstation 2"; Plat="Sony PlayStation 2"; Ext=@("iso","bin","chd","gz","zip","7z"); Tags=@("[LED:CONSOLE]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="psp"; Plat="Sony PSP"; Ext=@("iso","cso","pbp","zip","7z"); Tags=@("[LED:CONSOLE]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="nds"; Plat="Nintendo DS"; Ext=@("nds","zip","7z"); Tags=@("[LED:CONSOLE]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="Nintendo Games Cube"; Plat="Nintendo GameCube"; Ext=@("iso","gcm","gcz","ciso","wbfs","rvz"); Tags=@("[LED:CONSOLE]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="Ninendo WiiU"; Plat="Nintendo Wii U"; Ext=@("wud","wux","rpx","wua"); Tags=@("[LED:CONSOLE]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="playstation 3"; Plat="Sony PlayStation 3"; Ext=@("iso","bin","pkg"); Tags=@("[LED:CONSOLE]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    @{ Dir="Sony PlayStation Minis"; Plat="Sony PlayStation Minis"; Ext=@("pbp","iso","zip","7z"); Tags=@("[LED:CONSOLE]","[INPUT:GAMEPAD]"); Root=$ConsoleRomRoot }
    
    # === Arcade ROMs ===
    @{ Dir="ATOMISWAVE"; Plat="Atomiswave"; Ext=@("zip","7z","bin"); Tags=@("[LED:STANDARD]","[INPUT:LIGHTGUN]"); Root=$ArcadeRomRoot }
    @{ Dir="NAOMI"; Plat="Sega NAOMI"; Ext=@("zip","7z","bin","dat","lst"); Tags=@("[LED:STANDARD]","[INPUT:LIGHTGUN]"); Root=$ArcadeRomRoot }
)

# --- Clean name function ---
function Get-CleanGameName {
    param([string]$FileName)
    $name = [System.IO.Path]::GetFileNameWithoutExtension($FileName)
    # Remove common ROM naming artifacts: (U), [!], (Rev 1), etc.
    $name = $name -replace '\s*[\(\[].*?[\)\]]', ''
    $name = $name.Trim()
    # Replace underscores and hyphens with spaces
    $name = $name -replace '_', ' '
    # Clean up multiple spaces
    $name = $name -replace '\s+', ' '
    return $name.Trim()
}

# --- Scan and generate ---
$allGames = @()
$stats = @()

foreach ($p in $platforms) {
    $dir = Join-Path $p.Root $p.Dir
    if (-not (Test-Path $dir)) {
        Write-Host "SKIP: $($p.Dir) - directory not found" -ForegroundColor Yellow
        continue
    }
    
    $files = Get-ChildItem $dir -File -Recurse -ErrorAction SilentlyContinue | Where-Object {
        $p.Ext -contains $_.Extension.TrimStart('.').ToLower()
    }
    
    $count = 0
    foreach ($f in $files) {
        $gameName =  Get-CleanGameName $f.Name
        if ([string]::IsNullOrWhiteSpace($gameName)) { continue }
        
        $allGames += @{
            name = $gameName
            platform = $p.Plat
            romName = $f.Name
            romPath = $f.FullName
            tags = $p.Tags
        }
        $count++
    }
    
    $stats += @{ Platform = $p.Plat; Dir = $p.Dir; Count = $count }
    Write-Host "OK: $($p.Plat) - $count games" -ForegroundColor Green
}

# --- Write manifest ---
$manifest = @{
    batchId = "mass-import-$(Get-Date -Format 'yyyy-MM-dd-HHmm')"
    games = $allGames
}

$outPath = Join-Path $PlaynitePath "pending_import.json"
$manifest | ConvertTo-Json -Depth 5 | Out-File $outPath -Encoding UTF8 -Force

Write-Host "`n=== MANIFEST GENERATED ===" -ForegroundColor Cyan
Write-Host "Output: $outPath" -ForegroundColor Cyan
Write-Host "Total games: $($allGames.Count)" -ForegroundColor Cyan
Write-Host "`nPlatform breakdown:"
foreach ($s in $stats | Sort-Object { $_.Count } -Descending) {
    Write-Host "  $($s.Platform): $($s.Count)"
}
Write-Host "`nRestart Playnite to import." -ForegroundColor Green
