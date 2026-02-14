@echo off
setlocal

rem Golden Drive Contract: Set AA_DRIVE_ROOT from launcher location
rem This ensures the app works on any drive letter (A:, D:, etc.)
set "AA_DRIVE_ROOT=%~dp0"
echo [INFO] AA_DRIVE_ROOT set to: %AA_DRIVE_ROOT%

rem Change to the repo root (where this script lives)
cd /d "%~dp0"

rem Start FastAPI backend with AA_DRIVE_ROOT set
echo [INFO] Starting FastAPI backend...
set "POWERSHELL_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%POWERSHELL_EXE%" set POWERSHELL_EXE=powershell
start "FastAPI Backend" cmd /c "set AA_DRIVE_ROOT=%AA_DRIVE_ROOT% && \"%POWERSHELL_EXE%\" -NoProfile -ExecutionPolicy Bypass -File \"%~dp0start_backend.ps1\" -Port 8000"

rem Small delay so backend binds before gateway
timeout /t 2 >nul

rem Start Arcade Assistant gateway with AA_DRIVE_ROOT set
echo [INFO] Starting Gateway...
start "Gateway Server" cmd /k "set AA_DRIVE_ROOT=%AA_DRIVE_ROOT% && cd gateway && node server.js"

rem Open the correct UI endpoint
timeout /t 4 >nul
echo [INFO] Opening UI at http://localhost:8787/
start "" "http://localhost:8787/"

exit /b
