# Arcade Assistant Playnite Extension
# API-Driven Import Pipeline + Emulator Wiring + LED Bridge
# Uses $PlayniteApi for live GUI synchronization

# --- Configuration ---
$BackendBaseUrl = "http://127.0.0.1:8000/api/game"

# ============================================================
#  SECTION 0: EMULATOR AUTO-CONFIGURATION
# ============================================================

function Setup-ArcadeEmulators {
    $debugLog = Join-Path $PlayniteApi.Paths.ApplicationPath "arcade_debug.log"
    
    function Write-Debug($msg) {
        "[$(Get-Date -Format 'HH:mm:ss')] $msg" | Out-File $debugLog -Append -Encoding UTF8
    }
    
    Write-Debug "=== STARTING EMULATOR SETUP ==="
    
    try {
        # Build a lookup of existing emulator names for per-emulator idempotency
        $existingEmulators = @{}
        $PlayniteApi.Database.Emulators | ForEach-Object { $existingEmulators[$_.Name] = $true }
        $existingCount = $existingEmulators.Count
        Write-Debug "Found $existingCount existing emulators: $($existingEmulators.Keys -join ', ')"
    }
    catch {
        Write-Debug "ERROR checking emulators: $_"
        $existingEmulators = @{}
    }
    
    # Helper: skip if emulator already exists
    # Each section below checks: if ($existingEmulators.ContainsKey("Name")) { skip }
    
    # --- RetroArch ---
    try {
        $raDir = "A:\Emulators\RetroArch"
        if ($existingEmulators.ContainsKey("RetroArch")) { Write-Debug "RetroArch: already exists, skipping" }
        elseif (Test-Path $raDir) {
            Write-Debug "Creating RetroArch emulator object..."
            $ra = New-Object Playnite.SDK.Models.Emulator
            Write-Debug "  Object created. Type: $($ra.GetType().FullName)"
            $ra.Name = "RetroArch"
            $ra.InstallDir = $raDir
            Write-Debug "  Name and InstallDir set"
            
            Write-Debug "  Calling Emulators.Add()..."
            $PlayniteApi.Database.Emulators.Add($ra)
            Write-Debug "  Add() succeeded. ID: $($ra.Id)"
            
            # Initialize CustomProfiles (null by default after New-Object)
            $ra.CustomProfiles = New-Object "System.Collections.ObjectModel.ObservableCollection[Playnite.SDK.Models.CustomEmulatorProfile]"
            Write-Debug "  CustomProfiles initialized"
            
            $raProfiles = @(
                @{ Name = "SNES"; Core = "snes9x_libretro.dll"; Plat = "Super Nintendo Entertainment System"; Ext = "zip,sfc,smc,7z" },
                @{ Name = "Genesis"; Core = "genesis_plus_gx_libretro.dll"; Plat = "Sega Mega Drive / Genesis"; Ext = "zip,md,bin,gen,smd,7z" },
                @{ Name = "NDS"; Core = "desmume_libretro.dll"; Plat = "Nintendo DS"; Ext = "zip,nds,7z" },
                @{ Name = "PS1"; Core = "pcsx_rearmed_libretro.dll"; Plat = "Sony PlayStation"; Ext = "zip,iso,bin,cue,img,pbp,chd,m3u" },
                @{ Name = "PSP"; Core = "ppsspp_libretro.dll"; Plat = "Sony PSP"; Ext = "zip,iso,cso,pbp,7z" },
                @{ Name = "PS2"; Core = "pcsx2_libretro.dll"; Plat = "Sony PlayStation 2"; Ext = "iso,bin,chd,cso,gz,m3u" },
                @{ Name = "NAOMI"; Core = "flycast_libretro.dll"; Plat = "Sega NAOMI"; Ext = "zip,7z,lst,bin,dat" },
                @{ Name = "Atomiswave"; Core = "flycast_libretro.dll"; Plat = "Sammy Atomiswave"; Ext = "zip,7z,lst,bin" }
            )
            
            foreach ($p in $raProfiles) {
                try {
                    Write-Debug "  Creating profile: $($p.Name)..."
                    $prof = New-Object Playnite.SDK.Models.CustomEmulatorProfile
                    $prof.Name = $p.Name
                    $prof.Executable = '{EmulatorDir}\retroarch.exe'
                    $prof.Arguments = '-L "{EmulatorDir}\cores\' + $p.Core + '" "{ImagePath}"'
                    Write-Debug "    Exe: $($prof.Executable)"
                    Write-Debug "    Args: $($prof.Arguments)"
                    
                    $prof.ImageExtensions = [System.Collections.Generic.List[string]]::new()
                    foreach ($ext in $p.Ext.Split(",")) {
                        $prof.ImageExtensions.Add($ext.Trim())
                    }
                    Write-Debug "    Extensions: $($prof.ImageExtensions.Count)"
                    
                    $plat = $PlayniteApi.Database.Platforms | Where-Object { $_.Name -eq $p.Plat } | Select-Object -First 1
                    Write-Debug "    Platform '$($p.Plat)' found: $($null -ne $plat)"
                    if ($null -ne $plat) {
                        $prof.Platforms = [System.Collections.Generic.List[System.Guid]]::new()
                        $prof.Platforms.Add($plat.Id)
                        Write-Debug "    Platform ID: $($plat.Id)"
                    }
                    
                    Write-Debug "    Adding to CustomProfiles..."
                    $ra.CustomProfiles.Add($prof)
                    Write-Debug "    Profile added OK"
                }
                catch {
                    Write-Debug "  ERROR adding profile $($p.Name): $_ | $($_.Exception.GetType().FullName)"
                }
            }
            
            Write-Debug "  Calling Emulators.Update()..."
            $PlayniteApi.Database.Emulators.Update($ra)
            Write-Debug "  RetroArch saved with $($ra.CustomProfiles.Count) profiles"
        }
    }
    catch {
        Write-Debug "RetroArch FAILED: $_ | $($_.Exception.GetType().FullName)"
    }
    
    # --- MAME ---
    try {
        $mameDir = "A:\Emulators\MAME"
        if ($existingEmulators.ContainsKey("MAME")) { Write-Debug "MAME: already exists, skipping" }
        elseif (Test-Path $mameDir) {
            Write-Debug "Creating MAME..."
            $mame = New-Object Playnite.SDK.Models.Emulator
            $mame.Name = "MAME"
            $mame.InstallDir = $mameDir
            $PlayniteApi.Database.Emulators.Add($mame)
            $mame.CustomProfiles = New-Object "System.Collections.ObjectModel.ObservableCollection[Playnite.SDK.Models.CustomEmulatorProfile]"
            
            $prof = New-Object Playnite.SDK.Models.CustomEmulatorProfile
            $prof.Name = "MAME Default"
            $prof.Executable = '{EmulatorDir}\mame.exe'
            $prof.Arguments = '{ImageName}'
            $prof.ImageExtensions = [System.Collections.Generic.List[string]]::new()
            @("zip", "7z", "chd") | ForEach-Object { $prof.ImageExtensions.Add($_) }
            
            $plat = $PlayniteApi.Database.Platforms | Where-Object { $_.Name -eq "Arcade" } | Select-Object -First 1
            if ($null -ne $plat) {
                $prof.Platforms = [System.Collections.Generic.List[System.Guid]]::new()
                $prof.Platforms.Add($plat.Id)
            }
            
            $mame.CustomProfiles.Add($prof)
            $PlayniteApi.Database.Emulators.Update($mame)
            Write-Debug "MAME saved"
        }
    }
    catch {
        Write-Debug "MAME FAILED: $_ | $($_.Exception.GetType().FullName)"
    }
    
    # --- Dolphin Tri-Force ---
    try {
        $dolphinDir = "A:\Emulators\Dolphin Tri-Force"
        if ($existingEmulators.ContainsKey("Dolphin Tri-Force")) { Write-Debug "Dolphin Tri-Force: already exists, skipping" }
        elseif (Test-Path $dolphinDir) {
            Write-Debug "Creating Dolphin..."
            $dolphin = New-Object Playnite.SDK.Models.Emulator
            $dolphin.Name = "Dolphin Tri-Force"
            $dolphin.InstallDir = $dolphinDir
            $PlayniteApi.Database.Emulators.Add($dolphin)
            $dolphin.CustomProfiles = New-Object "System.Collections.ObjectModel.ObservableCollection[Playnite.SDK.Models.CustomEmulatorProfile]"
            
            $prof = New-Object Playnite.SDK.Models.CustomEmulatorProfile
            $prof.Name = "GameCube"
            $prof.Executable = '{EmulatorDir}\Dolphin.exe'
            $prof.Arguments = '-b -e "{ImagePath}"'
            $prof.ImageExtensions = [System.Collections.Generic.List[string]]::new()
            @("iso", "gcm", "gcz", "ciso", "wbfs", "rvz") | ForEach-Object { $prof.ImageExtensions.Add($_) }
            
            $plat = $PlayniteApi.Database.Platforms | Where-Object { $_.Name -eq "Nintendo GameCube" } | Select-Object -First 1
            if ($null -ne $plat) {
                $prof.Platforms = [System.Collections.Generic.List[System.Guid]]::new()
                $prof.Platforms.Add($plat.Id)
            }
            
            $dolphin.CustomProfiles.Add($prof)
            $PlayniteApi.Database.Emulators.Update($dolphin)
            Write-Debug "Dolphin saved"
        }
    }
    catch {
        Write-Debug "Dolphin FAILED: $_ | $($_.Exception.GetType().FullName)"
    }
    
    # --- Sega Model 2 ---
    try {
        $m2Dir = "A:\Emulators\Sega Model 2"
        if ($existingEmulators.ContainsKey("Sega Model 2")) { Write-Debug "Sega Model 2: already exists, skipping" }
        elseif (Test-Path $m2Dir) {
            Write-Debug "Creating Sega Model 2..."
            $m2 = New-Object Playnite.SDK.Models.Emulator
            $m2.Name = "Sega Model 2"
            $m2.InstallDir = $m2Dir
            $PlayniteApi.Database.Emulators.Add($m2)
            $m2.CustomProfiles = New-Object "System.Collections.ObjectModel.ObservableCollection[Playnite.SDK.Models.CustomEmulatorProfile]"
            
            $prof = New-Object Playnite.SDK.Models.CustomEmulatorProfile
            $prof.Name = "Model 2 Default"
            $prof.Executable = '{EmulatorDir}\EMULATOR.EXE'
            $prof.Arguments = '{ImageName}'
            $prof.ImageExtensions = [System.Collections.Generic.List[string]]::new()
            @("zip", "7z") | ForEach-Object { $prof.ImageExtensions.Add($_) }
            
            $plat = $PlayniteApi.Database.Platforms | Where-Object { $_.Name -eq "Sega Model 2" } | Select-Object -First 1
            if ($null -ne $plat) {
                $prof.Platforms = [System.Collections.Generic.List[System.Guid]]::new()
                $prof.Platforms.Add($plat.Id)
            }
            
            $m2.CustomProfiles.Add($prof)
            $PlayniteApi.Database.Emulators.Update($m2)
            Write-Debug "Sega Model 2 saved"
        }
    }
    catch {
        Write-Debug "Sega Model 2 FAILED: $_ | $($_.Exception.GetType().FullName)"
    }
    
    # --- Super Model (Model 3) ---
    try {
        $m3Dir = "A:\Emulators\Super Model"
        if ($existingEmulators.ContainsKey("Super Model")) { Write-Debug "Super Model: already exists, skipping" }
        elseif (Test-Path $m3Dir) {
            Write-Debug "Creating Super Model..."
            $m3 = New-Object Playnite.SDK.Models.Emulator
            $m3.Name = "Super Model"
            $m3.InstallDir = $m3Dir
            $PlayniteApi.Database.Emulators.Add($m3)
            $m3.CustomProfiles = New-Object "System.Collections.ObjectModel.ObservableCollection[Playnite.SDK.Models.CustomEmulatorProfile]"
            
            $prof = New-Object Playnite.SDK.Models.CustomEmulatorProfile
            $prof.Name = "Model 3 Default"
            $prof.Executable = '{EmulatorDir}\Supermodel.bak.exe'
            $prof.Arguments = '"{ImagePath}" -fullscreen'
            $prof.ImageExtensions = [System.Collections.Generic.List[string]]::new()
            @("zip", "7z") | ForEach-Object { $prof.ImageExtensions.Add($_) }
            
            $plat = $PlayniteApi.Database.Platforms | Where-Object { $_.Name -eq "Sega Model 3" } | Select-Object -First 1
            if ($null -ne $plat) {
                $prof.Platforms = [System.Collections.Generic.List[System.Guid]]::new()
                $prof.Platforms.Add($plat.Id)
            }
            
            $m3.CustomProfiles.Add($prof)
            $PlayniteApi.Database.Emulators.Update($m3)
            Write-Debug "Super Model saved"
        }
    }
    catch {
        Write-Debug "Super Model FAILED: $_ | $($_.Exception.GetType().FullName)"
    }
    
    # --- MAME Gamepad (control panel / joystick+buttons arcade) ---
    try {
        $mameGpDir = "A:\Emulators\MAME Gamepad"
        if ($existingEmulators.ContainsKey("MAME Gamepad")) { Write-Debug "MAME Gamepad: already exists, skipping" }
        elseif (Test-Path $mameGpDir) {
            Write-Debug "Creating MAME Gamepad..."
            $mameGp = New-Object Playnite.SDK.Models.Emulator
            $mameGp.Name = "MAME Gamepad"
            $mameGp.InstallDir = $mameGpDir
            $PlayniteApi.Database.Emulators.Add($mameGp)
            $mameGp.CustomProfiles = New-Object "System.Collections.ObjectModel.ObservableCollection[Playnite.SDK.Models.CustomEmulatorProfile]"
            
            $prof = New-Object Playnite.SDK.Models.CustomEmulatorProfile
            $prof.Name = "MAME Gamepad Default"
            $prof.Executable = '{EmulatorDir}\mame.exe'
            $prof.Arguments = '{ImageName}'
            $prof.ImageExtensions = [System.Collections.Generic.List[string]]::new()
            @("zip", "7z", "chd") | ForEach-Object { $prof.ImageExtensions.Add($_) }
            
            $plat = $PlayniteApi.Database.Platforms | Where-Object { $_.Name -eq "Arcade" } | Select-Object -First 1
            if ($null -ne $plat) {
                $prof.Platforms = [System.Collections.Generic.List[System.Guid]]::new()
                $prof.Platforms.Add($plat.Id)
            }
            
            $mameGp.CustomProfiles.Add($prof)
            $PlayniteApi.Database.Emulators.Update($mameGp)
            Write-Debug "MAME Gamepad saved"
        }
    }
    catch {
        Write-Debug "MAME Gamepad FAILED: $_ | $($_.Exception.GetType().FullName)"
    }
    
    # --- TeknoParrot (lightgun / modern arcade) ---
    try {
        $tpDir = "A:\Emulators\TeknoParrot"
        if ($existingEmulators.ContainsKey("TeknoParrot")) { Write-Debug "TeknoParrot: already exists, skipping" }
        elseif (Test-Path $tpDir) {
            Write-Debug "Creating TeknoParrot..."
            $tp = New-Object Playnite.SDK.Models.Emulator
            $tp.Name = "TeknoParrot"
            $tp.InstallDir = $tpDir
            $PlayniteApi.Database.Emulators.Add($tp)
            $tp.CustomProfiles = New-Object "System.Collections.ObjectModel.ObservableCollection[Playnite.SDK.Models.CustomEmulatorProfile]"
            
            $prof = New-Object Playnite.SDK.Models.CustomEmulatorProfile
            $prof.Name = "TeknoParrot Default"
            $prof.Executable = '{EmulatorDir}\TeknoParrotUi.exe'
            $prof.Arguments = '--profile={ImageName}'
            $prof.ImageExtensions = [System.Collections.Generic.List[string]]::new()
            @("xml") | ForEach-Object { $prof.ImageExtensions.Add($_) }
            
            $tp.CustomProfiles.Add($prof)
            $PlayniteApi.Database.Emulators.Update($tp)
            Write-Debug "TeknoParrot saved"
        }
    }
    catch {
        Write-Debug "TeknoParrot FAILED: $_ | $($_.Exception.GetType().FullName)"
    }
    
    # --- TeknoParrot Gamepad (gamepad / modern arcade) ---
    try {
        $tpGpDir = "A:\Emulators\TeknoParrot Gamepad"
        if ($existingEmulators.ContainsKey("TeknoParrot Gamepad")) { Write-Debug "TeknoParrot Gamepad: already exists, skipping" }
        elseif (Test-Path $tpGpDir) {
            Write-Debug "Creating TeknoParrot Gamepad..."
            $tpGp = New-Object Playnite.SDK.Models.Emulator
            $tpGp.Name = "TeknoParrot Gamepad"
            $tpGp.InstallDir = $tpGpDir
            $PlayniteApi.Database.Emulators.Add($tpGp)
            $tpGp.CustomProfiles = New-Object "System.Collections.ObjectModel.ObservableCollection[Playnite.SDK.Models.CustomEmulatorProfile]"
            
            $prof = New-Object Playnite.SDK.Models.CustomEmulatorProfile
            $prof.Name = "TeknoParrot Gamepad Default"
            $prof.Executable = '{EmulatorDir}\TeknoParrotUi.exe'
            $prof.Arguments = '--profile={ImageName}'
            $prof.ImageExtensions = [System.Collections.Generic.List[string]]::new()
            @("xml") | ForEach-Object { $prof.ImageExtensions.Add($_) }
            
            $tpGp.CustomProfiles.Add($prof)
            $PlayniteApi.Database.Emulators.Update($tpGp)
            Write-Debug "TeknoParrot Gamepad saved"
        }
    }
    catch {
        Write-Debug "TeknoParrot Gamepad FAILED: $_ | $($_.Exception.GetType().FullName)"
    }
    
    Write-Debug "=== EMULATOR SETUP COMPLETE ==="
}


