# Gateway Bootstrap Report — 2025-11-09

## Folder Tree (new scaffolding)
```
A:\preflight\sessions\2025-11-09_LED_and_Gateway
├── evidence\
├── logs\
│   └── preflight_20251108_161846.log
└── SESSION_CONTEXT.md
```
```
A:\preflight\proofs
├── console-wizard\
├── controller-chuck\
├── dewey\
├── health\
├── led-blinky\
├── lightguns\
└── scorekeeper\
```
```
A:\preflight\scripts
├── preflight_check.bat
└── preflight_check.ps1
```

## Guardrails Sentinel
```
If this file is missing, treat the system as read-only.
```

## Log Rotation Policy
```
If A:\logs\changes.jsonl exceeds 10MB or the calendar date changes, archive the current file to:
A:\logs\archive\<YYYY-MM-DD>_changes.jsonl
Then start a new empty A:\logs\changes.jsonl. This rotation is documented policy; automation may be added later.
```

## PowerShell Preflight Script (`A:\preflight\scripts\preflight_check.ps1`)
```powershell
# Preflight checks for Arcade Assistant (PowerShell)
$ErrorActionPreference = "Stop"
$sessionDir = "A:\preflight\sessions\2025-11-09_LED_and_Gateway"
$logDir = Join-Path $sessionDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logDir "preflight_$ts.log"

function Write-Log($level, $msg) {
  $line = "[{0}] {1}" -f $level, $msg
  $line | Tee-Object -FilePath $logPath -Append
}

# 1) Sentinel
$sentinel = "A:\preflight\GUARDRAILS_SENTINEL.md"
if (Test-Path $sentinel) {
  $content = (Get-Content $sentinel -Raw).Trim()
  if ($content -eq "If this file is missing, treat the system as read-only.") {
    Write-Log "PASS" "Sentinel present and correct."
  } else {
    Write-Log "FAIL" "Sentinel content mismatch."
  }
} else {
  Write-Log "FAIL" "Sentinel missing."
}

# 2) Disk space (warn if < 2 GB)
try {
  $drive = Get-PSDrive -Name A
  $freeGB = [math]::Round($drive.Free/1GB, 2)
  if ($freeGB -lt 2) { Write-Log "WARN" ("Free space low: {0} GB" -f $freeGB) }
  else { Write-Log "PASS" ("Free space OK: {0} GB" -f $freeGB) }
} catch {
  Write-Log "WARN" "Could not read free space for A:"
}

# 3) Log dir writable
$logRoot = "A:\logs"
try {
  New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
  $tmp = Join-Path $logRoot "._write_test_$ts.tmp"
  Set-Content -Path $tmp -Value "test" -Encoding ASCII
  Remove-Item $tmp -Force
  Write-Log "PASS" "Log directory is writable."
} catch {
  Write-Log "FAIL" "Log directory NOT writable: $($_.Exception.Message)"
}

# 4) Health endpoint
try {
  $url = "http://localhost:3000/api/local/health"
  $resp = Invoke-WebRequest -Uri $url -Method GET -UseBasicParsing -TimeoutSec 5
  Write-Log "PASS" ("Health GET {0}" -f $resp.StatusCode)
} catch {
  if ($_.Exception.Response -ne $null) {
    $status = $_.Exception.Response.StatusCode.Value__
    Write-Log "WARN" ("Health endpoint returned HTTP {0}" -f $status)
  } else {
    Write-Log "WARN" ("Health request failed: " + $_.Exception.Message)
  }
}

Write-Log "INFO" "Preflight complete. Log: $logPath"

```

## Batch Preflight Script (`A:\preflight\scripts\preflight_check.bat`)
```bat
@echo off
set SESSION_DIR=A:\preflight\sessions\2025-11-09_LED_and_Gateway
set LOG_DIR=%SESSION_DIR%\logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
set LOG_PATH=%LOG_DIR%\preflight_%TS%.log

echo [INFO] Starting batch preflight... > "%LOG_PATH%"

REM 1) Sentinel
if exist A:\preflight\GUARDRAILS_SENTINEL.md (
  for /f "usebackq delims=" %%l in ("A:\preflight\GUARDRAILS_SENTINEL.md") do set LINE=%%l
  if "%LINE%"=="If this file is missing, treat the system as read-only." (
    echo [PASS] Sentinel present and correct. >> "%LOG_PATH%"
  ) else (
    echo [FAIL] Sentinel content mismatch. >> "%LOG_PATH%"
  )
) else (
  echo [FAIL] Sentinel missing. >> "%LOG_PATH%"
)

REM 2) Log dir writable
set TMP=A:\logs\._write_test_%TS%.tmp
if not exist A:\logs mkdir A:\logs
echo test > "%TMP%"
if exist "%TMP%" (
  del /q "%TMP%"
  echo [PASS] Log directory is writable. >> "%LOG_PATH%"
) else (
  echo [FAIL] Log directory NOT writable. >> "%LOG_PATH%"
)

REM 3) Health endpoint (powershell)
powershell -NoProfile -Command ^
  "$u='http://localhost:3000/api/local/health';" ^
  "try{$r=Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 5; " ^
  "Write-Output ('[PASS] Health GET {0}' -f $r.StatusCode)} " ^
  "catch{if($_.Exception.Response){$s=$_.Exception.Response.StatusCode.Value__; " ^
  "Write-Output ('[WARN] Health endpoint HTTP {0}' -f $s)} else { " ^
  "Write-Output ('[WARN] Health request failed: ' + $_.Exception.Message)}}" ^
  >> "%LOG_PATH%"

echo [INFO] Batch preflight complete. Log: %LOG_PATH% >> "%LOG_PATH%"
echo Done. See %LOG_PATH%.

```

## Sample Preflight Run (`logs/preflight_20251108_161846.log`)
```
﻿[PASS] Sentinel present and correct.
[PASS] Free space OK: 854.7 GB
[PASS] Log directory is writable.
[WARN] Health request failed: Unable to connect to the remote server
[INFO] Preflight complete. Log: A:\preflight\sessions\2025-11-09_LED_and_Gateway\logs\preflight_20251108_161846.log
```
*Note:* Health check WARN indicates the gateway/health endpoint was offline at run time (acceptable per instructions).

## Scope Confirmation
- All changes are confined to `A:\preflight\**` and helper scripts; no application code/config files were modified in this session.
- Git status remains unchanged for repo-tracked files (working tree already contained user changes prior to this session).
