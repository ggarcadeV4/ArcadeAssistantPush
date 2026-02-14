@echo off
echo ===================================================
echo   G&G ARCADE - FLEET MANAGER STARTUP
echo ===================================================

:: 1. Navigate to the correct directory
cd /d "C:\Users\Dad's PC\Desktop\Arcade Network 12-03-2025\fleet_manager"

:: 2. Start Backend (New clean port 8001 just to be safe, but adhering to plan)
echo [1/4] Starting Backend Server on Port 8001...
start "FleetBackend" cmd /k "python -m uvicorn main:app --host 127.0.0.1 --port 8001"

:: 3. Start UI Server (New clean port 8008)
echo [2/4] Starting UI Server on Port 8008...
start "FleetUI" cmd /k "python -m http.server 8008"

:: 4. Wait for servers to spin up
echo [3/4] Waiting 5 seconds for services to initialize...
timeout /t 5 >nul

:: 5. Run Simulation
echo [4/4] Simulating New Device Connection...
python simulate_new_cabinet.py

:: 6. Open Browser
echo Opening Fleet Manager...
start http://localhost:8008/mac_manager.html

echo.
echo ===================================================
echo   SUCCESS!
echo   - Backend: http://localhost:8001
echo   - UI:      http://localhost:8008
echo ===================================================
pause
