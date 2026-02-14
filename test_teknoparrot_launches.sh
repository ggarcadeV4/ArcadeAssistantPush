#!/bin/bash
# TeknoParrot Launch Test Script
# Tests multiple Taito Type X games to verify profile alias mappings work correctly

echo "=================================================="
echo "TeknoParrot Launch Verification Script"
echo "=================================================="
echo ""

BACKEND_URL="http://localhost:8888"

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test games - diverse selection to verify different profile types
TEST_GAMES=(
    "Akai Katana Shin"
    "BlazBlue: Central Fiction"
    "Street Fighter V"
    "Raiden IV"
    "Ikaruga"
)

echo -e "${BLUE}Step 1: Checking backend health...${NC}"
HEALTH=$(curl -s "$BACKEND_URL/health" 2>&1)
if echo "$HEALTH" | grep -q "status"; then
    echo -e "${GREEN}✓ Backend is running${NC}"
    echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
else
    echo -e "${RED}✗ Backend is not responding!${NC}"
    echo "Please start the backend with: python backend/app.py"
    exit 1
fi
echo ""

echo -e "${BLUE}Step 2: Fetching Taito Type X games from LaunchBox...${NC}"
GAMES_RESPONSE=$(curl -s "$BACKEND_URL/api/launchbox/games?platform=Taito%20Type%20X&limit=100")
GAME_COUNT=$(echo "$GAMES_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('games', [])))" 2>/dev/null)

if [ -z "$GAME_COUNT" ] || [ "$GAME_COUNT" = "0" ]; then
    echo -e "${RED}✗ No Taito Type X games found!${NC}"
    echo "Response: $GAMES_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✓ Found $GAME_COUNT Taito Type X games${NC}"
echo ""

echo -e "${BLUE}Step 3: Testing launch resolution for selected games...${NC}"
echo "This will show the command that would be executed (dry-run mode)"
echo ""

SUCCESS_COUNT=0
FAIL_COUNT=0

for GAME_TITLE in "${TEST_GAMES[@]}"; do
    echo -e "${YELLOW}Testing: $GAME_TITLE${NC}"

    # Find the game ID
    GAME_ID=$(echo "$GAMES_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for game in data.get('games', []):
    if game.get('title', '').strip() == '$GAME_TITLE':
        print(game.get('id', ''))
        break
" 2>/dev/null)

    if [ -z "$GAME_ID" ]; then
        echo -e "  ${RED}✗ Game not found in LaunchBox${NC}"
        ((FAIL_COUNT++))
        echo ""
        continue
    fi

    echo "  Game ID: $GAME_ID"

    # Test the launch endpoint (this won't actually launch, just resolve the config)
    LAUNCH_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/launchbox/launch/$GAME_ID" \
        -H "Content-Type: application/json" 2>&1)

    # Extract key information
    SUCCESS=$(echo "$LAUNCH_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('success', False))" 2>/dev/null)
    METHOD=$(echo "$LAUNCH_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('method', 'unknown'))" 2>/dev/null)
    MESSAGE=$(echo "$LAUNCH_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('message', ''))" 2>/dev/null)

    if [ "$SUCCESS" = "True" ]; then
        echo -e "  ${GREEN}✓ Launch resolved successfully${NC}"
        echo "  Method: $METHOD"

        # Show the command if available
        COMMAND=$(echo "$LAUNCH_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
exe = data.get('exe', '')
args = data.get('args', [])
if exe and args:
    print(f'{exe} {\" \".join(args)}'[:200])
" 2>/dev/null)

        if [ -n "$COMMAND" ]; then
            echo "  Command: $COMMAND..."
        fi

        ((SUCCESS_COUNT++))
    else
        echo -e "  ${RED}✗ Launch failed${NC}"
        echo "  Error: $MESSAGE"
        ((FAIL_COUNT++))
    fi

    echo ""
done

echo "=================================================="
echo -e "${BLUE}Test Summary${NC}"
echo "=================================================="
echo -e "Total Tests: ${#TEST_GAMES[@]}"
echo -e "${GREEN}Successful: $SUCCESS_COUNT${NC}"
echo -e "${RED}Failed: $FAIL_COUNT${NC}"
echo ""

if [ $FAIL_COUNT -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests passed!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Open LaunchBox LoRa panel in browser (http://localhost:8787)"
    echo "2. Filter by platform: Taito Type X"
    echo "3. Click any game to launch it"
    echo "4. TeknoParrot should open with the correct profile loaded"
    exit 0
else
    echo -e "${YELLOW}⚠ Some tests failed. Check the errors above.${NC}"
    exit 1
fi
