# ============================================================================
# Initialize-Arcade.ps1 — Infrastructure as Code for Playnite
# ============================================================================
#
# PURPOSE:  Programmatically create all Emulator profiles and ROM scan
#           configurations inside a blank portable Playnite installation.
#
# USAGE:    Playnite → Main Menu → Extensions → Interactive PowerShell
#           Then paste this script and press Enter.
#
# DESIGN:   - All paths use relative {EmulatorDir} for portability
#           - Drive letter is resolved from Playnite's install location
#           - Script is idempotent — re-running won't create duplicates
#
# REQUIRES: $PlayniteApi (available inside Playnite scripting context)
# ============================================================================

# --- Resolve drive root from Playnite's install location ---
$PlayniteRoot = $PlayniteApi.Paths.ApplicationPath
$DriveLetter = (Split-Path -Qualifier $PlayniteRoot)
$DriveRoot = $DriveLetter + "\"

$script:__log = @()
function Log([string]$msg) {
    $script:__log += "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Write-Host $msg
}

# ============================================================================
# HELPER: Get or create a Platform, return its Id (Guid)
# ============================================================================
function Ensure-Platform {
    param([string]$Name)

    $existing = $PlayniteApi.Database.Platforms | Where-Object { $_.Name -eq $Name } | Select-Object -First 1
    if ($existing) {
        return $existing.Id
    }

    $platform = New-Object Playnite.SDK.Models.Platform -ArgumentList $Name
    $PlayniteApi.Database.Platforms.Add($platform)
    Log "  [Platform] Created: $Name"
    return $platform.Id
}

# ============================================================================
# HELPER: Create or get an Emulator by name (idempotent)
# ============================================================================
function Ensure-Emulator {
    param(
        [string]$Name,
        [string]$InstallDir
    )

    $existing = $PlayniteApi.Database.Emulators | Where-Object { $_.Name -eq $Name } | Select-Object -First 1
    if ($existing) {
        Log "  [SKIP] Emulator '$Name' already exists"
        return $existing
    }

    $emu = New-Object Playnite.SDK.Models.Emulator -ArgumentList $Name
    $emu.InstallDir = $InstallDir
    $PlayniteApi.Database.Emulators.Add($emu)
    Log "  [NEW] Created emulator: $Name"
    return $emu
}

# ============================================================================
# HELPER: Add a Custom Emulator Profile (idempotent)
# ============================================================================
function Add-CustomProfile {
    param(
        [object]$Emulator,
        [string]$ProfileName,
        [string]$Executable,
        [string]$Arguments,
        [string[]]$PlatformNames,
        [string[]]$ImageExtensions
    )

    # Check if profile already exists
    if ($Emulator.CustomProfiles -and $Emulator.CustomProfiles.Count -gt 0) {
        $found = $Emulator.CustomProfiles | Where-Object { $_.Name -eq $ProfileName }
        if ($found) {
            Log "    [SKIP] Profile '$ProfileName' already exists"
            return
        }
    }

    # Resolve platform GUIDs
    $platformIds = New-Object 'System.Collections.Generic.List[System.Guid]'
    foreach ($pName in $PlatformNames) {
        $pid = Ensure-Platform -Name $pName
        $platformIds.Add($pid)
    }

    # Build extensions list
    $extList = New-Object 'System.Collections.Generic.List[string]'
    foreach ($ext in $ImageExtensions) {
        $extList.Add($ext)
    }

    # Create the profile
    $profile = New-Object Playnite.SDK.Models.CustomEmulatorProfile
    $profile.Name = $ProfileName
    $profile.Executable = $Executable
    $profile.Arguments = $Arguments
    $profile.Platforms = $platformIds
    $profile.ImageExtensions = $extList

    # Initialize CustomProfiles if null
    if ($null -eq $Emulator.CustomProfiles) {
        $Emulator.CustomProfiles = New-Object 'System.Collections.ObjectModel.ObservableCollection[Playnite.SDK.Models.CustomEmulatorProfile]'
    }

    $Emulator.CustomProfiles.Add($profile)
    $PlayniteApi.Database.Emulators.Update($Emulator)
    Log "    [ADD] Profile: $ProfileName"
}

# ============================================================================
# EMULATOR DEFINITIONS
# ============================================================================

Log "=== Arcade Assistant: Initialize-Arcade.ps1 ==="
Log "Drive Root: $DriveRoot"
Log ""
Log "--- Phase 1: Creating Emulators & Profiles ---"

