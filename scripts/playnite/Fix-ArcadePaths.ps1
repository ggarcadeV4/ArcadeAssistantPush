param (
    [Parameter(Mandatory = $true)]
    [string]$SourceDrive, # e.g., "D:\"
    [string]$TargetDrive = "A:\",
    [string]$PlayniteRoot = "A:\Playnite"
)

# 1. Load the LiteDB Engine from the portable install path
$LiteDBDll = Join-Path $PlayniteRoot "LiteDB.dll"
if (-not (Test-Path $LiteDBDll)) { 
    Write-Error "LiteDB.dll not found at $LiteDBDll. Check your PlayniteRoot path."
    return 
}
Add-Type -Path $LiteDBDll

$LibraryPath = Join-Path $PlayniteRoot "library"

function Update-LiteDBCollection {
    param($DbFile, $CollectionName, $PathFields)
    
    if (-not (Test-Path $DbFile)) { return 0 }

    Write-Host "Surgical Fix: $CollectionName in $(Split-Path $DbFile -Leaf)..." -ForegroundColor Cyan
    # Open DB in Exclusive mode to ensure a clean write
    $db = New-Object LiteDB.LiteDatabase("Filename=$DbFile;Mode=Exclusive")
    $collection = $db.GetCollection($CollectionName)
    $docs = $collection.FindAll()
    $fixCount = 0

    foreach ($doc in $docs) {
        $modified = $false
        foreach ($field in $PathFields) {
            # Fix standard string fields like 'InstallDirectory'
            if ($doc[$field] -ne $null -and $doc[$field].IsString -and $doc[$field].AsString.StartsWith($SourceDrive)) {
                $doc[$field] = $doc[$field].AsString.Replace($SourceDrive, $TargetDrive)
                $modified = $true
            }
            
            # Deep dive into 'Roms' BSON array (Game documents only)
            if ($field -eq "Roms" -and $doc["Roms"] -ne $null -and $doc["Roms"].IsArray) {
                foreach ($rom in $doc["Roms"].AsArray) {
                    if ($rom["Path"].AsString.StartsWith($SourceDrive)) {
                        $rom["Path"] = $rom["Path"].AsString.Replace($SourceDrive, $TargetDrive)
                        $modified = $true
                    }
                }
            }
        }

        if ($modified) {
            $collection.Update($doc)
            $fixCount++
        }
    }
    $db.Dispose()
    return $fixCount
}

# 2. Execute Path Fixes
try {
    # Fix Emulators: Targets 'InstallDirectory' within 'Emulators' collection
    $emuFixes = Update-LiteDBCollection -DbFile "$LibraryPath\emulators.db" `
        -CollectionName "Emulators" -PathFields @("InstallDirectory")

    # Fix Games: Targets 'InstallDirectory' and nested 'Roms' array
    $gameFixes = Update-LiteDBCollection -DbFile "$LibraryPath\games.db" `
        -CollectionName "Games" -PathFields @("InstallDirectory", "Roms")

    Write-Host "`n--- Database Remediation Complete ---" -ForegroundColor Green
    Write-Host "Fixed Emulator Profiles: $emuFixes"
    Write-Host "Fixed Game ROM Paths:    $gameFixes"
    Write-Host "Paths standardized to:   $TargetDrive"
}
catch {
    Write-Error "Database update failed: $_"
}
