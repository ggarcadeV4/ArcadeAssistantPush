#!/usr/bin/env bash
# MVP Environment Validation Script
# Run before starting UI integration work

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}MVP Environment Validation${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

ERRORS=0
WARNINGS=0

# Check 1: Manifest
echo -n "✓ Checking manifest... "
if [ -f ".aa/manifest.json" ]; then
  MANIFEST=$(cat .aa/manifest.json)

  if echo "$MANIFEST" | grep -q 'state' && \
     echo "$MANIFEST" | grep -q 'config' && \
     echo "$MANIFEST" | grep -q 'backups' && \
     echo "$MANIFEST" | grep -q 'logs'; then
    echo -e "${GREEN}OK${NC}"
    echo "  - Sanctioned paths: state ✓ config ✓ backups ✓ logs ✓"
  else
    echo -e "${RED}FAIL${NC}"
    echo "  - Missing required sanctioned paths"
    ERRORS=$((ERRORS + 1))
  fi
else
  echo -e "${RED}FAIL${NC}"
  echo "  - .aa/manifest.json not found"
  ERRORS=$((ERRORS + 1))
fi

# Check 2: Backend routes exist
echo -n "✓ Checking backend routes... "
if [ -f "backend/routers/scorekeeper.py" ] && [ -f "backend/routers/led_blinky.py" ]; then
  echo -e "${GREEN}OK${NC}"
  echo "  - scorekeeper.py ✓"
  echo "  - led_blinky.py ✓"
else
  echo -e "${RED}FAIL${NC}"
  ERRORS=$((ERRORS + 1))
fi

# Check 3: API clients exist
echo -n "✓ Checking API clients... "
if [ -f "frontend/src/services/scorekeeperClient.js" ] && [ -f "frontend/src/services/ledBlinkyClient.js" ]; then
  echo -e "${GREEN}OK${NC}"
  echo "  - scorekeeperClient.js ✓"
  echo "  - ledBlinkyClient.js ✓"
else
  echo -e "${RED}FAIL${NC}"
  ERRORS=$((ERRORS + 1))
fi

# Check 4: Test script exists
echo -n "✓ Checking test script... "
if [ -f "test_mvp_endpoints.sh" ] && [ -x "test_mvp_endpoints.sh" ]; then
  echo -e "${GREEN}OK${NC}"
else
  echo -e "${YELLOW}WARNING${NC}"
  echo "  - test_mvp_endpoints.sh not found or not executable"
  WARNINGS=$((WARNINGS + 1))
fi

# Check 5: Backend running
echo -n "✓ Checking backend status... "
BACKEND_URL="${FASTAPI_URL:-http://localhost:8888}"
if curl -s "$BACKEND_URL/health" > /dev/null 2>&1; then
  echo -e "${GREEN}OK${NC}"
  HEALTH=$(curl -s "$BACKEND_URL/health" | head -c 100)
  echo "  - Backend running at $BACKEND_URL"
  echo "  - Health: $HEALTH"
else
  echo -e "${YELLOW}OFFLINE${NC}"
  echo "  - Start with: npm run dev:backend"
  WARNINGS=$((WARNINGS + 1))
fi

# Check 6: Required directories
echo -n "✓ Checking directory structure... "
MISSING_DIRS=""
for dir in "backend/routers" "backend/services" "frontend/src/services" "frontend/src/panels" ".aa"; do
  if [ ! -d "$dir" ]; then
    MISSING_DIRS="$MISSING_DIRS $dir"
  fi
done

if [ -z "$MISSING_DIRS" ]; then
  echo -e "${GREEN}OK${NC}"
else
  echo -e "${RED}FAIL${NC}"
  echo "  - Missing directories:$MISSING_DIRS"
  ERRORS=$((ERRORS + 1))
fi

# Check 7: Logs directory writable
echo -n "✓ Checking logs directory... "
if [ -d "logs" ] && [ -w "logs" ]; then
  echo -e "${GREEN}OK${NC}"
  echo "  - logs/ directory writable ✓"
elif [ ! -d "logs" ]; then
  echo -e "${YELLOW}WARNING${NC}"
  echo "  - logs/ directory does not exist (will be created on first write)"
  WARNINGS=$((WARNINGS + 1))
else
  echo -e "${RED}FAIL${NC}"
  echo "  - logs/ directory not writable"
  ERRORS=$((ERRORS + 1))
fi

# Check 8: Quick reference docs
echo -n "✓ Checking documentation... "
if [ -f "MVP_QUICK_REFERENCE.md" ] && [ -f "NEXT_SESSION_HANDOFF.md" ]; then
  echo -e "${GREEN}OK${NC}"
  echo "  - MVP_QUICK_REFERENCE.md ✓"
  echo "  - NEXT_SESSION_HANDOFF.md ✓"
else
  echo -e "${YELLOW}WARNING${NC}"
  echo "  - Reference docs missing (not critical)"
  WARNINGS=$((WARNINGS + 1))
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Summary${NC}"
echo -e "${BLUE}========================================${NC}"

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
  echo -e "${GREEN}✓ All checks passed!${NC}"
  echo ""
  echo "Ready to start UI integration. Next steps:"
  echo "  1. Start backend: npm run dev:backend"
  echo "  2. Run tests: ./test_mvp_endpoints.sh"
  echo "  3. Start frontend: npm run dev:frontend"
  echo "  4. Follow: NEXT_SESSION_HANDOFF.md"
  exit 0
elif [ $ERRORS -eq 0 ]; then
  echo -e "${YELLOW}⚠ $WARNINGS warning(s) found${NC}"
  echo ""
  echo "Environment is usable but some optional components are missing."
  echo "Review warnings above before proceeding."
  exit 0
else
  echo -e "${RED}✗ $ERRORS error(s) found${NC}"
  if [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}⚠ $WARNINGS warning(s) found${NC}"
  fi
  echo ""
  echo "Fix errors before proceeding with UI integration."
  exit 1
fi
