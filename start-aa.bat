@echo off
setlocal EnableDelayedExpansion

rem ============================================================================
rem  Arcade Assistant - Production Launcher (Golden Drive)
rem  Serve-only boot: provision identity, verify dist, then start services
rem ============================================================================

cd /d "%~dp0"

set "DRIVE=%~d0"
set "LOGDIR=%DRIVE%\.aa\logs"
set "REPOROOT=%~dp0"
set "DIST_INDEX=%REPOROOT%frontend\dist\index.html"
set "AA_DRIVE_ROOT=%DRIVE%\"

set PYTHON_EXE=python
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
)
set PYTHONW_EXE=pythonw
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    set "PYTHONW_EXE=%~dp0.venv\Scripts\pythonw.exe"
)
rem [TEMPORARILY DISABLED 2026-03-16] Marquee auto-launch causes black-screen
rem on secondary monitor during dev. RE-ENABLE before drive duplication for
rem live cabinet hardware. See README "Marquee System" section.
rem Original: if not defined AA_MARQUEE_ENABLED ( set "AA_MARQUEE_ENABLED=1" )
set "AA_MARQUEE_ENABLED=0"
set AA_UPDATES_ENABLED=0

echo ============================================================
echo  Arcade Assistant - Starting...
echo ============================================================
echo.
echo ------------------------------------------------------------
echo  ENVIRONMENT
echo ------------------------------------------------------------
for /f "delims=" %%i in ('where node 2^>nul') do @echo   Node Path: %%i
for /f "delims=" %%i in ('node --version 2^>nul') do @echo   Node Version: %%i
for /f "delims=" %%i in ('where !PYTHON_EXE! 2^>nul') do @echo   Python Path: %%i
for /f "delims=" %%i in ('"!PYTHON_EXE!" --version 2^>nul') do @echo   Python Version: %%i
echo ------------------------------------------------------------
echo.
echo  Drive: %DRIVE%
echo  Repo:  %REPOROOT%
echo  AA_DRIVE_ROOT: %AA_DRIVE_ROOT%
echo ============================================================
echo.

if not exist "%LOGDIR%" (
    echo [INFO] Creating log folder: %LOGDIR%
    mkdir "%LOGDIR%"
)

echo [INFO] Checking for existing processes on ports 8000 and 8787...
set "KILLED_PIDS="

for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000.*LISTENING"') do (
    set "PID=%%a"
    echo "!KILLED_PIDS!" | findstr /C:":!PID!:" >nul 2>&1
    if errorlevel 1 (
        for /f "tokens=1" %%b in ('tasklist /fi "PID eq !PID!" /nh 2^>nul ^| findstr /i "python.exe node.exe cmd.exe"') do (
            echo [INFO] Killing existing process on port 8000 ^(PID: !PID!^)
            taskkill /F /T /PID !PID! >nul 2>&1
            set "KILLED_PIDS=!KILLED_PIDS!:!PID!:"
        )
    )
)

for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8787.*LISTENING"') do (
    set "PID=%%a"
    echo "!KILLED_PIDS!" | findstr /C:":!PID!:" >nul 2>&1
    if errorlevel 1 (
        for /f "tokens=1" %%b in ('tasklist /fi "PID eq !PID!" /nh 2^>nul ^| findstr /i "python.exe node.exe cmd.exe"') do (
            echo [INFO] Killing existing process on port 8787 ^(PID: !PID!^)
            taskkill /F /T /PID !PID! >nul 2>&1
            set "KILLED_PIDS=!KILLED_PIDS!:!PID!:"
        )
    )
)

timeout /t 1 >nul

echo [INFO] Bootstrapping cabinet identity and local config...
"!PYTHON_EXE!" "%REPOROOT%scripts\bootstrap_local_cabinet.py" --drive-root "%DRIVE%\\"
if errorlevel 1 (
    echo [ERROR] Cabinet bootstrap failed. Aborting launch.
    exit /b 1
)

if exist "%DRIVE%\.aa\device_id.txt" (
    set /p RESOLVED_DEVICE_ID=<"%DRIVE%\.aa\device_id.txt"
    set "AA_DEVICE_ID=!RESOLVED_DEVICE_ID!"
    echo [OK] Runtime device id: !AA_DEVICE_ID!
) else (
    echo [ERROR] Missing %DRIVE%\.aa\device_id.txt after bootstrap.
    exit /b 1
)


echo [INFO] Verifying shipped frontend dist...
if not exist "%DIST_INDEX%" (
    echo [ERROR] frontend\dist\index.html is missing.
    echo         This build is serve-only. Run scripts\prepare_golden_image.bat before cloning or booting.
    exit /b 1
)
echo [OK] Found frontend dist at %DIST_INDEX%
echo.

rem --- Controller Asset Provisioning ---
rem Sync controller images from public/ into dist/ so the serve-only
rem gateway can serve them at /assets/controllers/*
set "CTRL_SRC=%REPOROOT%frontend\public\assets\controllers"
set "CTRL_DST=%REPOROOT%frontend\dist\assets\controllers"
if exist "%CTRL_SRC%\*.png" (
    if not exist "%CTRL_DST%" mkdir "%CTRL_DST%"
    echo [INFO] Provisioning controller assets into dist...
    xcopy "%CTRL_SRC%\*.png" "%CTRL_DST%\" /Y /Q >nul 2>&1
    echo [OK] Controller images synced to dist.
) else (
    echo [WARN] No controller PNGs found in %CTRL_SRC% - Console Wizard will use text-only fallback.
)
echo.

echo [INFO] Starting FastAPI backend on 127.0.0.1:8000...
start "AA-Backend" /min %ComSpec% /c call "%REPOROOT%scripts\run-backend.bat"

echo [INFO] Waiting 8 seconds for backend initialization...
timeout /t 8 >nul
echo [INFO] Backend startup window elapsed. Continuing to gateway startup.

echo [INFO] Starting Gateway server on 127.0.0.1:8787...
start "AA-Gateway" /b %ComSpec% /c call "%REPOROOT%scripts\run-gateway.bat"

echo [INFO] Waiting 6 seconds for gateway initialization...
timeout /t 6 >nul
echo [INFO] Gateway startup window elapsed. Opening UI.

if /I "%AA_MARQUEE_ENABLED%"=="0" (
    echo [INFO] AA_MARQUEE_ENABLED=0 - skipping marquee display launch.
) else (
    echo [INFO] Checking marquee display process...
    powershell -Command "$running = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'pythonw?\.exe' -and $_.CommandLine -match 'scripts\\marquee_display\.py' }; if ($running) { exit 0 } else { exit 1 }" >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        echo [INFO] Marquee display already running - skipping second launch.
    ) else (
        echo [INFO] Waiting 2 seconds before launching marquee display...
        timeout /t 2 >nul
        echo [INFO] Launching marquee display...
        start "Marquee Display" "%PYTHONW_EXE%" "%REPOROOT%scripts\marquee_display.py"
    )
)

echo [INFO] Opening Arcade Assistant UI...
start "" "http://127.0.0.1:8787/assistants"

echo.
echo ============================================================
echo  Arcade Assistant is running!
echo ============================================================
echo.
echo   Backend:  http://127.0.0.1:8000/
echo   Gateway:  http://127.0.0.1:8787/
echo   Overlay:  Dewey Electron overlay is launched separately
echo.
echo   Logs:
echo     - %LOGDIR%\backend.log
echo     - %LOGDIR%\gateway.log
echo.
echo   To stop: run stop-aa.bat
echo ============================================================
exit /b 0
