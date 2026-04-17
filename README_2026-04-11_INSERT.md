## 2026-04-11 — Infrastructure Stabilization: Campaigns 1–3 + Safety Model Hardening

We completed a major infrastructure-stabilization sequence across Arcade Assistant:

### Campaign 1 — Gateway Enclosure
- Removed direct frontend backend-bypass behavior.
- Removed direct frontend Supabase browser-client usage from active runtime paths.
- Reconciled backend port drift to the canonical `:8000` contract.
- Added the missing backend websocket termination point for `/api/local/hardware/ws/encoder-events`.
- Removed dead legacy Gunner panel code and cleaned stale backend-port guidance.

### Campaign 2 — Identity & Device-ID Standardization
- Centralized frontend device identity through `frontend/src/utils/identity.js`.
- Eliminated synthetic frontend device-id fallbacks such as `CAB-0001`, `cabinet-001`, `demo_001`, `controller_chuck`, and `unknown-device`.
- Removed unsanctioned localStorage-based device identity resolution.
- Standardized `x-device-id`, `x-panel`, and `x-scope` header usage across active frontend runtime paths.

### Campaign 3 — Path Determinism & Root Unification
- Aligned `.env` and `.aa/manifest.json` to the same `AA_DRIVE_ROOT`.
- Unified sanctioned-path bootstrap defaults through a shared constant source.
- Replaced backend and gateway runtime drive-root fallback drift with canonical helpers (`get_drive_root()`, `getDriveRoot()`, `requireDriveRoot()`, `app.locals.driveRoot`).
- Removed scoped hardcoded `A:\` / `W:\...` runtime fallback literals from active backend and gateway paths.

### Safety Model Hardening — Mutation Paths
Hardened additional config/data mutation surfaces so they better conform to preview/apply/backup/log expectations:
- `POST /api/local/config/restore` — now creates a fresh pre-restore backup snapshot before overwrite
- `PUT /api/local/profile/primary` — now has `POST /api/local/profile/primary/preview`
- `POST /api/local/controller/cascade/apply` — now has preview + persistent JSONL audit with device/panel context
- `POST /api/local/controller/mapping/set` — now has preview + dry-run support
- `DELETE /api/scores/reset/{rom_name}` — now supports dry-run and writes request-aware audit log entries with device/panel context

### Current project state
Infrastructure is substantially cleaner than at session start:
- Gateway enclosure is in place
- Frontend identity drift is removed
- Root/path determinism is largely unified
- Safety-model coverage has expanded on several remaining mutation paths

### Known deferred / backlog item
- LaunchBox LoRa GUI regression: light guns and American Laser Games reappeared in the Arcade Assistant GUI, but intended direction is still to keep them deferred from the AA frontend for now while leaving direct LaunchBox access intact.

---

