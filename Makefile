# ================================
# Arcade Assistant Makefile
# ================================
# Development automation and environment management

.PHONY: help setup setup-win setup-wsl dev dev-win dev-wsl install test clean verify-env bootstrap

# Smoke checks
.PHONY: smoke smoke-no-start smoke-ps smoke-sh
.PHONY: smoke-stack smoke-stack-no-start
.PHONY: smoke-gateway smoke-gateway-no-start

# OS detection (Windows fallback)
OS := $(shell uname -s 2>/dev/null || echo Windows)

# Default target - show help
help:
	@echo "Arcade Assistant Development Commands"
	@echo "====================================="
	@echo ""
	@echo "Setup Commands:"
	@echo "  make setup        - Auto-detect and setup environment"
	@echo "  make setup-win    - Setup Windows native environment"
	@echo "  make setup-wsl    - Setup WSL environment"
	@echo ""
	@echo "Development Commands:"
	@echo "  make dev          - Start full development stack"
	@echo "  make dev-win      - Start with Windows configuration"
	@echo "  make dev-wsl      - Start with WSL configuration"
	@echo ""
	@echo "Individual Services:"
	@echo "  make frontend     - Start frontend only (Vite)"
	@echo "  make gateway      - Start gateway only (Express)"
	@echo "  make backend      - Start backend only (FastAPI)"
	@echo "  make plugin-test  - Test LaunchBox plugin connection"
	@echo ""
	@echo "Utility Commands:"
	@echo "  make install      - Install all dependencies"
	@echo "  make test         - Run all tests"
	@echo "  make clean        - Clean build artifacts"
	@echo "  make verify-env   - Verify environment setup"
	@echo "  make bootstrap    - Run agent bootstrap validation"
	@echo "  make logs         - Tail all service logs"
	@echo ""

# ================================
# Environment Setup
# ================================

setup:
	@echo "🔍 Auto-detecting environment..."
	@bash scripts/setup-env.sh

setup-win:
	@echo "🪟 Setting up Windows native environment..."
	@cp .env.win .env
	@echo "✅ Windows environment configured"
	@echo "📝 Please edit .env and add your API keys"

setup-wsl:
	@echo "🐧 Setting up WSL environment..."
	@cp .env.wsl .env
	@# Update Windows host IP dynamically
	@if grep -qi microsoft /proc/version 2>/dev/null; then \
		WINDOWS_IP=$$(ip route | grep default | awk '{print $$3}' | head -n1); \
		sed -i "s/WINDOWS_HOST_IP=.*/WINDOWS_HOST_IP=$$WINDOWS_IP/" .env; \
		echo "✅ WSL environment configured (Windows IP: $$WINDOWS_IP)"; \
	else \
		echo "⚠️  Not running in WSL, using default .env.wsl"; \
	fi
	@echo "📝 Please edit .env and add your API keys"

# ================================
# Development Environments
# ================================

dev: verify-env
	@echo "🚀 Starting full development stack..."
	npm run dev

dev-win: setup-win install
	@echo "🪟 Starting Windows development environment..."
	npm run dev

dev-wsl: setup-wsl install
	@echo "🐧 Starting WSL development environment..."
	npm run dev

# ================================
# Individual Services
# ================================

frontend:
	@echo "🎨 Starting frontend (Vite)..."
	npm run dev:frontend

gateway:
	@echo "🔌 Starting gateway (Express)..."
	npm run dev:gateway

backend:
	@echo "🐍 Starting backend (FastAPI)..."
	npm run dev:backend

# ================================
# Plugin Testing
# ================================

plugin-test:
	@echo "🎮 Testing LaunchBox plugin connection..."
	@echo ""
	@echo "Health Check:"
	@curl -s http://127.0.0.1:9999/health | python3 -m json.tool || echo "❌ Plugin not responding"
	@echo ""
	@echo "Search Test:"
	@curl -s "http://127.0.0.1:9999/search-game?title=Pac-Man" | python3 -m json.tool || echo "❌ Search failed"

# ================================
# Installation
# ================================

install:
	@echo "📦 Installing all dependencies..."
	npm run install:all

install-python:
	@echo "🐍 Installing Python dependencies..."
	@cd backend && pip install -r requirements.txt

install-node:
	@echo "📦 Installing Node dependencies..."
	@npm install
	@cd frontend && npm install
	@cd gateway && npm install

# ================================
# Testing
# ================================

test:
	@echo "🧪 Running all tests..."
	npm test

test-frontend:
	@echo "🎨 Testing frontend..."
	@cd frontend && npm test

test-backend:
	@echo "🐍 Testing backend..."
	@cd backend && pytest

test-gateway:
	@echo "🔌 Testing gateway..."
	npm run test:health
	npm run test:fastapi

# ================================
# Utility Commands
# ================================

clean:
	@echo "🧹 Cleaning build artifacts..."
	@rm -rf frontend/dist
	@rm -rf frontend/node_modules/.vite
	@rm -rf backend/__pycache__
	@rm -rf backend/**/__pycache__
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Clean complete"

