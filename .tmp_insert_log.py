"""
Insert the 2026-04-11 session entry into both README.md and ROLLING_LOG.md.
Handles encoding detection automatically.
"""
import sys, os

repo = r"w:\Arcade Assistant Master Build\Arcade Assistant Local"

NEW_ROLLING_LOG_ENTRY = r"""## 2026-04-11 (Antigravity Session \u2014 Infrastructure Stabilization: Campaigns 1\u20133 + Safety Model Hardening)

**Net Progress**: Completed a full-stack infrastructure stabilization sequence across three campaigns and expanded safety-model coverage on five mutation paths. Gateway enclosure, frontend identity standardization, and backend/gateway path determinism are all closed. The codebase is substantially cleaner and more deterministic than at session start.

### Campaign 1 \u2014 Gateway Enclosure
- Removed direct frontend \u2192 backend `:8000` bypass behavior from active runtime paths.
- Removed direct frontend \u2192 Supabase browser-client usage (`@supabase/supabase-js`, `createClient`, `supabase.from`, `supabase.channel`) from active runtime paths.
- Reconciled backend port drift to the canonical `:8000` contract.
- Added the missing backend websocket termination point for `/api/local/hardware/ws/encoder-events`.
- Removed dead legacy Gunner panel code and cleaned stale backend-port guidance.

### Campaign 2 \u2014 Identity & Device-ID Standardization
- Centralized frontend device identity through `frontend/src/utils/identity.js`.
- Eliminated synthetic frontend device-id fallbacks: `CAB-0001`, `cabinet-001`, `demo_001`, `controller_chuck`, `unknown-device`.
- Removed unsanctioned `localStorage`-based device identity resolution.
- Standardized `x-device-id`, `x-panel`, and `x-scope` header usage across active frontend runtime paths.

### Campaign 3 \u2014 Path Determinism & Root Unification
- Aligned `.env` `AA_DRIVE_ROOT` and `.aa/manifest.json` `drive_root` to exact match (`W:\Arcade Assistant Master Build`).
- Unified sanctioned-path bootstrap defaults through shared constant `DEFAULT_SANCTIONED_PATHS` in `backend/constants/sanctioned_paths.py`, consumed by `startup_manager.py` and `manifest_validator.py`.
- Replaced 15 backend inline `os.getenv("AA_DRIVE_ROOT", ...)` fallbacks with canonical `get_drive_root()` from `backend/constants/drive_root.py`.
- Gateway canonical helpers confirmed correct: `getDriveRoot()`, `requireDriveRoot()`, `resolveDriveRoot()`, `app.locals.driveRoot`. No hardcoded drive literals in any active gateway runtime path.
- 4 low-priority gateway `process.cwd()` shims remain (all guarded with `console.warn`), deferred to Gateway Pass 2.
- WSL compatibility shims (`A:/` \u2192 `/mnt/a/`) in 6 adapters confirmed intentional and acceptable.

### Safety Model Hardening \u2014 Mutation Paths
Hardened additional config/data mutation surfaces to conform to preview/apply/backup/log expectations:
- `POST /api/local/config/restore` \u2014 now creates a fresh pre-restore backup snapshot before overwrite.
- `PUT /api/local/profile/primary` \u2014 now has `POST /api/local/profile/primary/preview`.
- `POST /api/local/controller/cascade/apply` \u2014 now has preview + persistent JSONL audit with device/panel context.
- `POST /api/local/controller/mapping/set` \u2014 now has preview + dry-run support.
- `DELETE /api/scores/reset/{rom_name}` \u2014 now supports dry-run and writes request-aware audit log entries with device/panel context.

### Current Project State
Infrastructure is substantially cleaner than at session start:
- Gateway enclosure is in place.
- Frontend identity drift is removed.
- Root/path determinism is largely unified across backend and gateway.
- Safety-model coverage has expanded on several remaining mutation paths.

### Known Deferred / Backlog
- LaunchBox LoRa GUI regression: light guns and American Laser Games reappeared in the Arcade Assistant GUI, but intended direction is still to keep them deferred from the AA frontend while leaving direct LaunchBox access intact.

### Next Step
- Push this checkpoint to GitHub.
- Boot-test Arcade Assistant.
- Use any runtime regression from real boot as the next task anchor.

---

"""

