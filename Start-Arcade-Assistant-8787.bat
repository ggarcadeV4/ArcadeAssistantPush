@echo off
setlocal
title Arcade Assistant (DEV 8787)
color 0A

echo ==============================================
echo   Arcade Assistant - DEV Launcher (8787)
echo ==============================================

rem Golden Drive Contract: Set AA_DRIVE_ROOT from launcher location
rem This ensures the app works on any drive letter (A:, D:, etc.)
set "AA_DRIVE_ROOT=%~dp0"
echo [INFO] AA_DRIVE_ROOT set to: %AA_DRIVE_ROOT%

rem Always run from the repo root
cd /d "%~dp0"
echo Working directory: %CD%

rem Start FastAPI backend (required for cabinets) with AA_DRIVE_ROOT
echo Starting FastAPI backend on http://localhost:8000 ...
start "FastAPI Backend" cmd /c "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%~dp0start_backend.ps1\""

rem Small delay so backend binds before gateway
timeout /t 2 >nul

rem Start Arcade Assistant gateway from its folder with AA_DRIVE_ROOT
echo Starting Gateway on http://localhost:8787 ...
start "Gateway Server" cmd /k "set AA_DRIVE_ROOT=%AA_DRIVE_ROOT% && cd gateway && node server.js"

rem Open the correct UI endpoint
echo Opening browser to http://localhost:8787/ ...
timeout /t 4 >nul
start "" "http://localhost:8787/"

echo.
echo Launcher complete. Close this window any time.
exit /b