# --- 1. MAME (Joystick — primary cabinet config) ---
$mame = Ensure-Emulator -Name "MAME" -InstallDir ($DriveRoot + "Emulators\MAME")
Add-CustomProfile -Emulator $mame `
    -ProfileName "MAME Default" `
    -Executable '{EmulatorDir}\mame.exe' `
    -Arguments '{ImageNameNoExt}' `
    -PlatformNames @("Arcade") `
    -ImageExtensions @(".zip", ".7z", ".chd")

# --- 2. MAME Gamepad ---
$mameGP = Ensure-Emulator -Name "MAME Gamepad" -InstallDir ($DriveRoot + "Emulators\MAME Gamepad")
Add-CustomProfile -Emulator $mameGP `
    -ProfileName "MAME Gamepad Default" `
    -Executable '{EmulatorDir}\mame.exe' `
    -Arguments '{ImageNameNoExt}' `
    -PlatformNames @("Arcade") `
    -ImageExtensions @(".zip", ".7z", ".chd")

# --- 3. RetroArch (Joystick — primary) ---
$ra = Ensure-Emulator -Name "RetroArch" -InstallDir ($DriveRoot + "Emulators\RetroArch")

# RetroArch profiles per core/platform family
$retroArchProfiles = @(
    @{ Name = "RA: SNES (snes9x)"; Core = "snes9x_libretro"; Platforms = @("Super Nintendo") }
    @{ Name = "RA: NES (fceumm)"; Core = "fceumm_libretro"; Platforms = @("Nintendo Entertainment System") }
    @{ Name = "RA: Genesis (genesis_plus)"; Core = "genesis_plus_gx_libretro"; Platforms = @("Sega Genesis", "Sega Mega Drive") }
    @{ Name = "RA: Game Boy (gambatte)"; Core = "gambatte_libretro"; Platforms = @("Nintendo Game Boy", "Nintendo Game Boy Color") }
    @{ Name = "RA: GBA (mednafen)"; Core = "mednafen_gba_libretro"; Platforms = @("Nintendo Game Boy Advance") }
    @{ Name = "RA: N64 (mupen64plus)"; Core = "mupen64plus_next_libretro"; Platforms = @("Nintendo 64") }
    @{ Name = "RA: NDS (melonDS)"; Core = "melonds_libretro"; Platforms = @("Nintendo DS") }
    @{ Name = "RA: PSX (duckstation)"; Core = "duckstation_libretro"; Platforms = @("Sony PlayStation") }
    @{ Name = "RA: PS2 (pcsx2)"; Core = "pcsx2_libretro"; Platforms = @("Sony PlayStation 2") }
    @{ Name = "RA: PSP (ppsspp)"; Core = "ppsspp_libretro"; Platforms = @("Sony PSP") }
    @{ Name = "RA: Saturn (kronos)"; Core = "kronos_libretro"; Platforms = @("Sega Saturn") }
    @{ Name = "RA: Dreamcast (flycast)"; Core = "flycast_libretro"; Platforms = @("Sega Dreamcast") }
    @{ Name = "RA: Atari 2600 (stella)"; Core = "stella_libretro"; Platforms = @("Atari 2600") }
    @{ Name = "RA: Atari 7800 (prosystem)"; Core = "prosystem_libretro"; Platforms = @("Atari 7800") }
    @{ Name = "RA: Lynx (handy)"; Core = "handy_libretro"; Platforms = @("Atari Lynx") }
    @{ Name = "RA: Jaguar (virtualjaguar)"; Core = "virtualjaguar_libretro"; Platforms = @("Atari Jaguar") }
    @{ Name = "RA: TG-16 (beetle pce)"; Core = "mednafen_pce_fast_libretro"; Platforms = @("NEC TurboGrafx-16") }
    @{ Name = "RA: Game Gear (gearsystem)"; Core = "gearsystem_libretro"; Platforms = @("Sega Game Gear") }
    @{ Name = "RA: Sega 32X (picodrive)"; Core = "picodrive_libretro"; Platforms = @("Sega 32X") }
    @{ Name = "RA: FBNeo (Arcade)"; Core = "fbneo_libretro"; Platforms = @("Arcade") }
    @{ Name = "RA: NeoGeo CD"; Core = "neocd_libretro"; Platforms = @("SNK Neo Geo CD") }
    @{ Name = "RA: Atomiswave (flycast)"; Core = "flycast_libretro"; Platforms = @("Atomiswave") }
    @{ Name = "RA: NAOMI (flycast)"; Core = "flycast_libretro"; Platforms = @("Sega NAOMI") }
    @{ Name = "RA: 3DO (opera)"; Core = "opera_libretro"; Platforms = @("3DO") }
    @{ Name = "RA: Amiga (puae)"; Core = "puae_libretro"; Platforms = @("Commodore Amiga") }
    @{ Name = "RA: DOSBox (pure)"; Core = "dosbox_pure_libretro"; Platforms = @("DOS") }
    @{ Name = "RA: ScummVM"; Core = "scummvm_libretro"; Platforms = @("ScummVM") }
)

