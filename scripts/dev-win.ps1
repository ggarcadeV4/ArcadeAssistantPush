$ErrorActionPreference = 'Stop'

# Env
$env:AA_DRIVE_ROOT = "A:\"
$env:FASTAPI_URL = "http://localhost:8000"

Write-Host "Starting FastAPI (8000)"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendScript = Join-Path $repoRoot "start_backend.ps1"
Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$backendScript`" -Port 8000" | Out-Null
Start-Sleep -Seconds 2

Write-Host "Starting Gateway (8787)"
Start-Process powershell -ArgumentList "-NoProfile -Command node gateway/server.js" | Out-Null
Start-Sleep -Seconds 2

Write-Host "Starting Frontend (Vite dev)"
npm run --prefix frontend dev

Write-Host "Running smoke checks"
& (Join-Path $repoRoot "scripts\smoke_win.ps1")
exit $LASTEXITCODE

