Param(
  [string]$Root = (Resolve-Path "$PSScriptRoot\..\").Path,
  [string]$TaskName = 'ArcadeAssistantAutoStart'
)

$ErrorActionPreference = 'Stop'
$launcher = Join-Path $Root 'Start-Arcade-Assistant-8787.bat'
if (-not (Test-Path -LiteralPath $launcher)) {
  throw "Launcher not found: $launcher"
}

Write-Host "Installing auto-start scheduled task: $TaskName" -ForegroundColor Cyan

$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c cd /d `"$Root`" && `"$launcher`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -RunLevel Highest
try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue } catch {}
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal | Out-Null

Write-Host "Auto-start task installed. It will run at next logon." -ForegroundColor Green

