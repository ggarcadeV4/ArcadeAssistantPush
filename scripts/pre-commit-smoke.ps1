param(
  [switch]$NoStart
)

$ErrorActionPreference = 'Stop'

Write-Host "[pre-commit] Running smoke check..."

try {
  if ($NoStart) {
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-cache.ps1 -NoStart
  } else {
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-cache.ps1 -NoStart
  }
  if ($LASTEXITCODE -ne 0) { throw "Smoke script returned non-zero: $LASTEXITCODE" }
  Write-Host "[pre-commit] Smoke check GREEN. Proceeding with commit."
  exit 0
} catch {
  Write-Host "[pre-commit] Smoke check failed (RED). Commit blocked."
  Write-Host "Hint: Start backend locally, then retry commit; or run scripts\\verify-cache.ps1 -NoStart to see details."
  exit 1
}

