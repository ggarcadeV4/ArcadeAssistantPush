
# This script executes the Python-based LED-Wiz diagnostic tool
# using the required 32-bit Python 2.7 interpreter.

# Get the directory where the script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Construct the full path to the python script
$PythonScript = Join-Path $ScriptDir "ledwiz_test.py"

# Define the path to the 32-bit Python interpreter
$Python32Exe = "C:\Python27\python.exe"

Write-Host "--- PowerShell Runner for LED-Wiz Test ---"
Write-Host "Executing: $Python32Exe $PythonScript"
Write-Host ""

# Execute the python script
& $Python32Exe $PythonScript

Write-Host ""
Write-Host "--- PowerShell Runner Finished ---"

