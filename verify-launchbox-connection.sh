#!/bin/bash
# LaunchBox LoRa Connection Verification Script
# Created: 2025-10-06
# Purpose: Test if Gateway → FastAPI → LaunchBox integration is working

echo "=== LaunchBox LoRa Connection Verification ==="
echo ""

echo "Step 1: Testing Gateway health..."
GATEWAY_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8787/api/health)
if [ "$GATEWAY_HEALTH" = "200" ]; then
  echo "✅ Gateway is running on port 8787"
else
  echo "❌ Gateway not responding (HTTP $GATEWAY_HEALTH)"
  echo "   Fix: Run 'npm run dev:gateway' in a terminal"
  exit 1
fi

echo ""
echo "Step 2: Testing FastAPI backend health..."
BACKEND_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
if [ "$BACKEND_HEALTH" = "200" ]; then
  echo "✅ FastAPI backend is running on port 8000"
else
  echo "❌ Backend not responding (HTTP $BACKEND_HEALTH)"
  echo "   Fix: Run 'npm run dev:backend' in a terminal"
  exit 1
fi

echo ""
echo "Step 3: Testing Gateway → Backend proxy..."
PROXY_TEST=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8787/api/launchbox/stats)
if [ "$PROXY_TEST" = "200" ]; then
  echo "✅ Gateway successfully proxies /api/launchbox to backend"
else
  echo "⚠️  Proxy returning HTTP $PROXY_TEST"
  echo "   This might be normal if LaunchBox router isn't initialized yet"
fi

echo ""
echo "Step 4: Fetching LaunchBox stats..."
STATS=$(curl -s http://localhost:8787/api/launchbox/stats)
echo "$STATS" | python3 -m json.tool 2>/dev/null || echo "$STATS"

echo ""
echo "Step 5: Testing game listing..."
GAMES=$(curl -s "http://localhost:8787/api/launchbox/games?limit=1")
echo "$GAMES" | python3 -m json.tool 2>/dev/null || echo "$GAMES"

echo ""
echo "=== Verification Complete ==="
echo ""
echo "If you see JSON responses above, the connection is working!"
echo "If you see HTML or errors, check that both services are running:"
echo "  Terminal 1: npm run dev:backend"
echo "  Terminal 2: npm run dev:gateway"
echo "  Terminal 3: npm run dev:frontend"
