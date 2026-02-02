@echo off
REM ========================================
REM Arcade Assistant LaunchBox Plugin Build Script
REM ========================================

setlocal enabledelayedexpansion

REM Configuration
set PROJECT_NAME=ArcadeAssistantPlugin
set PROJECT_FILE=ArcadeAssistantPlugin.csproj
set LAUNCHBOX_PATH=A:\LaunchBox
set PLUGIN_DIR=%LAUNCHBOX_PATH%\Plugins\ArcadeAssistant
set BUILD_CONFIG=Release

REM Colors for output
set RED=[91m
set GREEN=[92m
set YELLOW=[93m
set CYAN=[96m
set RESET=[0m

echo %CYAN%========================================%RESET%
echo %CYAN%Arcade Assistant LaunchBox Plugin Builder%RESET%
echo %CYAN%========================================%RESET%
echo.

REM Check if LaunchBox directory exists
if not exist "%LAUNCHBOX_PATH%" (
    echo %RED%ERROR: LaunchBox not found at %LAUNCHBOX_PATH%%RESET%
    echo Please update LAUNCHBOX_PATH in this script.
    goto :error
)

REM Check if plugin SDK exists
if not exist "%LAUNCHBOX_PATH%\Core\Unbroken.LaunchBox.Plugins.dll" (
    echo %RED%ERROR: LaunchBox SDK not found at %LAUNCHBOX_PATH%\Core\%RESET%
    echo Please ensure LaunchBox is properly installed.
    goto :error
)

REM Find MSBuild
echo %YELLOW%Locating MSBuild...%RESET%

REM Try Visual Studio 2022 first
set MSBUILD_PATH=
for /f "delims=" %%i in ('"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -requires Microsoft.Component.MSBuild -property installationPath 2^>nul') do (
    set MSBUILD_PATH=%%i\MSBuild\Current\Bin\MSBuild.exe
)

REM Try Visual Studio 2019
if not exist "!MSBUILD_PATH!" (
    for /f "delims=" %%i in ('"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -version "[16.0,17.0)" -requires Microsoft.Component.MSBuild -property installationPath 2^>nul') do (
        set MSBUILD_PATH=%%i\MSBuild\Current\Bin\MSBuild.exe
    )
)

REM Try .NET Framework MSBuild
if not exist "!MSBUILD_PATH!" (
    if exist "%ProgramFiles(x86)%\Microsoft Visual Studio\2019\BuildTools\MSBuild\Current\Bin\MSBuild.exe" (
        set MSBUILD_PATH=%ProgramFiles(x86)%\Microsoft Visual Studio\2019\BuildTools\MSBuild\Current\Bin\MSBuild.exe
    ) else if exist "%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\MSBuild.exe" (
        set MSBUILD_PATH=%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\MSBuild.exe
    ) else if exist "%ProgramFiles(x86)%\MSBuild\14.0\Bin\MSBuild.exe" (
        set MSBUILD_PATH=%ProgramFiles(x86)%\MSBuild\14.0\Bin\MSBuild.exe
    ) else if exist "%ProgramFiles%\MSBuild\14.0\Bin\MSBuild.exe" (
        set MSBUILD_PATH=%ProgramFiles%\MSBuild\14.0\Bin\MSBuild.exe
    )
)

if not exist "!MSBUILD_PATH!" (
    echo %RED%ERROR: MSBuild not found!%RESET%
    echo.
    echo Please install one of the following:
    echo   - Visual Studio 2019/2022 with .NET desktop development workload
    echo   - Build Tools for Visual Studio
    echo   - .NET Framework SDK
    echo.
    echo You can also compile using the .NET Framework directly:
    echo   csc /target:library /reference:"%LAUNCHBOX_PATH%\Core\Unbroken.LaunchBox.Plugins.dll" /out:%PROJECT_NAME%.dll *.cs Properties\AssemblyInfo.cs
    goto :error
)

echo %GREEN%Found MSBuild at: !MSBUILD_PATH!%RESET%
echo.

REM Clean previous build
echo %YELLOW%Cleaning previous build...%RESET%
if exist "bin" rd /s /q "bin" 2>nul
if exist "obj" rd /s /q "obj" 2>nul

REM Build the project
echo %YELLOW%Building %PROJECT_NAME%...%RESET%
echo.

"!MSBUILD_PATH!" "%PROJECT_FILE%" /p:Configuration=%BUILD_CONFIG% /p:Platform="Any CPU" /v:minimal /nologo

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo %RED%ERROR: Build failed!%RESET%
    goto :error
)

echo.
echo %GREEN%Build successful!%RESET%
echo.

REM Deploy to LaunchBox
echo %YELLOW%Deploying to LaunchBox...%RESET%

if not exist "%PLUGIN_DIR%" (
    echo Creating plugin directory...
    mkdir "%PLUGIN_DIR%"
)

REM Copy built files
echo Copying plugin files...
copy /Y "bin\%BUILD_CONFIG%\%PROJECT_NAME%.dll" "%PLUGIN_DIR%\" >nul 2>&1
if exist "bin\%BUILD_CONFIG%\%PROJECT_NAME%.pdb" (
    copy /Y "bin\%BUILD_CONFIG%\%PROJECT_NAME%.pdb" "%PLUGIN_DIR%\" >nul 2>&1
)
if exist "bin\%BUILD_CONFIG%\%PROJECT_NAME%.xml" (
    copy /Y "bin\%BUILD_CONFIG%\%PROJECT_NAME%.xml" "%PLUGIN_DIR%\" >nul 2>&1
)

REM Verify deployment
if exist "%PLUGIN_DIR%\%PROJECT_NAME%.dll" (
    echo %GREEN%Plugin deployed successfully to:%RESET%
    echo   %PLUGIN_DIR%
    echo.
    echo %CYAN%The plugin will be loaded when LaunchBox starts.%RESET%
    echo %CYAN%HTTP API will be available at: http://127.0.0.1:31337/%RESET%
    echo.
    echo %YELLOW%Available endpoints:%RESET%
    echo   GET  /health  - Check server status
    echo   POST /launch  - Launch a game by ID
    echo   GET  /status  - Get detailed server status
    echo   GET  /games   - List sample games (for testing)
    echo.
) else (
    echo %RED%ERROR: Failed to deploy plugin!%RESET%
    goto :error
)

goto :end

:error
echo.
echo %RED%Build failed! Please check the errors above.%RESET%
exit /b 1

:end
echo %GREEN%Build completed successfully!%RESET%
echo.
pause
exit /b 0