# ============================================================
#  SECTION 0B: WIRE GAME LAUNCH ACTIONS
# ============================================================

function Wire-GameActions {
    $debugLog = Join-Path $PlayniteApi.Paths.ApplicationPath "arcade_debug.log"
    
    function Write-Debug($msg) {
        "[$(Get-Date -Format 'HH:mm:ss')] $msg" | Out-File $debugLog -Append -Encoding UTF8
    }
    
    Write-Debug "=== WIRING GAME ACTIONS ==="
    
    # Build platform-to-emulator/profile lookup
    # For each platform GUID, find the matching emulator ID and profile ID
    $platformMap = @{}  # platformGuid -> @{ EmulatorId; ProfileId }
    
    foreach ($emu in $PlayniteApi.Database.Emulators) {
        if ($null -eq $emu.CustomProfiles) { continue }
        foreach ($prof in $emu.CustomProfiles) {
            if ($null -eq $prof.Platforms) { continue }
            foreach ($platId in $prof.Platforms) {
                if (-not $platformMap.ContainsKey($platId.ToString())) {
                    $platformMap[$platId.ToString()] = @{
                        EmulatorId = $emu.Id
                        ProfileId  = $prof.Id
                        EmuName    = $emu.Name
                        ProfName   = $prof.Name
                    }
                }
            }
        }
    }
    
    Write-Debug "Platform map has $($platformMap.Count) entries"
    foreach ($k in $platformMap.Keys) {
        $v = $platformMap[$k]
        Write-Debug "  $k -> $($v.EmuName)/$($v.ProfName)"
    }
    
    # Scan all games and wire up those without emulator actions
    $wired = 0
    $alreadyWired = 0
    $noMatch = 0
    $buffer = $PlayniteApi.Database.BufferedUpdate()
    
    try {
        foreach ($game in $PlayniteApi.Database.Games) {
            # Skip games that already have a GameAction
            if ($null -ne $game.GameActions -and $game.GameActions.Count -gt 0) {
                $alreadyWired++
                continue
            }
            
            # Skip games with no ROMs (non-emulator games like PopCap .exe/.bat)
            if ($null -eq $game.Roms -or $game.Roms.Count -eq 0) {
                continue
            }
            
            # Skip games with no platform
            if ($null -eq $game.PlatformIds -or $game.PlatformIds.Count -eq 0) {
                continue
            }
            
            # Find matching emulator profile for this game's platform
            $platId = $game.PlatformIds[0].ToString()
            if (-not $platformMap.ContainsKey($platId)) {
                $noMatch++
                continue
            }
            
            $match = $platformMap[$platId]
            
            # Create emulator-type GameAction
            $action = New-Object Playnite.SDK.Models.GameAction
            $action.Type = [Playnite.SDK.Models.GameActionType]::Emulator
            $action.EmulatorId = $match.EmulatorId
            $action.EmulatorProfileId = $match.ProfileId
            $action.Name = "Launch via $($match.EmuName)"
            $action.IsPlayAction = $true
            
            # Initialize GameActions collection if null
            if ($null -eq $game.GameActions) {
                $game.GameActions = New-Object "System.Collections.ObjectModel.ObservableCollection[Playnite.SDK.Models.GameAction]"
            }
            $game.GameActions.Add($action)
            
            $PlayniteApi.Database.Games.Update($game)
            $wired++
        }
    }
    finally {
        if ($null -ne $buffer) { $buffer.Dispose() }
    }
    
    Write-Debug "Wiring complete: $wired wired, $alreadyWired already had actions, $noMatch no emulator match"
}


