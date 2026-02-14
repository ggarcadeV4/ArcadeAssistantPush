# Test PCSX2 Manual Launch Script
# This script tests if PCSX2 can load a game directly

Write-Host "Testing PCSX2 Manual Launch..." -ForegroundColor Cyan
Write-Host ""

# Test 1: Launch PCSX2 with a .gz file directly
Write-Host "[Test 1] Launching PCSX2 with Devil May Cry .gz file..." -ForegroundColor Yellow
$rom = "A:\Console ROMs\playstation 2\Devil May Cry (USA).gz"

if (Test-Path $rom) {
    Write-Host "ROM file exists: $rom" -ForegroundColor Green
    Write-Host "Command: A:\Emulators\PCSX2\pcsx2-qt.exe `"$rom`"" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Press any key to launch PCSX2 with .gz file..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

    Start-Process "A:\Emulators\PCSX2\pcsx2-qt.exe" -ArgumentList "`"$rom`"" -Wait

    Write-Host ""
    Write-Host "[Result] Did the game load? (y/n): " -NoNewline -ForegroundColor Yellow
    $response1 = Read-Host
} else {
    Write-Host "ERROR: ROM file not found!" -ForegroundColor Red
    $response1 = "n"
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Test 2: Extract .gz manually and launch with .iso
Write-Host "[Test 2] Extracting .gz file manually..." -ForegroundColor Yellow

if ($response1 -ne "y") {
    $tempDir = "$env:TEMP\pcsx2_test"
    if (-not (Test-Path $tempDir)) {
        New-Item -ItemType Directory -Path $tempDir | Out-Null
    }

    Write-Host "Extracting to: $tempDir" -ForegroundColor Gray

    # Use 7-Zip if available
    $sevenZip = "C:\Program Files\7-Zip\7z.exe"
    if (Test-Path $sevenZip) {
        & $sevenZip x "$rom" -o"$tempDir" -y | Out-Null
        $isoFile = Get-ChildItem "$tempDir\*.iso" | Select-Object -First 1

        if ($isoFile) {
            Write-Host "Extracted: $($isoFile.Name)" -ForegroundColor Green
            Write-Host "Command: A:\Emulators\PCSX2\pcsx2-qt.exe `"$($isoFile.FullName)`"" -ForegroundColor Gray
            Write-Host ""
            Write-Host "Press any key to launch PCSX2 with extracted .iso file..."
            $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

            Start-Process "A:\Emulators\PCSX2\pcsx2-qt.exe" -ArgumentList "`"$($isoFile.FullName)`"" -Wait

            Write-Host ""
            Write-Host "[Result] Did the game load? (y/n): " -NoNewline -ForegroundColor Yellow
            $response2 = Read-Host

            # Cleanup
            Remove-Item -Path $tempDir -Recurse -Force
        } else {
            Write-Host "ERROR: No .iso file found after extraction!" -ForegroundColor Red
        }
    } else {
        Write-Host "ERROR: 7-Zip not found at $sevenZip" -ForegroundColor Red
        Write-Host "Please install 7-Zip or manually extract the .gz file" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Test Results Summary:" -ForegroundColor Cyan
Write-Host "  Test 1 (.gz direct): $response1" -ForegroundColor $(if($response1 -eq "y"){"Green"}else{"Red"})
if ($response2) {
    Write-Host "  Test 2 (.iso extracted): $response2" -ForegroundColor $(if($response2 -eq "y"){"Green"}else{"Red"})
}
Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
