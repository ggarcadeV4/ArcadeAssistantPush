@echo off
setlocal enabledelayedexpansion
title Arcade Assistant - Startup Manager
color 0A

REM ============================================================
REM  Arcade Assistant - Robust Startup Script
REM  This script ensures the backend always starts correctly
REM  on port 8000 with proper error handling
REM ============================================================

echo.
echo ==========================================
echo   ARCADE ASSISTANT - STARTUP MANAGER
echo ==========================================
echo.

REM Always run from the repo root on Drive A
cd /d "%~dp0"
echo Working directory: %CD%
echo.

REM ============================================================
REM Step 1: Check for existing processes and clean up
REM ============================================================
echo [1/5] Checking for existing processes...

REM Check if port 8000 is already in use
netstat -ano | findstr ":8000" >nul 2>&1
if %errorlevel% equ 0 (
    echo WARNING: Port 8000 is already in use!
    echo.
    choice /C YN /M "Do you want to kill the existing process and restart"
    if !errorlevel! equ 1 (
        echo Killing existing process on port 8000...
        for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000"') do (
            taskkill /F /PID %%a >nul 2>&1
        )
        timeout /t 2 >nul
    ) else (
        echo Exiting. Please manually stop the existing process.
        pause
        exit /b 1
    )
)

REM Check if port 8787 is already in use
netstat -ano | findstr ":8787" >nul 2>&1
if %errorlevel% equ 0 (
    echo WARNING: Port 8787 is already in use!
    echo.
    choice /C YN /M "Do you want to kill the existing process and restart"
    if !errorlevel! equ 1 (
        echo Killing existing process on port 8787...
        for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8787"') do (
            taskkill /F /PID %%a >nul 2>&1
        )
        timeout /t 2 >nul
    ) else (
        echo Exiting. Please manually stop the existing process.
        pause
        exit /b 1
    )
)

echo Ports are clear!
echo.

REM ============================================================
REM Step 2: Verify dependencies
REM ============================================================
echo [2/5] Verifying dependencies...

REM Check Node.js
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Node.js not found!
    echo Please install Node.js from: https://nodejs.org/
    pause
    exit /b 1
)
echo   - Node.js: OK

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found!
    echo Please install Python from: https://python.org/
    pause
    exit /b 1
)
echo   - Python: OK

REM Check .env file
if not exist ".env" (
    echo ERROR: .env file not found!
    echo Please create a .env file in the project root.
    pause
    exit /b 1
)
echo   - .env file: OK
echo.

REM ============================================================
REM Step 3: Verify .env configuration
REM ============================================================
echo [3/5] Verifying .env configuration...

REM Check if FASTAPI_URL is set to port 8000
findstr /C:"FASTAPI_URL=http://127.0.0.1:8000" .env >nul 2>&1
if %errorlevel% neq 0 (
    echo WARNING: FASTAPI_URL in .env is not set to port 8000!
    echo Current .env configuration:
    findstr /C:"FASTAPI_URL" .env
    echo.
    echo Expected: FASTAPI_URL=http://127.0.0.1:8000
    echo.
    choice /C YN /M "Do you want to automatically fix this"
    if !errorlevel! equ 1 (
        echo Updating .env file...
        powershell -Command "(Get-Content .env) -replace 'FASTAPI_URL=http://127.0.0.1:8888', 'FASTAPI_URL=http://127.0.0.1:8000' | Set-Content .env"
        echo .env file updated!
    ) else (
        echo WARNING: Continuing with current configuration. This may cause issues!
    )
)
echo   - FASTAPI_URL: Configured for port 8000
echo.

REM ============================================================
REM Step 4: Start services
REM ============================================================
echo [4/5] Starting services...
echo.

REM Start FastAPI backend on port 8000
echo Starting FastAPI backend on http://localhost:8000 ...
set "POWERSHELL_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%POWERSHELL_EXE%" set POWERSHELL_EXE=powershell
start "FastAPI Backend (Port 8000)" cmd /c "\"%POWERSHELL_EXE%\" -NoProfile -ExecutionPolicy Bypass -File \"%~dp0start_backend.ps1\" -Port 8000"

REM Wait for backend to start
echo Waiting for backend to initialize...
timeout /t 3 >nul

REM Verify backend is running
echo Verifying backend is running...
set BACKEND_READY=0
for /L %%i in (1,1,10) do (
    curl -s http://localhost:8000/health >nul 2>&1
    if !errorlevel! equ 0 (
        set BACKEND_READY=1
        goto backend_ready
    )
    timeout /t 1 >nul
)

:backend_ready
if !BACKEND_READY! equ 0 (
    echo ERROR: Backend failed to start!
    echo Please check the FastAPI Backend window for errors.
    pause
    exit /b 1
)
echo   - Backend: RUNNING on port 8000
echo.

REM Start Gateway on port 8787
echo Starting Gateway on http://localhost:8787 ...
start "Gateway Server (Port 8787)" cmd /k "cd gateway && node server.js"

REM Wait for gateway to start
echo Waiting for gateway to initialize...
timeout /t 3 >nul

REM Verify gateway is running
echo Verifying gateway is running...
set GATEWAY_READY=0
for /L %%i in (1,1,10) do (
    curl -s http://localhost:8787/api/health >nul 2>&1
    if !errorlevel! equ 0 (
        set GATEWAY_READY=1
        goto gateway_ready
    )
    timeout /t 1 >nul
)

:gateway_ready
if !GATEWAY_READY! equ 0 (
    echo ERROR: Gateway failed to start!
    echo Please check the Gateway Server window for errors.
    pause
    exit /b 1
)
echo   - Gateway: RUNNING on port 8787
echo.

REM ============================================================
REM Step 5: Open browser
REM ============================================================
echo [5/5] Opening browser...
echo.

timeout /t 2 >nul
start "" "http://localhost:8787/"

echo.
echo ==========================================
echo   ARCADE ASSISTANT IS NOW RUNNING!
echo ==========================================
echo.
echo   Backend API: http://localhost:8000
echo   Gateway:     http://localhost:8787
echo   Frontend:    http://localhost:8787/
echo.
echo   Two terminal windows are now open:
echo   - FastAPI Backend (Port 8000)
echo   - Gateway Server (Port 8787)
echo.
echo   To stop the services, close those windows
echo   or press Ctrl+C in each window.
echo.
echo ==========================================
echo.
echo Press any key to close this launcher window...
pause >nul
exit /b 0
