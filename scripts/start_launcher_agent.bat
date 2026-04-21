@echo off
REM Start the Arcade Launcher Agent in the user's interactive session.
REM This script should be placed in the Windows Startup folder or run
REM alongside (but NOT inside) the backend startup chain.
REM
REM The agent MUST run from a clean process tree -- never inside
REM run-backend.bat's redirected stdout chain.

set "ROOT=%~dp0.."
cd /d "%ROOT%"

set "PYTHON_CMD="
for /f "delims=" %%I in ('where pythonw.exe 2^>nul') do (
    set "PYTHON_CMD=%%I"
    goto :launch
)
for /f "delims=" %%I in ('where python.exe 2^>nul') do (
    set "PYTHON_CMD=%%I"
    goto :launch
)
if exist ".venv\Scripts\pythonw.exe" (
    set "PYTHON_CMD=%ROOT%\.venv\Scripts\pythonw.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=%ROOT%\.venv\Scripts\python.exe"
) else (
    set "PYTHON_CMD=pythonw.exe"
)

:launch
start "" /B "%PYTHON_CMD%" scripts\arcade_launcher_agent.py

echo Launcher Agent started.
