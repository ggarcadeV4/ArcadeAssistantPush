@echo off
title Arcade Assistant (WSL backend)
color 0A
cd /d "%~dp0\.."

echo.
echo ==============================================
echo   Arcade Assistant - WSL Backend Quick Start
echo ==============================================
echo Repo: %CD%
echo.
echo Prereqs:
echo  - .env has AA_DRIVE_ROOT=/mnt/a
echo  - A:\.aa\manifest.json exists
echo  - Backend port: 8000
echo.

:: Start backend in a new window via WSL
start "WSL Backend" cmd /c scripts\start_wsl_backend.bat
timeout /t 2 >nul

:: Start gateway (Windows)
start "Gateway" cmd /c "cd gateway && node server.js && pause"
timeout /t 2 >nul

:: Start frontend (Vite)
start "Frontend (Vite)" cmd /c "cd frontend && npm run dev && pause"

echo.
echo Launched:
echo  - Backend (WSL): http://localhost:8000
echo  - Gateway:       http://localhost:8787
echo  - Frontend:      http://localhost:5173
echo.
echo Use Ctrl+C in each window to stop.

