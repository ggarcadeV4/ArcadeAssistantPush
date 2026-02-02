param(
    [switch]$NoStart  # If set, do not start gateway; just verify
)

$ErrorActionPreference = 'Stop'

if (!(Test-Path logs)) { New-Item -ItemType Directory -Path logs | Out-Null }

# A) Kill anything on 8787 unless --NoStart
$killedStr = 'none'
if (-not $NoStart) {
  try {
    $pid8787 = (Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue |
                Select-Object -First 1 -ExpandProperty OwningProcess)
    if ($pid8787) { Stop-Process -Id $pid8787 -Force -ErrorAction SilentlyContinue; $killedStr = "8787:$pid8787" }
  } catch {}
}

# B) Ensure FASTAPI_URL for proxy (fallback to localhost:8000)
if (-not $env:FASTAPI_URL -or [string]::IsNullOrWhiteSpace($env:FASTAPI_URL)) {
  $env:FASTAPI_URL = 'http://127.0.0.1:8000'
}

# C) Start gateway in background (unless --NoStart)
$gatewayProcessId = 'already running'
if (-not $NoStart) {
  $gw = Start-Process -WindowStyle Hidden -PassThru node -ArgumentList 'gateway/server.js' `
    -RedirectStandardOutput 'logs\gateway.out' `
    -RedirectStandardError  'logs\gateway.err'
  $gatewayProcessId = $gw.Id
  Start-Sleep -Seconds 2
}

function Get-Snippet([string]$text) {
  if (-not $text) { return '' }
  ($text -replace '\s+',' ').Substring(0,[Math]::Min(120, $text.Length))
}

function Probe($url,$t=5){
  try { $r=Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec $t; @{ ok=$true; body=$r.Content } }
  catch { @{ ok=$false; body=$_.Exception.Message } }
}

# D) Probes (5s timeouts)
$gwH = Probe 'http://127.0.0.1:8787/api/health' 5
$ptH = Probe 'http://127.0.0.1:8787/api/local/health' 5

$lbCount = -1; $lbStat='FAIL'
try {
  $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8787/api/launchbox/games?page=1&limit=10' -TimeoutSec 5
  $data = $r.Content | ConvertFrom-Json
  if ($null -ne $data.games) {
    $lbCount = ($data.games | Measure-Object).Count
  } else {
    $lbCount = ($data | Measure-Object).Count
  }
  $lbStat = 'PASS'
} catch {
  $lbStat = 'FAIL'
}

# E) Output summary
Write-Host 'Gateway:'
Write-Host ('- /api/health: ' + ($(if($gwH.ok){'PASS '}else{'FAIL '}) + (Get-Snippet $gwH.body)))
Write-Host ''
Write-Host 'Passthrough:'
Write-Host ('- /api/local/health: ' + ($(if($ptH.ok){'PASS '}else{'FAIL '}) + (Get-Snippet $ptH.body)))
Write-Host ''
Write-Host 'LaunchBox:'
Write-Host ('- /api/launchbox/games?page=1&limit=10: ' + $lbStat + '  page_count=' + $lbCount)
Write-Host ''
Write-Host 'Meta:'
Write-Host ('- 8787 reset: ' + $killedStr)
Write-Host ('- pid: ' + $gatewayProcessId)
Write-Host ''
Write-Host 'Verdict:'
if ($gwH.ok -and $ptH.ok -and $lbCount -ge 1) {
  Write-Host '- GREEN'
  exit 0
} else {
  $cause='unknown'
  if (-not $gwH.ok) { $cause='gateway health' }
  elseif (-not $ptH.ok) { $cause='passthrough health' }
  elseif ($lbCount -lt 1) { $cause='launchbox count<=0' }
  Write-Host ('- RED (' + $cause + ')')
  exit 1
}

