#!/bin/bash

# ================================
# Environment Setup Script
# ================================
# Detects Windows vs WSL and sets up appropriate .env file

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}==================================${NC}"
echo -e "${BLUE}Arcade Assistant Environment Setup${NC}"
echo -e "${BLUE}==================================${NC}\n"

# Detect if we're in WSL
detect_environment() {
    if grep -qi microsoft /proc/version 2>/dev/null; then
        echo "wsl"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
        echo "windows"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    else
        echo "unknown"
    fi
}

ENV_TYPE=$(detect_environment)

echo -e "${YELLOW}Detected environment: ${GREEN}$ENV_TYPE${NC}\n"

# Function to get Windows host IP in WSL
get_windows_host_ip() {
    if [[ "$ENV_TYPE" == "wsl" ]]; then
        ip route | grep default | awk '{print $3}' | head -n1
    else
        echo "127.0.0.1"
    fi
}

# Set up environment based on detection
case $ENV_TYPE in
    wsl)
        echo -e "${BLUE}Setting up WSL environment...${NC}"

        # Check if .env.wsl exists
        if [[ ! -f .env.wsl ]]; then
            echo -e "${RED}Error: .env.wsl not found!${NC}"
            exit 1
        fi

        # Get Windows host IP
        WINDOWS_IP=$(get_windows_host_ip)
        echo -e "${YELLOW}Windows host IP detected: ${GREEN}$WINDOWS_IP${NC}"

        # Create .env from .env.wsl
        cp .env.wsl .env

        # Update Windows host IP
        sed -i "s/WINDOWS_HOST_IP=.*/WINDOWS_HOST_IP=$WINDOWS_IP/" .env

        # Check if A: drive is accessible
        if [[ -d "/mnt/a/LaunchBox" ]]; then
            echo -e "${GREEN}✓ A: drive accessible at /mnt/a${NC}"
        else
            echo -e "${YELLOW}⚠ A: drive not found at /mnt/a${NC}"
            echo -e "${YELLOW}  You may need to mount it manually or update paths${NC}"
        fi

        echo -e "${GREEN}✓ WSL environment configured${NC}"
        ;;

    windows|msys|cygwin)
        echo -e "${BLUE}Setting up Windows native environment...${NC}"

        # Check if .env.win exists
        if [[ ! -f .env.win ]]; then
            echo -e "${RED}Error: .env.win not found!${NC}"
            exit 1
        fi

        # Create .env from .env.win
        cp .env.win .env

        # Check if A: drive exists
        if [[ -d "A:/LaunchBox" ]] || [[ -d "/a/LaunchBox" ]]; then
            echo -e "${GREEN}✓ A: drive found${NC}"
        else
            echo -e "${YELLOW}⚠ A: drive not found${NC}"
            echo -e "${YELLOW}  Please verify LaunchBox installation path${NC}"
        fi

        echo -e "${GREEN}✓ Windows environment configured${NC}"
        ;;

    linux)
        echo -e "${YELLOW}Native Linux detected (not WSL)${NC}"
        echo -e "${YELLOW}Using development/mock data mode${NC}"

        # Create development .env
        cat > .env << EOF
# Development Environment (Linux Native)
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
OPENAI_API_KEY=sk-your-openai-key-here
ELEVENLABS_API_KEY=your-elevenlabs-key-here

# Mock LaunchBox paths for development
LAUNCHBOX_ROOT=./mock_data/LaunchBox
AA_DRIVE_ROOT=./mock_data
LAUNCHBOX_PLUGIN_PORT=10099
export LB_PLUGIN_PORT=${LAUNCHBOX_PLUGIN_PORT}
LAUNCHBOX_PLUGIN_HOST=127.0.0.1

# Backend Configuration
FASTAPI_URL=http://localhost:8888
PORT=8787

# Development paths
ROMS_PATH=./mock_data/Roms
BIOS_PATH=./mock_data/Bios
EMULATORS_PATH=./mock_data/Emulators
ARCADE_CONFIGS=./mock_data/configs

# Development Settings
NODE_ENV=development
LOG_LEVEL=debug
AA_ALLOW_DIRECT_EMULATOR=false

# Linux Settings
USE_SHELL=false
PYTHON_EXECUTABLE=python3
HOST=localhost
FORCE_COLOR=1
EOF

        echo -e "${GREEN}✓ Linux development environment configured${NC}"
        ;;

    *)
        echo -e "${RED}Unable to detect environment type${NC}"
        echo -e "${YELLOW}Please manually copy .env.win or .env.wsl to .env${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${BLUE}Next steps:${NC}"
echo -e "1. Edit ${GREEN}.env${NC} and add your API keys"
echo -e "2. Verify paths are correct for your system"
echo -e "3. Run: ${GREEN}npm run install:all${NC}"
echo -e "4. Run: ${GREEN}npm run dev${NC}"
echo ""

# Check for required tools
echo -e "${BLUE}Checking required tools:${NC}"

check_tool() {
    if command -v $1 &> /dev/null; then
        echo -e "${GREEN}✓ $1 found${NC}"
        return 0
    else
        echo -e "${RED}✗ $1 not found${NC}"
        return 1
    fi
}

TOOLS_OK=true
check_tool node || TOOLS_OK=false
check_tool npm || TOOLS_OK=false
check_tool python3 || check_tool python || TOOLS_OK=false
check_tool curl || TOOLS_OK=false

if [[ "$TOOLS_OK" == "false" ]]; then
    echo ""
    echo -e "${RED}Some required tools are missing!${NC}"
    echo -e "${YELLOW}Please install missing dependencies before proceeding.${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Environment setup complete!${NC}"