verify-env:
	@echo "🔍 Verifying environment..."
	@if [ ! -f .env ]; then \
		echo "❌ .env file not found!"; \
		echo "Run 'make setup' first"; \
		exit 1; \
	fi
	@echo "✅ .env file found"
	@# Check for required variables
	@grep -q "AA_DRIVE_ROOT=" .env || (echo "❌ AA_DRIVE_ROOT not set in .env" && exit 1)
	@grep -q "FASTAPI_URL=" .env || (echo "❌ FASTAPI_URL not set in .env" && exit 1)
	@echo "✅ Required variables present"

bootstrap:
	@echo "🤖 Running agent bootstrap validation..."
	@python3 cloud_code/claude_boot.py || node cloud_code/claude_boot.js

# ================================
# Logging & Monitoring
# ================================

logs:
	@echo "📋 Tailing service logs..."
	@tail -f logs/**/*.log 2>/dev/null || echo "No logs found"

logs-agent:
	@echo "🤖 Viewing agent logs..."
	@tail -n 50 logs/agent_calls/$$(date +%Y-%m-%d)_calls.log 2>/dev/null || echo "No agent logs today"

logs-boot:
	@echo "🚀 Viewing boot logs..."
	@tail -n 50 logs/agents/boot-$$(date +%Y%m%d).jsonl 2>/dev/null || echo "No boot logs today"

# ================================
# Smoke Checks
# ================================

smoke:
ifeq ($(OS),Windows)
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-cache.ps1
else
	bash scripts/verify-cache.sh
endif

smoke-no-start:
ifeq ($(OS),Windows)
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-cache.ps1 -NoStart
else
	NOSTART=1 bash scripts/verify-cache.sh
endif

smoke-ps:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-cache.ps1

smoke-sh:
	bash scripts/verify-cache.sh

# Gateway smoke
smoke-gateway:
ifeq ($(OS),Windows)
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-gateway.ps1
else
	bash scripts/verify-gateway.sh
endif

smoke-gateway-no-start:
ifeq ($(OS),Windows)
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-gateway.ps1 -NoStart
else
	NOSTART=1 bash scripts/verify-gateway.sh
endif

# ================================
# Docker Support (Future)
# ================================

docker-build:
	@echo "🐳 Building Docker images..."
	@echo "TODO: Docker support not yet implemented"

docker-up:
	@echo "🐳 Starting Docker containers..."
	@echo "TODO: Docker support not yet implemented"

docker-down:
	@echo "🐳 Stopping Docker containers..."
	@echo "TODO: Docker support not yet implemented"

# ================================
# Production Builds
# ================================

build: clean
	@echo "🏗️ Building for production..."
	npm run build:frontend
	@echo "✅ Production build complete"

build-plugin:
	@echo "🎮 Building LaunchBox plugin..."
	@cd plugin && dotnet build -c Release
	@echo "✅ Plugin built to plugin/bin/Release/"

deploy-plugin: build-plugin
	@echo "📦 Deploying plugin to LaunchBox..."
	@if [ -d "A:/LaunchBox/Plugins" ]; then \
		cp -r plugin/bin/Release/net6.0/* "A:/LaunchBox/Plugins/ArcadeAssistant/"; \
		echo "✅ Plugin deployed"; \
	elif [ -d "/mnt/a/LaunchBox/Plugins" ]; then \
		cp -r plugin/bin/Release/net6.0/* "/mnt/a/LaunchBox/Plugins/ArcadeAssistant/"; \
		echo "✅ Plugin deployed (WSL)"; \
	else \
		echo "❌ LaunchBox directory not found"; \
		exit 1; \
	fi

# ================================
# Database & Migrations (Future)
# ================================

db-init:
	@echo "🗄️ Initializing database..."
	@echo "TODO: Database support not yet implemented"

db-migrate:
	@echo "🗄️ Running migrations..."
	@echo "TODO: Migration support not yet implemented"

# ================================
# Quick Actions
# ================================

quick-start: setup install dev
	@echo "🎉 Quick start complete!"

reset: clean
	@echo "♻️ Resetting development environment..."
	@rm -f .env
	@rm -rf node_modules
	@rm -rf frontend/node_modules
	@rm -rf gateway/node_modules
	@rm -rf backend/__pycache__
	@echo "✅ Reset complete - run 'make setup' to start fresh"

# ================================
# CI/CD Support
# ================================

ci-test: verify-env install test
	@echo "✅ CI tests complete"

ci-build: verify-env install build
	@echo "✅ CI build complete"

# ================================
# Version Management
# ================================

version:
	@echo "📌 Current versions:"
	@echo -n "  Node: " && node --version
	@echo -n "  npm: " && npm --version
	@echo -n "  Python: " && python3 --version
	@grep '"version"' package.json | head -1
	@grep '"version"' frontend/package.json | head -1 | sed 's/^/  Frontend: /'
	@grep '"version"' gateway/package.json 2>/dev/null | head -1 | sed 's/^/  Gateway: /' || echo "  Gateway: No package.json"
# Stack smoke
smoke-stack:
ifeq ($(OS),Windows)
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-stack.ps1
else
	bash scripts/verify-stack.sh
endif

smoke-stack-no-start:
ifeq ($(OS),Windows)
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-stack.ps1 -NoStart
else
	NOSTART=1 bash scripts/verify-stack.sh
endif
