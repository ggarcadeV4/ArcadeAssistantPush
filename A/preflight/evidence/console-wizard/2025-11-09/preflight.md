# Console Wizard Preflight — 2025-11-09

## Backend
- backend/routers/console.py lines 404-520 expose POST /retroarch/config/preview and POST /retroarch/config/apply; there is no restore endpoint defined anywhere in this router.
- Shared helpers already in use: log_console_wizard_change (lines 58-110) appends to logs/changes.jsonl, create_backup in backend/services/backup.py handles timestamped snapshots, and require_scope plus is_allowed_file enforce sanctioned-path writes.
- startup_manager.initializeApp stores drive_root, manifest, backup_on_write, and dry_run_default on app.state, so new routes should follow the same effective_dry pattern as backend/routers/config_ops.py.

## Frontend
- frontend/src/panels/console-wizard/ConsoleWizardPanel.jsx currently issues preview/apply (handleApplyConfig around lines 398-450) but only displays the returned target_file/backup_path; there is no Restore UI or API call.