foreach ($rp in $retroArchProfiles) {
    $coreArg = '-L "{EmulatorDir}\cores\' + $rp.Core + '.dll" "{ImagePath}"'
    Add-CustomProfile -Emulator $ra `
        -ProfileName $rp.Name `
        -Executable '{EmulatorDir}\retroarch.exe' `
        -Arguments $coreArg `
        -PlatformNames $rp.Platforms `
        -ImageExtensions @(".zip", ".7z", ".bin", ".cue", ".iso", ".chd", ".cso")
}

# --- 4. RetroArch Gamepad ---
$raGP = Ensure-Emulator -Name "RetroArch Gamepad" -InstallDir ($DriveRoot + "Emulators\RetroArch Gamepad")
Add-CustomProfile -Emulator $raGP `
    -ProfileName "RA GP: Default (snes9x)" `
    -Executable '{EmulatorDir}\retroarch.exe' `
    -Arguments '-L "{EmulatorDir}\cores\snes9x_libretro.dll" "{ImagePath}"' `
    -PlatformNames @("Super Nintendo") `
    -ImageExtensions @(".zip", ".7z", ".sfc", ".smc")

# --- 5. Dolphin Tri-Force ---
$dolphin = Ensure-Emulator -Name "Dolphin Tri-Force" -InstallDir ($DriveRoot + "Emulators\Dolphin Tri-Force")
Add-CustomProfile -Emulator $dolphin `
    -ProfileName "Dolphin Default" `
    -Executable '{EmulatorDir}\Dolphin.exe' `
    -Arguments '--exec="{ImagePath}"' `
    -PlatformNames @("Nintendo GameCube", "Sega Triforce") `
    -ImageExtensions @(".iso", ".gcm", ".gcz", ".ciso")

# --- 6. Sega Model 2 ---
$model2 = Ensure-Emulator -Name "Sega Model 2" -InstallDir ($DriveRoot + "Emulators\Sega Model 2")
Add-CustomProfile -Emulator $model2 `
    -ProfileName "Model 2 Default" `
    -Executable '{EmulatorDir}\EMULATOR.EXE' `
    -Arguments '"{ImageNameNoExt}"' `
    -PlatformNames @("Sega Model 2") `
    -ImageExtensions @(".zip")

# --- 7. SuperModel (Sega Model 3) ---
$model3 = Ensure-Emulator -Name "SuperModel" -InstallDir ($DriveRoot + "Emulators\Super Model")
Add-CustomProfile -Emulator $model3 `
    -ProfileName "Model 3 Default" `
    -Executable '{EmulatorDir}\Supermodel.exe' `
    -Arguments '"{ImagePath}" -fullscreen -new3d -quad-rendering' `
    -PlatformNames @("Sega Model 3") `
    -ImageExtensions @(".zip")

# --- 8. TeknoParrot (Joystick) ---
$tp = Ensure-Emulator -Name "TeknoParrot" -InstallDir ($DriveRoot + "Emulators\TeknoParrot")
Add-CustomProfile -Emulator $tp `
    -ProfileName "TeknoParrot Default" `
    -Executable '{EmulatorDir}\TeknoParrotUi.exe' `
    -Arguments '--profile="{ImageNameNoExt}"' `
    -PlatformNames @("Arcade") `
    -ImageExtensions @(".exe", ".zip")

# --- 9. TeknoParrot Gamepad ---
$tpGP = Ensure-Emulator -Name "TeknoParrot Gamepad" -InstallDir ($DriveRoot + "Emulators\TeknoParrot Gamepad")
Add-CustomProfile -Emulator $tpGP `
    -ProfileName "TP Gamepad Default" `
    -Executable '{EmulatorDir}\TeknoParrotUi.exe' `
    -Arguments '--profile="{ImageNameNoExt}"' `
    -PlatformNames @("Arcade") `
    -ImageExtensions @(".exe", ".zip")

# --- 10. TeknoParrot Latest ---
$tpLatest = Ensure-Emulator -Name "TeknoParrot Latest" -InstallDir ($DriveRoot + "Emulators\TeknoParrot Latest")
Add-CustomProfile -Emulator $tpLatest `
    -ProfileName "TP Latest Default" `
    -Executable '{EmulatorDir}\TeknoParrotUi.exe' `
    -Arguments '--profile="{ImageNameNoExt}"' `
    -PlatformNames @("Arcade") `
    -ImageExtensions @(".exe", ".zip")


# ============================================================================
# Phase 2: Ensure All Platforms Exist
# ============================================================================

Log ""
Log "--- Phase 2: Ensuring Platforms ---"

$allPlatforms = @(
    # Arcade
    "Arcade", "Atomiswave", "Sega NAOMI", "Sega Model 2", "Sega Model 3",
    "Sega Triforce", "Daphne", "Sega Hikaru", "Pinball FX2", "Pinball FX3",
    "Singe", "TTX", "SNK Neo Geo", "SNK Neo Geo CD",
    # Console
    "Atari 2600", "Atari 7800", "Atari Jaguar", "Atari Lynx",
    "NEC TurboGrafx-16", "Nintendo 64", "Nintendo Entertainment System",
    "Nintendo Game Boy", "Nintendo Game Boy Advance", "Nintendo Game Boy Color",
    "Nintendo GameCube", "Nintendo DS", "Nintendo Wii U",
    "Sega 32X", "Sega Dreamcast", "Sega Game Gear", "Sega Genesis",
    "Sega Mega Drive", "Sega Saturn", "Super Nintendo",
    "Sony PlayStation", "Sony PlayStation 2", "Sony PlayStation 3", "Sony PSP",
    "3DO", "Commodore Amiga", "DOS", "ScummVM", "PopCap"
)

$createdCount = 0
foreach ($pName in $allPlatforms) {
    $null = Ensure-Platform -Name $pName
    $createdCount++
}
Log "  Processed $createdCount platforms"


# ============================================================================
# Phase 3: ROM Directory Mapping (reference / scan config)
# ============================================================================

Log ""
Log "--- Phase 3: ROM Directory Verification ---"

$romDirs = @(
    # Arcade
    @{ Platform = "Arcade"; Dir = ($DriveRoot + "Roms\MAME") }
    @{ Platform = "Atomiswave"; Dir = ($DriveRoot + "Roms\ATOMISWAVE") }
    @{ Platform = "Sega NAOMI"; Dir = ($DriveRoot + "Roms\NAOMI") }
    @{ Platform = "Sega Model 2"; Dir = ($DriveRoot + "Roms\MODEL2") }
    @{ Platform = "Sega Model 3"; Dir = ($DriveRoot + "Roms\MODEL3") }
    @{ Platform = "Sega Triforce"; Dir = ($DriveRoot + "Roms\TRI-FORCE") }
    @{ Platform = "Daphne"; Dir = ($DriveRoot + "Roms\DAPHNE") }
    @{ Platform = "Sega Hikaru"; Dir = ($DriveRoot + "Roms\HIKARU") }
    @{ Platform = "TTX"; Dir = ($DriveRoot + "Roms\TTX") }
    @{ Platform = "Singe"; Dir = ($DriveRoot + "Roms\SINGE-HYPSEUS") }
    @{ Platform = "Pinball FX2"; Dir = ($DriveRoot + "Roms\PINBALL-FX2") }
    @{ Platform = "Pinball FX3"; Dir = ($DriveRoot + "Roms\PINBALL-FX3") }
    # Console
    @{ Platform = "Atari 2600"; Dir = ($DriveRoot + "Console ROMs\Atari 2600") }
    @{ Platform = "Atari 7800"; Dir = ($DriveRoot + "Console ROMs\Atari 7800") }
    @{ Platform = "Atari Jaguar"; Dir = ($DriveRoot + "Console ROMs\Atari Jaguar") }
    @{ Platform = "Atari Lynx"; Dir = ($DriveRoot + "Console ROMs\Atari Lynx") }
    @{ Platform = "NEC TurboGrafx-16"; Dir = ($DriveRoot + "Console ROMs\NEC Turbografx-16") }
    @{ Platform = "Nintendo 64"; Dir = ($DriveRoot + "Console ROMs\Nintendo 64") }
    @{ Platform = "Nintendo Entertainment System"; Dir = ($DriveRoot + "Console ROMs\Nintendo Entertainment System") }
    @{ Platform = "Nintendo Game Boy"; Dir = ($DriveRoot + "Console ROMs\Nintendo Game Boy") }
    @{ Platform = "Nintendo Game Boy Advance"; Dir = ($DriveRoot + "Console ROMs\Nintendo Game Boy Advance") }
    @{ Platform = "Nintendo GameCube"; Dir = ($DriveRoot + "Console ROMs\Nintendo Games Cube") }
    @{ Platform = "Nintendo DS"; Dir = ($DriveRoot + "Console ROMs\nds") }
    @{ Platform = "Super Nintendo"; Dir = ($DriveRoot + "Console ROMs\snes") }
    @{ Platform = "Sega 32X"; Dir = ($DriveRoot + "Console ROMs\Sega 32X") }
    @{ Platform = "Sega Dreamcast"; Dir = ($DriveRoot + "Console ROMs\Sega Dreamcast") }
    @{ Platform = "Sega Game Gear"; Dir = ($DriveRoot + "Console ROMs\Sega Game Gear") }
    @{ Platform = "Sega Genesis"; Dir = ($DriveRoot + "Console ROMs\Sega Genesis") }
    @{ Platform = "Sega Mega Drive"; Dir = ($DriveRoot + "Console ROMs\megadrive") }
    @{ Platform = "Sony PlayStation"; Dir = ($DriveRoot + "Console ROMs\playstation") }
    @{ Platform = "Sony PlayStation 2"; Dir = ($DriveRoot + "Console ROMs\playstation 2") }
    @{ Platform = "Sony PlayStation 3"; Dir = ($DriveRoot + "Console ROMs\playstation 3") }
    @{ Platform = "Sony PSP"; Dir = ($DriveRoot + "Console ROMs\psp") }
)

$okCount = 0
$missingCount = 0
foreach ($entry in $romDirs) {
    $exists = Test-Path $entry.Dir
    if ($exists) {
        $okCount++
    }
    else {
        $missingCount++
        Log "  [MISSING] $($entry.Platform) -> $($entry.Dir)"
    }
}
Log "  ROM dirs: $okCount OK, $missingCount missing"


# ============================================================================
# Phase 4: BIOS Health Check
# ============================================================================

Log ""
Log "--- Phase 4: BIOS Health Check ---"

$biosDir = $DriveRoot + "Bios\system"
$criticalBios = @(
    @{ Name = "PS1 US"; File = "scph5501.bin" }
    @{ Name = "PS1 JP"; File = "scph5500.bin" }
    @{ Name = "PS1 EU"; File = "scph5502.bin" }
    @{ Name = "Saturn"; File = "saturn_bios.bin" }
    @{ Name = "GBA"; File = "gba_bios.bin" }
    @{ Name = "Lynx"; File = "lynxboot.img" }
    @{ Name = "SegaCD US"; File = "bios_CD_U.bin" }
    @{ Name = "NeoGeo"; File = "neo-epo.bin" }
    @{ Name = "FDS"; File = "disksys.rom" }
    @{ Name = "TG-16 CD"; File = "Syscard3.pce" }
)

$biosOk = 0
$biosMissing = 0
foreach ($bios in $criticalBios) {
    $path = Join-Path $biosDir $bios.File
    $found = Test-Path $path
    if ($found) {
        $biosOk++
        Log "  [OK] $($bios.Name): $($bios.File)"
    }
    else {
        $biosMissing++
        Log "  [MISSING] $($bios.Name): $($bios.File)"
    }
}
Log "  BIOS: $biosOk OK, $biosMissing missing"


# ============================================================================
# Phase 5: Summary
# ============================================================================

Log ""
Log "=== Initialization Complete ==="
Log "Emulators: 10 created/verified"
Log "RetroArch profiles: $($retroArchProfiles.Count) core mappings"
Log "Platforms: $($allPlatforms.Count) ensured"
Log "ROM dirs: $okCount OK / $missingCount missing"
Log "BIOS: $biosOk OK / $biosMissing missing"
Log ""
Log "NEXT STEPS:"
Log "  1. Open Settings > Game Scanners"
Log "  2. Add ROM directories for each platform"
Log "  3. Run 'Update Game Library' to scan"

# Save log to file
$logDir = $DriveRoot + "Arcade Assistant Local\logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$logPath = Join-Path $logDir ("playnite-init-" + (Get-Date -Format 'yyyy-MM-dd-HHmmss') + ".log")
$script:__log | Out-File -FilePath $logPath -Encoding UTF8
Log "Log saved: $logPath"

$PlayniteApi.Dialogs.ShowMessage(
    "Arcade initialization complete!`n`nEmulators: 10`nProfiles: $($retroArchProfiles.Count + 10)`nPlatforms: $($allPlatforms.Count)`n`nLog: $logPath",
    "Arcade Assistant"
)
