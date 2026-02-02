# GOLDEN DRIVE CONTRACT

> Engineering and Operations Contract for Arcade Assistant  
> Version: 1.0 | Last Updated: 2025-12-12

---

## 1. Purpose and Scope

### What is the Golden Drive?

The **Golden Drive** is the master hard drive containing a complete, verified, production-ready Arcade Assistant installation. It serves as the **source of truth** for all cabinet deployments.

### How It's Used

1. The Golden Drive is prepared and tested on a development machine
2. It is duplicated using a **physical hard drive duplicator** (bit-for-bit clone)
3. Clone drives are installed into arcade cabinets
4. Each cabinet is provisioned with unique identity post-clone

### Why This Contract Exists

Because the drive is cloned bit-for-bit:
- **Every file, setting, and byte is copied exactly**
- **Machine-specific data will be duplicated** unless handled correctly
- **Changes must be deliberate** — there is no "undo" once drives ship

---

## 2. Definitions

| Term | Definition |
|------|------------|
| **Golden Drive** | The master A:\ drive containing the verified Arcade Assistant installation |
| **Clone Drive** | A bit-for-bit copy of the Golden Drive, installed in a cabinet |
| **Cabinet Name** | Human-friendly identifier for a specific arcade cabinet (e.g., "Cabinet-001") |
| **Device ID** | Globally unique machine identifier, assigned post-clone |
| **Fleet Manager** | Desktop application for managing multiple cabinets remotely |
| **Gateway** | Node.js proxy service (port 8787) that routes all API traffic |
| **Backend** | Python FastAPI service (port 8000) that handles business logic |
| **Frontend** | React web UI served through the gateway |

---

## 3. Folder and Runtime Invariants

### Folders That MUST Exist

```
A:\
├── Arcade Assistant Local\    # Repo root — DO NOT RENAME
│   ├── backend\               # Python FastAPI backend
│   ├── frontend\              # React frontend (src + dist)
│   ├── gateway\               # Node.js gateway proxy
│   ├── scripts\               # Helper scripts
│   ├── start-aa.bat           # Production launcher
│   └── stop-aa.bat            # Production shutdown
├── .aa\                       # Runtime data (identity, logs, state)
│   ├── logs\                  # All service logs
│   ├── identity\              # Cabinet identity (post-provisioning)
│   └── outbox\                # Offline event queue
├── LaunchBox\                 # Game library and metadata
├── Tools\                     # Pegasus, RetroFE, utilities
├── Emulators\                 # MAME, RetroArch, etc.
└── Roms\                      # Game ROMs by platform
```

### Folders That MUST NEVER Move

- `A:\Arcade Assistant Local\` — hardcoded in launchers
- `A:\LaunchBox\` — referenced by path constants
- `A:\.aa\` — identity and logging root

### Drive-Letter Expectations

- The system expects to run from **A:\** drive
- All path constants use `A:\` as the root
- Scripts use `%~d0` to derive drive letter dynamically where possible

---

## 4. Startup Contract

### What `start-aa.bat` MUST Do

1. ✅ Start the Python backend (`uvicorn` on port 8000)
2. ✅ Wait for backend to be healthy (port responds)
3. ✅ Start the Node.js gateway (`node server.js` on port 8787)
4. ✅ Wait for gateway to be healthy (port responds)
5. ✅ Open the UI in default browser (`http://127.0.0.1:8787/`)
6. ✅ Write PIDs to allow clean shutdown

### What `stop-aa.bat` MUST Do

1. ✅ Read saved PIDs
2. ✅ Kill only Arcade Assistant processes (python.exe, node.exe with matching PIDs)
3. ✅ Verify ports are released
4. ✅ Be safe to run even if nothing is running

### What "Healthy" Looks Like

| Service | Port | Health Check |
|---------|------|--------------|
| Backend | 8000 | `GET /health` returns 200 |
| Gateway | 8787 | `GET /api/health` returns 200 |
| UI | 8787 | Browser loads without error |

### Startup Failure Checklist

If startup fails:
1. Check `A:\.aa\logs\backend.log` for Python errors
2. Check `A:\.aa\logs\gateway.log` for Node errors
3. Verify no other process is using ports 8000 or 8787
4. Run `stop-aa.bat` and try again

---

## 5. Routing Contract

### Gateway Is The Law

**All frontend requests MUST go through the gateway.**

```
Frontend → Gateway (8787) → Backend (8000)
```

### Why No Direct Backend Access?

- Gateway handles authentication headers
- Gateway provides consistent API surface
- Gateway enables future load balancing / proxying
- Direct backend access will break when architecture evolves

### Exceptions (Explicit Authorization Only)

- Health checks during startup sequencing
- Internal service-to-service calls (documented)

---

## 6. Pause Screen Contract

### What the Pause Screen MUST Do

- ✅ Display current game info (title, platform, player)
- ✅ Show elapsed play time
- ✅ Provide "Resume" and "Exit" options
- ✅ Trigger via configurable hotkey (default: P key)

### Endpoints That MUST Remain Stable

| Endpoint | Purpose |
|----------|---------|
| `GET /api/runtime/state` | Current game state |
| `POST /api/runtime/pause` | Trigger pause |
| `POST /api/runtime/resume` | Resume game |
| `POST /api/runtime/exit` | Exit to frontend |

### Acceptance Checks

- [ ] Pause hotkey triggers overlay
- [ ] Game title displays correctly
- [ ] Resume returns to game
- [ ] Exit closes game and returns to menu

---

## 7. Scorekeeper Contract

### Frontend/Game Context Detection

Scorekeeper Sam MUST know which context it's operating in:

