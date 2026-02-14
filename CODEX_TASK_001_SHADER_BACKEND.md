# Codex Task 001: Shader Management Backend Endpoints

**Assigned:** 2025-12-01
**Priority:** HIGH (First V2 feature, validates entire approach)
**Estimated Time:** 45 minutes
**Dependencies:** None (start here)

---

## **Context**

We're adding shader management to Arcade Assistant V2. This allows LaunchBox LoRa to apply per-game visual shaders (CRT scanlines, LCD grids, etc.) to MAME and RetroArch games via AI conversation.

**Why this matters:**
- Users can say "LoRa, add CRT scanlines to Street Fighter 2"
- LoRa shows preview of shader config change
- User approves, shader applies with automatic backup
- Reuses proven preview/apply/revert pattern from LED Blinky and Controller Chuck

**This task:** Build the backend REST endpoints that will power shader management.

---

## **Files to Modify**

### **Primary File:**
- `backend/routers/launchbox.py` (add 5 new endpoints)

### **Related Files (reference only, don't modify yet):**
- `backend/constants/a_drive_paths.py` (already has emulator paths)
- `backend/models/emulator_config.py` (might need ShaderConfig model)

---

## **Step-by-Step Instructions**

### **Step 1: Add Pydantic Models (top of file)**

Add these data models after existing imports:

```python
from pydantic import BaseModel
from typing import Literal, Optional, Dict, Any

class ShaderChangeRequest(BaseModel):
    """Request to change shader for a specific game."""
    game_id: str
    shader_name: str
    emulator: Literal["mame", "retroarch"]
    parameters: Optional[Dict[str, Any]] = None  # Future: custom shader params

class ShaderConfig(BaseModel):
    """Stored shader configuration for a game."""
    game_id: str
    shader_name: str
    emulator: str
    shader_path: str
    parameters: Dict[str, Any] = {}
    applied_at: str  # ISO timestamp
```

---

### **Step 2: Add Shader Discovery Function**

Add this helper function to scan for installed shaders:

```python
import os
from pathlib import Path
from backend.constants.a_drive_paths import AA_DRIVE_ROOT

def get_available_shaders() -> Dict[str, list]:
    """Scan A: drive for installed shader presets."""
    shaders = {
        "mame": [],
        "retroarch": []
    }

    # MAME shaders: A:\Emulators\MAME\shaders\*.fx
    mame_shader_dir = Path(AA_DRIVE_ROOT) / "Emulators" / "MAME" / "shaders"
    if mame_shader_dir.exists():
        for shader_file in mame_shader_dir.glob("*.fx"):
            shaders["mame"].append({
                "name": shader_file.stem,
                "path": str(shader_file),
                "type": "hlsl"
            })

    # RetroArch shaders: A:\Emulators\RetroArch\shaders\*.slangp
    retroarch_shader_dir = Path(AA_DRIVE_ROOT) / "Emulators" / "RetroArch" / "shaders"
    if retroarch_shader_dir.exists():
        for shader_file in retroarch_shader_dir.glob("*.slangp"):
            shaders["retroarch"].append({
                "name": shader_file.stem,
                "path": str(shader_file),
                "type": "slang"
            })

    return shaders
```

---

### **Step 3: Add GET /shaders/available Endpoint**

```python
@router.get("/shaders/available")
async def get_shaders_available():
    """
    List all installed shader presets for MAME and RetroArch.

    Returns:
        {
            "mame": [{"name": "crt-royale", "path": "A:\\...", "type": "hlsl"}],
            "retroarch": [{"name": "crt-easy", "path": "A:\\...", "type": "slang"}]
        }
    """
    try:
        shaders = get_available_shaders()
        logger.info(f"[Shaders] Found {len(shaders['mame'])} MAME + {len(shaders['retroarch'])} RetroArch shaders")
        return shaders
    except Exception as e:
        logger.error(f"[Shaders] Failed to scan shaders: {e}")
        return {"mame": [], "retroarch": [], "error": str(e)}
```

---

### **Step 4: Add GET /shaders/game/{game_id} Endpoint**

```python
@router.get("/shaders/game/{game_id}")
async def get_game_shader(game_id: str):
    """
    Get current shader config for specific game.

    Args:
        game_id: LaunchBox game ID (e.g., "sf2")

    Returns:
        ShaderConfig if exists, else {"shader": null}
    """
    config_path = Path("configs") / "shaders" / "games" / f"{game_id}.json"

    if config_path.exists():
        import json
        with open(config_path, 'r') as f:
            config = json.load(f)
        logger.info(f"[Shaders] Loaded config for {game_id}: {config['shader_name']}")
        return config
    else:
        logger.info(f"[Shaders] No shader configured for {game_id}")
        return {"game_id": game_id, "shader": None}
```

