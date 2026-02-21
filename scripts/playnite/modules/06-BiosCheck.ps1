# ============================================================================
# 06-BiosCheck.ps1 — Self-contained: Verify critical BIOS files
# ============================================================================
# Just paste this entire block into Playnite PowerShell. No other files needed.
# ============================================================================

if (-not $PlayniteApi) {
    $PlayniteRunspace = Get-Runspace -Name 'PSInteractive'
    $PlayniteApi = $PlayniteRunspace.SessionStateProxy.GetVariable('PlayniteApi')
}
$DriveLetter = Split-Path -Qualifier $PlayniteApi.Paths.ApplicationPath
$DR = $DriveLetter + "\"
$biosDir = $DR + "Bios\system"

Write-Host "--- BIOS Health Check ---"
Write-Host "Checking: $biosDir"

$bios = @(
    @{ N = "PS1 US"; F = "scph5501.bin" }
    @{ N = "PS1 JP"; F = "scph5500.bin" }
    @{ N = "PS1 EU"; F = "scph5502.bin" }
    @{ N = "Saturn"; F = "saturn_bios.bin" }
    @{ N = "GBA"; F = "gba_bios.bin" }
    @{ N = "Lynx"; F = "lynxboot.img" }
    @{ N = "SegaCD US"; F = "bios_CD_U.bin" }
    @{ N = "NeoGeo"; F = "neo-epo.bin" }
    @{ N = "FDS"; F = "disksys.rom" }
    @{ N = "TG-16 CD"; F = "Syscard3.pce" }
)

$ok = 0; $miss = 0
foreach ($b in $bios) {
    $path = Join-Path $biosDir $b.F
    if (Test-Path $path) {
        $ok++
        Write-Host "  [OK] $($b.N): $($b.F)"
    }
    else {
        $miss++
        Write-Host "  [MISSING] $($b.N): $($b.F)"
    }
}

Write-Host "--- BIOS: $ok OK, $miss missing ---"
