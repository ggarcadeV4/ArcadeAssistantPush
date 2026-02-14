param(
  [string]$Configuration = "Release",
  [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'

Write-Host "== Arcade Assistant Plugin Deploy ==" -ForegroundColor Cyan
Write-Host "Configuration: $Configuration"

# Resolve paths
$projDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projDir
$proj = Join-Path $projDir 'ArcadeAssistantPlugin.csproj'
$tfm = 'net9.0-windows'
$outDir = Join-Path $projDir "bin/$Configuration/$tfm"
$dll = Join-Path $outDir 'ArcadeAssistantPlugin.dll'
$destDir = 'A:\LaunchBox\Plugins\ArcadeAssistant'
$destDll = Join-Path $destDir 'ArcadeAssistantPlugin.dll'

# Check .NET SDK version
try {
  $sdks = & dotnet --list-sdks 2>$null
} catch {}

if (-not $sdks -or ($sdks -notmatch '^9\.')) {
  Write-Warning "Requires .NET 9 SDK to build. Found:`n$sdks"
  if (-not $SkipBuild) { throw "Install .NET 9 SDK from https://aka.ms/dotnet/download" }
}

if (-not $SkipBuild) {
  Write-Host "Building project..." -ForegroundColor Yellow
  & dotnet build $proj -c $Configuration | Write-Host
}

if (-not (Test-Path $dll)) { throw "Build output not found: $dll" }

Write-Host "Deploying to $destDir" -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $destDir | Out-Null
Copy-Item -Force $dll $destDll

try { Unblock-File $destDll } catch {}

Write-Host "Deployed: $destDll" -ForegroundColor Green
Write-Host "Restart LaunchBox to load the plugin." -ForegroundColor Green

