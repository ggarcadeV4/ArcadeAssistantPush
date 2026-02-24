# clean-start.ps1 — Kill zombie gateway, rebuild frontend, deploy to A: drive, restart
# Usage: powershell -ExecutionPolicy Bypass -File scripts/clean-start.ps1

param(
    [switch]$SkipBuild,
    [switch]$SkipDeploy
)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot  # AI-Hub root
$ADrive = 'A:\Arcade Assistant Local'

Write-Host "`n=== CLEAN START ===" -ForegroundColor Cyan

# --- 1. Kill zombie processes on port 8787 ---
Write-Host "`n[1/4] Killing processes on port 8787..." -ForegroundColor Yellow
$connections = Get-NetTCPConnection -LocalPort 8787 -ErrorAction SilentlyContinue
if ($connections) {
    $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($pid in $pids) {
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "  Killing PID $pid ($($proc.ProcessName))" -ForegroundColor Red
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 1
    Write-Host "  Port 8787 cleared." -ForegroundColor Green
}
else {
    Write-Host "  No processes on port 8787." -ForegroundColor Green
}

# --- 2. Rebuild frontend ---
if (-not $SkipBuild) {
    Write-Host "`n[2/4] Building frontend..." -ForegroundColor Yellow
    Push-Location "$Root\frontend"
    npm run build 2>&1 | Select-Object -Last 3
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  BUILD FAILED" -ForegroundColor Red
        Pop-Location
        exit 1
    }
    Pop-Location
    Write-Host "  Build complete." -ForegroundColor Green
}
else {
    Write-Host "`n[2/4] Skipping build (--SkipBuild)" -ForegroundColor DarkGray
}

# --- 3. Deploy dist to A: drive ---
if (-not $SkipDeploy -and (Test-Path "$ADrive\frontend\dist")) {
    Write-Host "`n[3/4] Deploying to A: drive..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force "$ADrive\frontend\dist\assets\*" -ErrorAction SilentlyContinue
    Copy-Item -Recurse -Force "$Root\frontend\dist\*" "$ADrive\frontend\dist\"
    $hashes = Get-ChildItem "$ADrive\frontend\dist\assets\" -Name | Select-String 'index-|Assistants'
    Write-Host "  Deployed:" -ForegroundColor Green
    $hashes | ForEach-Object { Write-Host "    $_" }
}
else {
    Write-Host "`n[3/4] Skipping deploy" -ForegroundColor DarkGray
}

# --- 4. Start gateway from A: drive ---
Write-Host "`n[4/4] Starting gateway..." -ForegroundColor Yellow
Push-Location "$ADrive\gateway"
Start-Process -FilePath "node" -ArgumentList "server.js" -WindowStyle Normal
Pop-Location
Start-Sleep -Seconds 2

# Verify
try {
    $health = Invoke-WebRequest -Uri 'http://127.0.0.1:8787/healthz' -UseBasicParsing -TimeoutSec 3
    Write-Host "`n  Gateway: HTTP $($health.StatusCode)" -ForegroundColor Green
}
catch {
    Write-Host "`n  Gateway health check failed. Check terminal for errors." -ForegroundColor Red
}

Write-Host "`n=== READY ===" -ForegroundColor Cyan
Write-Host "Open http://127.0.0.1:8787/ in your browser`n"