# ============================================================
#  SECTION 0C: CINEMA LOGIC AUTO-TAGGER
# ============================================================

function Apply-CinemaLogicTags {
    $debugLog = Join-Path $PlayniteApi.Paths.ApplicationPath "arcade_debug.log"
    
    function Write-Debug($msg) {
        "[$(Get-Date -Format 'HH:mm:ss')] $msg" | Out-File $debugLog -Append -Encoding UTF8
    }
    
    Write-Debug "=== CINEMA LOGIC AUTO-TAGGER ==="
    
    # --- catver.ini parsing (load once into hashtable) ---
    $catverPath = "A:\Emulators\MAME\catver.ini"
    if (-not (Test-Path $catverPath)) {
        Write-Debug "catver.ini not found at $catverPath -- skipping Cinema Logic"
        return
    }
    
    $catverMap = @{}  # romname -> genre string
    $inCategory = $false
    $catverPattern = '^([^=]+)=(.+)$'
    foreach ($line in [System.IO.File]::ReadAllLines($catverPath)) {
        if ($line -eq "[Category]") { $inCategory = $true; continue }
        if ($line.StartsWith("[") -and $inCategory) { break }
        if ($inCategory -and $line -match $catverPattern) {
            $catverMap[$Matches[1].Trim()] = $Matches[2].Trim()
        }
    }
    Write-Debug "catver.ini loaded: $($catverMap.Count) entries"
    
    # --- Two-pass genre-to-LED mapping ---
    $ExactGenreMap = [ordered]@{
        # LIGHTGUN
        "Shooter / Gun"                 = "LED:LIGHTGUN"
        "Shooter / Gallery"             = "LED:LIGHTGUN"
        "Shooter / Gallery * Mature *"  = "LED:LIGHTGUN"
        # RACING
        "Driving / Race 1st Person"     = "LED:RACING"
        "Driving / Race 3rd Person"     = "LED:RACING"
        "Driving / Race Isometric"      = "LED:RACING"
        "Driving / Race Track"          = "LED:RACING"
        "Driving / Motorbike"           = "LED:RACING"
        "Driving / Race Bird-view"      = "LED:RACING"
        "Driving / Race 2nd Person"     = "LED:RACING"
        "Driving / Truck Guide"         = "LED:RACING"
        "Driving / 1st Person"          = "LED:RACING"
        # FIGHTING
        "Fighter / Versus"              = "LED:FIGHTING"
        "Fighter / 2.5D"                = "LED:FIGHTING"
        "Fighter / 3D"                  = "LED:FIGHTING"
        "Fighter / Field"               = "LED:FIGHTING"
        "Fighter / Medieval Tournament" = "LED:FIGHTING"
        "Fighter / Misc."               = "LED:FIGHTING"
        "Fighter / Compilation"         = "LED:FIGHTING"
        # SPORTS
        "Sports / Football"             = "LED:SPORTS"
        "Sports / Baseball"             = "LED:SPORTS"
        "Sports / Basketball"           = "LED:SPORTS"
        "Sports / Soccer"               = "LED:SPORTS"
        "Sports / Wrestling"            = "LED:SPORTS"
        "Sports / Tennis"               = "LED:SPORTS"
        "Sports / Boxing"               = "LED:SPORTS"
        "Sports / Volleyball"           = "LED:SPORTS"
        "Sports / Pool"                 = "LED:SPORTS"
        "Sports / Bowling"              = "LED:SPORTS"
        'Sports / Track and Field'      = 'LED:SPORTS'
    }
    
    $KeywordMap = [ordered]@{
        "Racing"     = "LED:RACING"
        "Driving"    = "LED:RACING"
        "Race"       = "LED:RACING"
        "Motorbike"  = "LED:RACING"
        "Shooter"    = "LED:SHOOTER"
        "Shoot"      = "LED:SHOOTER"
        "Fighter"    = "LED:FIGHTING"
        "Fighting"   = "LED:FIGHTING"
        "Beat"       = "LED:FIGHTING"
        "Sports"     = "LED:SPORTS"
        "Ball"       = "LED:SPORTS"
        "Track"      = "LED:SPORTS"
        "Platform"   = "LED:PLATFORMER"
        "Platformer" = "LED:PLATFORMER"
        "Puzzle"     = "LED:PUZZLE"
        "Maze"       = "LED:MAZE"
        "Trackball"  = "LED:TRACKBALL"
    }
    
    # --- Resolve or create LED tags ---
    $tagCache = @{}
    $ledTagNames = @("LED:LIGHTGUN", "LED:RACING", "LED:FIGHTING", "LED:SHOOTER", "LED:SPORTS", "LED:PLATFORMER", "LED:PUZZLE", "LED:MAZE", "LED:TRACKBALL", "LED:STANDARD")
    foreach ($tagName in $ledTagNames) {
        $existing = $PlayniteApi.Database.Tags | Where-Object { $_.Name -eq $tagName } | Select-Object -First 1
        if ($null -eq $existing) {
            $newTag = New-Object Playnite.SDK.Models.Tag($tagName)
            $PlayniteApi.Database.Tags.Add($newTag)
            $tagCache[$tagName] = $newTag.Id
        }
        else {
            $tagCache[$tagName] = $existing.Id
        }
    }
    Write-Debug "LED tags resolved: $($tagCache.Count) tags"
    
    # --- Apply tags to games ---
    $tagged = 0
    $alreadyTagged = 0
    $noGenre = 0
    $buffer = $PlayniteApi.Database.BufferedUpdate()
    
    try {
        foreach ($game in $PlayniteApi.Database.Games) {
            # Skip games that already have an LED:* tag
            if ($null -ne $game.TagIds -and $game.TagIds.Count -gt 0) {
                $hasLed = $false
                foreach ($tid in $game.TagIds) {
                    $tag = $PlayniteApi.Database.Tags | Where-Object { $_.Id -eq $tid } | Select-Object -First 1
                    if ($null -ne $tag -and $tag.Name.StartsWith("LED:")) {
                        $hasLed = $true
                        break
                    }
                }
                if ($hasLed) { $alreadyTagged++; continue }
            }
            
            # Skip games with no ROMs
            if ($null -eq $game.Roms -or $game.Roms.Count -eq 0) { continue }
            
            # Get ROM name (strip extension)
            $romFile = $game.Roms[0].Name
            $romName = [System.IO.Path]::GetFileNameWithoutExtension($romFile)
            
            # Look up genre in catver.ini
            $genre = $null
            if ($catverMap.ContainsKey($romName)) {
                $genre = $catverMap[$romName]
            }
            
            if ($null -eq $genre) { $noGenre++; continue }
            
            # Two-pass tag resolution
            $ledTag = $null
            # Pass 1: Exact match
            foreach ($key in $ExactGenreMap.Keys) {
                if ($genre -eq $key) { $ledTag = $ExactGenreMap[$key]; break }
            }
            # Pass 2: Keyword fallback
            if ($null -eq $ledTag) {
                foreach ($key in $KeywordMap.Keys) {
                    if ($genre -match [regex]::Escape($key)) { $ledTag = $KeywordMap[$key]; break }
                }
            }
            # Default
            if ($null -eq $ledTag) { $ledTag = "LED:STANDARD" }
            
            # Apply tag
            if ($null -eq $game.TagIds) {
                $game.TagIds = [System.Collections.Generic.List[System.Guid]]::new()
            }
            $game.TagIds.Add($tagCache[$ledTag])
            $PlayniteApi.Database.Games.Update($game)
            $tagged++
        }
    }
    finally {
        if ($null -ne $buffer) { $buffer.Dispose() }
    }
    
    Write-Debug "Cinema Logic complete: $tagged tagged, $alreadyTagged already had LED tag, $noGenre no genre found"
}

