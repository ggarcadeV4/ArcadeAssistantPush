# Acceptance runner for Console Wizard (Preview → Apply → Restore + Dry-run)
$ErrorActionPreference = "Stop"

# Paths
$ART = "A:\preflight\evidence\console-wizard\2025-11-09"
New-Item -ItemType Directory -Force -Path $ART | Out-Null

# Helpers
function Save-Curl($name, $url, $jsonBody, $scope = 'config') {
  $payload = if ($jsonBody -is [hashtable] -or $jsonBody -is [pscustomobject]) {
    $jsonBody | ConvertTo-Json -Depth 10 -Compress
  } else {
    [string]$jsonBody
  }

  $tmp = New-TemporaryFile
  try {
    Set-Content -Path $tmp.FullName -Value $payload -Encoding ascii
    $body = @('--data-binary', "@$($tmp.FullName)")
    $out = Join-Path $ART $name
    & curl.exe -s -X POST $url '-H' 'Content-Type: application/json' '-H' 'x-device-id:cabinet-001' '-H' 'x-panel:console-wizard' '-H' "x-scope:$scope" @body |
      Out-File -FilePath $out -Encoding ascii
    Write-Host "Saved $name"
  } finally {
    Remove-Item $tmp -ErrorAction SilentlyContinue
  }
}

$defaultRequest = @{
  profile_id = 'xbox_360'
  player = 1
  include_hotkeys = $true
  include_deadzones = $true
}

# 1) Preview
Save-Curl -name 'curl_preview.txt' `
  -url 'http://localhost:3000/api/local/console/retroarch/preview' `
  -jsonBody $defaultRequest

# 2) Apply (returns backup_path + target_file)
Save-Curl -name 'curl_apply.txt' `
  -url 'http://localhost:3000/api/local/console/retroarch/apply' `
  -jsonBody $defaultRequest

# Extract backup_path and target_file for restore
$applyJson = Get-Content (Join-Path $ART 'curl_apply.txt') -Raw | ConvertFrom-Json
$backupPath = $applyJson.backup_path
$targetFile = $applyJson.target_file
if (-not $backupPath) { throw "backup_path missing in apply response." }
$backupPath | Out-File (Join-Path $ART 'extracted_backup_path.txt') -Encoding ascii
if ($targetFile) {
  $targetFile | Out-File (Join-Path $ART 'extracted_target_file.txt') -Encoding ascii
}
Write-Host "backup_path: $backupPath"

Start-Sleep -Seconds 2  # ensure backup timestamps differ before restore

# 3) Restore (writes; should create a pre-restore backup as well)
$restoreBody = @{
  backup_path = $backupPath
  target_file = $targetFile
}
Save-Curl -name 'curl_restore.txt' `
  -url 'http://localhost:3000/api/local/console/retroarch/restore' `
  -jsonBody $restoreBody

# 4) Logs & backups evidence
Get-Content A:\logs\changes.jsonl -Tail 400 |
  Out-File (Join-Path $ART 'changes_excerpt.txt') -Encoding ascii

Get-ChildItem -Recurse "A:\backups" |
  Where-Object { $_.FullName -match 'retroarch' } |
  Select-Object FullName |
  Out-File (Join-Path $ART 'ls_backups_retroarch.txt') -Encoding ascii

# 5) Dry-run proof via explicit flag
$dryRunBody = @{
  backup_path = $backupPath
  target_file = $targetFile
  dry_run = $true
}
Save-Curl -name 'curl_restore_dry_run.txt' `
  -url 'http://localhost:3000/api/local/console/retroarch/restore' `
  -jsonBody $dryRunBody

Write-Host "Acceptance artifacts saved under $ART"
