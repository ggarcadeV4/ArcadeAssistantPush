# Phase 1: Architectural Fixes - Todo List

**Status:** 🔵 Ready to Start
**Priority:** P0 - Critical (Security & Architecture)
**Estimated Time:** 3 sessions (3-6 hours total)
**Started:** _____
**Completed:** _____

---

## Overview

Phase 1 focuses on critical architectural fixes that must be completed before proceeding with panel development. These fixes address security vulnerabilities, path inconsistencies, and offline resilience.

**Prerequisites:**
- ✅ Phase 0 complete (Environment Setup)
- ✅ Services running (Gateway, Backend, Frontend)
- ✅ Dependencies installed

**Success Criteria:**
- Gateway has ZERO direct file writes (all proxied to Backend)
- All LaunchBox paths corrected to `A:\LaunchBox` (not `A:\Arcade Assistant\LaunchBox`)
- Backend returns 501 (not 500) when API keys missing
- Frontend handles offline mode gracefully
- No CORS errors with `x-device-id` header

---

## Session 1.1: Gateway Routing Fix (P0 - Security)

**Goal:** Remove all direct file system operations from Gateway; proxy to Backend instead.

**Context:** Gateway currently performs direct file writes for config operations, violating the three-tier security model. All file operations must go through Backend with proper validation, backups, and audit logging.

### Tasks

#### 1. Audit Current Gateway File Operations
- [ ] Search for `fs.writeFile`, `fs.writeFileSync`, `fs.appendFile` in `gateway/routes/`
- [ ] Search for `fs.unlink`, `fs.unlinkSync`, `fs.rmdir` in `gateway/routes/`
- [ ] Document all locations where Gateway writes directly to disk
- [ ] Create audit report: `GATEWAY_FILE_OPS_AUDIT.md`

**Command:**
```bash
cd gateway
grep -r "fs\.write" routes/
grep -r "fs\.unlink" routes/
grep -r "fs\.rmdir" routes/
```

#### 2. Create Backend Config Router
- [ ] Create `backend/routers/config.py` with FastAPI routes
- [ ] Implement `POST /api/config/preview` - Preview config changes with diff
- [ ] Implement `POST /api/config/apply` - Apply config with automatic backup
- [ ] Implement `POST /api/config/restore` - Restore from backup
- [ ] Implement `GET /api/config/backups` - List available backups
- [ ] Add Pydantic models for request/response validation
- [ ] Use existing `backend/services/policies.py` for path validation

**File:** `backend/routers/config.py`

**Example Route:**
```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.policies import is_allowed_file
from backend.services.backup_manager import create_backup
import json

router = APIRouter(prefix="/api/config", tags=["config"])

class ConfigPreviewRequest(BaseModel):
    path: str
    content: str
    scope: str = "config"

class ConfigApplyRequest(BaseModel):
    path: str
    content: str
    scope: str = "config"
    backup: bool = True

@router.post("/preview")
async def preview_config(request: ConfigPreviewRequest):
    """Preview config changes with diff."""
    if not is_allowed_file(request.path, request.scope):
        raise HTTPException(403, "Path not sanctioned")

    # Read current content
    try:
        with open(request.path, 'r') as f:
            current = f.read()
    except FileNotFoundError:
        current = ""

    # Generate diff (use difflib)
    import difflib
    diff = list(difflib.unified_diff(
        current.splitlines(keepends=True),
        request.content.splitlines(keepends=True),
        fromfile="current",
        tofile="proposed"
    ))

    return {
        "path": request.path,
        "current": current,
        "proposed": request.content,
        "diff": "".join(diff)
    }

@router.post("/apply")
async def apply_config(request: ConfigApplyRequest):
    """Apply config changes with automatic backup."""
    if not is_allowed_file(request.path, request.scope):
        raise HTTPException(403, "Path not sanctioned")

    # Create backup if requested
    backup_path = None
    if request.backup:
        backup_path = create_backup(request.path)

    # Write new content
    try:
        with open(request.path, 'w') as f:
            f.write(request.content)
    except Exception as e:
        raise HTTPException(500, f"Write failed: {str(e)}")

    # Log to audit trail
    log_config_change(request.path, backup_path)

    return {
        "success": True,
        "path": request.path,
        "backup_path": backup_path
    }
```