# ============================================================
#  SECTION 0D: DEWEY F9 HUD OVERLAY
# ============================================================

# Module-scoped state for the overlay
$script:DeweyOverlayProcess = $null
$script:DeweyHotkeyRunspace = $null

function Toggle-DeweyOverlay {
    $debugLog = Join-Path $PlayniteApi.Paths.ApplicationPath "arcade_debug.log"
    
    # If overlay is running, kill it
    if ($null -ne $script:DeweyOverlayProcess -and -not $script:DeweyOverlayProcess.HasExited) {
        try {
            $script:DeweyOverlayProcess.Kill()
            $script:DeweyOverlayProcess = $null
            "[$(Get-Date -Format 'HH:mm:ss')] Dewey overlay CLOSED" | Out-File $debugLog -Append -Encoding UTF8
        }
        catch { }
        return
    }
    
    # Launch the overlay
    $overlayPath = Join-Path $PlayniteApi.Paths.ApplicationPath "Extensions\ArcadeAssistant\dewey-overlay.html"
    
    # Try to find Edge or Chrome for app mode
    $edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if (-not (Test-Path $edgePath)) {
        $edgePath = "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    }
    $chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
    
    $browserPath = $null
    if (Test-Path $edgePath) { $browserPath = $edgePath }
    elseif (Test-Path $chromePath) { $browserPath = $chromePath }
    
    if ($null -eq $browserPath) {
        "[$(Get-Date -Format 'HH:mm:ss')] Dewey: No Edge or Chrome found" | Out-File $debugLog -Append -Encoding UTF8
        return
    }
    
    # Get screen dimensions for positioning
    Add-Type -AssemblyName System.Windows.Forms
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $width = 420
    $height = 700
    $left = $screen.Right - $width - 20
    $top = [math]::Floor(($screen.Height - $height) / 2)
    
    $args = @(
        "--app=file:///$($overlayPath -replace '\\','/')"
        "--window-size=$width,$height"
        "--window-position=$left,$top"
        "--disable-extensions"
        "--disable-sync"
        "--no-first-run"
        "--user-data-dir=$env:TEMP\dewey-overlay"
    )
    
    try {
        $script:DeweyOverlayProcess = Start-Process $browserPath -ArgumentList $args -PassThru
        "[$(Get-Date -Format 'HH:mm:ss')] Dewey overlay OPENED (PID: $($script:DeweyOverlayProcess.Id))" | Out-File $debugLog -Append -Encoding UTF8
    }
    catch {
        "[$(Get-Date -Format 'HH:mm:ss')] Dewey overlay FAILED: $_" | Out-File $debugLog -Append -Encoding UTF8
    }
}

function Start-DeweyHotkey {
    $debugLog = Join-Path $PlayniteApi.Paths.ApplicationPath "arcade_debug.log"
    
    # Find browser
    $edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if (-not (Test-Path $edgePath)) {
        $edgePath = "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    }
    $chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
    
    $browserPath = $null
    if (Test-Path $edgePath) { $browserPath = $edgePath }
    elseif (Test-Path $chromePath) { $browserPath = $chromePath }
    
    if ($null -eq $browserPath) {
        "[$(Get-Date -Format 'HH:mm:ss')] Dewey: No Edge or Chrome found" | Out-File $debugLog -Append -Encoding UTF8
        return
    }
    
    $overlayPath = Join-Path $PlayniteApi.Paths.ApplicationPath "Extensions\ArcadeAssistant\dewey-overlay.html"
    
    # Self-contained watcher script: handles hotkey AND overlay toggle
    $watcherScript = @'
param($BrowserPath, $OverlayHtml, $DebugLog)

Add-Type -AssemblyName System.Windows.Forms

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public class F9Watcher {
    [DllImport("user32.dll")] public static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);
    [DllImport("user32.dll")] public static extern bool UnregisterHotKey(IntPtr hWnd, int id);
    [DllImport("user32.dll")] public static extern bool GetMessage(out MSG lpMsg, IntPtr hWnd, uint wMsgFilterMin, uint wMsgFilterMax);
    
    [StructLayout(LayoutKind.Sequential)]
    public struct MSG {
        public IntPtr hwnd;
        public uint message;
        public IntPtr wParam;
        public IntPtr lParam;
        public uint time;
        public int ptX;
        public int ptY;
    }
}
"@ -Language CSharp

$overlayPid = 0
$registered = [F9Watcher]::RegisterHotKey([IntPtr]::Zero, 9, 0, 0x78)  # VK_F9 = 0x78

if (-not $registered) {
    "[$(Get-Date -Format 'HH:mm:ss')] F9 watcher: RegisterHotKey FAILED" | Out-File $DebugLog -Append -Encoding UTF8
    exit 1
}

"[$(Get-Date -Format 'HH:mm:ss')] F9 watcher: Hotkey registered, waiting for F9..." | Out-File $DebugLog -Append -Encoding UTF8

$msg = New-Object F9Watcher+MSG
while ([F9Watcher]::GetMessage([ref]$msg, [IntPtr]::Zero, 0, 0)) {
    if ($msg.message -eq 0x0312 -and $msg.wParam.ToInt32() -eq 9) {
        # Check if overlay is running
        $alive = $false
        if ($overlayPid -gt 0) {
            $proc = Get-Process -Id $overlayPid -ErrorAction SilentlyContinue
            if ($null -ne $proc -and -not $proc.HasExited) { $alive = $true }
        }
        
        if ($alive) {
            # Close overlay
            try { Stop-Process -Id $overlayPid -Force -ErrorAction SilentlyContinue } catch {}
            $overlayPid = 0
            "[$(Get-Date -Format 'HH:mm:ss')] Dewey overlay CLOSED" | Out-File $DebugLog -Append -Encoding UTF8
        } else {
            # Open overlay
            $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
            $w = 420; $h = 700
            $left = $screen.Right - $w - 20
            $top = [Math]::Floor(($screen.Height - $h) / 2)
            $fileUri = "file:///" + ($OverlayHtml -replace '\\','/')
            
            $p = Start-Process $BrowserPath -ArgumentList @(
                "--app=$fileUri",
                "--window-size=$w,$h",
                "--window-position=$left,$top",
                "--disable-extensions",
                "--disable-sync",
                "--no-first-run",
                "--user-data-dir=$env:TEMP\dewey-overlay"
            ) -PassThru
            $overlayPid = $p.Id
            "[$(Get-Date -Format 'HH:mm:ss')] Dewey overlay OPENED (PID: $overlayPid)" | Out-File $DebugLog -Append -Encoding UTF8
        }
    }
}

[F9Watcher]::UnregisterHotKey([IntPtr]::Zero, 9)
'@
    
    $watcherPath = Join-Path $env:TEMP "dewey_f9_watcher.ps1"
    $watcherScript | Out-File $watcherPath -Encoding UTF8 -Force
    
    $script:DeweyHotkeyRunspace = Start-Process powershell -WindowStyle Hidden -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $watcherPath,
        '-BrowserPath', $browserPath,
        '-OverlayHtml', $overlayPath,
        '-DebugLog', $debugLog
    ) -PassThru
    
    "[$(Get-Date -Format 'HH:mm:ss')] Dewey F9 hotkey watcher started (PID: $($script:DeweyHotkeyRunspace.Id))" | Out-File $debugLog -Append -Encoding UTF8
    "[$(Get-Date -Format 'HH:mm:ss')] Dewey F9 listener active (self-contained)" | Out-File $debugLog -Append -Encoding UTF8
}

