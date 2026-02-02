# Backend Port Standardization - Fix Documentation

## Problem
The backend was frequently starting on inconsistent ports, causing connection failures between the gateway and FastAPI:
- Sometimes port **8888** (old default)
- Sometimes port **8000** (batch file default)
- `.env` configuration didn't match actual running port

## Root Cause
Multiple startup methods with different port configurations:
1. **Batch files** (`start-gui.bat`, `Start-Arcade-Assistant-8787.bat`): Port **8000**
2. **npm script** (`dev-backend.cjs`): Port **8888** (OLD)
3. **Direct Python** (`python backend/app.py`): Port **8888** (OLD)
4. **Python wrapper** (`scripts/start_backend.py`): Port **8000** (via env var)

## Solution Applied

### 1. Standardized on Port 8000
All startup methods now use **port 8000**:

✅ **Updated Files:**
- `scripts/dev-backend.cjs` - Changed from 8888 to 8000
- `backend/app.py` - Changed from 8888 to 8000
- `.env` - Updated `FASTAPI_URL=http://127.0.0.1:8000`

### 2. Created Robust Startup Script
New file: `start-arcade-assistant-robust.bat`

**Features:**
- ✅ Checks for port conflicts (8000, 8787)
- ✅ Offers to kill existing processes
- ✅ Verifies Node.js and Python are installed
- ✅ Validates `.env` configuration
- ✅ Auto-fixes `.env` if FASTAPI_URL is wrong
- ✅ Waits for services to actually start
- ✅ Verifies services are responding before continuing
- ✅ Opens browser only after everything is ready

## How to Use

### Option 1: Robust Startup (Recommended)
```batch
start-arcade-assistant-robust.bat
```
This script will:
1. Clean up any existing processes
2. Verify your environment
3. Fix `.env` if needed
4. Start backend and gateway
5. Verify everything is working
6. Open your browser

### Option 2: Quick Start (Production)
```batch
start-gui.bat
```
Standard production launcher (no dev server)

### Option 3: Development Mode
```batch
npm run dev
```
Starts all services with hot reload (gateway, backend, frontend)

### Option 4: Manual Start
```batch
# Terminal 1: Backend
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000

# Terminal 2: Gateway
cd gateway
node server.js
```

## Port Reference

| Service | Port | URL |
|---------|------|-----|
| FastAPI Backend | 8000 | http://localhost:8000 |
| Gateway | 8787 | http://localhost:8787 |
| Vite Dev Server | 5173 | http://localhost:5173 (dev only) |

## Environment Variables

**Required in `.env`:**
```bash
PORT=8787                              # Gateway port
FASTAPI_URL=http://127.0.0.1:8000     # Backend URL (MUST be 8000)
AA_DRIVE_ROOT=A:\                      # Drive root
```

## Troubleshooting

### Backend won't start
1. Check if port 8000 is already in use:
   ```batch
   netstat -ano | findstr ":8000"
   ```
2. Kill the process:
   ```batch
   taskkill /F /PID <PID>
   ```
3. Run the robust startup script

### Gateway can't connect to backend
1. Verify `.env` has `FASTAPI_URL=http://127.0.0.1:8000`
2. Check backend is running: `curl http://localhost:8000/health`
3. Restart gateway

### "Port mismatch" error
Run `start-arcade-assistant-robust.bat` - it will auto-fix the `.env` file

## Files Modified

1. ✅ `scripts/dev-backend.cjs` - Port 8888 → 8000
2. ✅ `backend/app.py` - Port 8888 → 8000
3. ✅ `.env` - FASTAPI_URL updated to port 8000
4. ✅ `start-arcade-assistant-robust.bat` - NEW robust startup script

## Testing

Verify the fix:
```batch
# 1. Start services
start-arcade-assistant-robust.bat

# 2. Test backend directly
curl http://localhost:8000/health

# 3. Test gateway health (includes backend connection)
curl http://localhost:8787/api/health

# 4. Check ports
netstat -ano | findstr ":8000"
netstat -ano | findstr ":8787"
```

## Future Prevention

**Always use one of these methods to start the backend:**
1. `start-arcade-assistant-robust.bat` (recommended)
2. `start-gui.bat`
3. `npm run dev`
4. `npm run dev:backend` (now uses port 8000)

**Never manually start with:**
- ❌ `python backend/app.py` (unless you verify it uses port 8000)
- ❌ `uvicorn backend.app:app --port 8888` (wrong port!)

---

**Date Fixed:** 2025-12-09  
**Issue:** Recurring backend port mismatch  
**Status:** ✅ RESOLVED