---

### **Step 5: Add POST /shaders/preview Endpoint**

This is the most important endpoint - it shows the diff before applying:

```python
@router.post("/shaders/preview")
async def preview_shader_change(request: ShaderChangeRequest):
    """
    Preview shader config change with diff (old vs new).

    Args:
        request: ShaderChangeRequest with game_id, shader_name, emulator

    Returns:
        {
            "old": {...},  # Current config or null
            "new": {...},  # Proposed config
            "diff": "..."  # Human-readable diff
        }
    """
    config_path = Path("configs") / "shaders" / "games" / f"{request.game_id}.json"

    # Get current config (if exists)
    if config_path.exists():
        import json
        with open(config_path, 'r') as f:
            old_config = json.load(f)
    else:
        old_config = None

    # Build new config
    from datetime import datetime
    shaders = get_available_shaders()
    shader_list = shaders.get(request.emulator, [])
    shader_obj = next((s for s in shader_list if s['name'] == request.shader_name), None)

    if not shader_obj:
        return {
            "error": f"Shader '{request.shader_name}' not found for {request.emulator}",
            "available": [s['name'] for s in shader_list]
        }

    new_config = {
        "game_id": request.game_id,
        "shader_name": request.shader_name,
        "emulator": request.emulator,
        "shader_path": shader_obj['path'],
        "parameters": request.parameters or {},
        "applied_at": datetime.utcnow().isoformat()
    }

    # Generate diff
    if old_config:
        diff = f"Change shader from '{old_config['shader_name']}' to '{new_config['shader_name']}'"
    else:
        diff = f"Add new shader '{new_config['shader_name']}' for {request.game_id}"

    logger.info(f"[Shaders] Preview: {diff}")
    return {
        "old": old_config,
        "new": new_config,
        "diff": diff
    }
```

---

### **Step 6: Add POST /shaders/apply Endpoint**

This applies the change with automatic backup:

```python
@router.post("/shaders/apply")
async def apply_shader_change(request: ShaderChangeRequest):
    """
    Apply shader config with automatic backup.

    Args:
        request: ShaderChangeRequest

    Returns:
        {"success": true, "backup_path": "..."}
    """
    import json
    from datetime import datetime
    from backend.services.policies import log_change  # Reuse existing backup system

    config_path = Path("configs") / "shaders" / "games" / f"{request.game_id}.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Backup existing config (if exists)
    backup_path = None
    if config_path.exists():
        backup_dir = Path("backups") / datetime.now().strftime("%Y%m%d")
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{request.game_id}_shader_{datetime.now().strftime('%H%M%S')}.json"

        import shutil
        shutil.copy(config_path, backup_path)
        logger.info(f"[Shaders] Backed up to {backup_path}")

    # Build and write new config
    shaders = get_available_shaders()
    shader_list = shaders.get(request.emulator, [])
    shader_obj = next((s for s in shader_list if s['name'] == request.shader_name), None)

    if not shader_obj:
        return {"success": False, "error": f"Shader '{request.shader_name}' not found"}

    new_config = {
        "game_id": request.game_id,
        "shader_name": request.shader_name,
        "emulator": request.emulator,
        "shader_path": shader_obj['path'],
        "parameters": request.parameters or {},
        "applied_at": datetime.utcnow().isoformat()
    }

    with open(config_path, 'w') as f:
        json.dump(new_config, f, indent=2)

    # Log change
    log_change(
        operation="shader_apply",
        file_path=str(config_path),
        backup_path=str(backup_path) if backup_path else None,
        details={"game_id": request.game_id, "shader": request.shader_name}
    )

    logger.info(f"[Shaders] Applied {request.shader_name} to {request.game_id}")
    return {
        "success": True,
        "backup_path": str(backup_path) if backup_path else None,
        "config_path": str(config_path)
    }
```

---

### **Step 7: Add POST /shaders/revert Endpoint**

```python
@router.post("/shaders/revert")
async def revert_shader_change(backup_path: str):
    """
    Rollback to previous shader config from backup.

    Args:
        backup_path: Path to backup file (from apply response)

    Returns:
        {"success": true, "restored_from": "..."}
    """
    import json
    import shutil

    backup = Path(backup_path)
    if not backup.exists():
        return {"success": False, "error": f"Backup not found: {backup_path}"}

    # Extract game_id from backup filename
    game_id = backup.stem.split('_shader_')[0]
    config_path = Path("configs") / "shaders" / "games" / f"{game_id}.json"

    # Restore backup
    shutil.copy(backup, config_path)

    logger.info(f"[Shaders] Reverted {game_id} from {backup_path}")
    return {
        "success": True,
        "restored_from": backup_path,
        "config_path": str(config_path)
    }
```

