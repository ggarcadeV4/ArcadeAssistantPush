@echo off
REM ============================================
REM Arcade Assistant - Pegasus Launch Bridge
REM ============================================
REM This script is called by Pegasus to launch games.
REM It routes the request through the AA backend.
REM
REM Usage: aa_launch_pegasus.bat "game_file" "platform"

set "GAME_FILE=%~1"
set "PLATFORM=%~2"

echo Pegasus Launch: "%GAME_FILE%" from "%PLATFORM%"

REM Call backend API with game info
curl -s -X POST "http://localhost:8787/api/launchbox/launch-by-title" ^
  -H "Content-Type: application/json" ^
  -H "x-panel: pegasus" ^
  -d "{\"title\": \"%GAME_FILE%\", \"collection\": \"%PLATFORM%\"}"
