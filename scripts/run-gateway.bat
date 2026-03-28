@echo off
cd /d "%~dp0..\gateway"

if not defined AA_DRIVE_ROOT (
    set "AA_DRIVE_ROOT=%~d0\"
)
if not defined FASTAPI_URL (
    set "FASTAPI_URL=http://127.0.0.1:8000"
)

node server.js
