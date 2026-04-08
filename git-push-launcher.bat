@echo off
echo === Arcade Assistant Git Push ===
echo.
cd /d "W:\Arcade Assistant Master Build\Arcade Assistant Local"

echo [1/4] Checking status...
git status backend/services/launcher.py
echo.

echo [2/4] Staging launcher.py...
git add backend/services/launcher.py
echo.

echo [3/4] Committing...
git commit -m "Fix: Direct-native platforms bypass health check — MAME, Daphne, SINGE2, Nintendo DS always launch direct first"
echo.

echo [4/4] Pushing to master...
git push origin master
echo.

echo === DONE ===
echo.
echo Commit hash:
git rev-parse HEAD
echo.
pause
