# Scorekeeper Undo/Restore — Preflight (2025-11-10)

## Backend observations
- `backend/routers/scorekeeper.py:281` defines `POST /submit/apply`, which already validates `x-scope`, checks sanctioned paths, creates backups via `create_backup`, and logs through `log_scorekeeper_change`.
- `backend/routers/scorekeeper.py:388` handles `POST /tournaments/create/apply` with similar scope validation + logging but no shared helper for restoring snapshots afterward.
- `backend/routers/scorekeeper.py:170-189` contains the reusable `log_scorekeeper_change()` helper; no complementary restore/undo utilities exist elsewhere in the router.
- `rg "scorekeeper/undo" backend/routers/scorekeeper.py` returned nothing, confirming there are currently no `/scorekeeper/undo` or `/scorekeeper/restore` endpoints.

## Frontend observations
- `frontend/src/panels/scorekeeper/ScoreKeeperPanel.jsx:1351-1413` drives score submission and only stores one `backup_path` coming back from `/submit/apply`.
- `frontend/src/panels/scorekeeper/ScoreKeeperPanel.jsx:649-689` exposes an `undoLast` helper that calls `http://localhost:8787/config/restore` directly, bypassing the gateway proxy and lacking any dry-run header support.
- There is no UI affordance for a general “Restore from backup” flow—only the single “Undo Last” button tied to the last score submit.

## Follow-ups before implementation
- Introduce `/scorekeeper/undo` and `/scorekeeper/restore` endpoints that mirror Console Wizard’s Preview→Apply→Restore symmetry, enforcing manifest-sanctioned files under `state/scorekeeper/`.
- Update the panel to call the new gateway-routed endpoints (`http://localhost:3000/api/local/scorekeeper/*`) with proper headers and expose both Undo + Restore buttons.
- Plan evidence capture under `A:\preflight\evidence\scorekeeper\2025-11-10\` per sprint spec (preflight, UI diff, curls, logs, backup listings).
