@echo off
cd /d "W:\Arcade Assistant Master Build\Arcade Assistant Local"
git add README.md ROLLING_LOG.md
git commit -m "docs: add 2026-04-11 daily slice — Campaigns 1-3 infrastructure stabilization"
git push origin master
echo.
echo Done! Documentation checkpoint pushed.
del /q "%~f0"
pause
