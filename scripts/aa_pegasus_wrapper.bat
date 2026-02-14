@echo off
REM ============================================
REM Pegasus Launch Wrapper v2.0
REM ============================================
REM Wrapper for Pegasus launch - avoids path with spaces issue
REM Pegasus calls: aa_pegasus_wrapper.bat "{file.path}" "Platform Name"
REM We forward to the main script with proper quoting
REM
REM CRITICAL: Must use CALL to ensure proper blocking behavior

call "A:\Arcade Assistant Local\scripts\aa_launch_pegasus_simple.bat" "%~1" "%~2"

REM Ensure we exit with code 0 to prevent Pegasus from closing
exit /b 0
