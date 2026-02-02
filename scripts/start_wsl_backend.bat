@echo off
setlocal enabledelayedexpansion

:: Start FastAPI backend under WSL at port 8000 using the repo's .env
:: This avoids Windows/WSL path mismatches when AA_DRIVE_ROOT=/mnt/a

:: Compute WSL path for the current repo (CWD)
for /f "tokens=2 delims==" %%I in ('wmic OS Get LocalDateTime /value') do set DTS=%%I
set DTS=%DTS:~0,8%_%DTS:~8,6%

:: Convert current directory (e.g., C:\Users\...\Arcade Assistant Local) to /mnt/c/... for WSL
set "WIN_PATH=%CD%"
set "WSL_PATH=%WIN_PATH:\=/mnt/%"
:: Replace drive letter colon "C:/" -> "/mnt/c/"
set "DRV=%WIN_PATH:~0,1%"
set "WSL_PATH=/mnt/%DRV:~0,1%%WIN_PATH:~2%"
set "WSL_PATH=%WSL_PATH:\=/%"

echo Starting FastAPI backend in WSL at: %WSL_PATH%
wsl bash -lc "cd \"%WSL_PATH%\" && uvicorn backend.app:app --reload --port 8000"

endlocal

