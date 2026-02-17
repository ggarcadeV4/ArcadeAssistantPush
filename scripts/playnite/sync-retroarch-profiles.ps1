# ============================================================
#  sync-retroarch-profiles.ps1
#  Directly injects missing RetroArch profiles into Playnite's
#  emulators.db via LiteDB. Run with Playnite STOPPED.
# ============================================================
param(
    [string]$PlaynitePath = "A:\Playnite"
)

# Load LiteDB
$liteDll = Join-Path $PlaynitePath "LiteDB.dll"
if (-not (Test-Path $liteDll)) {
    Write-Host "ERROR: LiteDB.dll not found at $liteDll" -ForegroundColor Red
    exit 1
}
Add-Type -Path $liteDll

# --- Read platform GUIDs ---
$platDb = New-Object LiteDB.LiteDatabase("Filename=$(Join-Path $PlaynitePath 'library\platforms.db');ReadOnly=true")
$platCol = $platDb.GetCollection("Platforms")
$platMap = @{}  # name -> GUID string
foreach ($p in $platCol.FindAll()) {
    $platMap[$p["Name"].AsString] = $p["_id"].AsGuid.ToString()
}
$platDb.Dispose()
Write-Host "Loaded $($platMap.Count) platforms"

# --- Open emulators DB ---
$emuDb = New-Object LiteDB.LiteDatabase("Filename=$(Join-Path $PlaynitePath 'library\emulators.db')")
$emuCol = $emuDb.GetCollection("Emulators")

# Find RetroArch
$ra = $null
foreach ($emu in $emuCol.FindAll()) {
    if ($emu["Name"].AsString -eq "RetroArch") {
        $ra = $emu
        break
    }
}

if ($null -eq $ra) {
    Write-Host "ERROR: RetroArch emulator not found in DB" -ForegroundColor Red
    $emuDb.Dispose()
    exit 1
}

# Get existing profile names
$existingNames = @{}
$profiles = $ra["CustomProfiles"]
if ($null -ne $profiles -and $profiles.IsArray) {
    foreach ($p in $profiles.AsArray) {
        $existingNames[$p["Name"].AsString] = $true
    }
}
Write-Host "RetroArch has $($existingNames.Count) existing profiles: $($existingNames.Keys -join ', ')"