---

## **Expected Outcome**

After completing this task, you should be able to:

1. **GET /api/launchbox/shaders/available**
   - Returns list of MAME shaders (e.g., crt-royale.fx)
   - Returns list of RetroArch shaders (e.g., crt-easy.slangp)

2. **GET /api/launchbox/shaders/game/sf2**
   - Returns current shader config for Street Fighter 2
   - Or returns `{"shader": null}` if no shader configured

3. **POST /api/launchbox/shaders/preview**
   ```json
   {
     "game_id": "sf2",
     "shader_name": "crt-royale",
     "emulator": "mame"
   }
   ```
   - Returns old vs new config diff

4. **POST /api/launchbox/shaders/apply**
   - Writes config to `configs/shaders/games/sf2.json`
   - Creates backup in `backups/YYYYMMDD/`
   - Logs change to `logs/changes.jsonl`

5. **POST /api/launchbox/shaders/revert**
   - Restores from backup path
   - Game reverts to previous shader

---

## **Testing**

### **Test with curl:**

```bash
# 1. List available shaders
curl http://localhost:8888/api/launchbox/shaders/available

# Expected: JSON with mame and retroarch shader arrays

# 2. Check current shader for sf2
curl http://localhost:8888/api/launchbox/shaders/game/sf2

# Expected: {"game_id": "sf2", "shader": null} (first time)

# 3. Preview shader change
curl -X POST http://localhost:8888/api/launchbox/shaders/preview \
  -H "Content-Type: application/json" \
  -d '{"game_id":"sf2","shader_name":"crt-royale","emulator":"mame"}'

# Expected: {"old": null, "new": {...}, "diff": "Add new shader..."}

# 4. Apply shader
curl -X POST http://localhost:8888/api/launchbox/shaders/apply \
  -H "Content-Type: application/json" \
  -d '{"game_id":"sf2","shader_name":"crt-royale","emulator":"mame"}'

# Expected: {"success": true, "backup_path": "backups/20251201/..."}

# 5. Verify file created
cat configs/shaders/games/sf2.json

# Expected: JSON with shader config

# 6. Revert shader
curl -X POST http://localhost:8888/api/launchbox/shaders/revert \
  -H "Content-Type: application/json" \
  -d '{"backup_path":"backups/20251201/sf2_shader_123456.json"}'

# Expected: {"success": true, "restored_from": "..."}
```

### **Validation Checklist:**
- ✅ All 5 endpoints return valid JSON
- ✅ Preview shows diff before applying
- ✅ Apply creates backup automatically
- ✅ Backup file exists in `backups/YYYYMMDD/`
- ✅ Change logged in `logs/changes.jsonl`
- ✅ Revert restores previous config
- ✅ No crashes or 500 errors

---

## **Common Issues to Watch For**

### **Issue 1: Shader directory doesn't exist**
- **Symptom:** `get_available_shaders()` returns empty arrays
- **Fix:** Check if `A:\Emulators\MAME\shaders\` exists
- **Workaround:** Create directory and add sample .fx file for testing

### **Issue 2: Permission denied writing to configs/**
- **Symptom:** `apply_shader_change()` fails with permission error
- **Fix:** Run backend with proper permissions
- **Workaround:** Change config path to writable location (temp for testing)

### **Issue 3: log_change function not found**
- **Symptom:** Import error for `backend.services.policies`
- **Fix:** Check if policies.py has log_change function
- **Workaround:** Comment out log_change call temporarily, add TODO

---

## **Dependencies for This Task**

**Python Packages (should already be installed):**
- `fastapi`
- `pydantic`
- `pathlib` (standard library)
- `json` (standard library)
- `shutil` (standard library)

**File System Requirements:**
- Write access to `configs/shaders/games/`
- Write access to `backups/YYYYMMDD/`
- Write access to `logs/changes.jsonl`

**Existing Code Dependencies:**
- `backend.constants.a_drive_paths.AA_DRIVE_ROOT` (should exist)
- `backend.services.policies.log_change` (might need to add if missing)

---

## **Next Task After This**

Once this backend is complete and tested, the next task will be:

**Task 002: Gateway Shader Proxy**
- Add proxy routes in `gateway/routes/launchboxProxy.js`
- Forward requests from frontend to backend with headers
- Estimated time: 15 minutes

---

## **Questions? Issues?**

If you encounter any blockers:
1. Document the exact error message
2. Note which file/line number
3. Include your attempted fix (if any)
4. Report back via status update markdown

**Status Update Template:** See `V2_STATUS_TEMPLATE.md`

---

**Codex - you've got this! This is a straightforward CRUD API following patterns we've used many times before. Start with Step 1 and work through sequentially. Test each endpoint as you go. Good luck! 🚀**
