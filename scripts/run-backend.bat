@echo off
cd /d "%~dp0.."

if not defined AA_DRIVE_ROOT (
    set "AA_DRIVE_ROOT=%~d0\"
)

:: Prefer explicit PowerShell path for reliability
set POWERSHELL_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe
if not exist "%POWERSHELL_EXE%" set POWERSHELL_EXE=powershell

:: Delegate to the canonical startup script (loads .env, uses venv, guards WSL)
"%POWERSHELL_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\\start_backend.ps1"
