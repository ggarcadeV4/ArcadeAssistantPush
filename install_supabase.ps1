# Supabase Integration - Quick Install Script (PowerShell)
# Arcade Assistant

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Supabase Integration - Quick Install" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Check if .env exists
if (-not (Test-Path .env)) {
    Write-Host "⚠️  .env file not found. Creating from template..." -ForegroundColor Yellow
    Copy-Item .env.example .env
    Write-Host "✅ Created .env file" -ForegroundColor Green
    Write-Host ""
    Write-Host "⚠️  IMPORTANT: Edit .env and add your Supabase credentials:" -ForegroundColor Yellow
    Write-Host "   - SUPABASE_URL"
    Write-Host "   - SUPABASE_ANON_KEY"
    Write-Host "   - SUPABASE_SERVICE_ROLE_KEY"
    Write-Host ""
    Read-Host "Press Enter after you've updated .env"
}

Write-Host "Step 1/3: Installing Python dependencies..." -ForegroundColor Cyan
Set-Location backend
pip install supabase>=2.0.0 | Out-Null
Write-Host "✅ Python dependencies installed" -ForegroundColor Green
Write-Host ""

Write-Host "Step 2/3: Installing Node.js dependencies..." -ForegroundColor Cyan
Set-Location ..
npm install @supabase/supabase-js | Out-Null
Write-Host "✅ Node.js dependencies installed" -ForegroundColor Green
Write-Host ""

Write-Host "Step 3/3: Testing connectivity..." -ForegroundColor Cyan
$backendJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    npm run dev:backend
}

# Wait for backend to start
Write-Host "Waiting for backend to start..."
Start-Sleep -Seconds 5

# Test health endpoint
Write-Host "Testing Supabase health endpoint..."
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8888/api/supabase/health" -ErrorAction Stop

    if ($response.status -eq "connected") {
        Write-Host "✅ Supabase connectivity test PASSED" -ForegroundColor Green
        Write-Host ""
        Write-Host "======================================" -ForegroundColor Green
        Write-Host "✅ Installation Complete!" -ForegroundColor Green
        Write-Host "======================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "Supabase is ready to use. Next steps:"
        Write-Host "1. Create Supabase project at supabase.com"
        Write-Host "2. Run schema: supabase/schema.sql in SQL Editor"
        Write-Host "3. Deploy Edge Functions (see SUPABASE_SETUP_GUIDE.md)"
        Write-Host ""
        Write-Host "Documentation:"
        Write-Host "  - Setup Guide: SUPABASE_SETUP_GUIDE.md"
        Write-Host "  - Quick Reference: SUPABASE_QUICK_REFERENCE.md"
        Write-Host ""
    } else {
        throw "Unexpected response status"
    }
} catch {
    Write-Host "⚠️  Supabase connectivity test FAILED" -ForegroundColor Red
    Write-Host ""
    Write-Host "Error: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Possible issues:"
    Write-Host "  1. .env not configured with correct SUPABASE_URL and SUPABASE_ANON_KEY"
    Write-Host "  2. Supabase project not created yet"
    Write-Host "  3. Network/firewall issues"
    Write-Host ""
    Write-Host "Check SUPABASE_SETUP_GUIDE.md for troubleshooting steps."
}

# Kill backend
Stop-Job $backendJob -ErrorAction SilentlyContinue
Remove-Job $backendJob -ErrorAction SilentlyContinue

exit 0
