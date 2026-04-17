@echo off
echo === Session 04-10-2026: LoRa Complete — Git Push ===
echo.
cd /d "W:\Arcade Assistant Master Build\Arcade Assistant Local"

echo [1/4] Checking status...
git status --short
echo.

echo [2/4] Staging files...
git add README.md
git add ROLLING_LOG.md
git add AA_Session_Briefing_04-10-2026.md
echo.

echo [3/4] Committing...
git commit -m "Session 04-10-2026: LoRa complete — all platforms routing, bezels fixed, CRT shader applied"
echo.

echo [4/4] Pushing to master...
git push origin master
echo.

echo === DONE ===
echo.
echo Final commit hash:
git rev-parse HEAD
echo.
pause