function Stop-DeweyHotkey {
    # Kill the hotkey watcher process (it handles its own overlay cleanup)
    if ($null -ne $script:DeweyHotkeyRunspace -and -not $script:DeweyHotkeyRunspace.HasExited) {
        try { $script:DeweyHotkeyRunspace.Kill() } catch { }
    }
}

# ============================================================
#  SECTION 1: IMPORT PIPELINE (OnApplicationStarted)
# ============================================================

function OnApplicationStarted {
    # Debug file log (bypasses $__logger issues)
    $debugLog = Join-Path $PlayniteApi.Paths.ApplicationPath "arcade_debug.log"
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] OnApplicationStarted ENTERED" | Out-File $debugLog -Encoding UTF8
    
    try {
        # --- Step 0: Configure Emulators ---
        "[$(Get-Date -Format 'HH:mm:ss')] Calling Setup-ArcadeEmulators..." | Out-File $debugLog -Append -Encoding UTF8
        Setup-ArcadeEmulators
        "[$(Get-Date -Format 'HH:mm:ss')] Setup-ArcadeEmulators completed" | Out-File $debugLog -Append -Encoding UTF8
    }
    catch {
        "[$(Get-Date -Format 'HH:mm:ss')] Setup-ArcadeEmulators CRASHED: $_" | Out-File $debugLog -Append -Encoding UTF8
    }
    

    # --- Step 1: Check for pending import manifest ---
    $manifestPath = Join-Path $PlayniteApi.Paths.ApplicationPath "pending_import.json"
    
    if (-not (Test-Path $manifestPath)) {
        "[$(Get-Date -Format 'HH:mm:ss')] No pending manifest" | Out-File $debugLog -Append -Encoding UTF8
    }
    else {
    
        $__logger.Info("ArcadeAssistant: Found pending import manifest at $manifestPath")
    
        try {
            $manifest = Get-Content $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $batchId = $manifest.batchId
            $gameList = $manifest.games
        
            $__logger.Info("ArcadeAssistant: Processing batch '$batchId' with $($gameList.Count) games")
        
            # --- Resolve Platform Cache (per-game lookup) ---
            $platformCache = @{}
        
            # --- Resolve Tags ---
            $tagCache = @{}
            foreach ($game in $gameList) {
                if ($null -ne $game.tags) {
                    foreach ($tagName in $game.tags) {
                        if (-not $tagCache.ContainsKey($tagName)) {
                            $existing = $PlayniteApi.Database.Tags | Where-Object { $_.Name -eq $tagName } | Select-Object -First 1
                            if ($null -eq $existing) {
                                $newTag = New-Object Playnite.SDK.Models.Tag($tagName)
                                $PlayniteApi.Database.Tags.Add($newTag)
                                $tagCache[$tagName] = $newTag.Id
                                $__logger.Info("ArcadeAssistant: Created tag '$tagName'")
                            }
                            else {
                                $tagCache[$tagName] = $existing.Id
                            }
                        }
                    }
                }
            }
        
            # --- Build existing name set for dedup ---
            $existingNames = @{}
            foreach ($g in $PlayniteApi.Database.Games) {
                $existingNames[$g.Name] = $true
            }
        
            # --- Import Games via BufferedUpdate ---
            $imported = 0
            $skipped = 0
        
            # PS 5.1: use try/finally instead of 'using' for IDisposable
            $buffer = $PlayniteApi.Database.BufferedUpdate()
            try {
                foreach ($entry in $gameList) {
                    $gameName = $entry.name
                
                    # Skip duplicates
                    if ($existingNames.ContainsKey($gameName)) {
                        $skipped++
                        continue
                    }
                
                    # Resolve platform (cached)
                    $platName = $entry.platform
                    if (-not $platformCache.ContainsKey($platName)) {
                        $plat = $PlayniteApi.Database.Platforms | Where-Object { $_.Name -eq $platName } | Select-Object -First 1
                        if ($null -eq $plat) {
                            $plat = New-Object Playnite.SDK.Models.Platform($platName)
                            $PlayniteApi.Database.Platforms.Add($plat)
                            $__logger.Info("ArcadeAssistant: Created platform '$platName'")
                        }
                        $platformCache[$platName] = $plat.Id
                    }
                    $platformId = $platformCache[$platName]
                
                    # Create game object
                    $newGame = New-Object Playnite.SDK.Models.Game($gameName)
                    $newGame.IsInstalled = $true
                    $newGame.PlatformIds = [System.Collections.Generic.List[System.Guid]]::new()
                    $newGame.PlatformIds.Add($platformId)
                    $newGame.Notes = "ImportedBatch:$batchId"
                
                    # Set ROM path
                    $rom = New-Object Playnite.SDK.Models.GameRom($entry.romName, $entry.romPath)
                    $newGame.Roms = [System.Collections.Generic.List[Playnite.SDK.Models.GameRom]]::new()
                    $newGame.Roms.Add($rom)
                
                    # Set tags
                    if ($null -ne $entry.tags) {
                        $newGame.TagIds = [System.Collections.Generic.List[System.Guid]]::new()
                        foreach ($tagName in $entry.tags) {
                            if ($tagCache.ContainsKey($tagName)) {
                                $newGame.TagIds.Add($tagCache[$tagName])
                            }
                        }
                    }
                
                    # Add to database (GUI syncs automatically)
                    $PlayniteApi.Database.Games.Add($newGame)
                    $existingNames[$gameName] = $true
                    $imported++
                }
            }
            finally {
                if ($null -ne $buffer) { $buffer.Dispose() }
            }
        
            # --- Rename manifest to prevent re-import ---
            $processedPath = $manifestPath -replace '\.json$', ".processed_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
            Rename-Item $manifestPath $processedPath
        
            $__logger.Info("ArcadeAssistant: Batch '$batchId' complete. Imported: $imported, Skipped: $skipped")
            $PlayniteApi.Dialogs.ShowMessage(
                "Arcade Assistant Import Complete`n`nBatch: $batchId`nImported: $imported games`nSkipped (duplicates): $skipped`n`nManifest archived.",
                "Arcade Assistant"
            )
        
        }
        catch {
            $__logger.Error("ArcadeAssistant: Import failed - $_")
            $PlayniteApi.Dialogs.ShowErrorMessage(
                "Import failed: $_`n`nManifest left at: $manifestPath",
                "Arcade Assistant Error"
            )
        }
    } # end else (manifest exists)
    
    # --- Step 2: Wire game launch actions (AFTER import) ---
    try {
        "[$(Get-Date -Format 'HH:mm:ss')] Calling Wire-GameActions..." | Out-File $debugLog -Append -Encoding UTF8
        Wire-GameActions
        "[$(Get-Date -Format 'HH:mm:ss')] Wire-GameActions completed" | Out-File $debugLog -Append -Encoding UTF8
    }
    catch {
        "[$(Get-Date -Format 'HH:mm:ss')] Wire-GameActions CRASHED: $_" | Out-File $debugLog -Append -Encoding UTF8
    }
    
    # --- Step 3: Cinema Logic auto-tagging ---
    try {
        "[$(Get-Date -Format 'HH:mm:ss')] Calling Apply-CinemaLogicTags..." | Out-File $debugLog -Append -Encoding UTF8
        Apply-CinemaLogicTags
        "[$(Get-Date -Format 'HH:mm:ss')] Apply-CinemaLogicTags completed" | Out-File $debugLog -Append -Encoding UTF8
    }
    catch {
        "[$(Get-Date -Format 'HH:mm:ss')] Apply-CinemaLogicTags CRASHED: $_" | Out-File $debugLog -Append -Encoding UTF8
    }
    
    # --- Step 4: Dewey F9 HUD hotkey ---
    try {
        "[$(Get-Date -Format 'HH:mm:ss')] Starting Dewey F9 hotkey listener..." | Out-File $debugLog -Append -Encoding UTF8
        Start-DeweyHotkey
        "[$(Get-Date -Format 'HH:mm:ss')] Dewey F9 hotkey ready" | Out-File $debugLog -Append -Encoding UTF8
    }
    catch {
        "[$(Get-Date -Format 'HH:mm:ss')] Dewey F9 hotkey CRASHED: $_" | Out-File $debugLog -Append -Encoding UTF8
    }
}

