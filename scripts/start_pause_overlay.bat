@echo off
REM ============================================
REM Start Arcade Assistant Pause Overlay Service
REM ============================================
REM This starts the global hotkey listener that enables
REM the pause menu overlay from any application.
REM
REM Add this to Windows startup or run manually.
REM
REM Hotkey: F1 (configurable in aa_pause_overlay.ahk)
REM ============================================

echo Starting Arcade Assistant Pause Overlay Service...

REM Find AutoHotkey
set "AHK_PATH="

REM Check common locations
if exist "A:\Tools\AutoHotkey\AutoHotkey.exe" set "AHK_PATH=A:\Tools\AutoHotkey\AutoHotkey.exe"
if exist "A:\Tools\AutoHotkey\AutoHotkeyU64.exe" set "AHK_PATH=A:\Tools\AutoHotkey\AutoHotkeyU64.exe"
if exist "C:\Program Files\AutoHotkey\AutoHotkey.exe" set "AHK_PATH=C:\Program Files\AutoHotkey\AutoHotkey.exe"
if exist "C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe" set "AHK_PATH=C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe"

REM Check if found
if not defined AHK_PATH (
    echo [ERROR] AutoHotkey not found. Please install AutoHotkey.
    echo Download from: https://www.autohotkey.com/
    pause
    exit /b 1
)

echo Using: %AHK_PATH%
echo.
echo Pause Overlay is now active!
echo Press F1 at any time to open the pause menu.
echo.

REM Run the AHK script (stays running in background)
start "" "%AHK_PATH%" "%~dp0aa_pause_overlay.ahk"

echo Pause overlay service started.
