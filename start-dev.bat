@echo off
REM Dev shortcut now delegates to start-gui.bat with DEV mode
cd /d "%~dp0"
call ".\start-gui.bat" dev
