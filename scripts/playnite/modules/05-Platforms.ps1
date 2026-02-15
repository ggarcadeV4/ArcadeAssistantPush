# ============================================================================
# 05-Platforms.ps1 — Self-contained: Ensure all platform entries exist
# ============================================================================
# Just paste this entire block into Playnite PowerShell. No other files needed.
# ============================================================================

if (-not $PlayniteApi) {
    $PlayniteRunspace = Get-Runspace -Name 'PSInteractive'
    $PlayniteApi = $PlayniteRunspace.SessionStateProxy.GetVariable('PlayniteApi')
}

function _EnsurePlatform([string]$N) {
    $e = $PlayniteApi.Database.Platforms | Where-Object { $_.Name -eq $N } | Select-Object -First 1
    if ($e) { return $e.Id }
    $p = New-Object Playnite.SDK.Models.Platform -ArgumentList $N
    $PlayniteApi.Database.Platforms.Add($p)
    Write-Host "  [NEW] $N"
    return $p.Id
}

Write-Host "--- Platforms ---"

$all = @(
    "Arcade", "Atomiswave", "Sega NAOMI", "Sega Model 2", "Sega Model 3",
    "Sega Triforce", "Daphne", "Sega Hikaru", "Pinball FX2", "Pinball FX3",
    "Singe", "TTX", "SNK Neo Geo", "SNK Neo Geo CD",
    "Atari 2600", "Atari 7800", "Atari Jaguar", "Atari Lynx",
    "NEC TurboGrafx-16", "Nintendo 64", "Nintendo Entertainment System",
    "Nintendo Game Boy", "Nintendo Game Boy Advance", "Nintendo Game Boy Color",
    "Nintendo GameCube", "Nintendo DS", "Nintendo Wii U",
    "Sega 32X", "Sega Dreamcast", "Sega Game Gear", "Sega Genesis",
    "Sega Mega Drive", "Sega Saturn", "Super Nintendo",
    "Sony PlayStation", "Sony PlayStation 2", "Sony PlayStation 3", "Sony PSP",
    "3DO", "Commodore Amiga", "DOS", "ScummVM", "PopCap"
)

foreach ($n in $all) { $null = _EnsurePlatform $n }

Write-Host "--- Platforms: $($all.Count) ensured ---"
