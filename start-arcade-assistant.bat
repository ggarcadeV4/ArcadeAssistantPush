@echo off
REM ========================================
REM Arcade Assistant - Startup Script
REM ========================================
REM This script starts the backend and gateway services
REM Desktop shortcut "Arcade Assistant" runs this file

color 0B
title Arcade Assistant - Starting Services...

cd /d "%~dp0"

echo.
echo ========================================
echo   ARCADE ASSISTANT
echo   Starting Services...
echo ========================================
echo.

REM ----------------------------------------
REM PRE-FLIGHT CHECK: Validate before launch
REM ----------------------------------------
echo [0/3] Running pre-flight check...
python scripts/preflight_check.py
set PREFLIGHT_RESULT=%ERRORLEVEL%

if %PREFLIGHT_RESULT%==1 (
    color 0C
    echo.
    echo ========================================
    echo   STARTUP ABORTED
    echo ========================================
    echo.
    echo Critical errors were found during pre-flight.
    echo Please fix the issues above before trying again.
    echo.
    echo Need help? Check docs/TROUBLESHOOTING.md
    echo.
    pause
    exit /b 1
)

if %PREFLIGHT_RESULT%==2 (
    color 0E
    echo.
    echo Warnings detected but continuing startup...
    timeout /t 3 /nobreak >nul
)

color 0B

REM Check if .env exists (backup check)
if not exist .env (
    echo [ERROR] .env file not found!
    echo.
    echo Please run install-cabinet.bat first to set up your cabinet.
    echo.
    pause
    exit /b 1
)

REM Read device serial from .env
for /f "tokens=2 delims==" %%a in ('findstr /r "^DEVICE_SERIAL=" .env') do set DEVICE_SERIAL=%%a
for /f "tokens=2 delims==" %%a in ('findstr /r "^DEVICE_NAME=" .env') do set DEVICE_NAME=%%a

if not "%DEVICE_SERIAL%"=="" (
    echo Cabinet: "%DEVICE_NAME%" [%DEVICE_SERIAL%]
    echo.
)

    set "POWERSHELL_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
    if not exist "%POWERSHELL_EXE%" set POWERSHELL_EXE=powershell
    start "AA Backend [%DEVICE_SERIAL%]" cmd /k "\"%POWERSHELL_EXE%\" -NoProfile -ExecutionPolicy Bypass -File \"%~dp0start_backend.ps1\" -Port 8888"
start "AA Backend [%DEVICE_SERIAL%]" cmd /k "python -m uvicorn backend.app:app --host 0.0.0.0 --port 8888"
timeout /t 3 /nobreak >nul

echo [2/3] Starting gateway (Express on port 8787)...
start "AA Gateway [%DEVICE_SERIAL%]" cmd /k "node gateway/server.js"
timeout /t 3 /nobreak >nul

echo [3/3] Services started!
echo.
echo ========================================
echo   SERVICES RUNNING
echo ========================================
echo.
echo Backend:  http://localhost:8888
echo Gateway:  http://localhost:8787
echo Frontend: http://localhost:8787
echo.
echo Two command windows should have opened:
echo - AA Backend [%DEVICE_SERIAL%]
echo - AA Gateway [%DEVICE_SERIAL%]
echo.
echo IMPORTANT: Do NOT close those windows!
echo They must stay open for Arcade Assistant to work.
echo.
echo ========================================
echo   NEXT STEPS:
echo ========================================
echo.
echo 1. Wait 10 seconds for services to fully start
echo.
echo 2. Double-click "Open Arcade Assistant" on your desktop
echo    OR open your browser to: http://localhost:8787
echo.
echo 3. To stop Arcade Assistant, close the backend and gateway windows
echo.
echo ========================================
echo.

REM Log startup
echo %DATE% %TIME% - Cabinet %DEVICE_SERIAL% started >> startup.log

echo Press any key to close this window...
echo (Backend and Gateway will keep running)
pause >nul
