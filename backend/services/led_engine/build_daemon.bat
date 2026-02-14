@echo off
echo Building LED-Wiz Daemon...
cl /EHsc /O2 ledwiz_daemon.cpp /Fe:ledwiz_daemon.exe setupapi.lib hid.lib
if %ERRORLEVEL% EQU 0 (
    echo Build successful: ledwiz_daemon.exe
) else (
    echo Build failed. Make sure you are running in a Visual Studio Developer Command Prompt.
)
