@echo off
setlocal enabledelayedexpansion
REM ============================================
REM Arcade Assistant - Pegasus Launcher v2.0
REM ============================================
REM FIXED: Better error handling, clear status messages
REM
REM This script ensures the AA backend is running
REM before launching Pegasus frontend.

title Arcade Assistant - Pegasus Launcher
echo.
echo  ============================================
echo   ARCADE ASSISTANT - Pegasus Launcher
echo  ============================================
echo.

REM Define paths
set "AA_ROOT=A:\Arcade Assistant Local"
set "PEGASUS_EXE=A:\Tools\Pegasus\pegasus-fe.exe"

REM Verify Pegasus exists
if not exist "%PEGASUS_EXE%" (
    echo  [ERROR] Pegasus not found at: %PEGASUS_EXE%
    echo.
    echo  Please install Pegasus to A:\Tools\Pegasus\
    echo.
    pause
    exit /b 1
)

REM Check if backend is already running
echo  Checking backend status...
curl.exe -s -o nul -w "%%{http_code}" http://localhost:8787/health > "%TEMP%\aa_health_check.txt" 2>&1
set /p HEALTH=<"%TEMP%\aa_health_check.txt"

if "%HEALTH%"=="200" (
    echo  [OK] Backend is already running.
    goto LAUNCH_PEGASUS
)

echo  [!] Backend not running. Starting Arcade Assistant...
echo.

REM Start the backend in a new minimized window
start /min "Arcade Assistant Backend" cmd /c "cd /d "%AA_ROOT%" && npm run dev"

REM Wait for backend to be ready
echo  Waiting for backend to initialize...
set "ATTEMPTS=0"
set "MAX_ATTEMPTS=45"

:WAIT_BACKEND
set /a ATTEMPTS+=1
if %ATTEMPTS% GTR %MAX_ATTEMPTS% (
    echo.
    echo  [ERROR] Backend failed to start after %MAX_ATTEMPTS% attempts
    echo  Please check the backend window for errors.
    echo.
    pause
    exit /b 1
)

timeout /t 2 /nobreak > nul
curl.exe -s -o nul -w "%%{http_code}" http://localhost:8787/health > "%TEMP%\aa_health_check.txt" 2>&1
set /p HEALTH=<"%TEMP%\aa_health_check.txt"

if NOT "%HEALTH%"=="200" (
    echo   Starting... [%ATTEMPTS%/%MAX_ATTEMPTS%]
    goto WAIT_BACKEND
)

echo  [OK] Backend is ready!
echo.

:LAUNCH_PEGASUS
echo  Launching Pegasus frontend...
echo.

REM Launch Pegasus and WAIT for it to close
REM This keeps the launcher window open as a reminder
start /wait "" "%PEGASUS_EXE%"

echo.
echo  ============================================
echo   Pegasus has exited.
echo  ============================================
echo.
echo  You can close this window now.
echo.

endlocal
pause