NEW_README_SECTION = r"""## 2026-04-11 \u2014 Infrastructure Stabilization: Campaigns 1\u20133 + Safety Model Hardening

We completed a major infrastructure-stabilization sequence across Arcade Assistant:

### Campaign 1 \u2014 Gateway Enclosure
- Removed direct frontend backend-bypass behavior.
- Removed direct frontend Supabase browser-client usage from active runtime paths.
- Reconciled backend port drift to the canonical `:8000` contract.
- Added the missing backend websocket termination point for `/api/local/hardware/ws/encoder-events`.
- Removed dead legacy Gunner panel code and cleaned stale backend-port guidance.

### Campaign 2 \u2014 Identity & Device-ID Standardization
- Centralized frontend device identity through `frontend/src/utils/identity.js`.
- Eliminated synthetic frontend device-id fallbacks such as `CAB-0001`, `cabinet-001`, `demo_001`, `controller_chuck`, and `unknown-device`.
- Removed unsanctioned localStorage-based device identity resolution.
- Standardized `x-device-id`, `x-panel`, and `x-scope` header usage across active frontend runtime paths.

### Campaign 3 \u2014 Path Determinism & Root Unification
- Aligned `.env` and `.aa/manifest.json` to the same `AA_DRIVE_ROOT`.
- Unified sanctioned-path bootstrap defaults through a shared constant source.
- Replaced backend and gateway runtime drive-root fallback drift with canonical helpers (`get_drive_root()`, `getDriveRoot()`, `requireDriveRoot()`, `app.locals.driveRoot`).
- Removed scoped hardcoded `A:\` / `W:\...` runtime fallback literals from active backend and gateway paths.

### Safety Model Hardening \u2014 Mutation Paths
Hardened additional config/data mutation surfaces so they better conform to preview/apply/backup/log expectations:
- `POST /api/local/config/restore` \u2014 now creates a fresh pre-restore backup snapshot before overwrite
- `PUT /api/local/profile/primary` \u2014 now has `POST /api/local/profile/primary/preview`
- `POST /api/local/controller/cascade/apply` \u2014 now has preview + persistent JSONL audit with device/panel context
- `POST /api/local/controller/mapping/set` \u2014 now has preview + dry-run support
- `DELETE /api/scores/reset/{rom_name}` \u2014 now supports dry-run and writes request-aware audit log entries with device/panel context

### Current project state
Infrastructure is substantially cleaner than at session start:
- Gateway enclosure is in place
- Frontend identity drift is removed
- Root/path determinism is largely unified
- Safety-model coverage has expanded on several remaining mutation paths

### Known deferred / backlog item
- LaunchBox LoRa GUI regression: light guns and American Laser Games reappeared in the Arcade Assistant GUI, but intended direction is still to keep them deferred from the AA frontend for now while leaving direct LaunchBox access intact.

---

"""


def read_file(path):
    """Read file trying multiple encodings."""
    for enc in ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']:
        try:
            with open(path, 'r', encoding=enc) as f:
                content = f.read()
            return content, enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise RuntimeError(f"Could not read {path} with any encoding")


def write_file(path, content, enc):
    """Write file with given encoding, preserving original line endings."""
    with open(path, 'w', encoding=enc, newline='') as f:
        f.write(content)


def update_rolling_log():
    path = os.path.join(repo, "ROLLING_LOG.md")
    content, enc = read_file(path)
    print(f"ROLLING_LOG: read with {enc}, {len(content)} chars")
    
    # Find first "## 2026-" which is the existing top entry
    marker = "## 2026-04-10"
    idx = content.find(marker)
    if idx < 0:
        # Try without specific date - find any ## after the title
        lines = content.split('\n')
        insert_pos = 0
        for i, line in enumerate(lines):
            stripped = line.strip().replace('\r', '')
            if stripped.startswith('## ') and i > 0:
                # Insert before this line
                insert_pos = sum(len(l) + 1 for l in lines[:i])
                break
        if insert_pos == 0:
            print("ERROR: Could not find insertion point in ROLLING_LOG.md")
            return False
        new_content = content[:insert_pos] + NEW_ROLLING_LOG_ENTRY + content[insert_pos:]
    else:
        new_content = content[:idx] + NEW_ROLLING_LOG_ENTRY + content[idx:]
    
    write_file(path, new_content, enc)
    print(f"ROLLING_LOG: SUCCESS - inserted entry, now {len(new_content)} chars")
    return True


def update_readme():
    path = os.path.join(repo, "README.md")
    content, enc = read_file(path)
    print(f"README: read with {enc}, {len(content)} chars")
    
    # Find "## 2026-04-10" section
    marker = "## 2026-04-10"
    idx = content.find(marker)
    if idx < 0:
        print("ERROR: Could not find '## 2026-04-10' in README.md")
        return False
    
    new_content = content[:idx] + NEW_README_SECTION + content[idx:]
    write_file(path, new_content, enc)
    print(f"README: SUCCESS - inserted section, now {len(new_content)} chars")
    return True


if __name__ == '__main__':
    ok1 = update_rolling_log()
    ok2 = update_readme()
    if ok1 and ok2:
        print("\nBoth files updated successfully.")
    else:
        print("\nSome updates failed - check output above.")
    
    # Self-cleanup
    try:
        os.remove(__file__)
    except:
        pass
