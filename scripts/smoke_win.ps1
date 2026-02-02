$ErrorActionPreference = 'Continue'

function Get-Status($url) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri $url -Method GET -TimeoutSec 3
    return $r.StatusCode
  } catch {
    return 0
  }
}

$backend = Get-Status "http://localhost:8000/health"
$gateway = Get-Status "http://localhost:8787/api/health"

if ($backend -eq 200 -and $gateway -eq 200) {
  Write-Host "✅ Dev stack healthy"
  exit 0
} else {
  Write-Host "⚠️  Degraded: backend=$backend gateway=$gateway"
  exit 2
}

