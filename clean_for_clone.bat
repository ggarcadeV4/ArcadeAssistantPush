@echo off
setlocal

echo ===============================================
echo   Arcade Assistant - Clean For Clone Utility
echo ===============================================
echo.
echo This script removes cabinet-specific identity and runtime data
echo while preserving the files a golden image needs to boot.
echo.
echo Targets:
echo   - .aa\device_id.txt
echo   - .aa\cabinet_manifest.json
echo   - .aa\logs\*
echo   - .aa\state\*
echo   - state\profile\*
echo   - state\scorekeeper\*
echo   - state\controller\*
echo   - state\marquee_current.json
echo   - state\teknoparrot_*.json
echo   - state\teknoparrot_*.log
echo   - logs\*
echo   - .git and developer caches
echo   - __pycache__, *.pyc, frontend node_modules
echo   - cabinet-specific .env labels ^(DEVICE_NAME / DEVICE_SERIAL^)
echo.
echo Preserved intentionally:
echo   - .aa\manifest.json
echo   - frontend\dist ^(golden image ships prebuilt UI^)
echo   - gateway\node_modules

echo.
set /p CONFIRM="Type Y to proceed, anything else to cancel: "
if /I not "%CONFIRM%"=="Y" (
  echo [CANCELLED] No files were removed.
  exit /b 1
)

echo.
echo [STEP 1] Removing cabinet identity files...
call :DeleteFile ".aa\device_id.txt"
call :DeleteFile ".aa\cabinet_manifest.json"

echo.
echo [STEP 2] Clearing .aa runtime state and logs...
call :CleanFolderContents ".aa\logs"
call :CleanFolderContents ".aa\state"

echo.
echo [STEP 3] Clearing state directories...
call :CleanFolderContents "state\profile"
call :CleanFolderContents "state\scorekeeper"
call :CleanFolderContents "state\controller"
if not exist "state\scorekeeper" mkdir "state\scorekeeper"
if not exist "state\scorekeeper\tournaments" mkdir "state\scorekeeper\tournaments"
if not exist "state\profile" mkdir "state\profile"

echo.
echo [STEP 4] Removing state runtime files...
call :DeleteFile "state\marquee_current.json"
call :DeleteFile "state\teknoparrot_launch.log"
call :DeleteFile "state\teknoparrot_missing_roms.json"
call :DeleteFile "state\teknoparrot_valid_games.json"

echo.
echo [STEP 5] Resetting cabinet-specific .env labels...
call :SanitizeEnv

echo.
echo [STEP 6] Clearing logs directory...
call :RemoveTree "logs"
mkdir "logs" >nul 2>&1
echo Created fresh logs directory.

echo.
echo [STEP 7] Removing source-control, cache, and dev artifacts...
call :RemoveTree ".git"
call :RemoveTree ".pytest_cache"
call :RemoveTree ".hypothesis"
call :RemoveTree ".mypy_cache"
call :RemoveTree ".ruff_cache"
call :RemoveTree ".uv-cache"
call :RemoveTree ".uvcache"
call :RemoveTree ".venv"
call :RemoveTree "frontend\node_modules"
call :RemoveTree "frontend\coverage"
call :RemoveRecursiveFolders "__pycache__"
call :DeleteRecursiveFiles "*.pyc"
call :DeleteRecursiveFiles "*.pyo"

echo.
echo [STEP 8] Removing temp/debug files...
call :DeleteFile ".tmp_readme_tail.txt"
call :DeleteFile ".tmp_readme_tail500.txt"
call :DeleteRecursiveFiles "npm-debug.log"
call :DeleteRecursiveFiles "yarn-error.log"
call :DeleteRecursiveFiles "pnpm-debug.log"
call :DeleteRecursiveFiles "*.stackdump"
call :DeleteRecursiveFiles "*.tmp"

echo.
if exist "backups" (
  echo Existing backups directory contents:
  dir /b "backups"
) else (
  echo No backups directory detected.
)
if exist "preflight" (
  echo Existing preflight directory contents:
  dir /b "preflight"
) else (
  echo No preflight directory detected.
)
echo.
set /p CLEAN_OLD="Remove backups and preflight snapshots as well? (Y/N): "
if /I "%CLEAN_OLD%"=="Y" (
  call :RemoveTree "backups"
  call :RemoveTree "preflight"
) else (
  echo Skipping backups/preflight cleanup.
)

