@echo off
REM ============================================
REM TeknoParrot Universal Launcher
REM ============================================
REM Usage: teknoparrot_launch.bat "ProfileName"
REM Example: teknoparrot_launch.bat "StreetFighterIV"
REM
REM This script handles all the setup TeknoParrot needs:
REM - Kills any existing TeknoParrot instances
REM - Launches with the correct profile
REM - Waits for game to close
REM ============================================

setlocal EnableDelayedExpansion

set "PROFILE=%~1"
set "TP_ROOT=A:\Emulators\TeknoParrot Latest"
set "LOGFILE=A:\Arcade Assistant Local\state\teknoparrot_launch.log"

REM Log start
echo [%DATE% %TIME%] Launching profile: %PROFILE% >> "%LOGFILE%"

REM Validate profile argument
if "%PROFILE%"=="" (
    echo ERROR: No profile specified
    echo Usage: teknoparrot_launch.bat "ProfileName"
    echo   [%DATE% %TIME%] ERROR: No profile specified >> "%LOGFILE%"
    exit /b 1
)

REM Check if profile exists
if not exist "%TP_ROOT%\UserProfiles\%PROFILE%.xml" (
    echo ERROR: Profile not found: %PROFILE%.xml
    echo   [%DATE% %TIME%] ERROR: Profile not found: %PROFILE%.xml >> "%LOGFILE%"
    exit /b 1
)

REM Kill any existing TeknoParrot instances
echo Closing existing TeknoParrot instances...
taskkill /F /IM TeknoParrotUi.exe >nul 2>&1
taskkill /F /IM OpenParrotLoader.exe >nul 2>&1
taskkill /F /IM OpenParrotLoader64.exe >nul 2>&1
taskkill /F /IM BudgieLoader.exe >nul 2>&1
timeout /t 2 /nobreak >nul

REM Launch TeknoParrot with profile
echo Launching: %PROFILE%
echo   [%DATE% %TIME%] Executing: TeknoParrotUi.exe --profile=%PROFILE%.xml --startGame >> "%LOGFILE%"

cd /d "%TP_ROOT%"
REM Use --startGame flag (newer TeknoParrot) to auto-launch
start "" "%TP_ROOT%\TeknoParrotUi.exe" --profile=%PROFILE%.xml --startGame

REM Wait for TeknoParrot to start
timeout /t 3 /nobreak >nul

REM Check if TeknoParrot started
tasklist /FI "IMAGENAME eq TeknoParrotUi.exe" 2>NUL | find /I "TeknoParrotUi.exe" >NUL
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: TeknoParrot failed to start
    echo   [%DATE% %TIME%] ERROR: TeknoParrot failed to start >> "%LOGFILE%"
    exit /b 1
)

echo TeknoParrot started successfully
echo   [%DATE% %TIME%] TeknoParrot started, waiting for game... >> "%LOGFILE%"

REM Wait for TeknoParrot/game to close
:WAIT_LOOP
timeout /t 2 /nobreak >nul
tasklist /FI "IMAGENAME eq TeknoParrotUi.exe" 2>NUL | find /I "TeknoParrotUi.exe" >NUL
if %ERRORLEVEL%==0 goto WAIT_LOOP

echo Game closed
echo   [%DATE% %TIME%] Game closed >> "%LOGFILE%"

endlocal
exit /b 0
