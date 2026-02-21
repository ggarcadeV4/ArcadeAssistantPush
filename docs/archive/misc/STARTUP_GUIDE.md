# 🚀 Arcade Assistant - Startup Scripts Guide

## Quick Start (Choose One)

### 🎯 **Recommended: Robust Startup**
```batch
start-arcade-assistant-robust.bat
```
**Best for:** First-time setup, troubleshooting, or when things aren't working
- ✅ Auto-detects and fixes port conflicts
- ✅ Validates environment configuration
- ✅ Auto-fixes `.env` if needed
- ✅ Verifies services are actually running
- ✅ Shows clear error messages

---

### ⚡ **Quick Production Start**
```batch
start-gui.bat
```
**Best for:** Daily use when everything is already configured
- Starts backend + gateway
- Serves built frontend from `dist/`
- Opens browser automatically
- Minimal checks

---

### 🛠️ **Development Mode**
```batch
npm run dev
```
**Best for:** Active development with hot reload
- Starts backend (port 8000)
- Starts gateway (port 8787)
- Starts Vite dev server (port 5173)
- Hot reload for all services
- Concurrently runs all three

---

### 🔧 **Development (GUI Launcher)**
```batch
start-dev.bat
```
Same as `npm run dev` but uses the GUI launcher

---

## Port Reference

| Service | Port | URL | Notes |
|---------|------|-----|-------|
| **FastAPI Backend** | 8000 | http://localhost:8000 | Always port 8000 |
| **Gateway** | 8787 | http://localhost:8787 | Main entry point |
| **Vite Dev Server** | 5173 | http://localhost:5173 | Dev mode only |

---

## Common Issues & Solutions

### ❌ "Port already in use"
**Solution:** Use `start-arcade-assistant-robust.bat` - it will offer to kill existing processes

### ❌ "Backend connection failed"
**Solution:** 
1. Check `.env` has `FASTAPI_URL=http://127.0.0.1:8000`
2. Run `start-arcade-assistant-robust.bat` to auto-fix

### ❌ "Services won't start"
**Solution:**
1. Close all Node and Python processes
2. Run `start-arcade-assistant-robust.bat`
3. Check the terminal windows for error messages

---

## Manual Start (Advanced)

If you need to start services manually:

```batch
# Terminal 1: Backend
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000

# Terminal 2: Gateway
cd gateway
node server.js

# Terminal 3 (Optional): Frontend Dev Server
cd frontend
npm run dev
```

---

## Environment Check

Verify your setup:
```batch
# Check Node.js
node --version

# Check Python
python --version

# Check backend is running
curl http://localhost:8000/health

# Check gateway is running
curl http://localhost:8787/api/health

# Check ports
netstat -ano | findstr ":8000"
netstat -ano | findstr ":8787"
```

---

## NPM Scripts Reference

```json
npm run dev              # Start all services (dev mode)
npm run dev:gateway      # Start gateway only
npm run dev:backend      # Start backend only (port 8000)
npm run dev:frontend     # Start Vite dev server only
npm run build:frontend   # Build frontend for production
npm run start            # Start gateway (production)
npm run test:health      # Test gateway health
npm run test:fastapi     # Test backend health
```

---

## Files You Should Know About

- ✅ `start-arcade-assistant-robust.bat` - **Recommended startup script**
- ✅ `start-gui.bat` - Quick production start
- ✅ `start-dev.bat` - Development mode launcher
- ✅ `.env` - Environment configuration (MUST have `FASTAPI_URL=http://127.0.0.1:8000`)
- ✅ `package.json` - NPM scripts
- ✅ `docs/BACKEND_PORT_FIX.md` - Detailed port standardization docs

---

## Need Help?

1. **First time?** → Use `start-arcade-assistant-robust.bat`
2. **Something broken?** → Use `start-arcade-assistant-robust.bat`
3. **Daily use?** → Use `start-gui.bat` or `npm run dev`
4. **Development?** → Use `npm run dev`

---

**Last Updated:** 2025-12-09  
**Port Standard:** All backends use port **8000** (not 8888)
