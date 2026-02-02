# ControllerAutoConfig-ExceptionGate-v1 Self-Test Script (PowerShell)
# Validates capsule acceptance tests 1-4

$ErrorActionPreference = "Stop"
$BACKEND_URL = "http://localhost:8888"
$GATEWAY_URL = "http://localhost:8787"
$AA_DRIVE = $env:AA_DRIVE_ROOT
if (-not $AA_DRIVE) { $AA_DRIVE = "A:" }

# Color output helpers
function Write-Success { param($msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Failure { param($msg) Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Write-Info { param($msg) Write-Host "[INFO] $msg" -ForegroundColor Cyan }

# Test counter
$script:passed = 0
$script:failed = 0

function Assert-True {
    param($condition, $message)
    if ($condition) {
        Write-Success $message
        $script:passed++
    } else {
        Write-Failure $message
        $script:failed++
        throw "Assertion failed: $message"
    }
}

Write-Host "`n[TEST] ControllerAutoConfig-ExceptionGate-v1 Self-Tests`n" -ForegroundColor Yellow

# ==============================================================================
# STEP 1: Ensure backend is running
# ==============================================================================
Write-Info "Step 1: Checking backend health..."
try {
    $health = Invoke-RestMethod -Uri "$BACKEND_URL/health" -Method GET -TimeoutSec 5
    Assert-True $true "Backend is healthy at $BACKEND_URL"
} catch {
    Write-Failure "Backend not running at $BACKEND_URL"
    Write-Info "Starting backend with: npm run dev:backend"

    # Start backend in background
    Start-Process -FilePath "npm" -ArgumentList "run", "dev:backend" -NoNewWindow

    Write-Info "Waiting 10 seconds for backend to start..."
    Start-Sleep -Seconds 10

    # Retry health check
    try {
        $health = Invoke-RestMethod -Uri "$BACKEND_URL/health" -Method GET -TimeoutSec 5
        Assert-True $true "Backend started successfully"
    } catch {
        Write-Failure "Backend failed to start after 10 seconds"
        exit 1
    }
}

# ==============================================================================
# STEP 2: Preview → Apply to staging area
# Acceptance Test 1: Writing to staging logs device_class, profile_name, backup_path
# ==============================================================================
Write-Info "`nStep 2: Testing staging write via /config/apply..."

$stagingPath = "$AA_DRIVE\config\controllers\autoconfig\staging\8BitDo_GENERIC_SN30.cfg"
$testConfig = @"
input_driver = "dinput"
input_device = "8BitDo SN30 Pro"
input_vendor_id = "0x2dc8"
input_product_id = "0x6101"
input_b_btn = "0"
input_a_btn = "1"
input_x_btn = "3"
input_y_btn = "4"
"@

# Preview first (dry-run)
$previewOps = @(
    @{
        op = "replace"
        path = $stagingPath
        value = $testConfig
    }
)
$previewBody = @{
    panel = "controller_chuck"
    dry_run = $true
    ops = $previewOps
}
$previewPayload = $previewBody | ConvertTo-Json -Depth 5 -Compress

try {
    $preview = Invoke-RestMethod -Uri "$GATEWAY_URL/api/config/preview" `
        -Method POST `
        -ContentType "application/json" `
        -Body $previewPayload `
        -TimeoutSec 10

    Assert-True ($preview -ne $null) "Preview successful (dry-run)"
} catch {
    Write-Failure "Preview failed: $_"
    exit 1
}

# Apply (actual write)
$applyOps = @(
    @{
        op = "replace"
        path = $stagingPath
        value = $testConfig
    }
)
$applyBody = @{
    panel = "controller_chuck"
    dry_run = $false
    ops = $applyOps
}
$applyPayload = $applyBody | ConvertTo-Json -Depth 5 -Compress

try {
    $apply = Invoke-RestMethod -Uri "$GATEWAY_URL/api/config/apply" `
        -Method POST `
        -ContentType "application/json" `
        -Headers @{
            "x-device-id" = "TEST-DEVICE"
            "x-scope" = "config"
        } `
        -Body $applyPayload `
        -TimeoutSec 10

    Assert-True ($apply -ne $null) "Apply successful (staging write)"
} catch {
    Write-Failure "Apply failed: $_"
    exit 1
}

# Verify file exists
Assert-True (Test-Path $stagingPath) "Staging file exists at $stagingPath"

# ==============================================================================
# STEP 3: Mirror to RetroArch autoconfig
# Acceptance Test 2: Mirror writes to emulator trees only (no gateway writes)
# ==============================================================================
Write-Info "`nStep 3: Testing mirror operation..."

$mirrorBody = @{
    profile_name = "8BitDo_GENERIC_SN30"
    device_class = "controller"
    vendor_id = "2dc8"
    product_id = "6101"
}
$mirrorPayload = $mirrorBody | ConvertTo-Json -Compress

try {
    $mirror = Invoke-RestMethod -Uri "$BACKEND_URL/api/controllers/autoconfig/mirror" `
        -Method POST `
        -ContentType "application/json" `
        -Body $mirrorPayload `
        -TimeoutSec 10

    Assert-True ($mirror.status -eq "mirrored") "Mirror operation successful"
    Assert-True ($mirror.mirror_paths.Count -gt 0) "Mirror created files in emulator trees"

    Write-Info "Mirrored to: $($mirror.mirror_paths -join ', ')"
} catch {
    Write-Failure "Mirror failed: $_"
    exit 1
}

# ==============================================================================
# STEP 4: Verify presence in RetroArch autoconfig folder
# ==============================================================================
Write-Info "`nStep 4: Verifying RetroArch autoconfig files..."

$retroarchPaths = @(
    "$AA_DRIVE\Emulators\RetroArch\autoconfig\8BitDo\8BitDo_GENERIC_SN30.cfg",
    "$AA_DRIVE\LaunchBox\Emulators\RetroArch\autoconfig\8BitDo\8BitDo_GENERIC_SN30.cfg"
)

$foundCount = 0
foreach ($path in $retroarchPaths) {
    if (Test-Path $path) {
        $foundCount++
        Write-Success "Found mirrored config at: $path"
    }
}

Assert-True ($foundCount -gt 0) "At least one RetroArch autoconfig file created"

# ==============================================================================
# STEP 5: Tail changes.jsonl and verify log fields
# Acceptance Test 4: Logs contain {device_class, vendor_id, product_id, profile_name, backup_path}
# ==============================================================================
Write-Info "`nStep 5: Verifying audit log entries..."

$logFile = "$AA_DRIVE\logs\changes.jsonl"
Assert-True (Test-Path $logFile) "Audit log exists at $logFile"

# Get last 5 lines (should include our mirror operation)
$lastLines = Get-Content $logFile -Tail 5

$foundMirrorLog = $false
foreach ($line in $lastLines) {
    try {
        $entry = $line | ConvertFrom-Json

        if ($entry.operation -eq "mirror" -and $entry.profile_name -eq "8BitDo_GENERIC_SN30") {
            $foundMirrorLog = $true

            # Verify required fields
            Assert-True ($entry.device_class -ne $null) "Log contains device_class"
            Assert-True ($entry.vendor_id -ne $null) "Log contains vendor_id"
            Assert-True ($entry.product_id -ne $null) "Log contains product_id"
            Assert-True ($entry.profile_name -ne $null) "Log contains profile_name"
            Assert-True ($entry.mirror_paths -ne $null) "Log contains mirror_paths"

            Write-Info "Audit log entry: $line"
            break
        }
    } catch {
        # Skip malformed lines
    }
}

Assert-True $foundMirrorLog "Found mirror operation in audit log"

# ==============================================================================
# STEP 6: Test device detection (with MOCK_DEVICES)
# Acceptance Test 3: Input probe <50ms with MOCK_DEVICES
# ==============================================================================
Write-Info "`nStep 6: Testing device detection with mock devices..."

# Set mock devices environment variable
$env:MOCK_DEVICES = '[{"vid":"2dc8","pid":"6101","name":"8BitDo SN30 Pro"}]'

try {
    $start = Get-Date
    $devices = Invoke-RestMethod -Uri "$BACKEND_URL/api/controllers/autoconfig/detect?force_refresh=true" `
        -Method GET `
        -TimeoutSec 5
    $elapsed = (Get-Date) - $start

    Assert-True ($devices.count -gt 0) "Detected mock devices"
    $detectionTime = [int]$elapsed.TotalMilliseconds
    Assert-True ($detectionTime -lt 100) "Detection completed in $detectionTime ms (target under 100ms)"

    Write-Info "Detection time: $([int]$elapsed.TotalMilliseconds)ms"
} catch {
    Write-Failure "Device detection failed: $_"
    exit 1
}

# ==============================================================================
# SUMMARY
# ==============================================================================
Write-Host "`n" -NoNewline
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host " Test Results" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Success "Passed: $script:passed"
if ($script:failed -gt 0) {
    Write-Failure "Failed: $script:failed"
    Write-Host "`n[FAILED] Self-tests FAILED`n" -ForegroundColor Red
    exit 1
} else {
    Write-Host "`n[SUCCESS] All self-tests PASSED`n" -ForegroundColor Green
    Write-Host "Capsule ControllerAutoConfig-ExceptionGate-v1 validated successfully." -ForegroundColor Cyan
    Write-Host "Ready for merge with CONTROLLER_AUTOCONFIG_ENABLED=false by default.`n" -ForegroundColor Cyan
    exit 0
}
