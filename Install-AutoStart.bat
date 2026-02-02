@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_autostart.ps1
exit /b %ERRORLEVEL%