| Context | How Detected | Behavior |
|---------|--------------|----------|
| LaunchBox/LoRa | `x-panel: launchbox` header | LaunchBox profile system |
| Pegasus | `x-panel: pegasus` header | Pegasus metadata context |
| RetroFE | `x-panel: retrofe` header | RetroFE collection context |
| Direct launch | `x-panel: direct` header | Standalone mode |

### The "Chip Mechanism" Concept

Like a membership chip at an arcade:
1. Player inserts profile chip (selects profile)
2. System remembers active player for session
3. Scores attributed to active player
4. Session ends when player exits or times out

### Minimum Guarantees

- ✅ Scores are always logged locally (offline-safe)
- ✅ Player attribution survives game crashes
- ✅ Leaderboards work without network
- ✅ Cloud sync happens when available (outbox pattern)

---

## 8. LED Blinky Contract

### Hardware Detection Requirements

- ✅ System MUST detect LED controller presence on startup
- ✅ System MUST gracefully handle missing hardware
- ✅ UI MUST show hardware status (connected/disconnected)

### Critical Rule

**LED Blinky MUST NOT crash if hardware is missing.**

Fallback behavior:
- Log warning to `A:\.aa\logs\backend.log`
- Show "Hardware not detected" in UI
- Allow configuration without hardware (preview mode)

### Supported Controllers

- Ultimarc PacLED64
- Ultimarc LED-Wiz
- (Others as documented)

---

## 9. Marquee Contract

### Minimum Viable Requirements

- ✅ Display game-specific marquee when game launches
- ✅ Display system/default marquee when browsing
- ✅ Support image and video formats
- ✅ Fallback to default if game-specific asset missing

### Critical Rule

**Marquee service MUST NOT block boot.**

If marquee fails:
- Log error
- Continue without marquee
- Show status in system health

### Defined "Done" State

- [ ] Marquee displays on secondary monitor
- [ ] Correct asset shows for current game
- [ ] Fallback works when asset missing
- [ ] Service recovers from display disconnect

---

## 10. Fleet/Update Contract

### What Is Allowed Today

- ✅ Manual updates via file copy
- ✅ Local configuration changes
- ✅ Identity provisioning post-clone

### What Is Coming (Future)

- 🔜 Fleet Manager assigns updates to cabinets
- 🔜 Cabinet agent checks for updates
- 🔜 Staged rollout with verification
- 🔜 Automatic rollback on failure

### Offline-First Boot Requirement

**Cabinets MUST boot and function fully without network.**

- All core features work offline
- Cloud features show "offline/pending" status
- Events queue in outbox for later sync

### Update Flow (Conceptual)

```
1. Fleet Manager creates release
2. Release uploaded to Supabase storage
3. Cabinet assigned to receive release
4. Cabinet agent downloads to staging folder
5. Agent verifies hash/signature
6. Agent backs up current state
7. Agent applies update
8. Agent runs health check
9. If healthy: report success
   If failed: rollback and report failure
```

---

## 11. Pre-Clone Checklist (Operator Steps)

Before duplicating the Golden Drive:

- [ ] Run `stop-aa.bat` — ensure nothing is running
- [ ] Delete `A:\.aa\identity\` folder (will be regenerated per-cabinet)
- [ ] Delete `A:\.aa\logs\*` (optional, for clean logs)
- [ ] Clear browser data/cache if stored on drive
- [ ] Verify no personal/test data in configs
- [ ] Run `start-aa.bat` — confirm healthy startup
- [ ] Run `stop-aa.bat` — confirm clean shutdown
- [ ] Drive is ready for duplication

---

## 12. Post-Clone Verification Checklist (Smoke Test)

After installing a clone drive in a cabinet:

### Startup Verification
- [ ] Power on cabinet
- [ ] `start-aa.bat` launches automatically (or run manually)
- [ ] Backend starts (check port 8000)
- [ ] Gateway starts (check port 8787)
- [ ] UI loads in browser

### Identity Verification
- [ ] Cabinet prompts for or assigns new Device ID
- [ ] Device ID is unique (not same as Golden Drive)
- [ ] Cabinet Name is set or prompted

### Feature Verification
- [ ] Launch a game from library
- [ ] Pause screen triggers correctly
- [ ] Exit game returns to menu
- [ ] Scorekeeper records a score
- [ ] LED Blinky shows status (hardware or no-hardware graceful)
- [ ] Marquee displays (if hardware present)

### Shutdown Verification
- [ ] `stop-aa.bat` works
- [ ] Ports are released
- [ ] No orphan processes

---

## 13. Change Control

### Changes Requiring Codex Pre-Audit

Any change to:
- Startup scripts (`start-aa.bat`, `stop-aa.bat`)
- Port numbers or binding addresses
- Path constants or folder structure
- Gateway routing logic
- Authentication or security
- Supabase schema or RLS policies

### Changes Requiring Manual Signoff (Greg)

- New dependencies or packages
- Changes to identity/provisioning flow
- Changes to fleet update mechanism
- Any change to Golden Drive folder structure
- Removal of features or endpoints

### Changes That Can Proceed (With Verification)

- Bug fixes in existing features
- UI improvements (no routing changes)
- New endpoints (additive only)
- Documentation updates

---

## Appendix: Quick Command Reference

| Action | Command |
|--------|---------|
| Start services | `A:\Arcade Assistant Local\start-aa.bat` |
| Stop services | `A:\Arcade Assistant Local\stop-aa.bat` |
| Check backend | `curl http://127.0.0.1:8000/health` |
| Check gateway | `curl http://127.0.0.1:8787/api/health` |
| View backend logs | `A:\.aa\logs\backend.log` |
| View gateway logs | `A:\.aa\logs\gateway.log` |

---

*This contract is the operational truth. When in doubt, follow the contract.*
