@echo off
REM Start the Arcade Launcher Agent in the user's interactive session.
REM This script should be placed in the Windows Startup folder or run
REM alongside (but NOT inside) the backend startup chain.
REM
REM The agent MUST run from a clean process tree — never inside
REM run-backend.bat's redirected stdout chain.

cd /d "A:\Arcade Assistant Local"

REM Use pythonw to hide the console window (runs silently in background)
start "" /B pythonw.exe scripts\arcade_launcher_agent.py

echo Launcher Agent started.
