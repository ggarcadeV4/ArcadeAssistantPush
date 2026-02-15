# ============================================================================
# 02-RetroArch.ps1 — Self-contained: RetroArch + 27 core profiles
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

# --- RetroArch (Joystick — primary) ---
Write-Host "--- RetroArch ---"
$ra = _EnsureEmu "RetroArch" ($DR + "Emulators\RetroArch")

$cores = @(
    @{ N = "RA: SNES (snes9x)"; C = "snes9x_libretro"; P = @("Super Nintendo") }
    @{ N = "RA: NES (fceumm)"; C = "fceumm_libretro"; P = @("Nintendo Entertainment System") }
    @{ N = "RA: Genesis (genesis_plus)"; C = "genesis_plus_gx_libretro"; P = @("Sega Genesis", "Sega Mega Drive") }
    @{ N = "RA: Game Boy (gambatte)"; C = "gambatte_libretro"; P = @("Nintendo Game Boy", "Nintendo Game Boy Color") }
    @{ N = "RA: GBA (mednafen)"; C = "mednafen_gba_libretro"; P = @("Nintendo Game Boy Advance") }
    @{ N = "RA: N64 (mupen64plus)"; C = "mupen64plus_next_libretro"; P = @("Nintendo 64") }
    @{ N = "RA: NDS (melonDS)"; C = "melonds_libretro"; P = @("Nintendo DS") }
    @{ N = "RA: PSX (duckstation)"; C = "duckstation_libretro"; P = @("Sony PlayStation") }
    @{ N = "RA: PS2 (pcsx2)"; C = "pcsx2_libretro"; P = @("Sony PlayStation 2") }
    @{ N = "RA: PSP (ppsspp)"; C = "ppsspp_libretro"; P = @("Sony PSP") }
    @{ N = "RA: Saturn (kronos)"; C = "kronos_libretro"; P = @("Sega Saturn") }
    @{ N = "RA: Dreamcast (flycast)"; C = "flycast_libretro"; P = @("Sega Dreamcast") }
    @{ N = "RA: Atari 2600 (stella)"; C = "stella_libretro"; P = @("Atari 2600") }
    @{ N = "RA: Atari 7800 (prosystem)"; C = "prosystem_libretro"; P = @("Atari 7800") }
    @{ N = "RA: Lynx (handy)"; C = "handy_libretro"; P = @("Atari Lynx") }
    @{ N = "RA: Jaguar (virtualjaguar)"; C = "virtualjaguar_libretro"; P = @("Atari Jaguar") }
    @{ N = "RA: TG-16 (beetle pce)"; C = "mednafen_pce_fast_libretro"; P = @("NEC TurboGrafx-16") }
    @{ N = "RA: Game Gear (gearsystem)"; C = "gearsystem_libretro"; P = @("Sega Game Gear") }
    @{ N = "RA: Sega 32X (picodrive)"; C = "picodrive_libretro"; P = @("Sega 32X") }
    @{ N = "RA: FBNeo (Arcade)"; C = "fbneo_libretro"; P = @("Arcade") }
    @{ N = "RA: NeoGeo CD"; C = "neocd_libretro"; P = @("SNK Neo Geo CD") }
    @{ N = "RA: Atomiswave (flycast)"; C = "flycast_libretro"; P = @("Atomiswave") }
    @{ N = "RA: NAOMI (flycast)"; C = "flycast_libretro"; P = @("Sega NAOMI") }
    @{ N = "RA: 3DO (opera)"; C = "opera_libretro"; P = @("3DO") }
    @{ N = "RA: Amiga (puae)"; C = "puae_libretro"; P = @("Commodore Amiga") }
    @{ N = "RA: DOSBox (pure)"; C = "dosbox_pure_libretro"; P = @("DOS") }
    @{ N = "RA: ScummVM"; C = "scummvm_libretro"; P = @("ScummVM") }
)

foreach ($c in $cores) {
    $a = '-L "{EmulatorDir}\cores\' + $c.C + '.dll" "{ImagePath}"'
    _AddProfile $ra $c.N '{EmulatorDir}\retroarch.exe' $a $c.P @(".zip", ".7z", ".bin", ".cue", ".iso", ".chd", ".cso")
}

# --- RetroArch Gamepad ---
$raGP = _EnsureEmu "RetroArch Gamepad" ($DR + "Emulators\RetroArch Gamepad")
_AddProfile $raGP "RA GP: Default (snes9x)" '{EmulatorDir}\retroarch.exe' '-L "{EmulatorDir}\cores\snes9x_libretro.dll" "{ImagePath}"' @("Super Nintendo") @(".zip", ".7z", ".sfc", ".smc")

Write-Host "--- RetroArch: Done! ($($cores.Count) profiles) ---"
