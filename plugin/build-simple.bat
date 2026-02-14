@echo off
setlocal
cd /d "%~dp0"

echo ==============================================
echo  Arcade Assistant Plugin - Simple Build
echo ==============================================

:: Prefer MSBuild if available, else dotnet build
where msbuild >nul 2>&1
if %errorlevel%==0 (
  echo Using MSBuild...
  msbuild ArcadeAssistantPlugin.csproj /p:Configuration=Release
) else (
  where dotnet >nul 2>&1
  if %errorlevel%==0 (
    echo Using dotnet build...
    dotnet build ArcadeAssistantPlugin.csproj -c Release
  ) else (
    echo ❌ Neither MSBuild nor dotnet CLI found. Install Visual Studio 2022 or .NET SDK.
    pause
    exit /b 1
  )
)

if not exist "bin\Release\ArcadeAssistantPlugin.dll" (
  echo ❌ Build output not found: bin\Release\ArcadeAssistantPlugin.dll
  pause
  exit /b 1
)

set "LB_PLUGINS=A:\LaunchBox\Plugins\ArcadeAssistant"
if not exist "%LB_PLUGINS%" (
  echo Creating plugin folder: %LB_PLUGINS%
  mkdir "%LB_PLUGINS%"
)

echo Copying DLL to LaunchBox plugins...
copy /Y "bin\Release\ArcadeAssistantPlugin.dll" "%LB_PLUGINS%\ArcadeAssistantPlugin.dll" >nul
if %errorlevel%==0 (
  echo ✅ Deployed to %LB_PLUGINS%
) else (
  echo ❌ Failed to copy DLL. Check A: drive and permissions.
)

echo Done.
endlocal

