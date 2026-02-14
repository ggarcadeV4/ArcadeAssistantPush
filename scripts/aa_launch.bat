@echo off
REM Arcade Assistant Launch Bridge
REM Called by RetroFE with game title and collection as arguments
REM Resolves title to game ID via title_map.json, then launches

setlocal EnableDelayedExpansion

set "GAME_TITLE=%~1"
set "COLLECTION=%~2"
echo RetroFE Launch: "%GAME_TITLE%" from collection "%COLLECTION%"

REM Call backend API with title (backend resolves to game ID)
curl -s -X POST "http://localhost:8787/api/launchbox/launch-by-title" ^
  -H "Content-Type: application/json" ^
  -H "x-panel: retrofe" ^
  -d "{\"title\": \"%GAME_TITLE%\", \"collection\": \"%COLLECTION%\"}"
