@echo off
setlocal enabledelayedexpansion
REM ============================================
REM Arcade Assistant - Pegasus Launch Bridge v2.0
REM ============================================
REM FIXED: More robust emulator detection, better error handling
REM
REM This script is called by Pegasus to launch games.
REM It routes the request through the AA backend using the game GUID.
REM
REM CRITICAL: This script MUST block until emulator exits.
REM If it returns early, Pegasus will show the menu immediately.
REM
REM Usage: aa_launch_pegasus_simple.bat "game_file_path" "platform"

set "GAME_PATH=%~1"
set "PLATFORM=%~2"
set "GAME_TITLE=%~n1"
set "GAME_ID="
set "SCRIPT_DIR=%~dp0"
set "LOG_FILE=%SCRIPT_DIR%..\logs\pegasus_launch.log"

REM Ensure log directory exists
if not exist "%SCRIPT_DIR%..\logs" mkdir "%SCRIPT_DIR%..\logs"

REM Extract game GUID from .game placeholder file (line 3: # ID: <guid>)
for /f "tokens=3 delims=: " %%a in ('findstr /b "# ID:" "%GAME_PATH%" 2^>nul') do set "GAME_ID=%%a"

REM Log what we're launching
echo [Pegasus] Launching: "%GAME_TITLE%" (ID: %GAME_ID%) from "%PLATFORM%"
echo [%DATE% %TIME%] Launch: "%GAME_TITLE%" (ID: %GAME_ID%) from "%PLATFORM%" >> "%LOG_FILE%"

REM Check if backend is running first
curl -s -o nul -w "%%{http_code}" http://localhost:8787/health > "%TEMP%\aa_pegasus_health.txt" 2>&1
set /p HEALTH=<"%TEMP%\aa_pegasus_health.txt"
if not "%HEALTH%"=="200" (
    echo [ERROR] Backend not running! Health check returned: %HEALTH%
    echo [%DATE% %TIME%] ERROR: Backend not running >> "%LOG_FILE%"
    REM Show error for 5 seconds then exit
    timeout /t 5 /nobreak >nul
    exit /b 0
)

REM Launch using GUID if available (reliable), otherwise fall back to title match
set "LAUNCH_SUCCESS=0"
if defined GAME_ID (
    REM Direct launch by GUID - most reliable method
    for /f %%i in ('curl -s -X POST "http://localhost:8787/api/launchbox/launch/%GAME_ID%" -H "Content-Type: application/json" -H "x-panel: pegasus" --data-raw "{}" -w "%%{http_code}" -o "%TEMP%\pegasus_response.txt"') do set "HTTP_CODE=%%i"
    type "%TEMP%\pegasus_response.txt" >> "%LOG_FILE%"
    if "!HTTP_CODE!"=="200" set "LAUNCH_SUCCESS=1"
) else (
    REM Fallback: title-based matching
    for /f %%i in ('curl -s -X POST "http://localhost:8787/api/launchbox/launch-by-title" -H "Content-Type: application/json" -H "x-panel: pegasus" --data-raw "{\"title\": \"%GAME_TITLE%\", \"collection\": \"%PLATFORM%\"}" -w "%%{http_code}" -o "%TEMP%\pegasus_response.txt"') do set "HTTP_CODE=%%i"
    type "%TEMP%\pegasus_response.txt" >> "%LOG_FILE%"
    if "!HTTP_CODE!"=="200" set "LAUNCH_SUCCESS=1"
)

REM If launch failed, wait briefly and exit
if "!LAUNCH_SUCCESS!"=="0" (
    echo [%DATE% %TIME%] Launch API failed with HTTP %HTTP_CODE% >> "%LOG_FILE%"
    timeout /t 3 /nobreak >nul
    exit /b 0
)

REM Give emulator time to start (increased from 3 to 5 seconds)
timeout /t 5 /nobreak >nul

REM Track iterations to prevent infinite loop
set "MAX_WAIT=300"
set "WAIT_COUNT=0"

:wait_loop
set /a WAIT_COUNT+=1
if %WAIT_COUNT% GTR %MAX_WAIT% (
    echo [%DATE% %TIME%] Wait loop timeout after %MAX_WAIT% iterations >> "%LOG_FILE%"
    goto done
)

timeout /t 1 /nobreak >nul

REM Check ALL common emulators (comprehensive list)
REM RetroArch variants
tasklist /FI "IMAGENAME eq retroarch.exe" 2>nul | find /i "retroarch.exe" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq retroarch_debug.exe" 2>nul | find /i "retroarch" >nul && goto wait_loop

REM MAME variants
tasklist /FI "IMAGENAME eq mame.exe" 2>nul | find /i "mame.exe" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq mame64.exe" 2>nul | find /i "mame64.exe" >nul && goto wait_loop

REM PlayStation emulators
tasklist /FI "IMAGENAME eq pcsx2-qt.exe" 2>nul | find /i "pcsx2" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq pcsx2.exe" 2>nul | find /i "pcsx2" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq rpcs3.exe" 2>nul | find /i "rpcs3.exe" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq duckstation-qt-x64-ReleaseLTCG.exe" 2>nul | find /i "duckstation" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq duckstation-nogui-x64-ReleaseLTCG.exe" 2>nul | find /i "duckstation" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq ppsspp.exe" 2>nul | find /i "ppsspp.exe" >nul && goto wait_loop

REM Nintendo emulators
tasklist /FI "IMAGENAME eq Dolphin.exe" 2>nul | find /i "Dolphin.exe" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq yuzu.exe" 2>nul | find /i "yuzu.exe" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq Ryujinx.exe" 2>nul | find /i "Ryujinx.exe" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq Cemu.exe" 2>nul | find /i "Cemu.exe" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq Citra.exe" 2>nul | find /i "Citra.exe" >nul && goto wait_loop

REM Sega emulators
tasklist /FI "IMAGENAME eq redream.exe" 2>nul | find /i "redream.exe" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq Supermodel.exe" 2>nul | find /i "Supermodel.exe" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq demul.exe" 2>nul | find /i "demul.exe" >nul && goto wait_loop

REM Arcade emulators
tasklist /FI "IMAGENAME eq TeknoParrotUi.exe" 2>nul | find /i "TeknoParrot" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq GameLoader.exe" 2>nul | find /i "GameLoader" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq JConfig.exe" 2>nul | find /i "JConfig.exe" >nul && goto wait_loop

REM Other emulators
tasklist /FI "IMAGENAME eq VisualBoyAdvance.exe" 2>nul | find /i "VisualBoyAdvance" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq bsnes.exe" 2>nul | find /i "bsnes.exe" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq mednafen.exe" 2>nul | find /i "mednafen.exe" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq Xemu.exe" 2>nul | find /i "Xemu.exe" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq xenia.exe" 2>nul | find /i "xenia.exe" >nul && goto wait_loop

REM AutoHotkey scripts (used by some launchers)
tasklist /FI "IMAGENAME eq AutoHotkeyU32.exe" 2>nul | find /i "AutoHotkey" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq AutoHotkey.exe" 2>nul | find /i "AutoHotkey" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq AutoHotkey32.exe" 2>nul | find /i "AutoHotkey" >nul && goto wait_loop
tasklist /FI "IMAGENAME eq AutoHotkey64.exe" 2>nul | find /i "AutoHotkey" >nul && goto wait_loop

REM Generic fallback
tasklist /FI "IMAGENAME eq EMULATOR.EXE" 2>nul | find /i "EMULATOR.EXE" >nul && goto wait_loop

:done
echo [%DATE% %TIME%] Emulator exited, returning to Pegasus >> "%LOG_FILE%"

REM Clear marquee state and reset runtime to browse mode
curl -s -X POST "http://localhost:8787/api/launchbox/pegasus/exit" -H "x-panel: pegasus" -o nul 2>&1

REM CRITICAL: Always exit with code 0 to prevent Pegasus from closing
endlocal
exit /b 0
