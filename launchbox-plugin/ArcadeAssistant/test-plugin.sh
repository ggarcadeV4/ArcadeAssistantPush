#!/bin/bash

# Arcade Assistant LaunchBox Plugin Test Script (WSL/Linux)
# Run this after installing the plugin and starting LaunchBox

set -e

BLUE='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

BASE_URL="http://127.0.0.1:31337"

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}Arcade Assistant Plugin Tester${NC}"
echo -e "${BLUE}================================${NC}"
echo

# Function to test endpoints
test_endpoint() {
    local method=$1
    local endpoint=$2
    local data=$3
    local description=$4

    echo -e "${YELLOW}Testing: $description${NC}"
    echo -e "  ${method} ${BASE_URL}${endpoint}"

    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\nHTTP_STATUS:%{http_code}" "${BASE_URL}${endpoint}" 2>/dev/null || true)
    else
        response=$(curl -s -X "$method" \
            -H "Content-Type: application/json" \
            -d "$data" \
            -w "\nHTTP_STATUS:%{http_code}" \
            "${BASE_URL}${endpoint}" 2>/dev/null || true)
    fi

    # Extract HTTP status
    http_status=$(echo "$response" | grep "HTTP_STATUS" | cut -d: -f2)
    body=$(echo "$response" | grep -v "HTTP_STATUS")

    if [ -z "$http_status" ] || [ "$http_status" = "000" ]; then
        echo -e "  ${RED}ERROR: Cannot connect to plugin server${NC}"
        echo -e "  ${YELLOW}- Is LaunchBox running?${NC}"
        echo -e "  ${YELLOW}- Is the plugin installed?${NC}"
        return 1
    elif [ "$http_status" -ge 200 ] && [ "$http_status" -lt 300 ]; then
        echo -e "  ${GREEN}Success! (HTTP $http_status)${NC}"
        if [ -n "$body" ]; then
            echo "  Response: $body" | head -n 5
        fi
        return 0
    else
        echo -e "  ${RED}Failed with HTTP $http_status${NC}"
        if [ -n "$body" ]; then
            echo "  Error: $body"
        fi
        return 1
    fi
}

# Test 1: Health Check
echo
echo -e "${BLUE}TEST 1: Health Check${NC}"
echo "-------------------"
if test_endpoint "GET" "/health" "" "Check if server is running"; then
    echo -e "  ${GREEN}Plugin is responding!${NC}"
fi

# Test 2: Server Status
echo
echo -e "${BLUE}TEST 2: Server Status${NC}"
echo "--------------------"
test_endpoint "GET" "/status" "" "Get detailed status"

# Test 3: Get Sample Games
echo
echo -e "${BLUE}TEST 3: Get Sample Games${NC}"
echo "------------------------"
if test_endpoint "GET" "/games" "" "List sample games"; then
    # Extract first game ID for testing (if jq is available)
    if command -v jq &> /dev/null; then
        game_json=$(curl -s "${BASE_URL}/games" 2>/dev/null)
        game_id=$(echo "$game_json" | jq -r '.sample[0].id' 2>/dev/null || echo "")
        game_title=$(echo "$game_json" | jq -r '.sample[0].title' 2>/dev/null || echo "")
        total_games=$(echo "$game_json" | jq -r '.total' 2>/dev/null || echo "0")

        if [ -n "$game_id" ] && [ "$game_id" != "null" ]; then
            echo -e "  Found ${GREEN}$total_games${NC} total games"
            echo "  First game: $game_title"
            echo "  Game ID: $game_id"
            FIRST_GAME_ID=$game_id
            FIRST_GAME_TITLE=$game_title
        fi
    else
        echo "  (Install 'jq' for better JSON parsing: sudo apt-get install jq)"
    fi
fi

# Test 4: Launch Game (optional)
if [ -n "$FIRST_GAME_ID" ]; then
    echo
    echo -e "${BLUE}TEST 4: Launch Game Test${NC}"
    echo "------------------------"
    echo -n "Do you want to test launching '$FIRST_GAME_TITLE'? (y/n): "
    read -r confirm

    if [ "$confirm" = "y" ]; then
        test_endpoint "POST" "/launch" "{\"game_id\":\"$FIRST_GAME_ID\"}" "Launch game"
    else
        echo "  Launch test skipped"
    fi
fi

# Test 5: Error Handling
echo
echo -e "${BLUE}TEST 5: Error Handling${NC}"
echo "----------------------"
test_endpoint "POST" "/launch" "{\"game_id\":\"invalid-id\"}" "Test invalid game ID" || true

# Summary
echo
echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}Test Complete!${NC}"
echo -e "${BLUE}================================${NC}"
echo

# Check if curl can reach the server
if curl -s -f "${BASE_URL}/health" > /dev/null 2>&1; then
    echo -e "${GREEN}Plugin is working correctly!${NC}"
    echo
    echo "Example commands you can use:"
    echo -e "${YELLOW}# Check health:${NC}"
    echo "  curl ${BASE_URL}/health"
    echo
    echo -e "${YELLOW}# List games:${NC}"
    echo "  curl ${BASE_URL}/games | jq '.sample[:3]'"
    echo
    echo -e "${YELLOW}# Launch a game:${NC}"
    echo "  curl -X POST ${BASE_URL}/launch \\"
    echo "    -H \"Content-Type: application/json\" \\"
    echo "    -d '{\"game_id\":\"YOUR-GAME-ID\"}'"
else
    echo -e "${RED}Plugin is not responding.${NC}"
    echo
    echo "Please check:"
    echo "1. LaunchBox is running on Windows"
    echo "2. Plugin DLL is in: A:\\LaunchBox\\Plugins\\ArcadeAssistant\\"
    echo "3. No errors in LaunchBox logs"
    echo "4. Windows Firewall is not blocking port 31337"
fi

echo