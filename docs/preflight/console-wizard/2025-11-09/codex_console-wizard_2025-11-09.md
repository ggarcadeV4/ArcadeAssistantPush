# Console Wizard — Restore Symmetry Evidence (2025-11-09)

## Verified
- Gateway `http://localhost:3000/api/local/console/retroarch/{preview|apply|restore}` returned healthy responses for profile `xbox_360`, including the cfg diff, target file, and backup handle `104031_config_retroarch_xbox_360_p1.cfg`.
- `A:\logs\changes.jsonl` now records `retroarch_config_preview`, `retroarch_config_apply`, and `retroarch_config_restore` entries with `panel:"console-wizard"` + the corresponding backup paths (see `changes_excerpt.txt`).
- Dry-run restore responded with `"dry_run": true` and zero writes, confirming rollback safety while still referencing the original backup payload.

## Artifacts
- A:\preflight\evidence\console-wizard\2025-11-09\curl_preview.txt
- A:\preflight\evidence\console-wizard\2025-11-09\curl_apply.txt
- A:\preflight\evidence\console-wizard\2025-11-09\curl_restore.txt
- A:\preflight\evidence\console-wizard\2025-11-09\curl_restore_dry_run.txt
- A:\preflight\evidence\console-wizard\2025-11-09\extracted_backup_path.txt
- A:\preflight\evidence\console-wizard\2025-11-09\changes_excerpt.txt
- A:\preflight\evidence\console-wizard\2025-11-09\ls_backups_retroarch.txt
- A:\preflight\evidence\console-wizard\2025-11-09\extracted_target_file.txt

## Notes
- Pre-restore snapshot created at: A:\backups\20251110\104035_config_retroarch_xbox_360_p1.cfg
