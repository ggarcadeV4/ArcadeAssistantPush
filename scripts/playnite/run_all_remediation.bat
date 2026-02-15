@echo off
setlocal
title Arcade Assistant: Field Deployment Tool

echo ============================================================
echo      ARCADE ASSISTANT: FIELD DEPLOYMENT TOOL (v1.0)
echo ============================================================
echo.

:: 1. Gather Inputs
set /p BACKUP_PATH="Enter Backup Source Path (e.g. D:\Backups\GoldenImage): "
set /p OLD_DRIVE="Enter Original Drive Letter of Backup (e.g. D:\): "

echo.
echo Proceeding with deployment to Drive A: using:
echo Source: %BACKUP_PATH%
echo Original Letter: %OLD_DRIVE%
echo.
pause

:: 2. Sequence Operations
echo [1/2] RESTORING AND FIXING DATABASE...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Restore-ArcadeAssistant.ps1" -BackupSourcePath "%BACKUP_PATH%" -SourceDriveLetter "%OLD_DRIVE%"
if %ERRORLEVEL% NEQ 0 goto FAIL

echo.
echo [2/2] STARTING POST-RESTORE SANITY CHECK...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Sanity-Check.ps1"
if %ERRORLEVEL% NEQ 0 goto FAIL

:: 3. Final Result
echo.
echo ============================================================
echo   DEPLOYMENT SUCCESSFUL: Cabinet is ready for play.
echo ============================================================
pause
exit

:FAIL
echo.
echo xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
echo   DEPLOYMENT FAILED: Check logs in A:\Playnite\playnite.log
echo xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
pause
exit /b 1
