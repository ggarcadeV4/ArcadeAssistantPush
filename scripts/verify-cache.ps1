param(
    [switch]$NoStart  # If set, do not start backend; just verify existing process
)

$ErrorActionPreference = 'Stop'

# Ensure logs directory exists
if (!(Test-Path logs)) { New-Item -ItemType Directory -Path logs | Out-Null }

# A) Ports: kill anything on 8000 unless --NoStart
$killedStr = 'none'
if (-not $NoStart) {
    try {
        $pid8000 = (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
                    Select-Object -First 1 -ExpandProperty OwningProcess)
        if ($pid8000) {
            Stop-Process -Id $pid8000 -Force -ErrorAction SilentlyContinue
            $killedStr = "8000:$pid8000"
        }
    } catch {}
}

# B) Environment (Windows AA_DRIVE_ROOT requires trailing backslash)
$env:AA_PRELOAD_LB_CACHE = 'true'
if (-not $env:AA_DRIVE_ROOT -or [string]::IsNullOrWhiteSpace($env:AA_DRIVE_ROOT)) {
    $env:AA_DRIVE_ROOT = 'A:\'
}
$env:PYTHONUNBUFFERED = '1'

# C) Start backend (unless --NoStart)
$procId = 'already running'
if (-not $NoStart) {
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    $backendScript = Join-Path $repoRoot 'start_backend.ps1'
    $powershellExe = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if (-not (Test-Path $powershellExe)) { $powershellExe = 'powershell' }

    $proc = Start-Process -WindowStyle Hidden -PassThru `
        $powershellExe -ArgumentList @(
            '-NoProfile',
            '-ExecutionPolicy','Bypass',
            '-File', $backendScript,
            '-Port','8000',
            '-Host','127.0.0.1'
        ) `
        -RedirectStandardOutput 'logs\backend.out' `
        -RedirectStandardError  'logs\backend.err'
    $procId = $proc.Id
    Start-Sleep -Seconds 2
}

# D) Find glob pre-check line in logs
$globLine = (Select-String -Path @('logs\backend.out','logs\backend.err') `
             -Pattern 'LaunchBox XML glob pre-check:' -ErrorAction SilentlyContinue |
             Select-Object -Last 1).Line
if (-not $globLine) {
    Start-Sleep -Seconds 2
    $globLine = (Select-String -Path @('logs\backend.out','logs\backend.err') `
                 -Pattern 'LaunchBox XML glob pre-check:' -ErrorAction SilentlyContinue |
                 Select-Object -Last 1).Line
}
$globN = $null
if ($globLine -match 'files_found=(\d+)') { $globN = [int]$Matches[1] }

function Probe([string]$url,[int]$t){
  try { Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec $t | Out-Null; 'OK' }
  catch { if ($_.Exception.Message -match 'timed out') { 'TIMEOUT' } else { 'ERROR ' + $_.Exception.Message } }
}

# E) Warm + probes
$p_health = Probe 'http://127.0.0.1:8000/health' 5
$p_platforms = Probe 'http://127.0.0.1:8000/api/launchbox/platforms' 30
$p_games_big = Probe 'http://127.0.0.1:8000/api/launchbox/games?page=1&limit=500' 30

$gamesStatus = 'ERROR'
$gamesCount = -1
$gamesTotal = -1
try {
    $resp = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8000/api/launchbox/games?page=1&limit=200' -TimeoutSec 5
    $data = $resp.Content | ConvertFrom-Json
    if ($null -ne $data.games) {
        $gamesCount = ($data.games | Measure-Object).Count
        $gamesTotal = [int]$data.total
    } else {
        # Legacy array shape
        $gamesCount = ($data | Measure-Object).Count
        $gamesTotal = $gamesCount
    }
    $gamesStatus = 'OK'
} catch {
    if ($_.Exception.Message -match 'timed out') { $gamesStatus='TIMEOUT' } else { $gamesStatus='ERROR ' + $_.Exception.Message }
}

# F) Output summary
Write-Host 'Backend:'
Write-Host ('- 8000 reset: ' + $killedStr)
Write-Host ('- pid: ' + $procId)
Write-Host ''
Write-Host 'Glob:'
$globLineSafe = if ($globLine) { $globLine } else { 'n/a' }
Write-Host ('- line: "' + $globLineSafe + '"')
Write-Host ''
Write-Host 'Warm:'
Write-Host ('- /health (5s): ' + $p_health)
Write-Host ('- /platforms (30s): ' + $p_platforms)
Write-Host ('- /games?page=1&limit=500 (30s): ' + $p_games_big)
Write-Host ('- /games?page=1&limit=200 (5s): ' + $gamesStatus + '  page_count=' + $gamesCount + '  total=' + $gamesTotal)
Write-Host ''
Write-Host 'Verdict:'
$globOk = $true
if (-not $NoStart) {
    $globOk = ($globN -as [int]) -gt 0
}
$isGreen = $globOk -and $p_health -eq 'OK' -and $gamesStatus -eq 'OK' -and $gamesTotal -gt 100
if ($isGreen) {
    Write-Host '- GREEN'
    exit 0
} else {
    $cause = 'unknown'
    if (-not $globOk) { $cause = 'files_found=0' }
    elseif ($p_platforms -like 'TIMEOUT*' -or $p_games_big -like 'TIMEOUT*') { $cause = 'warm TIMEOUT' }
    elseif ($gamesStatus -ne 'OK' -or $gamesTotal -le 100) { $cause = 'total<=100' }
    Write-Host ('- RED (' + $cause + ')')
    exit 1
}

