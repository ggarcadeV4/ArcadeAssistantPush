# Backup-Creator.ps1
# Purpose: Create a portable 'Golden Backup' of the Playnite environment

param (
    [Parameter(Mandatory = $true)]
    [string]$DestinationPath, # Where to save the backup (e.g., "E:\Backups")
    [string]$PlayniteRoot = "A:\Playnite",
    [switch]$ZipResult # Optional: Compress the backup into a .zip file
)

$Timestamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$BackupFolder = Join-Path $DestinationPath "GoldenBackup_$Timestamp"
$RequiredFolders = @("library", "Metadata", "ExtensionsData")
$ExcludeFiles = @("*.log", "browsercache", "webcache", "cef.log", "debug.log")

Write-Host "--- Arcade Assistant: Golden Exporter ---" -ForegroundColor Yellow

# 1. Verification: Ensure Playnite is offline
if (Get-Process -Name "Playnite.DesktopApp" -ErrorAction SilentlyContinue) {
    Write-Error "Playnite is currently running. Please close it to unlock LiteDB files."
    return
}

# 2. Preparation
if (-not (Test-Path $BackupFolder)) { New-Item -ItemType Directory -Path $BackupFolder | Out-Null }

# 3. Data Collection: Capture the 'Body' and 'Soul'
foreach ($folder in $RequiredFolders) {
    $src = Join-Path $PlayniteRoot $folder
    $dest = Join-Path $BackupFolder $folder

    if (Test-Path $src) {
        Write-Host "Exporting $folder (stripping cache/temp)..." -ForegroundColor Gray
        Copy-Item -Path $src -Destination $dest -Recurse -Force -Exclude $ExcludeFiles
    }
}

# 4. Manifest Creation: Recording Library Stats
Write-Host "Generating Golden Manifest..." -ForegroundColor Cyan
Add-Type -Path (Join-Path $PlayniteRoot "LiteDB.dll")

$gamesDbPath = Join-Path $BackupFolder "library\games.db"
$emusDbPath = Join-Path $BackupFolder "library\emulators.db"
$gameCount = 0
$emuCount = 0

if (Test-Path $gamesDbPath) {
    $db = New-Object LiteDB.LiteDatabase("Filename=$gamesDbPath;ReadOnly=true")
    $gameCount = ($db.GetCollection("Games")).Count()
    $db.Dispose()
}

if (Test-Path $emusDbPath) {
    $db = New-Object LiteDB.LiteDatabase("Filename=$emusDbPath;ReadOnly=true")
    $emuCount = ($db.GetCollection("Emulators")).Count()
    $db.Dispose()
}

$metadataPath = Join-Path $BackupFolder "Metadata"
$mediaSizeGB = "0.00"
if (Test-Path $metadataPath) {
    $mediaSizeGB = ((Get-ChildItem $metadataPath -Recurse | Measure-Object -Property Length -Sum).Sum / 1GB).ToString("F2")
}

$ManifestContent = @"
--- GOLDEN BACKUP MANIFEST ---
Timestamp: $Timestamp
Total Game Entries: $gameCount
Emulator Profiles: $emuCount
Media Size: $mediaSizeGB GB
Source: $PlayniteRoot
"@
$ManifestContent | Out-File (Join-Path $BackupFolder "manifest.txt")
Write-Host $ManifestContent

# 5. Packaging
if ($ZipResult) {
    Write-Host "Compressing Golden Image..." -ForegroundColor Cyan
    Compress-Archive -Path "$BackupFolder\*" -DestinationPath "$BackupFolder.zip" -Force
    Remove-Item $BackupFolder -Recurse -Force
    Write-Host "SUCCESS: Golden Backup compressed to $BackupFolder.zip" -ForegroundColor Green
}
else {
    Write-Host "SUCCESS: Golden Backup created at $BackupFolder" -ForegroundColor Green
}
