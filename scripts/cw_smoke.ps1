# ConsoleWizard Smoke Test Script
# Run after starting backend (npm run dev:backend) and gateway (npm run dev:gateway)

$ErrorActionPreference = "Stop"
$Base = $env:AA_BACKEND
if (-not $Base) {
    $Base = "http://localhost:8787"
    Write-Host "Using default backend: $Base" -ForegroundColor Yellow
}

Write-Host "`n=== ConsoleWizard Smoke Test ===" -ForegroundColor Cyan
Write-Host "Backend: $Base" -ForegroundColor Gray

try {
    # 1. Health Check
    Write-Host "`n[1/4] Health Check..." -ForegroundColor Yellow
    $health = Invoke-WebRequest -UseBasicParsing "$Base/api/health"
    if ($health.StatusCode -eq 200) {
        Write-Host "  ✅ Health check passed (200 OK)" -ForegroundColor Green
        $healthJson = $health.Content | ConvertFrom-Json
        Write-Host "  Status: $($healthJson.status)" -ForegroundColor Gray
    }

    # 2. Preview (no writes)
    Write-Host "`n[2/4] Preview (read-only)..." -ForegroundColor Yellow
    $preview = Invoke-WebRequest -UseBasicParsing "$Base/api/console_wizard/retroarch/preview?core=snes9x"
    if ($preview.StatusCode -eq 200) {
        Write-Host "  ✅ Preview returned successfully" -ForegroundColor Green
        $previewJson = $preview.Content | ConvertFrom-Json
        Write-Host "  Core: $($previewJson.core)" -ForegroundColor Gray
        Write-Host "  Diff ops: $($previewJson.diff.total_ops)" -ForegroundColor Gray
    }

    # 3. Apply (with backup)
    Write-Host "`n[3/4] Apply (with backup)..." -ForegroundColor Yellow
    $body = '{"core": "snes9x"}'
    $headers = @{
        "Content-Type" = "application/json"
        "x-device-id" = "DEV-LOCAL"
        "x-scope" = "config"
    }

    $apply = Invoke-WebRequest -UseBasicParsing `
        -Uri "$Base/api/console_wizard/retroarch/apply" `
        -Method POST `
        -Headers $headers `
        -Body $body

    if ($apply.StatusCode -eq 200) {
        Write-Host "  ✅ Apply completed successfully" -ForegroundColor Green
        $applyJson = $apply.Content | ConvertFrom-Json
        Write-Host "  Backup: $($applyJson.backup_path)" -ForegroundColor Gray
        Write-Host "  Ops count: $($applyJson.ops_count)" -ForegroundColor Gray
    }

    # 4. Check logs
    Write-Host "`n[4/4] Checking logs..." -ForegroundColor Yellow
    if (Test-Path "A:\logs\changes.jsonl") {
        $logs = Get-Content "A:\logs\changes.jsonl" -Tail 5
        $lastLog = $logs[-1] | ConvertFrom-Json
        if ($lastLog.action -eq "retroarch_config_apply") {
            Write-Host "  ✅ Log entry found" -ForegroundColor Green
            Write-Host "  Action: $($lastLog.action)" -ForegroundColor Gray
            Write-Host "  Core: $($lastLog.core)" -ForegroundColor Gray
            Write-Host "  Timestamp: $($lastLog.timestamp)" -ForegroundColor Gray
        }
    } else {
        Write-Host "  ⚠️  Log file not found at A:\logs\changes.jsonl" -ForegroundColor Yellow
    }

    Write-Host "`n✅ ConsoleWizard smoke test PASSED!" -ForegroundColor Green
    Write-Host "All endpoints are working correctly.`n" -ForegroundColor Gray

} catch {
    Write-Host "`n❌ Test FAILED" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red

    # Diagnostic hints
    Write-Host "`nTroubleshooting:" -ForegroundColor Yellow
    Write-Host "1. Ensure backend is running: npm run dev:backend" -ForegroundColor Gray
    Write-Host "2. Ensure gateway is running: npm run dev:gateway" -ForegroundColor Gray
    Write-Host "3. Check ports with: netstat -ano | Select-String ':8787|:8000'" -ForegroundColor Gray
    Write-Host "4. Check A: drive exists and is accessible" -ForegroundColor Gray

    exit 1
}