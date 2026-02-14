@echo off
setlocal

echo ===============================================
echo   Arcade Assistant - Clean For Clone Utility
echo ===============================================
echo.
echo This script will remove cabinet-specific identity
echo and runtime data so the A: drive can be cloned as
echo a golden master.
echo.
echo Targets:
echo   - .aa\device_id.txt
echo   - .aa\manifest.json
echo   - .aa\cabinet_manifest.json
echo   - .aa\logs\*
echo   - state\profile\*
echo   - state\scorekeeper\*
echo   - state\controller\*
echo   - state\marquee_current.json
echo   - state\teknoparrot_*.json
echo   - state\teknoparrot_*.log
echo   - logs\*
echo.
set /p CONFIRM="Type Y to proceed, anything else to cancel: "
if /I not "%CONFIRM%"=="Y" (
  echo [CANCELLED] No files were removed.
  exit /b 1
)

echo.
echo [STEP 1] Removing device identity files...
call :DeleteFile ".aa\device_id.txt"
call :DeleteFile ".aa\manifest.json"
call :DeleteFile ".aa\cabinet_manifest.json"

echo.
echo [STEP 2] Clearing .aa runtime state and logs...
call :CleanFolderContents ".aa\logs"
call :CleanFolderContents ".aa\state"

echo.
echo [STEP 3] Clearing state directories...
call :CleanFolderContents "state\profile"
call :CleanFolderContents "state\scorekeeper"
call :CleanFolderContents "state\controller"
if not exist "state\scorekeeper" mkdir "state\scorekeeper"
if not exist "state\scorekeeper\tournaments" mkdir "state\scorekeeper\tournaments"
if not exist "state\profile" mkdir "state\profile"

echo.
echo [STEP 4] Removing state runtime files...
call :DeleteFile "state\marquee_current.json"
call :DeleteFile "state\teknoparrot_launch.log"
call :DeleteFile "state\teknoparrot_missing_roms.json"
call :DeleteFile "state\teknoparrot_valid_games.json"

echo.
echo [STEP 5] Clearing logs directory...
call :RemoveTree "logs"
mkdir "logs" >nul 2>&1
echo Created fresh logs directory.

echo.
if exist "backups" (
  echo Existing backups directory contents:
  dir /b "backups"
) else (
  echo No backups directory detected.
)
if exist "preflight" (
  echo Existing preflight directory contents:
  dir /b "preflight"
) else (
  echo No preflight directory detected.
)
echo.
set /p CLEAN_OLD="Remove backups and preflight snapshots as well? (Y/N): "
if /I "%CLEAN_OLD%"=="Y" (
  call :RemoveTree "backups"
  call :RemoveTree "preflight"
) else (
  echo Skipping backups/preflight cleanup.
)

echo.
echo [OK] Drive cleaned for cloning. You can now image A:\ as a golden master.
exit /b 0

:DeleteFile
if exist %~1 (
  del /f /q %~1
  echo Deleted %~1
) else (
  echo %~1 not found, skipping.
)
goto :eof

:CleanFolderContents
if exist %~1 (
  del /f /q "%~1\*" >nul 2>&1
  for /d %%d in ("%~1\*") do rd /s /q "%%~d"
  echo Cleared contents of %~1
) else (
  echo %~1 not found, skipping.
)
goto :eof

:RemoveTree
if exist %~1 (
  rd /s /q %~1
  echo Removed %~1
) else (
  echo %~1 not found, skipping.
)
goto :eof
