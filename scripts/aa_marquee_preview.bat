@echo off
REM ============================================================================
REM Arcade Assistant - Marquee Preview Hook
REM ============================================================================
REM Call this script when a game is highlighted/scrolled to in Pegasus
REM Usage: aa_marquee_preview.bat "Game Title" "Platform" [mode]
REM   mode: "image" (default, fast) or "video" (play video then image)
REM
REM Examples:
REM   aa_marquee_preview.bat "Pac-Man" "Arcade MAME"           <- scroll preview
REM   aa_marquee_preview.bat "Pac-Man" "Arcade MAME" "video"   <- game selected
REM ============================================================================

setlocal enabledelayedexpansion

set "TITLE=%~1"
set "PLATFORM=%~2"
set "MODE=%~3"

if "%MODE%"=="" set "MODE=image"

REM Call the backend API to update marquee preview
curl -s -X POST "http://localhost:8787/api/local/marquee/preview" ^
  -H "Content-Type: application/json" ^
  -H "x-panel: pegasus" ^
  -d "{\"title\": \"%TITLE%\", \"platform\": \"%PLATFORM%\", \"mode\": \"%MODE%\"}" >nul 2>&1

exit /b 0
