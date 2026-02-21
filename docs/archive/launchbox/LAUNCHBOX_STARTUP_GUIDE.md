# LaunchBox LoRa - Startup Guide

## The Problem You Just Saw

**Error**: "Failed to execute 'json' on 'Response': Unexpected token '<', "<!DOCTYPE "... is not valid JSON"

**Translation**: The backend wasn't running, so the frontend got an HTML error page instead of JSON data.

---

## How to Actually Start LaunchBox LoRa

### Step 1: Start the Backend (REQUIRED)

Open a terminal in the project directory and run:

```bash
npm run dev:backend
```

**Wait for this message**:
```
✅ LaunchBox cache initialized: {...}
FastAPI backend started successfully
INFO:     Uvicorn running on http://0.0.0.0:8888
```

**What this does**:
- Starts FastAPI backend on port 8888
- Initializes LaunchBox XML parser
- Loads games from A: drive (or mock data if not on A:)
- Exposes API endpoints at `/api/launchbox/*`

### Step 2: Start the Frontend (If Not Already Running)

In a **separate terminal**:

```bash
npm run dev:frontend
```

**OR** if you're using the full stack:

```bash
npm run dev
```

This starts both gateway (port 8787) and frontend (Vite dev server).

### Step 3: Navigate to LaunchBox Panel

1. Open browser to `http://localhost:8787` (or wherever frontend is)
2. Click "LaunchBox LoRa" from home screen
3. Panel should now load games from backend

---

## Troubleshooting

### Error: "Backend returned HTML instead of JSON"

**Cause**: Backend isn't running on port 8888

**Fix**:
```bash
# Terminal 1: Start backend
npm run dev:backend

# Wait for "FastAPI backend started successfully"
# Then refresh the browser
```

### Error: "Failed to fetch"

**Cause**: Network request blocked or wrong port

**Fix**:
1. Check backend is running: `curl http://localhost:8888/api/launchbox/stats`
2. If that works but frontend doesn't, check CORS settings
3. Make sure frontend is hitting correct API endpoints

### Error: "Connection refused"

**Cause**: Nothing listening on port 8888

**Fix**: Start the backend (see Step 1)

### Backend starts but shows "Mock Data"

**Cause**: Not on A: drive or `AA_DRIVE_ROOT` not set

**Fix**:
```bash
# In .env file
AA_DRIVE_ROOT=A:\

# Restart backend
npm run dev:backend
```

---

## Verification Checklist

### ✅ Backend Running
```bash
curl http://localhost:8888/api/launchbox/stats
```

Should return JSON like:
```json
{
  "total_games": 15,
  "platforms_count": 4,
  "genres_count": 7,
  "xml_files_parsed": 0,
  "is_mock_data": true,
  "a_drive_status": "⚠️ Not on A: drive. Using mock data."
}
```

### ✅ Frontend Loading Data

Open browser DevTools (F12) → Network tab

You should see successful requests:
- `GET /api/launchbox/games` → 200 OK
- `GET /api/launchbox/platforms` → 200 OK
- `GET /api/launchbox/genres` → 200 OK
- `GET /api/launchbox/stats` → 200 OK

### ✅ Panel Shows Games

LaunchBox LoRa panel should display:
- List of games (5-15 depending on mock vs real data)
- Genre filter dropdown populated
- Stats tab shows counts
- Launch buttons functional

---

## Quick Reference Commands

```bash
# Start backend only
npm run dev:backend

# Start frontend only (if gateway already running)
npm run dev:frontend

# Start full stack (gateway + backend)
npm run dev

# Test backend health
curl http://localhost:8888/health

# Test LaunchBox stats
curl http://localhost:8888/api/launchbox/stats

# Test LaunchBox games
curl http://localhost:8888/api/launchbox/games?limit=5
```

---

## Why This Happened

The backend and frontend are **separate processes**. Just starting the frontend doesn't automatically start the backend.

**Frontend** (React/Vite) → Makes API requests
**Backend** (FastAPI/Python) → Serves API responses

If backend isn't running, frontend gets 404/502 errors (usually HTML error pages from the gateway), which fail to parse as JSON.

---

## Now Try Again

1. **Open Terminal 1**: `npm run dev:backend`
2. **Wait for "FastAPI backend started successfully"**
3. **Refresh browser**
4. **LaunchBox LoRa should now load**

The error message you saw is now much clearer and tells you exactly what to do.
