@echo off
cd /d "W:\Arcade Assistant Master Build\Arcade Assistant Local"

echo === Step 1: Merging daily slice into README + ROLLING_LOG ===
python insert_daily_slice.py
if errorlevel 1 (
    echo FAILED: insert_daily_slice.py - aborting
    pause
    exit /b 1
)

echo === Step 2: Cleanup temp files ===
del /q ".tmp_insert_log.py" 2>nul
del /q ".tmp_rolling_log_insert.md" 2>nul
del /q ".tmp_readme_head.txt" 2>nul
del /q ".tmp_readme_head_raw.md" 2>nul
del /q "insert_daily_slice.py" 2>nul
del /q "ROLLING_LOG_2026-04-11_INSERT.md" 2>nul
del /q "README_2026-04-11_INSERT.md" 2>nul

echo === Step 3: Git status ===
git status --short

echo === Step 4: Stage + Commit + Push ===
git add .
git commit -m "Stabilize infra: gateway enclosure, identity cleanup, path unification, safety hardening"
git push origin master

echo === Done ===
del /q "checkpoint-2026-04-11.bat" 2>nul
pause
