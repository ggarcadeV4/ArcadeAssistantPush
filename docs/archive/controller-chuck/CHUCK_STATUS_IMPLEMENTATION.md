# Chuck Status Endpoint Implementation

**Date:** 2025-11-22
**Feature:** GET /api/local/console_wizard/status/chuck
**Status:** ✅ Implemented and verified

## Summary

Implemented a read-only endpoint that reports whether Console Wizard is in sync with Controller Chuck's current mapping hash. This enables the frontend to display a sync status banner when Chuck's mappings have changed.

## Changes Made

### 1. Pydantic Response Model
**File:** `backend/routers/console_wizard.py` (lines 39-42)

```python
class ChuckStatusResponse(BaseModel):
    currentMappingHash: str
    lastSyncedHash: Optional[str]
    isOutOfSync: bool
```

### 2. Service Layer Method
**File:** `backend/services/console_wizard_manager.py` (lines 357-367)

```python
def get_chuck_status(self) -> Dict[str, Any]:
    """Return Chuck sync status with mapping hash comparison."""
    current_hash = self._controls_signature()
    last_synced_hash = self._load_signature()
    is_out_of_sync = (last_synced_hash is None) or (current_hash != last_synced_hash)

    return {
        "currentMappingHash": current_hash,
        "lastSyncedHash": last_synced_hash,
        "isOutOfSync": is_out_of_sync,
    }
```

**Logic:**
- Computes `currentMappingHash` from `config/mappings/controls.json` using SHA256
- Reads `lastSyncedHash` from `state/console_wizard/controls_signature.json`
- Sets `isOutOfSync = true` if:
  - Never synced before (`lastSyncedHash` is null), OR
  - Current hash differs from last synced hash

### 3. Router Endpoint
**File:** `backend/routers/console_wizard.py` (lines 124-136)

```python
@router.get("/status/chuck", response_model=ChuckStatusResponse)
async def chuck_status(request: Request):
    """Check if Console Wizard is in sync with Controller Chuck mappings (CW-10)."""
    require_scope(request, "state")
    try:
        manager = _manager(request)
        status = manager.get_chuck_status()
        return status
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load Chuck status: {str(exc)}"
        )
```

**Features:**
- Requires `x-scope: state` header (read-only operation)
- Returns structured JSON response
- Proper error handling with detailed messages

## Verification Results

### Unit Test Results
✅ **Service Layer Logic:**
- `get_chuck_status()` method returns correct structure
- `currentMappingHash` computed correctly from controls.json
- `lastSyncedHash` returns null when never synced
- `isOutOfSync` correctly set to `true` when never synced

### Response Schema Validation
✅ **Pydantic Model:**
```json
{
  "properties": {
    "currentMappingHash": {
      "type": "string"
    },
    "lastSyncedHash": {
      "anyOf": [
        {"type": "string"},
        {"type": "null"}
      ]
    },
    "isOutOfSync": {
      "type": "boolean"
    }
  },
  "required": ["currentMappingHash", "lastSyncedHash", "isOutOfSync"]
}
```

## Manual Testing Guide

### Prerequisites
1. Backend must be running:
   ```bash
   npm run dev:backend
   ```
   OR
   ```bash
   cd backend && uvicorn app:app --reload --port 8000
   ```

2. Ensure `.env` has `AA_DRIVE_ROOT` configured

### Test 1: First Request (Never Synced)
```bash
curl -X GET http://127.0.0.1:8000/api/local/console_wizard/status/chuck \
  -H "x-scope: state" \
  -H "Content-Type: application/json"
```

**Expected Response:**
```json
{
  "currentMappingHash": "4ccad60393be7421722976a4205706b502b00e30bf8e5d2a8dc64500cae93f30",
  "lastSyncedHash": null,
  "isOutOfSync": true
}
```

### Test 2: After Sync
```bash
# First, perform a sync
curl -X POST http://127.0.0.1:8000/api/local/console_wizard/sync-from-chuck \
  -H "x-scope: config" \
  -H "Content-Type: application/json" \
  -d '{"force": true}'

# Then check status again
curl -X GET http://127.0.0.1:8000/api/local/console_wizard/status/chuck \
  -H "x-scope: state" \
  -H "Content-Type: application/json"
```