@echo off
REM ============================================================================
REM  SECURITY SCRUB - Step 9 Addition for clean_for_clone.bat
REM  Golden Drive Security Master Plan - Pillar 2, Layer 2
REM  Add this entire block to clean_for_clone.bat, after the existing Step 8.
REM
REM  PURPOSE:
REM    Aggressively remove all AI agent configuration files, dev workflow
REM    documents, architect metadata, and dev tooling directories that expose
REM    internal system design and should never ship on a production cabinet.
REM
REM    This is separate from Step 7 (dev cache cleanup) because these are
REM    CONTENT files - they describe how the system was built, who built it,
REM    and what rules the AI agents operate under. That's threat surface.
REM
REM  NOTE ON AGENT MD FILES:
REM    AGENTS.md, CLAUDE.md, GEMINI.md, GROK.md, OPENAI.md are intentionally
REM    preserved DURING development for agent guardrails. They are removed
REM    here, at clone time, because a production cabinet has no dev agents.
REM    The validation pass (basement hardware check) must be COMPLETE before
REM    this script is run - these files are your last line of defense during
REM    active development.
REM ============================================================================

echo.
echo =========================================================================
echo  STEP 9: Security Scrub - AI Agent Docs and Dev Tooling
echo =========================================================================

REM -- Agent Instruction Files (Architecture Exposure Risk) --------------------
echo   [9.1] Removing AI agent instruction files...

if exist "%~dp0AGENTS.md"          del /f /q "%~dp0AGENTS.md"          && echo         Removed: AGENTS.md
if exist "%~dp0CLAUDE.md"          del /f /q "%~dp0CLAUDE.md"          && echo         Removed: CLAUDE.md
if exist "%~dp0GEMINI.md"          del /f /q "%~dp0GEMINI.md"          && echo         Removed: GEMINI.md
if exist "%~dp0GROK.md"            del /f /q "%~dp0GROK.md"            && echo         Removed: GROK.md
if exist "%~dp0OPENAI.md"          del /f /q "%~dp0OPENAI.md"          && echo         Removed: OPENAI.md

REM -- Dev Session / Workflow Files -------------------------------------------
echo   [9.2] Removing dev session and workflow files...

if exist "%~dp0ROLLING_LOG.md"          del /f /q "%~dp0ROLLING_LOG.md"
if exist "%~dp0SESSION_HANDOFF.md"      del /f /q "%~dp0SESSION_HANDOFF.md"
if exist "%~dp0JULES_TASKS.md"          del /f /q "%~dp0JULES_TASKS.md"
if exist "%~dp0Untitled-1.ps1"          del /f /q "%~dp0Untitled-1.ps1"
if exist "%~dp0.tmp_readme_head.txt"    del /f /q "%~dp0.tmp_readme_head.txt"
if exist "%~dp0.tmp_readme_head_raw.md" del /f /q "%~dp0.tmp_readme_head_raw.md"
echo         Session/workflow files cleaned.

REM -- AI Agent Configuration Directories -------------------------------------
echo   [9.3] Removing AI agent configuration directories...

call :RemoveTree "%~dp0.agent"
call :RemoveTree "%~dp0.claude"
call :RemoveTree "%~dp0.kiro"
call :RemoveTree "%~dp0codex-tasks"
call :RemoveTree "%~dp0claude"
echo         Agent config directories cleaned.

REM -- IDE and Dev Tooling Directories ----------------------------------------
echo   [9.4] Removing IDE and dev tooling directories...

call :RemoveTree "%~dp0.vscode"
call :RemoveTree "%~dp0__screenshots"
call :RemoveTree "%~dp0projects"
call :RemoveTree "%~dp0AA_DRIVE_ROOT_NOT_SET"
echo         IDE/tooling directories cleaned.

REM -- Loose Test Files at Root ------------------------------------------------
echo   [9.5] Removing loose test and diagnostic scripts from root...

REM Test scripts
for %%F in (
    "test_fresh_config.py"
    "test_gamepad.py"
    "test_heartbeat.py"
    "test_joystick_detection.py"
    "test_launchbox_chat.js"
    "test_mame_p2_debug.py"
    "test_mvp_endpoints.sh"
    "test_p2_input.py"
    "test_pcsx2_manual.ps1"
    "test_phase_a5.py"
    "test_port_collision.py"
    "test_search.html"
    "test_teknoparrot_launches.ps1"
    "test_teknoparrot_launches.sh"
    "test-launch.json"
    "test-platforms.ps1"
    "test_hotkey.html"
) do (
    if exist "%~dp0%%~F" del /f /q "%~dp0%%~F"
)

