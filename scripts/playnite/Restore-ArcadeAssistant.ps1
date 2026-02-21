param (
    [Parameter(Mandatory = $true)]
    [string]$BackupSourcePath, # Folder containing 'library', 'Metadata', 'ExtensionsData'
    [string]$SourceDriveLetter = "D:\"
)

$TargetRoot = "A:\Playnite"
$RequiredFolders = @("library", "Metadata", "ExtensionsData")

# 14 Arcade and 24 Console directories to verify
$ArcadeDirs = @("MAME", "Model 2", "Model 3", "Taito Type X", "Atomiswave", "Naomi", "Naomi 2", "Sega Hikaru", "Sega Lindbergh", "Sega Nu", "Nesica", "Teknoparrot", "Konami PC", "Sammy Atomiswave")
$ConsoleDirs = @("NES", "SNES", "N64", "GameCube", "Wii", "Game Boy", "GBA", "DS", "Genesis", "Saturn", "Dreamcast", "PlayStation", "PS2", "PSP", "TurboGrafx-16", "Neo Geo", "Atari 2600", "Atari 7800", "Master System", "Game Gear", "ColecoVision", "Intellivision", "3DO", "Jaguar")

Write-Host "--- Arcade Assistant One-Click Restore ---" -ForegroundColor Yellow

# 1. Folder Migration
foreach ($folder in $RequiredFolders) {
    $src = Join-Path $BackupSourcePath $folder
    $dest = Join-Path $TargetRoot $folder

    if (Test-Path $src) {
        Write-Host "Restoring $folder..." -ForegroundColor Gray
        if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
        Copy-Item $src $dest -Recurse -Force
    }
    else {
        Write-Warning "Critical: Source folder $folder not found in backup!"
    }
}

# 2. Path Remediation (Direct LiteDB Access)
Write-Host "Starting Path Remediation..." -ForegroundColor Yellow
& "$PSScriptRoot\Fix-ArcadePaths.ps1" -SourceDrive $SourceDriveLetter -TargetDrive "A:\" -PlayniteRoot $TargetRoot

# 3. Post-Restore Verification
Write-Host "`n--- Verification: Checking Drive A Structure ---" -ForegroundColor Cyan
$missingCount = 0

Write-Host "[Checking Arcade ROMs...]"
foreach ($dir in $ArcadeDirs) {
    $path = "A:\Roms\$dir"
    if (-not (Test-Path $path)) { Write-Warning "Missing: $path"; $missingCount++ }
}

Write-Host "[Checking Console ROMs...]"
foreach ($dir in $ConsoleDirs) {
    $path = "A:\Console ROMs\$dir"
    if (-not (Test-Path $path)) { Write-Warning "Missing: $path"; $missingCount++ }
}

if ($missingCount -eq 0) {
    Write-Host "SUCCESS: All 38 ROM directories verified on A:\." -ForegroundColor Green
    Write-Host "Library is ready for use." -ForegroundColor Green
}
else {
    Write-Error "Verification Failed: $missingCount directories were not found. Check Drive A mounting."
}
