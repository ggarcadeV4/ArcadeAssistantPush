@echo off
:: deploy-to-golden.bat
:: Forcefully mirror the dev directory to the production directory on A: drive.
:: Excludes node_modules, .git, and .env files.

set SOURCE="C:\Arcade Assistant Local"
set TARGET="A:\Arcade Assistant Local"

echo Mirroring %SOURCE% to %TARGET%...

robocopy %SOURCE% %TARGET% /MIR /XD node_modules .git /XF .env /R:3 /W:5

if %ERRORLEVEL% GEQ 8 (
    echo ERROR: Robocopy failed with error level %ERRORLEVEL%
    exit /b 1
)

echo Sync complete!
exit /b 0