REM Diagnostic scripts
for %%F in (
    "backend_diag.py"
    "cabinet_smoke_test.py"
    "check_db.py"
    "debug_test.ps1"
    "dump_joy_events.py"
    "fix_chars.py"
    "ledwiz_test.py"
    "led_enhancement_demo.py"
    "minimal_backend.py"
    "parse_pylint.py"
    "register_cabinet.py"
    "schema_audit.py"
    "led_color_picker_demo.html"
) do (
    if exist "%~dp0%%~F" del /f /q "%~dp0%%~F"
)
echo         Loose test and diagnostic files cleaned.

REM -- MAME Config Preview Artifacts ------------------------------------------
echo   [9.6] Removing MAME config preview artifacts...

if exist "%~dp0mame_config_preview.cfg"   del /f /q "%~dp0mame_config_preview.cfg"
if exist "%~dp0mame_config_preview2.cfg"  del /f /q "%~dp0mame_config_preview2.cfg"
echo         MAME preview artifacts cleaned.

REM -- Vault Sanity Check ------------------------------------------------------
echo   [9.7] Checking DPAPI vault status...

if exist "%~dp0.aa\credentials.dat" (
    echo         OK: credentials.dat found in .aa vault.
) else (
    echo.
    echo         WARNING: .aa\credentials.dat NOT FOUND.
    echo         Tier 1 secrets are not encrypted. The cabinet will run
    echo         on plaintext .env values only.
    echo         Run 'python encrypt_secrets.py' before deploying.
    echo.
)

REM -- Verify .env is scrubbed -------------------------------------------------
echo   [9.8] Checking .env for live Tier 1 secrets...

REM Search for known Tier 1 keys with real values (not VAULT_MANAGED placeholder)
findstr /i /c:"SUPABASE_ANON_KEY=ey" "%~dp0.env" >nul 2>&1
if %errorlevel% == 0 (
    echo.
    echo         WARNING: .env still contains a live SUPABASE_ANON_KEY.
    echo         This key should be replaced with VAULT_MANAGED after
    echo         running encrypt_secrets.py.
    echo         A live key on a removable drive is a security risk.
    echo.
) else (
    echo         OK: SUPABASE_ANON_KEY not found as plaintext in .env.
)

findstr /i /c:"AA_PROVISIONING_TOKEN=ey" "%~dp0.env" >nul 2>&1
if %errorlevel% == 0 (
    echo.
    echo         WARNING: .env still contains a live AA_PROVISIONING_TOKEN.
    echo         Run encrypt_secrets.py to move this into the vault.
    echo.
) else (
    echo         OK: AA_PROVISIONING_TOKEN not found as plaintext in .env.
)

echo.
echo   Step 9 complete - Security scrub finished.
echo =========================================================================

echo.
echo [OK] Drive cleaned for cloning. frontend\dist and gateway\node_modules were preserved.
exit /b 0

:SanitizeEnv
if not exist ".env" (
  echo .env not found, skipping.
  goto :eof
)
powershell -NoProfile -Command "$path='.env'; $text=Get-Content $path -Raw; $text=$text -replace '(?m)^DEVICE_NAME=.*$', 'DEVICE_NAME=Arcade Cabinet'; $text=$text -replace '(?m)^DEVICE_SERIAL=.*$', 'DEVICE_SERIAL=UNPROVISIONED'; Set-Content $path $text"
echo Sanitized DEVICE_NAME and DEVICE_SERIAL in .env
goto :eof

:DeleteFile
if exist %~1 (
  del /f /q %~1
  echo Deleted %~1
) else (
  echo %~1 not found, skipping.
)
goto :eof

:CleanFolderContents
if exist %~1 (
  del /f /q "%~1\*" >nul 2>&1
  for /d %%d in ("%~1\*") do rd /s /q "%%~d"
  echo Cleared contents of %~1
) else (
  echo %~1 not found, skipping.
)
goto :eof

:RemoveTree
if exist %~1 (
  rd /s /q "%~1"
  echo Removed %~1
) else (
  echo %~1 not found, skipping.
)
goto :eof

:RemoveRecursiveFolders
for /d /r %%d in (%~1) do (
  if exist "%%~fd" (
    rd /s /q "%%~fd"
    echo Removed %%~fd
  )
)
goto :eof

:DeleteRecursiveFiles
for /r %%f in (%~1) do (
  if exist "%%~ff" (
    del /f /q "%%~ff"
    echo Deleted %%~ff
  )
)
goto :eof
