# ============================================================================
# 00-Helpers.ps1 — Shared functions (RUN THIS FIRST)
# ============================================================================
# Paste this into Playnite Interactive PowerShell BEFORE any other module.
# ============================================================================

$PlayniteRoot = $PlayniteApi.Paths.ApplicationPath
$DriveLetter = (Split-Path -Qualifier $PlayniteRoot)
$global:DriveRoot = $DriveLetter + "\"

function Ensure-Platform {
    param([string]$Name)
    $existing = $PlayniteApi.Database.Platforms | Where-Object { $_.Name -eq $Name } | Select-Object -First 1
    if ($existing) { return $existing.Id }
    $platform = New-Object Playnite.SDK.Models.Platform -ArgumentList $Name
    $PlayniteApi.Database.Platforms.Add($platform)
    Write-Host "  [Platform] Created: $Name"
    return $platform.Id
}

function Ensure-Emulator {
    param([string]$Name, [string]$InstallDir)
    $existing = $PlayniteApi.Database.Emulators | Where-Object { $_.Name -eq $Name } | Select-Object -First 1
    if ($existing) {
        Write-Host "  [SKIP] Emulator '$Name' already exists"
        return $existing
    }
    $emu = New-Object Playnite.SDK.Models.Emulator -ArgumentList $Name
    $emu.InstallDir = $InstallDir
    $PlayniteApi.Database.Emulators.Add($emu)
    Write-Host "  [NEW] Emulator: $Name"
    return $emu
}

function Add-CustomProfile {
    param(
        [object]$Emulator,
        [string]$ProfileName,
        [string]$Executable,
        [string]$Arguments,
        [string[]]$PlatformNames,
        [string[]]$ImageExtensions
    )
    if ($Emulator.CustomProfiles -and $Emulator.CustomProfiles.Count -gt 0) {
        $found = $Emulator.CustomProfiles | Where-Object { $_.Name -eq $ProfileName }
        if ($found) {
            Write-Host "    [SKIP] Profile '$ProfileName'"
            return
        }
    }
    $platformIds = New-Object 'System.Collections.Generic.List[System.Guid]'
    foreach ($pName in $PlatformNames) {
        $pid = Ensure-Platform -Name $pName
        $platformIds.Add($pid)
    }
    $extList = New-Object 'System.Collections.Generic.List[string]'
    foreach ($ext in $ImageExtensions) { $extList.Add($ext) }
    $profile = New-Object Playnite.SDK.Models.CustomEmulatorProfile
    $profile.Name = $ProfileName
    $profile.Executable = $Executable
    $profile.Arguments = $Arguments
    $profile.Platforms = $platformIds
    $profile.ImageExtensions = $extList
    if ($null -eq $Emulator.CustomProfiles) {
        $Emulator.CustomProfiles = New-Object 'System.Collections.ObjectModel.ObservableCollection[Playnite.SDK.Models.CustomEmulatorProfile]'
    }
    $Emulator.CustomProfiles.Add($profile)
    $PlayniteApi.Database.Emulators.Update($Emulator)
    Write-Host "    [ADD] Profile: $ProfileName"
}

Write-Host "=== Helpers loaded. DriveRoot: $global:DriveRoot ==="
Write-Host "Ready! Paste the next module (01, 02, etc.)"
