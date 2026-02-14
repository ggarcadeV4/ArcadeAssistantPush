# Scorekeeper — Undo/Restore Evidence (2025-11-10)

## Verified
- `/api/local/scorekeeper/tournaments/create/apply` returns `backup_path` snapshots under `/backups/scorekeeper/`, enabling UI to keep handles for undo/restore.
- `/api/local/scorekeeper/undo` and `/api/local/scorekeeper/restore` run through the gateway with the required headers, log `action:"undo"|"restore"` entries, and respect sanctioned-path validation + pre-restore backups.
- Dry-run restore (`curl_restore_dry_run.txt`) reports `"dry_run": true` and performs no writes while still emitting a diff summary.

## Artifacts
- A:\preflight\evidence\scorekeeper\2025-11-10\preflight.md
- A:\preflight\evidence\scorekeeper\2025-11-10\ui_diff.patch
- A:\preflight\evidence\scorekeeper\2025-11-10\curl_create.txt
- A:\preflight\evidence\scorekeeper\2025-11-10\curl_undo.txt
- A:\preflight\evidence\scorekeeper\2025-11-10\curl_restore.txt
- A:\preflight\evidence\scorekeeper\2025-11-10\curl_restore_dry_run.txt
- A:\preflight\evidence\scorekeeper\2025-11-10\changes_excerpt.txt
- A:\preflight\evidence\scorekeeper\2025-11-10\ls_backups_scorekeeper.txt

## Notes
- Latest pre-restore snapshot captured at: `A:\backups\scorekeeper\20251110_112208\snapshot.json` (created automatically before the explicit restore).
- Stack ran with `.env` overrides `PORT=3000` and `AA_DRIVE_ROOT=/mnt/a` so the gateway + backend matched the acceptance script expectations.