#### 3. Update Gateway to Proxy Config Operations
- [ ] Update `gateway/routes/config.js` to proxy to Backend
- [ ] Replace all `fs.writeFile` calls with fetch to `POST /api/config/apply`
- [ ] Remove all direct file system imports (`fs`, `path` for writes)
- [ ] Keep read-only operations if needed (but prefer Backend for consistency)
- [ ] Add error handling for Backend failures

**File:** `gateway/routes/config.js`

**Example Proxy:**
```javascript
const express = require('express')
const router = express.Router()

// Proxy to Backend for config operations
router.post('/preview', async (req, res) => {
  try {
    const response = await fetch(`${process.env.FASTAPI_URL}/api/config/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body)
    })
    const data = await response.json()
    res.json(data)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

router.post('/apply', async (req, res) => {
  try {
    const response = await fetch(`${process.env.FASTAPI_URL}/api/config/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body)
    })
    const data = await response.json()
    res.json(data)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

module.exports = router
```

#### 4. Register Backend Router
- [ ] Import config router in `backend/app.py`
- [ ] Register with `app.include_router(config.router)`
- [ ] Verify OpenAPI docs show new routes at `/docs`
- [ ] Test routes with curl or Postman

**File:** `backend/app.py`

#### 5. Testing & Validation
- [ ] Test config change from LED Blinky panel UI
- [ ] Verify preview shows correct diff
- [ ] Verify apply creates backup in `backups/YYYYMMDD/`
- [ ] Verify audit log entry in `logs/changes.jsonl`
- [ ] Test restore functionality
- [ ] Check Gateway logs - should show NO direct file writes
- [ ] Run: `grep "fs.write" gateway/routes/*.js` - should return NOTHING

**Acceptance Criteria:**
- ✅ All config operations proxy through Backend
- ✅ Backups created automatically in `backups/YYYYMMDD/`
- ✅ Audit log entries in `logs/changes.jsonl`
- ✅ Restore functionality works
- ✅ Gateway has ZERO direct file writes (`grep` returns nothing)

---

## Session 1.2: Path Drift Correction (P0)

**Goal:** Fix all incorrect LaunchBox paths throughout codebase.

**Context:** Some code references `A:\Arcade Assistant\LaunchBox` but the actual path is `A:\LaunchBox`. This causes file-not-found errors. See `LAUNCHBOX_PREFLIGHT_REPORT.json` for analysis.

### Tasks

#### 1. Search for Incorrect Paths
- [ ] Search for `A:\\Arcade Assistant\\LaunchBox` in all backend files
- [ ] Search for `A:/Arcade Assistant/LaunchBox` (forward slash variant)
- [ ] Search for `Arcade Assistant/LaunchBox` (relative variant)
- [ ] Document all occurrences in `PATH_DRIFT_AUDIT.md`

**Commands:**
```bash
cd backend
grep -r "Arcade Assistant\\\\LaunchBox" .
grep -r "Arcade Assistant/LaunchBox" .
grep -r "ARCADE_ASSISTANT" .

cd ../gateway
grep -r "Arcade Assistant" .

cd ../frontend
grep -r "Arcade Assistant" src/
```

#### 2. Update Backend Paths
- [ ] Update `backend/constants/a_drive_paths.py` if it exists
- [ ] Update `backend/services/launchbox_*.py` files
- [ ] Update `backend/routers/launchbox*.py` files
- [ ] Replace all occurrences with `A:\\LaunchBox` (correct path)
- [ ] Use environment variable `LAUNCHBOX_ROOT` if available

**Correct Path:**
```python
LAUNCHBOX_ROOT = os.getenv('LAUNCHBOX_ROOT', 'A:\\LaunchBox')  # NOT "A:\\Arcade Assistant\\LaunchBox"
```

#### 3. Update Gateway Paths
- [ ] Update any LaunchBox path references in `gateway/`
- [ ] Update proxy routes if they construct paths
- [ ] Ensure paths passed to Backend are correct

#### 4. Update Frontend Constants
- [ ] Check `frontend/src/constants/paths.js` if it exists
- [ ] Update any hardcoded LaunchBox paths
- [ ] Ensure UI displays correct paths

#### 5. Verify with LaunchBox LoRa Panel
- [ ] Start services (`npm run dev`)
- [ ] Navigate to LaunchBox LoRa panel
- [ ] Attempt to load game library
- [ ] Check Backend logs for "file not found" errors
- [ ] Attempt to launch a non-MAME game (e.g., Atari 2600)
- [ ] Verify ROM path resolution works

**Acceptance Criteria:**
- ✅ All backend paths updated to `A:\LaunchBox`
- ✅ `grep` searches return ZERO results for old path
- ✅ LaunchBox LoRa panel loads game library without errors
- ✅ No "file not found" errors in logs
- ✅ Game metadata parsing works correctly

---

## Session 1.3: CORS & Offline Hardening (P0)

**Goal:** Fix CORS headers and improve offline mode graceful degradation.

**Context:** Backend AI routes should return 501 (Not Implemented) when API keys are missing, not 500 (Internal Server Error). Frontend should handle this gracefully. Also, `x-device-id` header needs to be in CORS allowedHeaders.

### Tasks

#### 1. Update Gateway CORS Configuration
- [ ] Open `gateway/server.js` or wherever CORS is configured
- [ ] Add `x-device-id` to `allowedHeaders` array
- [ ] Add `x-scope` if not already present
- [ ] Verify `Access-Control-Allow-Headers` includes both

**File:** `gateway/server.js` (or `gateway/middleware/cors.js`)

**Example:**
```javascript
const cors = require('cors')

app.use(cors({
  origin: 'http://localhost:8787',
  credentials: true,
  allowedHeaders: [
    'Content-Type',
    'Authorization',
    'x-device-id',  // ADD THIS
    'x-scope'       // VERIFY THIS EXISTS
  ]
}))
```

#### 2. Fix Backend AI Route Error Handling
- [ ] Find AI chat route (likely `backend/routers/ai.py` or similar)
- [ ] Check for missing API key detection
- [ ] Change HTTP status from 500 to 501 when keys missing
- [ ] Add clear error message: "AI service not configured (missing API key)"

**File:** `backend/routers/ai.py`

**Example:**
```python
@router.post("/chat")
async def ai_chat(request: ChatRequest):
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")

    if not api_key:
        # Return 501 Not Implemented, not 500 Internal Server Error
        raise HTTPException(
            status_code=501,  # NOT 500
            detail="AI service not configured (missing API key)"
        )

    # ... rest of chat logic
```

#### 3. Update Frontend AI Client Error Handling
- [ ] Open `frontend/src/services/aiClient.js`
- [ ] Add handler for 501 status code
- [ ] Display user-friendly message: "AI features unavailable (offline mode)"
- [ ] Prevent retry loops on 501 (it's permanent, not transient)

**File:** `frontend/src/services/aiClient.js`

**Example:**
```javascript
async function chat(message) {
  try {
    const response = await fetch('/api/ai/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-device-id': getDeviceId(),
        'x-scope': 'state'
      },
      body: JSON.stringify({ message })
    })

    if (response.status === 501) {
      // AI service not configured - don't retry
      return {
        error: true,
        message: "AI features unavailable (offline mode)",
        offline: true
      }
    }

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    return await response.json()
  } catch (error) {
    console.error('AI chat error:', error)
    return { error: true, message: error.message }
  }
}
```

#### 4. Update Panel UIs for Offline Mode
- [ ] Update LED Blinky panel to show "AI unavailable" when 501
- [ ] Update Voice panel to disable AI features when 501
- [ ] Update Dewey panel to show offline message when 501
- [ ] Use consistent messaging across panels

**Example UI:**
```jsx
{aiOffline && (
  <div className="offline-banner">
    ⚠️ AI features unavailable (offline mode)
  </div>
)}
```

#### 5. Testing & Validation
- [ ] Test config request with `x-device-id` header (should not get CORS error)
- [ ] Remove `ANTHROPIC_API_KEY` from `.env` temporarily
- [ ] Restart Backend
- [ ] Test AI chat request - should get 501 response
- [ ] Verify Frontend shows "offline mode" message
- [ ] Verify no CORS errors in browser console
- [ ] Verify no retry loops on 501 status
- [ ] Restore API key after testing

**Acceptance Criteria:**
- ✅ `x-device-id` in CORS allowedHeaders
- ✅ Backend returns 501 (not 500) when API keys missing
- ✅ Frontend handles 501 gracefully with user-friendly message
- ✅ No CORS errors in console
- ✅ No retry loops on 501 status
- ✅ Offline mode clearly indicated in UI

---

## Phase 1 Completion Checklist

### Before Starting
- [ ] Phase 0 complete (services running)
- [ ] `COMPLETION_PROGRESS.md` updated
- [ ] Git branch created: `git checkout -b phase-1-architectural-fixes`

### Session 1.1 Complete
- [ ] Gateway has zero direct file writes
- [ ] Backend config router implemented
- [ ] Gateway proxies to Backend
- [ ] Backups created automatically
- [ ] Audit log working
- [ ] Tests passing

### Session 1.2 Complete
- [ ] All paths updated to `A:\LaunchBox`
- [ ] No grep results for old path
- [ ] LaunchBox LoRa loads without errors
- [ ] Game metadata parsing works

### Session 1.3 Complete
- [ ] CORS headers updated
- [ ] Backend returns 501 when offline
- [ ] Frontend handles 501 gracefully
- [ ] No CORS errors
- [ ] Offline mode tested

### After Completion
- [ ] Update `COMPLETION_PROGRESS.md` - mark Phase 1 complete
- [ ] Update README.md with session log
- [ ] Create git commits (one per session)
- [ ] Create `PHASE_2_TODO.md` for ScoreKeeper Sam
- [ ] Ready to start Phase 3 (Controller Panels) or Phase 2 (ScoreKeeper)

---

## Testing Scripts

### Test Gateway File Operations Audit
```bash
# Should return NOTHING after Session 1.1
cd gateway
grep -r "fs\.write" routes/
grep -r "fs\.unlink" routes/
```

### Test Path Correction
```bash
# Should return NOTHING after Session 1.2
cd backend
grep -r "Arcade Assistant\\\\LaunchBox" .
grep -r "Arcade Assistant/LaunchBox" .
```

### Test CORS Headers
```bash
# Should include x-device-id in response
curl -X OPTIONS http://localhost:8787/api/config/preview \
  -H "Origin: http://localhost:8787" \
  -H "Access-Control-Request-Headers: x-device-id" \
  -v
```

### Test Offline Mode
```bash
# Should return 501 Not Implemented
curl -X POST http://localhost:8000/api/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}' \
  -w "\nHTTP Status: %{http_code}\n"
```

---

## Common Issues & Solutions

### Issue: Backend config router returns 403 "Path not sanctioned"
**Solution:** Ensure path is in sanctioned areas. Check `backend/services/policies.py` and manifest files.

### Issue: Gateway still has direct file writes after Session 1.1
**Solution:** Search for all fs operations: `grep -r "require('fs')" gateway/routes/`

### Issue: LaunchBox paths still incorrect after Session 1.2
**Solution:** Check environment variables: `echo $LAUNCHBOX_ROOT` or `.env` file

### Issue: CORS errors persist after updating headers
**Solution:** Restart Gateway after CORS config changes

### Issue: Frontend doesn't show offline message
**Solution:** Check AI client error handling and ensure 501 status is checked

---

## Next Phase Preview

After Phase 1 completion, you can choose:

**Option A: Phase 3 - Controller Panels (9th panel)**
- Complete Controller Chuck GUI fixes
- Implement Controller Wizard
- Achieve 9/9 panels complete

**Option B: Phase 2 - ScoreKeeper Sam (8th panel)**
- Design Supabase schema
- Implement backend routes
- Create frontend panel
- Achieve 8/9 panels complete

**Recommended:** Phase 3 first (GUI fixes easier than full Supabase integration)

---

**Last Updated:** 2025-10-23
**Phase 1 Status:** Ready to Start
**Estimated Completion:** 3-6 hours across 3 sessions
