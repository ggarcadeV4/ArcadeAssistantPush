@echo off
setlocal enabledelayedexpansion

REM Mode selection: default prod, optional "dev" argument
set MODE=prod
if /I "%~1"=="dev" set MODE=dev

title Arcade Assistant - GUI Launcher
color 0A

:: Change to the batch file's directory (project root)
cd /d "%~dp0"

:: Guard against WSL/Linux environments (A:\ path mismatch)
if defined WSL_DISTRO_NAME (
    echo ERROR: Detected WSL environment. Use Windows PowerShell/CMD for A:\ paths.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   dYZr ARCADE ASSISTANT - GUI LAUNCHER
echo ==========================================
echo.
echo ------------------------------------------
echo   ENVIRONMENT
echo ------------------------------------------
for /f "delims=" %%i in ('where node 2^>nul') do @echo   Node: %%i
for /f "delims=" %%i in ('node --version 2^>nul') do @echo     Version: %%i
set PYTHON_EXE_FOR_BANNER=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXE_FOR_BANNER=.venv\Scripts\python.exe
)
for /f "delims=" %%i in ('where !PYTHON_EXE_FOR_BANNER! 2^>nul') do @echo   Python: %%i
for /f "delims=" %%i in ('!PYTHON_EXE_FOR_BANNER! --version 2^>nul') do @echo     Version: %%i
echo ------------------------------------------
echo.
echo Selected mode: %MODE%
echo ==========================================
echo.
echo Current directory: %CD%
echo.

:: Ensure logs directory exists for startup diagnostics
if not exist "logs" mkdir logs
set LOG_DIR=%~dp0logs
set BACKEND_START_LOG=%LOG_DIR%\backend_start.log
set BACKEND_START_ERR=%LOG_DIR%\backend_start.err
set GATEWAY_START_LOG=%LOG_DIR%\gateway_start.log
set GATEWAY_START_ERR=%LOG_DIR%\gateway_start.err

:: Resolve PowerShell executable (more reliable than PATH lookup)
set POWERSHELL_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe
if not exist "%POWERSHELL_EXE%" (
    set POWERSHELL_EXE=powershell
)

:: Check if Node.js is installed
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ????O Node.js not found! Please install Node.js first.
    echo    Download from: https://nodejs.org/
    pause
    exit /b 1
)

:: Prefer venv python if available
set PYTHON_EXE=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXE=.venv\Scripts\python.exe
)

:: Check if Python is installed
%PYTHON_EXE% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ????O Python not found! Please install Python first.
    echo    Download from: https://python.org/
    pause
    exit /b 1
)

echo ???o. Node.js and Python detected
echo.

:: Check if we're in the right directory
if not exist "package.json" (
    echo ????O package.json not found in current directory!
    echo    Make sure you're running this from the project root.
    echo    Current directory: %CD%
    pause
    exit /b 1
)

:: Install dependencies if needed
if not exist "node_modules" (
    echo dY"??? Installing dependencies...
    npm run install:all
    if %errorlevel% neq 0 (
        echo ????O Failed to install dependencies
        pause
        exit /b 1
    )
)

if /I "%MODE%"=="dev" goto run_dev_mode

:: Check if frontend is built
if not exist "frontend\dist" (
    echo dY"" Building frontend...
    npm run build:frontend
    if %errorlevel% neq 0 (
        echo ????O Failed to build frontend
        pause
        exit /b 1
    )
)

echo.
echo dYs? Starting Arcade Assistant...
echo.
echo    Gateway: http://localhost:8787
echo    Backend API: http://localhost:8000
echo.
echo dY'??? Press Ctrl+C to stop all services
echo.

:: Start all services (gateway and backend only - frontend is served from dist)
start "FastAPI Backend" cmd /c "\"%POWERSHELL_EXE%\" -NoProfile -ExecutionPolicy Bypass -File \"%~dp0start_backend.ps1\" 1> \"%BACKEND_START_LOG%\" 2> \"%BACKEND_START_ERR%\""
timeout /t 2 >nul
start "Gateway Server" cmd /c "cd /d \"%~dp0gateway\" && node server.js 1> \"%GATEWAY_START_LOG%\" 2> \"%GATEWAY_START_ERR%\""

echo.
echo dYZ_ All services starting...
echo    - Backend API: http://localhost:8000
echo    - Gateway: http://localhost:8787 (serves built frontend)
echo.
echo dY'??? Two terminal windows will open
echo dY'??? Waiting for backend + gateway health...
echo.

:: Wait for services to initialize (health checks)
set WAIT_SECONDS=40
set /a ELAPSED=0
set BACKEND_OK=0
:wait_backend
"%POWERSHELL_EXE%" -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://localhost:8000/health | Out-Null; exit 0 } catch { exit 1 }"
if %errorlevel% neq 0 (
    timeout /t 2 >nul
    set /a ELAPSED+=2
    if %ELAPSED% lss %WAIT_SECONDS% goto wait_backend
    echo WARNING: Backend health check did not pass within %WAIT_SECONDS% seconds.
) else (
    set BACKEND_OK=1
)

