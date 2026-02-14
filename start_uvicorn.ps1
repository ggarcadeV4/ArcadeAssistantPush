$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$env:AA_QUICKSTART='true'
$env:AA_PRELOAD_LB_CACHE='true'
$env:PYTHONUNBUFFERED='1'

& "$ScriptDir\start_backend.ps1" -Port 8000 *> backend\uvicorn.log
