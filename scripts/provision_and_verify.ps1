Param(
  [string]$Root = (Resolve-Path "$PSScriptRoot\..\").Path
)

$ErrorActionPreference = 'Stop'

function Read-EnvFile([string]$path) {
  $result = @{}
  if (-not (Test-Path -LiteralPath $path)) { return $result }
  Get-Content -LiteralPath $path | ForEach-Object {
    $line = $_.Trim()
    if (-not $line) { return }
    if ($line.StartsWith('#')) { return }
    if ($line -notmatch '=') { return }
    $k,$v = $line.Split('=',2)
    $result[$k.Trim()] = $v.Trim()
  }
  return $result
}

function Write-EnvValue([string]$path, [string]$key, [string]$value) {
  $lines = @()
  if (Test-Path -LiteralPath $path) { $lines = Get-Content -LiteralPath $path }
  $found = $false
  for ($i=0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match "^\s*$([regex]::Escape($key))\s*=") {
      $lines[$i] = "$key=$value"
      $found = $true
      break
    }
  }
  if (-not $found) { $lines += "$key=$value" }
  $lines | Set-Content -LiteralPath $path -Encoding ascii
}

Write-Host "=== Arcade Assistant: Provision & Verify ===" -ForegroundColor Cyan

$envFile = Join-Path $Root '.env'
$envMap = Read-EnvFile $envFile

function Ensure-Env([string]$k) {
  if ($env:$k) { return $env:$k }
  if ($envMap.ContainsKey($k)) { return $envMap[$k] }
  return ''
}

$SUPABASE_URL = Ensure-Env 'SUPABASE_URL'
$SUPABASE_SERVICE_KEY = Ensure-Env 'SUPABASE_SERVICE_KEY'
$SUPABASE_ANON_KEY = Ensure-Env 'SUPABASE_ANON_KEY'
$AA_DEVICE_ID = Ensure-Env 'AA_DEVICE_ID'
$AA_DRIVE_ROOT = (Ensure-Env 'AA_DRIVE_ROOT'); if (-not $AA_DRIVE_ROOT) { $AA_DRIVE_ROOT = 'A:\' }
$AA_VERSION = Ensure-Env 'AA_VERSION'; if (-not $AA_VERSION) { $AA_VERSION = '1.0.3' }
$DEVICE_SERIAL = Ensure-Env 'DEVICE_SERIAL'
if (-not $DEVICE_SERIAL) { $DEVICE_SERIAL = Ensure-Env 'AA_SERIAL_NUMBER' }
if (-not $DEVICE_SERIAL) { $DEVICE_SERIAL = 'UNKNOWN_SERIAL' }

if (-not $SUPABASE_URL -or -not $SUPABASE_SERVICE_KEY) {
  throw "Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in $envFile or process environment"
}

# Resolve/generate AA_DEVICE_ID
if (-not $AA_DEVICE_ID -or $AA_DEVICE_ID -eq 'generate-a-uuid-on-first-boot') {
  $AA_DEVICE_ID = [guid]::NewGuid().ToString()
  Write-Host "Generated AA_DEVICE_ID: $AA_DEVICE_ID" -ForegroundColor Yellow
  Write-EnvValue -path $envFile -key 'AA_DEVICE_ID' -value $AA_DEVICE_ID
}

# Persist identity to Drive A
$aaDir = Join-Path $AA_DRIVE_ROOT '.aa'
New-Item -ItemType Directory -Force -Path $aaDir | Out-Null
Set-Content -LiteralPath (Join-Path $aaDir 'device_id.txt') -Value $AA_DEVICE_ID -Encoding UTF8

$manifestPath = Join-Path $aaDir 'cabinet_manifest.json'
$manifest = @{}
if (Test-Path -LiteralPath $manifestPath) {
  try { $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json } catch { $manifest = @{} }
}
$manifest.device_id = $AA_DEVICE_ID
if (-not $manifest.serial) { $manifest.serial = $DEVICE_SERIAL }
if (-not $manifest.name) { $manifest.name = "Arcade Cabinet" }
$manifest | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding UTF8

# Supabase REST helpers
$baseRest = "$SUPABASE_URL/rest/v1"
$headers = @{
  apikey = $SUPABASE_SERVICE_KEY
  Authorization = "Bearer $SUPABASE_SERVICE_KEY"
}

function SB-GetDevice($id){
  $url = "$baseRest/devices?id=eq.$id&select=id"
  try { Invoke-RestMethod -Method Get -Headers $headers -Uri $url -TimeoutSec 10 } catch { $null }
}

function SB-InsertDevice($id, $serial, $version){
  $url = "$baseRest/devices"
  $body = @{
    id = $id
    serial = $serial
    status = 'online'
    version = $version
    tags = @{ build='DriveA-v1.0'; os='Win11'; aa_version=$version; profile='prod'; channel='retail' }
    last_seen = (Get-Date).ToUniversalTime().ToString("o")
  } | ConvertTo-Json
  $h = $headers.Clone()
  $h['Content-Type'] = 'application/json'
  $h['Prefer'] = 'resolution=merge-duplicates'
  try { Invoke-RestMethod -Method Post -Headers $h -Uri $url -Body $body -TimeoutSec 10 } catch { $null }
}

Write-Host "Checking/creating device in Supabase..." -ForegroundColor Cyan
$exist = SB-GetDevice $AA_DEVICE_ID
if (-not $exist) {
  $ins = SB-InsertDevice $AA_DEVICE_ID $DEVICE_SERIAL $AA_VERSION
  if ($ins) { Write-Host "Device created: $AA_DEVICE_ID" -ForegroundColor Green } else { Write-Host "Device create request sent (no response)." -ForegroundColor Yellow }
} else {
  Write-Host "Device already exists: $AA_DEVICE_ID" -ForegroundColor Green
}

# Health checks
function Try-Get($url){ try { Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 8 } catch { $null } }
$status = Try-Get 'http://127.0.0.1:8000/api/supabase/status'
$health = Try-Get 'http://127.0.0.1:8000/api/supabase/health'
$gw = Try-Get 'http://localhost:8787/healthz'

Write-Host "=== Results ===" -ForegroundColor Cyan
Write-Host ("AA_DEVICE_ID: " + $AA_DEVICE_ID)
Write-Host ("Status endpoint: " + ($(if($status){$status.StatusCode}else{'ERR'})))
Write-Host ("Health endpoint: " + ($(if($health){$health.StatusCode}else{'ERR'})))
Write-Host ("Gateway healthz: " + ($(if($gw){$gw.StatusCode}else{'ERR'})))

Write-Host "Provision & Verify complete." -ForegroundColor Cyan

