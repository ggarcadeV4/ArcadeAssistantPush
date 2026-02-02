@echo off
REM ========================================
REM Simple Build Script - No Visual Studio Required
REM Uses .NET Framework C# Compiler directly
REM ========================================

setlocal enabledelayedexpansion

echo ========================================
echo Simple C# Compiler Build
echo ========================================
echo.

REM Configuration
set LAUNCHBOX_PATH=A:\LaunchBox
set OUTPUT_NAME=ArcadeAssistantPlugin.dll
set PLUGIN_DIR=%LAUNCHBOX_PATH%\Plugins\ArcadeAssistant

REM Check LaunchBox
if not exist "%LAUNCHBOX_PATH%\Core\Unbroken.LaunchBox.Plugins.dll" (
    echo ERROR: LaunchBox SDK not found at %LAUNCHBOX_PATH%\Core\
    echo Please ensure LaunchBox is installed at A:\LaunchBox
    goto :error
)

REM Find C# Compiler (csc.exe)
set CSC_PATH=
set ROSLYN_PATH=%ProgramFiles(x86)%\Microsoft Visual Studio\2019\BuildTools\MSBuild\Current\Bin\Roslyn\csc.exe
set FRAMEWORK_PATH=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
set FRAMEWORK32_PATH=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe

if exist "%ROSLYN_PATH%" (
    set CSC_PATH=%ROSLYN_PATH%
) else if exist "%FRAMEWORK_PATH%" (
    set CSC_PATH=%FRAMEWORK_PATH%
) else if exist "%FRAMEWORK32_PATH%" (
    set CSC_PATH=%FRAMEWORK32_PATH%
) else (
    echo ERROR: C# Compiler not found!
    echo.
    echo .NET Framework 4.8 must be installed.
    echo Download from: https://dotnet.microsoft.com/download/dotnet-framework/net48
    goto :error
)

echo Found C# Compiler: %CSC_PATH%
echo.

REM Create bin directory
if not exist "bin" mkdir "bin"

REM Compile the plugin
echo Compiling plugin...
echo.

"%CSC_PATH%" /nologo ^
    /target:library ^
    /out:bin\%OUTPUT_NAME% ^
    /reference:"%LAUNCHBOX_PATH%\Core\Unbroken.LaunchBox.Plugins.dll" ^
    /reference:System.dll ^
    /reference:System.Core.dll ^
    /reference:System.Web.Extensions.dll ^
    /reference:System.Windows.Forms.dll ^
    /reference:System.Xml.dll ^
    /reference:System.Data.dll ^
    /doc:bin\ArcadeAssistantPlugin.xml ^
    /optimize+ ^
    ArcadeAssistantPlugin.cs LaunchServer.cs Properties\AssemblyInfo.cs

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Compilation failed!
    goto :error
)

echo.
echo Compilation successful!
echo.

REM Deploy to LaunchBox
echo Deploying to LaunchBox...

if not exist "%PLUGIN_DIR%" (
    echo Creating plugin directory...
    mkdir "%PLUGIN_DIR%"
)

copy /Y "bin\%OUTPUT_NAME%" "%PLUGIN_DIR%\" >nul 2>&1
if exist "bin\ArcadeAssistantPlugin.xml" (
    copy /Y "bin\ArcadeAssistantPlugin.xml" "%PLUGIN_DIR%\" >nul 2>&1
)

if exist "%PLUGIN_DIR%\%OUTPUT_NAME%" (
    echo.
    echo ========================================
    echo BUILD SUCCESSFUL!
    echo ========================================
    echo.
    echo Plugin deployed to:
    echo   %PLUGIN_DIR%
    echo.
    echo Start LaunchBox to activate the plugin.
    echo HTTP API will be available at:
    echo   http://127.0.0.1:31337/
    echo.
) else (
    echo ERROR: Failed to deploy plugin!
    goto :error
)

goto :end

:error
echo.
echo Build failed! Please check the errors above.
pause
exit /b 1

:end
pause
exit /b 0