set /a ELAPSED=0
set GATEWAY_OK=0
:wait_gateway
"%POWERSHELL_EXE%" -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://localhost:8787/healthz | Out-Null; exit 0 } catch { exit 1 }"
if %errorlevel% neq 0 (
    timeout /t 2 >nul
    set /a ELAPSED+=2
    if %ELAPSED% lss %WAIT_SECONDS% goto wait_gateway
    echo WARNING: Gateway health check did not pass within %WAIT_SECONDS% seconds.
) else (
    set GATEWAY_OK=1
)

if %BACKEND_OK%==0 (
    set HEALTH_STATUS=BACKEND_FAILED
) else if %GATEWAY_OK%==0 (
    set HEALTH_STATUS=GATEWAY_FAILED
) else (
    set HEALTH_STATUS=OK
)

if not "%HEALTH_STATUS%"=="OK" (
    if not exist "logs" mkdir logs
    for /f "delims=" %%i in ('%POWERSHELL_EXE% -NoProfile -Command "Get-Date -Format o"') do set TS=%%i
    echo [%TS%] %HEALTH_STATUS% (backend=%BACKEND_OK% gateway=%GATEWAY_OK%)>> logs\startup_health.log
    "%POWERSHELL_EXE%" -NoProfile -Command "if (Test-Path '%BACKEND_START_ERR%') { '--- backend_start.err (tail) ---' | Out-File -FilePath 'logs\\startup_health.log' -Append -Encoding ascii; Get-Content '%BACKEND_START_ERR%' -Tail 200 | Out-File -FilePath 'logs\\startup_health.log' -Append -Encoding ascii }"
    "%POWERSHELL_EXE%" -NoProfile -Command "if (Test-Path '%BACKEND_START_LOG%') { '--- backend_start.log (tail) ---' | Out-File -FilePath 'logs\\startup_health.log' -Append -Encoding ascii; Get-Content '%BACKEND_START_LOG%' -Tail 200 | Out-File -FilePath 'logs\\startup_health.log' -Append -Encoding ascii }"
    "%POWERSHELL_EXE%" -NoProfile -Command "if (Test-Path 'backend.err') { '--- backend.err (tail) ---' | Out-File -FilePath 'logs\\startup_health.log' -Append -Encoding ascii; Get-Content 'backend.err' -Tail 200 | Out-File -FilePath 'logs\\startup_health.log' -Append -Encoding ascii }"
    "%POWERSHELL_EXE%" -NoProfile -Command "if (Test-Path 'backend.log') { '--- backend.log (tail) ---' | Out-File -FilePath 'logs\\startup_health.log' -Append -Encoding ascii; Get-Content 'backend.log' -Tail 200 | Out-File -FilePath 'logs\\startup_health.log' -Append -Encoding ascii }"
    "%POWERSHELL_EXE%" -NoProfile -Command "if (Test-Path '%GATEWAY_START_LOG%') { '--- gateway_start.log (tail) ---' | Out-File -FilePath 'logs\\startup_health.log' -Append -Encoding ascii; Get-Content '%GATEWAY_START_LOG%' -Tail 200 | Out-File -FilePath 'logs\\startup_health.log' -Append -Encoding ascii }"
    "%POWERSHELL_EXE%" -NoProfile -Command "if (Test-Path '%GATEWAY_START_ERR%') { '--- gateway_start.err (tail) ---' | Out-File -FilePath 'logs\\startup_health.log' -Append -Encoding ascii; Get-Content '%GATEWAY_START_ERR%' -Tail 200 | Out-File -FilePath 'logs\\startup_health.log' -Append -Encoding ascii }"
    "%POWERSHELL_EXE%" -NoProfile -Command "if (Test-Path 'gateway.log') { '--- gateway.log (tail) ---' | Out-File -FilePath 'logs\\startup_health.log' -Append -Encoding ascii; Get-Content 'gateway.log' -Tail 200 | Out-File -FilePath 'logs\\startup_health.log' -Append -Encoding ascii }"
    "%POWERSHELL_EXE%" -NoProfile -Command "if (Test-Path 'gateway.err') { '--- gateway.err (tail) ---' | Out-File -FilePath 'logs\\startup_health.log' -Append -Encoding ascii; Get-Content 'gateway.err' -Tail 200 | Out-File -FilePath 'logs\\startup_health.log' -Append -Encoding ascii }"
    "%POWERSHELL_EXE%" -NoProfile -Command "[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');[System.Windows.Forms.MessageBox]::Show('Arcade Assistant startup health check failed: %HEALTH_STATUS%`nSee logs\\startup_health.log for details.','Arcade Assistant','OK','Warning')" >nul 2>&1
)

:: Open default browser to Arcade Assistant hub (all panels)
start http://localhost:8787/

echo.
echo ???o. Browser opened to Arcade Assistant hub
echo    URL: http://localhost:8787/
echo.
echo Press any key to exit (this will NOT stop the services)
pause >nul

:: If we get here, something went wrong
echo.
echo ???s??????,?  Services stopped unexpectedly
pause
goto :eof

:run_dev_mode
echo.
echo ==========================================
echo   dYs? Starting Arcade Assistant (DEV)
echo ==========================================
echo.
echo This will launch gateway, FastAPI, and the Vite dev server with hot reload.
echo Close the npm windows or press Ctrl+C to stop.
echo.
npm run dev
goto :eof