# --- Define all profiles ---
$allProfiles = @(
    @{ Name = "NES"; Core = "fceumm_libretro.dll"; Plat = "Nintendo Entertainment System"; Ext = "zip,nes,7z" },
    @{ Name = "SNES"; Core = "snes9x_libretro.dll"; Plat = "Super Nintendo Entertainment System"; Ext = "zip,sfc,smc,7z" },
    @{ Name = "N64"; Core = "mupen64plus_next_libretro.dll"; Plat = "Nintendo 64"; Ext = "zip,n64,z64,v64,7z" },
    @{ Name = "Game Boy"; Core = "gambatte_libretro.dll"; Plat = "Nintendo Game Boy"; Ext = "zip,gb,gbc,7z" },
    @{ Name = "GBA"; Core = "mgba_libretro.dll"; Plat = "Nintendo Game Boy Advance"; Ext = "zip,gba,7z" },
    @{ Name = "NDS"; Core = "desmume_libretro.dll"; Plat = "Nintendo DS"; Ext = "zip,nds,7z" },
    @{ Name = "Genesis-MD"; Core = "genesis_plus_gx_libretro.dll"; Plat = "Sega Mega Drive/Genesis"; Ext = "zip,md,bin,gen,smd,7z" },
    @{ Name = "Genesis"; Core = "genesis_plus_gx_libretro.dll"; Plat = "Sega Genesis"; Ext = "zip,md,bin,gen,smd,7z" },
    @{ Name = "Game Gear"; Core = "genesis_plus_gx_libretro.dll"; Plat = "Sega Game Gear"; Ext = "zip,gg,7z" },
    @{ Name = "32X"; Core = "picodrive_libretro.dll"; Plat = "Sega 32X"; Ext = "zip,32x,7z" },
    @{ Name = "Dreamcast"; Core = "flycast_libretro.dll"; Plat = "Sega Dreamcast"; Ext = "zip,cdi,gdi,chd,7z" },
    @{ Name = "Saturn"; Core = "mednafen_saturn_libretro.dll"; Plat = "Sega Saturn"; Ext = "zip,cue,bin,chd,iso,7z" },
    @{ Name = "PS1"; Core = "pcsx_rearmed_libretro.dll"; Plat = "Sony PlayStation"; Ext = "zip,iso,bin,cue,img,pbp,chd,m3u" },
    @{ Name = "PSP"; Core = "ppsspp_libretro.dll"; Plat = "Sony PSP"; Ext = "zip,iso,cso,pbp,7z" },
    @{ Name = "PS2"; Core = "pcsx2_libretro.dll"; Plat = "Sony PlayStation 2"; Ext = "iso,bin,chd,cso,gz,m3u" },
    @{ Name = "PS Minis"; Core = "pcsx_rearmed_libretro.dll"; Plat = "Sony PlayStation Minis"; Ext = "zip,pbp,iso,7z" },
    @{ Name = "Atari 2600"; Core = "stella_libretro.dll"; Plat = "Atari 2600"; Ext = "zip,a26,bin,7z" },
    @{ Name = "Atari 7800"; Core = "prosystem_libretro.dll"; Plat = "Atari 7800"; Ext = "zip,a78,bin,7z" },
    @{ Name = "Atari Jaguar"; Core = "virtualjaguar_libretro.dll"; Plat = "Atari Jaguar"; Ext = "zip,j64,jag,7z" },
    @{ Name = "Atari Lynx"; Core = "handy_libretro.dll"; Plat = "Atari Lynx"; Ext = "zip,lnx,7z" },
    @{ Name = "TurboGrafx-16"; Core = "mednafen_pce_fast_libretro.dll"; Plat = "NEC TurboGrafx-16"; Ext = "zip,pce,7z" },
    @{ Name = "NAOMI"; Core = "flycast_libretro.dll"; Plat = "Sega NAOMI"; Ext = "zip,7z,lst,bin,dat" },
    @{ Name = "Atomiswave"; Core = "flycast_libretro.dll"; Plat = "Atomiswave"; Ext = "zip,7z,lst,bin" }
)

# --- Add missing profiles ---
$added = 0
$profileArray = $ra["CustomProfiles"].AsArray

foreach ($def in $allProfiles) {
    if ($existingNames.ContainsKey($def.Name)) { continue }
    
    $prof = New-Object LiteDB.BsonDocument
    $prof["_id"] = [LiteDB.BsonValue]::new([System.Guid]::NewGuid())
    $prof["Name"] = [LiteDB.BsonValue]::new($def.Name)
    $prof["Executable"] = [LiteDB.BsonValue]::new('{EmulatorDir}\retroarch.exe')
    $prof["Arguments"] = [LiteDB.BsonValue]::new('-L "{EmulatorDir}\cores\' + $def.Core + '" "{ImagePath}"')
    
    # Extensions
    $extArray = New-Object LiteDB.BsonArray
    foreach ($ext in $def.Ext.Split(",")) {
        $extArray.Add([LiteDB.BsonValue]::new($ext.Trim()))
    }
    $prof["ImageExtensions"] = $extArray
    
    # Platform ID
    if ($platMap.ContainsKey($def.Plat)) {
        $platArray = New-Object LiteDB.BsonArray
        $platArray.Add([LiteDB.BsonValue]::new([System.Guid]::Parse($platMap[$def.Plat])))
        $prof["Platforms"] = $platArray
        Write-Host "  + $($def.Name) -> $($def.Plat) ($($platMap[$def.Plat]))" -ForegroundColor Green
    } else {
        Write-Host "  + $($def.Name) (WARNING: platform '$($def.Plat)' not found)" -ForegroundColor Yellow
    }
    
    $profileArray.Add($prof)
    $added++
}

if ($added -gt 0) {
    $emuCol.Update($ra)
    Write-Host "`n=== $added profiles added to RetroArch ===" -ForegroundColor Cyan
    Write-Host "Total profiles: $($profileArray.Count)"
} else {
    Write-Host "`nAll profiles already up to date ($($profileArray.Count) total)" -ForegroundColor Green
}

$emuDb.Dispose()
Write-Host "Done. Restart Playnite to pick up changes."