**Expected Response:**
```json
{
  "currentMappingHash": "4ccad60393be7421722976a4205706b502b00e30bf8e5d2a8dc64500cae93f30",
  "lastSyncedHash": "4ccad60393be7421722976a4205706b502b00e30bf8e5d2a8dc64500cae93f30",
  "isOutOfSync": false
}
```

### Test 3: After Chuck Changes Mappings
1. Modify `config/mappings/controls.json`
2. Request status again

**Expected Response:**
```json
{
  "currentMappingHash": "<new-hash>",
  "lastSyncedHash": "<old-hash>",
  "isOutOfSync": true
}
```

### Test 4: Missing x-scope Header
```bash
curl -X GET http://127.0.0.1:8000/api/local/console_wizard/status/chuck
```

**Expected Response:**
```json
{
  "detail": "Missing required x-scope header. Must be one of: config|state|backup"
}
```
Status: `400 Bad Request`

## Gateway Integration

**No changes needed** - Gateway already correctly forwards all `/api/local/console_wizard/*` requests to the backend.

Request flow:
```
Frontend → Gateway → Backend
GET /api/local/console_wizard/status/chuck
```

Gateway preserves:
- HTTP method (GET)
- Headers (`x-scope`, `x-device-id`, etc.)
- Query parameters
- Response body

## Frontend Integration

To enable the Chuck sync status banner, update `ConsoleWizardPanel.jsx`:

```javascript
// Uncomment line 439 and add endpoint call
useEffect(() => {
  const fetchChuckStatus = async () => {
    try {
      const response = await fetchJSON('/api/local/console_wizard/status/chuck', {
        method: 'GET',
        scope: 'state'
      });

      setChuckSyncStatus({
        currentHash: response.currentMappingHash,
        lastSyncedHash: response.lastSyncedHash,
        isOutOfSync: response.isOutOfSync
      });
    } catch (err) {
      console.warn('[ConsoleWizard] Chuck status check failed:', err);
    }
  };

  fetchChuckStatus();
}, []);

// Show banner when isOutOfSync is true
{chuckSyncStatus?.isOutOfSync && (
  <div className="sync-banner warning">
    Controller mappings have changed.
    <button onClick={handleSyncFromChuck}>Sync Now</button>
  </div>
)}
```

## API Contract

### Request
- **Method:** GET
- **Path:** `/api/local/console_wizard/status/chuck`
- **Headers:**
  - `x-scope: state` (required)
  - `x-device-id: <uuid>` (optional, for tracking)

### Response
- **Status:** 200 OK
- **Content-Type:** application/json
- **Body:**
  ```typescript
  {
    currentMappingHash: string;    // SHA256 hash of current controls.json
    lastSyncedHash: string | null; // Last synced hash, null if never synced
    isOutOfSync: boolean;          // true if hashes differ or never synced
  }
  ```

### Error Responses
- **400 Bad Request:** Missing `x-scope` header
- **500 Internal Server Error:** Service failure (e.g., file read error)

## Backwards Compatibility

✅ **Fully backwards compatible:**
- No existing routes modified
- No breaking changes to request/response formats
- Additive-only change
- Gateway routing unchanged
- Frontend continues to work without using this endpoint

## Related Files

### Modified
- `backend/routers/console_wizard.py` - Added model and route
- `backend/services/console_wizard_manager.py` - Added get_chuck_status() method

### Unchanged
- `backend/app.py` - Router registration already in place
- `gateway/routes/consoleWizardProxy.js` - Proxy works for all paths
- `gateway/server.js` - Routing unchanged

### State Files
- `state/console_wizard/controls_signature.json` - Stores last synced hash
  ```json
  {
    "hash": "<sha256-hex>",
    "updated_at": "2025-11-22T12:34:56.789Z"
  }
  ```

## Next Steps

1. ✅ Backend implementation complete
2. ✅ Service layer logic verified
3. ✅ Response schema validated
4. ⏳ Manual testing with running server (pending user verification)
5. ⏳ Frontend integration (enable sync status banner)

## References

- Audit Report: Section 2.1 - Expected `/status/chuck` endpoint
- Audit Report: Section 6D - Recommended fix order (task #4)
- Console Wizard Manager: Lines 498-517 (signature tracking methods)
- Sync From Chuck: Line 354 (stores signature after sync)
