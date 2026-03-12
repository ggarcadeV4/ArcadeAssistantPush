@echo off
setlocal

cd /d "%~dp0.."

echo ============================================================
echo  Arcade Assistant - Prepare Golden Image
echo ============================================================
echo.

echo [STEP 1] Removing existing frontend dist for a clean build...
if exist "frontend\dist" rd /s /q "frontend\dist"

echo [STEP 2] Building frontend...
call npm run build:frontend
if errorlevel 1 (
  echo [ERROR] Frontend build failed.
  exit /b 1
)

echo [STEP 3] Verifying hashed assets in frontend\dist\index.html...
if not exist "frontend\dist\index.html" (
  echo [ERROR] frontend\dist\index.html missing after build.
  exit /b 1
)

for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "[regex]::Match((Get-Content 'frontend/dist/index.html' -Raw), 'assets/index-([a-f0-9]{8})\.js', 'IgnoreCase').Groups[1].Value"`) do set "SPA_BUILD=%%i"

if "%SPA_BUILD%"=="" (
  echo [ERROR] Could not extract hashed JS bundle from frontend\dist\index.html.
  exit /b 1
)

echo [OK] Golden-image frontend build verified.
echo [INFO] SPA build hash: %SPA_BUILD%
echo.
echo Next steps:
echo   1. Run start-aa.bat for a serve-only smoke test.
echo   2. Run clean_for_clone.bat immediately before imaging the drive.
exit /b 0
