param(
    [switch]$NoStart  # If set, do not start services; just verify
)

$ErrorActionPreference = 'Stop'
if (!(Test-Path logs)) { New-Item -ItemType Directory -Path logs | Out-Null }

function Run-Step($label, $scriptPath, $args) {
  Write-Host ("[stack] running: " + $label)
  $powershellExe = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $stepArgs = @()
  if ($args) { $stepArgs = @($args) }
  $noStartEffective = $NoStart.IsPresent -or ($MyInvocation.UnboundArguments -contains '-NoStart') -or ($MyInvocation.Line -match '(?i)\-nostart')
  $psi = @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', $scriptPath
  )
  if ($noStartEffective) { $psi += '-NoStart' }
  $psi += $stepArgs
  $safeLabel = ($label -replace "\s+", "_").ToLower()
  $logPath = ("logs/smoke." + $safeLabel + ".out")
  try {
    $out = & $powershellExe @psi 2>&1 | Tee-Object -FilePath $logPath -ErrorAction Stop
  } catch {
    $runId = (Get-Date -Format 'yyyyMMdd_HHmmss_fff') + '_' + $PID
    $fallback = ("logs/smoke." + $safeLabel + "." + $runId + ".out")
    Write-Host ("[stack] note: log file locked, writing to " + $fallback)
    $out = & $powershellExe @psi 2>&1 | Tee-Object -FilePath $fallback
  }
  $code = $LASTEXITCODE
  $status = if ($code -eq 0) { 'GREEN' } else { 'RED' }
  $cause = ''
  if ($status -eq 'RED') {
    try {
      $m = ($out | Select-String -Pattern '^- RED \(([^)]*)\)' -SimpleMatch:$false | Select-Object -Last 1)
      if ($m) { $cause = ($m.Matches[0].Groups[1].Value) }
      if (-not $cause) { $cause = 'unknown' }
    } catch { $cause = 'unknown' }
  }
  return [pscustomobject]@{ label=$label; status=$status; code=$code; cause=$cause }
}

$cacheArgs = @()
$cache = Run-Step 'cache' 'scripts/verify-cache.ps1' $cacheArgs

$gwArgs = @()
$gw = Run-Step 'gateway' 'scripts/verify-gateway.ps1' $gwArgs

Write-Host ''
Write-Host 'Stack Smoke:'
Write-Host ("- cache:   " + $cache.status + ($(if($cache.status -eq 'RED'){ ' ('+$cache.cause+')'} else {''})))
Write-Host ("- gateway: " + $gw.status + ($(if($gw.status -eq 'RED'){ ' ('+$gw.cause+')'} else {''})))
Write-Host ''
Write-Host 'Verdict:'
if ($cache.status -eq 'GREEN' -and $gw.status -eq 'GREEN') {
  Write-Host '- GREEN'
  exit 0
} else {
  $causes = @()
  if ($cache.status -ne 'GREEN') { $causes += ('cache: ' + $cache.cause) }
  if ($gw.status -ne 'GREEN')    { $causes += ('gateway: ' + $gw.cause) }
  Write-Host ('- RED (' + ($causes -join '; ') + ')')
  exit 1
}

