# ============================================================================
# 03-Sega.ps1 — Self-contained: Dolphin Tri-Force, Model 2, SuperModel
# ============================================================================
# Just paste this entire block into Playnite PowerShell. No other files needed.
# ============================================================================

if (-not $PlayniteApi) {
    $PlayniteRunspace = Get-Runspace -Name 'PSInteractive'
    $PlayniteApi = $PlayniteRunspace.SessionStateProxy.GetVariable('PlayniteApi')
}
$DriveLetter = Split-Path -Qualifier $PlayniteApi.Paths.ApplicationPath
$DR = $DriveLetter + "\"

function _EnsurePlatform([string]$N) {
    $e = $PlayniteApi.Database.Platforms | Where-Object { $_.Name -eq $N } | Select-Object -First 1
    if ($e) { return $e.Id }
    $p = New-Object Playnite.SDK.Models.Platform -ArgumentList $N
    $PlayniteApi.Database.Platforms.Add($p)
    return $p.Id
}

function _EnsureEmu([string]$N, [string]$D) {
    $e = $PlayniteApi.Database.Emulators | Where-Object { $_.Name -eq $N } | Select-Object -First 1
    if ($e) { Write-Host "  [SKIP] $N exists"; return $e }
    $emu = New-Object Playnite.SDK.Models.Emulator -ArgumentList $N
    $emu.InstallDir = $D
    $PlayniteApi.Database.Emulators.Add($emu)
    Write-Host "  [NEW] $N"
    return $emu
}

function _AddProfile($Emu, [string]$PN, [string]$Exe, [string]$Args, [string[]]$Plats, [string[]]$Exts) {
    if ($Emu.CustomProfiles) {
        $f = $Emu.CustomProfiles | Where-Object { $_.Name -eq $PN }
        if ($f) { Write-Host "    [SKIP] $PN"; return }
    }
    $pids = New-Object 'System.Collections.Generic.List[System.Guid]'
    foreach ($pl in $Plats) { $pids.Add((_EnsurePlatform $pl)) }
    $el = New-Object 'System.Collections.Generic.List[string]'
    foreach ($x in $Exts) { $el.Add($x) }
    $pr = New-Object Playnite.SDK.Models.CustomEmulatorProfile
    $pr.Name = $PN; $pr.Executable = $Exe; $pr.Arguments = $Args
    $pr.Platforms = $pids; $pr.ImageExtensions = $el
    if ($null -eq $Emu.CustomProfiles) {
        $Emu.CustomProfiles = New-Object 'System.Collections.ObjectModel.ObservableCollection[Playnite.SDK.Models.CustomEmulatorProfile]'
    }
    $Emu.CustomProfiles.Add($pr)
    $PlayniteApi.Database.Emulators.Update($Emu)
    Write-Host "    [ADD] $PN"
}

# --- Dolphin Tri-Force ---
Write-Host "--- Sega + Dolphin ---"
$dolphin = _EnsureEmu "Dolphin Tri-Force" ($DR + "Emulators\Dolphin Tri-Force")
_AddProfile $dolphin "Dolphin Default" '{EmulatorDir}\Dolphin.exe' '--exec="{ImagePath}"' @("Nintendo GameCube", "Sega Triforce") @(".iso", ".gcm", ".gcz", ".ciso")

# --- Sega Model 2 ---
$m2 = _EnsureEmu "Sega Model 2" ($DR + "Emulators\Sega Model 2")
_AddProfile $m2 "Model 2 Default" '{EmulatorDir}\EMULATOR.EXE' '"{ImageNameNoExt}"' @("Sega Model 2") @(".zip")

# --- SuperModel (Model 3) ---
$m3 = _EnsureEmu "SuperModel" ($DR + "Emulators\Super Model")
_AddProfile $m3 "Model 3 Default" '{EmulatorDir}\Supermodel.exe' '"{ImagePath}" -fullscreen -new3d -quad-rendering' @("Sega Model 3") @(".zip")

Write-Host "--- Sega + Dolphin: Done! ---"
