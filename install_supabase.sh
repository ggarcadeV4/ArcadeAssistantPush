#!/bin/bash
# Supabase Integration - Quick Install Script
# Arcade Assistant

set -e

echo "======================================"
echo "Supabase Integration - Quick Install"
echo "======================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cp .env.example .env
    echo "✅ Created .env file"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env and add your Supabase credentials:"
    echo "   - SUPABASE_URL"
    echo "   - SUPABASE_ANON_KEY"
    echo "   - SUPABASE_SERVICE_ROLE_KEY"
    echo ""
    read -p "Press Enter after you've updated .env..."
fi

echo "Step 1/3: Installing Python dependencies..."
cd backend
pip install supabase>=2.0.0
echo "✅ Python dependencies installed"
echo ""

echo "Step 2/3: Installing Node.js dependencies..."
cd ..
npm install @supabase/supabase-js
echo "✅ Node.js dependencies installed"
echo ""

echo "Step 3/3: Testing connectivity..."
npm run dev:backend &
BACKEND_PID=$!

# Wait for backend to start
echo "Waiting for backend to start..."
sleep 5

# Test health endpoint
echo "Testing Supabase health endpoint..."
HEALTH_RESPONSE=$(curl -s http://localhost:8888/api/supabase/health || echo '{"status":"error"}')

if echo "$HEALTH_RESPONSE" | grep -q '"connected"'; then
    echo "✅ Supabase connectivity test PASSED"
    echo ""
    echo "======================================"
    echo "✅ Installation Complete!"
    echo "======================================"
    echo ""
    echo "Supabase is ready to use. Next steps:"
    echo "1. Create Supabase project at supabase.com"
    echo "2. Run schema: supabase/schema.sql in SQL Editor"
    echo "3. Deploy Edge Functions (see SUPABASE_SETUP_GUIDE.md)"
    echo ""
    echo "Documentation:"
    echo "  - Setup Guide: SUPABASE_SETUP_GUIDE.md"
    echo "  - Quick Reference: SUPABASE_QUICK_REFERENCE.md"
    echo ""
else
    echo "⚠️  Supabase connectivity test FAILED"
    echo ""
    echo "Response: $HEALTH_RESPONSE"
    echo ""
    echo "Possible issues:"
    echo "  1. .env not configured with correct SUPABASE_URL and SUPABASE_ANON_KEY"
    echo "  2. Supabase project not created yet"
    echo "  3. Network/firewall issues"
    echo ""
    echo "Check SUPABASE_SETUP_GUIDE.md for troubleshooting steps."
fi

# Kill backend
kill $BACKEND_PID 2>/dev/null || true

exit 0
