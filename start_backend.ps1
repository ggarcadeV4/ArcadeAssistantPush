# start_backend.ps1 - Backend Startup Script
# Loads .env values into environment before starting uvicorn
# This ensures AA_DRIVE_ROOT is set before Python imports run

param(
    [Parameter(Mandatory = $false)]
    [int]$Port,
    [Parameter(Mandatory = $false)]
    [string]$BindHost = "0.0.0.0",
    [Parameter(Mandatory = $false)]
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $ScriptDir ".env"

function Write-Info([string]$Message) { Write-Host "[INFO] $Message" -ForegroundColor Gray }
function Write-Warn([string]$Message) { Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Write-Err([string]$Message) { Write-Host "[ERR ] $Message" -ForegroundColor Red }

Write-Host "=== Arcade Assistant Backend Startup ===" -ForegroundColor Cyan
Write-Info "Repo root: $ScriptDir"

# Ensure we are running from repo root
Set-Location $ScriptDir

# Guard against WSL/Linux PowerShell (path mismatch with A:\)
if ($env:WSL_DISTRO_NAME) {
    Write-Err "Detected WSL environment. Use Windows PowerShell for A:\ paths."
    exit 1
}
if (Get-Variable -Name IsLinux -ErrorAction SilentlyContinue) {
    if ($IsLinux) {
        Write-Err "Linux PowerShell detected. Use Windows PowerShell for A:\ paths."
        exit 1
    }
}

# Load .env file into environment
if (Test-Path $EnvFile) {
    Write-Info "Loading .env from: $EnvFile"
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $key = $parts[0].Trim()
            $value = $parts[1].Trim()
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
} else {
    Write-Warn ".env file not found at $EnvFile"
}

# Validate AA_DRIVE_ROOT
if (-not $env:AA_DRIVE_ROOT) {
    Write-Warn "AA_DRIVE_ROOT is not set."
} elseif ($env:AA_DRIVE_ROOT -notmatch '^[A-Za-z]:\\') {
    Write-Err "AA_DRIVE_ROOT must be a Windows path like A:\\ (current: $env:AA_DRIVE_ROOT)"
    exit 1
} else {
    if (-not (Test-Path $env:AA_DRIVE_ROOT)) {
        Write-Warn "AA_DRIVE_ROOT path not found: $env:AA_DRIVE_ROOT"
    }
    Write-Host "AA_DRIVE_ROOT = $env:AA_DRIVE_ROOT" -ForegroundColor Green
}

# Set PYTHONPATH
$env:PYTHONPATH = $ScriptDir
Write-Info "PYTHONPATH = $env:PYTHONPATH"

function Get-SystemPython {
    # Prefer the Python Launcher on Windows (more deterministic than PATH)
    $pyLauncher = (Get-Command py -ErrorAction SilentlyContinue)
    if ($pyLauncher) {
        return "py"
    }
    return "python"
}

function Ensure-Venv {
    param(
        [string]$RepoRoot,
        [string]$VenvPythonPath
    )
    if (Test-Path $VenvPythonPath) {
        return
    }

    $systemPython = Get-SystemPython
    Write-Warn ".venv not found; creating it using '$systemPython'"

    try {
        if ($systemPython -eq 'py') {
            & py -3 -m venv (Join-Path $RepoRoot '.venv')
        } else {
            & python -m venv (Join-Path $RepoRoot '.venv')
        }
    } catch {
        Write-Err "Failed to create .venv."
        exit 1
    }

    if (-not (Test-Path $VenvPythonPath)) {
        Write-Err ".venv python not found at $VenvPythonPath"
        exit 1
    }
}

$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
Ensure-Venv -RepoRoot $ScriptDir -VenvPythonPath $VenvPython

$PythonExe = $VenvPython
Write-Info "Using venv python: $PythonExe"

try {
    $PyPath = (& $PythonExe -c "import sys; print(sys.executable)").Trim()
    $PyVersion = (& $PythonExe -c "import sys; print(sys.version)").Trim()
    $PyPlatform = (& $PythonExe -c "import platform; print(platform.platform())").Trim()
    $PipVersion = (& $PythonExe -m pip --version).Trim()
    Write-Info "Python executable: $PyPath"
    Write-Info "Python version:    $PyVersion"
    Write-Info "Platform:          $PyPlatform"
    Write-Info "Pip:               $PipVersion"
    if ($PyPath -match '^/') {
        Write-Err "WSL/Linux Python detected: $PyPath"
        exit 1
    }
} catch {
    Write-Err "Unable to verify Python interpreter details."
    exit 1
}

$ReqFile = Join-Path $ScriptDir "backend\requirements.txt"
if (Test-Path $ReqFile) {
    $HashFile = Join-Path $ScriptDir ".venv\.requirements.hash"
    $FingerprintFile = Join-Path $ScriptDir ".venv\.requirements.fingerprint.json"
    $NeedInstall = $false
    $CurrentHash = $null

    try {
        $CurrentHash = (Get-FileHash -Path $ReqFile -Algorithm SHA256).Hash
    } catch {
        $NeedInstall = $true
    }

    if (-not $NeedInstall) {
        if (-not (Test-Path $FingerprintFile)) {
            $NeedInstall = $true
        } else {
            try {
                $Saved = Get-Content $FingerprintFile -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
                if (-not $Saved) {
                    $NeedInstall = $true
                } elseif ($Saved.requirements_sha256 -ne $CurrentHash) {
                    $NeedInstall = $true
                } elseif ($Saved.python_executable -ne $PyPath) {
                    $NeedInstall = $true
                } elseif ($Saved.pip_version -ne $PipVersion) {
                    $NeedInstall = $true
                }
            } catch {
                $NeedInstall = $true
            }
        }
    }

    if (-not $NeedInstall) {
        & $PythonExe -c "import fastapi, uvicorn, pydantic, structlog, psutil" 2>$null
        if ($LASTEXITCODE -ne 0) {
            $NeedInstall = $true
        }
    }

    if ($NeedInstall) {
        Write-Host "Installing backend requirements..." -ForegroundColor Cyan
        & $PythonExe -m pip install -r $ReqFile
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: pip install failed." -ForegroundColor Red
            exit 1
        }

        & $PythonExe -c "import fastapi, uvicorn, pydantic, structlog" 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Critical imports still failing after install." -ForegroundColor Red
            exit 1
        }

        try {
            if (-not (Test-Path (Split-Path $HashFile -Parent))) {
                New-Item -ItemType Directory -Path (Split-Path $HashFile -Parent) | Out-Null
            }
            if ($CurrentHash) {
                $CurrentHash | Out-File -FilePath $HashFile -Encoding ascii -Force
            }
            $FingerprintObj = [PSCustomObject]@{
                requirements_sha256 = $CurrentHash
                python_executable   = $PyPath
                python_version      = $PyVersion
                pip_version         = $PipVersion
            }
            $FingerprintObj | ConvertTo-Json -Depth 3 | Out-File -FilePath $FingerprintFile -Encoding utf8 -Force
        } catch {
            Write-Host "WARNING: Failed to write requirements fingerprint." -ForegroundColor Yellow
            Write-Warn "Failed to write requirements fingerprint."
        }
    }
} else {
    Write-Warn "backend\\requirements.txt not found."
}

# Derive port from CLI override, then FASTAPI_URL when set
$EffectivePort = 8000
if ($Port -and $Port -gt 0) {
    $EffectivePort = $Port
} elseif ($env:FASTAPI_URL -and $env:FASTAPI_URL -match ":(\d+)$") {
    $EffectivePort = [int]$Matches[1]
}

# Start backend
Write-Host ""
$env:PYTHONUNBUFFERED = '1'  # Phase0F: ensure logs flush immediately
Write-Host "Starting uvicorn on ${BindHost}:$EffectivePort..." -ForegroundColor Cyan

$args = @(
    '-m', 'uvicorn',
    'backend.app:app',
    '--host', $BindHost,
    '--port', "$EffectivePort"
)
if ($Reload) {
    $args += '--reload'
}

& $PythonExe @args
