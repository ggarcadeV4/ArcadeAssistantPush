@echo off
setlocal

echo ===============================================
echo   Arcade Assistant - Clean For Clone Utility
echo ===============================================
echo.
echo This script removes cabinet-specific identity and runtime data
echo while preserving the files a golden image needs to boot.
echo.
echo Targets:
echo   - .aa\device_id.txt
echo   - .aa\cabinet_manifest.json
echo   - .aa\logs\*
echo   - .aa\state\*
echo   - state\profile\*
echo   - state\scorekeeper\*
echo   - state\controller\*
echo   - state\marquee_current.json
echo   - state\teknoparrot_*.json
echo   - state\teknoparrot_*.log
echo   - logs\*
echo   - .git and developer caches
echo   - __pycache__, *.pyc, frontend node_modules
echo   - cabinet-specific .env labels ^(DEVICE_NAME / DEVICE_SERIAL^)
echo.
echo Preserved intentionally:
echo   - .aa\manifest.json
echo   - frontend\dist ^(golden image ships prebuilt UI^)
echo   - gateway\node_modules

echo.
set /p CONFIRM="Type Y to proceed, anything else to cancel: "
if /I not "%CONFIRM%"=="Y" (
  echo [CANCELLED] No files were removed.
  exit /b 1
)

echo.
echo [STEP 1] Removing cabinet identity files...
call :DeleteFile ".aa\device_id.txt"
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
echo [STEP 5] Resetting cabinet-specific .env labels...
call :SanitizeEnv

echo.
echo [STEP 6] Clearing logs directory...
call :RemoveTree "logs"
mkdir "logs" >nul 2>&1
echo Created fresh logs directory.

echo.
echo [STEP 7] Removing source-control, cache, and dev artifacts...
call :RemoveTree ".git"
call :RemoveTree ".pytest_cache"
call :RemoveTree ".hypothesis"
call :RemoveTree ".mypy_cache"
call :RemoveTree ".ruff_cache"
call :RemoveTree ".uv-cache"
call :RemoveTree ".uvcache"
call :RemoveTree ".venv"
call :RemoveTree "frontend\node_modules"
call :RemoveTree "frontend\coverage"
call :RemoveRecursiveFolders "__pycache__"
call :DeleteRecursiveFiles "*.pyc"
call :DeleteRecursiveFiles "*.pyo"

echo.
echo [STEP 8] Removing temp/debug files...
call :DeleteFile ".tmp_readme_tail.txt"
call :DeleteFile ".tmp_readme_tail500.txt"
call :DeleteRecursiveFiles "npm-debug.log"
call :DeleteRecursiveFiles "yarn-error.log"
call :DeleteRecursiveFiles "pnpm-debug.log"
call :DeleteRecursiveFiles "*.stackdump"
call :DeleteRecursiveFiles "*.tmp"

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
echo [OK] Drive cleaned for cloning. frontend\dist and gateway\node_modules were preserved.
exit /b 0

:SanitizeEnv
if not exist ".env" (
  echo .env not found, skipping.
  goto :eof
)
powershell -NoProfile -Command "$path='.env'; $text=Get-Content $path -Raw; $text=$text -replace '(?m)^DEVICE_NAME=.*$', 'DEVICE_NAME=Arcade Cabinet'; $text=$text -replace '(?m)^DEVICE_SERIAL=.*$', 'DEVICE_SERIAL=UNPROVISIONED'; Set-Content $path $text"
echo Sanitized DEVICE_NAME and DEVICE_SERIAL in .env
goto :eof

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

:RemoveRecursiveFolders
for /d /r %%d in (%~1) do (
  if exist "%%~fd" (
    rd /s /q "%%~fd"
    echo Removed %%~fd
  )
)
goto :eof

:DeleteRecursiveFiles
for /r %%f in (%~1) do (
  if exist "%%~ff" (
    del /f /q "%%~ff"
    echo Deleted %%~ff
  )
)
goto :eof