# ============================================================
#  SECTION 2: LED BRIDGE (Game Events)
# ============================================================

function Get-LedTags {
    param($Game)
    $tags = @()
    if ($null -eq $Game -or $null -eq $Game.TagIds) { return $tags }
    foreach ($tagId in $Game.TagIds) {
        try {
            $tag = $PlayniteApi.Database.Tags.Get($tagId)
            if ($null -ne $tag -and $tag.Name -match "\[LED:") {
                $tags += $tag.Name
            }
        }
        catch { }
    }
    return $tags
}

function Invoke-BackendAsync {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Endpoint,
        [string]$JsonPayload = $null
    )
    $Uri = "$BackendBaseUrl/$Endpoint"
    $base64 = ""
    if ($null -ne $JsonPayload) {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($JsonPayload)
        $base64 = [System.Convert]::ToBase64String($bytes)
    }
    $psCommand = ""
    if ($base64) {
        $psCommand = "`$json = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('$base64')); Invoke-RestMethod -Uri '$Uri' -Method Post -Body `$json -ContentType 'application/json'"
    }
    else {
        $psCommand = "Invoke-RestMethod -Uri '$Uri' -Method Post"
    }
    Start-Process powershell -WindowStyle Hidden -ArgumentList @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', $psCommand)
}

function OnGameStarted {
    param($eventArgs)
    try {
        $game = $eventArgs.Game
        if ($null -eq $game) { return }
        $tags = Get-LedTags -Game $game
        $payload = @{
            game_name = $game.Name
            game_id   = $game.Id.ToString()
            tags      = $tags
            event     = "started"
            timestamp = [DateTime]::UtcNow.ToString("o")
        }
        $json = $payload | ConvertTo-Json -Compress
        Invoke-BackendAsync -Endpoint "start" -JsonPayload $json
    }
    catch { }
}

function OnGameStopped {
    param($eventArgs)
    try {
        Invoke-BackendAsync -Endpoint "stop"
    }
    catch { }
}

function OnApplicationStopped {
    # Clean up Dewey F9 HUD resources
    try { Stop-DeweyHotkey } catch { }
}
