@echo off
:: deploy-to-golden.bat
:: Mirror the dev directory to the production directory on A: drive.
:: Excludes: node_modules, .git, .env, .venv, __pycache__, .gemini

set SOURCE="C:\Users\Dad's PC\Desktop\AI-Hub"
set TARGET="A:\Arcade Assistant Local"

echo ============================================================
echo  Golden Drive Deployment
echo ============================================================
echo.
echo  Source: %SOURCE%
echo  Target: %TARGET%
echo.

if not exist "A:\" (
    echo [ERROR] A: drive not detected! Is the Golden Drive connected?
    exit /b 1
)

echo [INFO] Starting robocopy mirror...
robocopy %SOURCE% %TARGET% /MIR /XD node_modules .git .venv __pycache__ .gemini /XF .env .env.local .env.production /R:3 /W:5 /NP

if %ERRORLEVEL% GEQ 8 (
    echo [ERROR] Robocopy failed with error level %ERRORLEVEL%
    exit /b 1
)

echo.
echo [INFO] Verifying key files...
if exist %TARGET%\start-aa.bat echo   [OK] start-aa.bat
if exist %TARGET%\backend\routers\led.py echo   [OK] backend/routers/led.py
if exist %TARGET%\frontend\dist\index.html echo   [OK] frontend/dist/index.html
if exist %TARGET%\gateway\server.js echo   [OK] gateway/server.js
echo.
echo [SUCCESS] Golden Drive deployment complete!
exit /b 0

