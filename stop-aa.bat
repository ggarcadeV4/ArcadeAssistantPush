@echo off
setlocal EnableDelayedExpansion

rem ============================================================================
rem  Arcade Assistant - Stop Script (Golden Drive)
rem  Safely kills backend (port 8000) and gateway (port 8787) processes
rem  - Dedupes PIDs (IPv4 + IPv6 report the same PID twice)
rem  - Only kills python.exe or node.exe; warns on unknown processes
rem  - Uses /T to kill child processes
rem ============================================================================

echo ============================================================
echo  Arcade Assistant - Stopping...
echo ============================================================
echo.

set "KILLED_PIDS="
set KILLED_COUNT=0

rem ----------------------------------------------------------------------------
rem  Kill process on port 8000 (Backend - expect python.exe)
rem ----------------------------------------------------------------------------
echo [INFO] Checking for process on port 8000...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000.*LISTENING"') do (
    set "PID=%%a"
    rem Skip if we already killed this PID
    echo "!KILLED_PIDS!" | findstr /C:":!PID!:" >nul 2>&1
    if errorlevel 1 (
        rem Check what process this is
        set "PROCNAME="
        for /f "tokens=1" %%b in ('tasklist /fi "PID eq !PID!" /nh 2^>nul ^| findstr /i "python.exe"') do set "PROCNAME=%%b"
        if defined PROCNAME (
            echo [INFO] Killing python.exe on port 8000 ^(PID: !PID!^)
            taskkill /F /T /PID !PID! >nul 2>&1
            set "KILLED_PIDS=!KILLED_PIDS!:!PID!:"
            set /a KILLED_COUNT+=1
        ) else (
            rem Check if it's something else
            for /f "tokens=1" %%c in ('tasklist /fi "PID eq !PID!" /nh 2^>nul') do set "PROCNAME=%%c"
            if "!PROCNAME!"=="INFO:" (
                rem Process already gone
                echo [INFO] Port 8000 process already terminated
            ) else (
                echo [WARN] Port 8000 occupied by !PROCNAME! ^(PID: !PID!^) - NOT killing ^(not python.exe^)
            )
        )
    )
)

rem ----------------------------------------------------------------------------
rem  Kill process on port 8787 (Gateway - expect node.exe)
rem ----------------------------------------------------------------------------
echo [INFO] Checking for process on port 8787...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8787.*LISTENING"') do (
    set "PID=%%a"
    rem Skip if we already killed this PID
    echo "!KILLED_PIDS!" | findstr /C:":!PID!:" >nul 2>&1
    if errorlevel 1 (
        rem Check what process this is
        set "PROCNAME="
        for /f "tokens=1" %%b in ('tasklist /fi "PID eq !PID!" /nh 2^>nul ^| findstr /i "node.exe"') do set "PROCNAME=%%b"
        if defined PROCNAME (
            echo [INFO] Killing node.exe on port 8787 ^(PID: !PID!^)
            taskkill /F /T /PID !PID! >nul 2>&1
            set "KILLED_PIDS=!KILLED_PIDS!:!PID!:"
            set /a KILLED_COUNT+=1
        ) else (
            rem Check if it's something else
            for /f "tokens=1" %%c in ('tasklist /fi "PID eq !PID!" /nh 2^>nul') do set "PROCNAME=%%c"
            if "!PROCNAME!"=="INFO:" (
                rem Process already gone
                echo [INFO] Port 8787 process already terminated
            ) else (
                echo [WARN] Port 8787 occupied by !PROCNAME! ^(PID: !PID!^) - NOT killing ^(not node.exe^)
            )
        )
    )
)

rem ----------------------------------------------------------------------------
rem  Kill process on port 9123 (Launcher Agent - expect python.exe/pythonw.exe)
rem ----------------------------------------------------------------------------
echo [INFO] Checking for process on port 9123...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":9123.*LISTENING"') do (
    set "PID=%%a"
    echo "!KILLED_PIDS!" | findstr /C:":!PID!:" >nul 2>&1
    if errorlevel 1 (
        set "PROCNAME="
        for /f "tokens=1" %%b in ('tasklist /fi "PID eq !PID!" /nh 2^>nul ^| findstr /i "python.exe pythonw.exe"') do set "PROCNAME=%%b"
        if defined PROCNAME (
            echo [INFO] Killing !PROCNAME! on port 9123 ^(PID: !PID!^)
            taskkill /F /T /PID !PID! >nul 2>&1
            set "KILLED_PIDS=!KILLED_PIDS!:!PID!:"
            set /a KILLED_COUNT+=1
        ) else (
            for /f "tokens=1" %%c in ('tasklist /fi "PID eq !PID!" /nh 2^>nul') do set "PROCNAME=%%c"
            if "!PROCNAME!"=="INFO:" (
                echo [INFO] Port 9123 process already terminated
            ) else (
                echo [WARN] Port 9123 occupied by !PROCNAME! ^(PID: !PID!^) - NOT killing ^(not python.exe/pythonw.exe^)
            )
        )
    )
)

rem ----------------------------------------------------------------------------
rem  Fallback: Also try to kill by window title (catches cmd.exe wrappers)
rem ----------------------------------------------------------------------------
taskkill /FI "WINDOWTITLE eq AA-Backend" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq AA-Gateway" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq AA-LauncherAgent" /F >nul 2>&1

rem ----------------------------------------------------------------------------
rem  Done
rem ----------------------------------------------------------------------------
echo.
if !KILLED_COUNT! EQU 0 (
    echo [INFO] No Arcade Assistant processes were found running.
) else (
    echo [OK] Stopped !KILLED_COUNT! process^(es^).
)
echo.
echo Arcade Assistant stopped.
echo ============================================================
exit /b 0
