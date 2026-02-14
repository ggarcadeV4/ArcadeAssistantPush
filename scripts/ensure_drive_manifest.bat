@echo off
setlocal

:: Ensure A:\.aa\manifest.json exists by copying from repo's .aa\manifest.json if missing
set "SRC=%~dp0\..\.aa\manifest.json"
set "DST_DIR=A:\.aa"
set "DST=%DST_DIR%\manifest.json"

if not exist "%DST_DIR%" (
  echo Creating %DST_DIR% ...
  mkdir "%DST_DIR%"
)

if exist "%DST%" (
  echo ✅ Manifest already exists at %DST%
) else (
  echo Copying manifest from %SRC% to %DST% ...
  copy "%SRC%" "%DST%" >nul
  if %errorlevel%==0 (
    echo ✅ Manifest copied.
  ) else (
    echo ❌ Failed to copy manifest. Check drive visibility and permissions.
  )
)

endlocal

