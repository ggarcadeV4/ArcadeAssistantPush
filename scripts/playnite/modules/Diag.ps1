# ============================================================================
# Diag.ps1 — Playnite SDK Diagnostic (paste into Playnite PowerShell)
# ============================================================================
# This script checks what's working and what's not. Paste the WHOLE thing.
# ============================================================================

Write-Host "=== PLAYNITE DIAGNOSTIC ==="

# 1. Is PlayniteApi available?
Write-Host ""
Write-Host "1. PlayniteApi check:"
if ($PlayniteApi) {
    Write-Host "   OK - PlayniteApi exists"
    Write-Host "   App Path: $($PlayniteApi.Paths.ApplicationPath)"
}
else {
    Write-Host "   FAIL - PlayniteApi is null. Trying runspace..."
    $PlayniteRunspace = Get-Runspace -Name 'PSInteractive'
    $PlayniteApi = $PlayniteRunspace.SessionStateProxy.GetVariable('PlayniteApi')
    if ($PlayniteApi) {
        Write-Host "   RECOVERED via runspace"
    }
    else {
        Write-Host "   FATAL - Cannot get PlayniteApi. Stop here."
        return
    }
}

# 2. Can we READ the database?
Write-Host ""
Write-Host "2. Database read check:"
$emuCount = $PlayniteApi.Database.Emulators.Count
$platCount = $PlayniteApi.Database.Platforms.Count
$gameCount = $PlayniteApi.Database.Games.Count
Write-Host "   Emulators: $emuCount"
Write-Host "   Platforms: $platCount"
Write-Host "   Games:     $gameCount"

# 3. List existing emulators (if any)
Write-Host ""
Write-Host "3. Existing emulators:"
if ($emuCount -gt 0) {
    foreach ($e in $PlayniteApi.Database.Emulators) {
        Write-Host "   - $($e.Name) | InstallDir: $($e.InstallDir) | Profiles: $($e.CustomProfiles.Count)"
    }
}
else {
    Write-Host "   (none)"
}

# 4. What SDK types are available?
Write-Host ""
Write-Host "4. SDK type check:"
$types = @(
    'Playnite.SDK.Models.Emulator',
    'Playnite.SDK.Models.CustomEmulatorProfile',
    'Playnite.SDK.Models.EmulatorProfile',
    'Playnite.SDK.Models.Platform',
    'Playnite.SDK.Models.GameAction'
)
foreach ($t in $types) {
    try {
        $test = [Type]::GetType($t)
        if ($test) {
            Write-Host "   [YES] $t"
        }
        else {
            # Try loading from assembly
            $test2 = $null
            try { $test2 = New-Object $t -ErrorAction Stop } catch {}
            if ($test2) {
                Write-Host "   [YES] $t (via New-Object)"
            }
            else {
                Write-Host "   [NO]  $t"
            }
        }
    }
    catch {
        Write-Host "   [ERR] $t - $($_.Exception.Message)"
    }
}

# 5. Try creating ONE platform (smallest possible write)
Write-Host ""
Write-Host "5. Write test - creating platform 'DIAG_TEST':"
try {
    $testPlat = New-Object Playnite.SDK.Models.Platform -ArgumentList "DIAG_TEST"
    Write-Host "   Created object: $($testPlat.Name) (Id: $($testPlat.Id))"
    $PlayniteApi.Database.Platforms.Add($testPlat)
    Write-Host "   Added to database - SUCCESS"
    Write-Host "   Check Settings > Platforms for 'DIAG_TEST' to confirm"
}
catch {
    Write-Host "   FAILED: $($_.Exception.Message)"
}

# 6. Try creating ONE emulator (minimal)
Write-Host ""
Write-Host "6. Write test - creating emulator 'DIAG_EMU':"
try {
    $testEmu = New-Object Playnite.SDK.Models.Emulator -ArgumentList "DIAG_EMU"
    Write-Host "   Object created: $($testEmu.Name)"
    $testEmu.InstallDir = "C:\DIAG_TEST"
    $PlayniteApi.Database.Emulators.Add($testEmu)
    Write-Host "   Added to database - SUCCESS"
    Write-Host "   Check Settings > Emulators for 'DIAG_EMU' to confirm"
}
catch {
    Write-Host "   FAILED: $($_.Exception.Message)"
    Write-Host "   Full error: $($_.Exception.ToString())"
}

Write-Host ""
Write-Host "=== DIAGNOSTIC COMPLETE ==="
Write-Host "Please share the output above so we can see exactly what's working."
