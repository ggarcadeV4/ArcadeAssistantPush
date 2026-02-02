@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\provision_and_verify.ps1
exit /b %ERRORLEVEL%

