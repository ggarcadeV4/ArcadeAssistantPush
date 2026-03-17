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

echo [INFO] Starting FastAPI backend on 127.0.0.1:8000...
start "AA-Backend" /min cmd /c ""%REPOROOT%scripts\run-backend.bat" > "%LOGDIR%\backend.log" 2>&1"

echo [INFO] Waiting for backend to be ready (port 8000)...
set BACKEND_READY=0
for /L %%i in (1,1,30) do (
    if !BACKEND_READY! EQU 0 (
        powershell -Command "if ((Test-NetConnection -ComputerName 127.0.0.1 -Port 8000 -WarningAction SilentlyContinue).TcpTestSucceeded) { exit 0 } else { exit 1 }" >nul 2>&1
        if !ERRORLEVEL! EQU 0 (
            set BACKEND_READY=1
            echo.
            echo [OK] Backend is listening on port 8000
        ) else (
            <nul set /p "=."
            timeout /t 1 >nul
        )
    )
)
if !BACKEND_READY! EQU 0 (
    echo.
    echo [ERROR] Backend failed to start within 30 seconds!
    echo         Check log: %LOGDIR%\backend.log
    echo.
    echo --- Last 20 lines of backend.log ---
    powershell -Command "Get-Content '%LOGDIR%\backend.log' -Tail 20 -ErrorAction SilentlyContinue"
    exit /b 1
)

echo [INFO] Starting Gateway server on 127.0.0.1:8787...
start "AA-Gateway" /min cmd /c ""%REPOROOT%scripts\run-gateway.bat" > "%LOGDIR%\gateway.log" 2>&1"

echo [INFO] Waiting for gateway to be ready (port 8787)...
set GATEWAY_READY=0
for /L %%i in (1,1,30) do (
    if !GATEWAY_READY! EQU 0 (
        powershell -Command "if ((Test-NetConnection -ComputerName 127.0.0.1 -Port 8787 -WarningAction SilentlyContinue).TcpTestSucceeded) { exit 0 } else { exit 1 }" >nul 2>&1
        if !ERRORLEVEL! EQU 0 (
            set GATEWAY_READY=1
            echo.
            echo [OK] Gateway is listening on port 8787
        ) else (
            <nul set /p "=."
            timeout /t 1 >nul
        )
    )
)
if !GATEWAY_READY! EQU 0 (
    echo.
    echo [ERROR] Gateway failed to start within 30 seconds!
    echo         Check log: %LOGDIR%\gateway.log
    echo.
    echo --- Last 20 lines of gateway.log ---
    powershell -Command "Get-Content '%LOGDIR%\gateway.log' -Tail 20 -ErrorAction SilentlyContinue"
    exit /b 1
)

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
