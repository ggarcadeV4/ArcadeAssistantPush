$ErrorActionPreference = 'Stop'
if (!(Test-Path logs)) { New-Item -ItemType Directory -Path logs | Out-Null }

# A) Start gateway (background, logs)

$env:FASTAPI_URL = 'http://127.0.0.1:8000'
$gw = Start-Process -WindowStyle Hidden -PassThru node -ArgumentList 'gateway/server.js' `
-RedirectStandardOutput 'logs\gateway.out' -RedirectStandardError 'logs\gateway.err'
Start-Sleep -Seconds 2

# Helpers

function Get-Snippet([string]$text) {
if (-not $text) { return '' }
($text -replace '\s+',' ').Substring(0,[Math]::Min(120, $text.Length))
}
function Probe($url, $t=5) {
try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec $t
    @{ ok = $true; snippet = (Get-Snippet $r.Content) }
} catch {
    @{ ok = $false; snippet = (Get-Snippet $_.Exception.Message) }
}
}
function GetJson($url) {
try { (Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 5).Content | ConvertFrom-Json } catch { @() }
}
function PathUsed($mu) {
if ($mu -eq 'plugin_bridge') { 'plugin' }
elseif ($mu -match 'direct|detected') { 'direct' }
else { 'backend' }
}
function Launch($g) {
if (-not $g) { return @{ title='(none)'; path='?'; success=$false; notes='no selection' } }
$hdr = @{ 'x-panel'='launchbox'; 'x-corr-id'=('proof-'+[guid]::NewGuid()) }
try {
    $r = Invoke-WebRequest -UseBasicParsing -Method POST -Headers $hdr -Uri ('http://127.0.0.1:8000/api/launchbox/launch/'+$g.id) -TimeoutSec 5
    $j = $r.Content | ConvertFrom-Json
    @{ title=$g.title; path=(PathUsed $j.method_used); success=[bool]$j.success; notes=('method_used='+$j.method_used) }
} catch {
    @{ title=$g.title; path='?'; success=$false; notes=$_.Exception.Message }
}
}

# B) Health checks (5s)

$gwH = Probe 'http://127.0.0.1:8787/api/health' 5
$beH = Probe 'http://127.0.0.1:8000/health' 5
$plH = Probe 'http://127.0.0.1:9999/health' 5  # OK if offline

# C) Pick 3 games

$f = GetJson 'http://127.0.0.1:8000/api/launchbox/games?genre=Fighting&limit=1'
$s = GetJson 'http://127.0.0.1:8000/api/launchbox/games?genre=Shooter&limit=1'
$m = GetJson 'http://127.0.0.1:8000/api/launchbox/games?genre=Maze&limit=1'
if (-not $f -or -not $s -or -not $m) {
$any = GetJson 'http://127.0.0.1:8000/api/launchbox/games?limit=200'
$f = @($any)[0]; $s = @($any)[1]; $m = @($any)[2]
}
$pick = @($f,$s,$m) | Where-Object { $_ -ne $null } | Select-Object -First 3

# D) Launch each

$l1 = Launch $pick[0]
$l2 = Launch $pick[1]
$l3 = Launch $pick[2]

# E) Output exactly

Write-Host 'Gateway:'
Write-Host ('- /api/health: ' + ($(if($gwH.ok){'PASS '}else{'FAIL '}) + $gwH.snippet))

Write-Host ''
Write-Host 'Backend:'
Write-Host ('- /health: ' + ($(if($beH.ok){'PASS '}else{'FAIL '}) + $beH.snippet))

Write-Host ''
Write-Host 'Plugin:'
Write-Host ('- 9999 reachability: ' + ($(if($plH.ok){'REACHABLE'}else{'OFFLINE'})))

Write-Host ''
Write-Host 'Launches:'
Write-Host ("- 1) {0}  path_used: {1}  success: {2}  notes: {3}" -f $l1.title,$l1.path,$l1.success,$l1.notes)
Write-Host ("- 2) {0}  path_used: {1}  success: {2}  notes: {3}" -f $l2.title,$l2.path,$l2.success,$l2.notes)
Write-Host ("- 3) {0}  path_used: {1}  success: {2}  notes: {3}" -f $l3.title,$l3.path,$l3.success,$l3.notes)

Write-Host ''
Write-Host 'Verdict:'
if ($l1.success -and $l2.success -and $l3.success) {
Write-Host '- GREEN'
} else {
$causes=@()
if (-not $l1.success){ $causes+=('1) '+$l1.notes) }
if (-not $l2.success){ $causes+=('2) '+$l2.notes) }
if (-not $l3.success){ $causes+=('3) '+$l3.notes) }
Write-Host ('- RED (' + ($causes -join '; ') + ')')
}